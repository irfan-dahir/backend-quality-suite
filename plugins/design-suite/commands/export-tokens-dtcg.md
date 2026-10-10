---
name: export-tokens-dtcg
description: "Export this project's declared design tokens as a W3C Design Tokens Community Group (DTCG 2025.10) .tokens.json that Figma, Tokens Studio and Style Dictionary can read. Previews to stdout by default; writes exactly one file only when --out is given, and never edits source. Anything without a faithful DTCG form is listed, never dropped. Use when asked to export tokens to DTCG, Figma, Tokens Studio or Style Dictionary."
invocation: explicit
maturity: unverified
---

# /export-tokens-dtcg

Turns the tokens `tokens.source` declares into a DTCG file.

**Format:** [Design Tokens Format Module 2025.10](https://www.designtokens.org/tr/2025.10/format/) —
a *Final Community Group Report* (28 October 2025). It is the format's first
stable version; it is a Community Group report, **not** a W3C Recommendation.
Later editors' drafts are not followed. Style Dictionary v4+ reads this format
natively.

`invocation: explicit` because it generates content (a file other tools will
consume); `maturity: unverified` because it has only been run against
synthetic token sets, never a real project.

## Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/export_tokens_dtcg.py"                       # preview
python3 "${CLAUDE_PLUGIN_ROOT}/bin/export_tokens_dtcg.py" --out design.tokens.json
python3 "${CLAUDE_PLUGIN_ROOT}/bin/export_tokens_dtcg.py" --out design.tokens.json --report .design-suite/dtcg-export.json
```

## What it writes

- No flags: **nothing.** The document goes to stdout, the summary to stderr.
- `--out PATH`: exactly that file, relative to the project root.
- `--report PATH`: a JSON list of what was exported, what was mapped with a
  stated loss, and what was not exported and why.

It never writes source, never stages, never commits.

## What each stack can export

| `adapters.lang` | Read from | Notes |
|---|---|---|
| `dart` | `static const` in `tokens.source` (via the adapter's existing `token_declarations`) | `Color(0x…)`, `Duration(…)`, known `Curves.*`, `Cubic(…)`, `FontWeight.wN00`, numbers, font-name strings. `EdgeInsets`, `BorderRadius`, `TextStyle`, `BoxShadow` are unrepresentable |
| `tsx`, `web` | CSS custom properties in `@theme` / `:root` of a `.css` `tokens.source.path` | A JS `tailwind.config.*` is **refused** (exit 2): it is never executed |
| `swift` | `static let` in `tokens.source.path` | `Color(red:green:blue:)`, numbers, font-name strings |
| `kotlin` | `val` in `tokens.source.path` | `Color(0x…)`, `N.dp`/`N.sp` (exported as `px` — the mapping is stated in `$extensions`), `FontWeight` |

A unitless number becomes a DTCG `number`, because the code does not say what
unit it means. Two name-based rules exist and are the only ones: a name segment
`weight` makes a 1–1000 number a `fontWeight`; `font`/`family` makes a string a
`fontFamily`. Names become groups by splitting on `-`/`_` or camelCase
(`colorPrimaryDark` → `color.primary.dark`); a name that is both a token and a
prefix of another becomes that group's `$root`, and aliases point at
`{group.$root}` as 2025.10 requires.

## Exit codes

`0` every token exported · `1` exported, some declarations unrepresentable
(listed on stderr, in `--report`, and in the file's root
`$extensions["io.github.irfan-dahir.design-suite"].unrepresentable`) · `2` refused: token
source unreadable, unsupported, or empty. Never report exit 1 as success.
