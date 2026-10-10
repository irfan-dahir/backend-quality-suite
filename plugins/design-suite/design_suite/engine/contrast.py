"""WCAG colour-contrast scoring. Pure arithmetic, no project literals.

## Why this lives here now, and did not before

`/audit-contrast` shipped for a long time as `maturity: pointer` — a listed
command whose whole content was "this runs in the design-system repository,
beside the palette it scores". The argument was that contrast needs the real
palette, so the audit should live with it.

Half of that is true and half of it was a historical accident, and the split is
exactly the seam this module draws:

  * **The pair list is project data.** Which foreground goes on which background,
    and at which WCAG threshold, is a fact about one product's screens. It cannot
    be universal and this module does not try to make it so — it is read from the
    consumer's own `.design-suite/contrast-pairs.json`.
  * **The scoring is not.** Relative luminance and the contrast ratio are fixed
    by WCAG 2.1 §1.4.3. They are the same arithmetic for a Flutter palette, a
    Tailwind theme and a CSS custom-property file. Nothing here knows which.

Once those are separated there is no reason the scoring has to sit next to any
one palette, and a strong reason it should not: the repo it was pointing at is
private, so for every team this suite is being prepared to ship to, the pointer
resolved to nothing at all.

## The refusal contract

This module raises `ContrastError` rather than returning a degraded answer, at
every point where it could plausibly return one:

  * a colour it cannot parse — NOT treated as black
  * a pair naming a token the palette does not declare — NOT skipped
  * a palette it could not read — NOT an empty palette that scores zero pairs

A contrast run that quietly scored 24 of 26 pairs because two token names were
renamed underneath it reports "all passing", and all-passing is the answer this
repo has twice paid for by mistaking it for a clean result.

Stdlib only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = 1

PAIRS_FILE = ".design-suite/contrast-pairs.json"

# WCAG 2.1 §1.4.3 / §1.4.11. A pair may override its own threshold — large text
# is 3.0, a non-text UI component boundary is 3.0 — but it must say so; the
# default is the one that applies to body text.
AA_NORMAL_TEXT = 4.5
AA_LARGE_TEXT = 3.0
AAA_NORMAL_TEXT = 7.0


class ContrastError(Exception):
    """Contrast could not be scored as asked. Raised, never worked around.

    Same reasoning as `chains.ChainError` and `adapters.base.CapabilityError`: a
    half-resolved palette that scores anyway produces a pass rate whose
    denominator nobody can see.
    """


# Every colour syntax this has to read arrives as *declared value text* from an
# adapter — `token_declarations()` deliberately does not parse it, because what
# counts as equal differs per token kind. So the parsing is here, and it is
# syntax-driven rather than language-driven: `#RRGGBB` is the same six digits
# whether a Dart file or a Tailwind config wrote it.
_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ARGB_LITERAL = re.compile(r"0x([0-9a-fA-F]{8})\b")
_RGB_FUNC = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})"
    r"\s*(?:[,/]\s*([0-9.]+%?)\s*)?\)$")


def parse_color(text: str) -> tuple[int, int, int]:
    """`(r, g, b)` from declared value text, or `ContrastError`.

    Accepts `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA`, a bare `0xAARRGGBB` literal
    anywhere in the text (which is how a Dart `Color(0xFF05678D)` arrives), and
    `rgb()`/`rgba()`.

    **Alpha is read and then refused unless it is opaque.** A translucent token
    has no single contrast ratio — it has one per thing behind it — so scoring it
    against its declared RGB would report a number for a pixel that is never that
    colour on screen. Refusing says so; compositing it against an assumed white
    would not.
    """
    raw = (text or "").strip()
    if not raw:
        raise ContrastError("empty colour value")

    argb = _ARGB_LITERAL.search(raw)
    if argb:
        value = int(argb.group(1), 16)
        alpha = (value >> 24) & 0xFF
        _require_opaque(alpha / 255, raw)
        return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    hexed = _HEX.match(raw)
    if hexed:
        digits = hexed.group(1)
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        red, green, blue = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
        if len(digits) == 8:
            _require_opaque(int(digits[6:8], 16) / 255, raw)
        return (red, green, blue)

    func = _RGB_FUNC.match(raw)
    if func:
        channels = [int(func.group(i)) for i in (1, 2, 3)]
        if any(c > 255 for c in channels):
            raise ContrastError(f"{raw!r} has a channel above 255")
        alpha_text = func.group(4)
        if alpha_text is not None:
            alpha = (float(alpha_text.rstrip("%")) / 100 if alpha_text.endswith("%")
                     else float(alpha_text))
            _require_opaque(alpha, raw)
        return (channels[0], channels[1], channels[2])

    raise ContrastError(
        f"cannot read {raw!r} as a colour. Supported: #RGB, #RGBA, #RRGGBB, "
        f"#RRGGBBAA, 0xAARRGGBB, rgb()/rgba(). This is a refusal rather than a "
        f"default, because a colour guessed wrong scores a ratio that looks "
        f"exactly as authoritative as a correct one.")


def _require_opaque(alpha: float, raw: str) -> None:
    if alpha < 0.999:
        raise ContrastError(
            f"{raw!r} is translucent (alpha {alpha:.3f}). A translucent token has "
            f"no single contrast ratio — it has one per surface behind it. Declare "
            f"the composited opaque token you actually paint, and score that.")


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.1 relative luminance of an sRGB triple."""
    channels = []
    for value in rgb:
        srgb = value / 255
        channels.append(srgb / 12.92 if srgb <= 0.03928
                        else ((srgb + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    """Contrast ratio, 1.0–21.0. Order-independent, as WCAG defines it."""
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def load_pairs(repo: Path) -> list[dict]:
    """The project's declared pair list, or `ContrastError`.

    There is no default pair list and there will not be one. A shipped default
    would score every project against pairs it never declared, and the audit
    would report a pass rate for a set of assertions nobody in that project
    agreed to — which is worse than not running, because it looks like it ran.
    """
    path = repo / PAIRS_FILE
    if not path.is_file():
        raise ContrastError(
            f"no pair list at {PAIRS_FILE}. Contrast is scored against the "
            f"foreground/background combinations this project actually paints, "
            f"and only this project knows them. Declare them there; this audit "
            f"will not invent a list and report a pass rate against it.")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ContrastError(f"{PAIRS_FILE} is not readable JSON: {exc}") from exc

    pairs = data.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ContrastError(f"{PAIRS_FILE} declares no pairs")

    seen = set()
    for index, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            raise ContrastError(f"{PAIRS_FILE} pair {index} is not an object")
        for field in ("name", "foreground", "background"):
            if not pair.get(field):
                raise ContrastError(f"{PAIRS_FILE} pair {index} has no {field!r}")
        if pair["name"] in seen:
            raise ContrastError(
                f"{PAIRS_FILE} has two pairs named {pair['name']!r} — a name is "
                f"how a finding is identified across runs, so a duplicate makes "
                f"one of them untrackable")
        seen.add(pair["name"])
        minimum = pair.get("minRatio", AA_NORMAL_TEXT)
        if not isinstance(minimum, (int, float)) or not 1 <= minimum <= 21:
            raise ContrastError(
                f"{PAIRS_FILE} pair {pair['name']!r} has minRatio {minimum!r}; "
                f"a WCAG ratio is between 1 and 21")
    return pairs


def score(pairs: list[dict], palette: dict) -> list[dict]:
    """Score every pair against `palette` ({token name: declared value text}).

    Returns one record per pair — passing ones included. This audit reports
    *checks*, not violations (`findings.REPORTS_CHECKS`), and dropping the passes
    would make an audit that scored nothing indistinguishable from one where
    everything passed.

    A pair naming a token the palette does not declare raises, and that is the
    load-bearing refusal here: a renamed token silently dropping out of the run
    is precisely how a contrast report keeps saying "all 26 passing" while
    scoring 24.
    """
    results = []
    for pair in pairs:
        resolved = {}
        for role in ("foreground", "background"):
            name = pair[role]
            if name not in palette:
                raise ContrastError(
                    f"pair {pair['name']!r} names {role} token {name!r}, which "
                    f"the palette does not declare. Refusing rather than skipping "
                    f"the pair: a skipped pair leaves the pass rate looking "
                    f"unchanged while the check silently stopped happening.")
            try:
                resolved[role] = parse_color(palette[name])
            except ContrastError as exc:
                raise ContrastError(
                    f"pair {pair['name']!r} {role} token {name!r}: {exc}") from exc

        minimum = float(pair.get("minRatio", AA_NORMAL_TEXT))
        measured = ratio(resolved["foreground"], resolved["background"])
        results.append({
            "name": pair["name"],
            "foreground": pair["foreground"],
            "background": pair["background"],
            # Two decimals, because WCAG is applied at that precision and a
            # 4.4999 rendered as "4.50" beside a FAIL reads as a bug in the tool.
            "ratio": round(measured, 2),
            "min_ratio": minimum,
            "passed": round(measured, 2) >= minimum,
            "surface": pair.get("surface"),
        })
    return results
