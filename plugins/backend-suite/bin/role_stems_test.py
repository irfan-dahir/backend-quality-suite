#!/usr/bin/env python3
"""Tests for the derived stem->role map and the drift reporter.

    python3 plugins/backend-suite/bin/role_stems_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.

## The two things being proved

1. **The drift cannot recur.** The hand-maintained table lagged the vocabulary by
   18 roles and kept proposing one the vocabulary had retired. The fix is
   derivation, and the assertion that matters is not "these 8 stems now work" —
   it is `unreachable_roles(stem_map()) == []` against a vocabulary the test does
   not get to choose. A fixture vocabulary is planted with an invented role to
   show that a role added tomorrow is reachable today, with no edit anywhere.

2. **It still refuses.** The whole reason the old table was hand-written was that
   a filename regex guessed badly. A derived map that claimed every stem would be
   worse than the lag it fixed, so every positive case here is paired with a
   control document stem that must still map to nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
sys.path.insert(0, str(BIN.parent))

from backend_suite.engine import archetypes, role_stems  # noqa: E402

FAILURES: list[str] = []

# Of the eight stems measured as unmapped on a real repository (2026-09-15)
# whose filenames are literally role names, the three that are still in the
# vocabulary after this repo re-domained. The other five (adaptive-patterns,
# figma, gallery, patterns, theming) left with the design domain, and a stem
# for a removed role now correctly maps to nothing.
MEASURED_MISSES = ["COMMON-MISTAKES", "DEPRECATIONS", "RELEASE"]

# Stems that are ordinary document names and NOT roles. A map that claimed any of
# these would be guessing, which is the failure the old table's conservatism was
# protecting against and which derivation must not reintroduce.
CONTROL_STEMS = ["notes", "todo", "scratch", "meeting-2026-09-15", "index",
                 "onboarding", "glossary", "faq", "license", "security"]


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def main() -> int:
    mapping = role_stems.stem_map()
    declared = {r for r in archetypes.roles() if not r.startswith("_")}

    print("check: every declared role is reachable from some stem")
    expect(role_stems.unreachable_roles(mapping) == [],
           "unreachable_roles(derived) is empty — by construction, not by luck")
    expect(role_stems.retired_roles(mapping) == [],
           "no derived stem proposes a role the vocabulary has retired")

    print("check: the eight measured misses now resolve")
    for stem in MEASURED_MISSES:
        got = role_stems.role_for_stem(stem)
        expect(got is not None and got[0] == stem.lower(),
               f"{stem}.md proposes the role {stem.lower()!r}")

    print("check: CONTROL — a non-role document stem is still claimed by nothing")
    for stem in CONTROL_STEMS:
        expect(role_stems.role_for_stem(stem) is None,
               f"CONTROL: {stem!r} proposes no role")

    print("check: spelling variants of one role are one role, not three entries")
    for stem in ("common-mistakes", "common_mistakes", "commonmistakes"):
        got = role_stems.role_for_stem(stem)
        expect(got is not None and got[0] == "common-mistakes",
               f"{stem!r} -> 'common-mistakes'")

    print("check: conventions that are not role names still resolve")
    for stem, role in (("readme", "entry-point"), ("claude", "entry-point"),
                       ("agents", "entry-point"), ("adr", "decisions"),
                       ("documentation", "documentation-rules")):
        got = role_stems.role_for_stem(stem)
        expect(got is not None and got[0] == role, f"{stem!r} -> {role!r}")

    print("check: a retired role name resolves to its CURRENT name, not itself")
    got = role_stems.role_for_stem("instructions")
    expect(got is not None and got[0] in declared,
           "the retired stem 'instructions' proposes a role the vocabulary "
           "still declares (the hand table proposed the retired name itself)")

    print("check: a role added to the vocabulary is reachable with no edit here")
    # PLANTED FAILURE, inverted: the point is that it CANNOT fail. A fresh role
    # is injected into the vocabulary and the derived map is asked for it. If
    # derivation ever regresses to a literal table, this is the case that breaks.
    invented = "widget-inventory"
    expect(invented not in declared, "the planted role is genuinely new")
    planted = json.loads(json.dumps(archetypes.vocabulary()))
    planted["roles"][invented] = {"group": "any", "template": None,
                                  "archetypes": {"service": "optional"}}
    # Patched in memory, not on disk: roles.json is shipped vocabulary, and a test
    # that edited the file would be mutating the very thing it is testing against.
    real_vocabulary = archetypes.vocabulary
    try:
        archetypes.vocabulary = lambda: planted  # type: ignore[assignment]
        got = role_stems.role_for_stem(invented)
        expect(got is not None and got[0] == invented,
               f"a role added to roles.json is proposed by {invented}.md "
               f"immediately — no second list to update")
        expect(role_stems.unreachable_roles(role_stems.stem_map()) == [],
               "and the vocabulary is still fully reachable with it present")
    finally:
        archetypes.vocabulary = real_vocabulary  # type: ignore[assignment]
    expect(role_stems.role_for_stem(invented) is None,
           "CONTROL: with the planted role removed, its stem claims nothing "
           "again — the map really is derived, not accumulated")

    # The drift reporter (bin/role_stem_drift.py) retired with the hand
    # table it measured: once survey.py derives from role_stems, the drift
    # it existed to make loud is unrepresentable. Its tests went with it.

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("role stems: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
