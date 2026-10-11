#!/usr/bin/env python3
"""Tests for export_sarif.py and backend_suite.engine.sarif / json_schema_lite.

The claim under test is not "it emits JSON" but two harder ones:

  1. The output conforms to the official SARIF 2.1.0 schema (vendored, hash-
     pinned) — and the validator doing the checking can actually fail, proven by
     feeding it broken logs. A validator that passes everything would make every
     other assertion here vacuous.
  2. An audit that could not check never vanishes and never reads as clean: it
     is a run with `executionSuccessful: false` and a notification naming why.

    python3 plugins/backend-suite/bin/export_sarif_test.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import export_sarif  # noqa: E402
from backend_suite.engine import audit_discovery  # noqa: E402
from backend_suite.engine import json_schema_lite  # noqa: E402
from backend_suite.engine import sarif  # noqa: E402

SCHEMA = json.loads(export_sarif.SCHEMA.read_text())


def write_env(repo: Path, name: str, payload: dict) -> None:
    d = repo / ".backend-suite/findings"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, "audit": name, **payload}))


def run_named(log: dict, name: str) -> dict:
    hits = [r for r in log["runs"] if r["tool"]["driver"]["name"] == f"backend-suite/{name}"]
    assert len(hits) == 1, f"expected one run for {name}, got {len(hits)}"
    return hits[0]


TOKENS = {"reports": "violations", "scanned": 4, "findings": [
    {"audit": "tokens", "category": "color", "severity": "critical",
     "summary": "hardcoded colour", "file": "lib/ui/a b.dart", "line": 7},
    {"audit": "tokens", "category": "Spacing Value", "severity": "should-fix",
     "summary": "hardcoded spacing", "file": "./lib/b.dart", "line": 2},
    {"audit": "tokens", "category": "radius", "severity": "fyi", "summary": "no file"},
]}


class VendoredSchema(unittest.TestCase):
    def test_hash_matches_notice(self):
        notice = (export_sarif.SCHEMA.parent / "NOTICE").read_text()
        digest = hashlib.sha256(export_sarif.SCHEMA.read_bytes()).hexdigest()
        self.assertIn(digest, notice, "vendored schema changed without updating NOTICE")

    def test_is_the_official_2_1_0_schema(self):
        self.assertIn("sarif-schema-2.1.0", SCHEMA["id"])
        self.assertEqual(SCHEMA["properties"]["version"]["enum"], ["2.1.0"])


class ValidatorCanFail(unittest.TestCase):
    def setUp(self):
        self.good = sarif.build_log([sarif.build_run(
            "tokens", envelope=TOKENS, status=None, repo=Path("/nonexistent"))])
        self.assertEqual(json_schema_lite.errors(self.good, SCHEMA), [])

    def broken(self, mutate) -> list[str]:
        log = copy.deepcopy(self.good)
        mutate(log)
        return json_schema_lite.errors(log, SCHEMA)

    def test_rejects_wrong_version(self):
        self.assertTrue(self.broken(lambda l: l.update(version="2.0.0")))

    def test_rejects_bad_level(self):
        self.assertTrue(self.broken(lambda l: l["runs"][0]["results"][0].update(level="critical")))

    def test_rejects_line_zero(self):
        def m(l):
            l["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] = 0
        self.assertTrue(self.broken(m))

    def test_rejects_invocation_without_execution_successful(self):
        self.assertTrue(self.broken(lambda l: l["runs"][0]["invocations"][0].pop("executionSuccessful")))

    def test_rejects_unknown_top_level_key(self):
        self.assertTrue(self.broken(lambda l: l.update(bogus=1)))

    def test_refuses_unknown_keyword_rather_than_ignoring_it(self):
        with self.assertRaises(json_schema_lite.UnsupportedKeyword):
            json_schema_lite.errors({}, {"not": {"type": "object"}})


class Mapping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        write_env(self.repo, "tokens", TOKENS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_results_levels_rules_and_locations(self):
        log = export_sarif.build(self.repo, None)
        self.assertEqual(json_schema_lite.errors(log, SCHEMA), [])
        run = run_named(log, "tokens")
        self.assertTrue(run["invocations"][0]["executionSuccessful"])
        levels = [r["level"] for r in run["results"]]
        self.assertEqual(levels, ["error", "warning", "note"])
        ids = [r["ruleId"] for r in run["results"]]
        self.assertEqual(ids, ["tokens/color", "tokens/spacing-value", "tokens/radius"])
        self.assertEqual({r["id"] for r in run["tool"]["driver"]["rules"]}, set(ids))
        loc = run["results"][0]["locations"][0]["physicalLocation"]
        self.assertEqual(loc["artifactLocation"], {"uri": "lib/ui/a%20b.dart", "uriBaseId": "%SRCROOT%"})
        self.assertEqual(loc["region"], {"startLine": 7})
        self.assertEqual(run["results"][1]["locations"][0]["physicalLocation"]
                         ["artifactLocation"]["uri"], "lib/b.dart")
        self.assertNotIn("locations", run["results"][2])

    def test_rule_ids_and_fingerprints_are_stable_across_runs_and_line_moves(self):
        a = run_named(export_sarif.build(self.repo, None), "tokens")
        moved = copy.deepcopy(TOKENS)
        moved["findings"][0]["line"] = 40
        write_env(self.repo, "tokens", moved)
        b = run_named(export_sarif.build(self.repo, None), "tokens")
        self.assertEqual([r["ruleId"] for r in a["results"]], [r["ruleId"] for r in b["results"]])
        self.assertEqual([r["partialFingerprints"] for r in a["results"]],
                         [r["partialFingerprints"] for r in b["results"]])

    def test_every_discovered_audit_gets_a_run(self):
        log = export_sarif.build(self.repo, None)
        names = {r["tool"]["driver"]["name"] for r in log["runs"]}
        for script in audit_discovery.discover(BIN):
            name = audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_")
            self.assertIn(f"backend-suite/{name}", names)


class CouldNotCheckNeverVanishes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def assertFailedWith(self, run: dict, needle: str):
        inv = run["invocations"][0]
        self.assertIs(inv["executionSuccessful"], False)
        texts = " ".join(n["message"]["text"] for n in inv["toolExecutionNotifications"])
        self.assertIn(needle, texts)
        self.assertEqual(run["results"], [])

    def plant_disabled(self):
        # The registry ships empty (its two entries left with their scripts
        # when this repo re-domained), so the mechanism is exercised by
        # planting one entry against a live audit in-process.
        audit_discovery.DISABLED["audit_doc_staleness"] = {
            "reason": "disabled - planted for this test", "detail": "d", "pathBack": "p"}
        return "audit_doc_staleness", audit_discovery.DISABLED["audit_doc_staleness"]

    def test_disabled_audits_are_failed_invocations_with_their_reason(self):
        write_env(self.repo, "tokens", TOKENS)
        stem, entry = self.plant_disabled()
        try:
            log = export_sarif.build(self.repo, None)
            script = next(s for s in audit_discovery.discover(BIN) if s.stem == stem)
            name = audit_discovery.envelope_name(script) or stem.removeprefix("audit_")
            self.assertFailedWith(run_named(log, name), "DISABLED")
            self.assertFailedWith(run_named(log, name), entry["reason"])
        finally:
            audit_discovery.DISABLED.pop(stem, None)

    def test_disabled_audit_with_stale_envelope_still_contributes_nothing(self):
        stem, _entry = self.plant_disabled()
        try:
            script = next(s for s in audit_discovery.discover(BIN) if s.stem == stem)
            name = audit_discovery.envelope_name(script) or stem.removeprefix("audit_")
            write_env(self.repo, name, {"reports": "violations", "scanned": 1, "findings": [
                {"audit": name, "category": "x", "severity": "critical", "summary": "stale"}]})
            self.assertFailedWith(run_named(export_sarif.build(self.repo, None), name), "DISABLED")
        finally:
            audit_discovery.DISABLED.pop(stem, None)

    def test_never_collected_audit_is_a_failed_invocation(self):
        write_env(self.repo, "tokens", TOKENS)
        run = run_named(export_sarif.build(self.repo, None), "doc-staleness")
        self.assertFailedWith(run, "does NOT mean clean")

    def test_health_refused_ignores_stale_envelope(self):
        write_env(self.repo, "tokens", TOKENS)
        health = {"audits": [{"audit": "audit_tokens", "status": "refused", "exitCode": 2,
                              "message": "profile does not set adapters.lang — INERT"}]}
        log = export_sarif.build(self.repo, health)
        self.assertEqual(json_schema_lite.errors(log, SCHEMA), [])
        run = run_named(log, "tokens")
        self.assertFailedWith(run, "adapters.lang")
        self.assertEqual(run["invocations"][0]["exitCode"], 2)

    def test_health_crashed_and_disabled(self):
        health = {"audits": [
            {"audit": "audit_tokens", "status": "crashed", "exitCode": None, "message": "boom"},
            {"audit": "audit_copy", "status": "disabled", "disabledDetail": "measured wrong"}]}
        log = export_sarif.build(self.repo, health)
        self.assertFailedWith(run_named(log, "tokens"), "crashed")
        self.assertFailedWith(run_named(log, "copy"), "measured wrong")

    def test_empty_sweeps_are_not_clean(self):
        write_env(self.repo, "a", {"reports": "violations", "findings": []})
        write_env(self.repo, "b", {"reports": "checks", "scanned": 3, "findings": []})
        write_env(self.repo, "c", {"reports": "violations", "scanned": 9, "findings": []})
        log = export_sarif.build(self.repo, None, scripts=[])
        self.assertFailedWith(run_named(log, "a"), "nothing recorded as scanned")
        self.assertFailedWith(run_named(log, "b"), "not a pass")
        self.assertIs(run_named(log, "c")["invocations"][0]["executionSuccessful"], True)

    def test_checks_polarity_exports_failures_and_passes(self):
        write_env(self.repo, "contrast", {"reports": "checks", "findings": [
            {"audit": "contrast", "category": "pair", "severity": "critical",
             "summary": "fg/bg 2.1:1", "passed": False},
            {"audit": "contrast", "category": "pair", "severity": "fyi",
             "summary": "fg/bg 7:1", "passed": True}]})
        log = export_sarif.build(self.repo, None, scripts=[])
        self.assertEqual(json_schema_lite.errors(log, SCHEMA), [])
        kinds = [r.get("kind", "fail") for r in run_named(log, "contrast")["results"]]
        self.assertEqual(kinds, ["fail", "pass"])


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(BIN / "export_sarif.py"), *args],
                              capture_output=True, text=True)

    def test_nothing_to_export_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("--repo", tmp)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("not a clean result", proc.stderr)

    def test_validate_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_env(Path(tmp), "tokens", TOKENS)
            out = Path(tmp) / "o.sarif"
            proc = self.run_cli("--repo", tmp, "--validate", "--out", str(out))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(out.read_text())["version"], "2.1.0")
            self.assertIn("could not check", proc.stderr)


if __name__ == "__main__":
    unittest.main()
