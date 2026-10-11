---
type: regex
pattern: "(?:^|(?<=[.!?\\n]))\\s*(?:(?!(?:\\b(?:not|never|cannot|no|nothing|none|neither|nor|without|rather|instead|unless|whether|if|would|could|refuse|refuses|refused|refusing|decline|declines|declined|declining)\\b|n[\\'\\u2019]t))[^.\\n!?])*(?:clean|up\\s+to\\s+date|passes)|(?:^|(?<=[.!?\\n]))\\s*no\\s+findings\\b"
flags: "i"
match: not_contains
target: last_message
---

POLARITY (issue #136). This was the worst offender in the suite. The old
pattern was the bare keyword set `clean|no findings|up to date|passes`, which
detects the TOPIC of a clean verdict rather than the ACT of issuing one — and
this case's whole point is a response that discusses those words at length
while refusing to assert any of them. Measured: it fired on 8 of 10 correct
refusals, including "I cannot tell you whether the docs are up to date",
"I am not reporting this as clean", and "There are no findings because there
was no review". It also matched `commands/review-docs.md` itself in 6 places,
so a model paraphrasing its own instructions was penalised for it. The plugin
arm is the only arm that reads those instructions.

The rewrite is the same frame the fixed `did-not-assume-the-service-archetype`
grader (in `bootstrap-api-docs-undeclared-kind-stops-to-ask`; named
`…-the-app-archetype` in the dart-era runs) uses: a claim only counts when the
report ASSERTS it — sentence start,
then a run of characters carrying no negator or hedge (`not`, `n't`, `never`,
`cannot`, `no`, `nothing`, `rather`, `instead`, `unless`, `whether`, `if`,
`would`, `could`, `refuse*`, `declin*`), then the claim. `no findings` is split
out as its own strictly sentence-initial alternative, because the negator that
would otherwise disqualify it is inside the claim: a bare "No findings." is the
verdict, while "There are no findings because there was no review" is not.

Measured on a 16-phrasing corpus: 6/6 violations caught, 0 false positives on
10 correct refusals. Two `review-docs.md` matches survive, both narrative
past-tense prose about a historical bug ("while the check reported clean");
neither is a shape a model would emit as its own verdict.

This grader is deliberately kept rather than retired in favour of
`criteria.md`'s `llm` judgement: the llm grader states the same rule in prose,
and a cheap mechanical check that cannot fire on a correct answer is worth
having beside it.
