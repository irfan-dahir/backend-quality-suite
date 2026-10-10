#!/usr/bin/env python3
"""The seven audits retrofitted onto the common findings envelope, tested as a set.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_findings_envelope_test.py"

`audit_api_consistency`, `audit_claude_md_drift`, `audit_doc_staleness`,
`audit_proposal_status`, `audit_prose_flags`, `audit_unused_tokens` and
`audit_unwired_roles` each wrote their own output and nothing else, so
`/design-debt` could not grade them, `repo_health.py` reported them `unclear`,
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

`--findings` is additive by contract (design_suite/engine/findings.py's module
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

from design_suite.engine import audit_discovery as A  # noqa: E402

# The seven, and the envelope name each is expected to write under. Hand-written
# here on purpose: this is the assertion, and `envelope_name()` is what is being
# asserted against. Deriving it from the function under test would test nothing.
EXPECTED_ENVELOPE_NAMES = {
    "audit_api_consistency": "api-consistency",
    "audit_claude_md_drift": "claude-md-drift",
    "audit_doc_staleness": "doc-staleness",
    "audit_proposal_status": "proposal-status",
    "audit_prose_flags": "prose-flags",
    "audit_unused_tokens": "unused-tokens",
    "audit_unwired_roles": "unwired-roles",
}


def run(script: str, args: list[str], repo: Path | None = None):
    env = dict(os.environ)
    if repo is not None:
        env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{script}.py"), *args],
                          capture_output=True, text=True, env=env)


def envelope(repo: Path, name: str) -> dict:
    return json.loads((repo / ".design-suite" / "findings" / f"{name}.json").read_text())


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
        the next time someone runs /design-debt and sees two-thirds of a picture.
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
            self.assertFalse((repo / ".design-suite" / "findings").exists())


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
            self.assertFalse((repo / ".design-suite" / "findings").exists())


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
        (repo / ".design-suite").mkdir(parents=True)
        (repo / "CLAUDE.md").write_text(CLAUDE_MD.format(gates=gates))
        (repo / ".design-suite" / "claude_md_enforcement.json").write_text(
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
    "adapters": {"lang": "dart"},
    "source": {"root": "lib", "fileGlob": "**/*.dart"},
    "tokens": {
        "source": {"kind": "file", "path": "lib/theme/tokens.dart"},
        "accessor": "AppTokens",
        "roleSource": {"kind": "file", "path": "lib/theme/roles.dart"},
        "roleAccessor": "DsColors",
    },
    "audits": {"exceptionsFile": ".design-suite/exceptions.json",
               "archRulesFile": ".design-suite/arch-rules.json"},
    "docs": {"manifest": ".design-suite/docs.manifest.json"},
}

ARCH_RULES = {
    "unwiredRoles": {"requiredRoles": ["primary", "surface"]},
    "unusedTokens": {"categories": {"spacing": "space", "radius": "radius"},
                     "requiredTokens": None},
    "apiConsistency": {
        "buttonishPattern": r"(?:Button|Cta|Fab)\b",
        "semanticsWrappers": ["Semantics"],
        "scope": ["lib/**/*.dart"],
        "checks": {"loadBearingCopy": True, "hardBakedCopy": True,
                   "authoredSemantics": True, "vocabulary": True},
    },
}

CLEAN_SOURCE = """class Foo {
  double pad() => AppTokens.space16 + AppTokens.space8 + AppTokens.radius4;
  void use(BuildContext context) {
    final colors = DsColors.of(context);
    colors.primary;
    colors.surface;
  }
}
"""

BAD_SOURCE = """class SaveButton extends StatelessWidget {
  final VoidCallback? onTap;
  final bool enabled;
  Widget build(BuildContext context) {
    return InkWell(onTap: onTap, child: Text('Tap here now'));
  }
}
"""


def dart_fixture(tmp: str) -> Path:
    """A minimal Dart project the three project-shaped audits can all run against.

    Hand-built rather than borrowed from `evals/_fixtures/build_fixture.py`:
    that builder shells out to the real toolchain to produce a project shaped
    like a consumer's, which is far more than these three need and makes the
    test depend on something installed.
    """
    repo = Path(tmp)
    (repo / ".design-suite").mkdir(parents=True)
    (repo / "lib" / "theme").mkdir(parents=True)
    (repo / ".design-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".design-suite" / "arch-rules.json").write_text(json.dumps(ARCH_RULES))
    (repo / ".design-suite" / "exceptions.json").write_text(json.dumps(
        {"apiConsistency": {}, "unusedTokens": {"exempt": {}}, "unwiredRoles": {}}))
    (repo / "lib" / "theme" / "tokens.dart").write_text(
        "class AppTokens {\n"
        "  static const space16 = 16.0;\n"
        "  static const space8 = 8.0;\n"
        "  static const radius4 = 4.0;\n"
        "}\n")
    (repo / "lib" / "theme" / "roles.dart").write_text(
        "class DsColors {\n  final Color primary;\n  final Color surface;\n}\n")
    (repo / "lib" / "clean.dart").write_text(CLEAN_SOURCE)
    return repo


class UnusedTokens(unittest.TestCase):
    def test_clean_fixture_writes_an_envelope_with_the_token_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            result = run("audit_unused_tokens", ["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = envelope(repo, "unused-tokens")
            EnvelopeContract().assert_well_formed(data, "unused-tokens")
            self.assertEqual(data["findings"], [])
            # Three declared tokens swept, not three files — the sweep unit for
            # this audit is the declared token.
            self.assertEqual(data["scanned"], 3)

    def test_planted_unread_token_reaches_the_envelope_under_its_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            tokens = repo / "lib" / "theme" / "tokens.dart"
            tokens.write_text(tokens.read_text().replace(
                "  static const radius4 = 4.0;",
                "  static const radius4 = 4.0;\n  static const space99 = 99.0;"))
            result = run("audit_unused_tokens", ["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = envelope(repo, "unused-tokens")
            self.assertEqual(len(data["findings"]), 1)
            planted = data["findings"][0]
            # Category is the project's own naming convention, so a dead spacing
            # token grades separately from a dead radius.
            self.assertEqual(planted["category"], "spacing")
            self.assertEqual(planted["severity"], "should-fix")
            self.assertIn("space99", planted["summary"])
            self.assertEqual(data["scanned"], 4)

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            EnvelopeContract().assert_control_unchanged(
                "audit_unused_tokens", [], ["--findings"], repo)


class UnwiredRoles(unittest.TestCase):
    def test_clean_fixture_writes_an_envelope_with_the_role_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            result = run("audit_unwired_roles", ["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = envelope(repo, "unwired-roles")
            EnvelopeContract().assert_well_formed(data, "unwired-roles")
            self.assertEqual(data["findings"], [])
            self.assertEqual(data["scanned"], 2)

    def test_planted_claimed_role_is_a_should_fix_finding(self):
        """A role this project holds itself to and reads nowhere — the broken
        re-skinning promise, and the case that exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            roles = repo / "lib" / "theme" / "roles.dart"
            roles.write_text(roles.read_text().replace(
                "  final Color surface;",
                "  final Color surface;\n  final Color danger;"))
            rules = json.loads((repo / ".design-suite" / "arch-rules.json").read_text())
            rules["unwiredRoles"]["requiredRoles"].append("danger")
            (repo / ".design-suite" / "arch-rules.json").write_text(json.dumps(rules))
            result = run("audit_unwired_roles", ["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = envelope(repo, "unwired-roles")
            self.assertEqual(len(data["findings"]), 1)
            self.assertEqual(data["findings"][0]["category"], "claimed-role")
            self.assertEqual(data["findings"][0]["severity"], "should-fix")
            self.assertIn("danger", data["findings"][0]["summary"])
            self.assertEqual(data["scanned"], 3)

    def test_planted_offered_role_is_reported_but_only_as_fyi(self):
        """Defined by the design system, never claimed by this project. Reported
        every run, never failed — so the two must not share a category, or the
        dashboard would grade accepted breadth as debt."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            roles = repo / "lib" / "theme" / "roles.dart"
            roles.write_text(roles.read_text().replace(
                "  final Color surface;",
                "  final Color surface;\n  final Color danger;"))
            result = run("audit_unwired_roles", ["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = envelope(repo, "unwired-roles")
            self.assertEqual(categories(data), {"offered-role"})
            self.assertEqual(data["findings"][0]["severity"], "fyi")

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            EnvelopeContract().assert_control_unchanged(
                "audit_unwired_roles", [], ["--findings"], repo)


class ApiConsistency(unittest.TestCase):
    def test_clean_fixture_writes_an_envelope_with_the_file_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            result = run("audit_api_consistency", ["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = envelope(repo, "api-consistency")
            EnvelopeContract().assert_well_formed(data, "api-consistency")
            self.assertEqual(data["findings"], [])
            self.assertEqual(data["scanned"], 3)

    def test_planted_defects_reach_the_envelope_under_three_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            (repo / "lib" / "bad.dart").write_text(BAD_SOURCE)
            result = run("audit_api_consistency", ["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = envelope(repo, "api-consistency")
            EnvelopeContract().assert_well_formed(data, "api-consistency")
            # One planted file trips three distinct checks; each must grade
            # under its own check name rather than rolling into one row.
            self.assertEqual(categories(data),
                             {"hardbaked", "semantics", "vocabulary"})
            self.assertEqual({f["file"] for f in data["findings"]}, {"lib/bad.dart"})
            self.assertEqual(data["scanned"], 4)

    def test_a_disabled_check_is_named_as_suppressed_not_silently_absent(self):
        """A check switched off must not read as a check that found nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            (repo / "lib" / "bad.dart").write_text(BAD_SOURCE)
            rules = json.loads((repo / ".design-suite" / "arch-rules.json").read_text())
            rules["apiConsistency"]["checks"]["authoredSemantics"] = {
                "enabled": False, "why": "this fixture has no screens"}
            (repo / ".design-suite" / "arch-rules.json").write_text(json.dumps(rules))
            run("audit_api_consistency", ["--findings"], repo)
            data = envelope(repo, "api-consistency")
            self.assertNotIn("semantics", categories(data))
            self.assertIn("semantics", data["suppressed"])
            self.assertIn("this fixture has no screens", data["suppressed"]["semantics"])

    def test_control_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            (repo / "lib" / "bad.dart").write_text(BAD_SOURCE)
            EnvelopeContract().assert_control_unchanged(
                "audit_api_consistency", [], ["--findings"], repo)


class EnvelopesAreReadableByTheRollUp(unittest.TestCase):
    """The point of all of the above: /design-debt can now grade these.

    Written against `findings.read_all`/`summarize` — the functions the
    dashboard itself calls — rather than against the JSON, because "the file
    parses" and "the roll-up can grade it" are different claims and only the
    second one is the measured problem.
    """

    def test_a_planted_finding_becomes_a_graded_row(self):
        from design_suite.engine import findings as F
        with tempfile.TemporaryDirectory() as tmp:
            repo = dart_fixture(tmp)
            (repo / "lib" / "bad.dart").write_text(BAD_SOURCE)
            run("audit_api_consistency", ["--findings"], repo)
            run("audit_unused_tokens", ["--findings"], repo)
            run("audit_unwired_roles", ["--findings"], repo)
            rows = F.summarize(F.read_all(repo))
            self.assertEqual({r["audit"] for r in rows},
                             {"api-consistency", "unused-tokens", "unwired-roles"})
            self.assertNotIn("!", {r["grade"] for r in rows})
            # No row may grade "?" — that is the marker for "did this run at
            # all", and it is exactly what these seven used to produce.
            self.assertNotIn("?", {r["grade"] for r in rows})
            graded = [r for r in rows if r["audit"] == "api-consistency"]
            self.assertEqual({r["category"] for r in graded},
                             {"hardbaked", "semantics", "vocabulary"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
