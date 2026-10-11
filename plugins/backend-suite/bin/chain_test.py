#!/usr/bin/env python3
"""Tests for the chain runner and its sequencing engine.

`bin/chain.py` had no test file at all. Every other script in this directory has
one, and `run_tests.py` refuses to be silent about a test that does not run — but
nothing checks that a script *has* a test, which is how this survived. A chain
runner is a bad thing to leave untested in particular: its whole job is to
remember where a sequence got to, so its failure mode is not a crash, it is
confidently reporting the wrong position.

Written under this directory's standing rule: **every refusal is tested next to
the positive case it must not swallow.** A runner that refuses on everything is
not careful, it is broken.

The headline case is `StateFileHandling.test_unreadable_state_refuses_...`.
`read_state` used to return `{}` on any read error, with a comment arguing that
starting over was recoverable. What it actually produced was a chain five steps
into an onboarding being told `Next: brand-voice` — step 1 — indistinguishable
from a chain that had never run. That is this repo's governing principle in
miniature, and the test is written against the behaviour rather than the
implementation: it asserts the *position is not silently lost*.
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
sys.path.insert(0, str(BIN))

from _bootstrap import PLUGIN_ROOT  # noqa: E402

from backend_suite.engine import chains as C  # noqa: E402

CHAIN_CLI = BIN / "chain.py"
SHIPPED = PLUGIN_ROOT / "templates" / "chains" / "onboard-new-client.json"

# A minimal chain exercising every shape the engine distinguishes: a checkpointed
# step, a non-checkpointed one, and a second checkpointed one after them so
# "blocks here" and "runs past" are both observable in one definition.
CHAIN = {
    "schemaVersion": 1,
    "name": "test-chain",
    "description": "A chain for testing.",
    "steps": [
        {"id": "one", "skill": "survey", "checkpoint": True,
         "purpose": "First.", "onFail": "halt"},
        {"id": "two", "skill": "map-project", "checkpoint": False,
         "onFail": "halt"},
        {"id": "three", "skill": "design-debt", "checkpoint": True,
         "onFail": "skip"},
    ],
}


def _project(root: Path, chain: dict = None) -> Path:
    """A minimal consumer project: a `.backend-suite/` marker and one chain."""
    (root / ".backend-suite").mkdir(parents=True, exist_ok=True)
    directory = root / C.CHAINS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    body = chain if chain is not None else CHAIN
    (directory / f"{body['name']}.json").write_text(json.dumps(body, indent=2))
    return root


def _cli(root: Path, *args) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(CHAIN_CLI), *args],
                          capture_output=True, text=True, cwd=str(root), env=env)


class ChainLoading(unittest.TestCase):
    def test_the_shipped_chain_loads_and_is_the_one_documented(self):
        chain = C.load(SHIPPED)
        self.assertEqual(chain["name"], "onboard-new-client")
        self.assertEqual([s["id"] for s in chain["steps"]],
                         ["survey", "doc-suite", "propose-config", "baseline-debt"])

    def test_a_project_chain_wins_over_the_shipped_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp), dict(CHAIN, name="onboard-new-client"))
            path = C.chain_path(root, "onboard-new-client", PLUGIN_ROOT)
            self.assertEqual(path.parent, root / C.CHAINS_DIR)

    def test_the_shipped_one_is_found_when_the_project_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = C.chain_path(Path(tmp), "onboard-new-client", PLUGIN_ROOT)
            self.assertEqual(path, SHIPPED)

    # --- refusals, each beside the positive case above ---

    def test_refuses_an_unknown_chain_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(C.ChainError) as caught:
                C.chain_path(Path(tmp), "no-such-chain", PLUGIN_ROOT)
            self.assertIn("no-such-chain", str(caught.exception))

    def test_refuses_a_definition_that_is_not_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{ not json")
            with self.assertRaises(C.ChainError):
                C.load(path)

    def test_refuses_a_definition_with_no_steps_or_a_malformed_step(self):
        cases = {
            "no steps key": {"name": "x"},
            "empty steps": {"name": "x", "steps": []},
            "step is not an object": {"name": "x", "steps": ["one"]},
            "step has no id": {"name": "x", "steps": [{"skill": "a"}]},
            "step names no skill": {"name": "x", "steps": [{"id": "one"}]},
            "duplicate ids": {"name": "x", "steps": [{"id": "a", "skill": "s"},
                                                     {"id": "a", "skill": "t"}]},
            "unknown onFail": {"name": "x", "steps": [{"id": "a", "skill": "s",
                                                       "onFail": "retry"}]},
        }
        for label, body in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "c.json"
                path.write_text(json.dumps(body))
                with self.assertRaises(C.ChainError):
                    C.load(path)
        # ...and a well-formed definition at the same path still loads, so the
        # cases above are failing on their own defect and not on the harness.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps(CHAIN))
            self.assertEqual(len(C.load(path)["steps"]), 3)


class MissingSkills(unittest.TestCase):
    def test_every_shipped_chain_step_names_a_skill_that_exists(self):
        """Not a unit test of `missing_skills` — a test of the artefact. A shipped
        chain pointing at a renamed skill is a playbook that dead-ends on a real
        user's project."""
        available = {p.stem for p in (PLUGIN_ROOT / "commands").glob("*.md")}
        self.assertTrue(available, "no commands found — the check would be vacuous")
        self.assertEqual(C.missing_skills(C.load(SHIPPED), available), [])

    def test_a_step_naming_a_nonexistent_skill_is_reported(self):
        broken = dict(CHAIN, steps=[{"id": "one", "skill": "no-such-skill"}])
        self.assertEqual(C.missing_skills(broken, {"establish-brand-voice"}),
                         ["one -> no-such-skill"])

    def test_the_cli_refuses_a_chain_naming_a_nonexistent_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp), dict(
                CHAIN, steps=[{"id": "one", "skill": "skill-that-does-not-exist"}]))
            result = _cli(root, "next", "test-chain")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("skill-that-does-not-exist", result.stderr)

    def test_the_cli_still_runs_a_chain_whose_skills_all_exist(self):
        # The positive case the refusal above must not swallow.
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            result = _cli(root, "next", "test-chain")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("one", result.stdout)


class NeverRunChain(unittest.TestCase):
    def test_status_of_a_never_run_chain_is_every_step_pending(self):
        rows = C.status(CHAIN, {}, "test-chain")
        self.assertEqual([r["status"] for r in rows],
                         [C.PENDING, C.PENDING, C.PENDING])
        self.assertEqual([r["id"] for r in rows], ["one", "two", "three"])

    def test_next_of_a_never_run_chain_is_the_first_step_unblocked(self):
        step = C.next_step(CHAIN, {}, "test-chain")
        self.assertEqual(step["id"], "one")
        self.assertFalse(step["blocked"])

    def test_checkpoint_defaults_to_true_when_a_step_does_not_say(self):
        silent = {"name": "x", "steps": [{"id": "a", "skill": "s"}]}
        self.assertTrue(C.status(silent, {}, "x")[0]["checkpoint"])
        self.assertTrue(C.next_step(silent, {}, "x")["checkpoint"])


class Resuming(unittest.TestCase):
    """The capability the whole script exists for: a chain must resume, not restart."""

    def test_resumes_mid_chain_rather_than_restarting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.DONE)   # -> awaiting ack
            C.mark(root, CHAIN, "test-chain", "one", C.DONE)   # -> done
            state = C.read_state(root)
            self.assertEqual(C.next_step(CHAIN, state, "test-chain")["id"], "two")

    def test_a_resolved_chain_reports_none_rather_than_looping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            for step_id in ("one", "three"):
                C.mark(root, CHAIN, "test-chain", step_id, C.DONE)
                C.mark(root, CHAIN, "test-chain", step_id, C.DONE)
            C.mark(root, CHAIN, "test-chain", "two", C.DONE)
            state = C.read_state(root)
            self.assertIsNone(C.next_step(CHAIN, state, "test-chain"))

    def test_position_survives_a_new_process(self):
        # The actual claim on the tin — "a chain survives a session ending
        # halfway" — exercised through the CLI rather than in-process state.
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            self.assertEqual(_cli(root, "done", "test-chain", "one").returncode, 0)
            self.assertEqual(_cli(root, "ack", "test-chain", "one").returncode, 0)
            result = _cli(root, "next", "test-chain")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("two", result.stdout)
            self.assertNotIn("Next: one", result.stdout)

    def test_reset_clears_the_position_deliberately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.DONE)
            C.reset(root, "test-chain")
            state = C.read_state(root)
            self.assertEqual(C.next_step(CHAIN, state, "test-chain")["id"], "one")

    def test_reset_touches_only_the_named_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            other = dict(CHAIN, name="other-chain")
            C.mark(root, CHAIN, "test-chain", "one", C.DONE)
            C.mark(root, other, "other-chain", "one", C.DONE)
            C.reset(root, "test-chain")
            state = C.read_state(root)
            self.assertEqual(
                state["chains"]["other-chain"]["steps"]["one"]["status"],
                C.AWAITING_ACK)


class Checkpoints(unittest.TestCase):
    """CHECKPOINTS DEFAULT TO ON, per the engine's own module docstring. These
    assert the two-call contract, which is the only thing stopping this runner
    from breaking the sign-off contract of the skills it composes."""

    def test_a_checkpointed_step_lands_on_awaiting_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            entry = C.mark(root, CHAIN, "test-chain", "one", C.DONE)
            self.assertEqual(entry["status"], C.AWAITING_ACK)

    def test_an_awaiting_step_blocks_next_rather_than_being_stepped_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.DONE)
            step = C.next_step(CHAIN, C.read_state(root), "test-chain")
            self.assertEqual(step["id"], "one")
            self.assertTrue(step["blocked"])

    def test_a_second_call_clears_the_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.DONE)
            entry = C.mark(root, CHAIN, "test-chain", "one", C.DONE)
            self.assertEqual(entry["status"], C.DONE)
            self.assertFalse(
                C.next_step(CHAIN, C.read_state(root), "test-chain")["blocked"])

    def test_a_non_checkpointed_step_completes_in_one_call(self):
        # The positive case the checkpoint block must not swallow: opting out is
        # per-step and declared, so a step that opted out must not be held.
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            entry = C.mark(root, CHAIN, "test-chain", "two", C.DONE)
            self.assertEqual(entry["status"], C.DONE)

    def test_the_cli_says_a_checkpoint_is_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            result = _cli(root, "done", "test-chain", "one")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("checkpoint", result.stdout)
            self.assertIn("ack", result.stdout)


class SkippedSteps(unittest.TestCase):
    def test_a_skipped_step_resolves_and_the_chain_moves_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            entry = C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED,
                           "voice already documented")
            self.assertEqual(entry["status"], C.SKIPPED)
            self.assertEqual(entry["note"], "voice already documented")
            self.assertEqual(
                C.next_step(CHAIN, C.read_state(root), "test-chain")["id"], "two")

    def test_skipping_a_checkpointed_step_does_not_become_awaiting_ack(self):
        # SKIPPED is a decision already made; routing it through the checkpoint
        # would ask for sign-off on a step nobody ran.
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            self.assertEqual(
                C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED)["status"],
                C.SKIPPED)

    def test_a_skip_note_is_visible_in_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED, "docs exist")
            rows = C.status(CHAIN, C.read_state(root), "test-chain")
            self.assertEqual(rows[0]["note"], "docs exist")

    def test_a_skip_with_no_note_records_no_empty_note_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            self.assertNotIn(
                "note", C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED))


class Marking(unittest.TestCase):
    def test_refuses_a_step_the_chain_does_not_define(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            with self.assertRaises(C.ChainError) as caught:
                C.mark(root, CHAIN, "test-chain", "not-a-step", C.DONE)
            self.assertIn("not-a-step", str(caught.exception))
            # ...and a step it does define still marks.
            self.assertTrue(C.mark(root, CHAIN, "test-chain", "two", C.DONE))

    def test_refuses_an_unknown_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            with self.assertRaises(C.ChainError):
                C.mark(root, CHAIN, "test-chain", "one", "finished-ish")

    def test_the_cli_refuses_done_without_a_step_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            self.assertEqual(_cli(root, "done", "test-chain").returncode, 2)

    def test_the_cli_refuses_an_unknown_chain_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            result = _cli(root, "status", "no-such-chain")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("no-such-chain", result.stderr)


class StateFileHandling(unittest.TestCase):
    """What happens when the state file is missing, unreadable, or out of date
    with the chain definition. Stated explicitly because each answer is different
    and only one of them is 'start over'."""

    def test_a_missing_state_file_is_an_empty_position_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            self.assertFalse((root / C.STATE_FILE).exists())
            self.assertEqual(C.read_state(root), {})
            self.assertEqual(
                C.next_step(CHAIN, C.read_state(root), "test-chain")["id"], "one")

    def test_unreadable_state_refuses_rather_than_silently_restarting(self):
        """THE regression this file exists for.

        `read_state` used to return `{}` on a parse error, so a chain most of the
        way through an onboarding reported step 1 as next, in exactly the tone of
        a chain that had never run. Position-lost and position-never-set were
        indistinguishable, which is the governing principle's failure in
        miniature."""
        for corrupt in ("{ truncated", "", "[]", "null", '"a string"'):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as tmp:
                root = _project(Path(tmp))
                (root / C.STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
                (root / C.STATE_FILE).write_text(corrupt)
                with self.assertRaises(C.ChainError):
                    C.read_state(root)

    def test_the_cli_exits_2_on_unreadable_state_and_names_the_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            (root / C.STATE_FILE).write_text("{ truncated")
            for action in ("status", "next"):
                with self.subTest(action=action):
                    result = _cli(root, action, "test-chain")
                    self.assertEqual(result.returncode, 2, result.stdout)
                    # Not merely non-zero: it must NOT have printed a position.
                    self.assertNotIn("Next: one", result.stdout)
                    self.assertIn("reset", result.stderr)

    def test_a_valid_state_file_still_reads_after_all_that(self):
        # The positive case the refusals above must not swallow.
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED)
            result = _cli(root, "status", "test-chain")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("one", result.stdout)

    def test_reset_is_the_one_caller_allowed_to_discard_corrupt_state(self):
        # Refusing to reset because the thing being reset is corrupt would leave
        # no recovery but deleting the file by hand — so `reset` forgives, and
        # only `reset`.
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            (root / C.STATE_FILE).write_text("{ truncated")
            result = _cli(root, "reset", "test-chain")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(C.read_state(root), {"chains": {}})

    def test_a_chain_whose_definition_changed_underneath_its_state(self):
        """A recorded step the definition no longer has. The outcome is lost —
        the schema says renaming an id does that — but it must be VISIBLE, or a
        completed step reappears as pending with no explanation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED)
            renamed = dict(CHAIN, steps=[
                dict(CHAIN["steps"][0], id="one-renamed"), *CHAIN["steps"][1:]])
            state = C.read_state(root)
            self.assertEqual(C.orphaned_steps(renamed, state, "test-chain"), ["one"])
            # The renamed step is genuinely pending again — that part is correct.
            self.assertEqual(
                C.next_step(renamed, state, "test-chain")["id"], "one-renamed")

    def test_no_orphans_reported_when_the_definition_did_not_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(Path(tmp))
            C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED)
            self.assertEqual(
                C.orphaned_steps(CHAIN, C.read_state(root), "test-chain"), [])

    def test_the_cli_surfaces_an_orphaned_step_rather_than_dropping_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)
            C.mark(root, CHAIN, "test-chain", "one", C.SKIPPED)
            renamed = dict(CHAIN, steps=[
                dict(CHAIN["steps"][0], id="one-renamed"), *CHAIN["steps"][1:]])
            (root / C.CHAINS_DIR / "test-chain.json").write_text(
                json.dumps(renamed, indent=2))
            result = _cli(root, "status", "test-chain")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("one", result.stderr)
            self.assertIn("no longer", result.stderr)


class DoesNotInvokeAnything(unittest.TestCase):
    def test_the_runner_never_shells_out_to_a_skill(self):
        """Stated in the module docstring as a design decision, so it is worth a
        test: this records position, it does not run anything. A future edit that
        made it invoke would be a much larger change than it looked."""
        source = CHAIN_CLI.read_text()
        for forbidden in ("subprocess", "os.system", "os.exec"):
            self.assertNotIn(forbidden, source)


class UnconfiguredProject(unittest.TestCase):
    """understand-existing-project starts where no `.backend-suite/` exists yet.

    Found by running that chain end to end: `status` and `next` refused with
    "Refusing to guess" before step one, so the chain could not show its own
    first step. Reading position must work there; recording it must not create
    the marker directory as a side effect.
    """

    def test_status_and_next_read_on_a_project_with_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = _cli(root, "status", "understand-existing-project")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("survey", status.stdout)
            nxt = _cli(root, "next", "understand-existing-project")
            self.assertEqual(nxt.returncode, 0, nxt.stderr)
            self.assertIn("Next: survey", nxt.stdout)
            self.assertFalse((root / ".backend-suite").exists(),
                             "a read-only action created the marker directory")

    def test_recording_still_refuses_without_a_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            done = _cli(root, "done", "understand-existing-project", "survey")
            self.assertEqual(done.returncode, 2)
            self.assertFalse((root / ".backend-suite").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
