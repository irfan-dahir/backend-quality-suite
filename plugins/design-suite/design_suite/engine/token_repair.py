"""Band-1 token repair: turn a raw literal into the one token that equals it.

RFC-0003 §3b/§3c. Three bands, and the whole value of this module is in what it
*refuses* to do:

    band 1  the literal exactly equals exactly one declared token of the right
            category                                    -> generate the rewrite
    band 2  a near match, or several equally good tokens -> propose, never apply
    band 3  no declared token has this value             -> never auto-fix.
            Creating a token is a convention decision, reserved for humans.

There is a fourth outcome that is not a band at all, and keeping it separate is
the point of this module rather than an implementation detail:

    undeterminable  this project has never said which token names mean
                    "spacing" or "radius", or the token source does not resolve

Reporting that as band 3 would be a lie with consequences. Band 3 means "no such
token exists, go decide whether to author one" — telling a project to grow its
design system because *we* could not read it is worse than saying nothing. It is
the same None-vs-empty-set contract the token audits already hold to, one layer
up. See RFC-0003 §2c: `dart.checks()` falls back to `ctx.token_accessor or
"AppTokens"`, so a token audit with no declared token source appears to work
while having no idea whether a token exists. Band 1 is therefore only available
when a token source is genuinely declared *and* resolves; the caller's job is to
refuse, not guess, when it does not.

Nothing here writes to a working tree. `rewrite()` returns new text; emitting it
as a unified diff, and stopping there, is the caller's contract.
"""
from __future__ import annotations

import difflib
import re

BAND_DETERMINISTIC = 1
BAND_AMBIGUOUS = 2
BAND_ABSENT = 3

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_HEX = re.compile(r"0x([0-9A-Fa-f]{6,8})")


def _as_number(text: str):
    text = text.strip()
    return float(text) if _NUMBER.match(text) else None


def _normalise(text: str) -> str:
    """Declared value and source literal in one comparable spelling.

    Whitespace and a leading `const` are noise; a 6-digit colour hex is the same
    colour as the 8-digit one with an opaque alpha, and Dart code writes both.
    """
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"^const\s+", "", text)

    def widen(m):
        digits = m.group(1).upper()
        return "0x" + (digits if len(digits) == 8 else "FF" + digits)

    return _HEX.sub(widen, text)


def equal(literal: str, declared: str) -> bool:
    """Whether a source literal is *exactly* the declared token value.

    Numeric when both sides are numbers (`5` and `5.0` are the same spacing),
    normalised text otherwise. Deliberately no tolerance: a value one pixel off a
    token is band 2's problem, and a repairer that rounds is a repairer that
    silently changes what the screen looks like.
    """
    a, b = _as_number(literal), _as_number(declared)
    if a is not None and b is not None:
        return a == b
    if a is not None or b is not None:
        return False
    return _normalise(literal) == _normalise(declared)


class Site:
    """One repairable literal: where it is, what it says, and what it could be.

    A finding can carry several — `EdgeInsets.symmetric(horizontal: 8, vertical:
    3)` is one finding and two independent sites, and they can land in different
    bands. The finding takes the worst of them (see `band_of`), because a partial
    rewrite of a single expression is a diff a reviewer cannot trust.
    """

    def __init__(self, start, end, literal, category, candidates, accessor):
        self.start = start
        self.end = end
        self.literal = literal
        self.category = category
        self.candidates = sorted(candidates)
        self.accessor = accessor

    @property
    def band(self) -> int:
        if len(self.candidates) == 1:
            return BAND_DETERMINISTIC
        return BAND_AMBIGUOUS if self.candidates else BAND_ABSENT

    @property
    def replacement(self) -> str | None:
        if self.band != BAND_DETERMINISTIC:
            return None
        return f"{self.accessor}.{self.candidates[0]}"


def band_of(sites) -> int:
    """The band a whole finding sits in: the worst of its sites."""
    return max(site.band for site in sites)


UNSUPPORTED = "unsupported"
UNDETERMINABLE = "undeterminable"


def sites_for(check_kind: str, match, adapter, tokens: dict, accessor: str):
    """Repair sites for one audit match, or a refusal string instead of a list.

    Returns `UNSUPPORTED` when the adapter has no way to name the literal behind
    this kind of finding (`entrance_curve` flags a token used in the wrong place
    — there is no literal to replace), and `UNDETERMINABLE` when the literal's
    category is one this project never told us the naming prefix for.

    Neither is a band. Folding them into band 3 would report "no matching token
    exists" — the one answer that sends a human off to author a new token —
    about a lookup that never happened.

    `tokens` is `{category: {name: declared value}}`, already restricted to the
    categories the project declared a prefix for. Locating the literals is the
    adapter's job (`repair_literals`); deciding what they could become is this
    module's.
    """
    located = adapter.repair_literals(check_kind, match, accessor)
    if located is None:
        return UNSUPPORTED

    sites = []
    for start, end, text, category in located:
        if category not in tokens:
            return UNDETERMINABLE
        candidates = [name for name, value in tokens[category].items()
                      if equal(text, value)]
        sites.append(Site(start, end, text, category, candidates, accessor))
    return sites


def revalidates(check, match, source: str, sites) -> bool:
    """Whether applying `sites` to `source` would actually clear the finding
    that `check` raised at `match` — the Getafix pattern (RFC-0003 phase 2,
    V1). Never offer a candidate without checking it did what it claims.

    A previous repair — issue #109, the corrupting `title_case` fix, not in
    this module — shipped an unvalidated diff that looked exactly like a
    working rewrite right up until someone applied it. An unapplied diff and
    a working one are indistinguishable to a reviewer unless something
    actually re-runs the check; this is that something. The governing
    principle is the same one this whole suite is built on: a fix that
    doesn't fix anything must never look identical to one that does.

    Patches only this finding's sites into a throwaway copy of `source`, then
    re-runs the *same* check over the patched text. If a match still starts at
    the same offset and still fires, the candidate did not clear its own
    finding and must not be offered as band 1.
    """
    patched = rewrite(source, sites)
    for candidate in check.pattern.finditer(patched):
        if candidate.start() != match.start():
            continue
        if check.fires(candidate, patched):
            return False
    return True


def rewrite(source: str, sites) -> str:
    """`source` with every band-1 site replaced. Returns text; writes nothing.

    Applied right-to-left so an earlier replacement cannot shift a later site's
    offsets — the classic way a mechanical rewriter corrupts a file it was only
    supposed to improve.
    """
    out = source
    for site in sorted(sites, key=lambda s: s.start, reverse=True):
        if site.replacement is None:
            continue
        out = out[:site.start] + site.replacement + out[site.end:]
    return out


def unified(rel_path: str, before: str, after: str) -> list[str]:
    """A unified diff for one file, in `git apply`-compatible a/ b/ form."""
    if before == after:
        return []
    return list(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}"))
