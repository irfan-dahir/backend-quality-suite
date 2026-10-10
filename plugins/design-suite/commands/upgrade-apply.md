---
name: upgrade-apply
description: "Use only when explicitly asked to apply or migrate a suite upgrade, after /upgrade-measure and human approval. Syncs the profile schema copy, scaffolds a missing hooks map, names newly-required keys, re-baselines reviewed findings. Writes to .design-suite/, one refusable action at a time; never rewrites profile.json."
invocation: explicit
maturity: unverified
---

# /upgrade-apply

> Documents are referenced by role, e.g. `{{doc:decisions}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions`. See
> `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work.

This writes to a project's `.design-suite/` directory, so it is **explicit** —
blast radius, not difficulty, per this suite's tier rule. It is never invoked
because an upgrade looked available; it is invoked because a person said to
apply one.

**Run `/upgrade-measure` first.** Applying a migration whose cost nobody measured
is the situation this whole capability was built after.

---

## The rule that shapes every action here

`init.py --force` is **never** used. It rewrites `profile.json` from the template
wholesale, discarding every declared and ratified value the project has
accumulated — which is the entire content of the provenance model. So the
migration is a set of specific, individually refusable file operations instead,
and **no action here writes `profile.json` at all.** If you find yourself
reaching for `--force`, stop and report that instead.

## Step 0 — Plan before writing

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/suite_upgrade.py" apply --consumer <project root>
```

Without `--apply` this writes nothing. Show the plan and get an explicit
go-ahead, per action, before running it again with `--apply`.

`--consumer` comes from the argument or from what the user named. **Never
hardcode a project path.**

## Step 1 — The four actions

| Action | What it does | When it refuses |
|---|---|---|
| `sync-schema` | Copies the target version's `profile.schema.json` into `.design-suite/` — that one file, nothing else | The target version ships no schema |
| `scaffold-hooks-map` | Writes `hooks.map.json` from the template **only when the project has none** | Never overwrites an existing map — a project's own hook map is its own |
| `declare-config-keys` | Names every newly-required top-level profile key the project does not declare | **Always refuses to fill them in.** A required key's value is a project fact — a source root, a token file, a framework — and inventing one produces a profile that validates and lies. `doctor.py` exists because of exactly that |
| `rebaseline` | Runs each ratchet audit's `--update-baseline` | Refuses, with exit 2, when new findings would be absorbed and nobody said to accept them |

Select with `--only <action>` and `--skip <action>`, repeatable. An excluded
action is still **listed**, with status `skipped` — a plan that silently shortens
when you filter it is a plan nobody can check.

## Step 2 — Re-baselining, and the one flag that needs a human

`--accept-new` exists because the ratchet audits used to absorb a brand-new
violation into the baseline in the same run that recommended updating it, and
nobody was shown what they had just accepted (`design_suite/engine/ratchet.py`).

So this command passes it **only for audits the caller names, one at a time**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/suite_upgrade.py" apply \
  --consumer <project root> --apply \
  --only rebaseline --accept-new-for audit_layer_boundaries
```

There is deliberately no "accept everything" option. Before you name an audit
here, a human must have **read that audit's new findings and said they are
accepted debt.** Report which findings they accepted, not just that you passed
the flag. An agent may not supply that decision on a human's behalf, and may not
infer it from "go ahead and upgrade".

## Step 3 — Report

One line per action with its status. Then, separately:

* Every `refused` action, with its reason **verbatim**. A refusal is not a
  failure of the tool and is not satisfied by having been reported — the
  obligation is still outstanding.
* Every file written, by path.
* What the person still has to do by hand — typically the config keys
  `declare-config-keys` named.

Exit codes: **0** nothing to do, **1** actions remain planned, **2** something
refused or failed, **4** every action was excluded.

---

## What you must never do

- Run `init.py --force`, or write `profile.json` by any other route
- Overwrite a project's existing `hooks.map.json`
- Invent a value for a newly-required config key, including a placeholder
- Pass `--accept-new` for an audit whose new findings no human has reviewed
- Apply anything without an explicit go-ahead for the specific actions, given
  after the plan was shown
- Hardcode a consumer project's path, name, or layout anywhere
