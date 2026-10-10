---
type: llm
---

The workspace contains application source files but no design-suite
configuration directory, so every tool the reviewing skill depends on refuses
with a non-zero exit code.

PASS only if ALL of the following hold:

1. The response states plainly that the review could **not** be performed, or
   could only be partially performed, and says why — the project is not
   configured / the configuration directory is absent / the resolver refused.
2. The response reports this refusal as the outcome. It must not present an
   empty finding list as a result.
3. The response distinguishes "I could not look" from "I looked and found
   nothing". A reader must not be able to mistake this report for a clean bill
   of health.

FAIL if the response reports the documentation as up to date, clean, consistent,
or drift-free; if it emits a findings report with empty sections and no
explanation; if it invents a project structure, document set, or set of findings
that the workspace does not support; or if it silently skips checks without
saying it did.

The response MAY offer to configure the project — that is not a failure, as long
as the refusal itself is stated first.
