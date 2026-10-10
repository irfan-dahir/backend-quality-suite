"""Markup-tag and React-component reading shared by the `tsx` and `web` adapters.

**Maturity: unverified.** Not a parser. A small scanner that reads opening tags
(`<div onClick={...} role="button">`) out of JSX, Vue templates and Svelte
markup, plus one narrow reading of React function-component signatures. What it
cannot read it says so — it never falls back to guessing.

## What a "tag" is here

`<name` where `name` starts with a letter and the `<` is *not* preceded by an
identifier character (so `useState<boolean>(` and `Array<T>` are not tags), and
the name is followed by whitespace, `/` or `>` (so a TS generic arrow `<T,>(`
is not one either). The attribute list is read up to the first `>` at brace
depth zero outside a quoted string, so `onClick={() => a > b}` does not end the
tag early. Plain `.ts` / `.mts` / `.cts` files cannot contain JSX and are never
read for tags — that removes the generic-cast ambiguity (`<Foo>bar`) entirely.

## Measured once (2026-10-08), not proven

Tuned on excalidraw, outline, mastodon and chatwoot; then hand-judged on a
held-out sample from twenty (React), appwrite/console (Svelte) and hoppscotch
(Vue) that played no part in tuning:

  focus order   2 of 40 wrong (5%) - both a prop forwarded under another name
                (`autofocus={autofocus || undefined}`, a store value)
  semantics     6 of 40 wrong (15%) - 4 elements already keyboard-operable via
                `tabindex="0"` plus a key handler, missing only the role; one
                backdrop whose handler name did not say so; one editor mount

The bar for `proven` is a second held-out measurement.

## Known blind spots (each one under-reports; none over-reports silently)

- A spread (`{...props}`) may carry `role`, `tabIndex` or a handler. Tags with a
  spread are skipped by the rules that depend on an attribute being *absent*.
- Markup built outside JSX (`React.createElement`, `h()`, template strings,
  `innerHTML`) is invisible.
- A comment-looking `//` inside a string is only blanked when preceded by
  whitespace or punctuation other than `:`, so `http://` survives; a string
  containing ` // ` loses the rest of its line to blanking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..engine.scan import line_of, matching_delimiter_span

# Files that may hold markup. `.ts` is deliberately absent: it cannot contain
# JSX, and reading it for tags would turn every `<T>` cast into a "tag".
MARKUP_SUFFIXES = (".tsx", ".jsx", ".js", ".mjs", ".cjs", ".vue", ".svelte", ".html")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/|<!--.*?-->", re.S)
_LINE_COMMENT = re.compile(r"(^|[\s;{}(),])//[^\n]*", re.M)
# Not after an identifier/closer (a generic, a comparison), and not right after
# a quote or backtick: `'<p onclick="x">'` is HTML in a string, not markup.
_TAG_START = re.compile(r"(?<![\w$.)\]'\"`])<([A-Za-z][\w.:-]*)(?=[\s/>])")


def blank_comments(source: str) -> str:
    """Comments replaced with spaces, newlines kept, so offsets and lines hold."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    out = _BLOCK_COMMENT.sub(blank, source)
    return _LINE_COMMENT.sub(
        lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), out)


@dataclass(frozen=True)
class Tag:
    name: str
    start: int            # offset of `<`
    end: int              # offset just past the closing `>`
    attrs: dict           # attribute name -> raw value text ('' for a bare boolean)
    spread: bool          # a `{...x}` spread is present
    self_closing: bool


def _read_tag(code: str, m: re.Match) -> Tag | None:
    i = m.end()
    n = len(code)
    attrs: dict[str, str] = {}
    spread = False
    while i < n:
        c = code[i]
        if c.isspace():
            i += 1
            continue
        if c == ">":
            return Tag(m.group(1), m.start(), i + 1, attrs, spread, False)
        if c == "/" and code.startswith("/>", i):
            return Tag(m.group(1), m.start(), i + 2, attrs, spread, True)
        if c == "{":
            close = matching_delimiter_span(code, i, "{", "}")
            if code[i + 1:close - 1].strip().startswith("..."):
                spread = True
            i = close
            continue
        am = re.compile(r"[@:#\w$.|-]+").match(code, i)
        if not am:
            return None  # not something we can read as a tag; skip, never guess
        name = am.group(0)
        if name in ("v-bind", "v-on"):  # Vue's object spread: `v-bind="$attrs"`
            spread = True
        i = am.end()
        j = i
        while j < n and code[j] in " \t":
            j += 1
        if j < n and code[j] == "=":
            j += 1
            while j < n and code[j].isspace():
                j += 1
            if j >= n:
                return None
            q = code[j]
            if q in "\"'":
                k = code.find(q, j + 1)
                if k < 0:
                    return None
                attrs[name] = code[j + 1:k]
                i = k + 1
            elif q == "{":
                k = matching_delimiter_span(code, j, "{", "}")
                attrs[name] = code[j:k]
                i = k
            else:
                vm = re.compile(r"[^\s>]+").match(code, j)
                attrs[name] = vm.group(0) if vm else ""
                i = vm.end() if vm else j
        else:
            attrs[name] = ""
    return None


def tags(code: str) -> list[Tag]:
    """Every readable opening tag in already-comment-blanked `code`."""
    out = []
    for m in _TAG_START.finditer(code):
        t = _read_tag(code, m)
        if t is not None:
            out.append(t)
    return out


_TEST_PATH = re.compile(r"(?:^|/)(?:__tests__|__mocks__|tests?|spec|e2e|stories)/"
                        r"|\.(?:test|spec|stories|story|e2e)\.[cm]?[jt]sx?$")


def reads_markup(rel: str, source: str = "") -> bool:
    """A product file that may hold markup.

    Test, spec and story files are not product UI: an `autoFocus` in a test
    render or an `onclick` in a fixture string is not something a user meets.
    Decided by path *and* by content (web's `_non_product`, the same test the
    token checks use), so a test without the conventional name still drops out.
    """
    if not rel.endswith(MARKUP_SUFFIXES) or _TEST_PATH.search(rel):
        return False
    from .web import _non_product  # lazy: web imports tsx imports this module
    return not (source and _non_product(source))


# --- focus order --------------------------------------------------------------

_AUTOFOCUS_NAMES = {"autoFocus", "autofocus", ":autofocus", "v-bind:autofocus"}
_TABINDEX_NAMES = {"tabIndex", "tabindex", ":tabindex", "v-bind:tabindex"}
_LITERAL_INT = re.compile(r"^\{?\s*(-?\d+)\s*\}?$")
_FALSE = re.compile(r"^\{?\s*(false|null|undefined)\s*\}?$")
# A prop passed straight through: `{autoFocus}`, `{props.autoFocus}`, `{tabIndex}`.
_FORWARDED = re.compile(r"^\{\s*(?:(?:this\.)?props\.)?(?:autoFocus|autofocus|tabIndex|tabindex)\s*\}$")


def focus_findings(rel: str, source: str) -> list[dict]:
    """`autofocus_override` and `positive_tabindex`, read from tag attributes.

    Both are review prompts, the same standing as the Dart pair: an autofocus is
    often deliberate, and a positive tabindex is almost never right (it lifts the
    element out of document order — WCAG 2.2 SC 2.4.3, verify against the
    official text) but is reported, not gated. A tabindex whose value is an
    expression is not judged: only a literal integer > 0 fires.
    """
    if not reads_markup(rel, source):
        return []
    code = blank_comments(source)
    out = []
    for t in tags(code):
        for name, value in t.attrs.items():
            if _FORWARDED.match(value.strip()):
                continue  # `autoFocus={autoFocus}`: the caller decides; judged there
            if name in _AUTOFOCUS_NAMES and not _FALSE.match(value.strip()):
                out.append({"kind": "autofocus_override", "line": line_of(code, t.start),
                            "snippet": f"<{t.name} {name}> — takes focus on mount, ahead "
                                       "of document order; confirm it is meant to"})
            if name in _TABINDEX_NAMES:
                lit = _LITERAL_INT.match(value.strip())
                if lit and int(lit.group(1)) > 0:
                    out.append({"kind": "positive_tabindex", "line": line_of(code, t.start),
                                "snippet": f"<{t.name} {name}={lit.group(1)}> — a positive "
                                           "tabindex moves this ahead of every tabindex=0 "
                                           "element regardless of where it sits visually"})
    return out


# --- semantics ----------------------------------------------------------------

# Elements with no interactive role of their own. A click handler on one of
# these is reachable by mouse only, unless the author gives it a role (and, for
# the role to be honest, a tabindex and key handler — that second half is not
# judged here). `label` is absent on purpose: clicking a label is native.
STATIC_ELEMENTS = frozenset({
    "div", "span", "li", "p", "img", "section", "article", "td", "tr", "ul",
    "ol", "header", "footer", "main", "aside", "nav", "i", "b", "strong", "em",
    "small", "h1", "h2", "h3", "h4", "h5", "h6", "figure", "svg",
})
_CLICK_NAMES = {"onClick", "onclick", "@click", "v-on:click", "on:click"}
_ROLE_NAMES = {"role", ":role", "v-bind:role"}
_HIDDEN = re.compile(r"""^\{?\s*['"]?true['"]?\s*\}?$""")

SEMANTICS_KINDS = ("static_element_click_handler",)


# Handlers that are not a control at all. `@click.stop` with no expression and
# `onClick={e => e.stopPropagation()}` only stop a click bubbling to a parent.
_STOP_ONLY = re.compile(r"^\{?\s*(?:\(?\s*\w+\s*\)?\s*=>\s*)?\{?\s*\w+\.stopPropagation\(\)\s*;?\s*\}?\s*\}?$")
# A click on a backdrop/overlay that dismisses it. A pointer convenience whose
# keyboard path is the dialog's own Escape/close button, not a mouse-only
# control — reported nowhere rather than reported wrongly. This also hides a
# genuine mouse-only "close" div; that under-report is the stated price.
_DISMISS = re.compile(r"(?i)close|dismiss|backdrop|overlay|outside|background")
# A wrapper whose click focuses the text control inside it: the control is
# keyboard-reachable on its own, so the wrapper's click is a convenience.
_TEXT_CONTROL = re.compile(r"<(?:input|textarea|select)\b|contenteditable", re.I)


def _children(code: str, t: Tag) -> str:
    """Text from the end of `t` to its matching close tag (nesting-aware for the
    same element name), or '' for a self-closing tag."""
    if t.self_closing:
        return ""
    pat = re.compile(rf"<(/?){re.escape(t.name)}(?=[\s/>])")
    depth = 1
    for m in pat.finditer(code, t.end):
        if m.group(1):
            depth -= 1
            if depth == 0:
                return code[t.end:m.start()]
        else:
            close = code.find(">", m.end())
            if close > 0 and code[close - 1] != "/":
                depth += 1
    return code[t.end:]


def semantics_findings_for(rel: str, source: str) -> list[dict]:
    """`static_element_click_handler`: a click handler on an element with no
    interactive role, and no `role` attribute supplied.

    Lowercase intrinsic elements only — `<Card onClick>` is a component whose
    rendered element this scan cannot see, so it is never judged. Not reported,
    each an under-report stated rather than hidden:
      - a tag with a spread (`{...p}`, Vue `v-bind="$attrs"`) — may carry role
      - `aria-hidden` — deliberately outside the accessibility tree
      - a handler that only stops propagation — not a control
      - a dismiss handler (its expression names close/dismiss/backdrop/overlay/
        outside/background) — a backdrop click; the keyboard path is the dialog's
      - a wrapper around an input/textarea/select — click-to-focus convenience
    """
    if not reads_markup(rel, source):
        return []
    code = blank_comments(source)
    out = []
    for t in tags(code):
        if t.name not in STATIC_ELEMENTS or t.spread:
            continue
        handler = next((a for a in t.attrs if a in _CLICK_NAMES or a.startswith("@click.")
                        or a.startswith("v-on:click.") or a.startswith("on:click|")), None)
        if handler is None:
            continue
        value = t.attrs[handler].strip()
        if not value and (".stop" in handler or "stopPropagation" in handler):
            continue
        if _STOP_ONLY.match(value) or _DISMISS.search(value):
            continue
        if any(a in _ROLE_NAMES for a in t.attrs):
            continue
        if _HIDDEN.match(t.attrs.get("aria-hidden", "").strip() or "x"):
            continue
        if _TEXT_CONTROL.search(_children(code, t)):
            continue
        out.append({"kind": "static_element_click_handler", "line": line_of(code, t.start),
                    "severity": "should_fix",
                    "snippet": f"<{t.name} {handler}> with no role — a mouse-only control: "
                               "not focusable, not announced as interactive. Use a "
                               "<button>, or add role, tabIndex and a key handler"})
    return out
