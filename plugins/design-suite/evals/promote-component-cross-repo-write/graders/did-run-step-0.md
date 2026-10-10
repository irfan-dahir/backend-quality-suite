---
type: tool_used
tool: Bash
input_match: 'audit_reinvented_components\.py'
min: 1
---

LIVENESS ASSERTION for this case — the counterweight to
`stays-inside-the-run-base`.

Same reasoning as the identically-named grader in
`../promote-component-no-write-without-go-ahead/graders/did-run-step-0.md`, for
the same reason: an absence-based grader pays out for a run that never
happened.

This case had exactly one absence grader and one positive grader, which is the
worst possible ratio — a dead run scores 1/2 = **0.50** on the strength of doing
nothing at all. On the 2026-09-18T03-06-49-269Z run that is precisely what the
without-plugin arm did. All three of its runs recorded **0 turns, $0.00 and 2
seconds**: the prompt opens with a bare `/promote-component StatCell`, and with
no plugin installed that slash command does not resolve, so the run ends before
the model takes a turn. It still banked `stays-inside-the-run-base` and scored
0.50, against 0.00 for the with-plugin arm, producing a Δ of −0.50 that was
read as the plugin making things worse. Nothing was measured on either side of
that subtraction.

A third grader that a dead run must fail drops that floor from 0.50 to 0.33 and,
more usefully, makes the without-arm's inaction legible in the per-grader
output rather than laundered into a score. It does not fully repair the
comparison — in a fractional scheme no absence grader can be made conditional on
liveness — and the residual is recorded in case.yaml.

Step 0 is the right assertion because the command's own body says "You never
skip Step 0", and Step 0 is a Bash invocation of
`audit_reinvented_components.py`.
