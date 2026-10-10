#!/usr/bin/env python3
"""Tests for the derived stem->role map and the drift reporter.

    python3 plugins/design-suite/bin/role_stems_test.py

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

from design_suite.engine import archetypes, role_stems  # noqa: E402

DRIFT = BIN / "role_stem_drift.py"
FAILURES: list[str] = []

# The eight stems measured as unmapped on a real design-system repository
# (2026-09-15) whose filenames are literally role names. These are the
# regression: each one was surveyed as "no role" while being named after one.
MEASURED_MISSES = ["ADAPTIVE-PATTERNS", "COMMON-MISTAKES", "DEPRECATIONS",
                   "FIGMA", "GALLERY", "PATTERNS", "RELEASE", "THEMING"]

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
    for stem in ("brand-voice", "brand_voice", "brandvoice"):
        got = role_stems.role_for_stem(stem)
        expect(got is not None and got[0] == "brand-voice",
               f"{stem!r} -> 'brand-voice'")

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
                                  "archetypes": {"app": "optional"}}
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

    print("check: the drift reporter refuses rather than passing when it cannot look")
    with tempfile.TemporaryDirectory() as tmp:
        blank = Path(tmp) / "no_table.py"
        blank.write_text("X = 1\n")
        result = subprocess.run([sys.executable, str(DRIFT), str(blank)],
                                capture_output=True, text=True)
        expect(result.returncode == 2,
               "a source file with no ROLE_BY_STEM exits 2 (could not look), "
               "never 0 — an absent table is not a clean table")

        # PLANTED FAILURE. A table missing one role, and a table naming one the
        # vocabulary does not declare. Both must be caught; a reporter that only
        # caught the first would have missed the live 'instructions' defect.
        planted_src = Path(tmp) / "planted.py"
        planted_src.write_text(
            "ROLE_BY_STEM = {\n"
            "    'design': ('design', 0.7, 'x'),\n"
            "    'obsolete': ('no-such-role', 0.7, 'x'),\n"
            "}\n")
        result = subprocess.run([sys.executable, str(DRIFT), str(planted_src)],
                                capture_output=True, text=True)
        expect(result.returncode == 1, "a drifted table exits 1")
        expect("flows" in result.stderr,
               "PLANTED: a role present in roles.json but absent from the stem "
               "map is named")
        expect("no-such-role" in result.stderr,
               "PLANTED: a stem naming a role the vocabulary does not declare "
               "is named")
        # Matched against the itemised lines, not against the whole stream: the
        # fix hint at the bottom names `design_suite.engine.role_stems`, and a
        # substring check over stderr would "pass" on that instead of on the
        # finding list. A control that can pass for the wrong reason is not one.
        listed = {line.strip() for line in result.stderr.splitlines()
                  if line.startswith(" " * 6)}
        expect("design" not in listed,
               "CONTROL: the one role the planted table DOES cover is not "
               "reported as missing")
        expect("flows" in listed,
               "CONTROL: and the itemised list is genuinely where findings "
               "appear, so the check above could have failed")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("role stems: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
