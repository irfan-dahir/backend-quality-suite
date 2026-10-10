---
name: audit-tokens
description: "Mechanically audit source for hardcoded design values that should route through design tokens — colours, spacing, radii, durations, curves. Never changes your code; saves its report to .design-suite/tokens-findings.json on every run. Use when asked to check design-token compliance or find hardcoded styling."
invocation: auto
maturity: proven
---

# /audit-tokens

> **What it writes.** This audit never edits source, but every plain run
> (no flag needed) saves its raw report to `.design-suite/tokens-findings.json` (override with `--out`;
> before this release it was `<pipelines.tokens>/findings.json` — `git rm --cached` any old copy),
> and `--findings` additionally writes the envelope under `.design-suite/findings/`.
> Those files are what `/design-debt` and the MCP server read, so they are
> written deliberately. Keep them out of git — they quote your source.

> Documents are referenced by role, e.g. `{{doc:design}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the design-token consistency auditor. the project's token source (`<tokens.source.path>` in the profile) is the single source of truth for colors, spacing, and radii in principle — this skill mechanically checks that the rest of the codebase actually routes through it instead of hand-duplicating literal values.

**You report; you do not edit code without confirmation. Reference: `{{doc:design}}` §"Color System"/"Spacing"/"Radius".**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens.py` is stdlib-only Python — nothing to install.

## Step 1 — Gather state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens.py"
```

This scans `lib/` (excluding `app_theme.dart` itself, the definition) for five patterns:
- **`color`** — `Color(0x...)` literals
- **`edge_insets`** — `EdgeInsets.{all,symmetric,only,fromLTRB}(...)` with a raw numeric argument instead of `AppTokens.spaceN`
- **`border_radius`** — `BorderRadius.circular(N)` with a raw numeric literal instead of `AppTokens.radiusX`
- **`duration`** — `Duration(milliseconds: N)` literals instead of `AppTokens.durationFast/Medium/Slow`/`durationAssetEntrance`
- **`curve`** — bare `Curves.*` usage instead of `AppTokens.curveStandard`/`curveEmphasized`

The `duration`/`curve` checks exist because a real violation was found on first run: `card_preview.dart:46`/`:49` hardcodes `Duration(milliseconds: 400)` + `Curves.easeInOut` for the CVV card-flip animation instead of referencing an `AppTokens` duration/curve — not a hypothetical, an actual finding this script now catches mechanically.

`.design-suite/tokens-findings.json` is regenerable and ignored by the scaffolded `.design-suite/.gitignore` — always regenerate fresh.

## Step 2 — Read what the script suppressed, and do not re-apply it by hand

The script applies this project's accepted exceptions itself, from
`.design-suite/exceptions.json` — both `allowlistFiles` and `allowlistRegions`,
scoped to the category each was documented under. Anything it suppressed is
already absent from the findings file, and it prints a `Suppressed N further
finding(s)` block naming each entry and how much that entry hid.

**Do not maintain a second list of accepted exceptions in your head or in this
file.** A prose list here and a JSON list there is two lists that must agree and
cannot check each other — the drift this suite exists to prevent. This step used
to be that second list, which is why the audit re-reported documented exceptions
for its whole life (issue #108).

What to do with the suppression block:
- Report the count in your summary. A suppressed finding is a decision the
  project made, not an absence — never let it read as a clean file.
- If an entry suppressed nothing on this run, that is worth a 🔵: an exception
  covering no code either got fixed or is now guarding a path that moved.
- If an entry is marked `"appliedBy": "reader"`, the script says so. That field
  is stale metadata — the engine applies these now — so offer to change it to
  `"script"` rather than acting on it.

A path listed under a category's `reportAnyway` is deliberately never suppressed:
it is a logged-but-unfixed item, not an accepted exception, and it must keep
appearing in every report.

If a finding looks like it might be a new, undocumented exception (a fixed
skeuomorphic skin, a brand colour, a deliberate gradient) rather than plain
drift — say so and ask, and propose an `exceptions.json` entry with a reason.
Don't assume it's a bug just because the script flagged it, and don't silence it
anywhere but that file.

## Step 3 — Report

Same format as every other audit skill in this repo (`/audit-assets`, `/audit-copy`, `/review-docs`): 🔴/🟡/🔵 sections, one finding per bullet with `file:line`, summary count. Suggested severity:
- 🔴 Critical: none by default — hardcoded values are a consistency problem, not usually a correctness bug, unless a value diverges from what `AppTokens` actually defines (e.g. a radius that doesn't match any existing `AppTokens.radiusX` value at all).
- 🟡 Should fix: color literals (colors are the most likely to actually drift from the brand when tokens change — see the recent `design-system` recolor).
- 🔵 FYI: spacing/radius literals that happen to already match an existing `AppTokens` value (lower urgency — no visual drift risk today, but still worth tokenizing for future-proofing).
- 🟡 Should fix: `duration`/`curve` findings — motion feel is meant to be centralized (see `/establish-interaction-spec`'s spec doc once it exists), and a hardcoded value here silently drifts if the token set changes later.

---

## What you must never do

- Edit any `.dart` file to replace a literal with a token reference without confirmation
- Keep a list of this project's accepted exceptions anywhere but `.design-suite/exceptions.json` — the script reads that file and applies it; a second copy here is one that silently stops agreeing
- Present the findings count without the suppressed count beside it — "nothing reported" and "everything a documented exception covered" must not read the same
- Treat every flagged literal as equally urgent — a color literal that happens to equal `AppTokens.colorError`'s hex value is lower-risk than one that doesn't match any token at all (the latter means the app would visibly diverge from a future `AppTokens` change)
