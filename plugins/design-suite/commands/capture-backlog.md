---
name: capture-backlog
description: "Draft backlog entries in the project backlog's own existing format, for review before anything is written. Use when asked to add something to the backlog, file follow-up work, or capture what came up during a session."
argument-hint: "<the item, or nothing to use what /session-decisions found>"
invocation: explicit
maturity: unverified
---

# /capture-backlog

> Documents are referenced by role, e.g. `{{doc:backlog}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" backlog`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are drafting backlog entries for work that came up but was not done.

**Explicit by design**, for the same reason as `/log-decision`: detection is
automatic, writing is not. A backlog quietly filled with speculative items stops
being read, and an unread backlog is worse than a short one.

---

## Step 1 — Resolve the backlog

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" backlog --check
```

Same exit-code discipline as `/log-decision`: 1 is a project defect to report, 2
means the role is unmapped here, 3 means another repository owns it, 4 means this
project has recorded that it keeps no backlog — quote the reason `resolve.py`
printed, say the entries were not captured because of it, and stop — and 5 means
the backlog is a stub, so say plainly that these are its first entries rather
than additions to an existing list. Never create the file, and never write into a
document this project does not own.

## Step 2 — Learn the format, including where things go

Read enough of the document to answer three questions before drafting:

- **Is it ordered?** Many backlogs are sequenced by delivery order rather than
  appended to — in which case *where* an item goes is part of the entry
- **Are there sections?** A "Shipped" section at the bottom is common; so are
  splits by area or by product-vs-infrastructure. Putting an item in the wrong
  section is worse than not filing it, because it will not be found again
- **How much detail does an entry carry?** Match it

If the document points elsewhere for a class of work — infrastructure, release
readiness, compliance — respect that split and say so rather than filing an item
into the wrong document.

## Step 3 — Draft

One entry per item. Each should carry:

- **What** — concrete enough that someone else could pick it up
- **Why it came up** — the context that made it worth filing, which is what
  someone triaging it later will need
- **What it is not** — only where the boundary is genuinely unclear

Do not assign priority unless the document's existing entries carry one. Inventing
a priority scheme the backlog does not use is a change to the document's
conventions, which is not this skill's call to make.

## Step 4 — Show it and wait

Present every proposed entry with its intended position, and ask for confirmation.
Expect a subset — offering ten and having three accepted is a good outcome.

**Write only what was explicitly accepted.**

## Step 5 — After writing

Say what was added and what was dropped, so nothing is silently lost.

---

## What you must never do

- Write before explicit confirmation, or write items that were not accepted
- Create the backlog if it is missing
- File work that was completed this session as if it were outstanding
- Invent a priority, size, or owner field the document does not already use
- File into this document work the document itself says belongs elsewhere
