# Documents are referenced by role, not by path

Every skill and agent in the suite refers to documentation by **role** — `{{doc:design}}`,
`{{doc:pr}}`, `{{doc:decisions}}` — never by a literal path like `docs/DESIGN.md`.

This file is the one place that explains how to resolve them, so the explanation is not copied into
two dozen skill prompts. A skill needs only a single line pointing here.

---

## Resolving a role

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design      # → docs/DESIGN.md
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all       # every role this project maps
```

Or read `.backend-suite/docs.manifest.json` directly, which is often cheaper when you already need
several roles.

Exit codes carry meaning, and the difference matters:

| Exit | Meaning | What to do |
|---:|---|---|
| 0 | Mapped, path printed | Use it |
| 1 | Mapped but the file is missing (`--check`) | Report it as a project defect — do not create the file silently |
| 2 | **Not mapped in this project** | Say the role is unavailable here and continue with what you can. Never guess a path |
| 3 | Owned by another repository, URL printed | Read it there if you must; **never edit it here** |
| 4 | **Declined** — the project decided it has no such document, reason printed | Skip the check **and say so, with the reason, in your report**. Declined is not passed |
| 5 | **Stub** — registered and mapped, but unwritten (`status: stub`), path still printed | Treat it as outstanding work; never report the category as covered |

## Why

Measured on 2026-08-03, the suite hardcoded **184 references to 24 distinct `docs/*` paths**. That
was its single most pervasive form of project coupling — larger than its Flutter coupling. A skill
that names a path only works in a project that happens to use that path, and it fails *quietly*: a
grep against a file that does not exist returns nothing, which reads exactly like a clean audit.

Roles fix the direction of the dependency. The skill declares what kind of document it needs; the
project declares where that document lives.

## The two failure modes this is designed against

1. **Silent absence.** A missing document must never look like a passing check. That is why exit 2
   is distinct from exit 0, and why `--check` exists for the cases where a skill genuinely cannot
   proceed without the file.
2. **Editing someone else's document.** Component specs and token tables live in the design-system
   repository, not here. Exit 3 exists so a skill can read them without ever proposing an edit to a
   file this project does not own.

## Adding a role

Add it to `roles` in `.backend-suite/docs.manifest.json`, then run
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"` — it fails if the path does not resolve. If another
repository owns the document, add it under `externalRoles` with a `repo` URL instead.
