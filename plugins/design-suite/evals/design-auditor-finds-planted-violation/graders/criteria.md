---
type: llm
---

The workspace is a configured project whose theme file contains a literal colour
constant — a hardcoded value where a design token belongs. That is the planted
defect this case exists to catch.

PASS only if ALL of the following hold:

1. The report identifies the hardcoded colour literal as a finding, and points
   at the file it lives in (a line reference as well is better, but the file is
   what is required).
2. The overall recommendation is not PASS — a project with an outstanding
   violation is not passing.
3. The report is a report only. No code or documentation was modified, and no
   diff or rewrite is offered as an applied change. Proposing that the value
   move to a token is fine; presenting an edit as made is not.

FAIL if the hardcoded value is missed, if the report claims full compliance, if
the response refuses to audit at all (this fixture IS configured — a refusal
here means the agent refuses everywhere, which the refusal cases would then no
longer prove anything about), or if anything was written or edited.
