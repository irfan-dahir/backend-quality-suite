#!/usr/bin/env python3
"""The five audits retrofitted onto the common findings envelope, tested as a set.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_findings_envelope_test.py"

`audit_api_consistency`, `audit_claude_md_drift`, `audit_doc_staleness`,
`audit_proposal_status` and `audit_prose_flags` each wrote their own output and
nothing else, so `/quality-debt` could not grade them, `repo_health.py` reported them `unclear`,
and `mcp/audit_server.py` returned their raw stdout tagged `"structured":
false`. A third of the suite was invisible to its own roll-up — the governing
principle's failure mode at the dashboard level.

## Why every case plants a defect

A 0-finding envelope proves nothing: an audit that writes `{"findings": []}`
because it caught nothing and one that writes it because it swept nothing
produce the same bytes. So each audit here is run twice — once against a clean
fixture and once against the same fixture with something it is specifically
supposed to catch planted in it — and the test asserts the planted thing
arrives in the envelope, by category and severity, not merely that a count went
up.

## Why every case also asserts the control

`--findings` is additive by contract (backend_suite/engine/findings.py's module
docstring) and these scripts carry exit contracts a consumer's CI may grade on.
So each case runs the audit with and without the flag and asserts that stdout,
stderr and the exit code are byte-identical between the two — the envelope is a
side file, never a change in what the audit reports.

Subprocesses rather than imports throughout: several of these resolve
`project_root()` at *import* time, so a fixture can only be pointed at through
`CLAUDE_PROJECT_DIR` in a child process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN.parents[0]))

from backend_suite.engine import audit_discovery as A  # noqa: E402

# The seven, and the envelope name each is expected to write under. Hand-written
# here on purpose: this is the assertion, and `envelope_name()` is what is being
# asserted against. Deriving it from the function under test would test nothing.
EXPECTED_ENVELOPE_NAMES = {
    "audit_api_consistency": "api-consistency",
    "audit_claude_md_drift": "claude-md-drift",
    "audit_doc_staleness": "doc-staleness",
    "audit_proposal_status": "proposal-status",
    "audit_prose_flags": "prose-flags",
}


def run(script: str, args: list[str], repo: Path | None = None):
    env = dict(os.environ)
    if repo is not None:
        env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{script}.py"), *args],
                          capture_output=True, text=True, env=env)


def envelope(repo: Path, name: str) -> dict:
    return json.loads((repo / ".backend-suite" / "findings" / f"{name}.json").read_text())


def categories(data: dict) -> set[str]:
    return {f["category"] for f in data["findings"]}


class EnvelopeContract(unittest.TestCase):
    """Shape assertions that hold for every envelope any of the seven writes."""

    def assert_well_formed(self, data: dict, audit: str):
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["audit"], audit)
        self.assertEqual(data["reports"], "violations")
        self.assertIsInstance(data["findings"], list)
        # Not optional for any of the seven: `summarize()` grades a
        # zero-finding envelope with no `scanned` as "?" rather than "A",
        # precisely so an audit that swept nothing cannot read as clean.
        self.assertIn("scanned", data)
        for finding in data["findings"]:
            self.assertEqual(finding["audit"], audit)
            self.assertIn(finding["severity"], ("critical", "should-fix", "fyi"))
            self.assertTrue(finding["summary"].strip(),
                            "a finding with an empty summary is a count, not a finding")
            self.assertTrue(finding["category"].strip())

    def assert_control_unchanged(self, script: str, args: list[str],
                                 findings_args: list[str], repo: Path | None = None):
        """The envelope is additive: same stdout, same stderr, same exit code."""
        without = run(script, args, repo)
        with_flag = run(script, args + findings_args, repo)
        self.assertEqual(without.returncode, with_flag.returncode,
                         f"{script}: --findings changed the exit code")
        self.assertEqual(without.stdout, with_flag.stdout,
                         f"{script}: --findings changed stdout")
        self.assertEqual(without.stderr, with_flag.stderr,
                         f"{script}: --findings changed stderr")
        return without


class EnvelopeNamesAreDiscoverable(unittest.TestCase):
    """`envelope_name()` parses the script's own source, so an unusual call shape
    returns None silently and every dashboard then reads a path the audit never
    wrote to. Asserted per audit rather than in bulk so a regression names itself.
    """

    def test_all_seven_support_the_flag(self):
        for stem in sorted(EXPECTED_ENVELOPE_NAMES):
            with self.subTest(stem):
                self.assertTrue(A.supports_findings_flag(BIN / f"{stem}.py"))

    def test_all_seven_resolve_to_the_expected_name(self):
        for stem, expected in sorted(EXPECTED_ENVELOPE_NAMES.items()):
            with self.subTest(stem):
                self.assertEqual(A.envelope_name(BIN / f"{stem}.py"), expected)

    def test_every_discovered_audit_now_writes_an_envelope(self):
        """The measured problem this file exists to close: 12 of 19, not 19 of 19.

        Asserted over `discover()` rather than over the seven, so adding a
        nineteenth audit without an envelope fails here instead of being noticed
        the next time someone runs /quality-debt and sees two-thirds of a picture.
        """
        missing = [s.stem for s in A.discover() if not A.supports_findings_flag(s)]
        self.assertEqual(missing, [])
        nameless = [s.stem for s in A.discover() if A.envelope_name(s) is None]
        self.assertEqual(nameless, [])


class DocStaleness(unittest.TestCase, ):
    """A doc whose own stated date is long past the threshold."""

    def _repo(self, tmp: str, date: str) -> Path:
        repo = Path(tmp)
        (repo / "docs").mkdir(parents=True, exist_ok=True)
        (repo / "docs" / "a.md").write_text(f"# Thing\n\n_Last updated: {date}_\n")
        return repo

    def test_planted_stale_doc_reaches_the_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "2001-01-01")
            result = run("audit_doc_staleness",
                         ["--repo", str(repo), "--today", "2026-01-01", "--findings"])
            self.assertEqual(result.returncode, 0)
            data = envelope(repo, "doc-staleness")
            EnvelopeContract().assert_well_formed(data, "doc-staleness")
            self.assertIn("stale_by_stated_date", categories(data))
            stale = [f for f in data["findings"]
                     if f["category"] == "stale_by_stated_date"]
            self.assertEqual([f["file"] for f in stale], ["docs/a.md"])
            # "should_fix" from the audit must be normalised to the envelope's
            # own "should-fix"; the underscore form fails make()'s validation.
            self.assertEqual(stale[0]["severity"], "should-fix")
            self.assertEqual(data["scanned"], 1)

    def test_fresh_doc_writes_a_clean_envelope_with_the_sweep_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "2025-12-25")
            run("audit_doc_staleness",
                ["--repo", str(repo), "--today", "2026-01-01", "--findings"])
            data = envelope(repo, "doc-staleness")
            self.assertEqual([f for f in data["findings"]
                              if f["category"] == "stale_by_stated_date"], [])
            self.assertEqual(data["scanned"], 1)

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "2001-01-01")
            args = ["--repo", str(repo), "--today", "2026-01-01"]
            before = EnvelopeContract().assert_control_unchanged(
                "audit_doc_staleness", args, ["--findings"])
            self.assertIn("2001-01-01", before.stdout)

    def test_inert_run_writes_no_envelope_at_all(self):
        """An empty sweep exits 2 and must not leave a clean-looking envelope
        behind for the dashboard to grade as an A."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs").mkdir()
            result = run("audit_doc_staleness", ["--repo", str(repo), "--findings"])
            self.assertEqual(result.returncode, 2)
            self.assertFalse((repo / ".backend-suite" / "findings").exists())


PROPOSAL = """# RFC-9: A Proposal, dated 2001-01-01

Status: open

There are {count} open questions remaining.

## Decisions

- {marks}
"""


class ProposalStatus(unittest.TestCase):
    """A header claiming open questions its own Decisions section cannot account for."""

    def _repo(self, tmp: str, count: str, marks: str) -> Path:
        repo = Path(tmp)
        (repo / "docs" / "proposals").mkdir(parents=True)
        (repo / "docs" / "proposals" / "p.md").write_text(
            PROPOSAL.format(count=count, marks=marks))
        return repo

    def test_planted_count_mismatch_reaches_the_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "3", "\n- ".join(["✅ decided"] * 3))
            result = run("audit_proposal_status",
                         ["--repo", str(repo), "--today", "2026-01-01", "--findings"])
            self.assertEqual(result.returncode, 1)
            data = envelope(repo, "proposal-status")
            EnvelopeContract().assert_well_formed(data, "proposal-status")
            self.assertTrue(data["findings"], "planted mismatch produced no finding")
            self.assertEqual({f["severity"] for f in data["findings"]}, {"critical"})
            self.assertEqual({f["file"] for f in data["findings"]},
                             {"docs/proposals/p.md"})
            # Scanned is the proposal-shaped count, not every markdown file.
            self.assertEqual(data["scanned"], 1)

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "3", "\n- ".join(["✅ decided"] * 3))
            EnvelopeContract().assert_control_unchanged(
                "audit_proposal_status",
                ["--repo", str(repo), "--today", "2026-01-01"], ["--findings"])

    def test_inert_run_writes_no_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs" / "proposals").mkdir(parents=True)
            (repo / "docs" / "proposals" / "p.md").write_text("# Just a note\n")
            result = run("audit_proposal_status", ["--repo", str(repo), "--findings"])
            self.assertEqual(result.returncode, 2)
            self.assertFalse((repo / ".backend-suite" / "findings").exists())


CLAUDE_MD = """# Rules

1. There are {gates} gates.
"""

ENFORCEMENT = {
    "rules": [
        # `value_match` compares a number CLAUDE.md states against a number the
        # real thing prints. `echo` stands in for the real command so the test
        # measures the drift check, not whatever tool it would otherwise shell out to.
        {"id": "gate-count", "statement": "CLAUDE.md states the gate count",
         "check": {"kind": "value_match",
                   "claudeMdPattern": r"There are (\d+) gates\.",
                   "actualCommand": "echo running 2 gates",
                   "actualPattern": r"running (\d+) gates"}},
        {"id": "a-process-rule", "statement": "somebody behaves well",
         "check": {"kind": "unenforceable", "reason": "operator behaviour"}},
    ]
}


class ClaudeMdDrift(unittest.TestCase):
    """CLAUDE.md stating a number that no longer matches what enforces it."""

    def _repo(self, tmp: str, gates: str) -> Path:
        repo = Path(tmp)
        (repo / ".backend-suite").mkdir(parents=True)
        (repo / "CLAUDE.md").write_text(CLAUDE_MD.format(gates=gates))
        (repo / ".backend-suite" / "claude_md_enforcement.json").write_text(
            json.dumps(ENFORCEMENT))
        return repo

    def test_planted_drift_reaches_the_envelope_as_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "7")  # enforcement expects 2
            result = run("audit_claude_md_drift", ["--findings"], repo)
            self.assertEqual(result.returncode, 1)
            data = envelope(repo, "claude-md-drift")
            EnvelopeContract().assert_well_formed(data, "claude-md-drift")
            drifted = [f for f in data["findings"] if f["category"] == "drifted"]
            self.assertEqual(len(drifted), 1)
            self.assertEqual(drifted[0]["severity"], "critical")
            self.assertIn("gate-count", drifted[0]["summary"])
            self.assertEqual(drifted[0]["file"], "CLAUDE.md")
            self.assertEqual(data["scanned"], 2)

    def test_unenforceable_rules_are_findings_not_silence(self):
        """A rule nothing mechanical can check must appear in the roll-up. If it
        vanished from the envelope, a project whose every rule is unenforceable
        would grade identically to one whose every rule is verified."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "2")  # matches — no drift
            result = run("audit_claude_md_drift", ["--findings"], repo)
            self.assertEqual(result.returncode, 0)
            data = envelope(repo, "claude-md-drift")
            unenforceable = [f for f in data["findings"]
                             if f["category"] == "unenforceable"]
            self.assertEqual(len(unenforceable), 1)
            self.assertEqual(unenforceable[0]["severity"], "fyi")
            self.assertEqual([f for f in data["findings"]
                              if f["category"] == "drifted"], [])

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp, "7")
            EnvelopeContract().assert_control_unchanged(
                "audit_claude_md_drift", [], ["--findings"], repo)


class ProseFlags(unittest.TestCase):
    """A skill's markdown naming a flag its own script does not have.

    Scoped with `--root` at a synthetic plugin tree rather than this plugin's
    real one, so the planted case is deterministic and this test does not fail
    the day someone legitimately adds a flag.
    """

    def _root(self, tmp: str, flag: str) -> Path:
        root = Path(tmp) / "plugins" / "fake" / "bin"
        root.mkdir(parents=True)
        (root / "thing.py").write_text(
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--real')\n"
            "p.parse_args()\n")
        # `commands/`, not `skills/`: SCAN_GLOBS covers commands and agents.
        commands = Path(tmp) / "plugins" / "fake" / "commands"
        commands.mkdir(parents=True)
        (commands / "s.md").write_text(
            "# Skill\n\n```bash\n"
            f'python3 "${{CLAUDE_PLUGIN_ROOT}}/bin/thing.py" {flag}\n'
            "```\n")
        return Path(tmp) / "plugins"

    def test_planted_nonexistent_flag_reaches_the_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, "--invented")
            out = Path(tmp) / "env.json"
            result = run("audit_prose_flags",
                         ["--root", str(root), "--findings", str(out)])
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(out.read_text())
            EnvelopeContract().assert_well_formed(data, "prose-flags")
            planted = [f for f in data["findings"]
                       if f["category"] == "nonexistent-flag"]
            self.assertEqual(len(planted), 1)
            self.assertEqual(planted[0]["severity"], "critical")
            self.assertIn("--invented", planted[0]["summary"])
            self.assertEqual(planted[0]["file"], "fake/commands/s.md")
            self.assertIsInstance(planted[0]["line"], int)
            self.assertEqual(data["scanned"], 1)

    def test_real_flag_writes_a_clean_envelope_with_the_sweep_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, "--real")
            out = Path(tmp) / "env.json"
            result = run("audit_prose_flags",
                         ["--root", str(root), "--findings", str(out)])
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text())
            self.assertEqual(data["findings"], [])
            # The distinction the governing principle is about: clean over 1
            # checked pair, not clean over nothing.
            self.assertEqual(data["scanned"], 1)

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, "--invented")
            out = Path(tmp) / "env.json"
            EnvelopeContract().assert_control_unchanged(
                "audit_prose_flags", ["--root", str(root)],
                ["--findings", str(out)])


PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "adapters": {"lang": "php"},
    "audits": {"exceptionsFile": ".backend-suite/exceptions.json",
               "archRulesFile": ".backend-suite/arch-rules.json"},
}

ARCH_RULES = {
    "apiConsistency": {
        "scope": ["routes/**/*.php"],
        "semanticsWrappers": ["Semantics"],
        "checks": {
            "loadBearingCopy": True,
            "hardBakedCopy": True,
            # The check's surface is a client-side one; the fixture is a
            # server tree, so it is off with a written reason — and the
            # envelope has to carry that reason rather than vanish.
            "authoredSemantics": {"enabled": False,
                                  "why": "server-side tree; interaction "
                                         "surfaces live in the client app"},
            "vocabulary": True,
        },
        "vocabularyRules": [
            {"message": "uses fetch, where the codebase names this find",
             "classPattern": r"Repository",
             "has": [r"function\s+fetch\s*\("]},
        ],
    },
}

BAD_SOURCE = """<?php

final class UserRepository
{
    public function fetch(int $id)
    {
        return $this->client->get('/users/' . $id);
    }
}

if ($payload['status'] === 'Unknown') {
    return response()->json(['message' => 'Not found'], 404);
}
"""

CLEAN_SOURCE = """<?php

final class HealthController
{
    public function status()
    {
        return ['status' => 'ok'];
    }
}
"""


def php_fixture(tmp: str, source: str) -> Path:
    """A minimal PHP project the audit can run end to end.

    Hand-built and tiny on purpose: this file tests the envelope, not the
    adapter — the fixture only has to give each enabled check a real surface
    to decide over, and the php adapter's syntax has its own probes.
    Braces on their own lines because the audit's class extraction takes
    multi-line bodies (the convention).
    """
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "routes").mkdir(parents=True)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(json.dumps(ARCH_RULES))
    (repo / ".backend-suite" / "exceptions.json").write_text(
        json.dumps({"apiConsistency": {}}))
    (repo / "routes" / "api.php").write_text(source)
    return repo


# UnusedTokens and UnwiredRoles classes removed with their scripts (audit_unused_tokens.py, audit_unwired_roles.py) when this repo re-domained; re-authored against backend audits if the envelope gain is re-measured.

class ApiConsistency(unittest.TestCase):
    """The project-shaped audit of the five: its findings ARE the check output.

    The other four decide over docs, manifests and skill prose; this one's four
    checks (load-bearing copy, hard-baked copy, authored semantics, vocabulary)
    decide over a source tree through the php adapter's API_CONSISTENCY syntax,
    and its config is the one place the audit makes a project say what it turned
    off. So the envelope's `suppressed` block is under test here as much as its
    findings are.
    """

    def test_planted_findings_reach_the_envelope_per_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = php_fixture(tmp, BAD_SOURCE)
            result = run("audit_api_consistency", ["--findings"], repo=repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = envelope(repo, "api-consistency")
            EnvelopeContract().assert_well_formed(data, "api-consistency")
            self.assertEqual(categories(data),
                             {"compared", "hardbaked", "vocabulary"})
            compared = [f for f in data["findings"] if f["category"] == "compared"]
            self.assertEqual(len(compared), 1)
            self.assertIn("Unknown", compared[0]["summary"])
            # Line-scoped checks carry a line number; vocabulary is
            # class-scoped and reports the class, not a line.
            self.assertIsInstance(compared[0]["line"], int)
            vocabulary = [f for f in data["findings"]
                          if f["category"] == "vocabulary"]
            self.assertIn("UserRepository", vocabulary[0]["summary"])
            # The check that is off is named WITH its reason — a disabled
            # check must not read as one that found nothing.
            self.assertIn("semantics", data["suppressed"])
            self.assertIn("authoredSemantics",
                          data["suppressed"]["semantics"])
            self.assertIn("client app", data["suppressed"]["semantics"])
            self.assertEqual(data["scanned"], 1)

    def test_a_clean_sweep_is_empty_but_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = php_fixture(tmp, CLEAN_SOURCE)
            result = run("audit_api_consistency", ["--findings"], repo=repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = envelope(repo, "api-consistency")
            EnvelopeContract().assert_well_formed(data, "api-consistency")
            # The distinction the governing principle is about: clean over 1
            # scanned file, not clean over a sweep that refused to run.
            self.assertEqual(data["findings"], [])
            self.assertEqual(data["scanned"], 1)

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = php_fixture(tmp, BAD_SOURCE)
            out = Path(tmp) / "env.json"
            EnvelopeContract().assert_control_unchanged(
                "audit_api_consistency", [], ["--findings", str(out)], repo=repo)

    def test_vocabulary_on_with_no_rules_refuses_rather_than_sweeping(self):
        """On with zero rules is the confident-zero failure in a config file.

        The check must not be able to run and report nothing because nothing
        was configured for it to compare.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = php_fixture(tmp, CLEAN_SOURCE)
            rules_file = repo / ".backend-suite" / "arch-rules.json"
            rules = json.loads(rules_file.read_text())
            rules["apiConsistency"]["vocabularyRules"] = []
            rules_file.write_text(json.dumps(rules))
            result = run("audit_api_consistency", [], repo=repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("REFUSED", result.stderr)
            self.assertIn("vocabularyRules", result.stderr)

class EnvelopesAreReadableByTheRollUp(unittest.TestCase):
    """The point of all of the above: /quality-debt can now grade these.

    Written against `findings.read_all`/`summarize` — the functions the
    dashboard itself calls — rather than against the JSON, because "the file
    parses" and "the roll-up can grade it" are different claims and only the
    second one is the measured problem.
    """

    def test_a_planted_finding_becomes_a_graded_row(self):
        from backend_suite.engine import findings as F
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs").mkdir(parents=True, exist_ok=True)
            (repo / "docs" / "a.md").write_text("# Thing\n\n_Last updated: 2001-01-01_\n")
            run("audit_doc_staleness",
                ["--repo", str(repo), "--today", "2026-01-01", "--findings"])
            rows = F.summarize(F.read_all(repo))
            self.assertEqual({r["audit"] for r in rows}, {"doc-staleness"})
            self.assertNotIn("!", {r["grade"] for r in rows})
            # No row may grade "?" — that is the marker for "did this run at
            # all", and it is exactly what these seven used to produce.
            self.assertNotIn("?", {r["grade"] for r in rows})
            graded = [r for r in rows if r["audit"] == "doc-staleness"]
            self.assertEqual({r["category"] for r in graded},
                             {"stale_by_stated_date"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
