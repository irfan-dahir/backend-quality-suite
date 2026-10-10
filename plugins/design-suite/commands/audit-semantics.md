---
name: audit-semantics
description: "Four precisely-scoped Flutter semantics rules, each from a defect that shipped (issue #128) — error text never announced, selection shown by colour alone, excludeSemantics dropping more than one node, and (advisory only) a tappable inside a labelling Semantics. Never changes your code; saves its report to .design-suite/semantics-findings.json on every run. Use when asked whether screen-reader semantics are wired, or after building an input, chip, or legend component. Not a re-enabled audit-accessibility."
invocation: auto
maturity: unverified
---

# /audit-semantics

> **What it writes.** This audit never edits source, but every plain run
> (no flag needed) saves its raw report to `.design-suite/semantics-findings.json` (override with `--out`),
> and `--findings` additionally writes the envelope under `.design-suite/findings/`.
> Those files are what `/design-debt` and the MCP server read, so they are
> written deliberately. Keep them out of git — they quote your source.

> **Exit codes:** 0 clean or advisory-only, 1 `should-fix` findings, 2 could not
> look (no adapter support, missing scan dir, zero files matched). Exit 2 is
> never a pass.

You are the semantics auditor. **You report; you do not edit code without
confirmation.**

This is **not** `/audit-accessibility` re-enabled. That audit stays disabled
(`design_suite/engine/audit_discovery.DISABLED`) because its threshold rules were
100% wrong on two real projects. This one carries no thresholds; its rules are
about which semantics argument is present. It is `unverified`: no rule here has
yet been measured on a real project by an independent judge.

## Step 1 — Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_semantics.py" --findings
```

## Step 2 — The rules

| Check | Matches | Deliberately does not match | Severity |
|---|---|---|---|
| `error_not_announced` | A file declaring an `errorText`/`error` field that renders it in `Text(...)` outside any `Semantics(liveRegion: true)`, with no `SemanticsService.sendAnnouncement` in the file | Delegation — passing `errorText:` to `InputDecoration` or another widget; the receiver is judged in its own file | 🟡 should-fix |
| `selection_by_colour_only` | A `GestureDetector`/`InkWell`/`InkResponse` whose subtree computes a colour from `selected`/`isSelected`, with no `selected:` on the wrapper or on a `Semantics` enclosing or inside it | Selection published by an enclosing `Semantics(selected:)` in the same file; an ancestor in another file cannot be seen — use an exception | 🟡 should-fix |
| `exclude_semantics_over_multiple_nodes` | `Semantics(excludeSemantics: true, ...)` whose inline subtree has two or more semantics-bearing nodes | A single `Text` (the safe use); the scoped `ExcludeSemantics` widget | 🟡 should-fix |
| `tappable_in_labelling_semantics` | A `Semantics` with its own `label`/`onTap`/`selected`/`checked` enclosing a `GestureDetector`/`InkWell` with `onTap` and no `excludeFromSemantics: true` | Anything under an intervening `MergeSemantics` | 🔵 FYI — measured 40% wrong in #128's follow-up. Never gates. The fix is a rendered-semantics test proving it either way, not the annotation |

**Cannot see:** subtrees built by helper methods (`child: _buildRow()`),
ancestors in another file, and the rendered semantics tree. Say so in the report.

## Escapes

Each check name is its own category in `.design-suite/exceptions.json`, using
the existing `allowlistFiles` / `allowlistRegions` / `reportAnyway` keys.
Suppressed findings are printed with their count — report them.

## What you must never do

- Present a `tappable_in_labelling_semantics` finding as a confirmed defect
- Read a zero-finding result as "semantics are correct"
- Treat this audit as clearing `/audit-accessibility`'s re-enable bar
