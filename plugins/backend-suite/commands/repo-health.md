---
name: repo-health
description: "Use when starting a session on an unfamiliar project, or asked for overall audit/health status in one read. Runs every audit fresh and reports one JSON posture: configured, clean, findings, refused. Never changes your code, but saves every audit's report files as it runs."
invocation: auto
maturity: unverified
---

# /repo-health

> **What it writes.** Never fixes anything, but it is not read-only: it runs
> every audit with `--findings`, so each audit writes its envelope under
> `.backend-suite/findings/`, and audits that save a raw report on every run
> (e.g. `/audit-mock-api`) write that too.

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are producing one agent-readable JSON document summarising every audit's
run-health on this project right now, so a session can `cat` it once instead of
running N audit commands to find out what even works here.

**You report; you never fix.** Same rule as `/design-debt` — this makes the
project's audit posture visible, not a first step toward changing it.

---

## Step 0 — How this differs from `/design-debt`

`/design-debt` grades **existing** `.backend-suite/findings/*.json` files and never
runs an audit — that separation protects `capture-baselines.sh`, whose whole job
is noticing when an audit's own output moves.

This command **runs every `audit_*.py` fresh**, right now, and reports whether
each one even ran, separately from what it found:

  * `clean` — ran, exit 0
  * `findings` — ran, exit 1, something to report
  * `refused` — ran, exit 2: not configured for this project (missing profile
    key, adapter without the capability, empty sweep) — **never** reported as a
    pass
  * `unclear` — exited nonzero without writing a findings envelope even though
    it supports one; a gap in that audit's own exit-code discipline, not
    something this command can resolve
  * `crashed` — the process itself failed or timed out

It writes the same `--findings` envelopes `/design-debt` reads, so running this
also leaves `/design-debt` with fresh data.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_health.py" --json
```

Takes 10s–2min depending on repo size; each audit has its own per-row timestamp
and duration, so a slow one is visible rather than blamed on the whole run.

## Step 2 — Report

Present the dashboard, then interpret it. Four things to get right, mirroring
`/design-debt`'s own rules because the same failure modes apply here:

**A `refused` row is not a failure of the codebase — it is a gap in project
configuration.** Say what is missing (the row's `message`), not just that the
audit didn't run.

**An `unclear` row is not the same as `findings`.** It means the dashboard could
not obtain a severity breakdown for that run; do not invent one, and do not
present its `findingsCount: null` as zero.

**A `crashed` row is never a pass.** Surface `exitCode` and `message` verbatim.

**Do not compute a single overall score** across audits — same reasoning as
`/design-debt`: a pass/fail count is not comparable across audits that check
fundamentally different things, and inviting one invites optimising the number.

---

## What you must never do

- Report `refused` or `unclear` as if the audit passed
- Treat `findingsCount: null` as zero findings
- Compute or quote a single overall health score
- Edit any source file, or start fixing findings, as part of this command
