---
name: audit-doc-staleness
description: "Use when asked how stale a doc is by its own stated date, or before relying on an old doc. Flags docs whose last-updated footer/Date: field is past a threshold. Days since last edit, not proof the doc is still true. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-doc-staleness

You check one narrow, purely textual thing: how many days has it been since a
document's own stated last-updated date? Not whether the document still
matches the codebase, and not whether anyone has actually checked that it
does — this script only reads a date out of the document's own text.

**You report; you do not edit docs without confirmation.**

---

## Step 0 — Preconditions and the claim boundary

`${CLAUDE_PLUGIN_ROOT}/bin/audit_doc_staleness.py` is stdlib-only Python. It
needs no profile section: detection is by content convention (a
`_Last updated: YYYY-MM-DD_` footer, a header `Date:` field, or a "dated
YYYY-MM-DD" phrase), the same kind of convention-by-content
`audit_proposal_status.py` (#51) already uses, whose date-parsing this script
reuses via `backend_suite/engine/dating.py`.

**Before reporting anything, say what this is not.** Issue #84 asked for a
"days since last verified" stamp. This script answers a narrower, cheaper
question — days since the doc was last *edited*, by its own say-so — and the
richer claim ("a human/agent confirmed this doc still matches reality") is
explicitly deferred to `.backend-suite/evidence/<name>.json`
(RFC-0001, Workstream A1/A2), which does not exist yet. Never present this
script's output as verification.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_doc_staleness.py"
```

Pass `--stale-days N` to change the threshold (default 90) and `--dir` to
scope the scan to a subdirectory instead of the whole project.

## Step 2 — Read the outcome

| Outcome | Meaning | Exit |
|---|---|---|
| `stale_by_stated_date` (`should_fix`) | The doc's stated last-updated date is older than the threshold | reported, does not fail |
| `unparseable_date` / `future_dated` (`info`) | A last-updated label exists but its value isn't a real past ISO date — most often an unfilled `<!-- DERIVED -->` template placeholder | reported, does not fail |
| no signal | The doc has none of the recognised date conventions at all | silent — not the same as "fresh" |

Exit code **2** means the audit refused to run: either an empty sweep, or
every scanned doc lacked a parseable date entirely (all placeholders, or a
convention this script does not recognise). That is **not** the same as
"checked N docs, all fresh," and must not be reported as a clean pass.

## Step 3 — Report

Frame every finding as "days since last updated," never "verified" or
"confirmed current." For a `stale_by_stated_date` finding, name the file, the
stated date, and the day count; do not imply the doc's content is wrong —
only that its own stated date is old.

---

## What you must never do

- Call this "verification," "confirmed," or anything implying someone
  checked the doc against reality — it only reads a date the doc states
  about itself
- Report exit code 2 (refused / no signal anywhere) as a clean run
- Treat a doc with no last-updated convention as fresh — it is unscored, not
  passing
- Edit a doc's footer/header date without confirming the correct date with
  whoever owns it
