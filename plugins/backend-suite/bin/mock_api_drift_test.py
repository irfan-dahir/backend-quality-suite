#!/usr/bin/env python3
"""Tests for the mock-API drift defects measured on a real consumer (issue
#117 (an optional model field reported critical when nothing could
carry one) and issue #116 (a fixture-wins sync deleting correct data).

Stdlib-only (`unittest`), matching this directory's convention — no pytest.

## Why these are subprocess tests against a synthetic project

`backend_suite/engine/mockapi/*` resolves its project root, profile, pipeline
directory and three providers **at import time**, so the modules cannot be
imported twice against two different trees in one process. Each case therefore
builds a complete throwaway consumer project in a temp directory — profile,
mock-API config, contract registry, Dart model, fixture, Postman collection,
API doc — and runs the real script against it with `CLAUDE_PROJECT_DIR` set.
Slower than importing, but it exercises the actual entry point and the actual
exit codes, which are the contract both issues are about.

Nothing here reads the suite's own repository, and no value below is a literal
borrowed from any consumer: `manuscripts` / `weekday` / `cadence` are this
file's own fixture vocabulary, drawn from the same made-up archive-catalogue
domain the mock-API engine's worked examples use, so a reader moving between
them stays inside one fictional product.

## The pairing rule

Every case that proves something is NOT reported is paired with the case it
must not have swallowed. A fix that silences a check is not a fix, so:

  * #117: `test_absent_optional_field_not_reported_when_nothing_exercises_it`
    is paired with `test_absent_optional_field_still_critical_when_exercised`
    and `test_missing_required_field_is_still_critical`.
  * #116: `test_write_refuses_when_sync_would_delete_target_only_data` is
    paired with `test_richer_fixture_still_propagates_outward`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
PLUGIN = BIN.parent
MOCKAPI = PLUGIN / "backend_suite" / "engine" / "mockapi"
AUDIT = MOCKAPI / "audit_mock_api.py"
SYNC = MOCKAPI / "sync_mock_api.py"
GENERATE = MOCKAPI / "generate_openapi.py"

CONTRACT = "manuscripts"
ANCHOR = "### GET /manuscripts"

# `weekday` is optional and conditioned on `cadence`; the rest are required.
MODEL_SRC = """
class Item {
  factory Item.fromJson(Map<String, dynamic> json) => Item(
    id: json['id'] as String,
    name: json['name'] as String,
    cadence: json['cadence'] as String,
    weekday: json['weekday'] as int?,
  );
}
"""

WEEKLY_CONDITION = {"field": "cadence", "equals": "weekly"}


DECLARED_SERVERS = {"dev": "https://mock.example.invalid"}


def build_project(
    root: Path,
    *,
    records: list[dict],
    mock_records: list[dict] | None = None,
    optional_fields: dict | None = None,
    servers: dict | None = DECLARED_SERVERS,
    project_name: str | None = "Synthetic",
) -> Path:
    """A complete synthetic consumer project rooted at `root`.

    `records` are the fixture's records. `mock_records` are what the Postman
    example and the API doc's example block hold; `None` means "identical to
    the fixture", which is the in-sync baseline every drift case perturbs.
    """
    if root.exists():
        shutil.rmtree(root)
    mock_records = records if mock_records is None else mock_records

    (root / ".backend-suite").mkdir(parents=True)
    project: dict = {} if project_name is None else {"name": project_name}
    (root / ".backend-suite" / "profile.json").write_text(
        json.dumps({"project": project,
                    "pipelines": {"mockApi": "mock_api"}}, indent=2))

    contract: dict = {
        "model_file": "lib/item_model.dart",
        "fixture": "test/fixtures/items.json",
        "fixture_list_key": "items",
        "mock_folder": "Items",
        "mock_request": "GET Items",
        "api_doc_anchor": ANCHOR,
    }
    if optional_fields is not None:
        contract["optional_fields"] = optional_fields

    (root / "mock_api").mkdir()
    config: dict = {
        "schema_provider": "dart_fromjson",
        "doc_provider": {"kind": "markdown_api", "file": "docs/API.md"},
        "mock_provider": {"kind": "postman", "file": "mock_api/collection.json"},
    }
    if servers is not None:
        config["servers"] = servers
    (root / "mock_api" / "config.json").write_text(json.dumps(config, indent=2))
    (root / "mock_api" / "contracts.json").write_text(
        json.dumps({CONTRACT: contract}, indent=2))

    (root / "lib").mkdir()
    (root / "lib" / "item_model.dart").write_text(MODEL_SRC)

    (root / "test" / "fixtures").mkdir(parents=True)
    (root / "test" / "fixtures" / "items.json").write_text(
        json.dumps({"items": records}, indent=2))

    body = json.dumps({"data": mock_records}, indent=2)
    (root / "mock_api" / "collection.json").write_text(json.dumps({
        "item": [{"name": "Items", "item": [
            {"name": "GET Items", "response": [{"body": body}]}]}]
    }, indent=2))

    (root / "docs").mkdir()
    (root / "docs" / "API.md").write_text(
        f"{ANCHOR}\n\n| Field | Type | Notes |\n|---|---|---|\n"
        "| `id` | String | |\n| `name` | String | |\n"
        "| `cadence` | String | |\n| `weekday` | int? | |\n\n"
        "```json\n" + body + "\n```\n")
    return root


def run_script(script: Path, root: Path, args: list[str]):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=root, env=env, capture_output=True, text=True)


def audit(root: Path):
    """(exit code, findings list) for a scoped audit of the one contract."""
    proc = run_script(AUDIT, root, [CONTRACT])
    findings_file = root / ".backend-suite" / "mock-api-findings.json"
    findings = json.loads(findings_file.read_text()) if findings_file.is_file() else []
    return proc, [f for f in findings if f.get("contract") == CONTRACT]


def of_check(findings: list[dict], check: str) -> list[dict]:
    return [f for f in findings if f["check"] == check]


DAILY = {"id": "itm_a", "name": "Codex Aureus", "cadence": "daily"}
WEEKLY = {"id": "itm_b", "name": "Ledger of Tides", "cadence": "weekly"}
WEEKLY_WITH_DAY = {**WEEKLY, "weekday": 1}


class TempProjectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="mockapi-drift-")
        self.root = Path(self._tmp) / "proj"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class OptionalFieldSeverityTest(TempProjectTest):
    """Issue #117 — the false positive, and the true positives it must keep."""

    def test_absent_optional_field_not_reported_when_nothing_exercises_it(self):
        # The measured case: a fixture with no weekly record at all. Nothing
        # in it could carry a `weekday`, so there is no edit that resolves a
        # finding about one.
        build_project(self.root, records=[DAILY],
                      optional_fields={"weekday": {"when": WEEKLY_CONDITION}})
        proc, findings = audit(self.root)
        self.assertEqual(of_check(findings, "model_vs_fixture"), [])
        self.assertEqual(of_check(findings, "model_vs_mock"), [])
        self.assertEqual([f["severity"] for f in findings if f["check"] != "model_vs_doc_table"
                          and f["severity"] == "critical"], [])
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_not_exercised_is_announced_rather_than_silent(self):
        # The governing principle: a check that did not run must not be
        # indistinguishable from one that ran and passed.
        build_project(self.root, records=[DAILY],
                      optional_fields={"weekday": {"when": WEEKLY_CONDITION}})
        proc, findings = audit(self.root)
        notices = of_check(findings, "optional_field_not_exercised")
        self.assertEqual(len(notices), 1, "exactly one notice per field, not one per direction")
        self.assertEqual(notices[0]["severity"], "fyi")
        self.assertIn("weekday", notices[0]["detail"])
        self.assertIn("optional_field_not_exercised", proc.stdout,
                      "the notice must reach the run's own output, not only the file")

    def test_absent_optional_field_still_critical_when_exercised(self):
        # The pair. One weekly record with no weekday: the audit must still
        # gate, or the fix above would have been a silencing.
        build_project(self.root, records=[DAILY, WEEKLY],
                      optional_fields={"weekday": {"when": WEEKLY_CONDITION}})
        proc, findings = audit(self.root)
        fixture_side = of_check(findings, "model_vs_fixture")
        self.assertEqual(len(fixture_side), 1)
        self.assertEqual(fixture_side[0]["severity"], "critical")
        self.assertIn("weekday", fixture_side[0]["detail"])
        self.assertEqual(of_check(findings, "optional_field_not_exercised"), [])
        self.assertEqual(proc.returncode, 1)

    def test_missing_required_field_is_still_critical(self):
        # The other pair: an undeclared field is required, and its absence is
        # a contract break exactly as before this change.
        no_name = {k: v for k, v in DAILY.items() if k != "name"}
        build_project(self.root, records=[no_name],
                      optional_fields={"weekday": {"when": WEEKLY_CONDITION}})
        proc, findings = audit(self.root)
        breaks = [f for f in of_check(findings, "model_vs_fixture")
                  if "'name'" in f["detail"]]
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["severity"], "critical")
        self.assertEqual(proc.returncode, 1)

    def test_undeclared_optionality_keeps_the_old_behaviour(self):
        # No declaration means no change: this fix cannot quiet a project that
        # has not said anything, so it can never silence a check by upgrade.
        build_project(self.root, records=[DAILY], optional_fields=None)
        proc, findings = audit(self.root)
        self.assertEqual(len(of_check(findings, "model_vs_fixture")), 1)
        self.assertEqual(of_check(findings, "model_vs_fixture")[0]["severity"], "critical")
        self.assertEqual(len(of_check(findings, "model_vs_mock")), 1)
        self.assertEqual(proc.returncode, 1)

    def test_unconditionally_optional_field_downgrades_instead_of_vanishing(self):
        # `{}` — optional, no condition. Still reported (absence is still
        # information), but not as a contract break.
        build_project(self.root, records=[DAILY], optional_fields={"weekday": {}})
        proc, findings = audit(self.root)
        fixture_side = of_check(findings, "model_vs_fixture")
        self.assertEqual(len(fixture_side), 1)
        self.assertEqual(fixture_side[0]["severity"], "should_fix")
        self.assertEqual(proc.returncode, 0)

    def test_condition_can_match_a_set_of_values(self):
        build_project(self.root, records=[DAILY, WEEKLY],
                      optional_fields={"weekday": {
                          "when": {"field": "cadence", "in": ["weekly", "biweekly"]}}})
        _, findings = audit(self.root)
        self.assertEqual(len(of_check(findings, "model_vs_fixture")), 1)

    def test_present_optional_field_reports_nothing_at_all(self):
        build_project(self.root, records=[DAILY, WEEKLY_WITH_DAY],
                      optional_fields={"weekday": {"when": WEEKLY_CONDITION}})
        proc, findings = audit(self.root)
        self.assertEqual(of_check(findings, "model_vs_fixture"), [])
        self.assertEqual(of_check(findings, "optional_field_not_exercised"), [])
        self.assertEqual(proc.returncode, 0)


class MalformedDeclarationTest(TempProjectTest):
    """A declaration the audit cannot understand is a refusal, never a pass.

    Cannot-determine is exit 2. Degrading to "assume required" would flood the
    run with criticals from a premise it never established; degrading to
    "assume optional" would hide real breaks. Both read as a result.
    """

    def _refuses(self, optional_fields, expect_in_message):
        build_project(self.root, records=[DAILY], optional_fields=optional_fields)
        proc = run_script(AUDIT, self.root, [CONTRACT])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("REFUSING", proc.stderr)
        self.assertIn(expect_in_message, proc.stderr)

    def test_condition_without_a_comparison_refuses(self):
        self._refuses({"weekday": {"when": {"field": "cadence"}}}, "exactly one")

    def test_condition_without_a_field_refuses(self):
        self._refuses({"weekday": {"when": {"equals": "weekly"}}}, "'field'")

    def test_unknown_condition_key_refuses(self):
        self._refuses(
            {"weekday": {"when": {"field": "cadence", "matches": "week.*"}}},
            "unknown key")

    def test_unknown_spec_key_refuses(self):
        self._refuses({"weekday": {"unless": {"field": "cadence"}}}, "unknown key")

    def test_non_object_spec_refuses(self):
        self._refuses({"weekday": True}, "must be an object")


class SyncLossRefusalTest(TempProjectTest):
    """Issue #116 — a fixture-wins sync must not delete data only the target
    side holds, and must still propagate a legitimately richer fixture."""

    def _collection_body(self) -> dict:
        col = json.loads((self.root / "mock_api" / "collection.json").read_text())
        return json.loads(col["item"][0]["item"][0]["response"][0]["body"])

    def test_write_refuses_when_sync_would_delete_target_only_data(self):
        # The measured shape: the FIXTURE is the rotted side. It has lost the
        # weekday that the mock and docs still carry correctly.
        build_project(self.root, records=[DAILY, WEEKLY],
                      mock_records=[DAILY, WEEKLY_WITH_DAY])
        before = self._collection_body()
        proc = run_script(SYNC, self.root, [CONTRACT, "--write"])
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("REFUSING", proc.stderr)
        self.assertIn("weekday", proc.stderr)
        self.assertEqual(self._collection_body(), before,
                         "a refusal must not have written anything")

    def test_dry_run_names_what_a_write_would_delete(self):
        build_project(self.root, records=[DAILY, WEEKLY],
                      mock_records=[DAILY, WEEKLY_WITH_DAY])
        proc = run_script(SYNC, self.root, [CONTRACT])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("weekday", proc.stdout)
        self.assertIn("direction: fixture ->", proc.stderr,
                      "every run states which way data flows")

    def test_richer_fixture_still_propagates_outward(self):
        # The pair. The refusal above must not have cost the common, correct
        # case: a fixture that legitimately grew must still reach the mock.
        build_project(self.root, records=[DAILY, WEEKLY_WITH_DAY],
                      mock_records=[DAILY, WEEKLY])
        proc = run_script(SYNC, self.root, [CONTRACT, "--write"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._collection_body()["data"][1].get("weekday"), 1)

    def test_allow_loss_is_the_only_way_through(self):
        build_project(self.root, records=[DAILY, WEEKLY],
                      mock_records=[DAILY, WEEKLY_WITH_DAY])
        proc = run_script(SYNC, self.root, [CONTRACT, "--write", "--allow-loss"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("weekday", self._collection_body()["data"][1])
        self.assertIn("allow-loss", proc.stdout,
                      "an override must still say what it destroyed")


class DifferFindingNamesNoDirectionTest(TempProjectTest):
    """Issue #116's other half: a finding that measures disagreement must not
    also pronounce on authority by naming a one-way repair."""

    def test_values_finding_shows_both_sides_and_recommends_no_sync(self):
        build_project(self.root, records=[DAILY, WEEKLY],
                      mock_records=[DAILY, WEEKLY_WITH_DAY])
        _, findings = audit(self.root)
        values = of_check(findings, "mock_vs_fixture_values")
        self.assertEqual(len(values), 1)
        detail = values[0]["detail"]
        self.assertNotIn("sync_mock_api", detail,
                         "naming a one-way repair is how #116 lost data")
        self.assertIn("mock", detail)
        self.assertIn("fixture", detail)
        self.assertIn("weekday", detail)


class SpecIdentityFromProjectConfigTest(TempProjectTest):
    """The generated spec's `servers` and `info.title` used to be module
    constants in the universal engine — one consumer's Postman mock-server
    endpoint and one consumer's product name — so every other project's spec
    named, and offered to fire live requests at, somebody else's service.

    Both now come from the project under audit. The pairing rule applies: the
    case proving nothing is emitted when a project declares no server is paired
    with the case proving the absence is REPORTED, because an omitted `servers`
    block that nothing mentions is exactly the silence this suite forbids.
    """

    def _spec(self) -> dict:
        proc = run_script(GENERATE, self.root, [])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads((self.root / "mock_api" / "openapi.json").read_text())

    def test_declared_servers_reach_the_spec(self):
        build_project(self.root, records=[DAILY])
        self.assertEqual(
            self._spec()["servers"],
            [{"url": DECLARED_SERVERS["dev"], "description": "dev"}])

    def test_undeclared_servers_omits_the_key_rather_than_inventing_one(self):
        build_project(self.root, records=[DAILY], servers=None)
        self.assertNotIn("servers", self._spec())

    def test_undeclared_servers_is_reported_by_the_full_audit(self):
        # The pair for the case above. A spec with nowhere to send a request
        # must not read the same as a correctly configured one.
        build_project(self.root, records=[DAILY], servers=None)
        run_script(AUDIT, self.root, [])
        findings = json.loads((self.root / ".backend-suite" / "mock-api-findings.json").read_text())
        undeclared = of_check(findings, "openapi_servers_undeclared")
        self.assertEqual(len(undeclared), 1, findings)
        self.assertIn("config.json", undeclared[0]["detail"])

    def test_declared_servers_report_nothing(self):
        build_project(self.root, records=[DAILY])
        run_script(AUDIT, self.root, [])
        findings = json.loads((self.root / ".backend-suite" / "mock-api-findings.json").read_text())
        self.assertEqual(of_check(findings, "openapi_servers_undeclared"), [])

    def test_title_comes_from_the_project_profile(self):
        build_project(self.root, records=[DAILY], project_name="Archive Portal")
        self.assertEqual(self._spec()["info"]["title"], "Archive Portal API Reference")

    def test_nameless_project_refuses_rather_than_titling_itself(self):
        build_project(self.root, records=[DAILY], project_name=None)
        proc = run_script(GENERATE, self.root, [])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("project.name", proc.stdout + proc.stderr)

    def test_no_engine_module_holds_a_mock_server_url(self):
        """The literal itself, guarded so it cannot come back by copy-paste."""
        offenders = [
            str(f.relative_to(MOCKAPI))
            for f in MOCKAPI.rglob("*.py")
            if re.search(r"https?://[^\s\"']+", f.read_text())
        ]
        self.assertEqual(offenders, [],
                         "a base URL in the engine is one project's server for everyone")


class ReportPathTest(TempProjectTest):
    """The raw report lands in .backend-suite/, not <pipelines.mockApi>/ at the
    project root (a tracked file every run used to dirty); --out still wins."""

    def test_default_is_inside_dot_backend_suite(self):
        build_project(self.root, records=[DAILY])
        run_script(AUDIT, self.root, [])
        self.assertTrue((self.root / ".backend-suite" / "mock-api-findings.json").is_file())
        self.assertFalse((self.root / "mock_api" / "findings.json").exists())

    def test_out_still_wins(self):
        build_project(self.root, records=[DAILY], servers=None)
        run_script(AUDIT, self.root, ["--out", "scratch/m.json"])
        planted = json.loads((self.root / "scratch" / "m.json").read_text())
        # The planted drift (no servers declared) survives the move.
        self.assertEqual(len(of_check(planted, "openapi_servers_undeclared")), 1)
        self.assertFalse((self.root / ".backend-suite" / "mock-api-findings.json").exists())

    def test_scaffolded_gitignore_covers_it(self):
        text = (Path(__file__).resolve().parent.parent
                / "templates/dot-backend-suite/gitignore.template").read_text()
        self.assertIn("\nmock-api-findings.json\n", text)


class NoProfileRefuses(unittest.TestCase):
    """A marker dir with no profile.json is "could not look" (2), never 1."""

    def test_missing_profile_is_exit_2_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / ".backend-suite").mkdir()
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            r = subprocess.run([sys.executable, str(AUDIT)], cwd=tmp, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("REFUSED", r.stderr)
            self.assertIn("no profile", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
