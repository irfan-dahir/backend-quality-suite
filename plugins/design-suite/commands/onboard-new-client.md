---
name: onboard-new-client
description: "Playbook rather than a new capability: the ordered sequence of existing skills for standing up the design-system foundation of a new client project or a greenfield area. Start here when onboarding a project."
invocation: explicit
maturity: unverified
---

# /onboard-new-client

> Documents are referenced by role, e.g. `{{doc:brand-voice}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" brand-voice`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are a **playbook**, not a new capability — an ordered sequence of skills that already exist in this repo, run in the right order for standing up the design-system foundation of a new client project (or a genuinely greenfield area of this one). This is a documented composition chain, not multi-agent orchestration: you follow the steps below one at a time, in a normal conversation, pausing at each decision point for the user — you never silently chain them end-to-end without checking in between.

**Reference each linked skill's own doc for its actual mechanics — this file only sequences them and calls out the decision points between steps.**

---

## The sequence

### Step 1 — Brand voice
Run **`/establish-brand-voice`**. If the client already has a brand book, this skill ingests it directly (Step 1 of that skill: "ingest an existing brand document" mode) instead of reverse-engineering from scratch. Produces `{{doc:brand-voice}}`. When there's a live client/stakeholder to interview, that skill's Step 1 points at `templates/docs/fragments/BRAND-ONBOARDING-INTERVIEW.md.template` for a consistent question set — use it here rather than improvising the conversation per client.

**Decision point:** does a brand document exist, or does this need to be reverse-engineered from whatever copy already exists (or drafted fresh if there's truly nothing yet)? Ask before running.

### Step 2 — Design docs (only if the project has none yet)
If `{{doc:design}}`/`{{doc:flows}}` don't exist yet, run **`/bootstrap-design-docs`** to reverse-engineer them from the existing codebase (or scaffold a starting structure if the codebase is also new). **Skip this step entirely** if the project already has these docs — this is for genuinely greenfield projects only.

**Decision point:** is this a zero-docs project, or does it already have a design-system doc suite (like this one does)? If the latter, skip straight to Step 3.

### Step 3 — Interaction spec
Run **`/establish-interaction-spec`** to establish motion conventions (reverse-engineered from existing tokens/usage, same as brand voice) and haptic/sound conventions (greenfield — ask, don't assume). Produces `{{doc:motion}}`.

### Step 4 — First real screen
Run **`/scaffold-screen`** for the client's first real screen, once the specs above exist to draft on-brand copy and correctly-toned motion against. This is deliberately last — scaffolding a screen before the voice/motion specs exist means it'll need revisiting once they land.

---

## What this playbook does NOT do

- It does not run any of these skills for you automatically — you still invoke each one explicitly, in this order, checking in with the user between steps
- It does not skip any skill's own confirmation/sign-off requirements — `/establish-brand-voice` and `/establish-interaction-spec` still require attribute-by-attribute sign-off, this playbook doesn't shortcut that
- It is not the Workflow tool — no multi-agent fan-out, no background orchestration; this is a plain sequential checklist authored the same way every other skill in this repo is (a markdown file the assistant reads and follows)

## When to add a new playbook instead of extending this one

If a different common multi-step task emerges (e.g. "audit an existing project before taking it over" = `/audit-tokens` → `/audit-accessibility` → `design-auditor` → `/review-docs`, in that order), author it as its own `.claude/commands/*.md` playbook rather than growing this one into a catch-all — each playbook should map to one recognizable real-world task, not become a menu.
