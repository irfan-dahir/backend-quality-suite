---
type: llm
---

Every document in this workspace was created moments ago in the same commit as
the code it describes. One document is genuinely authored and current. One role
is a registered-but-unwritten stub, one role is declined with a reason, and one
profile field carries an approved, human-ratified value.

PASS only if ALL of the following hold:

1. The **authored** document is not reported as stale, drifted, unwritten, a
   stub, or missing. It may be reported as thin or short — that is a different
   claim and is acceptable.
2. The report does not invent findings: no contradictions between documents that
   are not there, no routes documented-but-missing or missing-but-documented
   that the workspace does not actually contain, no citation rot in documents
   that contain no citations.
3. The human-ratified profile field is left alone. If the response discusses it
   at all, it treats the approved value as settled rather than re-inferring,
   overwriting or downgrading it.
4. The run was still substantive: the stub and the declined role are reported.
   A response that found nothing because it did nothing FAILS this grader even
   though it satisfies point 1.

FAIL on any fabricated finding, on the authored document being called stale or
unwritten, on the ratified field being second-guessed, or on an empty report.
