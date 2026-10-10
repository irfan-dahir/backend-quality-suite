---
name: audit-pattern-adoption
description: "Count which design-system patterns this project actually calls, and fail on ones it claims but never reaches for. Read-only: reports findings, never edits. Use when asked whether the design system is really being used, or which patterns a product has never adopted."
invocation: auto
maturity: unverified
---

# /audit-pattern-adoption

> Documents are referenced by role, e.g. `{{doc:design}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.

`/audit-unwired-roles` catches a colour role nothing reads. This is the same failure one layer up: a **pattern nothing calls**. Built, documented, listed in a gallery, and reached for by no product code at all.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_pattern_adoption.py` is stdlib-only Python.

It needs a `patternAdoption` section listing the symbols to look for. An empty list is refused rather than passed: an adoption audit with nothing to look for reports nothing, which is indistinguishable from a project that adopted everything.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_pattern_adoption.py"
```

`--selftest` proves the six counting rules still fire and needs no project.

Add `--findings` to also write the common findings envelope for `/design-debt`
(default `.design-suite/findings/pattern-adoption.json`). It is additive: stdout,
stderr and the exit code are identical with and without it.

## Step 2 — Read the three lists differently

**`UNADOPTED`** — patterns the project *claims* in `requiredPatterns` and calls nowhere. These fail.

**`unused here`** — patterns available and never called. These never fail, and in a consumer they are usually information rather than a defect: a phone app not calling a data table is a phone app, not a problem. Report them; do not propose adopting one to clear a line.

**`referenced but never called`** — worth its own look. Usually a type annotation on a field nothing ever fills, which reads as adoption in a grep and is not.

## Step 3 — This is not the two component audits, and pairs with both

`/audit-reinvented-components` and `/audit-promotion-candidates` scan the app's
own private widgets — what it BUILT. This scans call sites of what the design
system EXPORTS — what it never REACHED FOR. A pattern can sit at zero call sites
with nothing reinvented anywhere, and only this audit reports that.

## Step 4 — Pair it with the reinvention audit before concluding anything

A low adoption count and a long `audit_reinvented_components` baseline are the **same finding from two sides**: the project is on its own private copies of components the design system already exports. The reinvention baseline makes those look managed; this audit shows what they cost. Read both before deciding whether low adoption is a problem or a phone app.

## Step 5 — Report

🔴/🟡/🔵 sections. Failing patterns under 🔴, unused-here under 🔵 with a one-line note on what each is for, so the reader can judge which ones the product should be reaching for.

---

## What you must never do

- Call a pattern once somewhere to clear a finding — that is a fake adoption and the audit will pass while meaning less than nothing
- Read low adoption as a defect without checking whether the pattern is even applicable to this product's form factor
- Treat this as a substitute for the design system's own ledger of cross-repo adoption; this measures **one** project, which is the half a consumer can actually verify
