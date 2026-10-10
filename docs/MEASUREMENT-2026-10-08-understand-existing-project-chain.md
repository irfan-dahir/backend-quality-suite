# Measurement — `understand-existing-project` run end to end, 2026-10-08

**What ran:** the chain `templates/chains/understand-existing-project.json`
(survey → `init --from-survey` → map-project → bootstrap-design-docs →
repo-health), two ways, against public open-source code only. No client or
company project was touched. Suite under test: branch
`fix/issue-0-existing-project-chain-e2e`, cut from `main` @ `2cfe39a`.

## Subjects

Each was shallow-cloned into a `mktemp -d /tmp/...` directory, its sub-app copied
out and `git init`-ed so it stood alone as a project root.

| Subject | Source | Commit | Licence |
|---|---|---|---|
| React/Vite app | `github.com/alan2207/bulletproof-react`, `apps/react-vite` | `9506629ed003a561c6627735480cce4994244bb4` | MIT |
| Flutter app | `github.com/flutter/samples`, `compass_app/app` | `5541c59ab8e9d7e74c1a35ef22bd43a487fc596c` | BSD-3-Clause |
| Synthetic | hand-built: `package.json`, `src/components/Button.tsx` with two hardcoded values, `src/tokens.css`, `docs/DESIGN.md` | — | — |

(`flutter/samples/veggieseasons` was tried first; at that commit it is a README
only, and the survey correctly reported 1 file and no stack.)

## 1. Scripted — each step's backing scripts, as the docs instruct

All three subjects. Before the fixes on this branch, the chain **could not get
past step 2 on any of them**:

| # | Where | What happened | Fix |
|---|---|---|---|
| 1 | `bin/chain.py status/next` | Exit 2 "Refusing to guess" on a project with no `.design-suite/` — the exact state this chain starts in, so `/run-chain` could not show step 1 | Read-only actions resolve like `survey.py`; writing actions still require the marker (`chain_test.py` `UnconfiguredProject`) |
| 2 | `bin/init.py --from-survey` → `bin/map_project.py` | init stamped `value` + `verifiedAgainst` on every `inferred` entry; map_project's serialised-bytes audit refuses any inferred entry carrying them, so **every** proposal on a freshly seeded profile exited 2 as "a defect in map_project.py" | init writes `{state, evidence}` only (survey commit folded into evidence); map_project audits only the entries it wrote this run (`init_from_survey_test.py`, `map_project_test.py` legacy case) |
| 3 | `bin/resolve.py --all` (bootstrap Step 0) | Roles init registers by default (`backlog`, `decisions`, `flows`, `design`) listed unmarked and exit 0 although their files do not exist — reads as "already documented"; `--check` silently ignored with `--all` | `--all` marks `(missing)`; `--all --check` exits 1 (`resolve_test.py`) |
| 4 | `commands/bootstrap-design-docs.md` | Step 0 used `--all` (see 3); its worked example proposes `tokens`, which `scaffold_doc.py` refuses for an `app` | Step 0 uses `--all --check`; example labelled design-system-only |
| 5 | chain `health` step | Claimed "writes nothing"; repo-health leaves `token_pipeline/findings.json` (quotes source, not gitignored) at the project root | Stated in `purpose`, which `chain.py next` prints (`checkpointReason` is not printed) |

After the fixes, all four steps completed on all three subjects; `chain.py status`
ends with every step ✅.

## 2. Real session — `claude -p --plugin-dir <worktree>/plugins/design-suite`

On a fresh copy of the React/Vite subject. `--allowedTools` is ignored under this
machine's managed settings (`allowManagedPermissionRulesOnly`), so the first
session stopped before running anything and asked for approval — reported, not
bypassed. The rest ran under `--permission-mode auto`; six `-p` sessions in all,
chained with `--continue`.

| Session | Prompt | Observed |
|---|---|---|
| 2 | `/design-suite:run-chain understand-existing-project` | Showed status, put step 1's decision point, **wrote nothing** (`.design-suite/` absent afterwards) |
| 3 | "yes" | Survey ran; step left `⏸ awaiting sign-off`, not acked by the model |
| 4 | "confirmed, ack; yes to init + map" | init scaffold + 5 argued `inferred` proposals + 6 refusals with what would settle each; every provenance entry `{state, evidence}`; step 2 left `⏸` |
| 5 | "ack; propose one doc, I accept" | `docs/DESIGN.md` scaffolded as a stub (exit 5); the model left step 3 pending because the user said "stop and ask" |
| 6 | "close step 3, ack; run health" | repo-health ran; final status all ✅ |

Result: a usable `.design-suite/` (10 config files, 0 of 25 fields ratified — as
designed), one stub context document, and a health dashboard. Checkpoints held:
no step advanced without a separate user turn. Session 6 ran before the `purpose`
fix in row 5 and did not mention `token_pipeline/findings.json`.

## What this does and does not prove

The bar (`docs/CONCEPTS.md`, Maturity): `proven` = "Recorded evidence of a real
end-to-end run"; ROADMAP A2 adds "naming what ran, when, and against which
project". **Nothing is promoted.** These subjects are public reference/sample
apps, not projects that adopted the suite; checkpoint answers came from the
agent running the measurement, not from the owning team; and bootstrap-design-docs
only produced a stub — no document was authored from reverse-engineered content.
That is a real run of the chain's mechanics, not the "real project" the bar
describes. `run-chain` stays `experimental`; survey, map-project,
bootstrap-design-docs and repo-health stay `unverified`.
