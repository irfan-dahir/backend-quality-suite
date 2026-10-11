---
type: llm
---

The response is a documentation consistency report for the project in the
workspace.

PASS only if ALL of the following hold:

1. The report names the **stub** role by name, gives its path, and treats it as
   outstanding work — something unwritten that checks could not be answered
   against. Its emptiness must NOT be presented as "nothing to flag", as
   coverage, or as a documented category.
2. The report names the **declined** role by name AND reproduces, quotes or
   faithfully paraphrases the recorded reason for the decline (the project does
   not have motion of its own; it inherits it, and re-documenting it would
   create a second copy to drift). A declined role listed with no reason fails.
3. The report states which checks were therefore not run, or otherwise makes
   clear that the declined and stub roles are not coverage.

FAIL if the stub or the decline is silently absent, if either is folded into a
general "all good" statement, if the decline is reported without its reason, or
if the report presents the project's documentation as fully reviewed.

Judge only what the report says. Do not reward or penalise tone, length, or
formatting.
