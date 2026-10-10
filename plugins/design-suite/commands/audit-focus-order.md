---
name: audit-focus-order
description: "Best-effort, source-only check of focus/tab traversal order against visual layout order — Stack/Positioned mismatches and explicit traversal overrides (autofocus, FocusTraversalOrder). Never changes your code; saves its report to .design-suite/focus-order-findings.json on every run. Use when asked to check focus order, tab order, or whether traversal matches visual layout. Cannot walk a rendered widget tree — see the report's caveat before treating a clean result as proof."
invocation: auto
maturity: unverified
---

# /audit-focus-order

> **What it writes.** This audit never edits source, but every plain run
> (no flag needed) saves its raw report to `.design-suite/focus-order-findings.json` (override with `--out`),
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

You are the focus-order auditor. A screen's tab/focus traversal order can
silently diverge from what a sighted user perceives as the reading order —
absolute positioning, transforms, and explicit traversal overrides are the
usual causes, and the divergence is invisible to visual QA because the screen
still looks right.

**This suite scans source, not a running app.** There is no rendered DOM or
live focus ring to walk here, so this is a **structural, best-effort** check,
not a rendered-order walk. Say so in the report, every time — do not let a
clean result read as "traversal order verified."

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_focus_order.py` is stdlib-only Python —
nothing to install.

## Step 1 — Gather state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_focus_order.py"
```

`.design-suite/focus-order-findings.json` is regenerable and ignored by the scaffolded `.design-suite/.gitignore` —
always regenerate fresh.

## Step 2 — Run every check

| Check | What it catches | Severity |
|---|---|---|
| `stack_order_mismatch` | Inside one `Stack(...)`, a `Positioned` child (containing a focusable widget) declared *after* a sibling it visually sits above/left of — default traversal follows declaration order, not the `top`/`left` it was given | 🔵 FYI — heuristic; only compares literal `top`/`left` values when both siblings set `top`, and only within an inline `Stack` |
| `autofocus_override` | `autofocus: true` — jumps traversal to this widget on build, ahead of whatever declaration order would otherwise give | 🔵 FYI — often deliberate; flagged so the override gets a second look, not because it's presumed wrong |
| `explicit_traversal_order` | `FocusTraversalOrder(...)` — traversal order set by hand | 🔵 FYI — confirm the numeric/lexical order still matches this widget's current visual position; layouts move, these silently stop matching |

**Everything this cannot see, by construction**: `Transform`-shifted widgets,
offsets computed at runtime (`MediaQuery`, `LayoutBuilder`, an animation
value), `Flex`'s `order` property reordering a `Row`/`Column`, an
`OverlayEntry`, a `Stack` assembled by a helper method rather than written
inline, RTL flips via `Positioned.directional`, and — the biggest gap — which
`FocusTraversalPolicy` an ancestor `FocusTraversalGroup` actually installs,
which decides whether "declaration order" is even the right mental model for
a given screen. None of that is silently skipped and reported clean; name the
gap in the report.

## Step 3 — Report

Same format as every other audit skill in this repo: 🔴/🟡/🔵 sections, one
finding per bullet with `file:line`, summary count — plus, unlike the other
audits here, a leading caveat line stating this is source-only and cannot
confirm actual runtime traversal order. A zero-finding result is "no
structural mismatch found in source," not "focus order is correct."

---

## What you must never do

- Edit any `.dart` file to reorder widgets, add/remove `autofocus`, or change
  a `FocusTraversalOrder` value without confirmation
- Report a `stack_order_mismatch` finding as a confirmed defect — it is a
  prompt to read the surrounding `Stack`, not a certainty
- Claim a clean result means tab order is correct — it means this specific,
  narrow structural pattern wasn't found; a live-render/integration-test walk
  is the only way to actually confirm traversal order
