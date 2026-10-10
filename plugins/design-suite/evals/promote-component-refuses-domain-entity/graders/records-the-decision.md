---
type: tool_used
tool: Bash
input_match: 'audit_promotion_candidates\.py.*--update-baseline'
min: 1
---

The decision to keep it in the app is recorded, not merely stated.

Step 1: "If it stays, run [audit_promotion_candidates.py] --update-baseline so
the decision is recorded rather than re-litigated every push."

This is the effect that distinguishes a considered decline from a shrug. Note
that it is also the one place in this command's body where a baseline write is
the *correct* action — the never-do list forbids baselining a candidate that
was just promoted, which is the opposite situation.
