# `.backend-suite/` config templates

Fixes issue #15: onboarding used to mean opening an already-onboarded project
and hand-copying/reconstructing these six files by eye. Now:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

copies every `*.template` file here into the target project's `.backend-suite/`
directory (stripping the `.template` suffix), plus a copy of the canonical
`templates/profile.schema.json` so `doctor.py`'s drift check has something to
compare against immediately. See `ONBOARDING.md` Step 2 and `docs/ADOPTING.md`
for what each file is for.

## What is and isn't decided for you

Every template ships with `TODO` markers instead of guessed values — this is
generic scaffolding, not a real project's config with the names filed off. Per
`CLAUDE.md`'s rule against project literals in the universal plugin, nothing
here names a real consumer project, client, or path that only happens to exist
in one repo.

`init.py` never invents a value beyond substituting `--name` for
`{{PROJECT_NAME}}` / `TODO_PROJECT_NAME` in `profile.json`. Everything else —
which language adapter, where source and tokens live, which doc roles are
mapped, which architecture rules apply — is a real decision about the target
project that only a human (or `/bootstrap-design-docs` reverse-engineering the
codebase) can make. Run `doctor.py` after filling things in; it is expected to
report every unresolved `TODO` path as a problem until you either fill it in or
delete that section/role.

## Inventory

| File | Consumed by | Notes |
|---|---|---|
| `profile.json` | Every skill and audit | The only required file. `profileVersion`, `project`, `adapters`, `source`, `tokens`, `docs` are the required sections; delete any optional section you don't have |
| `docs.manifest.json` | `resolve.py`, every doc-aware skill | Role → path. Map only roles you actually have — see `plugins/backend-suite/docs/DOC-ROLES.md` for the full vocabulary and the exit-code contract |
| `exceptions.json` | `audit_tokens.py`, `audit_copy.py`, and others | Deliberate, reviewed exceptions only — never a place to silence an unreviewed finding |
| `arch-rules.json` | The eight structural `audit_*.py` scripts (layer boundaries, banned imports, reinvented components, …) | An absent section makes its audit refuse rather than pass vacuously — delete sections for audits you don't use |
| `hooks.map.json` | `hooks/audit_on_edit.py` | Advisory on-save nudges only. Optional — delete or leave `entries` empty if you don't want it yet |
| `known-traps.json` | Nothing mechanical — read by an agent (or a human) at the start of a session, the way it would read `CLAUDE.md` | Situations that look safe but aren't, per project. Optional — see `plugins/backend-suite/templates/known-traps.schema.json` for the field contract |

Regenerate nothing here by hand-copying from a real project's file again —
if a template's shape is wrong, fix the template.
