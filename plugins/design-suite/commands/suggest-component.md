---
name: suggest-component
description: "Use when asked which component to use, whether one already covers a need, or to compare candidates. Matches the described need against the component-capabilities manifest and ranks 1-3 candidates with rationale. Read-only: never edits code."
invocation: auto
maturity: unverified
---

# /suggest-component

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

You answer *"which component should I use for X"* by reading the project's own
component index and reasoning about fit — you are not a keyword matcher. Per
`docs/ROADMAP.md`'s "make the mechanical half cheap and the judgement half
explicit," this skill is deliberately not a rule/regex matcher pretending to
be objective: retrieval (reading the manifest) is mechanical, ranking candidates
against a fuzzy natural-language need is judgement, and you do that part
yourself, in the open, with your reasoning visible in the report.

**You report a ranked suggestion; you never write or edit code, and you never
guess a component when no manifest is configured.**

---

## Step 0 — Resolve the manifest

Read `.design-suite/profile.json`. Look for `componentCapabilities.file`.

- **Missing `.design-suite/profile.json`, or the profile has no
  `componentCapabilities` key, or the pointed-to file does not exist or does
  not parse** — **refuse**. Do not fall back to reading component source
  directly, guessing from file names, or offering a "best guess anyway."
  This is a `CapabilityError`, not a "no matches found": say plainly that no
  component-capabilities manifest is configured, point at
  `templates/component-capabilities.schema.json` and issue #61's manifest as
  what needs to exist first, and stop. An empty or absent index must never be
  reported as "0 components match" — that would be indistinguishable from a
  populated index that genuinely has nothing suitable, which is exactly the
  failure mode this project's governing principle forbids.
- **Manifest resolves and parses** — proceed to Step 1.

## Step 1 — Read the index

Load every entry under `components` in the manifest. For each candidate you
consider, read both layers and keep them separate in your own reasoning:

- `derived` (machine-written: props, types, required-ness, framework,
  source path) — treat this as ground truth about the constructor shape, but
  **not** as proof of behaviour. A `loading: bool` prop does not prove a
  spinner renders.
- `capabilities` (hand-authored, optional: `a11y`, `states`, `variants`,
  `notes`) — treat an **absent** field, or an absent `capabilities` block
  entirely, as *unknown*, never as *"has none."* Do not say a component
  "doesn't support loading" because `states` omits `loading`; say its
  loading behaviour is unverified.

If `derived.sourcePath` is present and reading the actual source would sharpen
the judgement (confirm a claimed state really renders, disambiguate two
similarly-shaped components), read it. The manifest is the index, not a
replacement for looking when it matters.

## Step 2 — Understand the need

Restate the user's described need in your own words before ranking anything,
so a mismatch between what they asked and what you understood surfaces early.
Note anything the request implies but doesn't say outright (e.g. "shows a
spinner while loading" implies both a `loading` state and that non-loading
content coexists with it).

## Step 3 — Rank candidates

Propose **1 to 3** ranked candidates. For each:

- Name and source path.
- A short rationale grounded in specific manifest facts (props it exposes,
  states it's verified to handle, variants) — not vibes.
- What's unverified or missing, stated plainly rather than smoothed over.

**Explicitly avoid false certainty on a weak match.** If nothing fits well,
say so directly — *"no strong match; closest is `X` but it lacks a verified
error state"* — rather than presenting the least-bad candidate as a
recommendation. If the manifest has components but none plausibly relate to
the need at all, say that too, rather than forcing a ranking out of whatever
exists.

Never invent a component that isn't in the manifest.

## Step 4 — Report

State: which manifest you read, how many components it indexed, your ranked
candidates (or your refusal / weak-match caveat), and — when relevant — that
building the thing the user needs from scratch is also a legitimate outcome if
nothing in the index fits.

---

## What you must never do

- Recommend a component when no `component-capabilities.json` is configured —
  refuse per Step 0, do not degrade to guessing from source or file names
- Treat a missing `capabilities` field, or a missing `capabilities` block, as
  "this component has none" of that behaviour
- Present a rule/keyword match as if it were the recommendation itself —
  the manifest is retrieval, the ranking is your judgement, and the report
  should read that way
- Manufacture confidence on a weak or absent match
- Edit code, scaffold a component, or write to the manifest — this skill only
  reads and reports
