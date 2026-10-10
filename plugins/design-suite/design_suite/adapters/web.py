"""Web adapter — everything `tsx` audits, plus stylesheets and single-file components.

**Maturity: unverified.** Measured once, on 2026-10-08, against five public
open-source web projects (docs/MEASUREMENT-2026-10-08-web-adapter.md): 2.8%
wrong pooled over 248 hand-judged findings after tuning, but 8.3% on the worst
single project, and the corpus that measured it is the corpus it was tuned on.
That is not the bar for `proven`; a held-out re-measurement is.

## Why this exists alongside `tsx`

`tsx` globs `.tsx/.ts/.jsx/.js`. A Vue or Svelte project keeps most of its styling
in `.vue` / `.svelte` files and `.css` / `.scss` sheets, so pointing `tsx` at one
swept the entry `main.js`, found nothing, and exited 0 — measured on a synthetic
Vue fixture with four planted hardcoded values, every one missed. That is the
governing failure, so `audit_tokens.py` now refuses when files of a stack the
adapter does not cover sit under the scan root; this adapter is what such a
project should name instead.

`tsx` is left exactly as it was. Widening its globs would have changed every
existing React consumer's findings overnight; a project opts into stylesheet
coverage by naming `web`.

## What is checked, by file kind

  script (`.tsx .ts .jsx .js .mjs .cjs`)
      every `tsx` check, unchanged — inline style objects, Tailwind arbitrary
      values, CSS-in-JS template literals.

  stylesheet (`.css .scss .sass .less`)
      the whole file is CSS: hex / rgb() / hsl() colours, px/rem/em lengths on
      spacing-and-size properties, border-radius, transition/animation durations.

  single-file component (`.vue .svelte`)
      the stylesheet checks inside `<style>` blocks and plain `style="…"`
      attributes; the `tsx` checks everywhere else (so `:style="{ padding: '13px' }"`
      and `<script>` code are still read as JS). Each region is owned by exactly
      one family, so one literal is never reported twice.

A value **defining** a token is not a violation: `--brand: #36f;`, `$gap: 8px;`,
`@gap: 8px;` are skipped. A value **reading** one never matches, because the
patterns only match literals (`padding: var(--gap)` has no number to match).

## Not a violation, by measurement (see the precision filters below)

Test / Storybook / minified files (decided from content); hairlines (|n| <= 1px,
except letter-spacing); 50%/100%/>=999px radii; percentage and viewport lengths;
`1em` sizes; `var()` fallbacks; multi-line custom-property definitions and JS
`'--x':` keys; SVG presentation-attribute colours; `{url, width, height}` image
metadata; Tailwind keyword brackets (`rounded-[inherit]`).

Added after the held-out measurement
(docs/MEASUREMENT-2026-10-08-web-adapter-held-out.md): story files by name
(`*.stories.*`, `*.story.*`) or by CSF content (`export default { title: … }`,
`storiesOf(`) without a Storybook import; `{width, height}` dimension records
(array rows with non-CSS keys, `x`/`y` rects, typed constructors — never a
style position, a unit string, or prop defaults); HTML numeric entities
(`&#8595;`); all-colour palette arrays; `mask*` alpha stops; custom-property
definitions in embedded `<style>` text and Tailwind `[--x:#hex]`; `var(…, #hex)`
colour fallbacks; durations that are all zero (`0ms`).

Added after the round-4 measurement
(docs/MEASUREMENT-2026-10-09-web-adapter-round-4.md), at FILE level through
`non_product_file`, every skip printed to stderr with its path and
re-includable via `exceptions.json` `scanSkipFiles.include`: a vendored copy
of a library (a leading `/*!` or `/**` banner carrying BOTH a licence line and
a semver `x.y.z` — a project's own `Copyright … Licensed …` header has no
release version, so it stays scanned); mock/fixture paths (`*.mock.*`,
`*.mocks.*`, `__mocks__/`, `__fixtures__/`, `fixtures/`); story files by name.
At match level: name→colour data maps (an object of >= 3 entries whose every
value is a colour literal and no key is a CSS colour property); the off-screen hide
hack (`left/top/right/bottom/text-indent: -9999px` or further, in a rule with
`position: absolute|fixed`); a colour passed to `.indexOf/.includes(` (a lookup,
not paint).

Added after the fresh held-out measurement
(docs/MEASUREMENT-2026-10-09-web-adapter-fresh-held-out.md): colours under a
theme `palette:` / `colorSchemes:` key (MUI `createTheme`); width/height passed
to an image-URL builder (`get…ImageUrl(id, {width})`) or a graph-layout API
(`setNode`, `addNode`), or in a row `.push({…})`ed with non-CSS keys; a
custom-property definition read as its suffix (`--x-max-width:` — `tsx` shares
this fix); a `* 1s` unit multiplier in `calc()`; canvas 2D paint
(`ctx.fillStyle =`, `addColorStop`); a colour assigned to a form control's
`.value` (a user-setting default).

## Not covered, stated rather than implied

- A palette file is still scanned; use `exceptions.json` (`themeFileToSkip`,
  `allowlistRegions` globs) for it.
- `defaultSize: { width, height }`-style data defaults (grafana canvas editor,
  round 4) are still reported: no rule found separates a data default from a
  component's own default size without naming one project's key.
- `non_product_file` (round 5) is applied by `audit_tokens.py` only. The
  per-check content tests still apply in every audit; the path rules do not.

- `.sass` indented syntax has no `;`; a declaration is ended by the newline,
  which the length pattern accepts, but nested-selector edge cases are untested.
- Vue `<template>` text and Svelte markup text that happens to contain
  `padding: 16px` over-reports, the same trade `tsx` makes for JSX text.
- No reduced-motion or token-usage capabilities. Those audits refuse (exit 2)
  for this adapter, as they do for `tsx`. Focus-order, semantics, error-handling
  and React component-shape capabilities are at the end of this file (unverified).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields, replace

from . import tsx
from .base import AdapterContext, Check, CheckSet

NAME = "web"
SCRIPT_SUFFIXES = (".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs")
SFC_SUFFIXES = (".vue", ".svelte")
STYLESHEET_SUFFIXES = (".css", ".scss", ".sass", ".less")
FILE_GLOBS = tuple(f"**/*{s}" for s in SCRIPT_SUFFIXES + SFC_SUFFIXES + STYLESHEET_SUFFIXES)
GENERATED_SUFFIXES = (".d.ts", ".min.css", ".min.js")

# Script imports (inside <script> blocks too — the regex is line-anchored, not
# block-aware, which is a superset) plus stylesheet @import / @use / @forward.
IMPORT_RE = re.compile(
    tsx.IMPORT_RE.pattern + r"""|^\s*@(?:import|use|forward)\s+(?:url\()?['"]([^'"]+)['"]""",
    re.M)

# --- where CSS lives inside a single-file component -------------------------

STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.S | re.I)
# Plain `style="…"` only. `:style=` (Vue) and `style={…}` (JSX/Svelte expression)
# are JS, which the tsx checks already read.
STYLE_ATTR_RE = re.compile(r"(?<![:\w-])style\s*=\s*(\"[^\"]*\"|'[^']*')")

# --- CSS-syntax patterns -----------------------------------------------------

_HEX = r"(?<!&)#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
CSS_COLOR_RE = re.compile(rf"{_HEX}|\b(?:rgba?|hsla?|oklch)\(\s*\d[^)]*\)")
_LEN_PROPS = (r"padding|margin|gap|row-gap|column-gap|top|left|right|bottom|inset"
              r"|width|height|min-width|min-height|max-width|max-height"
              r"|font-size|line-height|letter-spacing")
# `}` is a terminator too: `.box { margin: 13px }` is legal and common; so is a
# closing quote, for the last declaration in a `style="…"` attribute.
CSS_LEN_RE = re.compile(rf"(?<![-\w$@])(?:{_LEN_PROPS})(?:-(?:top|right|bottom|left|inline|block)(?:-(?:start|end))?)?"
                        r"\s*:\s*[^;{}\n]*?(?<![\w.-])-?\d*\.?[1-9]\d*(?:px|rem|em)\b[^;{}\n\"']*[;}\n\"']")
CSS_RADIUS_RE = re.compile(r"(?<![-\w$@])border(?:-(?:top|bottom)-(?:left|right))?-radius"
                           r"\s*:\s*[^;{}\n]*?(?<![\w.-])\d*\.?[1-9]\d*(?:px|rem|em|%)")
CSS_DURATION_RE = re.compile(r"(?<![-\w$@])(?:transition|animation)(?:-duration|-delay)?"
                             r"\s*:[^;{}\n]*?(?<![\w.-])(\d*\.?\d+m?s)\b")

# A declaration that DEFINES a variable: `--brand:`, `$gap:`, `@gap:`.
DEFINITION_RE = re.compile(r"(?:^|[;{\s])(?:--[\w-]+|\$[\w-]+|@[\w-]+)\s*:[^;{}]*$")
COMMENT_LINE_RE = re.compile(r"\s*(?://|\*|/\*)")


def _regions(source: str) -> list[tuple[int, int]]:
    """(start, end) of every CSS region inside a single-file component."""
    spans = [(m.start(1), m.end(1)) for m in STYLE_BLOCK_RE.finditer(source)]
    spans += [(m.start(1), m.end(1)) for m in STYLE_ATTR_RE.finditer(source)]
    return spans


# --- precision filters (measured: docs/MEASUREMENT-2026-10-08-web-adapter.md) --
#
# Each filter below removes one false-positive CLASS measured on real
# open-source projects. Every one is a statement about what the matched literal
# IS, never about how often it occurs, so none can hide a real hardcoded value
# of the kind the check exists for. Planted-violation tests pin both halves.

# A file that is not shipped UI: a test (fixtures are data, not styling), a
# Storybook story, or a minified bundle. Decided from content, because a check
# sees source text, not a path — and content is what makes a file a test.
_TEST_CALL_RE = re.compile(r"^\s*(?:describe|it|test)(?:\.\w+)?\s*\(", re.M)
_EXPECT_RE = re.compile(r"\bexpect\s*\(")
_DESCRIBE_RE = re.compile(r"^describe(?:\.\w+)?\s*\(\s*['\"`]", re.M)
# Component Story Format without a Storybook import: `export default { title: 'X' }`
# is the CSF default export (mantine's 115 `.story.tsx` files have no `Meta`).
# `storiesOf(` is the pre-CSF API. A product module never default-exports an
# object whose first key is a story title.
_STORY_RE = re.compile(r"""from\s+['"]@storybook/|\bsatisfies\s+Meta\b|:\s*Meta<"""
                       r"""|^export\s+default\s*\{\s*title\s*:\s*['"`]|\bstoriesOf\s*\(""", re.M)
# The filename convention every Storybook config globs for (`*.stories.*`,
# `*.story.*`). Checked by path, so a story file is excluded even when its
# content carries no signal at all.
STORY_NAME_RE = re.compile(r"\.(?:stories|story)\.(?:[cm]?[jt]sx?|mdx|svelte|vue)$")
# Shipped code never imports a test runner or testing library; a test helper
# module (fixtures, factories) does, even though it has no `expect(` itself.
_TEST_IMPORT_RE = re.compile(
    r"""(?:from\s+|require\(\s*)['"](?:vitest|jest|@jest/[\w-]+|@testing-library/[\w-]+|@playwright/test|cypress)['"]""")


def _non_product(source: str) -> bool:
    if _DESCRIBE_RE.search(source):
        return True  # suites with custom assertion helpers have no `expect(`
    if _TEST_CALL_RE.search(source) and _EXPECT_RE.search(source):
        return True
    if _STORY_RE.search(source) or _TEST_IMPORT_RE.search(source):
        return True
    # Minified: long and almost no newlines. Real authored CSS/JS averages well
    # under 100 characters a line.
    return len(source) > 5000 and len(source) / (source.count("\n") + 1) > 500


# --- file-level non-product classification (round-4 measurement, #104) ------
# Leading comments only (after an optional BOM / `@charset`): a library banner
# may follow a short header comment (AdGuardHome's Tabler.css).
_LEAD_RE = re.compile(r"\A\ufeff?\s*(?:@charset[^;]*;\s*)?")
_COMMENT_RE = re.compile(r"/\*([!*]?)(.*?)\*/\s*", re.S)
_LICENCE_RE = re.compile(r"(?i)\bcopyright\b|\blicen[sc]ed\b|@licen[sc]e\b|\(c\)|\bMIT\b")
_SEMVER_RE = re.compile(r"(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])")
_MOCK_PATH_RE = re.compile(r"(?:^|/)(?:__mocks__|__fixtures__|fixtures)/|\.mocks?\.[^/]+$")


def non_product_file(rel: str, source: str):
    """A reason string when the whole file is not authored product UI, else None.

    Applied by the engine at file level, which prints every skipped path; a
    project re-includes one with `exceptions.json` `scanSkipFiles.include`.
    """
    posix = rel.replace("\\", "/")
    if STORY_NAME_RE.search(posix):
        return "story"
    if _MOCK_PATH_RE.search(posix):
        return "mock/fixture"
    head = source[:6000]
    pos = _LEAD_RE.match(head).end()
    while (c := _COMMENT_RE.match(head, pos)):
        if c.group(1) and _LICENCE_RE.search(c.group(2)) and _SEMVER_RE.search(c.group(2)):
            return "vendored (licence+version banner)"
        pos = c.end()
    return None


def _strip_vars(value: str) -> str:
    """`value` with every `var(...)` removed, nested fallbacks included.

    `width: var(--icon-size, 1rem)` READS a token; the `1rem` only applies when
    the token is undefined. Reporting it would flag the token read itself.
    """
    out, i = [], 0
    while True:
        j = value.find("var(", i)
        if j < 0:
            out.append(value[i:])
            return "".join(out)
        out.append(value[i:j])
        depth, k = 0, j + 3
        while k < len(value):
            if value[k] == "(":
                depth += 1
            elif value[k] == ")":
                depth -= 1
                if not depth:
                    break
            k += 1
        i = k + 1


_NUM_UNIT_RE = re.compile(r"(?<![\w.#-])-?(\d*\.?\d+)(px|rem|em|%|vh|vw|ch)?(?![\w%])")
_TRACKING_PROP_RE = re.compile(r"letter-?spacing|tracking", re.I)
_SIZE_PROP_RE = re.compile(r"(?:min-|max-)?(?:width|height)|(?:min|max)?(?:Width|Height)|size|font-size|fontSize")


def _literal_is_design_value(value: str, *, unit_required: bool, radius: bool = False,
                             prop: str = "") -> bool:
    """True when `value` (a declaration's right-hand side) holds at least one
    literal a design token should own.

    Not a design value, by construction rather than by frequency:
      * 0 and hairlines (|n| <= 1px): a border-width nudge or a separator, never
        a spacing step;
      * percentages on lengths (`max-w-[85%]`) — a proportion, not a scale step;
        on a radius only 50% / 100% (a circle), and >= 999px (a pill);
      * `1em` as a width/height/font-size — "the size of the text": the icon
        idiom, or a font-size reset that changes nothing;
      * anything inside `var(...)`, i.e. a token fallback.
    """
    value = _strip_vars(value).strip().strip("'\"`").strip()
    if prop and _SIZE_PROP_RE.fullmatch(prop) and value == "1em":
        return False
    for m in _NUM_UNIT_RE.finditer(value):
        n, unit = float(m.group(1)), m.group(2)
        if unit is None and unit_required:
            continue  # a calc() multiplier, not a length
        if unit == "%":
            if radius and n not in (50.0, 100.0):
                return True
            continue
        if unit in (None, "px") and n <= 1 and not _TRACKING_PROP_RE.search(prop):
            continue  # hairline; but 0.4px of letter-spacing IS a type value
        if radius and unit == "px" and n >= 999:
            continue
        if unit in ("vh", "vw"):
            continue  # viewport proportion, same as %
        if n == 0:
            continue
        return True
    return False


def _declaration(m, source: str, js: bool) -> tuple[str, str]:
    """(property, value) of the declaration a property-anchored match starts."""
    text = m.group(0)
    colon = text.find(":")
    if colon < 0:
        return "", text
    prop = text[:colon].strip()
    start = m.start() + colon + 1
    stops = ",}\n" if js else ";}\n\"'"
    end = start
    depth = 0
    while end < len(source):
        c = source[end]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c in stops and depth <= 0:
            break
        end += 1
    return prop, source[start:end]


# A JS object key that DEFINES a CSS custom property: `{'--dark': '#000'}`.
_JS_VAR_DEF_RE = re.compile(r"""['"]--[\w-]+['"]\s*:\s*['"`]?\s*$""")
# A colour that is SVG artwork, not UI chrome: a presentation attribute in
# markup, or set on an element by script. Brand logos and illustration paths
# live here; they belong to the asset pipeline, not to colour tokens.
_SVG_ATTR_RE = re.compile(
    r"""(?:\b(?:fill|stroke|stop-?[cC]olor|flood-?[cC]olor|lighting-?[cC]olor)\s*=\s*\{?\s*\\?["'`]?"""
    r"""|setAttribute(?:NS)?\(\s*(?:null\s*,\s*)?["'](?:fill|stroke|stop-color)["']\s*,\s*["'`])$""")
# An object literal that is image metadata: `{url, width: 1200, height: 630}`.
_IMAGE_META_RE = re.compile(r"\b(?:url|src)\s*:")

# --- `{width, height}` data objects (held-out measurement, issue #104) --------
#
# A JS object whose only length keys are `width`/`height` is a *dimension
# record* — a video codec ladder row, a crop region, an aspect-ratio option —
# unless it sits where a style object goes. What it IS is decided by its keys
# and its position, never by how often the shape occurs:
#   * any other CSS-property key (`padding`, `color`, `top`, …) makes it a style
#     object, and it is reported as before;
#   * a style position (`style={{`, `style: {`, `sx={{`, `:style="{`, `css({`,
#     `StyleSheet.create(`, a `…style(s)` variable) makes it a style object.
# Not covered: `const box = { width: 200, height: 100 }` later passed to
# `style={box}` is read as data. Stated, not hidden.
_JS_KEY_RE = re.compile(r"""(?:^|[{,])\s*['"]?([A-Za-z_$][\w$-]*)['"]?\s*:""")
_CSS_KEY_RE = re.compile(
    r"(?:min|max)?(?:[wW]idth|[hH]eight)|padding\w*|margin\w*|gap|rowGap|columnGap|inset\w*"
    r"|top|left|right|bottom|font\w*|line\w*|letter\w*|color|background\w*|border\w*"
    r"|outline\w*|boxShadow|opacity|zIndex|display|position|flex\w*|grid\w*|transform\w*"
    r"|transition\w*|animation\w*|overflow\w*|cursor|align\w*|justify\w*|textAlign|whiteSpace"
    r"|[a-z]+-[a-z-]+")
_DIM_KEYS = {"width", "height"}
_STYLE_POSITION_RE = re.compile(
    r"""(?:\bstyle\s*=\s*\{|\bsx\s*=\s*\{|:style\s*=\s*["']|\bstyles?\s*:|\bcss\s*\(|\.create\s*\("""
    r"""|\b\w*[sS]tyles?\s*(?::[^=]*)?=)\s*\{?\s*$""")


def _enclosing_object(source: str, pos: int, limit: int = 2000) -> tuple[int, int]:
    """(open, close) of the innermost `{…}` around `pos`, or (-1, -1)."""
    depth, i = 0, pos
    while i > 0 and pos - i < limit:
        i -= 1
        c = source[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if not depth:
                break
            depth -= 1
    else:
        return -1, -1
    depth, j = 0, pos
    while j < len(source) and j - pos < limit:
        c = source[j]
        if c == "{":
            depth += 1
        elif c == "}":
            if not depth:
                return i, j
            depth -= 1
        j += 1
    return -1, -1


def _dimension_record(m, source: str) -> bool:
    """True when the matched `width`/`height` belongs to a data object."""
    a, b = _enclosing_object(source, m.start())
    if a < 0:
        return False
    body = source[a + 1:b]
    # keys at this object's own depth only: blank out nested {…} / […] / (…)
    flat, depth = [], 0
    for c in body:
        if c in "{[(":
            depth += 1
        if not depth:
            flat.append(c)
        if c in "}])":
            depth -= 1
    # a key whose value is an object (`position: { x, y }`) is not a CSS property
    keys = {k for k in _JS_KEY_RE.findall("".join(flat))}
    keys -= set(re.findall(r"""['"]?([A-Za-z_$][\w$-]*)['"]?\s*:\s*(?=\{|$)""", _nested_keys(body)))
    if not keys & _DIM_KEYS:
        return False
    if any(_CSS_KEY_RE.fullmatch(k) and k not in _DIM_KEYS for k in keys):
        return False
    if re.search(r"""\b(?:width|height)\s*:\s*['"`]""", "".join(flat)):
        return False  # `width: "40px"` is a CSS value even in a config object
    before = source[max(0, a - 80):a + 1]
    if _STYLE_POSITION_RE.search(before):
        return False
    # Positive evidence it is a record, not a component's size: a row in an
    # array of objects with non-CSS sibling keys (a codec ladder, a list of
    # aspect-ratio options), a geometry rect (`x`/`y` siblings), or a typed
    # constructor (`$state<Dims>({`). Prop defaults —
    # `defaultProps = { width: 239 }`, `withDefaults(…, { withOk: false, width: 400 })`
    # — have none of these and stay reported.
    if {"x", "y"} <= keys:
        return True
    if re.search(r"<[\w.\[\]]+>\s*\(\s*\{$", before):
        return True
    # An argument to an image-URL builder or a graph-layout API: the size is a
    # request parameter or a layout-engine input, never applied as CSS.
    if _DATA_CALL_RE.search(before):
        return True
    if bool(keys - _DIM_KEYS) and re.search(r"\.(?:push|unshift)\s*\(\s*\{$", before):
        return True  # a row appended to an array, same as an array-literal row
    return bool(keys - _DIM_KEYS) and _array_element(source, a)


_DATA_CALL_RE = re.compile(
    r"""(?:\b\w*(?:Image\w*Url|ImageUrl|ImageSrc|ThumbnailUrl)|\.(?:setNode|addNode))\s*\([^()]*\{$""")


def _nested_keys(body: str) -> str:
    """`body` with nested object bodies blanked but their opening `{` kept, so
    `key: {` is visible as an object-valued key."""
    out, depth = [], 0
    for c in body:
        if c in "{[(":
            if not depth:
                out.append(c)
            depth += 1
        elif c in "}])":
            depth -= 1
        elif not depth:
            out.append(c)
    return "".join(out)


def _array_element(source: str, open_brace: int) -> bool:
    """True when the `{` at `open_brace` is an element of an array literal."""
    depth, i = 0, open_brace
    while i > 0 and open_brace - i < 4000:
        i -= 1
        c = source[i]
        if c in ")]}":
            depth += 1
        elif c in "([{":
            if not depth:
                return c == "["
            depth -= 1
    return False


# --- colour literals that are not UI colour usages (issue #104 held-out) ------

# Inside a custom-property definition: `--brand: #36f` in an embedded
# `<style>` / template string, or a Tailwind arbitrary property `[--brand:#36f]`.
_CSS_VAR_DEF_BEFORE_RE = re.compile(r"(?:^|[\s;{\[])--[\w-]+\s*:\s*$")
# A palette: an array whose every element is a colour literal (>= 3 of them),
# e.g. a 10-shade scale. A definition of the scale, not a use of it.
_PALETTE_ARRAY_RE = re.compile(
    r"""\[\s*(?:['"`](?:#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?|oklch)\([^)'"`]*\))['"`]\s*,\s*){2,}"""
    r"""['"`](?:#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?|oklch)\([^)'"`]*\))['"`]\s*,?\s*\]""")
# A mask uses only the alpha channel; `rgba(0,0,0,.3)` there is an opacity stop.
_MASK_PROP_RE = re.compile(r"(?:^|[\s;{\"'])(?:-webkit-)?mask(?:-image|-border(?:-source)?)?\s*:[^;{}]*$")


def _unclosed_var(text: str) -> bool:
    """True when `text` ends inside an open `var(` — i.e. a token fallback."""
    i = text.rfind("var(")
    while i >= 0:
        depth = 0
        for c in text[i + 3:]:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if not depth:
                    break  # this var( closed before the literal
        else:
            return True
        i = text.rfind("var(", 0, i)
    return False


def _in_palette_array(m, source: str) -> bool:
    a = source.rfind("[", max(0, m.start() - 400), m.start())
    if a < 0 or "]" in source[a:m.start()]:
        return False
    pm = _PALETTE_ARRAY_RE.match(source, a)
    return bool(pm) and pm.end() > m.end()


def _object_around(m, source: str) -> str:
    a = source.rfind("{", max(0, m.start() - 300), m.start())
    b = source.find("}", m.end(), m.end() + 300)
    return source[a:b] if a >= 0 and b >= 0 else ""


# Canvas 2D paint state: `ctx.fillStyle = '#fff'`. Pixels drawn into a bitmap
# (a chart, a document preview), the canvas analogue of an SVG `fill` — artwork,
# not UI chrome. `el.style.color = …` is not this and stays reported.
_CANVAS_PAINT_RE = re.compile(
    r"""(?:\.(?:fillStyle|strokeStyle|shadowColor)\s*=(?!=)[^;\n]*|\.addColorStop\(\s*[\w.]+\s*,\s*)['"`]$""")
# A form control's value: `input.value = setting || '#ffffff'`. The literal is
# a user-setting default (data the user edits), not a colour the UI paints.
_FORM_VALUE_RE = re.compile(r"""\.(?:value|defaultValue)\s*=(?!=)[^;\n]*['"`]$""")
# Object keys under which a theme library DEFINES its colour tokens
# (MUI `createTheme({ palette })`, `colorSchemes`). Reading them
# (`theme.palette.primary.main`) never contains a literal.
_PALETTE_KEYS = {"palette", "colorSchemes"}


def _under_theme_palette(m, source: str) -> bool:
    """True when the colour sits (at any depth) inside a `palette: {…}` object."""
    pos = m.start()
    for _ in range(8):
        a, _b = _enclosing_object(source, pos)
        if a < 0:
            return False
        k = re.search(r"""['"]?([A-Za-z_$][\w$]*)['"]?\s*:\s*$""", source[max(0, a - 80):a])
        if k and k.group(1) in _PALETTE_KEYS:
            return True
        pos = a
    return False


# `* 1s` / `1s *` / `* 1000ms`: a unit conversion factor in calc(), not a duration.
_UNIT_MULTIPLIER_RE = re.compile(r"\*\s*(?:1s|1000ms)\b|(?<![\w.])(?:1s|1000ms)\s*\*")

_TW_BRACKET_RE = re.compile(r"-\[([^\]]*)\]$")
_TW_KEYWORDS = {"inherit", "initial", "unset", "revert", "auto", "none",
                "transparent", "currentcolor"}


_COLOR_LIT = r"""['"`](?:#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?)\([^)'"`]*\))['"`]"""
_COLOR_MAP_ENTRY_RE = re.compile(r"""\s*(?:"([^"\n]+)"|'([^'\n]+)'|([\w$]+))\s*:\s*""" + _COLOR_LIT + r"""\s*""")
# Keys that make an all-colour object a STYLE object (a CSS colour property).
_COLOR_PROP_KEY_RE = re.compile(
    r"(?i)(?:-webkit-)?(?:color|background[\w-]*|border[\w-]*|outline[\w-]*|fill|stroke"
    r"|box-?shadow|text-?shadow|caret[\w-]*|accent[\w-]*|column-?rule[\w-]*|text-?decoration[\w-]*)")
# A colour as a lookup key, not paint: `colors.indexOf('#E24D42')`. A `==`
# comparison stays reported (an earlier test pins it).
_COLOR_LOOKUP_RE = re.compile(r"""\.(?:indexOf|lastIndexOf|includes)\(\s*['"`]$""")
_OFFSCREEN_PROPS = {"left", "top", "right", "bottom", "text-indent", "textIndent"}
_OFFSCREEN_VALUE_RE = re.compile(r"""\s*['"`]?-(\d{4,})(?:px)?['"`]?\s*,?\s*$""")
_ABS_POS_RE = re.compile(r"""\bposition\s*:\s*['"`]?(?:absolute|fixed)\b""")


def _in_color_map(m, source: str) -> bool:
    """True when the colour is a value in a name→colour data map: an object of
    >= 3 entries, every value a colour literal, no key a CSS colour property."""
    a, b = _enclosing_object(source, m.start(), limit=50000)  # maps run long
    if a < 0:
        return False
    entries = [e for e in source[a + 1:b].split(",") if e.strip()]
    if len(entries) < 3:
        return False
    keys = []
    for e in entries:
        em = _COLOR_MAP_ENTRY_RE.fullmatch(re.sub(r"//[^\n]*", "", e))
        if not em:
            return False
        keys.append(em.group(1) or em.group(2) or em.group(3))
    if any(_COLOR_PROP_KEY_RE.fullmatch(k) for k in keys):
        return False
    return not _STYLE_POSITION_RE.search(source[max(0, a - 80):a + 1])


def _offscreen_hack(prop, value: str, m, source: str) -> bool:
    if prop not in _OFFSCREEN_PROPS:
        return False
    v = _OFFSCREEN_VALUE_RE.fullmatch(value)
    if not v or int(v.group(1)) < 9999:
        return False
    # the declaration block: a `{…}` rule / object, or an inline `style="…"`
    start, end = m.start(), m.end()
    a = max(source.rfind(ch, max(0, start - 400), start) for ch in "{\"'`")
    ends = [i for i in (source.find(ch, end, end + 400) for ch in "}\"'`") if i >= 0]
    return a >= 0 and bool(ends) and bool(_ABS_POS_RE.search(source[a:min(ends)]))


def _precise(kind: str, m, source: str) -> bool:
    """False when this match is one of the measured non-violation classes."""
    if kind in ("color", "css_color"):
        before = source[max(0, m.start() - 120):m.start()]
        if _SVG_ATTR_RE.search(before):
            return False
        decl = before.rsplit("\n", 1)[-1]
        if _CSS_VAR_DEF_BEFORE_RE.search(decl.rsplit(";", 1)[-1].rsplit("{", 1)[-1]):
            return False  # defines a custom property
        if _unclosed_var(source[max(0, m.start() - 300):m.start()]):
            return False  # `var(--x, #fff)`: a token read with a fallback
        if _MASK_PROP_RE.search(source[max(0, m.start() - 300):m.start()]):
            return False
        if _in_palette_array(m, source):
            return False
        line_before = before.rsplit("\n", 1)[-1]
        if _CANVAS_PAINT_RE.search(line_before) or _FORM_VALUE_RE.search(line_before):
            return False
        if _COLOR_LOOKUP_RE.search(line_before):
            return False
        if kind == "color" and _in_color_map(m, source):
            return False
        if kind == "color" and _under_theme_palette(m, source):
            return False
        if kind == "color" and _JS_VAR_DEF_RE.search(before.rsplit("\n", 1)[-1]
                                                     .rsplit(",", 1)[-1].rsplit("{", 1)[-1]):
            return False
        return True
    if kind in ("tw_spacing", "tw_border_radius"):
        b = _TW_BRACKET_RE.search(m.group(0))
        content = b.group(1) if b else ""
        if content.strip().lower() in _TW_KEYWORDS:
            return False
        return _literal_is_design_value(content.replace("_", " "), unit_required=True,
                                        radius=kind == "tw_border_radius")
    if kind in ("css_spacing", "css_border_radius"):
        prop, value = _declaration(m, source, js=False)
        if kind == "css_spacing" and _offscreen_hack(prop, value, m, source):
            return False
        return _literal_is_design_value(value, unit_required=True,
                                        radius=kind == "css_border_radius", prop=prop)
    if kind in ("spacing", "border_radius"):
        if kind == "spacing" and _IMAGE_META_RE.search(_object_around(m, source)):
            return False
        if kind == "spacing" and _dimension_record(m, source):
            return False
        prop, value = _declaration(m, source, js=True)
        if kind == "spacing" and _offscreen_hack(prop, value, m, source):
            return False
        return _literal_is_design_value(value, unit_required=False,
                                        radius=kind == "border_radius", prop=prop)
    if kind in ("css_duration", "duration", "tw_duration"):
        # `0ms` / `0s` is "no animation" — a reset, like a 0 length. Reported
        # when ANY duration in the declaration is non-zero.
        text = m.group(0) if kind == "tw_duration" else _declaration(m, source, js=kind == "duration")[1]
        durs = re.findall(r"(?<![\w.])(\d*\.?\d+)m?s\b", text)
        if durs and kind == "css_duration":
            # `calc(${token} * 1s)` converts a unitless token to seconds; the
            # `1s` is a unit, not a duration. Any other duration still counts.
            text = _UNIT_MULTIPLIER_RE.sub(" ", text)
            if not re.findall(r"(?<![\w.])(\d*\.?\d+)m?s\b", text):
                return False
            durs = re.findall(r"(?<![\w.])(\d*\.?\d+)m?s\b", text)
        return not durs or any(float(d) for d in durs)
    return True


def checks(ctx: AdapterContext) -> CheckSet:
    # One slot, compared by identity. Keying on `id(source)` alone was a real
    # bug: once a file's text is freed, CPython reuses its id for a later file,
    # which then inherited the earlier file's <style> spans and silently lost
    # findings (measured: 4 of 10 planted-equivalent values in one .vue file).
    region_cache: list = [None, ()]

    def in_css_region(m, source) -> bool:
        if region_cache[0] is not source:
            region_cache[:] = [source, _regions(source)]
        return any(a <= m.start() < b for a, b in region_cache[1])

    def css_violation(m, source) -> bool:
        line_start = max(source.rfind("\n", 0, m.start()),
                         source.rfind(";", 0, m.start()),
                         source.rfind("{", 0, m.start())) + 1
        window = source[line_start:m.start()]
        if COMMENT_LINE_RE.match(source[source.rfind("\n", 0, m.start()) + 1:m.start()]):
            return False
        if source.rfind("/*", 0, m.start()) > source.rfind("*/", 0, m.start()):
            return False  # inside a multi-line comment, e.g. an issue ref `(#5399)`
        # The colour pattern matches bare values, so it needs the definition test;
        # the property patterns start at the property name, so `--gap: 8px`
        # cannot reach them (the lookbehind rejects the leading `-`).
        # A definition may span lines (`--shadow: 0 1px #000,\n 0 2px #111;`),
        # so the definition test also looks back to the declaration's start.
        decl_start = max(source.rfind(";", 0, m.start()), source.rfind("{", 0, m.start()),
                         source.rfind("}", 0, m.start())) + 1
        return not DEFINITION_RE.search(source[max(0, line_start - 1):m.start()]) \
            and not DEFINITION_RE.search(source[max(0, decl_start - 1):m.start()]) \
            and "var(--" not in window

    def in_sfc_style(m, source) -> bool:
        return in_css_region(m, source) and css_violation(m, source)

    def script_side(check: Check) -> Check:
        """A tsx check, made to stand aside inside an SFC's CSS regions."""
        def accept(m, source, _orig=check):
            return not in_css_region(m, source) and _orig.fires(m, source)
        return replace(check, accept=accept)

    script = list(tsx.checks(ctx))
    out = [replace(c, suffixes=SCRIPT_SUFFIXES) for c in script]
    out += [replace(script_side(c), suffixes=SFC_SUFFIXES) for c in script]

    css = [
        ("css_color", CSS_COLOR_RE, "color", ()),
        ("css_spacing", CSS_LEN_RE, None, ()),
        ("css_border_radius", CSS_RADIUS_RE, None, ()),
        ("css_duration", CSS_DURATION_RE, None, ("motion",)),
    ]
    for kind, pattern, category, tags in css:
        out.append(Check(kind, pattern, accept=css_violation, category=category,
                         tags=("stylesheet",) + tags, suffixes=STYLESHEET_SUFFIXES))
        out.append(Check(kind, pattern, accept=in_sfc_style, category=category,
                         tags=("sfc",) + tags, suffixes=SFC_SUFFIXES))
    return CheckSet([_with_precision(c) for c in out])


@dataclass(frozen=True)
class _WebCheck(Check):
    """A Check that also refuses story files by name (`*.stories.*`, `*.story.*`)."""

    def applies_to(self, rel: str) -> bool:
        return not STORY_NAME_RE.search(rel) and super().applies_to(rel)


def _with_precision(check: Check) -> Check:
    """`check`, additionally refusing non-product files and the measured
    non-violation literal classes. Composes with, never replaces, the check's
    own accept — so every original exclusion still holds."""
    def accept(m, source, _orig=check):
        if not _orig.fires(m, source):
            return False
        if _LAST_FILE[0] is not source:  # one slot: the engine scans file by file
            _LAST_FILE[:] = [source, _non_product(source)]
        return not _LAST_FILE[1] and _precise(_orig.kind, m, source)
    return _WebCheck(**{f.name: getattr(check, f.name) for f in fields(Check)} | {"accept": accept})


_LAST_FILE: list = [None, False]


def token_names(ctx: AdapterContext):
    """Same answer as `tsx` — a Tailwind theme, or None for "cannot tell"."""
    return tsx.token_names(ctx)


# --- capabilities beyond tokens (unverified) -----------------------------------
# Additive only; none of the token checks above are touched. The tag-scoped
# readers in `_jsx` already understand Vue (`@click`, `:tabindex`) and Svelte
# (`on:click`) attribute spellings, and skip stylesheets by suffix.
from . import _jsx  # noqa: E402

# `catch (e)` / `.catch(e =>` reads the same in a `.vue` / `.svelte` <script>
# block as in a `.ts` file; a stylesheet never matches `catch`.
ERROR_HANDLING = tsx.ERROR_HANDLING
ERROR_HANDLING_SUFFIXES = SCRIPT_SUFFIXES + SFC_SUFFIXES
FOCUS_ORDER_CAVEAT = (
    "Source-only: reads autofocus / positive tabindex from JSX, Vue and Svelte "
    "tags. Cannot see CSS order, flex/grid reordering, absolute positioning, "
    "portals, or the rendered tab sequence.")
focus_order_checks = tsx.focus_order_checks
MARKUP_SUFFIXES = tsx.MARKUP_SUFFIXES
file_focus_findings = tsx.file_focus_findings
file_semantics_findings = tsx.file_semantics_findings
SEMANTICS_KINDS = tsx.SEMANTICS_KINDS
SEMANTICS_CAVEAT = tsx.SEMANTICS_CAVEAT
