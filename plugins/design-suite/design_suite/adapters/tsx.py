"""TypeScript / React adapter — inline styles and Tailwind arbitrary values.

## What it audits, and the one idea that makes Tailwind auditable

Two styling paradigms, and they need opposite treatment:

**Inline style objects** (`style={{ padding: 16 }}`) — a raw literal is a
violation, same as anywhere else.

**Tailwind utility classes** — here the naive reading is wrong. `h-4`, `p-2`,
`text-sm` are *not* hardcoded values; they are references into Tailwind's scale,
which is the design system. Flagging them would report a correctly-tokenised
codebase as entirely broken.

What bypasses the scale is **arbitrary-value syntax**: `h-[17px]`,
`text-[#111827]`, `rounded-[7px]`, `duration-[350ms]`. Square brackets are how you
tell Tailwind "ignore the scale, use this exact value" — which is precisely the
thing a token audit exists to find. So:

    h-4          token reference    → not a finding
    h-[17px]     scale bypass       → finding

That mapping is the whole Tailwind story, and it is why this can be done with a
regex rather than a CSS pipeline.

## Why this was added

Portability validation against `calcom/cal.com` (142 `.tsx` files in
`packages/ui`) found 20 genuine inline-style findings — and also found that only
**2** of those files contained a raw hex colour and only **13** used an inline
`style={{}}` at all. cal.com is Tailwind-first, so the adapter was structurally
blind to most of its styling. 20 real findings was a true result and not the whole
picture, which is the kind of half-truth this suite treats as a defect.

## The two defects that used to be documented here as unfixed

Both are fixed, and both are worth knowing about because the fixes are load-bearing:

1. **`not_a_token`'s 40-character lookback caused false negatives.** In
   `{ color: tokens.colorOnSurface, marginTop: "12px" }` the `marginTop`
   violation was suppressed because `tokens.` happened to sit earlier on the
   line. The lookback is now bounded to the *current property assignment* — back
   to the nearest `,` `{` `;` or newline — so a token in a sibling property can no
   longer mask a real finding. A hex or px literal is never itself part of a token
   reference, so the only thing this test should ever suppress is a value that
   genuinely *is* the token.
2. **`padding: 16` (unitless) was missed.** React style objects treat a bare
   number as px, and usually omit the unit, so requiring `px` missed the common
   case. Unitless numbers now count, with zero excluded — `margin: 0` is
   idiomatic and not a tokenisation failure.

## Still not covered, stated rather than implied

- **A literal written in JSX *text* over-reports.** `<p>Set padding: 16px; in your
  config</p>` is flagged as a spacing violation. Distinguishing a JSX text node from
  code needs a parser, and the suite's stated preference is to over-report rather
  than risk silence — a noisy audit gets fixed, a silent one does not. Comments are
  excluded (cheap and unambiguous); JSX text is not.
- **`token_names()` returns None for any config built by code** — a spread, a
  `require()`, a function value, a `presets` entry. See `tailwind_theme.py`: the
  alternative is executing the project's JavaScript during an audit, which is not a
  trade worth a nicer result. None means "cannot tell", never "there are none".
"""
from __future__ import annotations

import re

from .base import AdapterContext, Check, CheckSet, ErrorHandlingSyntax

NAME = "tsx"
FILE_GLOBS = ("**/*.tsx", "**/*.ts", "**/*.jsx", "**/*.js")
GENERATED_SUFFIXES = (".d.ts",)

# ES module imports/re-exports, side-effect imports, require() and dynamic
# import(). Group 1 is the target. Used by the structural audits.
IMPORT_RE = re.compile(
    r"""(?:^\s*(?:import|export)\b[^'"`;]*?\bfrom\s*|^\s*import\s*|\brequire\s*\(\s*|\bimport\s*\(\s*)['"]([^'"]+)['"]""",
    re.M)

# --- inline style / plain-code literals ------------------------------------

# Hex colour literal in code or CSS-in-JS: #fff, #ffffff, #ffffffff.
# `(?<!&)`: an HTML numeric character reference (`&#8595;`, `&#8203;` in JSX
# text) is digits after `#` too, and was read as a 4-digit hex colour —
# measured on two held-out projects (issue #104).
COLOR_RE = re.compile(r"(?<!&)#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")

_LEN_PROPS = (r"padding|margin|gap|top|left|right|bottom|width|height"
              r"|fontSize|lineHeight|letterSpacing")
# A length in a style object: padding: 16px, marginTop: "12px", padding: 16.
# The unit is optional because React treats a bare number as px, and the `[1-9]`
# on the unitless branch keeps `margin: 0` — idiomatic, not a violation — out.
# The `(?<![-\w])` is not decoration: `\b` alone let `line-height: 21px` match as
# `height`, attributing a CSS declaration to the wrong property.
PX_RE = re.compile(rf"(?<![-\w])(?:{_LEN_PROPS})(?:Top|Right|Bottom|Left|X|Y)?\s*:\s*"
                   r"(?:['\"]\s*-?\d+px\s*['\"]|-?\d+px|-?[1-9]\d*(?![\d.%a-zA-Z]))")
# border-radius as a raw value rather than a token.
RADIUS_RE = re.compile(r"\bborderRadius\s*:\s*['\"]?(-?\d+)(?:px)?")
# A transition/animation duration literal.
DURATION_RE = re.compile(r"\b(?:transition|animation)(?:Duration)?\s*:\s*['\"][^'\"]*?(\d+m?s)")
CSS_VAR_RE = re.compile(r"var\(--")

# --- Tailwind arbitrary values --------------------------------------------
#
# Anything in square brackets bypasses the configured scale. The prefix decides
# which category it lands in, so a project can exempt colour without exempting
# spacing. An optional variant/negative prefix (`hover:`, `md:`, `-`) is allowed
# before the utility, and `!` for Tailwind's important modifier.

_TW_LEAD = r"(?:[a-z][a-z0-9-]*:)*!?-?"
# `\b` cannot be used to anchor these: it fails before Tailwind's `!` important
# modifier, so `!gap-[7px]` matched from `g` and the `!` was silently dropped from
# the snippet. A negative lookbehind is the anchor that works for both.
_TW_NB = r"(?<![\w-])"
# text-[#111827], bg-[#fff], border-[rgb(0,0,0)], fill-[hsl(...)], shadow-[...]
TW_COLOR_RE = re.compile(
    rf"{_TW_NB}{_TW_LEAD}(?:text|bg|border|ring|fill|stroke|shadow|from|via|to|outline|decoration|accent|caret|divide|placeholder)"
    r"-\[(?:#[0-9a-fA-F]{3,8}|(?:rgb|rgba|hsl|hsla|oklch|color-mix)\([^\]]*\))\]")
# w-[240px], p-[13px], gap-[7px], text-[15px], h-[calc(100%-2rem)]
TW_LEN_RE = re.compile(
    rf"{_TW_NB}{_TW_LEAD}(?:w|h|min-w|min-h|max-w|max-h|p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml"
    r"|gap|gap-x|gap-y|space-x|space-y|top|right|bottom|left|inset|text|leading|tracking|size|basis|indent)"
    r"-\[[^\]]*(?:px|rem|em|vh|vw|ch|%|calc\()[^\]]*\]")
# rounded-[7px], rounded-t-[3px]
TW_RADIUS_RE = re.compile(rf"{_TW_NB}{_TW_LEAD}rounded(?:-[a-z]{{1,2}})?-\[[^\]]+\]")
# duration-[350ms], delay-[1.5s], ease-[cubic-bezier(...)]
TW_DURATION_RE = re.compile(rf"{_TW_NB}{_TW_LEAD}(?:duration|delay|ease|animate)-\[[^\]]+\]")

# True when the cursor sits inside an unclosed Tailwind `-[…]` arbitrary value.
# Used to stop the generic hex check double-reporting `text-[#111827]`, which the
# tw_color check already owns. Two findings for one violation is noise, and noise
# is what gets audits switched off.
IN_TW_BRACKET_RE = re.compile(r"-\[[^\]\s]*$")

# A line that is a comment by the time the match starts. Cheap and only ever
# reduces false positives — a value written in a comment is documentation.
COMMENT_LINE_RE = re.compile(r"\s*(?://|\*|/\*)")

# --- CSS-in-JS template literals (styled-components, Emotion) --------------
#
# Inside a tagged template literal the syntax is CSS, not a JS object: properties
# are kebab-case and values end with `;`. The object-syntax checks above match
# camelCase followed by `:`, so they see almost nothing here — which is why this
# was listed as an under-reporting gap rather than a solved case.
#
# Scoped to template literals on purpose. Running kebab-case CSS patterns over a
# whole .tsx file would match plain prose and JSX text; a check that fires on
# comments is noise, and noise is what gets audits switched off.

_CSS_LEN_PROPS = (r"padding|margin|gap|top|left|right|bottom|width|height"
                  r"|font-size|line-height|letter-spacing|border-radius"
                  r"|min-width|min-height|max-width|max-height")
# padding: 16px;  margin-top: 1.5rem;  gap: 8px;
# `(?<![-\w$@])`, not `\b`: `\b` matches after `-`, so a custom-property
# DEFINITION (`--chat-max-width: 768px;`) read as `max-width` (issue #104, round 4).
# `scroll-margin-*` / `scrollbar-width`, which `\b` used to reach that way, are named.
CSS_LEN_RE = re.compile(rf"(?<![-\w$@])(?:scroll(?:bar)?-)?(?:{_CSS_LEN_PROPS})(?:-(?:top|right|bottom|left))?"
                        r"\s*:\s*-?\d*\.?[1-9]\d*(?:px|rem|em)\s*[;\n]")
# transition: opacity 250ms ease;  animation-duration: .3s;
CSS_DURATION_RE = re.compile(r"\b(?:transition|animation)(?:-duration|-delay)?"
                             r"\s*:[^;\n]*?(\d+\.?\d*m?s)")

# A tagged template literal: styled.div`…`, styled(Foo)`…`, css`…`, createGlobalStyle`…`
TAGGED_TEMPLATE_RE = re.compile(
    r"(?:styled(?:\.[A-Za-z][\w]*|\([^)]*\))(?:\.attrs\([^`]*?\))?|css|createGlobalStyle|keyframes)\s*`",
    re.M)

# Where a property assignment starts. Used to bound the "is this already a token"
# lookback so a sibling property cannot suppress a real finding.
_BOUNDARY = re.compile(r"[,{;\n]")


def _template_spans(source: str) -> list[tuple[int, int]]:
    """(start, end) of every tagged template literal body.

    Interpolations (`${...}`) are left inside the span: a hardcoded value next to
    an interpolated token is still hardcoded, and excising them would need a real
    parser to handle nested braces and backticks.
    """
    spans = []
    for m in TAGGED_TEMPLATE_RE.finditer(source):
        i = m.end()          # just past the opening backtick
        depth = 0
        while i < len(source):
            c = source[i]
            if c == "\\":
                i += 2
                continue
            if c == "$" and source[i:i + 2] == "${":
                depth += 1
                i += 2
                continue
            if c == "}" and depth:
                depth -= 1
            elif c == "`" and not depth:
                spans.append((m.end(), i))
                break
            i += 1
    return spans


def checks(ctx: AdapterContext) -> CheckSet:
    accessor = ctx.token_accessor or "tokens"

    def not_a_token(m, source):
        """True when this literal is a real violation.

        Scoped to the current property assignment, not a fixed character window.
        The old 40-character lookback let `color: tokens.x` on the same line
        suppress a sibling `marginTop: "12px"` — a false negative, which is the
        one outcome this suite refuses to ship quietly.
        """
        line_start = source.rfind("\n", 0, m.start()) + 1
        window = source[line_start:m.start()]
        if IN_TW_BRACKET_RE.search(window):
            return False  # tw_color owns this one; don't report it twice
        if COMMENT_LINE_RE.match(window):
            return False  # a literal written in a comment is not a violation
        spans = _spans_for(source)
        if any(a <= m.start() < b for a, b in spans):
            # CSS-in-JS. The property names overlap between the two syntaxes
            # (`padding` is `padding` either way), so this check does fire inside
            # template literals — but css_spacing owns them, and reporting one
            # violation under two kinds is the noise this yields to avoid.
            return False
        cut = 0
        for b in _BOUNDARY.finditer(window):
            cut = b.end()
        window = window[cut:]
        return accessor not in window and not CSS_VAR_RE.search(window)

    # Computed once per file rather than per match — _template_spans scans the
    # whole source, and a file with many styled components would otherwise rescan
    # it for every candidate.
    #
    # Keyed by the source object itself, held alive in the cache, never by
    # id(source): CPython reuses an id once a string is freed, so an id-keyed
    # cache handed a later file an earlier file's spans and silently dropped
    # its findings. Holding the reference makes id reuse impossible; one entry
    # bounds the memory, since checks walk one file at a time.
    span_cache: list = [None, None]

    def _spans_for(source):
        if span_cache[0] is not source:
            span_cache[0], span_cache[1] = source, _template_spans(source)
        return span_cache[1]

    def in_template(m, source):
        """True when the match sits inside a tagged template literal.

        Also honours a token reference or CSS custom property in the same
        declaration, so `padding: ${tokens.md};` and `gap: var(--gap);` do not fire.
        """
        spans = _spans_for(source)
        if not any(a <= m.start() < b for a, b in spans):
            return False
        line_start = source.rfind("\n", 0, m.start()) + 1
        window = source[line_start:m.start()]
        return accessor not in window and not CSS_VAR_RE.search(window)

    return CheckSet([
        # Inline styles and plain literals.
        Check("color", COLOR_RE, accept=not_a_token, category="color"),
        Check("spacing", PX_RE, accept=not_a_token),
        Check("border_radius", RADIUS_RE, accept=not_a_token),
        Check("duration", DURATION_RE, accept=not_a_token, tags=("motion",)),
        # Tailwind arbitrary values. No `accept` — a bracketed value is a scale
        # bypass by construction, so there is nothing to second-guess, and
        # defaulting to accept keeps a wrong adapter noisy rather than silent.
        Check("tw_color", TW_COLOR_RE, category="color", tags=("tailwind",)),
        Check("tw_spacing", TW_LEN_RE, tags=("tailwind",)),
        Check("tw_border_radius", TW_RADIUS_RE, tags=("tailwind",)),
        Check("tw_duration", TW_DURATION_RE, tags=("tailwind", "motion")),
        # CSS-in-JS. Only fires inside a tagged template literal, so kebab-case
        # patterns cannot match prose or JSX text elsewhere in the file.
        Check("css_spacing", CSS_LEN_RE, accept=in_template, tags=("css-in-js",)),
        Check("css_duration", CSS_DURATION_RE, accept=in_template,
              tags=("css-in-js", "motion")),
    ])


def token_names(ctx: AdapterContext):
    """Tokens this project defines, or None if they cannot be determined.

    Delegates to `tailwind_theme`, which reads a v4 `@theme` CSS block or a v3
    `tailwind.config.*` static object literal.

    **None still means "cannot tell", and is returned often.** A config whose theme
    is built by code — a spread, a `require()`, a function value, a preset — is not
    parsed, because the alternative is executing a project's JavaScript during an
    audit. That is not a trade worth a nicer result.

    The caller must not read None as an empty set: it uses this to check whether a
    project's configured token list has gone stale, and an empty set would report
    every configured token as nonexistent.
    """
    from pathlib import Path

    from . import tailwind_theme

    source = (ctx.profile.get("tokens", {}) or {}).get("source", {}) or {}
    return tailwind_theme.token_names(Path(str(ctx.repo)), source)


# --- audit_error_handling syntax ---------------------------------------------
# `catch (e)`, `catch (e: unknown)`, `.catch((e) => ...)`, `onError: (e) =>`.
# The sanctioned guard is `e instanceof AppError`; the leak is the whole error
# reaching a string - `${e}`, `String(e)`, `e.toString()`, `"..." + e`.
# No API_CONSISTENCY: its checks are Flutter-widget shaped (and its vocabulary
# check is Dart class syntax in the engine itself), so that audit refuses here
# rather than guess.
ERROR_HANDLING = ErrorHandlingSyntax(
    catch_var=re.compile(
        r"catch\s*\(\s*(\w+)(?:\s*:\s*\w+)?\s*\)"
        r"|\.catch\(\s*\(?\s*(\w+)(?:\s*:\s*\w+)?\s*\)?\s*=>"
        r"|onError\s*[:=]\s*\(?\s*(\w+)(?:\s*:\s*\w+)?\s*\)?\s*=>"),
    type_guard=lambda var, typ: re.compile(
        rf"\b{re.escape(var)}\s+instanceof\s+{re.escape(typ)}\b"),
    stringify=lambda var: re.compile(
        rf"\b{re.escape(var)}\.toString\(\)"
        rf"|\$\{{\s*{re.escape(var)}\s*\}}"
        rf"|\bString\(\s*{re.escape(var)}\s*\)"
        rf"|['\"`]\s*\+\s*{re.escape(var)}\b(?![\w.])"),
    type_test=lambda cls: re.compile(rf"\binstanceof\s+{re.escape(cls)}\b"),
    string_quotes=("'", '"', "`"),
    line_comment="//",
)


# --- focus order, semantics, component shape (unverified) ---------------------
# Read from markup tags by `_jsx`, never from whole-file regexes: `autoFocus?:
# boolean` in a props type is not an autofocus. See _jsx.py for what the tag
# scanner can and cannot see. Each hook takes the file's path because only
# markup-capable files are read (`.ts` holds no JSX).
from . import _jsx  # noqa: E402

FOCUS_ORDER_CAVEAT = (
    "Source-only: reads autoFocus / positive tabIndex from JSX tags. Cannot see "
    "CSS order, flex/grid reordering, absolute positioning, portals, or the "
    "rendered tab sequence.")


def focus_order_checks(ctx: AdapterContext) -> CheckSet:
    """No whole-file regex checks — every focus rule here is tag-scoped, and
    lives in `file_focus_findings`. Empty is not "clean": the audit runs both."""
    return CheckSet([])


MARKUP_SUFFIXES = _jsx.MARKUP_SUFFIXES


def file_focus_findings(rel: str, source: str) -> list[dict]:
    return _jsx.focus_findings(rel, source)


def file_semantics_findings(rel: str, source: str) -> list[dict]:
    return _jsx.semantics_findings_for(rel, source)


SEMANTICS_KINDS = _jsx.SEMANTICS_KINDS
SEMANTICS_CAVEAT = (
    "Source-only: reads intrinsic tags only — a <Component onClick> renders an "
    "element this scan cannot see, and a {...spread} may carry the role. Cannot "
    "see the rendered accessibility tree.")

# No WIDGET_SHAPE_GLOB / component-shape capability, by measurement: a reader
# of destructured React props (`function Foo({ a, b })`, non-exported only) was
# built and run on 2026-10-08 over three public React apps. 7 of the 11
# duplicated-shape clusters it produced were wrong — React components
# overwhelmingly take one id-like prop (`id`, `status`, `accountId`) and fetch
# the rest, so a shared prop set says nothing about a shared UI, and the
# near-match clustering chained unrelated components. 7 wrong already exceeds
# 20% of any 30-cluster sample, so promotion_candidates / reinvented_components
# keep refusing here rather than ship it.
