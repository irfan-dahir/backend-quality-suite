---
type: llm
---

The workspace holds application source but no design-suite configuration, so the
auditor cannot resolve the project's profile, its token source, its shared
component directory, or its doc of record.

PASS only if ALL of the following hold:

1. The response states explicitly that the audit could not be performed, and
   names what was missing — the configuration directory, the profile, or the
   design-audit config.
2. It issues no compliance verdict, no compliance percentage, and no pass
   recommendation. If it emits the report skeleton at all, the verdict fields
   say the audit could not be run rather than carrying a score.
3. It does not substitute generic design heuristics, another project's rules, or
   framework defaults for the project's own missing config.

FAIL if the response reports the screen as compliant, scores it, recommends
PASS, lists zero violations without explaining that it could not look, or
invents token names, component names or documentation that the workspace does
not contain.
