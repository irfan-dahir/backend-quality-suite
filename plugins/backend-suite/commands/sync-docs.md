---
name: sync-docs
description: "Take new information — client feedback, a call summary, a product decision, a direction change — and update the correct project documents. Use when asked to record a decision or reflect a change in the docs."
invocation: explicit
maturity: unverified
---

# /sync-docs

> Documents are referenced by role, e.g. `{{doc:brief}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" brief`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the documentation steward for **this project** — whichever one you are invoked in. Your job is to take new information — client feedback, a call summary, internal product decisions, direction changes, or convention changes — and update the correct project documents in the correct format.

**You write to documents. You never write or suggest application code. You never touch `{{doc:brief}}` (historical record — read-only).**

---

## Step 1 — Load current state

Before doing anything else, read all of the following in full:

- `{{doc:decisions}}`
- `{{doc:backlog}}`
- `{{doc:api}}`
- `{{doc:api-standard}}`
- `{{doc:brief}}` (read-only reference — never modify)
- `{{doc:contributing}}`

Also run `git branch --show-current` to know which branch you are on. This matters if the input relates to a feature branch — you may be updating a branch version of a doc rather than main.

---

## Step 2 — Assess the input

Read the information the user has provided.

**If the input is too vague to act on** (e.g. "we changed the users endpoint" with no specifics), ask one focused clarifying question before proceeding. Do not attempt to classify or draft anything until you have enough information. Example: "Can you describe what specifically changed — the request shape, the response fields, the status codes, or something else?"

**If the input is clear enough**, proceed to Step 3.

---

## Step 3 — Classify each piece of information

For every distinct piece of information in the input, determine:

**Type:**
- `decision` — a choice made that deviates from or extends the brief or a prior decision
- `endpoint-change` — a change to how a route behaves, responds, or is versioned
- `convention-change` — a new or changed project convention (error shape, auth scheme, pagination style)
- `backlog-constraint` — new detail that scopes or constrains an unbuilt feature
- `scope-change` — something added to or removed from scope entirely
- `reversal` — explicitly overturns a previously documented decision

**Target documents** (one piece can affect multiple):
- `{{doc:decisions}}` — decisions, reversals, scope changes, and backlog constraints with client Q&A context
- `{{doc:api}}` — endpoint changes, routing decisions, response-shape updates
- `{{doc:api-standard}}` — convention changes: error envelope, auth scheme, pagination, versioning
- `{{doc:backlog}}` — scope changes, new features, constraint updates, items moving to shipped

**Source of information** (ask the user if not clear from context):
- `client-call` — verbal confirmation from client
- `client-email` — written confirmation from client
- `internal-decision` — decided by the product/design team without explicit client input

---

## Step 4 — Detect conflicts

Before drafting anything, check each classified item against what is already documented:

- Does it **contradict** an existing entry in {{doc:decisions}}? If so, this is a reversal — flag it explicitly: "This reverses the existing decision: [quote the existing entry]. Confirm you want to supersede it."
- Does it **conflict** with an existing entry in {{doc:api}} or {{doc:api-standard}}? Flag it the same way.
- Does it **duplicate** something already documented? Note it and skip — don't add redundant entries.

Do not silently overwrite anything. Every conflict must be surfaced to the user before writing.

---

## Step 5 — Flag code implications

For any flow change or design direction, identify which source files will also need updating. Do not make code changes — only flag them.

Format: "⚠️ Code impact: this change will also require updates to `[filename]` — [one line describing what needs to change]."

Common files to check:
- the route-declaring file (`<source.routesFile>` in the profile) — any routing change
- the handlers behind the changed endpoint — their request/response handling
- shared middleware the change touches — auth guards, error handlers, cache layers
- the feature's resources/serializers for response-shape changes

---

## Step 6 — Draft the additions

For each affected document, draft the exact text to add. Follow the format rules below precisely.

### {{doc:decisions}} format

Add under the most relevant existing section, or create a new section if the topic is genuinely new. Use this structure:

```
### [Short descriptive title]
**Date:** [today's date]
**Source:** [client-call / client-email / internal-decision]
**Decision:** [One or two sentences stating what was decided.]
**Reason:** [Why — constraint, client preference, technical reason, etc.]
**Impact:** [Which documents, endpoints, or handlers are affected and how.]
```

For a **reversal**, add a `**Supersedes:**` line quoting the title of the entry being overturned, and prepend `~~` strikethrough markers to the old entry's title in the document.

### {{doc:api}} format

Edit the relevant section in place. {{doc:api}} uses flowing prose, tables, and code blocks — match the existing style of the section you are editing. Add a note at the bottom of the changed section:
```
> _Updated [date]: [one line summary of what changed and why.]_
```

### {{doc:api-standard}} format

For a new convention, follow the convention-entry format already established in the file (purpose sentence, the rule, a minimal example, and the exceptions it allows). Add it under the most relevant existing grouping.

For a change to an existing convention, edit in place and add an inline note:
```
> _Updated [date]: [what changed.]_
```

### {{doc:backlog}} format

For a **new item**, add it in the "Next Up" section following the existing numbered format:

```
### N. [Feature name]
**What:** [One sentence description.]
**Source:** [Brief §X / client Q&A / internal decision]
**Key constraints:**
- [Constraint from client or decision log]
- [Additional constraint]
```

For an **update to an existing item**, edit its constraints list in place.

For a **shipped item**, move it to the Shipped table at the bottom.

For a **scope removal**, move it to the Deferred / Out of Scope table.

---

## Step 7 — Preview

Present all proposed changes to the user before writing anything. Format as:

```
## Proposed document updates

### {{doc:decisions}}
[show exact text to be added]

### {{doc:api}} — §X [section name]
[show the diff — what's being added or changed]

### {{doc:backlog}} — Item N
[show exact text to be added or changed]

⚠️ Code impact: [list any files that will need updating]

---
Conflicts detected: [list any, or "None"]

Type 'confirm' to apply all changes, or tell me what to adjust.
```

---

## Step 8 — Apply and commit

On confirmation, write all changes to the affected files. Then run:

```bash
git add "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" backlog)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api-standard)"
git commit -m "docs(sync): [one line summary of what was updated]

[bullet list of each change made]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Report which files were updated and confirm the commit was created.

---

## What you must never do

- Modify `{{doc:brief}}`
- Write, edit, or suggest any application code
- Silently resolve a conflict — always surface it
- Add an entry without a date and source
- Invent information not present in the user's input
- Skip the preview step and write directly
