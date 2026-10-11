# Eval cases: `/bootstrap-design-docs` and `/map-project`

Eleven cases covering the two highest-blast-radius skills in the suite. Both ship
`maturity: unverified`; these cases are what a promotion off `unverified` would
have to clear first.

| Case | Skill | The rule it holds |
|---|---|---|
| `bootstrap-accept-one-document` | bootstrap | one accept → exactly one scaffold, one stub |
| `bootstrap-decline-names-reason` | bootstrap | a decline is recorded with its reason, and scaffolds nothing |
| `bootstrap-stub-is-debt-not-coverage` | bootstrap | a stub reports as outstanding work, never as coverage |
| `bootstrap-undeclared-kind-stops-to-ask` | bootstrap | no `projectKind` → say so and stop; never assume `service` |
| `bootstrap-na-role-never-proposed` | bootstrap | a role `na` for the archetype is refused even when asked for by name |
| `bootstrap-anti-loop-guard` | bootstrap | 🔴 no bulk scaffolding, no `for role in …`, no `roles_for(` loop |
| `map-project-inferred-only` | map-project | proposals land `inferred`; no `by`/`on`/`value`/`verifiedAgainst` |
| `map-project-preserves-ratified-field` | map-project | a ratified field is neither deleted nor duplicated (`count:1`) |
| `map-project-refuses-tied-candidates` | map-project | equal candidates → refuse, and name what would settle it |
| `map-project-chat-yes-is-not-ratification` | map-project | 🔴 "yes, that's right" in chat never becomes `approved` |
| `map-project-zero-state-refuses` | map-project | 🔴 no `.backend-suite/` → refuse legibly; never scaffold one to write into |

---

## 🔴 How to run these, and how a green here can lie

```bash
claude plugin eval . \
  --case 'bootstrap-*' \
  --scaffold \
  --allow-tools Bash Write Edit \
  --runs 1 --ablation none --no-publish -j 1
```

**`--scaffold` and `--allow-tools Bash Write Edit` are both mandatory.** This is
the governing principle applied to the test harness itself:

- Without `--scaffold` the case's `scaffold_script` never runs, so the workspace
  is empty and the skill is auditing nothing.
- Without `--allow-tools Bash Write Edit` the model never receives those tools.
  Every `tool_used … max: 0` assertion in this suite — which is most of the
  load-bearing ones — then passes **vacuously**: the scaffolder was never
  reachable, so of course it was never called. A suite that scores 1.00 because
  the agent could not act is indistinguishable from a suite that scores 1.00
  because the skill behaved, and that is the failure this repository exists to
  refuse.

The harness does emit a pre-flight warning for the second case
(`grader "…" cannot pass with the granted tools: … add Bash to the case's
allowed_tools and grant it with --allow-tools Bash`), but it is a **warning, not
an abort** — the run proceeds and scores. Read it.

Two further notes on any run:

- The plugin declares an MCP server (`backend-suite-audits`) with no mock, so the
  harness withholds it. None of these eleven cases needs it; every skill step
  here goes through `Bash` and `python3`.
- **A case's fixture has to be able to satisfy its own graders.**
  `map-project-inferred-only` ran against `zero-state` until 2026-09-24 and
  scored 0.17 on both arms because of it: nine of its graders target
  `.backend-suite/profile.json`, which that fixture deliberately does not ship
  and which the skill is forbidden to create. It now uses `undeclared-kind`,
  and `zero-state`'s job here is `map-project-zero-state-refuses`. See that
  case's `scaffold.sh` for the argument, including why neither case scaffolds a
  fixture of its own. A case whose fixture makes a grader unpassable fails both
  arms equally, so nothing in a results summary distinguishes it from a skill
  that simply did badly.
- These cases score effects, never prose *alone*. Each one pairs a positive
  assertion (a file written, a script invoked, a field present) with at least one
  negative control (`max: 0`, `not_contains`, or a `count:N` that fails on both
  deletion and duplication), because a suite that can only pass is not a test.

## Fixtures

Cases reference shared fixtures in `evals/_fixtures/<name>/scaffold.sh`, owned
separately from these cases.

`context.scaffold_script` **must name a path inside the case directory** — the
harness rejects `..` and absolute paths outright:

```
path "../_fixtures/service/scaffold.sh" escapes the case directory
(`..` or an absolute path) — it must name something inside it
```

So each case carries a two-line `scaffold.sh` shim that `exec`s the shared
fixture builder. The shim resolves the fixture from its own location, not from
the working directory. Do not turn the shims into fixtures — a fixture copied
per case is a fixture that drifts per case.

## On multi-turn

Both skills are multi-turn by design (accept/decline; per-field ratification).
`context.history_file` exists and would be the right mechanism, but its `.jsonl`
schema is **not documented** in `claude plugin eval --help`, in `init --bare`'s
template, or anywhere else reachable — the only mention in the binary is the
validation message `context.history_file requires execution.prompt`. Rather than
guess at a transcript format and ship cases that fail for the wrong reason,
every case here is single-turn and **carries the human's answer inside the
prompt** ("Answering ahead of time: I accept the first document you propose").

That is a real reduction in fidelity and worth naming: it tests whether the
skill honours a decision, not whether it correctly *elicits* one turn at a time.
When `history_file`'s schema is documented, `bootstrap-accept-one-document` and
`bootstrap-decline-names-reason` are the two to convert first.
