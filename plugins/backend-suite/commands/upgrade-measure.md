---
name: upgrade-measure
description: "Use before upgrading the suite in a project, or on a suite PR before merging. Runs both versions' audits on throwaway copies and diffs exit codes and finding counts, checks two revisions for consumer breaks, and lists which projects are on which version. Read-only: never writes to the measured project."
invocation: auto
maturity: unverified
---

# /upgrade-measure

> Documents are referenced by role, e.g. `{{doc:decisions}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions`. See
> `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work.

This is the **read-only** half of the upgrade capability. It measures; it never
migrates. Applying a migration is `/upgrade-apply`, which is `explicit` precisely
because it writes to a project's config — the split exists so that finding out
what an upgrade costs never risks starting one.

It is `auto` for the same reason every audit is: nothing it does can be undone,
because nothing it does changes anything.

---

## Why this exists

A merge to `main` reached live client CI carrying four changes, each defensible
on its own:

* `audit_tokens.py` stopped always returning 0 and started returning 1 when it
  had findings.
* `audit_error_handling.py` widened from failing on critical findings only to
  failing on any finding.
* `audit_accessibility` and `audit_copy` entered
  `audit_discovery.DISABLED` and now exit 2.
* `--update-baseline` stopped absorbing new findings without `--accept-new`.

Every consumer's CI went red on a tree that had not changed, and no surface
warned anyone. That is what this measures, and `compat` below is what would have
caught it before the merge.

## Step 0 — Which of the three questions is being asked

| The question | The subcommand |
|---|---|
| "What would upgrading *this project* cost?" | `measure` |
| "Would merging *this PR* break consumers?" | `compat` |
| "Who is on what version?" | `fleet` |

All three are read-only. All three use the same exit codes: **0** nothing to
report, **1** something to report, **2** could not determine.

**Exit 2 is never a pass and never a clean bill of health.** A compatibility
check that could not read the old revision has not told you the versions are
compatible — it has told you it could not look. Report the reason verbatim.

## Step 1 — Measure one project

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/suite_upgrade.py" measure \
  --consumer <project root> --from <old rev> --to <new rev>
```

`--consumer` comes from the argument or from what the user named. **Never
hardcode a project path**, here or anywhere: the consumer is an argument, per
this suite's no-project-literals rule.

Both versions' audits run against **throwaway copies** of the project tree, made
under the system temp directory and named in the report. The project's own
directory is read once, to copy it, and never written to. That is not a courtesy:
most audits write a findings envelope by default, so measuring in place would
overwrite the envelopes `/quality-debt` grades, with output from a version the
project has not adopted. The report says which copies it used — quote that line,
so the reader can verify the claim rather than trusting it.

Reading the table:

* `unchanged` — the same verdict and the same count under both versions.
* `count-changed` / `exit-changed` / `status-changed` — **the upgrade's cost.**
  The tree did not change, so any difference here is the new version's opinion,
  not a regression the project introduced. Say it that way.
* `no-answer-either-side` — both versions refused, were disabled, or were absent.
  Two silences are not an agreement that the project is clean. Never present this
  as `unchanged`.
* `disabled` — switched off suite-wide; it tells you **nothing** about the
  project. Report it as a gap in coverage.

## Step 2 — Check a suite PR before it merges

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/suite_upgrade.py" compat \
  --from <base rev> --to <head rev>
```

Categories, and what each one means for somebody downstream:

| Category | What breaks |
|---|---|
| `exit-contract-changed` | The set of exit codes a script can reach changed (including `raise SystemExit("msg")` = 1 and `raise Refused(...)` = 2), the condition choosing between them changed, or the number of places that exit non-zero changed. A library module's change is graded by the audits that import it. A consumer grading it by exit code gets a different verdict on an unchanged tree |
| `audit-newly-disabled` | The audit now exits 2 everywhere it is invoked — a hook map, a CI step, a runbook |
| `config-key-newly-required` | Profiles that validated no longer do. `critical` when the section is one every profile carries; `should-fix` when it binds only a project that declared an optional section — and that project breaks completely |
| `script-removed` / `flag-removed` | An existing invocation fails to start, or argparse exits 2 on a flag that used to work |
| `output-path-moved` | The default of an `--out`-style flag or a `*_OUT` path constant changed. Anything reading the old location reads a file that is no longer written |
| `new-gating-flag` | A script gained a flag *and* a refusal path in the same revision — the shape of an action that now refuses until a new word is added. Suggestive, not conclusive: check it, don't assume it |

A finding here is **not** an instruction to revert. It is an instruction to say
so in the PR description, and to tell the fleet before they reinstall.

## Step 3 — See the fleet

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/suite_upgrade.py" fleet
```

Reads the same install registry `bin/installed_drift.py` reads, and folds agent
worktrees back into the project they belong to — a registry entry per worktree
is not a project anybody upgrades. The report prints both numbers (projects, and
the registry entries they were folded from) so the fold is visible rather than
silent.

An empty fleet is **exit 2, not "zero projects"**: an unreadable registry and a
fleet with nothing in it must not read the same.

`installed_drift.py` remains the tool for the adjacent question — whether a given
project's *installed* plugin matches what the repo ships. Run it when a command
a user names does not exist for them.

## Step 4 — Report

State, in this order: which projects are affected, what each would cost, and what
could not be determined. Never present an exit 2 as either a pass or a failure of
the project — it is a failure to look.

---

## What you must never do

- Run any of this against a project's tree in place, or pass `--consumer` a path
  the user did not name
- Report exit 2 as "compatible", "clean", or "no findings"
- Present `no-answer-either-side` or `disabled` as an audit that passed
- Begin applying a migration from this command — that is `/upgrade-apply`, and it
  is explicit for a reason
- Hardcode a consumer project's path, name, or layout anywhere
