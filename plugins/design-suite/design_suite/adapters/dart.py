"""Dart / Flutter language adapter.

Every regex here was lifted verbatim from `token_pipeline/scripts/audit_tokens.py`,
where it sat as a module-level constant. Behaviour is intentionally unchanged —
the audit reports the same 143 findings before and after the move, which is the
only acceptance test that matters for this refactor.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import (numeric_minimum, AdapterContext, ApiConsistencySyntax, Capability, CapabilityError,
                   CapabilityEvidence, Check, CheckSet, ErrorHandlingSyntax)

NAME = "dart"
FILE_GLOBS = ("**/*.dart",)
# Files engine/component_shape.py's constructor-shape parser can read. Declared
# here rather than hardcoded in the two duplicate-widget audits, which used to
# sweep a literal `lib/**/*.dart` and so scanned nothing on any other tree.
WIDGET_SHAPE_GLOB = "**/*.dart"

# Generated output is not hand-written code, so a literal in it is not a
# violation anyone can fix at the call site. Which suffixes mean "generated" is a
# per-language fact, which is why it lives here and not in the scan engine.
GENERATED_SUFFIXES = (".g.dart", ".freezed.dart")

# How this language spells "this file depends on that one", for the structural
# audits (audit_adapter_pattern, audit_layer_boundaries). Group 1 is the target.
IMPORT_RE = re.compile(r"^\s*(?:import|export)\s+['\"]([^'\"]+)['\"]", re.M)
# audit_adapter_pattern's historical default scope for a Flutter feature-first
# layout, kept so existing Dart consumers see no change. Any other stack has no
# default and must declare adapterPattern.screensGlob, or the audit refuses.
ADAPTER_PATTERN_SCREENS_GLOB = "*/presentation/pages/**/*.dart"
# Route-entry wrappers may read state via context; skipped by default.
ADAPTER_PATTERN_EXEMPT_SUFFIXES = ("_page_wrapper.dart",)

COLOR_RE = re.compile(r"\bColor\(0x[0-9A-Fa-f]{6,8}\)")
EDGE_INSETS_RE = re.compile(r"\bEdgeInsets\.(all|symmetric|only|fromLTRB)\(([^)]*)\)")
BORDER_RADIUS_RE = re.compile(r"\bBorderRadius\.circular\(([^)]*)\)")
DURATION_RE = re.compile(r"\bDuration\(milliseconds:\s*-?\d+(\.\d+)?\)")
CURVES_RE = re.compile(r"\bCurves\.\w+")
RAW_NUMBER_RE = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")
NAMED_ARG_NUMBER_RE = re.compile(r":\s*(-?\d+(\.\d+)?)\b")
ZERO_LITERAL_RE = re.compile(r"^-?0+(\.0+)?$")

# Tail of "Future.delayed(" / "Future<void>.delayed(" immediately before a
# Duration literal: a mock-API or processing-simulation delay, not motion, so not
# a motion-token violation. See the motion document's "Not motion" list.
MOCK_DELAY_RE = re.compile(r"\.delayed\(\s*(const\s+)?$", re.DOTALL)

# A slide/translate near a curveStandard signals an entrance animation, which
# wants an ease-out curve rather than the on-screen-morph default.
ENTRANCE_SIGNAL_RE = re.compile(r"\bTween<Offset>|\bSlideTransition\b|Transform\.translate\(")
ENTRANCE_WINDOW = 200
MOCK_DELAY_LOOKBACK = 60


def _is_zero(number: str) -> bool:
    """A zero inset is not a token violation. There is no zero token to reach
    for — `AppTokens.space0` does not and should not exist — and `0` is already
    the clearest way to say "no inset on this edge"."""
    return bool(ZERO_LITERAL_RE.match(number.strip()))


def _raw_numbers(part: str) -> list[str]:
    """Bare numeric literals in a single argument, ignoring token references."""
    m = RAW_NUMBER_RE.match(part)
    if m:
        return [m.group(0).strip()]
    return [nm.group(1) for nm in NAMED_ARG_NUMBER_RE.finditer(part)]


def _has_raw_number(args: str, accessor: str) -> bool:
    """True if any argument is a bare non-zero number rather than a token
    reference.

    Argument-by-argument rather than whole-expression, so a raw number is still
    caught alongside a token — EdgeInsets.only(left: AppTokens.space16, top: 4).
    Two things are deliberately NOT violations: a zero (see _is_zero), and an
    argument carrying no numeric literal at all, such as
    EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom), where the
    value is computed at runtime and there is nothing to tokenise.
    """
    for part in args.split(","):
        part = part.strip()
        if not part or (accessor and accessor in part):
            continue
        if any(not _is_zero(n) for n in _raw_numbers(part)):
            return True
    return False


def checks(ctx: AdapterContext) -> CheckSet:
    accessor = ctx.token_accessor or "AppTokens"
    curve_standard_re = re.compile(rf"\b{re.escape(accessor)}\.curveStandard\b")

    def edge_insets_accept(m, _source):
        return _has_raw_number(m.group(2), accessor)

    def border_radius_accept(m, _source):
        arg = m.group(1)
        return accessor not in arg and bool(RAW_NUMBER_RE.match(arg))

    def duration_accept(m, source):
        window = source[max(0, m.start() - MOCK_DELAY_LOOKBACK):m.start()]
        return not MOCK_DELAY_RE.search(window)

    def entrance_accept(m, source):
        window = source[max(0, m.start() - ENTRANCE_WINDOW):m.end() + ENTRANCE_WINDOW]
        return bool(ENTRANCE_SIGNAL_RE.search(window))

    return CheckSet([
        Check("color", COLOR_RE, category="color"),
        Check("edge_insets", EDGE_INSETS_RE, accept=edge_insets_accept),
        Check("border_radius", BORDER_RADIUS_RE, accept=border_radius_accept),
        Check("duration", DURATION_RE, accept=duration_accept, tags=("motion",)),
        Check("curve", CURVES_RE, tags=("motion",)),
        Check("entrance_curve", curve_standard_re, accept=entrance_accept, tags=("motion",)),
    ])


# Flutter's reduced-motion signal, in the three shapes real code reaches for it:
# `MediaQuery.of(context).disableAnimations`, the newer
# `MediaQuery.disableAnimationsOf(context)` (avoids a full MediaQuery rebuild),
# and the platform-level `AccessibilityFeatures.disableAnimations` reached via
# `WidgetsBinding.instance.platformDispatcher.accessibilityFeatures`. All three
# are Flutter API facts, not project facts, so they are a regex here rather than
# config — config only says which widgets count as "animated" in the first place
# (see `reduced_motion_checks`).
REDUCED_MOTION_SIGNAL_RE = re.compile(
    r"\bdisableAnimations\b|\bMediaQuery\.disableAnimationsOf\("
)

# How the Flutter SDK names its animated widgets and drivers: `Animated*`
# (AnimatedOpacity, AnimatedContainer, ...), `*Transition` (FadeTransition,
# SlideTransition, ...), the `AnimationController` that drives explicit
# animations, and the builder forms. A Flutter API naming fact, not a project
# fact. It is NOT the audit's animated list — that stays config, per
# `reduced_motion_checks` below. bin/propose_config.py uses it only to PROPOSE
# that config from the names this project's source actually uses, so a human
# reviews a measured list instead of typing one from memory.
ANIMATED_NODE_NAME_RE = re.compile(
    r"\b(Animated[A-Z]\w*|[A-Z]\w*Transition|AnimationController"
    r"|TweenAnimationBuilder|AnimatedBuilder)\("
    r"|\b(AnimationController)\b"
)

# How far either side of an animated-node match to look for a reduced-motion
# check. Wide enough to cover a `build()` method reading the flag a few lines
# above the widget it gates, narrow enough not to pick up an unrelated check
# elsewhere in a long file. Same shape as ENTRANCE_WINDOW above.
REDUCED_MOTION_WINDOW = 400


def reduced_motion_checks(ctx: AdapterContext) -> CheckSet:
    """Flag animated nodes with no reduced-motion signal nearby.

    "Which components count as animated" is config-driven per the issue this
    exists for — `token_categories.motion.animated_widgets` in the design-audit
    config — never a hardcoded widget list here. A missing or empty list is not
    "nothing is animated"; it is "this project has not told the audit what
    animated looks like", so the check is omitted rather than silently passing
    with zero findings (see `CheckSet.omitted` / the CapabilityError pattern in
    `a11y_checks` above).
    """
    motion_cfg = (ctx.audit_config.get("token_categories", {}) or {}).get("motion", {}) or {}
    widgets = motion_cfg.get("animated_widgets")

    if not widgets:
        return CheckSet([], omitted=[
            "reduced_motion_unwired: token_categories.motion.animated_widgets "
            "is not set in the audit config"])

    names = [w.strip() for w in widgets if isinstance(w, str) and w.strip()]
    # The scaffolded config ships this list as one "TODO: every widget/class
    # name ..." sentence. Taken literally that is a widget name nothing is ever
    # called, so the check compiled, matched nothing, and reported 0 findings on
    # a file full of AnimatedContainer — a clean-looking pass on an unconfigured
    # project. A placeholder is not a name.
    placeholders = [n for n in names if n.upper().startswith("TODO")]
    names = [n for n in names if n not in placeholders]
    if not names:
        return CheckSet([], omitted=[
            "reduced_motion_unwired: token_categories.motion.animated_widgets "
            + ("still holds the scaffolded TODO placeholder"
               if placeholders else "is set but empty")
            + " in the audit config"])

    animated_re = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b")

    def unwired(m, source):
        window = source[max(0, m.start() - REDUCED_MOTION_WINDOW):
                         m.end() + REDUCED_MOTION_WINDOW]
        return not REDUCED_MOTION_SIGNAL_RE.search(window)

    def describe(m, _source):
        return f"{m.group(0)} — no reduced-motion check within range"

    return CheckSet([
        Check("reduced_motion_unwired", animated_re, accept=unwired,
              tags=("motion",), snippet=describe),
    ])


FONT_SIZE_RE = re.compile(r"fontSize:\s*(\d+(\.\d+)?)")
ICON_BUTTON_RE = re.compile(r"\bIconButton\(")
GESTURE_WRAP_RE = re.compile(
    r"\b(SizedBox|Container)\(\s*(?:width:\s*(\d+(\.\d+)?)\s*,\s*)?"
    r"(?:height:\s*(\d+(\.\d+)?)\s*,\s*)?[^)]*?\b(GestureDetector|InkWell)\("
)


def _inside_call(source: str, offset: int, name: str, limit: int = 600) -> bool:
    """Whether `offset` sits inside an unclosed `name(` call (within `limit` chars)."""
    depth, i, floor = 0, offset - 1, max(0, offset - limit)
    while i >= floor:
        c = source[i]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                j = i
                while j > 0 and (source[j - 1].isalnum() or source[j - 1] == "_"):
                    j -= 1
                if source[j:i] == name:
                    return True
            else:
                depth -= 1
        i -= 1
    return False


def a11y_checks(ctx: AdapterContext) -> CheckSet:
    """Accessibility checks, with thresholds taken from config rather than baked in.

    The thresholds used to be the literals 14 and 48 in the scanner while the
    audit config *separately* declared min_text_sp 14 and min_touch_target_dp 48.
    They matched, but nothing made them match: raising the minimum in config would
    have left the scanner enforcing the old one, silently.

    A missing threshold omits its check and says so — see CheckSet.omitted. It
    must not default to a plausible number, because a project that never set one
    would then be told it passes a bar it never agreed to.
    """
    minimums = ctx.minimums()
    checks: list[Check] = []
    omitted: list[str] = []

    min_sp, bad = numeric_minimum(minimums, "min_text_sp")
    if bad:
        omitted.append(f"font_size: {bad}")
    elif min_sp is None:
        omitted.append("font_size: accessibility_minimums.min_text_sp is not set in the audit config")
    else:
        def small_text(m, _source):
            return float(m.group(1)) < float(min_sp)
        checks.append(Check("font_size", FONT_SIZE_RE, accept=small_text))

    # No threshold needed: an icon-only control either has an accessible label or
    # it does not.
    def icon_button_unlabelled(m, source):
        from ..engine.scan import matching_delimiter_span
        end = matching_delimiter_span(source, m.end() - 1)
        # `tooltip:` on the button, or a `Tooltip(` / `semanticLabel:` inside its
        # icon argument, labels it.
        if re.search(r"\btooltip\s*:|\bTooltip\(|\bsemanticLabel\s*:", source[m.start():end]):
            return False
        # Labelled by an enclosing `Semantics(label:/value: …)`.
        if _inside_call(source, m.start(), "Semantics"):
            return False
        # Labelled by an enclosing `Tooltip(message: …)` — the measured false
        # positive on a public sample (flutter/gallery's tooltip demo).
        return not _inside_call(source, m.start(), "Tooltip")
    checks.append(Check("icon_button_no_tooltip", ICON_BUTTON_RE,
                        accept=icon_button_unlabelled,
                        snippet="IconButton(...) — no tooltip:"))

    min_dp, bad = numeric_minimum(minimums, "min_touch_target_dp")
    if bad:
        omitted.append(f"small_tap_target: {bad}")
    elif min_dp is None:
        omitted.append(
            "small_tap_target: accessibility_minimums.min_touch_target_dp is not set in the audit config")
    else:
        def small_target(m, _source):
            dims = [float(d) for d in (m.group(2), m.group(4)) if d]
            return bool(dims) and min(dims) < float(min_dp)
        checks.append(Check("small_tap_target", GESTURE_WRAP_RE,
                            accept=small_target, snippet_limit=80))

    return CheckSet(checks, omitted)


# --- focus order -------------------------------------------------------
#
# Flutter's analogue of "DOM order vs. visual order" is "declaration order
# (what FocusTraversalGroup's default WidgetOrderTraversalPolicy walks) vs.
# Positioned offsets inside a Stack" — the one place source alone can name a
# widget's visual position without rendering anything. Everything else that can
# cause the same divergence (Transform, computed offsets, a custom
# RenderObject, Row/Column reordering via Flex `order`, an
# OverlayEntry) is invisible to a text scan and is named as a gap below rather
# than silently skipped.

FOCUSABLE_DEFAULT = (
    "GestureDetector", "InkWell", "IconButton", "ElevatedButton", "TextButton",
    "OutlinedButton", "FilledButton", "TextField", "TextFormField", "Checkbox",
    "Radio", "Switch", "DropdownButton", "Focus", "FocusableActionDetector",
)

STACK_RE = re.compile(r"\bStack\(")
POSITIONED_RE = re.compile(r"\bPositioned(?:\.fill|\.directional)?\(")
AUTOFOCUS_RE = re.compile(r"\bautofocus:\s*true\b")
FOCUS_TRAVERSAL_ORDER_RE = re.compile(r"\bFocusTraversalOrder\(")
TOP_RE = re.compile(r"\btop:\s*(-?\d+(\.\d+)?)")
LEFT_RE = re.compile(r"\bleft:\s*(-?\d+(\.\d+)?)")


def focus_order_checks(ctx: AdapterContext) -> CheckSet:
    """Regex-only findings: places where focus traversal is overridden explicitly.

    Both are review prompts, not confirmed defects — an `autofocus: true` or an
    explicit `FocusTraversalOrder` is often exactly the deliberate override the
    project wants. They are flagged because an override is also the most common
    place a *mistaken* one gets introduced, and neither can be judged correct or
    wrong from text alone.
    """
    return CheckSet([
        Check("autofocus_override", AUTOFOCUS_RE, tags=("focus-order",),
              snippet="autofocus: true — jumps traversal here on build; confirm this "
                      "is meant to receive focus first, ahead of declaration order"),
        Check("explicit_traversal_order", FOCUS_TRAVERSAL_ORDER_RE, tags=("focus-order",),
              snippet="FocusTraversalOrder(...) — traversal order is being set "
                      "explicitly; confirm the order value still matches this widget's "
                      "visual position"),
    ])


def _stack_span(source: str, stack_start: int) -> tuple[int, int]:
    from ..engine.scan import matching_delimiter_span
    open_paren = source.index("(", stack_start)
    return open_paren, matching_delimiter_span(source, open_paren) - 1


def _positioned_offsets(block: str) -> tuple[float | None, float | None]:
    from ..engine.scan import matching_delimiter_span
    open_paren = block.index("(")
    end = matching_delimiter_span(block, open_paren)
    body = block[open_paren:end]
    top = TOP_RE.search(body)
    left = LEFT_RE.search(body)
    return (float(top.group(1)) if top else None,
            float(left.group(1)) if left else None)


def stack_order_findings(source: str, focusable_widgets=FOCUSABLE_DEFAULT) -> list[dict]:
    """Positioned children of one Stack whose declaration order disagrees with
    their (top, left) offsets — a Stack is Flutter's direct equivalent of CSS
    absolute positioning, so this is the one structural case a source scan can
    actually catch rather than approximate.

    Only Positioned children that contain a widget from `focusable_widgets`
    are compared — a decorative image out of visual order is not a focus-order
    defect, and including it would make the check noisy enough to ignore.

    Two Positioned entries are only compared when *both* declare `top` (the
    primary reading-order axis); one or both omitting it (common — many
    Positioned widgets only constrain `bottom`/`right`) means there is nothing
    to compare and the pair is silently skipped rather than guessed at.

    This does NOT walk render output and cannot see: Transform-shifted widgets,
    offsets computed from MediaQuery/LayoutBuilder/animation values, a Stack
    built by a helper method rather than written inline, or RTL flips from
    `Positioned.directional`. Treat every finding as "read this Stack", not as
    a confirmed defect — the same posture this suite already takes for
    `small_tap_target`.
    """
    from ..engine.scan import matching_delimiter_span, line_of

    findings = []
    for stack_match in STACK_RE.finditer(source):
        open_paren, close = _stack_span(source, stack_match.start())
        stack_body = source[open_paren:close]

        entries = []  # (declared_index, top, left, offset)
        for i, pos_match in enumerate(POSITIONED_RE.finditer(stack_body)):
            block_start = pos_match.start()
            block_end = matching_delimiter_span(stack_body, stack_body.index("(", block_start))
            block = stack_body[block_start:block_end]
            if not any(re.search(rf"\b{re.escape(w)}\b", block) for w in focusable_widgets):
                continue
            top, left = _positioned_offsets(block)
            if top is None:
                continue
            entries.append((i, top, left if left is not None else 0.0,
                            open_paren + block_start))

        for a, b in zip(entries, entries[1:]):
            (idx_a, top_a, left_a, off_a), (idx_b, top_b, left_b, off_b) = a, b
            visually_earlier = (top_b, left_b) < (top_a, left_a)
            if visually_earlier:
                findings.append({
                    "line": line_of(source, off_b),
                    "kind": "stack_order_mismatch",
                    "snippet": (
                        f"Positioned(top: {top_b:g}, left: {left_b:g}) is declared "
                        f"after a Positioned(top: {top_a:g}, left: {left_a:g}) sibling "
                        f"but sits visually above/left of it — default focus traversal "
                        f"will visit them in declaration order, not reading order"
                    ),
                })
    return findings


# --- semantics rules (issue #128) -----------------------------------------
#
# Four rules, each derived from a defect that shipped, each with a named false
# positive. They live in the adapter because every one of them is a statement
# about Flutter's semantics API — which named argument publishes what — and that
# is language knowledge, not engine mechanics. The engine-side audit
# (bin/audit_semantics.py) only runs them, applies exceptions, and reports.
#
# What none of them can see, by construction: a subtree built by a helper method
# or another file (`child: _buildRow()`), an ancestor `Semantics` in a parent
# widget's file, and anything about the rendered SemanticsNode tree. A rule that
# cannot see its subtree does not fire — the gap is named here and in the
# report's caveat rather than read as a pass.

SEMANTICS_RE = re.compile(r"(?<![\w.])Semantics\(")
MERGE_SEMANTICS_RE = re.compile(r"\bMergeSemantics\(")
TAPPABLE_RE = re.compile(r"(?<![\w.])(GestureDetector|InkWell)\(")
INTERACTIVE_WRAPPER_RE = re.compile(r"(?<![\w.])(GestureDetector|InkWell|InkResponse)\(")
LABELLING_ARG_RE = re.compile(r"\b(label|onTap|selected|checked):")
ON_TAP_ARG_RE = re.compile(r"\bonTap:")
EXCLUDE_FROM_SEMANTICS_RE = re.compile(r"\bexcludeFromSemantics:\s*true\b")
EXCLUDE_SEMANTICS_ARG_RE = re.compile(r"\bexcludeSemantics:\s*true\b")
LIVE_REGION_RE = re.compile(r"\bliveRegion:\s*true\b")
ANNOUNCE_RE = re.compile(r"\bSemanticsService\.(sendAnnouncement|announce)\(")
ERROR_FIELD_RE = re.compile(r"\bfinal\s+(?:String|Widget)\??\s+(errorText|error)\s*;")
SELECTED_ARG_RE = re.compile(r"\bselected:")
SELECTION_COLOUR_RE = re.compile(
    r"\b(?:color|backgroundColor|foregroundColor):\s*[^,\n]*?\b(?:widget\.)?(?:is)?[sS]elected\b")
# Nodes that publish their own semantics — what `excludeSemantics: true` drops.
SEMANTICS_BEARING_RE = re.compile(
    r"(?<![\w.])(Text|Text\.rich|RichText|SelectableText|Icon|Image(?:\.\w+)?|Tooltip|"
    + "|".join(FOCUSABLE_DEFAULT) + r")\(")


def _calls(source: str, pattern: re.Pattern) -> list[tuple[int, int, int]]:
    """(start, open paren, index past close paren) for every call `pattern` matches."""
    from ..engine.scan import matching_delimiter_span
    out = []
    for m in pattern.finditer(source):
        open_paren = m.end() - 1
        out.append((m.start(), open_paren, matching_delimiter_span(source, open_paren)))
    return out


def _own_args(source: str, open_paren: int, close: int) -> str:
    """The call's own argument text, with every nested bracket's contents removed.

    `Semantics(label: 'x', child: InkWell(onTap: f))` has own args
    `label: 'x', child: InkWell()` — so a named argument of a descendant is never
    mistaken for one of the call's own. Strings are not special-cased: the caller
    passes comment-blanked source, and a bracket inside a string literal only ever
    removes more text, never invents an argument.
    """
    out, depth = [], 0
    for ch in source[open_paren + 1:close - 1]:
        if ch in "([{":
            depth += 1
            if depth == 1:
                out.append(ch)
            continue
        if ch in ")]}":
            depth -= 1
            if depth == 0:
                out.append(ch)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def _encloses(span: tuple[int, int, int], offset: int) -> bool:
    return span[1] < offset < span[2]


def semantics_findings(source: str) -> list[dict]:
    """All four issue-#128 rules over one file. Each finding carries `kind`,
    `line`, `snippet`, and `severity` (`fyi` or `should_fix`).

    1. `tappable_in_labelling_semantics` — a `Semantics` with its own
       `label:`/`onTap:`/`selected:`/`checked:` enclosing a `GestureDetector` or
       `InkWell` that has `onTap:` and no `excludeFromSemantics: true`, with no
       `MergeSemantics` in between. **Advisory (fyi), never gating**: issue #128's
       own follow-up measured this shape at 40% wrong, because whether the
       descendant opens a separate semantics node depends on the widget's
       implementation and ancestor configuration, not on the call site. The
       remedy it asks for is a rendered-semantics test, not the annotation.

    2. `error_not_announced` — a file declaring an `errorText`/`error` field that
       renders it directly in `Text(...)`, where that `Text` is not inside a
       `Semantics(liveRegion: true)` and the file never calls
       `SemanticsService.sendAnnouncement`/`announce`. Delegation (passing
       `errorText:` on to `InputDecoration` or another widget) is never matched,
       because only a `Text` rendering it fires — the receiving widget is judged
       in its own file.

    3. `selection_by_colour_only` — a `GestureDetector`/`InkWell`/`InkResponse`
       whose subtree computes a colour from `selected`/`isSelected`, with no
       `selected:` argument on any `Semantics` enclosing it or inside it.

    4. `exclude_semantics_over_multiple_nodes` — `Semantics(excludeSemantics:
       true, ...)` whose inline subtree holds two or more semantics-bearing
       nodes. One `Text` (the safe use) does not fire; neither does the
       `ExcludeSemantics` widget, which the lookbehind keeps from matching.
    """
    from ..engine.scan import line_of

    code = blank_comments(source)
    semantics = _calls(code, SEMANTICS_RE)
    merges = _calls(code, MERGE_SEMANTICS_RE)
    findings: list[dict] = []

    def add(kind, offset, severity, snippet):
        findings.append({"kind": kind, "line": line_of(code, offset),
                         "severity": severity, "snippet": snippet})

    # Rule 1
    reported: set[int] = set()
    for sem in semantics:
        if not LABELLING_ARG_RE.search(_own_args(code, sem[1], sem[2])):
            continue
        for tap in _calls(code[sem[1]:sem[2]], TAPPABLE_RE):
            start = sem[1] + tap[0]
            if start in reported:
                continue
            own = _own_args(code, sem[1] + tap[1], sem[1] + tap[2])
            if not ON_TAP_ARG_RE.search(own) or EXCLUDE_FROM_SEMANTICS_RE.search(own):
                continue
            if any(_encloses(mg, start) and mg[0] > sem[0] for mg in merges):
                continue
            reported.add(start)
            add("tappable_in_labelling_semantics", start, "fyi",
                f"{code[start:sem[1] + tap[1]]}(onTap: ...) inside a labelling Semantics, "
                "without excludeFromSemantics: true — may publish a second, unlabelled "
                "tappable node. Prove it either way with a rendered-semantics test "
                "(issue #128: this shape alone was 40% wrong).")

    # Rule 2
    fields = {m.group(1) for m in ERROR_FIELD_RE.finditer(code)}
    if fields and not ANNOUNCE_RE.search(code):
        live = [s for s in semantics if LIVE_REGION_RE.search(_own_args(code, s[1], s[2]))]
        names = "|".join(sorted(fields))
        render = re.compile(rf"(?<![\w.])Text\(\s*(?:widget\.)?(?:{names})\b")
        for m in render.finditer(code):
            if any(_encloses(s, m.start()) for s in live):
                continue
            add("error_not_announced", m.start(), "should_fix",
                f"{m.group(0).strip()}...) renders the error with neither a "
                "Semantics(liveRegion: true) around it nor SemanticsService."
                "sendAnnouncement — an error appearing after submit changes the "
                "screen silently")

    # Rule 3
    selected_sems = [s for s in semantics
                     if SELECTED_ARG_RE.search(_own_args(code, s[1], s[2]))]
    for wrap in _calls(code, INTERACTIVE_WRAPPER_RE):
        colour = SELECTION_COLOUR_RE.search(code, wrap[1], wrap[2])
        if not colour:
            continue
        if SELECTED_ARG_RE.search(_own_args(code, wrap[1], wrap[2])):
            continue
        if any(_encloses(s, wrap[0]) or wrap[1] < s[0] < wrap[2] for s in selected_sems):
            continue
        add("selection_by_colour_only", colour.start(), "should_fix",
            f"{code[wrap[0]:wrap[1]]}(...) shows selection through "
            f"`{colour.group(0).strip()}` and no Semantics(selected: ...) reaches it "
            "— selection is announced by colour alone")

    # Rule 4
    for sem in semantics:
        own = _own_args(code, sem[1], sem[2])
        if not EXCLUDE_SEMANTICS_ARG_RE.search(own):
            continue
        nodes = [m.group(1) for m in SEMANTICS_BEARING_RE.finditer(code, sem[1], sem[2])]
        if len(nodes) < 2:
            continue
        add("exclude_semantics_over_multiple_nodes", sem[0], "should_fix",
            f"Semantics(excludeSemantics: true) drops {len(nodes)} semantics-bearing "
            f"descendants ({', '.join(nodes[:4])}{', ...' if len(nodes) > 4 else ''}) — "
            "only a single Text whose content is the label is safe; use the scoped "
            "ExcludeSemantics widget around what should be hidden")

    findings.sort(key=lambda f: f["line"])
    return findings


SEMANTICS_KINDS = ("tappable_in_labelling_semantics", "error_not_announced",
                   "selection_by_colour_only", "exclude_semantics_over_multiple_nodes")


# --- user-facing copy -------------------------------------------------------

# Text('...') / Text("...") — the widget itself, plus the other widgets whose
# whole argument list IS the literal rather than a keyword carrying it.
# `SelectableText('...')` takes the same first-positional-string shape as
# `Text(...)` and was invisible until this rule existed — a selectable
# error/help paragraph is exactly the kind of string an audit exists to catch.
TEXT_WIDGET_RE = re.compile(
    r"""\b(?:Text|SelectableText)\(\s*(['"])((?:\\.|(?!\1).)*?)\1""")

# Keyword arguments that carry user-facing copy outside a bare Text(...) call.
# Purely a Flutter fact, which is why it lives here rather than in the engine.
#
# `label` was missing until 2026-08-07, and it is the argument a button takes.
# Every button caption in both consuming apps — 405 literals in one, 67 in the
# other — was invisible to copy extraction, so the copy inventory silently
# excluded the most user-facing copy there is. Found by planting a deliberately
# bad button label and watching the audit report clean.
#
# `label` is not `labelText`: Material's field takes the latter, and this
# project's own buttons and chips take the former. Matching one and not the
# other is how a keyword list drifts from the widgets it is supposed to cover.
# Extracted, but NOT treated as microcopy-by-construction. `label` is dual-use
# in a way the other keys are not: a button takes a two-word caption and a
# transcript chip takes a whole sentence. Forcing both to microcopy told a chip
# its sentence should not end in a full stop. Length decides these instead.
#
# `text`, `subtitle` and `content` joined `label` here for the same reason:
# `TextSpan(text: '...')` (the only way `RichText`/`Text.rich` copy shows up —
# there is no bare string literal to catch there), a `ListTile`'s `subtitle`,
# and a custom toast/banner's `content` can each be a whole sentence or a
# two-word fragment depending on the call site. Forcing any of them to
# microcopy-by-construction would have mis-flagged the long ones the same way
# `label` did before this split existed.
AMBIGUOUS_KEYS = ("label", "text", "subtitle", "content")

# Argument keys still missing until this fix, found the same way `label` was:
# by reading real call sites rather than guessing from the widget catalogue.
#
# `message` is what `Tooltip` and `SnackBar.showSnackBar`'s simple-message
# helpers actually take — not `tooltip` (that key exists on `IconButton` etc.,
# already covered) — so every plain Tooltip's text was silently excluded.
# `confirmText`/`cancelText` are the button captions `showDatePicker` and
# friends take directly, bypassing `Text(...)` entirely. `hint` (as opposed to
# `hintText`) and `placeholder` are the equivalent keys on non-Material and
# third-party field widgets used alongside Material ones in the same app.
MICROCOPY_KEYS = (
    "label", "labelText", "hintText", "tooltip", "semanticLabel", "errorText",
    "helperText", "title", "titleText", "message", "confirmText", "cancelText",
    "hint", "placeholder", "actionLabel", "buttonText",
)
KEYWORD_RE = re.compile(
    r"""\b(""" + "|".join(MICROCOPY_KEYS + AMBIGUOUS_KEYS) +
    r""")\s*:\s*(['"])((?:\\.|(?!\2).)*?)\2"""
)

# Dart implicitly concatenates adjacent string literals ('a ' 'b' -> 'a b') with
# no operator between them, so one logical Text(...) argument routinely spans
# several source lines. Matching only the first literal truncates the copy
# mid-sentence — precisely the gap an audit built on this inventory cannot see
# around. A language quirk, not a general one, so it belongs here.
CONTINUATION_RE = re.compile(r"""[ \t\n]*(['"])((?:\\.|(?!\1).)*?)\1""")


def _consume_continuations(source: str, end: int) -> tuple:
    extra = ""
    pos = end
    while True:
        m = CONTINUATION_RE.match(source, pos)
        if not m:
            break
        extra += m.group(2)
        pos = m.end()
    return extra, pos


def extract_copy_strings(source: str) -> list:
    """(offset, text, keyword|None, kind, skip_reason|None) for every
    user-facing string in `source`.

    `keyword` drives classification (see AMBIGUOUS_KEYS — nulled for keys whose
    length, not their name, decides microcopy vs content). `kind` is the
    provenance the classifier must NOT touch: the literal widget/keyword a
    string was found through — "text" for a bare Text(...), otherwise the
    keyword's own name ("label", "title", "hintText", ...). Two entries with
    the same text but a different kind are a nav label and a screen title, not
    a duplicate — that distinction was previously discarded at the point of
    extraction and unrecoverable downstream.

    A string containing `$` is Dart interpolation — `'Hello $name'` — and its
    static shell cannot be scored for readability or checked against the
    mechanical microcopy rules the way a fixed string can (there is no reading
    ease for "Hello ", and no honest answer to whether it "ends in a period"
    when the real ending is a runtime value). The old behaviour was to drop
    these with `continue`, which is exactly the failure this project's
    governing principle is about: a greeting built from interpolation is
    still user-facing copy, and an inventory that quietly excludes it is
    indistinguishable from a project that has no interpolated copy at all.
    So it is still recorded, tagged with a reason a report can surface as
    "N strings skipped — dynamic interpolation" instead of vanishing.
    """
    found = []
    seen_spans = set()

    for pattern, text_group, keyword_group in (
        (TEXT_WIDGET_RE, 2, None),
        (KEYWORD_RE, 3, 1),
    ):
        for m in pattern.finditer(source):
            text = m.group(text_group)
            extra, _ = _consume_continuations(source, m.end())
            text += extra
            if not text.strip():
                continue
            span = m.span(text_group)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            raw_keyword = m.group(keyword_group) if keyword_group else None
            kind = raw_keyword or "text"
            keyword = None if raw_keyword in AMBIGUOUS_KEYS else raw_keyword
            skip_reason = "dynamic interpolation" if "$" in text else None
            found.append((span[0], text, keyword, kind, skip_reason))

    return found


# --------------------------------------------------------------------------- #
# Capability detection (base.LanguageCapabilityProtocol)
# --------------------------------------------------------------------------- #
#
# Every signature below is a Dart/Flutter fact and none of it may migrate into
# the engine: what a router looks like is exactly the sort of language-shaped
# knowledge the adapter seam exists to hold. The engine asks "does this project
# route?" and never learns what the answer was made of.

ROUTING_SIGNATURES = (
    re.compile(r"\bGoRouter\s*\("),
    re.compile(r"\bMaterialApp\.router\b"),
    re.compile(r"\bCupertinoApp\.router\b"),
    re.compile(r"\bonGenerateRoute\s*:"),
    re.compile(r"\bNavigator\.(of\(\s*context\s*\)\.)?pushNamed\b"),
    re.compile(r"@(AutoRouterConfig|MaterialAutoRouter|RoutePage)\b"),
    re.compile(r"\bRouter\s*\(\s*routerDelegate\s*:"),
)

CAPABILITY_SIGNATURES = {
    "routing": (
        ROUTING_SIGNATURES,
        "a Flutter app either declares routes somewhere or pushes widgets "
        "directly; these are the constructions that mean the former",
    ),
}

CAPABILITIES = (
    Capability(
        name="routing",
        profile_field="source.routesFile",
        why="every route-aware check reads the file this field names. Undeclared, "
            "the check has nothing to read and reports clean — inert, not passing",
    ),
)


def capabilities(ctx: AdapterContext) -> list:
    """What this adapter can be asked about. See base.LanguageCapabilityProtocol."""
    return list(CAPABILITIES)


def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    """Whether this project does `name`, or a refusal.

    Three separate refusals, all of which would otherwise arrive as "no":
    an unknown capability, a source root that is not there, and a source root
    holding no Dart at all. The last is the one that bites in practice — point
    the adapter at a workspace stub and every capability reads as absent, which
    is a clean report about a tree nobody looked at.
    """
    signatures = CAPABILITY_SIGNATURES.get(name)
    if signatures is None:
        raise CapabilityError(name, NAME,
                              f"no signature set for this capability; known: "
                              f"{sorted(CAPABILITY_SIGNATURES)}")
    patterns, why = signatures

    repo = Path(str(ctx.repo))
    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    if not root_rel:
        raise CapabilityError(name, NAME, "profile sets no source.root, so there is no "
                                          "tree to read for evidence")
    root = repo / root_rel
    if not root.is_dir():
        raise CapabilityError(name, NAME, f"source.root {root_rel!r} is not a directory here")

    sources = [p for p in root.rglob("*.dart") if not p.name.endswith(GENERATED_SUFFIXES)]
    if not sources:
        raise CapabilityError(name, NAME,
                              f"no hand-written .dart under {root_rel!r} — absence of evidence "
                              f"in an empty tree is not evidence of absence")

    hits = []
    unreadable = []
    for path in sorted(sources):
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f"{path.relative_to(repo).as_posix()}: {exc}")
            continue
        if any(p.search(text) for p in patterns):
            hits.append(path.relative_to(repo).as_posix())

    if not hits and unreadable:
        # A negative answer built partly on files nobody could read is a guess.
        raise CapabilityError(name, NAME,
                              f"found no evidence, but {len(unreadable)} file(s) could not be "
                              f"read: {unreadable[:5]}")
    return CapabilityEvidence(
        present=bool(hits),
        files=tuple(hits[:20]),
        why=why if hits else f"none of the {len(sources)} source file(s) match: {why}",
    )


def package_prefix(ctx: AdapterContext) -> str | None:
    """How this package's own absolute imports are spelled, e.g. package:foo/.

    Derived from pubspec.yaml's `name:` rather than configured. The layer-boundary
    audit used to hardcode one consumer's own package prefix — the single most
    project-specific string in the whole suite, and one that would have silently
    stopped matching (so silently reported zero violations) the first time anyone
    renamed the package. Deriving it removes the literal instead of relocating it.
    """
    pubspec = Path(str(ctx.repo)) / "pubspec.yaml"
    if not pubspec.is_file():
        return None
    for line in pubspec.read_text().splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            return f"package:{name}/" if name else None
    return None


def resolve_source(ctx: AdapterContext, source: dict) -> Path | None:
    """The file a declared token source points at, or None if unresolvable.

    Resolved through the package manager's own map rather than by guessing a path.
    Guessing is what silently broke export_palette.py and both copies of
    audit_contrast.py, and it is why the tokens moving into a package went
    unnoticed by the design audit for as long as it did.

    Factored out when a second consumer arrived (the colour-role audit needs a
    different file from the same package). One resolver, so a project that
    resolves for one audit resolves for both.
    """
    repo = Path(str(ctx.repo))

    if source.get("kind") == "file":
        target = repo / source.get("path", "")
        return target if target.is_file() else None

    if source.get("kind") != "package":
        return None

    resolver = repo / source.get("resolveVia", "")
    if not resolver.is_file():
        return None
    try:
        packages = json.loads(resolver.read_text()).get("packages", [])
    except (OSError, ValueError):
        return None
    for package in packages:
        if package.get("name") != source.get("package"):
            continue
        root = package["rootUri"]
        root = root[len("file://"):] if root.startswith("file://") else root
        target = (resolver.parent / root).resolve() / source.get("pathInPackage", "")
        return target if target.is_file() else None
    return None


def token_names_matching(ctx: AdapterContext, prefix: str) -> set | None:
    """Declared token names in `tokens.source` whose name starts with `prefix`,
    or None if the token source is undeterminable.

    Generalises `token_names`'s colour-only regex to any naming convention a
    project's token file uses — `space16`, `radius8`, `durationFast`,
    `curveStandard`, `size48` are all `static const <prefix>\\w+ = ...;`
    declarations the same way `colorPrimary` is. Which prefixes correspond to
    which category (spacing, radii, durations, curves, sizing, colour, ...) is
    not this adapter's call: a naming convention is a project fact, so it is
    read from `unusedTokens.categories` in the project's architecture rules
    rather than hardcoded here.

    Same None-vs-empty contract as `token_names` and `color_role_names`: None
    means "could not read the tokens", which must never be reported as "this
    prefix matches nothing" — the caller would otherwise treat an unresolved
    package as a clean audit.
    """
    source = (ctx.profile.get("tokens", {}) or {}).get("source", {}) or {}
    target = resolve_source(ctx, source)
    if target is None:
        return None
    return set(re.findall(rf"static const ({re.escape(prefix)}\w+)", target.read_text()))


# Which declared-token category each check's literal must be repaired from.
# The keys are this adapter's own check kinds (see `checks`), so the map belongs
# here; the values are category labels a project maps to its own naming prefixes
# (`{"spacing": "space"}`) in arch-rules, never guessed.
#
# `entrance_curve` is deliberately absent: it fires on `AppTokens.curveStandard`
# used where an entrance curve belongs — already a token, and which token is
# right is a judgement about the animation, not a value lookup.
REPAIR_CATEGORY = {
    "color": "color",
    "edge_insets": "spacing",
    "border_radius": "radius",
    "duration": "duration",
    "curve": "curve",
}


def repair_literals(check_kind: str, match, accessor: str):
    """`[(start, end, text, category)]` for every raw literal in one match, or
    None if this kind of finding carries no literal to replace.

    The Dart half of band-1 repair: which capture group holds the value, how an
    argument list is partitioned, and which literals are not violations in the
    first place. `engine/token_repair.py` decides what a literal could become
    and never learns any of this.

    The partitioning mirrors `_has_raw_number` line for line, on purpose. A
    repairer that splits an argument list differently from the audit that
    flagged it would offer to rewrite something no finding ever mentioned —
    and zeros are skipped here for the same reason they are not violations
    there (see `_is_zero`).
    """
    category = REPAIR_CATEGORY.get(check_kind)
    if category is None:
        return None

    if check_kind in ("color", "duration", "curve"):
        return [(match.start(), match.end(), match.group(0), category)]

    if check_kind == "border_radius":
        arg = match.group(1)
        stripped = arg.strip()
        if not RAW_NUMBER_RE.match(arg):
            return []
        start = match.start(1) + arg.index(stripped)
        return [(start, start + len(stripped), stripped, category)]

    # edge_insets
    found = []
    offset = match.start(2)
    for part in match.group(2).split(","):
        part_start, offset = offset, offset + len(part) + 1
        if not part.strip() or (accessor and accessor in part):
            continue
        whole = RAW_NUMBER_RE.match(part)
        if whole:
            stripped = part.strip()
            spans = [(part_start + part.index(stripped),
                      part_start + part.index(stripped) + len(stripped), stripped)]
        else:
            spans = [(part_start + m.start(1), part_start + m.end(1), m.group(1))
                     for m in NAMED_ARG_NUMBER_RE.finditer(part)]
        found.extend((s, e, text, category) for s, e, text in spans
                     if not _is_zero(text))
    return found


def token_declarations(ctx: AdapterContext, prefix: str) -> dict | None:
    """`{token name: declared value text}` for tokens whose name starts with
    `prefix`, or None if the token source is undeterminable.

    The value half of `token_names_matching`, and it exists for exactly one
    consumer: band-1 token repair, which cannot say "this literal is
    `AppTokens.space8`" from names alone — it has to know that `space8` is `8.0`.

    The right-hand side is returned as *text* (`8.0`, `Color(0xFF05678D)`,
    `Duration(milliseconds: 150)`, `Curves.easeInOut`) rather than parsed. What
    counts as equal is the repair engine's judgement (numeric for a spacing
    token, normalised text for a colour), and parsing here would mean deciding
    that in the adapter with less context.

    Same None-vs-empty contract as `token_names_matching`, and it is
    load-bearing twice over here: an unresolved token source reported as "no
    tokens" would make every literal look like band 3 ("no matching token
    exists"), which is the one band that tells a human to go author a new
    token. Silence would not just under-report — it would actively recommend
    growing the design system.
    """
    source = (ctx.profile.get("tokens", {}) or {}).get("source", {}) or {}
    target = resolve_source(ctx, source)
    if target is None:
        return None
    pairs = re.findall(
        rf"static const (?:[\w<>,?\s\[\]]+\s+)?({re.escape(prefix)}\w+)\s*=\s*([^;]+);",
        target.read_text())
    return {name: value.strip() for name, value in pairs}


def token_names(ctx: AdapterContext) -> set | None:
    """Colour-token names the design system defines, or None if undeterminable.

    None and empty-set are different answers and the caller relies on it: None
    means "could not read the tokens" (the package is unresolved), which must not
    be reported as "the config lists tokens that do not exist".

    A thin, colour-specific wrapper over `token_names_matching` kept for the
    existing `audit_tokens.py` call site, which compares against the design-audit
    config's `token_categories.color` list and has no reason to learn about other
    categories.
    """
    return token_names_matching(ctx, "color")


def color_role_names(ctx: AdapterContext) -> set | None:
    """Semantic colour-role names — the re-skinning contract's actual surface.

    Distinct from `token_names`, and the distinction is the point. A token is a
    literal the palette defines; a *role* is what a component asks for. A brand
    swap changes tokens, and only the roles a component actually reads carry that
    change onto the screen.

    In Dart these are the fields of the theme extension a component reads through
    (`final Color primary;`), which is a different file from the token constants
    even when both ship in the same package. Same None-vs-empty contract as above.
    """
    source = (ctx.profile.get("tokens", {}) or {}).get("roleSource", {}) or {}
    target = resolve_source(ctx, source)
    if target is None:
        return None
    return set(re.findall(r"^\s*final Color (\w+);", target.read_text(), re.M))


def color_role_readers(ctx: AdapterContext) -> list[str]:
    """Regex fragments that mean "this source is reading role X".

    The accessor's own name is derived from the profile; the short local names
    are conventional (`final colors = DsColors.of(context)`), which is why they
    are a default a project may override rather than something inferred.
    """
    tokens = ctx.profile.get("tokens", {}) or {}
    accessor = tokens.get("roleAccessor")
    locals_ = tokens.get("roleLocalNames") or ["colors", "c"]
    fragments = [rf"\b{re.escape(name)}" for name in locals_]
    if accessor:
        fragments.append(rf"{re.escape(accessor)}\.of\(context\)")
    return fragments


# ---------------------------------------------------------------------------
# Structural extraction, for audit_contract_headers
# ---------------------------------------------------------------------------
#
# These four answer "what does this class declare", "what does this code read"
# and "where are the block comments" — questions the contract-header engine asks
# without knowing what language it is looking at. Every Dart-shaped assumption
# about `final`, `//`, `/* */` and string literals is here rather than there.

CONTRACT_CAPABLE = True  # the engine checks this before trusting the four below


def blank_comments(source: str) -> str:
    """`source` with every comment replaced by spaces, same length, same lines.

    Blanking rather than deleting is load-bearing. The engine reports line
    numbers into the original file and does set arithmetic on names, so any
    transform that shifted offsets would make findings point at the wrong line.

    It also has to know about strings, which is the part a regex gets wrong: a
    `'https://…'` literal contains `//`, and stripping from there to end-of-line
    silently eats real code. Dart's four quote forms plus `r`-prefixes and
    backslash escapes are all handled for that one reason.
    """
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        # Strings first — a comment marker inside one is not a comment.
        if ch in "'\"":
            triple = source[i:i + 3] in ("'''", '"""')
            quote = source[i:i + 3] if triple else ch
            raw = i > 0 and source[i - 1] == "r"
            i += len(quote)
            while i < n:
                if not raw and source[i] == "\\":
                    i += 2
                    continue
                if source[i:i + len(quote)] == quote:
                    i += len(quote)
                    break
                i += 1
            continue
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if source.startswith("/*", i):
            # Dart block comments nest, and a doc header quoting `/*` would
            # otherwise end the block early.
            depth = 0
            while i < n:
                if source.startswith("/*", i):
                    depth += 1
                    out[i] = out[i + 1] = " "
                    i += 2
                    continue
                if source.startswith("*/", i):
                    depth -= 1
                    out[i] = out[i + 1] = " "
                    i += 2
                    if depth == 0:
                        break
                    continue
                if source[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def block_comments(source: str) -> list[tuple[int, str]]:
    """Every `/* … */` block, as (1-based start line, text)."""
    found = []
    for match in re.finditer(r"/\*(.*?)\*/", source, re.DOTALL):
        found.append((source.count("\n", 0, match.start()) + 1, match.group(1)))
    return found


def _class_body_span(source: str, class_name: str) -> tuple[int, int] | None:
    match = re.search(rf"\bclass\s+{re.escape(class_name)}\b[^{{]*{{", source)
    if not match:
        return None
    depth, start = 0, match.end() - 1
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return start + 1, i
    return None


def class_members(source: str, class_name: str) -> dict[str, int] | None:
    """Like `class_fields`, but also the class's own public *methods*.

    For a class whose whole purpose is to be a surface — an adapter — a query
    method is part of that surface. `int totalMinutesToday(String id)` is
    something a screen calls and a contract header documents, and excluding it
    reported correctly documented members as stale.

    Deliberately a separate entry point rather than a flag on `class_fields`,
    because it is the wrong answer for a UI widget: `build`, `createState` and
    `dispose` are framework overrides, not a contract, and a caller asking about
    a widget must not get them.
    """
    return _members(source, class_name, methods=True)


def class_fields(source: str, class_name: str) -> dict[str, int] | None:
    """`{field name: 1-based line}` for one class's `final` declarations.

    None means the class is not in this source — distinct from `{}` meaning it
    declares nothing, which the caller must not conflate.

    Three things this gets right that a line-anchored regex does not, each of
    which produced a wrong answer on a real file:

    * The span is brace-matched to `class_name`. An adapter file usually also
      declares the row model it hands the screen, and reading to end-of-file
      counted `SupportTicket.subject` as an adapter field — 16 fields where the
      adapter has 9.
    * Fields are split on `;` at depth 0, so a declaration wrapped over seven
      lines (`final void Function({String? id, …}) onSave;`) is found. Missing it
      reported a documented field as absent, which is a false positive on a
      correct header — the one failure that gets an audit switched off.
    * A constructor's `required this.x` list and a method body's internals are
      both at depth > 0 or end in `}`, so neither reads as a declaration.
    """
    return _members(source, class_name, methods=False)


def _members(source: str, class_name: str, methods: bool) -> dict[str, int] | None:
    blanked = blank_comments(source)
    span = _class_body_span(blanked, class_name)
    if span is None:
        return None
    start, end = span
    fields: dict[str, int] = {}
    depth, buf_start, buf = 0, start, []

    def record(stmt: str, offset: int):
        name = _member_name(stmt, methods=methods)
        if name:
            fields.setdefault(name, blanked.count("\n", 0, offset) + 1)

    for i in range(start, end):
        ch = blanked[i]
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if depth == 0 and ch == ";":
            record("".join(buf), buf_start)
            buf, buf_start = [], i + 1
        elif depth == 0 and ch == "}":
            # A brace-bodied member ends here. Still worth reading: a getter
            # written `T get x { … }` is part of the read surface.
            record("".join(buf), buf_start)
            buf, buf_start = [], i + 1
        else:
            if not buf:
                buf_start = i
            buf.append(ch)
    return fields


# `bool get canConfirm`, `List<Point>? get points` — the signature only.
GETTER_RE = re.compile(r"^\s*(?:@\w+\s+)*(?:static\s+)?[\w<>,?\s\[\]().]*?"
                       r"\bget\s+([A-Za-z_]\w*)\s*$")


# `int totalMinutesToday(String id)` — a return type, a name, an argument list.
# Anchored so a call expression inside a body cannot match.
METHOD_RE = re.compile(r"^\s*(?:@\w+\s+)*(?:static\s+)?[\w<>,?\s\[\]]+?"
                       r"\b([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:async\s*)?$")


def _member_name(stmt: str, methods: bool = False) -> str | None:
    """The field or getter a class-body statement declares, if it declares one.

    Getters count, and leaving them out was wrong. An adapter exposing
    `bool get canConfirm` is offering something a screen reads and a contract
    header documents; treating it as "not declared" reported six correctly
    documented members as stale header entries across a second project.

    Only the part before `=>` or `{` is considered, so a method body mentioning
    the word `get` cannot masquerade as a getter declaration.
    """
    if re.match(r"^\s*(?:@\w+\s+)*final\b", stmt):
        names = re.findall(r"\b([A-Za-z_]\w*)\b", stmt)
        return names[-1] if names else None
    signature = re.split(r"=>|\{", stmt, maxsplit=1)[0]
    match = GETTER_RE.match(signature)
    if match:
        return match.group(1)
    if methods:
        found = METHOD_RE.match(signature)
        if found and not found.group(1).startswith("_"):
            return found.group(1)
    return None


def receiver_aliases(source: str, receiver: str) -> set[str]:
    """Local names bound to `receiver`, so reads through them still count.

    A screen that writes `SubscriptionAdapter get _a => widget.adapter;` and then
    `_a.activePlans` is reading its adapter. Counting only `adapter.` reported
    **every field of that adapter as dead** — 15 on one screen, and the same
    mistake on 7 files in one project.

    Three bindings appear in practice and all three are matched:

        SubscriptionAdapter get _a => widget.adapter;
        final adapter = widget.adapter;
        var a = widget.adapter;
    """
    code = blank_comments(source)
    escaped = re.escape(receiver)
    patterns = (
        rf"\bget\s+([A-Za-z_]\w*)\s*=>\s*(?:widget\.)?{escaped}\s*;",
        rf"\b(?:final|var|late\s+final)\s+([A-Za-z_]\w*)\s*=\s*(?:widget\.)?{escaped}\s*;",
    )
    found = {m.group(1) for pattern in patterns for m in re.finditer(pattern, code)}
    return found - {receiver}


def member_reads(source: str, receiver: str) -> set[str]:
    """Names read off `receiver` in real code — `adapter.onSave` → {"onSave"}.

    Comments are blanked first, and that is not a detail. A CONTRACT header
    listing `- adapter.isLoading` would otherwise count as a read of
    `isLoading`, so every documented field would look wired and the dead-field
    check would report zero forever. Measured: it reported 0 dead fields on a
    tree with 14.
    """
    return set(re.findall(rf"\b{re.escape(receiver)}\.(\w+)", blank_comments(source)))


# Dart words that can follow a type name without being a variable it declares —
# `class ThingAdapter extends …`, `ThingAdapter as x`.
_NOT_A_BINDING = frozenset({
    "extends", "implements", "with", "as", "is", "on", "get", "set", "return",
    "new", "const", "final", "var", "class", "mixin", "typedef", "late",
})


def typed_member_reads(source: str, types) -> dict[str, set[str]]:
    """`{type name: members read off any identifier declared with that type}`.

    DO NOT "simplify" this back to matching one well-known receiver name.

    The audit that calls this used to answer "is this adapter field read
    anywhere" by looking only for reads off an identifier literally named
    `adapter` (plus local aliases of it). That holds on screens, because a screen
    names its adapter `adapter` by convention — and silently fails everywhere
    else. Measured on a real project: `CarePlanPdfPayload.fromAdapter(
    CarePlanAdapter a)` reads `a.patientName` and `a.nutritionDeficiencies`, and
    both were reported "declared and read nowhere" with *deletion* as the
    suggested fix. The receiver has to be resolved by its declared type, not by
    what it happens to be called. This is the same class of bug as the
    line-scoping defect in #107: a regex-shaped assumption about source text,
    true of the corpus it was written against and quietly false elsewhere.

    Raises `CapabilityError` when the file hands one of `types` to an identifier
    whose type this parser cannot follow (`dynamic`/`Object`). Reads through such
    an identifier are invisible here, so every field of that adapter would read
    as dead — "I cannot tell" must not come back as "nothing reads it". The rule
    is deliberately narrow: an inferred `final x = ThingAdapter(...)` is followed
    fine, and only an explicitly untyped binding refuses, because an audit that
    refuses on ordinary code is an audit nobody runs.
    """
    code = blank_comments(source)
    found: dict[str, set[str]] = {}
    for type_name in types:
        escaped = re.escape(type_name)
        blind = re.search(rf"\b(?:dynamic|Object\??)\s+[A-Za-z_]\w*\s*=[^;]*"
                          rf"\b{escaped}\b", code)
        if blind:
            raise CapabilityError(
                "typed_member_reads", NAME,
                f"{type_name} is bound to an untyped receiver "
                f"({blind.group(0).strip()!r}); reads through it cannot be "
                f"resolved, so this file cannot be used to decide whether "
                f"{type_name}'s members are read")
        names = set()
        # `ThingAdapter a`, `final ThingAdapter a`, `ThingAdapter? a` — a
        # parameter, field or local whose declared type is the contract class.
        for match in re.finditer(
                rf"\b(?:final\s+|const\s+|late\s+(?:final\s+)?)?{escaped}\s*\??\s+"
                rf"([A-Za-z_]\w*)\b", code):
            if match.group(1) not in _NOT_A_BINDING:
                names.add(match.group(1))
        # `final a = something as ThingAdapter;` and `final a = ThingAdapter(…)`.
        for pattern in (rf"\b(?:final|var|late\s+final)\s+([A-Za-z_]\w*)\s*="
                        rf"[^;]*\bas\s+{escaped}\b",
                        rf"\b(?:final|var|late\s+final)\s+([A-Za-z_]\w*)\s*=\s*"
                        rf"(?:const\s+)?{escaped}\s*\("):
            names |= {m.group(1) for m in re.finditer(pattern, code)}
        members = set()
        for name in names:
            members |= member_reads(code, name)
        if members:
            found[type_name] = members
    return found


# --- audit_error_handling / audit_api_consistency syntax ---------------------
# Moved verbatim out of those audits, which used to apply Dart's spelling to
# every stack. Behaviour on Dart is unchanged.
ERROR_HANDLING = ErrorHandlingSyntax(
    catch_var=re.compile(
        r"catch\s*\(\s*(\w+)(?:\s*,\s*\w+)?\s*\)|onError:\s*\(\s*(\w+)\s*\)\s*=>"),
    type_guard=lambda var, typ: re.compile(
        rf"\b{re.escape(var)}\s+is\s+{re.escape(typ)}\b"),
    # Only a *bare* `$var`/`${var}` - not `${var.message}`.
    stringify=lambda var: re.compile(
        rf"\b{re.escape(var)}\.toString\(\)"
        rf"|\$\{{{re.escape(var)}\}}"
        rf"|\${re.escape(var)}(?![\w.])"),
    type_test=lambda cls: re.compile(rf"\bis\s+{re.escape(cls)}\b"),
    string_quotes=("'", '"'),
    line_comment="//",
)

API_CONSISTENCY = ApiConsistencySyntax(
    user_facing=re.compile(
        r"""(?:Text\(\s*|(?:label|title|tooltip|hintText|labelText|semanticLabel|"""
        r"""message|subtitle|hint)\s*:\s*)'([^'\\]{2,})'"""),
    defaulted=re.compile(r"""this\.\w+\s*=\s*'([^'\\]+)'"""),
    compared=re.compile(r"""(?:==|!=)\s*'([^'\\]{2,})'|'([^'\\]{2,})'\s*(?:==|!=)"""),
    tappable=re.compile(r"\b(?:InkWell|GestureDetector)\("),
)
