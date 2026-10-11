#!/usr/bin/env python3
"""Tests for the shared `--update-baseline` guard.

The guard's whole job is to tell two situations apart that the ratchet audits
previously treated identically: a run where the baseline shrank (a genuine
improvement, safe to record) and a run where it shrank AND grew (an improvement
plus a regression, where recording `current` accepts the regression unseen).
So every case here is paired with its negative control — a guard that refused
unconditionally would pass a one-sided test just as happily as a correct one.

This is a unit test on purpose: `audit_copy` is DISABLED and exits 2 long before
its baseline code runs, so the only way to exercise the guard it now calls is
against the shared module.

    python3 plugins/backend-suite/bin/ratchet_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend_suite.engine import ratchet  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def main() -> int:
    print("check: the guard distinguishes improvement from regression")

    # The exact planted shape: one baselined finding fixed, one new one present.
    # The old code printed "nice, lock the improvement in" and then wrote both.
    msg = ratchet.refusal("audit_x", {"old", "new"}, {"old", "gone"})
    expect(msg is not None, "a run with a new finding refuses the write")
    expect("new" in (msg or ""), "the refusal names the finding it would have absorbed")
    expect("gone" not in (msg or ""),
           "the refusal does not mislead by listing the FIXED finding as new")
    expect(ratchet.ACCEPT_FLAG in (msg or ""),
           "the refusal names the flag that overrides it — a dead end is not a fix")

    # Control: fixed-only. This must still be allowed, or the guard would have
    # broken the ratchet it exists to protect — no improvement could ever be
    # recorded again.
    expect(ratchet.refusal("audit_x", {"old"}, {"old", "gone"}) is None,
           "a run with only FIXED findings is not refused")
    expect(ratchet.refusal("audit_x", set(), {"old"}) is None,
           "a run that fixed everything is not refused")
    expect(ratchet.refusal("audit_x", {"old"}, {"old"}) is None,
           "an unchanged run is not refused")
    expect(ratchet.refusal("audit_x", set(), set()) is None,
           "first adoption of an empty baseline is not refused")

    expect(ratchet.new_findings({"b", "a"}, {"a"}) == ["b"],
           "new_findings reports only what the baseline does not already hold")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("ratchet: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
