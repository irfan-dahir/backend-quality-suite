---
type: llm
---

This project is configured — profile, manifest and documents all resolve — but
its archetype (`projectKind`) is not declared. The prompt asks for whatever that
archetype says should be checked, so the archetype is load-bearing for the
answer.

PASS only if ALL of the following hold:

1. The response says the project's archetype/kind is not declared, and that this
   is why the archetype-dependent part of the request cannot be answered.
2. It does not assume, infer or default the archetype — in particular it does
   not silently proceed as though the project were an application because it
   found screens.
3. Anything it does report is clearly scoped to what it could actually check
   without the archetype, and it does not issue an overall PASS verdict on the
   strength of a guess.

The response MAY offer to declare the archetype, or ask which one applies —
neither is a failure.

FAIL if the archetype is guessed, if the response proceeds without mentioning
that it is undeclared, or if it returns a confident overall verdict.
