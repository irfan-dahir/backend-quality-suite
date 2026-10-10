"""Helpers shared by the native-mobile language adapters (`swift`, `kotlin`).

Not an adapter: it declares no NAME / FILE_GLOBS / checks(), so the loader's
`available()` does not list it and `adapters.lang: "_native"` is refused.

Everything here is language-neutral plumbing the two adapters would otherwise
duplicate: "is this match in a comment", "is this match the definition of a
token rather than a use of a literal", and the config-driven reduced-motion
check, which has the same shape as `dart.reduced_motion_checks` with a
different signal regex.
"""
from __future__ import annotations

import re

from .base import AdapterContext, Check, CheckSet

IMPORT_LINE_RE = re.compile(r"\s*(?:@\w+\s+)*import\b")
ZERO_RE = re.compile(r"^-?0*(?:\.0*)?[fFdD]?$")


def line_prefix(source: str, offset: int) -> str:
    return source[source.rfind("\n", 0, offset) + 1:offset]


def in_comment(source: str, offset: int) -> bool:
    """True for `// ...`, a `*`/`/*` doc-comment line, or an open block comment.

    Cheap and only ever reduces findings: a value written in a comment is
    documentation, not styling. A `//` inside a string literal on the same line
    (a URL) is the known over-suppression; it can only hide a literal sharing a
    line with a URL string, which is rare in view code.
    """
    prefix = line_prefix(source, offset)
    if "//" in prefix or re.match(r"\s*(?:\*|/\*)", prefix):
        return True
    opened = source.rfind("/*", 0, offset)
    return opened != -1 and source.rfind("*/", opened, offset) == -1


def is_zero(number: str) -> bool:
    return bool(ZERO_RE.match(number.strip()))


def reduced_motion_checks(ctx: AdapterContext, signal_re: re.Pattern,
                          binding_re: re.Pattern, window: int = 400) -> CheckSet:
    """Animated nodes with no reduced-motion signal nearby.

    Mirrors `dart.reduced_motion_checks`: which call names count as "animated"
    comes from `token_categories.motion.animated_widgets` in the audit config,
    never from a list here. A missing, empty or TODO-placeholder list is a
    refusal (`omitted`), not zero findings.

    `signal_re` is the platform's reduce-motion API. `binding_re` captures the
    name a file binds that signal to (`@Environment(\\.accessibilityReduceMotion)
    var reduceMotion`, `val animationsOff = ...ANIMATOR_DURATION_SCALE...`), so a
    view that reads the flag once at the top and branches on `reduceMotion` far
    below still counts as wired — a SwiftUI property wrapper is routinely more
    than `window` characters from the modifier it gates.
    """
    motion_cfg = (ctx.audit_config.get("token_categories", {}) or {}).get("motion", {}) or {}
    widgets = motion_cfg.get("animated_widgets")
    if not widgets:
        return CheckSet([], omitted=[
            "reduced_motion_unwired: token_categories.motion.animated_widgets "
            "is not set in the audit config"])
    names = [w.strip() for w in widgets if isinstance(w, str) and w.strip()]
    placeholders = [n for n in names if n.upper().startswith("TODO")]
    names = [n for n in names if n not in placeholders]
    if not names:
        return CheckSet([], omitted=[
            "reduced_motion_unwired: token_categories.motion.animated_widgets "
            + ("still holds the scaffolded TODO placeholder"
               if placeholders else "is set but empty")
            + " in the audit config"])

    # `.animation(` / `withAnimation` style names are matched as written; a
    # leading `.` in config is honoured literally so `.animation` does not also
    # match `withAnimation`.
    animated_re = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in names) + r")\b")
    bindings: dict[int, re.Pattern | None] = {}

    def unwired(m, source):
        if in_comment(source, m.start()):
            return False
        # `import androidx.compose.animation.AnimatedVisibility` names the API;
        # it animates nothing. Measured: every Compose file using one was
        # reported twice, once at its import line.
        if IMPORT_LINE_RE.match(line_prefix(source, m.start())):
            return False
        lo, hi = max(0, m.start() - window), m.end() + window
        if signal_re.search(source, lo, hi):
            return False
        if id(source) not in bindings:
            found = sorted(set(binding_re.findall(source)))
            bindings[id(source)] = (re.compile(r"\b(?:" + "|".join(map(re.escape, found)) + r")\b")
                                    if found else None)
        rx = bindings[id(source)]
        return not (rx and rx.search(source, lo, hi))

    def describe(m, _source):
        return f"{m.group(0)} — no reduced-motion check within range"

    return CheckSet([Check("reduced_motion_unwired", animated_re, accept=unwired,
                           tags=("motion",), snippet=describe)])
