---
name: draft-pr-description
description: "Draft a PR title and description from the actual diff and commit history, following the project's own PR template. Drafts only — never pushes, force-pushes, or opens the PR without an explicit go-ahead."
invocation: auto
maturity: proven
---

# /draft-pr-description

> Documents are referenced by role, e.g. `{{doc:pr}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" pr`. See the design-suite plugin's `docs/DOC-ROLES.md` for the role vocabulary and exit-code contract.

You draft a PR title and description from the actual diff and commit history — not the full PR-mechanics workflow (fetch/rebase/push stay manual, per `{{doc:pr}}`). This is narrower and purely a convenience: turning "write the PR description" from a from-scratch writing task into a review-and-confirm task.

**You draft; you never push, force-push, or create the PR yourself without the user's explicit go-ahead — that's still `{{doc:pr}}`'s territory.**

---

## Step 1 — Gather state

Ask for the target branch if not already established in conversation (never assume — `{{doc:pr}}`'s own Step 1 makes the same point).

```bash
git log --oneline <target-branch>..HEAD
git diff --stat <target-branch>...HEAD
git diff <target-branch>...HEAD
```

Read every commit in the range, not just the latest one — the description must reflect everything the PR actually contains.

## Step 2 — Draft using this project's own PR template

Read the template and the title conventions from `{{doc:pr}}` rather than from memory:

```bash
PR_DOC="$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" pr)" && echo "$PR_DOC"
```

That document owns the canonical template, its checklist items, and the title prefixes. **Do not carry a copy of them in this skill** — a duplicated checklist drifts from the real one, and the checklist is where the project-specific parts live (which platforms get tested, which conventions apply). Copy the shape you find there.

If the `pr` role is not mapped in this project (`resolve_role.py` exits 2), fall back to a minimal, framework-neutral shape and say plainly that you did so:

```markdown
## Summary
- <what changed and why>

## Changes
- <bullet per meaningful change>

## Test plan
- [ ] <how this was verified>
```

Title: follow the prefix convention the project's PR document states; if it states none, use Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`) and keep it under 72 characters.

If the template carries a `Verification-Tier:` trailer (issue #59), leave its value blank for the human or dispatching agent to fill in rather than guessing one — and never draft it in as `cross-verified` or `human-reviewed` on this skill's own authority, since those tiers require an independent party this skill cannot supply.

If the diff touches multiple unrelated things (common on a long-lived branch), say so explicitly rather than papering over it with one artificially unified narrative — a reviewer needs to know if this is really three changes bundled into one PR.

## Step 3 — Present for confirmation

Show the drafted title + description. Once confirmed, you may run `gh pr create` (if the user has already pushed the branch and wants the PR opened) — but confirm the base/head branches explicitly first, and never push or force-push as part of this skill; that's `{{doc:pr}}`'s job.

---

## What you must never do

- Push, force-push, rebase, or resolve conflicts as part of this skill
- Create the PR without the user confirming the drafted title/description first
- Flatten a multi-topic diff into one artificially clean narrative — flag the mix instead
- Guess the target branch instead of asking
- Embed a copy of the PR template or its checklist in this file — read it from `{{doc:pr}}` every time, so it cannot drift
