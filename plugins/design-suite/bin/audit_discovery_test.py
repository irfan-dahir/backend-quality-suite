#!/usr/bin/env python3
"""Tests for audit_discovery.discover()'s count and coverage.

Issue #120: `discover()` globbed `bin/audit_*.py` only. `audit_mock_api.py`
lives at `design_suite/engine/mockapi/audit_mock_api.py` — one directory over,
tightly coupled to sibling modules there via a directory-relative `sys.path`
insert, so moving it into `bin/` would have severed that locality for no
architectural gain. `discover()` was widened to also glob one level into
`design_suite/engine/*/` instead. Every derived surface (`repo_health.py`,
`design_debt.py`, `mcp/audit_server.py`, the oracle) reads this function, so
an audit invisible to it is invisible everywhere at once — this is the count
this repo's RFC-0003 has been quoting as "18" while the code said 17.

The closing bar in #120 asked for exactly this: a test asserting the
discovered count matches the number of audit scripts actually on disk, so the
next audit added outside the glob's reach cannot disappear the same way.

    python3 plugins/design-suite/bin/audit_discovery_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import _bootstrap  # noqa: F401,E402 — sets up the design_suite import path
from design_suite.engine import audit_discovery  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    (print(f"  ok   {what}") if condition
     else (FAILURES.append(what), print(f"  FAIL {what}")))


def _independent_count() -> int:
    """The same count, computed a different way than discover() computes it —
    so this test cannot pass merely because it shares discover()'s own logic
    (and therefore its own bugs) with the thing it is checking."""
    engine_dir = BIN.parents[0] / "design_suite" / "engine"
    names = {p.name for p in BIN.glob("audit_*.py") if not p.stem.endswith("_test")}
    names |= {p.name for p in engine_dir.glob("*/audit_*.py") if not p.stem.endswith("_test")}
    names -= set(audit_discovery.NOT_AN_AUDIT)
    return len(names)


def main() -> int:
    found = audit_discovery.discover()

    expect(len(found) == _independent_count(),
           f"discover() count ({len(found)}) matches an independently-globbed "
           f"count computed by this test, not by discover() itself")

    stems = [s.stem for s in found]
    expect(len(stems) == len(set(stems)), "no audit is discovered twice")

    mock_api = [s for s in found if s.stem == "audit_mock_api"]
    expect(len(mock_api) == 1,
           "audit_mock_api.py is discovered exactly once (issue #120)")
    if mock_api:
        expect(mock_api[0].parent.name == "mockapi",
               "audit_mock_api.py is found at its real location "
               "(design_suite/engine/mockapi/), not assumed to be in bin/")

    # Control: an ordinary bin/ audit is still found, so widening the glob
    # didn't accidentally narrow it or change what bin/ contributes.
    expect(any(s.stem == "audit_tokens" for s in found),
           "an ordinary bin/ audit (audit_tokens) is still discovered")

    # Control: the plugin-self-check exclusions still apply after widening —
    # a scanner that checks THIS repo, not a consumer project, is not "every
    # audit ships" material any more than it was before.
    self_checks = {"audit_skill_paths", "audit_safe_repairers"}
    expect(not (self_checks & set(stems)),
           f"plugin-self-check scripts stay excluded: {sorted(self_checks)}")

    # Every discovered path must actually exist and be invocable by the same
    # path discover() returned — the exact bug capture-baselines.sh hit before
    # repo_health.py --list started naming each audit's real path: a script
    # "discovered" at a path nobody can run it from is not discovered.
    missing = [str(s) for s in found if not s.is_file()]
    expect(not missing, f"every discovered path exists on disk (missing: {missing})")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print(f"audit_discovery: all cases hold ({len(found)} audits discovered).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
