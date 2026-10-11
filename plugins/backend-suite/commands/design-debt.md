---
name: design-debt
description: "Use when asked for an overall picture of design health or design debt across audits. Grades findings already collected in .backend-suite/findings/ per category; it runs no audit, so a category with no findings is missing data, and it names what to re-run. Read-only: reports, never fixes."
invocation: auto
maturity: unverified
---

# /design-debt

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

You are reporting the project's design debt across every audit at once, so nobody
has to run four skills and hold four reports in their head.

**You report; you never fix.** This skill exists to make the shape of the debt
visible, not to start paying it down.

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/design_debt.py` is stdlib-only Python.

It reads `.backend-suite/findings/*.json` — it does **not** run any audit. That
separation is deliberate: an audit's output is baselined byte-for-byte by
`capture-baselines.sh`, and a dashboard that re-ran audits could become the reason
that baseline moved.

## Step 1 — Find out what data exists

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/design_debt.py" --stale-only
```

This lists audits the project declares under `debt.audits` in
`.backend-suite/profile.json` that have no collected findings.

**If anything is listed, collect it before reporting.** Each audit writes the
common envelope with `--findings`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_handling.py" --findings
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_doc_staleness.py" --findings
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_proposal_status.py" --findings
```

**An audit registered as DISABLED refuses with exit 2 and writes nothing.** That
is not a broken tool and not something to work around — do not pass
`--run-disabled`, and do not report the resulting absence as a clean category.
`design_debt.py` already lists any disabled audit in its own section with the
measured reason; repeat that in your report and leave it ungraded.

An audit that has never run leaves no file at all. Reporting on the remaining
audits without saying which ones are absent would present a partial picture as a
complete one — say what is missing, every time.

## Step 2 — Read the dashboard

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/design_debt.py"
```

## Step 3 — Report

Present the table as-is, then interpret it. Four things to get right:

**Grades are per category, never combined.** There is no overall score and you
should not invent one — averaging a contrast pass-rate against a count of
hardcoded colours produces a number that means nothing in either unit, and a
single figure invites moving the figure instead of fixing the code.

**"All known debt" is not the same as a fresh problem.** A category whose findings
are all baselined is debt the project already decided to carry. It still grades on
volume — a debt register that stops showing the debt is not doing its job — but
report it as standing debt, not as something that just broke.

**"Clean across N files" is a real pass. "No findings, but nothing recorded as
scanned" is not.** The second means the audit examined nothing, which reads
exactly like a clean result and is the failure mode this suite has been bitten by
before. Treat it as a configuration finding, not a pass.

**A `⚠️ !` row is a broken findings file**, not a broken codebase. Say so plainly.

**Name the re-runs, don't just note the absence.** This skill grades what is
already on disk; it runs no audit. Any report covering fewer than all the
declared audits must say in its opening line that the picture is partial, and
must end with the exact commands that would close the gap: one
`--findings` invocation per missing or stale audit, each naming its own real
script path as Step 1 lists them, never a placeholder. A dashboard that reads as a health verdict
while silently grading nothing is this suite's governing principle failing on its
own reporting surface.

Then, if asked what to do about it, order by what is cheapest to stop growing
rather than by raw count — a category with 3 new findings and one with 300
baselined ones are different problems.

---

## What you must never do

- Compute, quote, or estimate a single overall design-health score
- Run an audit and report its numbers without writing findings first — a number
  read off a stale file is worse than no number
- Report grades while staying silent about audits with no data
- Present a `?` grade as a pass
- Edit any source file, or start fixing findings, as part of this skill
