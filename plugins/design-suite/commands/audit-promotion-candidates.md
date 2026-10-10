---
name: audit-promotion-candidates
description: "Use when asked what should be promoted into the design system, or what was reinvented under a different noun. Finds private widgets built more than once, by constructor shape rather than name; a heuristic tuned to under-report. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-promotion-candidates

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

You find the design system's intake queue: widgets this project has built twice.

`/audit-reinvented-components` answers a narrower, exact question — does this
private widget share a NAME with something the design system exports. That
precision is deliberate, and it is also blind to the two cases that cost most:
a duplicate that was renamed, and a widget invented twice inside the app in a
place where the design system has nothing yet, so there is no name to match
against.

This audit stops matching names and matches **shape** instead: a widget's
constructor parameter names, sorted, with the framework's key parameter
dropped. Two classes in different files with the same parameter set are usually
the same job done twice, whatever each file called it.

**This is a heuristic, and every report must say so.** A candidate is a prompt
to go and read two files, not a defect. It is deliberately tuned to
under-report, so a short list is not evidence that nothing was duplicated.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates.py` is stdlib-only
Python — nothing to install.

It reads the `promotionCandidates` section of this project's architecture rules
(`audits.archRulesFile` in the profile) for where to scan and where its baseline
lives. Exit **2** means it refused — no such section, or nothing to scan.
Refused is not clean, and must not be summarised as "no candidates".

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates.py"
```

`--update-baseline` rewrites the accepted-duplicates baseline. Never run it
without explicit confirmation: it is how a candidate stops being reported, which
is a decision about the design system's scope, not a way to quiet a red run.

## Step 2 — Judge each candidate, do not just relay it

For each group the script reports, read both definitions and say which case it
is:

| Case | What to say |
|---|---|
| The same component twice | 🟡 Promote — name the better of the two implementations and what the shared API would be |
| The same shape, different jobs | 🔵 Coincidence — two widgets can share `(color, label)` and mean different things; say so and propose a baseline entry with that reason |
| A worse copy of something the design system already exports | 🔴 — this is a fork, not a candidate; `/audit-reinvented-components` may already be naming it |

A group you dismiss belongs in the baseline **with its reason**, never dropped
silently: "we looked and it was fine" and "nobody looked" must not produce the
same absence.

## Step 3 — Report

🔴/🟡/🔵 sections, one candidate per bullet naming every `file:line` in the
group and the shared parameter set, a summary count, and a leading line stating
that this is a shape heuristic that under-reports by design.

---

## What you must never do

- Present a candidate as a confirmed duplicate without having read both files
- Run `--update-baseline` without explicit confirmation
- Promote anything into the design system here — that is `/promote-component`,
  and it is an explicit, content-generating action
- Let a short list read as "this project has no duplication"
