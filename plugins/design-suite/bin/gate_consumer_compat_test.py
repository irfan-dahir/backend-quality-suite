#!/usr/bin/env python3
"""Tests for the consumer-compatibility merge gate.

The rule this file is written under is the same one `suite_upgrade_test.py`
states: **every refusal is tested next to the positive case it must not
swallow.** A gate that fails on everything is not a safety property, it is a
broken check — and this whole capability exists because a quiet pass and a real
pass looked the same. So each `_refuses` test has a `_still_passes` or
`_still_answers` beside it.

The gate's own biting is tested against a real range rather than a fixture
written to make it pass: `e14048a..ba7029e` is where `audit_tokens` flipped to
`1`-on-findings, two audits entered `DISABLED`, and
`audit_reinvented_components` lost `--require-resolution`. If that range stops
producing blocking findings, this gate has regressed — and the test fails rather
than skipping, because "the fixture was unavailable" is the silence this repo
forbids.
"""
from __future__ import annotations

import atexit
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

from _bootstrap import PLUGIN_ROOT  # noqa: E402

import gate_consumer_compat as gate_cli  # noqa: E402
from design_suite.engine import compat_gate  # noqa: E402
from design_suite.engine.upgrade import CannotDetermine  # noqa: E402

REPO = PLUGIN_ROOT.parents[1]

# The real range in which the breaking shapes landed.
OLD_REV, NEW_REV = "e14048a", "ba7029e"

# A complete, valid acknowledgement. Individual tests remove one field from a
# copy of this, so "what makes an entry invalid" is always a one-field delta from
# something the suite has proved is valid — never two changes at once.
GOOD_ACK = {
    "id": "reinvented-require-resolution-removed",
    "category": "flag-removed",
    "subject": "plugins/design-suite/bin/audit_reinvented_components.py "
               "--require-resolution",
    "break": "the audit no longer accepts --require-resolution, so argparse "
             "exits 2 on an invocation that used to work",
    "consumerInvocation": "the CI step that invokes the audit by path with "
                          "--require-resolution",
    "migration": "drop the flag from the CI step; resolution is now required "
                 "unconditionally, so the behaviour is unchanged without it",
    "acknowledgedOn": "2026-09-17",
}


def _write_acks(root: Path, entries: list[dict]) -> Path:
    path = root / "acks.json"
    path.write_text(json.dumps({"schemaVersion": 1, "entries": entries}, indent=2))
    return path


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BIN / "gate_consumer_compat.py"), *argv],
        capture_output=True, text=True, cwd=str(REPO), timeout=600)


# --------------------------------------------------------- the gate actually bites


class GateBites(unittest.TestCase):
    """The pair that matters: a real break fails, and acknowledging it passes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.findings = compat_gate.evaluate(
            REPO, [], old_rev=OLD_REV, new_rev=NEW_REV)

    def test_unacknowledged_critical_blocks(self) -> None:
        self.assertTrue(
            self.findings["blocking"],
            "the fixture range carries known critical breaks and the gate found "
            "none — the check has regressed, it has not been reassured")
        categories = {f["category"] for f in self.findings["blocking"]}
        self.assertIn("flag-removed", categories)
        self.assertIn("audit-newly-disabled", categories)
        self.assertTrue(
            all(f["severity"] == "critical" for f in self.findings["blocking"]),
            "only critical findings may block")

    def test_acknowledged_critical_passes_and_is_listed(self) -> None:
        """The same finding, acknowledged: no longer blocking, and still visible.

        Both halves are asserted. A ratchet that stops printing what it carries
        is a baseline nobody reads, so "passes" is not enough — it must also
        still appear under `acknowledged`.
        """
        acknowledged = compat_gate.evaluate(
            REPO, [GOOD_ACK], old_rev=OLD_REV, new_rev=NEW_REV)
        key = compat_gate.ack_key(GOOD_ACK)
        self.assertNotIn(
            key, {compat_gate.ack_key(f) for f in acknowledged["blocking"]})
        self.assertIn(
            key, {compat_gate.ack_key(r["finding"])
                  for r in acknowledged["acknowledged"]},
            "an acknowledged break must be listed, not silently absorbed")
        self.assertEqual(len(acknowledged["blocking"]),
                         len(self.findings["blocking"]) - 1,
                         "acknowledging one break must clear exactly one")

    def test_acknowledging_everything_critical_exits_clean(self) -> None:
        """Acknowledged breaks really do let a merge through — the escape works.

        If this failed, the gate would be un-escapable, which is the shape that
        gets a gate deleted rather than obeyed.
        """
        acks = []
        for i, finding in enumerate(self.findings["blocking"]):
            entry = dict(compat_gate.suggested_entry(finding))
            entry["id"] = f"ack-{i}"
            entry.update(**{k: "stated" for k in
                            ("break", "consumerInvocation", "migration")})
            acks.append(entry)
        cleared = compat_gate.evaluate(REPO, acks, old_rev=OLD_REV, new_rev=NEW_REV)
        self.assertEqual(cleared["blocking"], [])
        self.assertEqual(cleared["counts"]["acknowledged"], len(acks))

    def test_should_fix_is_reported_but_never_blocks(self) -> None:
        self.assertTrue(self.findings["advisory"],
                        "the fixture range carries should-fix findings")
        self.assertTrue(
            all(f["severity"] != "critical" for f in self.findings["advisory"]))

    def test_severity_regrade_does_not_unacknowledge(self) -> None:
        """Identity is (category, subject) — not severity, not the detail prose.

        Matching on detail would un-acknowledge every entry the next time a
        message was reworded; matching on severity would drop an acknowledgement
        exactly when a break was graded more serious.
        """
        self.assertEqual(
            compat_gate.ack_key({"category": "flag-removed", "subject": "x",
                                 "severity": "critical", "detail": "one"}),
            compat_gate.ack_key({"category": "flag-removed", "subject": "x",
                                 "severity": "should-fix", "detail": "TWO"}))


# ------------------------------------------- the acknowledgement file's refusals


class AcknowledgementLoading(unittest.TestCase):

    def test_complete_entry_loads(self) -> None:
        """The positive case every refusal below must not swallow."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_acks(Path(tmp), [GOOD_ACK])
            self.assertEqual(len(compat_gate.load_acks(path)), 1)

    def test_entry_without_migration_is_refused(self) -> None:
        entry = {k: v for k, v in GOOD_ACK.items() if k != "migration"}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_acks(Path(tmp), [entry])
            with self.assertRaises(CannotDetermine) as ctx:
                compat_gate.load_acks(path)
        self.assertIn("migration", str(ctx.exception))
        self.assertIn("rubber stamp", str(ctx.exception),
                      "the refusal must say WHY a migration note is mandatory")

    def test_empty_migration_is_refused_like_a_missing_one(self) -> None:
        """'accepted' with the field blanked is the rubber stamp in disguise."""
        entry = dict(GOOD_ACK, migration="   ")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_acks(Path(tmp), [entry])
            with self.assertRaises(CannotDetermine):
                compat_gate.load_acks(path)

    def test_entry_without_consumer_invocation_is_refused(self) -> None:
        entry = {k: v for k, v in GOOD_ACK.items() if k != "consumerInvocation"}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_acks(Path(tmp), [entry])
            with self.assertRaises(CannotDetermine):
                compat_gate.load_acks(path)

    def test_one_bad_entry_refuses_the_whole_file(self) -> None:
        """Fail closed. A partial load would grade a real break on a partial set."""
        bad = {k: v for k, v in GOOD_ACK.items() if k != "migration"}
        bad["id"] = "bad-entry"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_acks(Path(tmp), [GOOD_ACK, bad])
            with self.assertRaises(CannotDetermine):
                compat_gate.load_acks(path)

    def test_duplicate_acknowledgement_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_acks(Path(tmp), [GOOD_ACK, dict(GOOD_ACK, id="other")])
            with self.assertRaises(CannotDetermine) as ctx:
                compat_gate.load_acks(path)
        self.assertIn("already acknowledges", str(ctx.exception))

    def test_malformed_json_is_refused_not_treated_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acks.json"
            path.write_text("{not json")
            with self.assertRaises(CannotDetermine):
                compat_gate.load_acks(path)

    def test_missing_file_is_empty_and_not_a_refusal(self) -> None:
        """The one absence that is a real state: nothing has been acknowledged.

        Paired with the malformed case above — unreadable and empty must not
        produce the same verdict, but *absent* legitimately means zero.
        """
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(compat_gate.load_acks(Path(tmp) / "nope.json"), [])

    def test_this_repos_own_ack_file_loads(self) -> None:
        """The committed instance must be valid, or the gate refuses in CI."""
        compat_gate.load_acks(REPO / gate_cli.DEFAULT_ACKS)


# ------------------------------------------------------- the baseline's refusals


class BaselineResolution(unittest.TestCase):

    def test_release_tag_is_discoverable_here(self) -> None:
        """The positive case: this repo has a tag and it is found."""
        tag = compat_gate.latest_release_tag(REPO)
        self.assertTrue(tag.startswith("design-suite--v"), tag)

    def test_no_release_tag_refuses_rather_than_passing(self) -> None:
        """A repo with no matching tag must be exit 2, never a clean pass.

        This is the governing principle applied to this gate: a check that
        passed because it could not find its baseline is indistinguishable from
        one that passed because the tree was clean.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (["init", "-q"], ["add", "-A"]):
                subprocess.run(["git", "-C", str(root), *args], check=True,
                               capture_output=True)
            (root / "f.txt").write_text("x")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                           capture_output=True)
            subprocess.run(
                ["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "c"], check=True,
                capture_output=True)
            with self.assertRaises(CannotDetermine) as ctx:
                compat_gate.latest_release_tag(root)
            self.assertIn("exit 2", str(ctx.exception))

            # And the CLI turns that into exit 2, not exit 0.
            proc = subprocess.run(
                [sys.executable, str(BIN / "gate_consumer_compat.py"),
                 "--repo", str(root)], capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("cannot determine", proc.stderr)

    def test_unresolvable_revision_refuses(self) -> None:
        with self.assertRaises(CannotDetermine):
            compat_gate.evaluate(REPO, [], old_rev="no-such-rev-here",
                                 new_rev="HEAD")


# --------------------------------------------------------------- the CLI contract


class CliExitCodes(unittest.TestCase):
    """Each case is one full CLI run of the gate against this repository.

    Four of those runs walk the whole release-tag range and cost ~20-30s each,
    so ``setUpClass`` launches all five concurrently (they only read git blobs
    and their own private ack files) and each test asserts on its own result.
    The assertions are exactly what they were when each test ran its own
    subprocess inline; only *when* the subprocess runs moved.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from concurrent.futures import ThreadPoolExecutor

        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        for name in ("unacked", "json", "malformed", "stale"):
            (tmp / name).mkdir()
        unacked = _write_acks(tmp / "unacked", [])
        json_acks = _write_acks(tmp / "json", [])
        malformed = tmp / "malformed" / "acks.json"
        malformed.write_text('{"entries": [{"id": "x"}]}')
        stale = dict(GOOD_ACK, id="stale-one", subject="plugins/nothing/here.py")
        # The stale case runs the DEFAULT range (release tag -> HEAD) against the
        # live tree, so the substituted ack file must still carry whatever
        # this repository genuinely acknowledges. Without that, the case
        # asserts exit 0 on a tree that legitimately holds an acknowledged
        # break, and any commit that ships one fails a test about staleness
        # for a reason that has nothing to do with staleness.
        real = compat_gate.load_acks(REPO / gate_cli.DEFAULT_ACKS)
        stale_acks = _write_acks(tmp / "stale", [*real, stale])

        argvs = {
            "clean": (),
            "unacked": ("--from", OLD_REV, "--to", NEW_REV, "--acks", str(unacked)),
            "malformed": ("--from", OLD_REV, "--to", NEW_REV, "--acks", str(malformed)),
            "json": ("--from", OLD_REV, "--to", NEW_REV, "--acks", str(json_acks),
                     "--json"),
            "stale": ("--acks", str(stale_acks)),
        }
        with ThreadPoolExecutor(max_workers=len(argvs)) as pool:
            futures = {k: pool.submit(_run, *v) for k, v in argvs.items()}
            cls.procs = {k: f.result() for k, f in futures.items()}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_clean_tree_against_its_own_tag_exits_zero(self) -> None:
        proc = self.procs["clean"]
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_unacknowledged_range_exits_one_and_prints_a_skeleton(self) -> None:
        proc = self.procs["unacked"]
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("BLOCKING", proc.stdout)
        self.assertIn('"migration"', proc.stdout,
                      "the failure must hand the author the form to fill in")

    def test_refusal_exit_is_two_not_one(self) -> None:
        """A malformed ack file is 'cannot determine', not 'here are findings'."""
        proc = self.procs["malformed"]
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_json_report_is_machine_readable(self) -> None:
        proc = self.procs["json"]
        report = json.loads(proc.stdout)
        self.assertEqual(report["counts"]["blocking"], len(report["blocking"]))

    def test_stale_acknowledgement_is_reported_and_does_not_fail(self) -> None:
        """Tidying up must not be punished — but it must not be invisible either."""
        proc = self.procs["stale"]
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("STALE", proc.stdout)
        self.assertIn("stale-one", proc.stdout)

# ------------------------------------------------- blind spots, synthetic repos


from design_suite.engine import upgrade  # noqa: E402

PFX = "plugins/design-suite"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                    "-c", "user.name=t", *args], check=True,
                   capture_output=True, text=True)


def _synthetic(old: dict[str, str], new: dict[str, str]) -> Path:
    """A repo with `old` committed and tagged (annotated, as the real tag is),
    then `new` committed on top. Keys are paths under the plugin prefix."""
    repo = Path(tempfile.mkdtemp())
    atexit.register(shutil.rmtree, repo, ignore_errors=True)
    _git(repo, "init", "-q")

    def write(files: dict[str, str]) -> None:
        for rel, body in files.items():
            path = repo / PFX / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        for rel in set(old) - set(files):
            (repo / PFX / rel).unlink(missing_ok=True)

    write(old)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "old")
    _git(repo, "tag", "-a", "design-suite--v0.0.1", "-m", "release")
    write(new)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "new", "--allow-empty")
    return repo


def _gate(old: dict[str, str], new: dict[str, str]) -> dict:
    return compat_gate.evaluate(_synthetic(old, new), [])


def _by_category(report: dict, category: str) -> list[dict]:
    return [f for f in report["blocking"] + report["advisory"]
            if f["category"] == category]


AUDIT = "bin/audit_x.py"
MAIN = "import sys\n\ndef main():\n{body}\n\nif __name__ == '__main__':\n    sys.exit(main())\n"


def _main(*lines: str) -> str:
    return MAIN.format(body="\n".join("    " + ln for ln in lines))


class ExitSiteResolution(unittest.TestCase):
    def codes(self, src: str) -> list[int]:
        return upgrade.exit_contract(upgrade.exit_sites(src))["codes"]

    def test_systemexit_message_is_one(self):
        self.assertEqual(self.codes('raise SystemExit("no config")\n'), [1])
        self.assertEqual(self.codes('raise SystemExit(f"no {x}")\n'), [1])
        self.assertEqual(self.codes('raise SystemExit(str(exc))\n'), [1])

    def test_systemexit_empty_and_bare_are_zero(self):
        self.assertEqual(self.codes("raise SystemExit()\n"), [0])
        self.assertEqual(self.codes("raise SystemExit\n"), [0])

    def test_systemexit_int_and_module_constant(self):
        self.assertEqual(self.codes("raise SystemExit(2)\n"), [2])
        self.assertEqual(self.codes("REFUSED = 2\nraise SystemExit(REFUSED)\n"), [2])
        self.assertEqual(self.codes("A, B = 0, 3\ndef f():\n    return B\n"), [3])

    def test_refused_is_two_whatever_the_message(self):
        self.assertEqual(self.codes('raise Refused("x", audit="a")\n'), [2])
        self.assertEqual(self.codes('raise refusal.Refused("x")\n'), [2])

    def test_local_main_is_a_delegation_not_a_site(self):
        self.assertEqual(self.codes(_main("return 0")), [0])
        self.assertEqual(upgrade.exit_contract(
            upgrade.exit_sites(_main("return 0")))[upgrade.DYNAMIC], [])

    def test_unresolvable_is_reported_as_dynamic_never_dropped(self):
        """Governing principle: what cannot be resolved is named, not ignored."""
        src = "import sys\nfrom elsewhere import main\nsys.exit(main())\nsys.exit(rc)\n"
        contract = upgrade.exit_contract(upgrade.exit_sites(src))
        self.assertEqual(contract[upgrade.DYNAMIC], ["main()", "rc"])
        self.assertEqual(contract["codes"], [])


class BlindSpotsOnSyntheticRepos(unittest.TestCase):
    def test_raise_systemexit_message_to_refused_is_caught(self):
        report = _gate({AUDIT: _main('raise SystemExit("no config")', "return 0")},
                       {AUDIT: _main('raise Refused("no config")', "return 0")})
        found = _by_category(report, "exit-contract-changed")
        self.assertEqual([f["subject"] for f in found], [f"{PFX}/{AUDIT}"])
        self.assertEqual((found[0]["beforeCodes"], found[0]["afterCodes"]),
                         ([0, 1], [0, 2]))
        self.assertEqual(found[0]["severity"], "critical")

    def test_added_raise_systemexit_2_is_caught(self):
        report = _gate({AUDIT: _main("return 0")},
                       {AUDIT: _main("if x:\n        raise SystemExit(2)", "return 0")})
        self.assertEqual(len(_by_category(report, "exit-contract-changed")), 1)

    def test_new_refusal_site_with_same_code_set_is_caught(self):
        """audit_tokens' shape: it already could exit 2; now one more path does."""
        report = _gate({AUDIT: _main("if a:\n        return 2", "return 0")},
                       {AUDIT: _main("if a:\n        return 2",
                                     "if b:\n        return 2", "return 0")})
        self.assertEqual(len(_by_category(report, "exit-contract-changed")), 1)

    def test_library_change_is_graded_by_the_audits_importing_it(self):
        lib = "design_suite/engine/arch.py"
        user = "from design_suite.engine import arch\n" + _main("arch.load()", "return 0")
        report = _gate({lib: 'def load():\n    raise SystemExit("missing")\n', AUDIT: user},
                       {lib: 'def load():\n    raise Refused("missing")\n', AUDIT: user})
        found = _by_category(report, "exit-contract-changed")
        self.assertEqual([f["subject"] for f in found], [f"{PFX}/{lib}"])
        self.assertEqual(found[0]["severity"], "critical")
        self.assertEqual(found[0]["importedByAudits"], [f"{PFX}/{AUDIT}"])

    def test_out_default_moved_is_caught(self):
        def src(default: str) -> str:
            return ("import argparse\np = argparse.ArgumentParser()\n"
                    f"p.add_argument('--out', default={default!r})\n")
        report = _gate({AUDIT: src("scripts/x_findings.json")},
                       {AUDIT: src(".design-suite/x-findings.json")})
        found = _by_category(report, "output-path-moved")
        self.assertEqual([f["subject"] for f in found], [f"{PFX}/{AUDIT} --out"])
        self.assertIn("scripts/x_findings.json", found[0]["before"])
        self.assertEqual(found[0]["severity"], "critical")

    def test_out_constant_moved_is_caught(self):
        report = _gate({AUDIT: 'DEFAULT_OUT = "a.json"\n'},
                       {AUDIT: 'DEFAULT_OUT = "b.json"\n'})
        self.assertEqual([f["subject"] for f in _by_category(report, "output-path-moved")],
                         [f"{PFX}/{AUDIT} DEFAULT_OUT"])

    def test_more_return_zero_is_not_a_break(self):
        """The audit_on_edit false positive: every path still exits 0."""
        report = _gate({AUDIT: _main("return 0")},
                       {AUDIT: _main("if a:\n        return 0",
                                     "if b:\n        return 0", "return 0")})
        self.assertEqual(report["blocking"] + report["advisory"], [])

    def test_reworded_refusal_message_is_not_a_break(self):
        report = _gate({AUDIT: _main('raise SystemExit("old words")')},
                       {AUDIT: _main('raise SystemExit(f"new {words}")')})
        self.assertEqual(report["blocking"] + report["advisory"], [])

    def test_unresolved_exit_is_named_in_the_notes(self):
        src = "import sys\nsys.exit(compute())\n"
        report = _gate({AUDIT: src}, {AUDIT: src + "\n"})
        self.assertTrue(any("could not be resolved" in n and "compute()" in n
                            for n in report["notes"]), report["notes"])

    def test_unresolved_exit_change_is_a_finding(self):
        report = _gate({AUDIT: "import sys\nsys.exit(a())\n"},
                       {AUDIT: "import sys\nsys.exit(b())\n"})
        self.assertEqual(len(_by_category(report, "exit-contract-changed")), 1)

    def test_output_path_moved_is_acknowledgeable(self):
        repo = _synthetic({AUDIT: 'DEFAULT_OUT = "a.json"\n'},
                          {AUDIT: 'DEFAULT_OUT = "b.json"\n'})
        ack = dict(GOOD_ACK, category="output-path-moved",
                   subject=f"{PFX}/{AUDIT} DEFAULT_OUT")
        with tempfile.TemporaryDirectory() as tmp:
            acks = compat_gate.load_acks(_write_acks(Path(tmp), [ack]))
        report = compat_gate.evaluate(repo, acks)
        self.assertEqual(report["blocking"], [])
        self.assertEqual(len(report["acknowledged"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
