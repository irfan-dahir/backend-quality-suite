#!/usr/bin/env python3
"""Tests for the upgrade/migration capability.

Two rules shape this file.

**Every refusal is tested next to the positive case it must not swallow.** A
refusal that fires on everything is not a safety property, it is a broken check —
and this whole capability exists because a quiet pass and a real pass looked the
same. So `test_..._refuses` never appears without a `test_..._still_answers`
beside it.

**The compatibility check is tested against the regression that motivated it**,
not against a fixture written to make it pass. `e14048a..ba7029e` is the real
range in which `audit_tokens` flipped to `1`-on-findings, `audit_error_handling`
widened from critical-only to any finding, two audits entered `DISABLED`, and
`--update-baseline` started refusing without `--accept-new`. If that range ever
stops reporting all four, this check has regressed — and the test fails rather
than skipping, because "the fixture was unavailable" is precisely the silence
this repo forbids.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

from _bootstrap import PLUGIN_ROOT  # noqa: E402

import suite_upgrade  # noqa: E402
from design_suite.engine import fleet, migrate, upgrade  # noqa: E402
from design_suite.engine.upgrade import CannotDetermine  # noqa: E402

REPO = PLUGIN_ROOT.parents[1]

# The real range in which all four regression shapes landed.
OLD_REV, NEW_REV = "e14048a", "ba7029e"


def _make_consumer(root: Path, *, profile: dict | None = None,
                   hooks_map: bool = False) -> Path:
    dot = root / ".design-suite"
    dot.mkdir(parents=True)
    (dot / "profile.json").write_text(json.dumps(
        profile if profile is not None else {
            "profileVersion": 1, "project": {}, "adapters": {}, "source": {},
            "tokens": {}, "docs": {},
        }))
    if hooks_map:
        (dot / "hooks.map.json").write_text('{"hooks": []}')
    (root / "README.md").write_text("a consumer\n")
    return root


def _row(report: dict, action: str) -> dict:
    """One named action's row. Looked up by name, never by position: every action
    is always listed, so `actions[0]` is whichever one sorts first, not the one
    under test."""
    return next(r for r in report["actions"] if r["action"] == action)


def _tree_state(root: Path) -> set[tuple[str, int]]:
    """Every file under a tree with its size — enough to notice any write."""
    return {
        (str(p.relative_to(root)), p.stat().st_size)
        for p in root.rglob("*") if p.is_file()
    }


# --------------------------------------------------------------- source reading


class ExitExpressions(unittest.TestCase):
    def test_conditional_return_is_part_of_the_contract(self):
        """The shape a set-of-exit-codes comparison cannot see."""
        before = upgrade.exit_expressions("def main():\n    return 1 if critical else 0\n")
        after = upgrade.exit_expressions("def main():\n    return 1 if findings else 0\n")
        self.assertEqual(before, ["return 1 if critical else 0"])
        self.assertNotEqual(before, after)

    def test_always_zero_to_one_on_findings_is_seen(self):
        before = upgrade.exit_expressions("def main():\n    return 0\n")
        after = upgrade.exit_expressions("def main():\n    return 1 if findings else 0\n")
        self.assertNotEqual(before, after)

    def test_returning_data_is_not_an_exit_code(self):
        """The paired negative: a helper returning a value must not read as a contract."""
        self.assertEqual(
            upgrade.exit_expressions("def helper():\n    return [1, 2]\n"), [])
        self.assertEqual(
            upgrade.exit_expressions("def helper():\n    return 404\n"), [])

    def test_flags_come_from_argparse_not_from_prose(self):
        source = (
            'def main():\n'
            '    """Run with --documented-but-fake."""\n'
            '    p.add_argument("--real", action="store_true")\n'
        )
        self.assertEqual(upgrade.flags(source), {"--real"})

    def test_unparseable_source_refuses(self):
        with self.assertRaises(CannotDetermine):
            upgrade.exit_expressions("def (:\n")


class DisabledRegistry(unittest.TestCase):
    def test_literal_dict_is_read(self):
        self.assertEqual(
            upgrade.disabled_audits('DISABLED = {"audit_copy": {"reason": "x"}}'),
            {"audit_copy"})

    def test_computed_keys_refuse_rather_than_guess(self):
        """Paired refusal: a registry it cannot read must not read as empty."""
        with self.assertRaises(CannotDetermine):
            upgrade.disabled_audits("DISABLED = {name: {} for name in names}")

    def test_absent_assignment_refuses(self):
        with self.assertRaises(CannotDetermine):
            upgrade.disabled_audits("X = 1\n")


class RequiredConfigKeys(unittest.TestCase):
    def test_keys_are_qualified_by_location(self):
        keys = upgrade.required_config_keys(json.dumps({
            "required": ["project"],
            "properties": {"project": {"required": ["name"]}},
        }))
        self.assertIn("/::project", keys)
        self.assertIn("/properties/project::name", keys)

    def test_unreadable_schema_refuses(self):
        with self.assertRaises(CannotDetermine):
            upgrade.required_config_keys("{not json")


# ------------------------------------------------------- the regression fixture


class CompatAgainstTheRealRegression(unittest.TestCase):
    """`e14048a..ba7029e` must report all four shapes. Nothing found means broken."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.report = upgrade.compare(REPO, OLD_REV, NEW_REV)
        except CannotDetermine as exc:
            raise AssertionError(
                f"the regression fixture {OLD_REV}..{NEW_REV} could not be read "
                f"({exc}). This test fails rather than skipping: an unavailable "
                f"fixture is not a passing check."
            ) from exc

    def _subjects(self, category: str) -> set[str]:
        return {f["subject"] for f in self.report["findings"]
                if f["category"] == category}

    def test_shape_1_audit_tokens_started_exiting_1_on_findings(self):
        subjects = self._subjects("exit-contract-changed")
        self.assertTrue(any(s.endswith("audit_tokens.py") for s in subjects), subjects)
        finding = next(f for f in self.report["findings"]
                       if f["subject"].endswith("audit_tokens.py"))
        self.assertIn("return 1 if findings else 0", finding["after"])
        self.assertNotIn("return 1 if findings else 0", finding["before"])

    def test_shape_2_error_handling_widened_from_critical_to_any_finding(self):
        finding = next(
            (f for f in self.report["findings"]
             if f["category"] == "exit-contract-changed"
             and f["subject"].endswith("audit_error_handling.py")), None)
        self.assertIsNotNone(finding, "audit_error_handling's widening went unreported")
        self.assertIn("return 1 if critical else 0", finding["before"])
        self.assertIn("return 1 if findings else 0", finding["after"])

    def test_shape_3_two_audits_entered_DISABLED(self):
        self.assertEqual(self._subjects("audit-newly-disabled"),
                         {"audit_accessibility", "audit_copy"})

    def test_shape_4_update_baseline_now_needs_accept_new(self):
        gating = {f["subject"]: f for f in self.report["findings"]
                  if f["category"] == "new-gating-flag"}
        ratchets = [s for s, f in gating.items()
                    if "--accept-new" in f.get("addedFlags", [])]
        self.assertTrue(ratchets, f"no script reported --accept-new as gating: {gating}")

    def test_every_finding_carries_a_severity_and_a_reason(self):
        for finding in self.report["findings"]:
            self.assertIn(finding["severity"], (upgrade.CRITICAL, upgrade.SHOULD_FIX))
            self.assertTrue(finding["detail"].strip())

    def test_an_absent_mechanism_is_noted_not_silently_empty(self):
        """`audit_discovery.py` did not exist at the old revision — say so."""
        self.assertTrue(any("audit_discovery.py" in n
                            for n in self.report["old"]["notes"]))


class CompatRefusals(unittest.TestCase):
    def test_unknown_revision_refuses(self):
        with self.assertRaises(CannotDetermine):
            upgrade.compare(REPO, "not-a-real-revision", NEW_REV)

    def test_a_revision_with_no_plugin_tree_refuses(self):
        """Paired with the positive below: an empty answer is never 'compatible'."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "unrelated.txt").write_text("hi\n")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "x"], check=True)
            with self.assertRaises(CannotDetermine):
                upgrade.compare(repo, "HEAD", "HEAD")

    def test_identical_revisions_still_answer_clean(self):
        report = upgrade.compare(REPO, NEW_REV, NEW_REV)
        self.assertEqual(report["findings"], [])

    def test_cli_refusal_is_exit_2_not_0(self):
        code = suite_upgrade.main(["compat", "--from", "nope-nope", "--to", NEW_REV])
        self.assertEqual(code, suite_upgrade.REFUSED)

    def test_cli_clean_is_exit_0_and_findings_is_exit_1(self):
        self.assertEqual(
            suite_upgrade.main(["compat", "--from", NEW_REV, "--to", NEW_REV]),
            suite_upgrade.CLEAN)
        self.assertEqual(
            suite_upgrade.main(["compat", "--from", OLD_REV, "--to", NEW_REV]),
            suite_upgrade.FINDINGS)


# ---------------------------------------------------------------------- fleet


class Fleet(unittest.TestCase):
    REGISTRY = {
        "design-suite@m": [
            {"scope": "user", "version": "new", "lastUpdated": "2026-09-01"},
            {"scope": "project", "projectPath": "/repos/alpha",
             "version": "new", "lastUpdated": "2026-09-01"},
            {"scope": "project",
             "projectPath": "/repos/alpha/.claude/worktrees/agent-abc",
             "version": "old", "lastUpdated": "2026-08-01"},
            {"scope": "project",
             "projectPath": "/repos/alpha/.claude/worktrees/agent-def",
             "version": "old", "lastUpdated": "2026-08-02"},
            {"scope": "project", "projectPath": "/repos/beta",
             "version": "old", "lastUpdated": "2026-08-03"},
        ],
    }

    def test_worktrees_fold_into_their_project(self):
        report = fleet.fleet(self.REGISTRY)
        self.assertEqual(report["projectCount"], 2)
        self.assertEqual([r["project"] for r in report["projects"]],
                         ["/repos/alpha", "/repos/beta"])
        alpha = report["projects"][0]
        self.assertEqual(len(alpha["foldedWorktrees"]), 2)
        self.assertEqual(alpha["plugins"]["design-suite"]["version"], "new")

    def test_a_dot_claude_elsewhere_is_not_a_worktree(self):
        """The paired negative: folding must not eat a legitimately-named path."""
        self.assertEqual(fleet.real_project_root("/repos/dot-claude-demo"),
                         "/repos/dot-claude-demo")
        self.assertEqual(fleet.real_project_root("/repos/alpha/.claude/settings"),
                         "/repos/alpha/.claude/settings")

    def test_user_scope_is_not_a_project(self):
        report = fleet.fleet(self.REGISTRY)
        self.assertIn("design-suite", report["userScope"])
        self.assertNotIn("", [r["project"] for r in report["projects"]])

    def test_empty_fleet_refuses_rather_than_reporting_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "installed_plugins.json"
            registry.write_text(json.dumps({"plugins": {}}))
            code = suite_upgrade.main(["fleet", "--registry", str(registry)])
        self.assertEqual(code, suite_upgrade.REFUSED)

    def test_a_populated_fleet_still_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "installed_plugins.json"
            registry.write_text(json.dumps({"plugins": self.REGISTRY}))
            code = suite_upgrade.main(["fleet", "--registry", str(registry)])
        # Two versions across the fleet is a finding, not a refusal.
        self.assertEqual(code, suite_upgrade.FINDINGS)


# ----------------------------------------------------------------------- apply


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.consumer = _make_consumer(Path(self.tmp.name) / "proj")

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_writes_nothing(self):
        before = _tree_state(self.consumer)
        report = migrate.apply(self.consumer, PLUGIN_ROOT, write=False)
        self.assertFalse(report["wrote"])
        self.assertEqual(_tree_state(self.consumer), before)

    def test_sync_schema_applies_and_is_idempotent(self):
        migrate.apply(self.consumer, PLUGIN_ROOT, write=True, only=("sync-schema",))
        dest = self.consumer / ".design-suite" / "profile.schema.json"
        self.assertTrue(dest.is_file())
        self.assertEqual(
            dest.read_text(),
            (PLUGIN_ROOT / "templates" / "profile.schema.json").read_text())
        again = migrate.apply(self.consumer, PLUGIN_ROOT, write=True,
                              only=("sync-schema",))
        self.assertEqual(_row(again, "sync-schema")["status"], "clean")

    def test_profile_json_is_never_written_by_any_action(self):
        """The rule init.py --force breaks, asserted rather than trusted."""
        profile = self.consumer / ".design-suite" / "profile.json"
        before = profile.read_text()
        report = migrate.apply(self.consumer, PLUGIN_ROOT, write=True)
        self.assertEqual(profile.read_text(), before)
        for row in report["actions"]:
            self.assertNotIn("profile.json", " ".join(row["writes"]))

    def test_hooks_map_is_scaffolded_when_absent(self):
        migrate.apply(self.consumer, PLUGIN_ROOT, write=True,
                      only=("scaffold-hooks-map",))
        self.assertTrue((self.consumer / ".design-suite" / "hooks.map.json").is_file())

    def test_an_existing_hooks_map_is_never_overwritten(self):
        """Paired with the scaffold case above: present means hands off."""
        consumer = _make_consumer(Path(self.tmp.name) / "proj2", hooks_map=True)
        original = (consumer / ".design-suite" / "hooks.map.json").read_text()
        report = migrate.apply(consumer, PLUGIN_ROOT, write=True,
                               only=("scaffold-hooks-map",))
        self.assertEqual((consumer / ".design-suite" / "hooks.map.json").read_text(),
                         original)
        self.assertEqual(_row(report, "scaffold-hooks-map")["status"], "clean")

    def test_missing_required_key_refuses_and_writes_nothing(self):
        consumer = _make_consumer(Path(self.tmp.name) / "proj3", profile={"project": {}})
        before = _tree_state(consumer)
        report = migrate.apply(consumer, PLUGIN_ROOT, write=True,
                               only=("declare-config-keys",))
        row = _row(report, "declare-config-keys")
        self.assertEqual(row["status"], "refused")
        self.assertIn("profileVersion", row["missingKeys"])
        self.assertEqual(_tree_state(consumer), before)

    def test_a_complete_profile_still_passes_that_check(self):
        """The positive the refusal above must not swallow."""
        report = migrate.apply(self.consumer, PLUGIN_ROOT, write=False,
                               only=("declare-config-keys",))
        self.assertEqual(_row(report, "declare-config-keys")["status"], "clean")

    def test_a_project_without_design_suite_refuses(self):
        empty = Path(self.tmp.name) / "not-a-consumer"
        empty.mkdir()
        with self.assertRaises(CannotDetermine):
            migrate.apply(empty, PLUGIN_ROOT, write=False)

    def test_unknown_action_refuses_rather_than_silently_running_none(self):
        with self.assertRaises(CannotDetermine):
            migrate.apply(self.consumer, PLUGIN_ROOT, only=("rewrite-everything",))

    def test_excluded_actions_are_listed_not_dropped(self):
        report = migrate.apply(self.consumer, PLUGIN_ROOT, only=("sync-schema",))
        actions = {r["action"] for r in report["actions"]}
        for action in migrate.ACTIONS:
            self.assertTrue(any(a == action or a.startswith(f"{action}:")
                                for a in actions), action)

    def test_cli_exit_4_when_every_action_is_excluded(self):
        code = suite_upgrade.main([
            "apply", "--consumer", str(self.consumer),
            *sum([["--skip", a] for a in migrate.ACTIONS], []),
        ])
        self.assertEqual(code, suite_upgrade.DECLINED)


# --------------------------------------------------------------------- measure


class Measure(unittest.TestCase):
    def test_a_project_without_design_suite_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "plain"
            empty.mkdir()
            with self.assertRaises(CannotDetermine):
                migrate.copy_consumer(empty, Path(tmp) / "copy")

    def test_a_real_consumer_is_copied(self):
        """Paired positive: the refusal above must not fire on an adopter."""
        with tempfile.TemporaryDirectory() as tmp:
            consumer = _make_consumer(Path(tmp) / "proj")
            copy = migrate.copy_consumer(consumer, Path(tmp) / "copy")
            self.assertEqual(_tree_state(copy), _tree_state(consumer))

    def test_measure_never_writes_to_the_consumer_tree(self):
        """The property the whole read-only half rests on, measured not asserted.

        Runs one real audit from each of the two real revisions against a
        throwaway consumer, then compares the consumer's file inventory
        byte-count-for-byte-count. The audits write findings envelopes by
        default; if any of that landed in the consumer, this fails.
        """
        with tempfile.TemporaryDirectory() as tmp:
            consumer = _make_consumer(Path(tmp) / "proj")
            before = _tree_state(consumer)
            report = migrate.measure(consumer, REPO, OLD_REV, NEW_REV,
                                     only="tokens", timeout=120.0,
                                     workdir=Path(tmp) / "scratch")
            self.assertEqual(_tree_state(consumer), before,
                             "measure wrote into the consumer's own tree")
            self.assertTrue(report["readOnly"])
            self.assertNotEqual(report["old"]["tree"], str(consumer))
            self.assertNotEqual(report["new"]["tree"], str(consumer))
            self.assertTrue(report["audits"])

    def test_a_filter_matching_nothing_refuses(self):
        """Nothing running is not the same as nothing having changed."""
        with tempfile.TemporaryDirectory() as tmp:
            consumer = _make_consumer(Path(tmp) / "proj")
            with self.assertRaises(CannotDetermine):
                migrate.measure(consumer, REPO, OLD_REV, NEW_REV,
                                only="no-such-audit-anywhere",
                                workdir=Path(tmp) / "scratch")


class OutputPathsResolveComputedDefaults(unittest.TestCase):
    """`default=None` + `args.out or <expr>` hid four report moves (audit_tokens,
    focus_order, semantics, accessibility) from output-path-moved."""

    BEFORE = ('def main():\n    p.add_argument("--out", default=None)\n'
              '    out_rel = args.out or PIPE.out_path(ctx.profile, "tokens", "findings.json")\n')
    AFTER = ('DEFAULT_OUT = ".design-suite/tokens-findings.json"\n'
             'def main():\n    p.add_argument("--out", default=None)\n'
             '    out_rel = args.out or DEFAULT_OUT\n')

    def test_pipeline_call_and_constant_are_resolved(self):
        self.assertEqual(upgrade.output_paths(self.BEFORE)["--out"],
                         repr("<pipelines.tokens>/findings.json"))
        self.assertEqual(upgrade.output_paths(self.AFTER)["--out"],
                         repr(".design-suite/tokens-findings.json"))

    def test_move_is_visible_as_a_difference(self):
        self.assertNotEqual(upgrade.output_paths(self.BEFORE)["--out"],
                            upgrade.output_paths(self.AFTER)["--out"])

    def test_unchanged_computed_default_is_not_a_move(self):
        self.assertEqual(upgrade.output_paths(self.AFTER)["--out"],
                         upgrade.output_paths(self.AFTER.replace("def main", "def run"))["--out"])

    def test_unresolvable_default_is_labelled_dynamic_not_dropped(self):
        src = ('def main():\n    p.add_argument("--out", default=None)\n'
               '    o = args.out or compute(x)\n')
        self.assertTrue(upgrade.output_paths(src)["--out"].startswith("dynamic: "))

    def test_literal_default_still_seen(self):
        self.assertEqual(upgrade.output_paths('p.add_argument("--out", default="a/b.json")\n'),
                         {"--out": "'a/b.json'"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
