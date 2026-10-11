---
name: survey
description: "Survey an unknown project — detected stack, candidate source roots, ranked candidate token sources, a document inventory with proposed roles, and an explicit list of what could not be determined. With --check, diff what is on disk against what the config declares, the one direction no existing check runs. Read-only: writes only .backend-suite/survey.json, and --check, --stdout and --json write nothing, and a default run writes only .backend-suite/survey.json, creating that directory if it is absent."
invocation: auto
maturity: unverified
---

# /survey

> Documents are referenced by role, e.g. `{{doc:design}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

Two jobs, one script. **It modifies nothing that already exists.** A default
run writes one file — `.backend-suite/survey.json`, a derived collateral —
creating the `.backend-suite/` directory if it is absent, which is the one thing
it adds to a tree beyond that file. `--check`, `--stdout` and `--json` write
nothing at all and create no directory, so those are the forms to point at a
repository you do not own.

You never write the survey's conclusions into `profile.json`,
`docs.manifest.json`, or any context document. That direction is the one rule a
derived collateral has.

---

## Step 1 — Which half you need

**`--check` first, on a project that already has a `.backend-suite/`.** It is the
cheaper and sharper of the two: it reports what is on disk that no config file
mentions. Every `doctor.py` check runs declared → disk and is blind by
construction to anything *added* — an addition is not a broken path, it is the
absence of one.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py" --check
```

**The full survey on a project you are onboarding**, or when the stack, source
roots or token source are what you need:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py"
```

The full survey needs no `.backend-suite/` — an unconfigured project is the case
it exists for. With no `--project-root` it surveys `CLAUDE_PROJECT_DIR` if set,
else the git root of the working directory, else the working directory. It never
walks up to the nearest configured repo: if the working directory is outside
`CLAUDE_PROJECT_DIR`, or is not in a git repo but sits under a directory that has
a `.backend-suite/`, it exits 2 and names both rather than surveying the wrong
codebase. Check `sourceStamp.projectRoot` in the output before trusting it.

`--check` is the opposite: it compares disk against an existing config, so on a
project with no `.backend-suite/` it refuses with exit 2 and says so.

Both take `--project-root` to survey somewhere else, and `--json` for
machine-readable output.

Exit codes: **0** clean, **1** findings, **2** it refused — the project declares
nothing to diff against, or the question could not be answered. A 2 is never a
pass.

## Step 2 — Read `--check` output as claims, not chores

Each finding is a directory the configuration does not know exists. Two kinds,
and they deserve different responses:

- **`undeclared-top-level-directory`** — usually either genuinely out of scope
  (a hosting directory, CI config) or a real gap. The ones with
  **`proseMentions`** are the sharp ones: a config *sentence* talks about the
  path while no config *field* declares it. If that sentence asserts the
  directory does not exist, you are looking at an assertion the disk contradicts
  — which is worse than a gap, because it reads as a considered decision.
- **`undeclared-sibling-directory`** — a config names one member of a directory
  and not its siblings. Naming one member is an implicit completeness claim
  about the rest; the audits scoped by that field skip everything else in there.

Do not "fix" these by adding paths to the profile on your own judgement. Report
them, say which are real, and let the owner decide. A directory deliberately out
of scope should be recorded as such, with a reason — otherwise the next run
reports it again and the run after that is ignored.

## Step 3 — Read the survey as candidates, never conclusions

Three fields are deliberately hedged, and the hedging is measured, not modesty:

- **`stack.fileCensus` never votes.** A committed documentation build makes a
  census read a Dart repository as JavaScript. The manifest decides.
- **`candidateTokenSources` is ranked and plural.** An earlier detector matched
  the token audit's own output file, and on both real consumer projects the true
  token source is not in the repository at all — it arrives as a package
  dependency. `tokens.source` stays human-approved.
- **`documents[].proposedRole` is `inferred` and confidence-scored per
  document.** Choosing between four plausible `design` documents is judgement,
  not a filename match, and it is not this script's job.

## Step 4 — `couldNotDetermine` is the most important field

Read it first and repeat it in your report. A survey with nothing in it that
determined everything and a survey that never ran produce the same short file
unless this list is present — which is this repo's governing principle applied to
discovery. If the survey says it could not determine the stack, you do not pick
one.

## Step 5 — Report

State, in order: what `--check` found and which findings are real; what the
survey determined; what it explicitly could not; and what the next human decision
is. Never present an inferred value as a fact, and never offer to write one into
the profile — that is `init --from-survey`'s job, once it exists, and it lands
values as `inferred` for a human to ratify.
