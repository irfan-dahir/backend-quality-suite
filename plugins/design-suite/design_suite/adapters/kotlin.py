"""Kotlin / Jetpack Compose (and Android View) adapter — hardcoded colours, dp/sp, radii, durations.

**Maturity: unverified.** Proven against synthetic planted-violation fixtures
(`bin/native_adapters_test.py`) and sanity-run on public OSS Compose sample apps,
never against a consumer project. Its findings are leads, not a measured
false-positive rate.

## What is checked

  color          `Color(0xFF6200EE)`, `Color(red = 0.2f, …)` / `Color(255, 0, 0)`,
                 `Color.parseColor("#…")` / `android.graphics.Color.rgb(…)`, and a
                 hex string literal `"#RRGGBB"` anywhere in code.
  spacing        a non-zero `N.dp` in a spacing context only — the argument of
                 `padding(…)` / `absolutePadding(…)` / `PaddingValues(…)`,
                 `Arrangement.spacedBy(…)`, `offset(…)` / `absoluteOffset(…)`,
                 a named argument whose name says spacing (`contentPadding =`,
                 `itemSpacing =`, `horizontalPadding =`), or the width/height
                 of a `Spacer(…)`. Sizes — `Modifier.size(200.dp)`,
                 `width(…)`, `height(…)`, `elevation`, `BorderStroke(1.dp, …)`
                 — are deliberately skipped: they are component dimensions, not
                 the spacing scale, and reporting them as spacing made the
                 category mostly noise on real Compose code. A size scale is a
                 separate token family this adapter does not claim to audit.
  font_size      non-zero `N.sp` — `fontSize = 14.sp`, `lineHeight = 20.sp`.
  border_radius  `RoundedCornerShape(12.dp)` / `RoundedCornerShape(12)` (percent),
                 `CornerSize(8.dp)`, `.clip(RoundedCornerShape(…))` via the same.
  duration       `tween(300)` / `tween(durationMillis = 300)`, `durationMillis = 300`,
                 `delayMillis = 100`, `keyframes { durationMillis = … }`,
                 `.setDuration(300)` / `animate().duration = 300` on Views.

`0.dp`, `0.sp`, `tween(0)` are never findings. `MaterialTheme.spacing.md`,
`Dimens.md` etc. never match — the patterns need a numeric literal.

**Token definitions are not violations.** The stock Compose template's
`ui/theme/Color.kt` is a file of `val Purple80 = Color(0xFFD0BCFF)` lines, and
`Type.kt` is one top-level `val Typography = Typography(...)` full of `.sp`. A
literal whose enclosing *top-level* declaration is a `val`, an `object`, or a
class constructor (data-class defaults) is a token definition and is skipped.
The same literal inside a top-level `fun` (every `@Composable`) is a use and is
reported. Known miss: a top-level `val` holding a composable lambda.

## Capabilities

  checks()                 yes
  reduced_motion_checks()  yes — config-driven like dart; the signal is
                           `ANIMATOR_DURATION_SCALE` / `TRANSITION_ANIMATION_SCALE`
                           / `areAnimatorsEnabled()` / `LocalReduceMotion` /
                           `reduceMotion`, or a name the file binds one to.
                           Android has no single reduced-motion API, so a project
                           that wraps it in its own helper must name the helper's
                           binding the same way or expect findings.
  IMPORT_RE                yes — `import a.b.c.D` / `import a.b.*` / `as` alias.
                           Targets are PACKAGE names, not paths, so
                           `audit_adapter_pattern` works (write the banned pattern
                           as `data\\.repositories`) and `audit_layer_boundaries`
                           refuses — see IMPORT_TARGETS.
  token_names              not implemented: audit_tokens reads "cannot tell".
  WIDGET_SHAPE_GLOB        not set — the constructor-shape parser is Dart-shaped.
  focus order, semantics,  not implemented — those audits refuse (exit 2).
  copy, token repair,
  contracts, colour roles
"""
from __future__ import annotations

import re

from . import _native
from .base import AdapterContext, Check, CheckSet

NAME = "kotlin"
# `.kts` is build script, not UI; deliberately not globbed.
FILE_GLOBS = ("**/*.kt",)
GENERATED_SUFFIXES = ("_Factory.kt", "_Impl.kt", "Binding.kt")

IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_]\w*(?:\.\w+)*(?:\.\*)?)", re.M)
IMPORT_TARGETS = "module"

_NUM = r"\d+(?:\.\d+)?[fF]?"

COLOR_RE = re.compile(
    r"(?<![\w.])Color\(\s*0x[0-9A-Fa-f]{6,8}[uUlL]*\s*\)"
    r"|(?<![\w.])Color\(\s*(?:red\s*=\s*)?" + _NUM + r"\s*,\s*(?:green\s*=\s*)?" + _NUM
    + r"\s*,\s*(?:blue\s*=\s*)?" + _NUM + r"[^)]*\)"
    r"|\bColor\.(?:parseColor\([^)]*\)|rgb\([^)]*\)|argb\([^)]*\))"
    r"|\"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\"")
RADIUS_RE = re.compile(
    r"\b(?:RoundedCornerShape|CutCornerShape|CornerSize)\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
SPACING_RE = re.compile(r"(?<![\w.])(" + _NUM + r")\.dp\b")
FONT_SIZE_RE = re.compile(r"(?<![\w.])(" + _NUM + r")\.sp\b")
DURATION_RE = re.compile(
    r"\btween\(\s*(?:durationMillis\s*=\s*)?(\d+)"
    r"|\b(?:durationMillis|delayMillis)\s*=\s*(\d+)"
    r"|\.setDuration\(\s*(\d+)"
    r"|\.duration\s*=\s*(\d+)")

# The top-level declaration that encloses a match decides whether it is a token
# definition. Kotlin theme files declare tokens as top-level vals
# (`val Purple80 = Color(0xFFD0BCFF)`, `val Typography = Typography(displayLarge =
# TextStyle(fontSize = 57.sp, ...))`), objects (`object Spacing { val md = 16.dp }`)
# or data-class defaults (`data class Gaps(val tiny: Dp = 4.dp)`). A match inside
# a top-level `fun` (every @Composable) is a use, and is reported.
_TOKEN_HOLDER_RE = re.compile(
    r"(?:(?:private|internal|public|const|data|companion|expect|actual)\s+)*"
    r"(?:val\b|object\b|class\s+\w+\s*(?:<[^>]*>)?\s*\()")
_SKIP_LINE_RE = re.compile(r"\s*$|@|//|/\*|\*")


def _is_definition(source: str, offset: int) -> bool:
    end = source.find("\n", offset)
    end = len(source) if end == -1 else end
    while end > 0:
        start = source.rfind("\n", 0, end) + 1
        line = source[start:end]
        if line and not line[0].isspace() and not _SKIP_LINE_RE.match(line):
            return bool(_TOKEN_HOLDER_RE.match(line))
        end = start - 1
    return False


def _real(m, source) -> bool:
    return not _native.in_comment(source, m.start()) and not _is_definition(source, m.start())


def _numeric(m, source) -> bool:
    if not _real(m, source):
        return False
    groups = [g for g in m.groups() if g is not None]
    return any(not _native.is_zero(g) for g in groups) if groups else True


def _radius(m, source) -> bool:
    if not _real(m, source):
        return False
    return any(not _native.is_zero(n) for n in re.findall(r"(?<![\w.])(" + _NUM + r")", m.group(1)))


_SPACING_CALLS = frozenset({"padding", "absolutePadding", "PaddingValues", "spacedBy",
                            "offset", "absoluteOffset", "Spacer"})
_SPACER_DIMS = frozenset({"width", "height", "size", "requiredWidth", "requiredHeight"})
_SPACING_KWARG_RE = re.compile(r"(?i)\b\w*(?:padding|spacing|spacer|gap|offset|inset)\w*\s*=\s*$")


def _enclosing_calls(source: str, offset: int, limit: int = 400):
    """Names of the unclosed calls around `offset`, innermost first."""
    names, depth, i = [], 0, offset - 1
    floor = max(0, offset - limit)
    while i >= floor:
        c = source[i]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                j = i
                while j > 0 and (source[j - 1].isalnum() or source[j - 1] == "_"):
                    j -= 1
                names.append(source[j:i])
            else:
                depth -= 1
        elif c in "{};" and depth == 0:
            break
        i -= 1
    return names


def _is_spacing_context(source: str, offset: int) -> bool:
    line_start = source.rfind("\n", 0, offset) + 1
    if _SPACING_KWARG_RE.search(source[line_start:offset]):
        return True
    calls = _enclosing_calls(source, offset)
    if not calls:
        return False
    if calls[0] in _SPACING_CALLS:
        return True
    # Spacer(Modifier.width(4.dp)) — a spacer's dimension *is* a gap.
    return calls[0] in _SPACER_DIMS and "Spacer" in calls[1:]


def _spacing(m, source) -> bool:
    """A `.dp` inside a shape constructor belongs to border_radius, not here;
    a `.dp` outside a spacing context is a size, not spacing."""
    if not _numeric(m, source):
        return False
    if not _is_spacing_context(source, m.start()):
        return False
    open_shape = None
    for s in re.finditer(r"\b(?:RoundedCornerShape|CutCornerShape|CornerSize)\(",
                         source[max(0, m.start() - 120):m.start()]):
        open_shape = s
    if open_shape is None:
        return True
    tail = source[max(0, m.start() - 120) + open_shape.end():m.start()]
    return tail.count(")") > tail.count("(")


def checks(ctx: AdapterContext) -> CheckSet:
    return CheckSet([
        Check("color", COLOR_RE, accept=_real, category="color"),
        Check("spacing", SPACING_RE, accept=_spacing),
        Check("font_size", FONT_SIZE_RE, accept=_numeric),
        Check("border_radius", RADIUS_RE, accept=_radius),
        Check("duration", DURATION_RE, accept=_numeric, tags=("motion",)),
    ])


REDUCED_MOTION_SIGNAL_RE = re.compile(
    r"\bANIMATOR_DURATION_SCALE\b|\bTRANSITION_ANIMATION_SCALE\b|\bareAnimatorsEnabled\b"
    r"|\bLocalReduceMotion\b|\breduceMotion\b|\bisReduceMotionEnabled\b")
REDUCED_MOTION_BINDING_RE = re.compile(
    r"\b(?:val|var)\s+(\w+)\s*(?::\s*[\w.<>?]+\s*)?=[^\n]*?"
    r"(?:ANIMATOR_DURATION_SCALE|TRANSITION_ANIMATION_SCALE|areAnimatorsEnabled|LocalReduceMotion)")


def reduced_motion_checks(ctx: AdapterContext) -> CheckSet:
    return _native.reduced_motion_checks(ctx, REDUCED_MOTION_SIGNAL_RE, REDUCED_MOTION_BINDING_RE)
