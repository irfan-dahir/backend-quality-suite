---
name: audit-accessibility
description: "DISABLED pending correct scoping — measured 100% false positives on two real projects (issue #104), and zero true-positive capacity on one of them. It refuses with exit 2 rather than running. Do not invoke it expecting a result; read this file for the measured reason and the bar for re-enabling it."
invocation: explicit
maturity: disabled
---

# /audit-accessibility

> ## ⛔ DISABLED — do not run this expecting a result
>
> This audit **does not run**. `${CLAUDE_PLUGIN_ROOT}/bin/audit_accessibility.py`
> refuses with **exit 2** (the CapabilityError convention in
> `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`) and prints why. It is listed as
> disabled — never as clean, never as passing — in `repo_health.py`,
> `design_debt.py` and `docs/CATALOG.md`. If you were about to conclude anything
> about this project's accessibility from its silence: don't. Nothing was scanned.
>
> **The measured reason (issue #104).** Run read-only against two live consumer
> projects, it produced 31 findings and **all 31 were false positives** — 25 on
> one project, 6 on the other, judged independently by opening the code. Every one
> was a `package:pdf` print widget checked against `accessibility_minimums.min_text_sp`,
> a *screen* minimum that means nothing for generated PDF output. An 8pt page
> footer in a PDF is ordinary print typography, not an accessibility violation.
>
> **Worse than the rate: it is also blind.** Every one of the 29 `fontSize:`
> literals under one of those projects' source root sits in a PDF-generating file.
> There were no on-screen `fontSize:` literals for it to find at all, so its
> true-positive capacity on that project was **zero**. It is not a noisy check
> that needs a threshold nudged; it is a check that has never once been right
> here. The cause is that the scanner's font-size pattern has no notion of which
> framework's `TextStyle` it matched.
>
> **What re-enabling it takes** — all three, in the commit that removes the
> `audit_accessibility` entry from `design_suite/engine/audit_discovery.DISABLED`:
>
> 1. **A project-declared exclusion for PDF/print-generation code.** It must be
>    declared by the consumer project in its own `.design-suite/` config and read
>    from there. Hardcoding a path, filename pattern or `package:pdf` literal in
>    the plugin violates CLAUDE.md's no-project-literals rule and would only be
>    right for the projects that happen to look like these two.
> 2. **Re-measurement on at least two real consumer projects**, findings judged by
>    opening the code, recorded the way issue #104 records it.
> 3. **Clearing the bar on both axes**: ≤5% wrong *and* demonstrated non-zero
>    true-positive capacity. A check that scores 0% wrong because it now finds
>    nothing has not been fixed — it has been silenced, which is the same failure
>    in a better-looking costume.
>
> `--run-disabled` exists on the script for step 2 only. It prints the same
> warning and its output is not a result anyone should act on.
>
> The `icon_button_no_tooltip` and `small_tap_target` checks are disabled along
> with it. They reported nothing across 65 `IconButton` call sites, which is
> plausible but was never verified — so they are unmeasured, not vindicated, and
> they ride in the same script.

---

## Everything below describes the audit as designed, for whoever re-enables it. It is not currently runnable.


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

You are the mechanical accessibility auditor. This checks things already codified as rules in `{{doc:design}}` — the 14sp text floor, semantic labels on icon-only buttons — but never mechanically verified before.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_accessibility.py` is stdlib-only Python — nothing to install.

## Step 1 — Gather state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_accessibility.py"
```

`.design-suite/accessibility-findings.json` is regenerable and ignored by the scaffolded `.design-suite/.gitignore` — always regenerate fresh.

## Step 2 — Run every check

| Check | What it catches | Severity |
|---|---|---|
| `font_size` | `TextStyle(fontSize: N)`/`.copyWith(fontSize: N)` with `N < 14` — violates `{{doc:design}}` Design Principle #5 ("min 14sp text everywhere, no exceptions") | 🔴 Critical — direct rule violation |
| `icon_button_no_tooltip` | `IconButton(...)` with no `tooltip:` argument — an icon-only tap target with no accessible label for screen readers | 🟡 Should fix |
| `small_tap_target` | A `GestureDetector`/`InkWell` wrapped in a `SizedBox`/`Container` with an explicit `width`/`height` literal under 48dp | 🔵 FYI — heuristic only, real layout constraints (padding, parent sizing) can make the actual tappable area fine even when this literal looks small; read the surrounding code before concluding it's a real violation |

**Contrast-ratio checking is out of scope for this script** — it needs real color math against rendered backgrounds, not a text scan. Don't attempt to eyeball it from hex values in the report. Run `/audit-contrast` for that — it's the companion check, not a gap.

## Step 3 — Report

Same format as every other audit skill in this repo: 🔴/🟡/🔵 sections, one finding per bullet with `file:line`, summary count.

---

## What you must never do

- Edit any `.dart` file to add a `tooltip:`/change a `fontSize:` without confirmation
- Report a `small_tap_target` finding as definitely broken without reading the surrounding layout code first — it's a heuristic, not a certainty
- Attempt contrast-ratio judgments from hex values alone
