---
name: onboard-new-client
description: "Playbook rather than a new capability: the ordered sequence of existing skills for standing up the documentation and contract foundation of a new client project or a greenfield area. Start here when onboarding a project."
invocation: explicit
maturity: unverified
---

# /onboard-new-client

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

You are a **playbook**, not a new capability — an ordered sequence of skills that already exist in this repo, run in the right order for standing up the foundation of a new client project (or a genuinely greenfield area of this one). This is a documented composition chain, not multi-agent orchestration: you follow the steps below one at a time, in a normal conversation, pausing at each decision point for the user — you never silently chain them end-to-end without checking in between.

**Reference each linked skill's own doc for its actual mechanics — this file only sequences them and calls out the decision points between steps.**

---

## The sequence

### Step 1 — Scaffold the config
Run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "<project>"` to create the `.backend-suite/` directory. Every value it writes is the literal text `TODO` — that is deliberate, and this playbook fills them in order.

**Decision point:** does the client already have a codebase, or is this greenfield? A codebase means Step 2 can reverse-engineer; greenfield means the docs come from the plan instead, and Step 2 scaffolds starting structures.

### Step 2 — Context documents (only if the project has none yet)
If `{{doc:api}}`/`{{doc:decisions}}` don't exist yet, run **`/bootstrap-api-docs`** to reverse-engineer them from the existing codebase (or scaffold a starting structure from the plan if the codebase is also new). **Skip this step entirely** if the project already has these docs — this is for genuinely greenfield projects only.

**Decision point:** is this a zero-docs project, or does it already have an API doc suite? If the latter, skip straight to Step 3. Expect to do real work here: the templates mark decisions as **DECIDE**, and a `DECIDE` is genuinely yours to make.

### Step 3 — Map and propose
Run **`/map-project`** to argue which of the client's files plays which document role (each proposal written with provenance `inferred`, ratified later by a human). Then, once source exists to read, **`/propose-config`** proposes real values for the config sections Step 1 left as `TODO`, each with the evidence behind it.

**Decision point:** `/propose-config` proposes nothing where the evidence is weak — on a zero-code greenfield it correctly proposes almost nothing. Do not fill TODOs by hand to make it quiet; leave them for when the code exists to justify an answer.

### Step 4 — First contract, kept in sync
Once there is a first endpoint to expose, run **`/wire-endpoint`** to connect it to a mocked endpoint, and **`/sync-mock-api`** / **`/audit-mock-api`** to keep the contract's four sides (model, fixture, docs, mock server) from drifting from day one. This is deliberately last — wiring an endpoint before the docs exist to describe it means it needs revisiting once they land.

---

## What this playbook does NOT do

- It does not run any of these skills for you automatically — you still invoke each one explicitly, in this order, checking in with the user between steps
- It does not skip any skill's own confirmation/sign-off requirements — `/map-project` and `/propose-config` still wait for explicit approval, this playbook doesn't shortcut that
- It is not the Workflow tool — no multi-agent fan-out, no background orchestration; this is a plain sequential checklist authored the same way every other skill in this repo is (a markdown file the assistant reads and follows)

## When to add a new playbook instead of extending this one

If a different common multi-step task emerges (e.g. "audit an existing project before taking it over" = `/survey` → `/review-docs` → `/repo-health`, in that order), author it as its own `.claude/commands/*.md` playbook rather than growing this one into a catch-all — each playbook should map to one recognizable real-world task, not become a menu.
