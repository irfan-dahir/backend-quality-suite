# Eval suite

Cases for `claude plugin eval` (needs Claude Code ≥ 2.1.269). This directory is
the default eval dir; `--eval-dir` or `experimental.evals` in
`.claude-plugin/plugin.json` would move it, and both gates below read the
manifest rather than assuming the default.

```bash
claude plugin eval .                      # run every case (costs model calls)
claude plugin eval . --case 'map-*'       # one family
claude plugin eval . --scaffold           # ALSO run each case's scaffold_script
```

`--scaffold` is **off by default** and runs author-supplied bash as you. Every
fixture below is materialised by a `context.scaffold_script`, so a case that
needs one does nothing useful without that flag.

🔴 **A run without `--scaffold` fails every file grader, and it reads as a skill
defect.** No fixture is built, so each case runs in an empty directory and every
grader with a `{source: file}` target errors with

```
grader threw: grader focus file ".design-suite/profile.json": path ".design-suite/profile.json" does not exist
```

That is indistinguishable, at a glance, from a skill that argued well in chat and
wrote nothing — which is a real failure mode this suite exists to catch, so the
misreading is the expensive kind.

**The discriminator: a `not_contains` grader cannot fail against a file that
exists and does not contain the pattern.** A failing `not_contains` on a file
target proves the *file* was absent. If file graders failed across cases backed
by *different* fixtures — some of which do ship a `.design-suite/profile.json` —
the run is the explanation, not the fixtures. Re-run with `--scaffold` before
editing a fixture, a grader, or the skill.

The result JSON does **not** record whether `--scaffold` was passed, so this
cannot be recovered after the fact once the run's trace directory under `/tmp`
is gone. Run `results/2026-09-18T03-06-49-269Z` is the worked example: all four
`map-project-*` cases lost every file grader this way.

## Results carry the machine they were measured on

A run's `aggregate-result.json` records `suite.root` and every
`suite.plugins[].path` as **absolute paths on the machine that ran it**, and a
grader `evidence` string quotes whatever the agent read — more absolute paths
again. That is a home directory and a username, so a results directory is not
shareable as it lands: attaching one to an issue, a PR comment or a bug report
publishes both.

`.gitignore` covers the commit path (`plugins/*/evals/results/`), which is why
none of this has ever reached history — but an ignore rule does not cover
copy-paste, and `git add -f` overrides it. **Before a run leaves this machine,
replace the home prefix with `$HOME`.** Nothing is lost by doing it:
`bin/eval_results_read.py` re-derives the run directory at read time and never
parses the stored path, so a scrubbed run returns byte-identical verdicts.

## Before quoting a number out of `results/`

```bash
python3 ../bin/eval_results_read.py --latest        # or: <run-id>, --list, --json
```

**Run it before you quote a score, and paste what it says next to the number.**
It is a command, not a gate — `results/` is gitignored (a result embeds the last
message, which quotes the fixture), so there is no committed artifact to gate
against, and a gate that found no results directory would be the exact silence
this suite exists to refuse. The gate count stays at 18. What *is* gated is the
reader's own behaviour: `bin/eval_results_read_test.py` runs under
`run_tests.py`, which `attest.py` wires.

Exit 0 when every case is quotable, 1 when one is not, **2 when it could not
look** — a missing directory, an unparseable `aggregate-result.json`, or a
`schemaVersion` it has not been read against. Never 0 for those.

It withholds a number in four situations, each drawn from a real misquote
(issue #143):

| Withheld | Because | What it must NOT flag |
|---|---|---|
| **ONE-ARMED** — arm with every run at `turns: 0` | the arm ended before turn 1, so every absence grader banked its weight against a transcript that does not exist. All four `promote-component` cases did this in every run they ever produced; the reported +0.33/+0.33/+0.20/0.00 measured nothing | a live arm that merely scored low, or a short-but-nonzero one (3 turns is a run) |
| **VOID** — every run of every arm carries an `error` | #135: 45 runs died on `exit 1: You've hit your session limit` and still carried scores | a case that lost *some* runs — that is noise, reported as a caveat, and the survivors stay quotable |
| **UNQUOTABLE** — `skippedPaidGraders: true`, or a grader whose `explanation` contains `skipped:` | `--max-cost-usd` drops the LLM `criteria` graders and still reports `partial: false`; a skipped grader scores 0, so the case reads as a plugin failure it was never asked about | a grader that merely *failed*. `judge votes: FAIL FAIL FAIL` is the suite working |
| the whole run, on `partial: true` | the aggregates cover only what finished | a complete run |

One deliberate disagreement with the harness: an arm's score here is the mean
over its **live** runs only, where `aggregates` averages the dead ones in too. A
run that produced nothing is not a zero, and averaging it as one is how a broken
arm came to look like a weak one.

## Layout

```
evals/
  _fixtures/build_fixture.py        the fixtures, built by script (see below)
  _fixtures/<name>/scaffold.sh      materialises one fixture into cwd
  <case>/prompt.md                  frontmatter + the prompt
  <case>/case.yaml                  optional; carries context.scaffold_script
  <case>/scaffold.sh                shim that execs the fixture script
  <case>/graders/<name>.md          one grader each
```

## How a case reaches a fixture

🔴 **`context.scaffold_script` may not escape the case directory** — a path
containing `..` or an absolute path is rejected outright. A case therefore
cannot point at `../_fixtures/service/scaffold.sh`.

The working pattern is a shim *inside* the case directory that execs outward:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/../_fixtures/service/scaffold.sh"
```

The shim passes validation because it lives in the case dir; the fixture script
it execs does the reaching. Neither changes directory, so the fixture lands in
the run's working directory.

🔴 **Never put a `case.yaml` or a `prompt.md` anywhere under `_fixtures/`.**
Case discovery walks the whole eval dir, so either file at any depth makes the
suite try to run a fixture as a case. `eval_fixture_selftest.py` fails if one
appears.

## Fixtures

`_fixtures/build_fixture.py <name> --dir <where>` materialises a throwaway
consumer project in a known state. They are **built by script, not committed**,
because a committed `.design-suite/` tree is a photograph of what `init.py`
produced on one particular day: it goes stale silently, and every case built on
it then measures a project shape no real adopter has. The builder calls the real
`init.py`, `decline_doc.py` and `scaffold_doc.py`, so the fixture cannot rot away
from the tools it stands in for.

| Fixture | State it produces |
|---|---|
| `zero-state` | No `.design-suite/` at all — every `bin/*.py` exits 2 via `project_root()` |
| `app` | Scaffolded `app`: one authored doc (exit 0), one real decline with a reason (exit 4), one stub (exit 5). Its screens carry `_StatCell`, a shape-duplicate `_MetricTile`, and the domain-coupled `_OrderSummaryRow` |
| `app-configured` | The same, with profile and arch-rules actually filled in — the `/promote-component` cases need a project whose Step 0 audit can resolve |
| `design-system` | Package-shaped Dart repo, undeclared. Same language as `app`, because it is `app`'s promotion target |
| `design-system-declared` | The same, with `projectKind: design-system` |
| `docs-site` | Declared `docs-site` — owns no role exclusively, so there is nothing to fall through to |
| `undeclared-kind` | `app` with `projectKind` removed. **Both real consumers are in this state today** |
| `pre-ratified` | `app` plus one provenance field at `state: approved` with `by`/`on`/`verifiedAgainst` |

Every fixture's scaffolded `profile.json` has its `_readme` / `_comment` /
`_example` keys stripped. Those keys are prose read by nothing, but the
template's `provenance._readme` spells out the vocabulary — three `approved`,
two `declared` — which would false-fail a `not_contains` grader on a fixture
where nothing is ratified at all. After stripping, `pre-ratified` contains
`approved` exactly once (its real entry) and every other fixture zero times.
Caveat worth knowing: a **real** adopter's profile does contain those words, so
`not_contains: approved` over a whole profile is not a sound field check — the
sound target is `provenance.fields`. The fixtures honour the whole-file form
because the cases are written against it.

`bin/eval_fixture_selftest.py` asserts every one of those states for free, in
CI, before any model is paid to look at a fixture. A fixture that stops
producing its state is INERT — and an INERT fixture does not fail its cases, it
makes them pass while measuring nothing.

## Rules a case must follow

Enforced by `bin/eval_suite_lint.py`, which runs in CI.

1. **Name the case directory after the skill it evaluates** — `<skill>` or
   `<skill>-<variant>`, e.g. `map-project-undeclared-kind`. This is how a case
   is attributed to a component, and an unattributable case fails the lint: a
   case nobody can attribute is a case nobody can tell is guarded.
2. **A case for a skill whose `invocation` is `explicit`** (the writing tier —
   CLAUDE.md sets the tier by blast radius) must carry all four of:
   - a `regex` grader with `match: not_contains` and a pattern naming
     `approved` — the provenance state only a human may author;
   - a **negative** `tool_used` grader with `min: 0` **and** `max: 0`;
   - at least one result grader (`regex`, `file_exists`, `llm`, `baseline`);
   - at least one process grader (`tool_used`, `tool_order`).

   Grant the forbidden tool in `allowed_tools` anyway. A `min: 0, max: 0` grader
   that passes because the tool was never in reach is the audit that reports
   nothing on a codebase it never read.
3. Grader `type` must be one of the six the harness knows: `regex`,
   `tool_used`, `tool_order`, `file_exists`, `llm`, `baseline`. A typo is a
   grader that silently does not run.

The result/process split in rule 2 is *this repo's* vocabulary, inferred from
the grader type — the harness defines no such key, and inventing a frontmatter
key it does not know risks the grader being rejected.

## Writing a prose negative control (issue #136)

Not lint-enforced, and deliberately so — see the bottom of this section. It is
still the rule with the worst measured cost in this suite.

**A prose negative control must detect the ACT, not the TOPIC.** A keyword
pattern over the last message detects what the response is *about*. A correct
refusal is about the forbidden thing constantly — that is what makes it a
refusal. And only the plugin arm has read the skill that supplies the
vocabulary, so a topic-matching grader penalises the arm that behaved
correctly, and the result reads as the plugin making the model worse.

This is not hypothetical. `bootstrap-design-docs-undeclared-kind-stops-to-ask`
scored **Δ −0.22 in favour of the no-plugin arm**, and the entire delta was one
grader — `(assum|default|treat)\w*[^.\n]{0,40}\bapp\b` — which fires on 13 of 17
correct-refusal phrasings, including *"I did not assume the `app` archetype"*,
and on the skill's own instruction ``Do not assume `app` ``. The only phrasing
that stayed clean described the refusal *without* the skill's vocabulary: the
grader rewarded not having read the skill.

The shape that works — the frame used by every fixed grader here:

```
sentence start  +  a run of characters containing NO negator or hedge  +  the claim
```

Negators and hedges: `not`, `n't`, `never`, `cannot`, `no`, `nothing`, `none`,
`neither`, `nor`, `without`, `rather`, `instead`, `unless`, `whether`, `if`,
`would`, `could`, `refuse*`, `declin*`. Anchoring at a sentence start is what
stops `I cannot say the project is now documented` from counting, and the
negator-free run is what stops `I have not marked them as approved`.
`review-docs-zero-state-refusal/graders/no-clean-verdict.md` carries the worked
form, with the measurement in its body.

**Two checks before shipping one:**

1. **Both polarities, as numbers.** Write out the phrasings where the model did
   the forbidden thing and the phrasings where it correctly refused *and said
   so*. Run the pattern against both. Report the hit rate on each side. The
   target is every violation caught and zero refusals fired on; anything else
   is a measurement of the grader, not of the skill.
2. **Grep the pattern against its own skill.** `commands/<skill>.md`, or
   `agents/<agent>.md` for an agent case. A hit means the grader can fire on a
   model quoting or paraphrasing its own instructions.

   One exception, and only one: a pattern anchored to a **literal structured
   report field** may legitimately match the skill's report template, because
   emitting that template line verbatim *is* the violation.
   `Overall Recommendation:\s*PASS` is the example — it matches
   `agents/design-auditor.md` and is correct as written (0 of 6 correct-refusal
   phrasings).

Where a regex genuinely cannot separate the act from the topic, **use an `llm`
grader with an explicit `PASS only if` clause** —
`design-auditor-undeclared-kind/graders/criteria.md` is the model — rather than
shipping a pattern you know is wrong. Never weaken the assertion to make it
green: the point is that it asserts the right thing, not that it is passing.

### Why this is not a lint rule

The obvious gate — flag any `not_contains` pattern that matches its own skill's
markdown — was assessed and rejected on measurement, not on cost. It is cheap
to build: the case-to-skill mapping is already there in the directory name that
rule 1 above enforces. It is the false-positive rate that fails. Run against the
suite as it now stands, it flags **4 of the 12 prose negative controls, and all
4 are correct** — three `Overall Recommendation:\s*PASS` graders matching the
report template they are deliberately quoting, and `no-clean-verdict` matching
two lines of narrative past-tense prose in `review-docs.md`. Zero true
positives, four false ones. A gate whose every finding is wrong teaches people
to ignore it, so this stays prose here and an entry in `known-traps.json`
(`polarity-blind-negative-control`), which is where judgment-call traps live.
