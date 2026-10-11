---
name: audit-error-handling
description: "Use when asked about error-handling coverage, or before wiring a new endpoint. Checks every failure reaches the user: no call bypassing the shared guard, no raw exception text on screen, no unmatched failure state, no per-screen error widget. Read-only: reports findings, never edits."
invocation: auto
maturity: proven
---

# /audit-error-handling

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

You audit the part of an app nobody demos and everybody discovers in production. None of these checks is about whether the code compiles; all of them are about whether a user finds out something went wrong.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_error_handling.py` is stdlib-only Python.

It needs an `errorHandling` section naming this project's own error machinery — the shared exception type, the guard every network call sits inside, the shared error widget. **The engine has no names of its own on purpose**: a wrong name matches nothing and reports a confident zero. If it refuses for a missing field, help write the section.

A project with no network layer should not configure this at all, rather than owning a tool aimed at nothing.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_handling.py"
```

## Step 2 — Read the two tiers, and keep them apart

| Tier | Meaning | Exit |
|---|---|---|
| `critical` | Unambiguous, no realistic false positive. Today that is one check: a network call outside the guard, which means its failure never maps onto the shared exception hierarchy | **fails** |
| `should_fix` | Needs a human's judgement — a stringified exception, a dead failure state, a bespoke inline error widget | reported, does not fail |

The tiers are separate so the failing one stays worth reading. A build that fails on judgement calls is one people learn to switch off, and it takes the critical tier with it. **Do not propose promoting an advisory check to critical** without a concrete false-positive review.

## Step 3 — Report

🔴 for critical, 🟡 for should-fix, one finding per bullet with `file:line`, summary count.

For a `dead_failure_state` finding, check whether the state is deliberately unwired before proposing anything — a state waiting on a real backing fetch is a decision, and belongs in the exceptions file with the reason and the source that documents it. Re-confirm with the feature owner rather than wiring it speculatively.

---

## What you must never do

- Wire a dead failure state into a screen speculatively — you are guessing at what the failure should say to a user
- Add a `guardApiCall`-equivalent wrapper around a call without reading what the call does; the guard maps errors, and mapping the wrong ones is worse than not mapping
- Report advisory findings as build failures, or let a clean critical tier imply the advisory tier was empty
