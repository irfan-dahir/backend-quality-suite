---
name: audit-proposal-status
description: "Use when asked whether a proposal's status is current, or before relying on a roadmap/proposal doc's header. Checks the header's open-question count and framing against its own Decisions section markers; a cheaper, one-document /review-docs. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-proposal-status

You check one narrow thing: does a proposal document's own stated status still
match what the document's own body says has actually been resolved? Not
whether the document is stale relative to the codebase — that is
`/review-docs`. Not whether an external condition the document names (a
roadmap gate, say) has actually happened — this cannot see the codebase or its
history, and says so rather than guessing.

**You report; you do not edit docs without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_proposal_status.py` is stdlib-only Python. It
needs no profile section: detection is by content convention (a header naming
itself a proposal, a `Status: open|resolved|superseded` field, or a stated
open-question count, checked against 🔴/✅-marked headings under a `##
Decisions` section), not by a project-specific vocabulary.

It prefers `docs/proposals/**/*.md` when that directory exists, and otherwise
degrades to scanning every markdown file in the project — announcing that
degradation on stderr, per this plugin's rule that a fallback must say so
rather than quietly changing scope.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_proposal_status.py"
```

## Step 2 — Read the two tiers, and the refusal

| Tier | Meaning | Exit |
|---|---|---|
| `critical` (`count_mismatch`, `reverse_claim`) | The header's count or resolved/open claim does not match what the Decisions section's 🔴/✅ headings show | **fails** |
| `should_fix` (`stale_framing`, `unverifiable_claim`) | Internally consistent but the header's framing has not caught up with its own resolved body, or the header makes a claim with no Decisions section to check it against | reported, does not fail |

Exit code **2** means the audit refused to run — zero proposal-shaped documents
found (or an empty sweep). That is **not** the same as "checked N, found
nothing wrong," and must not be reported as a clean pass.

## Step 3 — Report

🔴 for critical, 🟡 for should-fix, one finding per bullet naming the file and
what disagreed. For a `stale_framing` finding that also names a downstream
gate condition, say plainly that whether the gate itself has been met is
outside what this audit checked, and offer to verify it by hand (e.g. against
git history) rather than asserting either way.

---

## What you must never do

- Treat a `stale_framing` finding as proof that a downstream gate condition
  has or has not actually been met — this audit only compares the document to
  itself
- Report exit code 2 (refused) as a clean run
- Edit the document's header or Decisions section without confirming the
  correct status with whoever owns the decision
