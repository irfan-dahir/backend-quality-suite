---
name: audit-reinvented-components
description: "Use when asked what has been rebuilt instead of reused. Finds private widgets forking a design-system export by exact name, and bespoke widgets that never touch the design system; ratcheted against a committed baseline. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-reinvented-components

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

You find components nobody found. The cost of a reinvented widget is not the
hour spent writing it — it is that the original now has a competitor which will
drift from it silently, and neither one is obviously the wrong one to edit.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_reinvented_components.py` is stdlib-only
Python — nothing to install.

It reads the `reinventedComponents` section of this project's architecture rules
(`audits.archRulesFile` in the profile): which package the design system is,
where to scan, and (optionally) where the baseline lives. Exit **2** means it
refused — no section, no declared design-system package, or nothing to scan.
A refusal is not a clean result and must never be summarised as one.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reinvented_components.py"
```

## Step 2 — Read the two things it finds, and the one it refuses to

**FORKED (the name check).** A private widget whose name matches an exported
design-system type once the leading underscore is dropped. Exact, no false
positives by construction.

**BESPOKE.** A widget built in a file that never imports the design system at
all — the gap the name check cannot see, because a component that was never
named after anything cannot collide with anything.

**Deliberately not flagged: resemblance.** A private widget that merely *looks
like* an exported one is a judgement call, and a check that guesses is a check
people learn to ignore. Shape-based matching lives in
`/audit-promotion-candidates`, which states its heuristic openly rather than
smuggling it in here.

**Deliberately not flagged: a recorded collision.** A name shared by genuinely
different components is listed in the rules with the reason it was allowed, not
silently skipped — because "we looked and it was fine" and "nobody looked" must
not produce identical silence. Report what was suppressed and why, beside the
count.

`--update-baseline` rewrites the accepted-violations baseline and must not be
run without explicit confirmation.

## Step 3 — Report

🔴/🟡/🔵 sections, one finding per bullet with `file:line`, plus the suppressed
count and the baselined count beside the new one.

- 🔴 Critical: a FORKED widget — there is an exported component with that exact
  name, so this is a competitor to something that already exists.
- 🟡 Should fix: a BESPOKE widget in a file that touches the design system
  nowhere — worth asking what it should have used.
- 🔵 FYI: a recorded collision, named so the exception stays visible.

---

## What you must never do

- Delete or rewrite a private widget to "use the real one" without
  confirmation — the two may have diverged in ways the name does not show
- Report a resemblance as a finding of this audit; it does not check for one
- Run `--update-baseline` without explicit confirmation
- Present the finding count without the suppressed and baselined counts beside
  it
