#!/usr/bin/env python3
"""Prove the scan engine is not shaped around any one language.

The engine's whole justification is that a second language plugs in without
touching it. That claim is easy to assert and easy to get wrong, so this runs the
*same* engine over a React fixture using the `tsx` adapter and asserts what comes
back — including what must NOT come back, which is where a naive adapter fails.

    python3 design_suite/adapters/verify_seam.py

Exit 0 = the seam holds. This is a check on the *engine interface*, not an
endorsement of the tsx adapter, which is explicitly unfinished (see tsx.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from design_suite.adapters import AdapterContext, load          # noqa: E402
from design_suite.engine.scan import scan_tree                  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

# (kind, substring that must appear in the snippet)
MUST_FIND = [
    # Inline style objects.
    ("color", "#f3f9fc"),
    ("border_radius", "borderRadius: 8"),
    ("duration", "250ms"),
    ("spacing", "padding: 16"),      # unitless React number — used to be missed
    ("spacing", 'marginTop: "12px"'),  # used to be suppressed by a sibling token
    # Tailwind arbitrary values — scale bypasses.
    ("tw_spacing", "h-[17px]"),
    ("tw_spacing", "w-[240px]"),
    ("tw_color", "text-[#111827]"),
    ("tw_border_radius", "rounded-[7px]"),
    ("tw_duration", "duration-[350ms]"),
    ("tw_color", "hover:text-[#FF0000]"),   # a variant must not hide a bypass
    ("tw_spacing", "md:p-[13px]"),
    ("tw_spacing", "!gap-[7px]"),           # nor the important modifier
    ("tw_color", "border-[rgb(17,24,39)]"),  # function value, not a literal
    ("tw_spacing", "max-w-[calc(100%-2rem)]"),
    # CSS-in-JS template literals — kebab-case CSS, not JS object syntax.
    ("css_spacing", "padding: 16px"),
    ("css_spacing", "margin-top: 1.5rem"),
    ("css_spacing", "border-radius: 7px"),
    ("css_duration", "250ms"),
    ("css_spacing", "height: 42px"),        # styled(Foo).attrs(...)`…`
    ("css_spacing", "gap: 13px"),           # bare css`…`
    ("css_spacing", "line-height: 21px"),   # createGlobalStyle`…`
]

# Substrings that must never be flagged.
#
# The Tailwind entries are the load-bearing ones: `h-4`, `p-4`, `gap-2`,
# `text-sm`, `rounded-md` and `duration-200` are references into the configured
# scale — they ARE the design system. An adapter that flags them reports a
# correctly-tokenised codebase as entirely broken, which is a worse failure than
# finding nothing. `margin: 0` is idiomatic rather than a tokenisation failure.
MUST_NOT_FIND = [
    "colorOnSurface", "--brand-primary",
    "h-4", "p-4", "gap-2", "text-sm", "rounded-md", "duration-200",
    "md:px-6", "hover:bg-slate-100", "p-2",
    "margin: 0", "padding: 0",
    # CSS-in-JS correct usage: an interpolated token and a custom property.
    "spacingMd", "var(--gap-sm)",
    # Prose and JSX text outside any template literal. A kebab-case check that
    # fired on a comment would be noise, and noise gets audits switched off.
    "editor config",
]


def main() -> int:
    adapter = load("tsx")
    ctx = AdapterContext(repo=FIXTURES, profile={}, exceptions={}, token_accessor="tokens")
    findings = scan_tree(FIXTURES, FIXTURES, adapter.checks(ctx), globs=adapter.FILE_GLOBS)

    problems = []
    for kind, needle in MUST_FIND:
        if not any(f["kind"] == kind and needle in f["snippet"] for f in findings):
            problems.append(f"expected a {kind!r} finding containing {needle!r}, got none")
    for needle in MUST_NOT_FIND:
        for f in findings:
            if needle in f["snippet"]:
                problems.append(f"{needle!r} is correct usage but was flagged as {f['kind']!r}")

    print(f"engine + {adapter.NAME} adapter over {len(list(FIXTURES.glob('*')))} fixture file(s): "
          f"{len(findings)} finding(s)")
    for f in findings:
        print(f"  {f['file']}:{f['line']:<3} {f['kind']:<14} {f['snippet']}")

    if problems:
        print("\nSEAM BROKEN:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\nSeam holds: the engine ran a non-Dart language with no engine changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
