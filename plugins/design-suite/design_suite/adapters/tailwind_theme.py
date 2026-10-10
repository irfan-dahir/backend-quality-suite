"""Enumerate a Tailwind project's design tokens, or admit it cannot.

`tsx.token_names()` returned None unconditionally before this existed. None is the
honest answer when a language has no way to enumerate tokens, but for Tailwind it
was really "nobody implemented it" — and the two are indistinguishable to a caller,
which is the failure this suite keeps guarding against.

Two config formats, because Tailwind changed shape at v4:

**v4 — CSS.** Tokens are custom properties in an `@theme` block:

    @theme {
      --color-brand-500: #6366f1;
      --spacing-gutter: 1.5rem;
    }

Reliably parseable. `--color-brand-500` is referenced as `text-brand-500`, so the
namespace prefix is stripped to recover the class-facing name.

**v3 — JavaScript.** `tailwind.config.{js,ts,cjs,mjs}` exporting a `theme` object,
usually under `extend`. A JS object literal of string values is parseable; a real JS
program is not, and this module does not pretend otherwise (see below).

## When this returns None, and why that matters more than the happy path

None means **cannot tell**. It must never be an empty set, because the caller uses
`token_names()` to check whether the project's configured token list is stale — and
an empty set would report every configured token as nonexistent.

So None is returned for:

  * no config file found
  * a `theme` block containing a spread (`...colors`), a `require()`, a call, or an
    arrow/function value — the values depend on code this module does not execute
  * a config that reads config (`presets`, dynamic imports)

**This module never executes the config.** Running a project's JavaScript to read
its tokens would mean arbitrary code execution during an audit, which is not a
trade the suite makes for a nicer result.

## What "token name" means here

The class-facing name Tailwind generates, which is what appears in source and so
what an audit can compare against. Nested keys join with `-`, `DEFAULT` is dropped:

    colors: { brand: { 500: '#111' } }   ->  brand-500
    colors: { accent: { DEFAULT: '#0f0' } } -> accent
    spacing: { gutter: '1.5rem' }        ->  gutter
"""
from __future__ import annotations

import re
from pathlib import Path

CONFIG_NAMES = ("tailwind.config.js", "tailwind.config.ts",
                "tailwind.config.cjs", "tailwind.config.mjs")

# v4: --color-brand-500, --spacing-gutter, --font-display, --radius-lg …
THEME_BLOCK_RE = re.compile(r"@theme\s*(?:[a-zA-Z-]+\s*)?\{", re.I)
CUSTOM_PROP_RE = re.compile(r"--([a-zA-Z0-9-]+)\s*:", re.M)

# Namespaces Tailwind v4 defines. The prefix is not part of the class name:
# `--color-brand-500` is used as `text-brand-500`.
V4_NAMESPACES = ("color", "spacing", "font", "text", "radius", "shadow",
                 "breakpoint", "container", "tracking", "leading", "ease",
                 "animate", "blur", "perspective", "aspect")

# Anything inside a theme object that means "the value comes from code".
DYNAMIC_RE = re.compile(r"\.\.\.|require\s*\(|=>|\bfunction\b|\bimport\s*\(")

# A static "key": "value" or key: 'value' / bare number.
PAIR_RE = re.compile(r"""["']?([A-Za-z0-9_@.-]+)["']?\s*:\s*(.+?)(?:,\s*$|,(?=\s*["'\w])|$)""",
                     re.M)


def _find_config(repo: Path, declared: str | None) -> Path | None:
    if declared:
        p = repo / declared
        return p if p.is_file() else None
    for name in CONFIG_NAMES:
        p = repo / name
        if p.is_file():
            return p
    return None


def _match_brace(text: str, open_idx: int) -> int | None:
    """Index just past the `}` matching the `{` at open_idx, ignoring strings."""
    depth = 0
    i = open_idx
    quote = None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _flatten(body: str, prefix: str = "") -> set[str] | None:
    """Token names in a JS object body. None if anything is dynamic."""
    if DYNAMIC_RE.search(body):
        return None

    names: set[str] = set()
    i = 0
    while i < len(body):
        # A nested object: key: { ... }
        m = re.compile(r"""["']?([A-Za-z0-9_@.-]+)["']?\s*:\s*\{""").search(body, i)
        brace_at = m.end() - 1 if m else None

        pair = PAIR_RE.search(body, i)
        if m and (pair is None or m.start() <= pair.start()):
            end = _match_brace(body, brace_at)
            if end is None:
                return None
            key = m.group(1)
            inner = _flatten(body[brace_at + 1:end - 1],
                             f"{prefix}{key}-" if key != "DEFAULT" else prefix)
            if inner is None:
                return None
            names |= inner
            i = end
            continue

        if pair is None:
            break
        key, value = pair.group(1), pair.group(2).strip()
        if value.startswith("{"):
            i = pair.start() + 1
            continue
        name = prefix.rstrip("-") if key == "DEFAULT" else f"{prefix}{key}"
        if name:
            names.add(name)
        i = pair.end()
    return names


def from_css(text: str) -> set[str] | None:
    """v4 `@theme` custom properties, namespace prefix stripped."""
    m = THEME_BLOCK_RE.search(text)
    if not m:
        return None
    end = _match_brace(text, m.end() - 1)
    if end is None:
        return None
    body = text[m.end():end - 1]

    names: set[str] = set()
    for prop in CUSTOM_PROP_RE.findall(body):
        for ns in V4_NAMESPACES:
            if prop.startswith(ns + "-"):
                names.add(prop[len(ns) + 1:])
                break
        else:
            names.add(prop)
    return names or None


_SCALE_RE = re.compile(r"""["']?([A-Za-z0-9_-]+)["']?\s*:\s*\{""")


def _scales(body: str) -> list[tuple[str, str]] | None:
    """Top-level `name: { ... }` entries — (scale name, inner body).

    Only the *immediate* children, so nesting inside a scale is left to _flatten.
    None if a brace never closes.
    """
    out = []
    i = 0
    while True:
        m = _SCALE_RE.search(body, i)
        if not m:
            return out
        brace = m.end() - 1
        end = _match_brace(body, brace)
        if end is None:
            return None
        out.append((m.group(1), body[brace + 1:end - 1]))
        i = end


def from_js(text: str) -> set[str] | None:
    """v3 config `theme` object. None if it is not a static literal."""
    if re.search(r"\bpresets\s*:", text):
        return None  # a preset supplies tokens from code we will not execute

    m = re.search(r"\btheme\s*:\s*\{", text)
    if not m:
        return None
    end = _match_brace(text, m.end() - 1)
    if end is None:
        return None
    theme = text[m.end():end - 1]

    # A theme's immediate children are SCALE names — `colors`, `spacing`,
    # `fontSize`. They are not part of a token's name: `colors: { ink: … }` is
    # referenced as `text-ink`, never `text-colors-ink`. The first version of this
    # prefixed them in and produced `colors-ink`, which would have matched nothing
    # in real source.
    #
    # `extend` is a container for the same scales, so it is recursed into rather
    # than treated as a scale — and NOT also scanned as part of the parent body,
    # which double-counted every token it held.
    top = _scales(theme)
    if top is None:
        return None

    names: set[str] = set()
    for scale, body in top:
        if scale == "extend":
            inner = _scales(body)
            if inner is None:
                return None
            for _, ibody in inner:
                got = _flatten(ibody)
                if got is None:
                    return None
                names |= got
            continue
        got = _flatten(body)
        if got is None:
            return None
        names |= got
    return names or None


def token_names(repo: Path, source: dict) -> set[str] | None:
    """Tokens this Tailwind project defines, or None if undeterminable.

    `source` is the profile's `tokens.source`. It may name the config explicitly
    (`path`), which is preferred over discovery — guessing a path is what silently
    broke three scripts in the originating project.
    """
    declared = source.get("path")
    if declared and declared.endswith(".css"):
        p = repo / declared
        return from_css(p.read_text()) if p.is_file() else None

    cfg = _find_config(repo, declared)
    if cfg is not None:
        return from_js(cfg.read_text())

    # v4 projects may have no JS config at all — look for an @theme block.
    for pattern in ("**/*.css",):
        for p in sorted(repo.glob(pattern))[:200]:
            if "node_modules" in p.parts:
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if THEME_BLOCK_RE.search(text):
                return from_css(text)
    return None


# ---------------------------------------------------------------------------


def _selftest() -> int:
    """Prove enumeration works AND that it refuses on configs built by code.

    The refusal cases matter more than the happy path. If a dynamic config quietly
    returned a partial set instead of None, the token-drift check would report every
    token the spread contributed as nonexistent — a confident wrong answer, which is
    worse than the honest "cannot tell".

        python3 design_suite/adapters/tailwind_theme.py
    """
    import tempfile

    problems: list[str] = []

    def case(label, got, want):
        if got != want:
            problems.append(f"{label}\n      got  {got}\n      want {want}")

    # --- v4 CSS -----------------------------------------------------------
    case("v4 @theme", from_css("""
        @theme {
          --color-brand-500: #6366f1;
          --color-accent: oklch(0.7 0.1 200);
          --spacing-gutter: 1.5rem;
          --radius-card: 12px;
          --custom-thing: 3;
        }
        .unrelated { --not-a-token: 1; }
    """), {"brand-500", "accent", "gutter", "card", "custom-thing"})

    case("v4 with no @theme", from_css(".a { color: red }"), None)

    # --- v3 JS ------------------------------------------------------------
    case("v3 extend", from_js("""
        module.exports = {
          content: ["./src/**/*.tsx"],
          theme: {
            extend: {
              colors: { brand: { 500: '#6366f1', 900: '#111827' },
                        accent: { DEFAULT: '#0f0' } },
              spacing: { gutter: '1.5rem' },
            },
          },
        }
    """), {"brand-500", "brand-900", "accent", "gutter"})

    # Top-level theme keys count too, not only `extend`.
    case("v3 top-level", from_js("""
        export default { theme: { colors: { ink: '#000' } } }
    """), {"ink"})

    # --- refusals ---------------------------------------------------------
    for label, src in [
        ("spread", "module.exports={theme:{extend:{colors:{...palette, x:'#fff'}}}}"),
        ("require", "module.exports={theme:{extend:{colors:require('./c.js')}}}"),
        ("arrow", "module.exports={theme:{extend:{spacing:(u)=>({a:u(1)})}}}"),
        ("function", "module.exports={theme:{extend:{colors:function(){return{}}}}}"),
        ("presets", "module.exports={presets:[require('./p')],theme:{colors:{a:'#fff'}}}"),
        ("no theme", "module.exports={content:['./src']}"),
    ]:
        if from_js(src) is not None:
            problems.append(f"a {label} config returned a set instead of None — "
                            f"its values come from code this module does not run")

    # --- discovery via a real directory -----------------------------------
    tmp = Path(tempfile.mkdtemp())
    (tmp / "tailwind.config.js").write_text(
        "module.exports={theme:{extend:{colors:{ink:'#000'}}}}")
    case("discovered config", token_names(tmp, {}), {"ink"})
    case("explicit .css path that is missing",
         token_names(tmp, {"path": "nope.css"}), None)

    tmp2 = Path(tempfile.mkdtemp())
    (tmp2 / "app.css").write_text("@theme { --color-ink: #000; }")
    case("v4 discovery with no JS config", token_names(tmp2, {}), {"ink"})
    case("empty project", token_names(Path(tempfile.mkdtemp()), {}), None)

    if problems:
        print("tailwind_theme selftest FAILED:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("tailwind_theme: enumerates v3 and v4 configs, and returns None for all "
          "6 code-built cases.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
