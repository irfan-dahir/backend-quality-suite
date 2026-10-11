---
name: log-decision
description: "Draft an entry for the project's decision log in that log's own existing format, for review before anything is written. Use when asked to log, record, or write down a decision, or after /session-decisions surfaces one."
argument-hint: "<the decision, in a sentence>"
invocation: explicit
maturity: unverified
---

# /log-decision

> Documents are referenced by role, e.g. `{{doc:decisions}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are drafting one entry for this project's decision log — the document that
explains *why* the implementation differs from the plan.

**Explicit by design.** This writes into the project's most judgment-heavy
document, so it is never automatic and never silent. `/session-decisions` finds
candidates; this drafts one; a human accepts it.

---

## Step 1 — Resolve the log, and stop if it is not there

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions --check
```

| Exit | Meaning | What to do |
|---:|---|---|
| 0 | Mapped and present | Continue |
| 1 | Mapped, file missing | Report it as a project defect. **Do not create the file** — its structure is a project decision, not yours to invent |
| 2 | Not mapped here | Say this project has no decision-log role and stop |
| 3 | Owned by another repo | Say so. Never write into a document this project does not own |
| 4 | Declined here, with a reason on stdout | Say this project has recorded that it keeps no decision log, quote the reason, and stop. Declined is not passed |
| 5 | Mapped to a stub — registered, unwritten | Continue, and say plainly that the log is still a stub, so this entry is the first real content rather than an addition to an existing record |

## Step 2 — Learn the format from the document, do not impose one

**Read the last two or three entries before drafting anything.** Match what you
find: the heading level and grouping, the field set and their order, the tense,
and the typical length.

This step is the whole reason this skill is portable. A template hardcoded here
would produce entries that look foreign in every project that did not happen to
share it — the same coupling the doc-role manifest exists to prevent, moved from
paths into prose. Observed shapes differ widely: some logs use
`Date / Source / Decision / Reason / Impact` under thematic headings and run
several paragraphs; others are one line per decision. Both are correct in their
own document.

Note in particular:

- **Grouping** — if entries sit under thematic headings, find the right existing
  heading before adding a new one
- **Length** — a two-line entry in a log of five-paragraph entries reads as an
  afterthought, and a five-paragraph entry in a log of one-liners reads as noise
- **Sections that recur** — some logs carry a standing "known risk" or "impact"
  section; if the surrounding entries have one, yours needs one

## Step 3 — Draft, with the reasoning as the substance

The decision is the cheap part; the reasoning is what the document exists for.
Cover, in whatever shape the document uses:

- **What was decided**, concretely enough to act on
- **What it was decided against** — the alternative someone would otherwise try
- **Why** — the constraint, failure, or trade-off that drove it
- **What it affects** — files, workflows, other documents

Where a fact is genuinely unknown, mark it explicitly rather than filling it in
plausibly. An entry that quietly invents a rationale is worse than a short one, and
it is unfalsifiable once merged.

**If the log already headings each entry** (rather than one-line-per-decision),
stamp the heading with a ✅ (resolved) / 🔴 (open) marker and a date, the way
`docs/ROADMAP.md`'s own `## Decisions` section does — e.g.
`### ✅ 1 — <decision>`. Match whatever the surrounding entries already do; don't
introduce the marker into a log that has never used one. This is additive, not a
new imposed format: `bin/audit_proposal_status.py` and `bin/query_decisions.py`
both parse this exact convention, and a heading with no marker or date is
invisible to both.

## Step 4 — Show it and wait

Present the draft in full, say exactly where it would go (which heading, before or
after which entry), and ask for confirmation.

**Write only after an explicit yes.** If the answer is a revision, revise and ask
again — do not write a version nobody approved.

## Step 5 — After writing

Say what changed and remind that the log is usually reviewed as part of the pre-PR
checklist in `{{doc:pr}}`.

---

## What you must never do

- Write to the decision log before an explicit confirmation
- Create the decision log if it is missing, or write into one owned by another repo
- Impose a template instead of matching the document's existing entries
- Invent reasoning that was never stated
- Log a decision the document already records — check first
