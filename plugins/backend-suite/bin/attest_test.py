#!/usr/bin/env python3
"""Tests for attest.py — the verdict, and the conditions attached to it.

    python3 plugins/backend-suite/bin/attest_test.py

Every refusal here is paired with the positive case it must not swallow. That
pairing is the whole point: a verdict function that returned PARTIAL for
everything would satisfy any test that only checked "a skip is not a pass", and
would be useless. So each case that must be PARTIAL sits next to the otherwise
identical case that must be VERIFIED, and vice versa.

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import attest  # noqa: E402
import gates  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


class FakeResult:
    """Stands in for gates.GateResult — only the fields attest reads."""

    def __init__(self, name: str, ok: bool) -> None:
        self.name, self.ok = name, ok
        self.returncode = 0 if ok else 1
        self.seconds = 0.1
        self.stdout, self.stderr = "", "" if ok else "boom"


def build(monkey_plan, monkey_results, monkey_steps):
    """Run attest.attest() against a fabricated plan/result/step set."""
    saved = (gates.plan, gates.run_plan, gates.steps)
    gates.plan, gates.run_plan, gates.steps = monkey_plan, monkey_results, monkey_steps
    try:
        return attest.attest(run=True)
    finally:
        gates.plan, gates.run_plan, gates.steps = saved


COVERED_STEPS = lambda: [  # noqa: E731 - a stub, not a design
    ("t", "python3 plugins/backend-suite/bin/run_tests.py"),
    ("c", "python3 plugins/backend-suite/bin/gate_consumer_compat.py"),
]


def main() -> int:
    print("check: heredoc bodies are not mistaken for programs")

    # The real defect this caught: scanning "first word of each line" walked into
    # an embedded Python program and announced `import` and `except` as tools
    # missing from PATH — a fabricated dependency, reported as an absence.
    cmd = "python3 - <<'PY'\nimport json\nfrom pathlib import Path\nexcept_me = 1\nPY\ngit status"
    kept = attest.strip_heredocs(cmd)
    expect("import json" not in kept and "from pathlib" not in kept,
           "the heredoc body is dropped")
    expect("python3 - <<'PY'" in kept and "git status" in kept,
           f"the shell lines around it survive, got {kept!r}")

    found = attest.programs([cmd])
    expect("import" not in found and "from" not in found and "except_me" not in found,
           f"no Python keyword is reported as a program, got {sorted(found)}")
    # The negative control: stripping must not eat the real commands too, or the
    # fix would "pass" by reporting nothing at all.
    expect("python3" in found and "git" in found,
           f"the real programs are still detected, got {sorted(found)}")

    unterminated = "python3 - <<'PY'\nimport os\n"
    expect("import os" not in attest.strip_heredocs(unterminated),
           "an unterminated heredoc swallows to end-of-command rather than leaking")

    print("check: a clean full run is VERIFIED, and only then")

    report = build(lambda k=None: gates.Plan([("a", "true"), ("b", "true")], [], []),
                   lambda r, on_result=None: [FakeResult("a", True), FakeResult("b", True)],
                   COVERED_STEPS)
    expect(report["verdict"] == "VERIFIED",
           f"every gate ran and passed -> VERIFIED, got {report['verdict']}")
    expect(attest.exit_code(report) == 0, "VERIFIED exits 0")

    print("check: a failed gate is FAILED, not PARTIAL")

    report = build(lambda k=None: gates.Plan([("a", "true"), ("b", "false")], [], []),
                   lambda r, on_result=None: [FakeResult("a", True), FakeResult("b", False)],
                   COVERED_STEPS)
    expect(report["verdict"] == "FAILED",
           f"a failing gate -> FAILED, got {report['verdict']}")
    expect(attest.exit_code(report) == 1, "FAILED exits 1")

    print("check: a skipped gate makes an otherwise-green run PARTIAL")

    # The pairing that matters. This plan is identical to the VERIFIED case above
    # except for one step that could not run. Everything that ran, passed — and
    # that must still not be exit 0, or a partial run is indistinguishable from a
    # verified one, which is this repo's governing failure.
    report = build(lambda k=None: gates.Plan([("a", "true")], [("b", "needs uninstalled yaml")], []),
                   lambda r, on_result=None: [FakeResult("a", True)],
                   COVERED_STEPS)
    expect(report["verdict"] == "PARTIAL",
           f"every gate that ran passed, but one could not run -> PARTIAL, "
           f"got {report['verdict']}")
    expect(attest.exit_code(report) == 2, "PARTIAL exits 2, not 0")
    expect(any("b" == row["name"] for row in report["gatesSkipped"]),
           "the skipped gate is named in the report, not just counted")
    expect("yaml" in report["reason"] or "could not run" in report["reason"],
           f"the reason says what was partial, got {report['reason']!r}")

    print("check: a failure outranks a skip")

    report = build(lambda k=None: gates.Plan([("a", "false")], [("b", "nope")], []),
                   lambda r, on_result=None: [FakeResult("a", False)],
                   COVERED_STEPS)
    expect(report["verdict"] == "FAILED",
           f"a real failure is reported as FAILED even alongside a skip, "
           f"got {report['verdict']}")

    print("check: no runnable gate at all is never a pass")

    report = build(lambda k=None: gates.Plan([], [], []),
                   lambda r, on_result=None: [],
                   COVERED_STEPS)
    expect(report["verdict"] == "PARTIAL" and attest.exit_code(report) == 2,
           f"an empty plan -> PARTIAL/2, got {report['verdict']}")
    expect("not the same as everything passing" in report.get("reason", ""),
           "the empty-plan reason says so in the words this repo uses everywhere")

    print("check: an uncovered entry point degrades the verdict")

    # If run_tests.py ever drops out of the workflow, "this one command suffices" stops
    # being sufficient advice — and nothing else would say so.
    uncovered = lambda: [("x", "python3 plugins/backend-suite/bin/run_tests.py")]  # noqa: E731
    report = build(lambda k=None: gates.Plan([("a", "true")], [], []),
                   lambda r, on_result=None: [FakeResult("a", True)],
                   uncovered)
    expect(report["verdict"] == "PARTIAL",
           f"a must-cover entry point no gate invokes -> PARTIAL, got {report['verdict']}")
    gaps = [row for row in report["coverage"] if not row["invokedByAGate"]]
    expect(any("gate_consumer_compat.py" in row["script"] for row in gaps),
           f"the uncovered script is named, got {[r['script'] for r in gaps]}")

    # Negative control for the same check: with both covered, coverage must not
    # be what makes the run partial.
    report = build(lambda k=None: gates.Plan([("a", "true")], [], []),
                   lambda r, on_result=None: [FakeResult("a", True)],
                   COVERED_STEPS)
    expect(all(row["invokedByAGate"] for row in report["coverage"]),
           "with both entry points wired, coverage reports no gap")
    expect(report["verdict"] == "VERIFIED",
           "coverage does not manufacture a PARTIAL when nothing is missing")

    print("check: the real workflow still covers both entry points")

    # Not a unit test — the live claim CLAUDE.md rule 3 now makes. If this fails,
    # the rule's "one command" promise has become false.
    for path, _why, ok in attest.coverage():
        expect(ok, f"{path} is invoked by a real gate in the workflow")

    print("check: the limits are reported, always")

    expect(len(attest.LIMITS) >= 4, "the limits list is non-empty")
    expect(any("COMMITTED git blobs" in limit for limit in attest.LIMITS),
           "the consumer-compat blind spot is stated as a limit")
    rendered = "\n".join(attest.render(report))
    expect("LIMITS" in rendered and "WORKING TREE" in rendered,
           "a rendered report carries the limits section")
    expect("ENVIRONMENT" in rendered and "python" in rendered,
           "a rendered report states the environment it was reached under")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("attest.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
