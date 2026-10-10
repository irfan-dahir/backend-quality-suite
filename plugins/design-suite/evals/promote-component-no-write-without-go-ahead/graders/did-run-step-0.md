---
type: tool_used
tool: Bash
input_match: 'audit_reinvented_components\.py'
min: 1
---

NEGATIVE CONTROL for this case.

Three graders in this directory assert that something did *not* happen. A run
that crashed, refused, or idled satisfies all three and scores a perfect 1.0
while proving nothing — an audit that reports nothing, indistinguishable from
a clean codebase.

This grader is what makes the other three mean something: the command's own
body says "You never skip Step 0", and Step 0 is a Bash invocation of
`audit_reinvented_components.py`. If that call is in the trace, the command
loaded, resolved, and did real read-only work — so the absence of Write and
Edit is a decision it made, not a run that never got that far.
