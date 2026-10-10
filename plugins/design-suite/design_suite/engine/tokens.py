"""Shared "declared vs read" comparison for unused-token/role audits.

`audit_unwired_roles.py` and `audit_unused_tokens.py` ask the same question of
two different graphs — semantic colour roles in one case, raw design tokens
(spacing, radii, durations, curves, colour, ...) in the other: of everything
declared, what does nothing read? Before this module existed each script did its
own regex-and-set-difference dance; a second copy of that dance is the exact
thing this project's own governing principle warns about, so the comparison
moved here once a second consumer arrived.

Nothing here knows what a "role" or a "token" is, or what language declared it —
that stays in the adapter. This module only knows how to compare a set of names
against a source string once a reader pattern is given.
"""
from __future__ import annotations

import re


def unwired(names: set, accessor_pattern: str, src: str) -> list:
    """Names in `names` that `accessor_pattern` never reads in `src`.

    A name counts as read when `{accessor_pattern}.{name}` appears as a whole
    word in the swept source — being emitted, declared, or exported elsewhere
    does not count. `accessor_pattern` is a regex fragment (already escaped by
    the caller where it should be literal), not a plain string, so a caller with
    several accepted local names can pass `(?:colors|c)` in one call.
    """
    return sorted(
        name for name in names
        if not re.search(rf"{accessor_pattern}\.{re.escape(name)}\b", src)
    )


def split_required(unwired_names, required: set) -> tuple[list, list]:
    """(failing, unused) — `unwired_names` split by whether this project holds
    itself accountable for them.

    `failing` is unwired AND required: this project claimed the name and reads
    it nowhere, which is a real finding. `unused` is unwired but not required:
    offered by the design system (or declared upstream) and never claimed here —
    reported every run, never failed, so the list stays visible without being
    able to break a build on its own.
    """
    failing = sorted(n for n in unwired_names if n in required)
    unused = sorted(n for n in unwired_names if n not in required)
    return failing, unused
