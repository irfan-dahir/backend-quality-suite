#!/usr/bin/env python3
"""Tests for `eval_results_read.py`.

Every fixture below is the minimum shape copied out of a real run under
`evals/results/` — those directories are gitignored and may be cleaned, so
nothing here depends on their paths. The run ids in the docstrings are the
provenance of each shape, not a dependency.

Each refusal is tested **paired with the positive case it must not swallow**. A
reader that flags everything is as useless as one that flags nothing, so:

  * 0-turn arm refused  — short-but-nonzero arm accepted;
  * all-errored case VOID — one-of-three errored stays quotable;
  * skipped grader refused — a merely *failing* grader accepted;
  * missing/unparseable input is exit 2 — a well-formed run is 0, never 2.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
READER = BIN / "eval_results_read.py"

LIMIT = "exit 1: You've hit your session limit · resets 11:40am (Asia/Karachi)"


def run_obj(score=0.5, turns=10, error=None, skipped_paid=False,
            graders=None) -> dict:
    return {
        "score": score, "passed": False, "turns": turns, "costUsd": 0.1,
        "error": error, "skippedPaidGraders": skipped_paid,
        "graders": graders if graders is not None else [
            {"name": "counts-one-stub", "passed": True, "weight": 1,
             "explanation": "matched Stub documents:\\s*1", "scored": True},
        ],
    }


def aggregate(cases: list[dict], *, ablation="with-without", partial=False,
              schema=1) -> dict:
    return {
        "schemaVersion": schema, "claudeVersion": "2.1.273",
        "startedAt": "2026-09-23T12:17:45.460Z", "partial": partial,
        "costUsd": 5.15,
        "suite": {"ablation": ablation, "caseFilter": None},
        "cases": cases,
    }


def case(name: str, with_runs: list[dict], without_runs: list[dict] | None):
    arms = {"with": with_runs}
    if without_runs is not None:
        arms["without"] = without_runs
    return {"name": name, "dir": f"evals/{name}", "runsPerCase": len(with_runs),
            "graders": [], "arms": arms, "aggregates": {}}


class ReaderTest(unittest.TestCase):

    def read(self, data, *extra):
        """Write an aggregate to a temp dir and read it. Returns (code, out)."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "2026-09-23T12-17-45-460Z"
            run_dir.mkdir()
            if data is not None:
                (run_dir / "aggregate-result.json").write_text(
                    data if isinstance(data, str) else json.dumps(data))
            proc = subprocess.run(
                [sys.executable, str(READER), str(run_dir), "--json", *extra],
                capture_output=True, text=True)
            return proc.returncode, proc.stdout + proc.stderr

    def verdict(self, data):
        code, out = self.read(data)
        self.assertNotEqual(code, 2, f"unexpected CANNOT DETERMINE:\n{out}")
        return code, json.loads(out)

    # -- 0-turn arm ------------------------------------------------------
    # Shape from 2026-09-23T23-43-56-620Z: every promote-component `without`
    # arm ran 0 turns and still banked its absence graders.

    def test_zero_turn_arm_yields_no_delta(self):
        code, v = self.verdict(aggregate([case(
            "promote-component-cross-repo-write",
            [run_obj(score=0.667, turns=39)],
            [run_obj(score=0.333, turns=0)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "ONE-ARMED")
        self.assertIsNone(v["cases"][0]["delta"])
        self.assertFalse(v["quotable"])
        self.assertTrue(any("turns: 0" in r for r in v["cases"][0]["reasons"]))

    def test_short_but_nonzero_arm_is_not_flagged(self):
        """2026-09-23T12-17-45-460Z's `without` arm ran 3 turns. Live."""
        code, v = self.verdict(aggregate([case(
            "review-docs-no-false-drift",
            [run_obj(score=0.5, turns=34)], [run_obj(score=0.0, turns=3)])]))
        self.assertEqual(code, 0)
        self.assertEqual(v["cases"][0]["verdict"], "QUOTABLE")
        self.assertAlmostEqual(v["cases"][0]["delta"], 0.5)
        self.assertEqual(v["cases"][0]["reasons"], [])

    # -- aborted runs ----------------------------------------------------
    # Shape from 2026-09-18T03-42-13-832Z: 45 runs died on the session limit.

    def test_every_run_errored_is_void_not_a_score(self):
        code, v = self.verdict(aggregate([case(
            "review-docs-zero-state-refusal",
            [run_obj(score=0.25, turns=1, error=LIMIT) for _ in range(3)],
            [run_obj(score=0.25, turns=1, error=LIMIT) for _ in range(3)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "VOID")
        self.assertIsNone(v["cases"][0]["delta"])
        self.assertTrue(any(LIMIT in r for r in v["cases"][0]["reasons"]))

    def test_one_errored_run_of_three_stays_quotable_with_a_caveat(self):
        """design-auditor-undeclared-kind lost 1 of 3. Noise, not a void."""
        code, v = self.verdict(aggregate([case(
            "design-auditor-undeclared-kind",
            [run_obj(score=0.917, turns=19) for _ in range(3)],
            [run_obj(score=0.75, turns=23), run_obj(score=0.5, turns=23),
             run_obj(score=0.25, turns=25, error=LIMIT)])]))
        self.assertEqual(code, 0)
        self.assertEqual(v["cases"][0]["verdict"], "QUOTABLE")
        self.assertEqual(v["cases"][0]["arms"]["without"]["state"], "DEGRADED")
        # The surviving runs set the score; the dead one does not drag it down.
        self.assertAlmostEqual(v["cases"][0]["arms"]["without"]["score"], 0.625)
        self.assertTrue(any(LIMIT in r for r in v["cases"][0]["reasons"]),
                        "a survivable error must still be reported")

    def test_a_case_whose_only_live_arm_is_the_other_one(self):
        """with-arm all errored, without-arm all 0 turns: nothing usable."""
        code, v = self.verdict(aggregate([case(
            "promote-component-refuses-domain-entity",
            [run_obj(turns=1, error=LIMIT) for _ in range(3)],
            [run_obj(turns=0) for _ in range(3)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "VOID")

    # -- skipped graders -------------------------------------------------
    # Shape from 2026-09-23T10-38-52-722Z: --max-cost-usd dropped three
    # `criteria` graders and still reported partial: false.

    def test_skipped_paid_graders_flag_withholds_the_score(self):
        skipped = [{"name": "criteria", "passed": False, "weight": 1,
                    "explanation": "skipped: cost ceiling", "scored": True}]
        code, v = self.verdict(aggregate([case(
            "review-docs-no-false-drift",
            [run_obj(score=0.5, turns=24)],
            [run_obj(score=0.0, turns=29, skipped_paid=True,
                     graders=skipped)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "UNQUOTABLE")
        self.assertIsNone(v["cases"][0]["delta"])
        reasons = " ".join(v["cases"][0]["reasons"])
        self.assertIn("skippedPaidGraders", reasons)
        self.assertIn("skipped: cost ceiling", reasons)

    def test_grader_explanation_skip_is_caught_without_the_run_flag(self):
        """The two signals are independent; either alone must withhold."""
        skipped = [{"name": "criteria", "passed": False, "weight": 1,
                    "explanation": "skipped: cost ceiling", "scored": True}]
        code, v = self.verdict(aggregate([case(
            "review-docs-zero-state-refusal",
            [run_obj(score=1.0, turns=23)],
            [run_obj(score=0.5, turns=18, skipped_paid=False,
                     graders=skipped)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "UNQUOTABLE")

    def test_a_failing_grader_is_a_result_not_a_refusal(self):
        """`judge votes: FAIL FAIL FAIL` is the suite working, not skipping."""
        failed = [{"name": "criteria", "passed": False, "weight": 1,
                   "explanation": "judge votes: FAIL FAIL FAIL",
                   "scored": True}]
        code, v = self.verdict(aggregate([case(
            "review-docs-app-stub-and-decline",
            [run_obj(score=0.8, turns=31, graders=failed)],
            [run_obj(score=0.2, turns=30, graders=failed)])]))
        self.assertEqual(code, 0)
        self.assertEqual(v["cases"][0]["verdict"], "QUOTABLE")
        self.assertEqual(v["cases"][0]["reasons"], [])

    # -- run-level -------------------------------------------------------

    def test_partial_run_is_never_quotable(self):
        code, v = self.verdict(aggregate(
            [case("x", [run_obj()], [run_obj()])], partial=True))
        self.assertEqual(code, 1)
        self.assertTrue(any("partial" in r for r in v["runReasons"]))

    def test_single_arm_ablation_is_not_one_armed_by_defect(self):
        code, v = self.verdict(aggregate(
            [case("x", [run_obj(turns=12)], None)], ablation="with-only"))
        self.assertEqual(code, 0)
        self.assertEqual(v["cases"][0]["verdict"], "SINGLE-ARM")
        self.assertIsNone(v["cases"][0]["delta"])

    def test_clean_three_case_run_exits_zero(self):
        """2026-09-23T12-17-45-460Z's shape: the run that must stay quotable."""
        code, v = self.verdict(aggregate([
            case("review-docs-app-stub-and-decline",
                 [run_obj(score=0.8, turns=31)], [run_obj(score=0.2, turns=30)]),
            case("review-docs-no-false-drift",
                 [run_obj(score=0.5, turns=34)], [run_obj(score=0.0, turns=3)]),
            case("review-docs-zero-state-refusal",
                 [run_obj(score=1.0, turns=23)], [run_obj(score=0.5, turns=18)]),
        ]))
        self.assertEqual(code, 0)
        self.assertTrue(v["quotable"])
        self.assertEqual([c["verdict"] for c in v["cases"]], ["QUOTABLE"] * 3)

    # -- cannot determine is 2, never 0 ----------------------------------

    def test_missing_aggregate_exits_two(self):
        code, out = self.read(None)
        self.assertEqual(code, 2, out)
        self.assertIn("CANNOT DETERMINE", out)

    def test_unparseable_json_exits_two(self):
        code, out = self.read("{not json")
        self.assertEqual(code, 2, out)

    def test_unknown_schema_version_exits_two(self):
        code, out = self.read(aggregate([case("x", [run_obj()], [run_obj()])],
                                        schema=99))
        self.assertEqual(code, 2, out)
        self.assertIn("schemaVersion", out)

    def test_zero_cases_exits_two(self):
        code, out = self.read(aggregate([]))
        self.assertEqual(code, 2, out)

    def test_missing_directory_exits_two(self):
        proc = subprocess.run(
            [sys.executable, str(READER), "/nonexistent/results/run-id"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("CANNOT DETERMINE", proc.stderr)

    def test_no_argument_exits_two(self):
        proc = subprocess.run([sys.executable, str(READER)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_latest_with_no_runs_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(READER), "--latest",
                 "--results-root", tmp],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    # -- runs that completed but measured nothing -------------------------
    # Shapes from 2026-09-18T03-06-49-269Z (don't-ask-mode denials of
    # plugin-folder reads) and 2026-09-23T12-17-45-460Z (a 3-turn `without`
    # arm whose last message was a background-task follow-up).

    @staticmethod
    def said(text, score=0.8, turns=10, trace=None):
        r = run_obj(score=score, turns=turns, graders=[
            {"name": "criteria", "passed": False, "weight": 1,
             "explanation": "judge votes: FAIL FAIL FAIL", "scored": True,
             "evidence": text}])
        if trace is not None:
            r["tracePath"] = trace
        return r

    DENIED = ("**2. Every tool call Step 0 needs was denied by the session's "
              "permission mode.** Claude Code is running in \"don't ask\" mode")
    SKILL_LIST = ("The skills registered are `dataviz`, `update-config`, "
                  "`fewer-permission-prompts`, `loop`. Nothing design-system.")
    FOLLOWUP = ("One correction to the framing in my review: the background "
                "command has now finished and shows `git` was unavailable.")

    def test_permission_denial_in_final_message_is_unquotable(self):
        code, v = self.verdict(aggregate([case(
            "promote-component-no-write-without-go-ahead",
            [self.said(self.DENIED)], [self.said("Answer.", score=0.2)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "UNQUOTABLE")
        self.assertIsNone(v["cases"][0]["delta"])
        self.assertTrue(any("permission denial" in r
                            for r in v["cases"][0]["reasons"]))

    def test_permission_denial_in_trace_is_unquotable(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            trace.write_text(json.dumps({"type": "tool_result", "is_error": True,
                "content": "Permission to use Read has been denied because "
                           "Claude Code is running in don't ask mode."}) + "\n")
            code, v = self.verdict(aggregate([case(
                "design-auditor-undeclared-kind",
                [self.said("Clean report.", trace=str(trace))],
                [self.said("Answer.", score=0.2)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "UNQUOTABLE")
        self.assertTrue(any("in trace" in r for r in v["cases"][0]["reasons"]))

    def test_skill_list_naming_permission_is_not_a_denial(self):
        code, v = self.verdict(aggregate([case(
            "design-auditor-undeclared-kind",
            [self.said("Report.")], [self.said(self.SKILL_LIST, score=0.5)])]))
        self.assertEqual(code, 0, v)
        self.assertEqual(v["cases"][0]["verdict"], "QUOTABLE")

    def test_background_followup_final_message_is_unquotable(self):
        code, v = self.verdict(aggregate([case(
            "review-docs-no-false-drift",
            [self.said("Report.", score=0.5, turns=34)],
            [self.said(self.FOLLOWUP, score=0.0, turns=3)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "UNQUOTABLE")
        self.assertTrue(any("background-task follow-up" in r
                            for r in v["cases"][0]["reasons"]))

    def test_one_turn_run_is_unquotable(self):
        code, v = self.verdict(aggregate([case(
            "review-docs-no-false-drift",
            [self.said("Report.", turns=1)], [self.said("Report.", score=0.2)])]))
        self.assertEqual(code, 1)
        self.assertEqual(v["cases"][0]["verdict"], "UNQUOTABLE")
        self.assertTrue(any("turns: 1" in r for r in v["cases"][0]["reasons"]))

    def test_single_arm_with_denial_is_not_quotable(self):
        code, v = self.verdict(aggregate([case(
            "review-docs-no-false-drift", [self.said(self.DENIED)], None)],
            ablation="with-only"))
        self.assertEqual(code, 1)
        self.assertFalse(v["cases"][0]["quotable"])

    def test_prose_report_names_the_verdict(self):
        """--json is for machines; the default output must be readable."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "2026-09-23T23-43-56-620Z"
            run_dir.mkdir()
            (run_dir / "aggregate-result.json").write_text(json.dumps(
                aggregate([case("promote-component-cross-repo-write",
                                [run_obj(score=0.667, turns=39)],
                                [run_obj(score=0.333, turns=0)])])))
            proc = subprocess.run([sys.executable, str(READER), str(run_dir)],
                                  capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ONE-ARMED", proc.stdout)
        self.assertIn("Δ WITHHELD", proc.stdout)
        self.assertIn("NOT QUOTABLE", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
