# Doc roles

**Runtime reference.** This file lives inside the plugin because the skills read
it while they run. For the human-facing explanation of *why* roles exist, see
[`docs/CONCEPTS.md`](../../../docs/CONCEPTS.md) at the repo root.

---

## The problem this solves

A skill that says "read `docs/DESIGN.md`" works on exactly one project. The
reference project had **252** such hardcoded paths, which was the single largest
obstacle to reuse — larger than anything language-specific.

So skills never name a file. They name a **role**, and each project maps roles to
its own paths.

## Notation

In skill and agent content:

| Notation | Means |
|---|---|
| `{{doc:design}}` | The file playing the `design` role in this project |
| `{{dir:derived}}` | The directory playing the `derived` role |

These are **not** substituted by Claude Code. They are a convention for the
model: when you encounter one, resolve it before reading anything.

## Resolving

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design
```

Prints the project-relative path, e.g. `docs/DESIGN.md`.

Reads `.backend-suite/docs.manifest.json` from the project root, which
`resolve.py` locates via `CLAUDE_PROJECT_DIR` or by walking up to the nearest
`.backend-suite/` directory.

### Full interface

| Invocation | Does |
|---|---|
| `resolve.py <role>` | Print that role's path |
| `resolve.py --all` | Every role and path, tab-separated (external ones marked) |
| `resolve.py --dirs` | Every directory role |
| `resolve.py --dir <name>` | One directory role's path |
| `resolve.py --reverse <path>` | Which role a path plays |
| `resolve.py --profile <key>` | A dotted key from `profile.json`, e.g. `audits.configFile` |
| `resolve.py --project-kind` | This project's declared archetype, or exit 2 |
| `resolve.py --roles-for-kind <kind>` | Roles that apply to an archetype, with `expected`/`optional` |
| `resolve.py --check` | Also fail if the mapped file doesn't exist |
| `resolve.py --members` | For a directory-valued role, also list its documents |
| `resolve.py --manifest <p>` | Use a different manifest |

### Exit codes — these are the contract

| Code | Meaning | What a skill must do |
|---|---|---|
| **0** | Resolved. Path on stdout | Proceed |
| **1** | Role is mapped, file is missing (`--check` only) | Report it. Do not create the file silently |
| **2** | Unknown role, or no manifest | **Stop.** Say which role is unmapped. Do not guess a path |
| **3** | Role is **external** — owned by another repository | Read it if you must, **never edit it** |
| **4** | Role was **declined**, with a reason (printed on stdout) | Skip the check **and say so, with the reason, in your report** |
| **5** | The document is a **stub** — registered and mapped, but unwritten | Treat it as outstanding work. Never report the category as covered |

### Directory-valued roles

A role's manifest value is normally a path string. It may instead be an object
naming a **directory** of documents:

```json
"roles": { "components": { "directory": "docs/components" } }
```

This exists because `components` mapped to a single file, and a design system
with one markdown page per component has ~130 of them. PR #111 gave the role a
`pageTemplate` — an index plus a page per component — which is the *write* side;
this is the *read* side that was missing.

An object, not a trailing `/` on the string, so a caller can tell the two apart
before touching disk. A string's meaning must not depend on a typo.

The same exit codes carry four distinct states, and **none of them may collapse**:

| Directory state | Code | Why that code |
|---|---|---|
| At least one **authored** member | **0** | Real coverage |
| Members exist, **all stubs** | **5** | Exactly what 5 already means: registered, unwritten |
| Exists, **no members** | **2** | "I could not look." Nothing to read — an empty glob graded clean is this repo's governing failure |
| **Absent** | **1** | Mapped, does not exist |

Absent is reported **without** `--check`, unlike a file role. For a file,
printing an unchecked path is useful because the caller often means to create it.
For a directory the caller's next move is to enumerate members, and enumerating a
missing directory returns an empty list with no error — indistinguishable from a
documented-and-empty one. So the directory branch always checks.

Members are `*.md` found recursively. Recursive because grouping component pages
into subdirectories is not the same as having none; markdown-only because
counting a stray image as coverage is the empty-directory bug with a different
file extension.

`--reverse` on a path *inside* a directory role returns that role — otherwise the
~130 documents the role exists to cover would each answer "no role maps to this".

**Exit 2 is a feature.** An unmapped role is a question about the project that
only a human can answer, and a skill that guessed `docs/DESIGN.md` would produce
confident output about the wrong file — or silently audit nothing and report
clean. Per the suite's governing principle: an audit that reports nothing must
never be indistinguishable from a clean codebase.

This has already earned itself: during portability validation on an unfamiliar
codebase, `resolve.py` rejected an invented token-source path that would
otherwise have produced plausible garbage.

## The audit exit-code contract

The table above is about **resolving a doc role**. The audits reuse two of those
codes for something adjacent, and this is where that gets written down — not in
CONCEPTS.md and not in a new file, because it is where the audits already send
the reader: `audit_accessibility.py`, `audit_copy.py` and `verify.py` each cite
"docs/DOC-ROLES.md's exit-code contract" in their own docstrings for the meaning
of exit 2. A contract cited from three places and stated in none is how the two
halves drift.

`audit_contract_headers.py` states it in one line, and that line is the contract:

> 1 means I looked and this is wrong, 2 means I could not look.

| Code | Meaning | What a caller must do |
|---|---|---|
| **0** | Ran, and found nothing to report | Treat as clean — **only** because something actually ran |
| **1** | Ran, and found findings | Report them. This is a result, not a malfunction |
| **2** | **Could not run** — `CapabilityError` | Report the refusal *by name*. Never baseline it, never grade it, never count it as a pass |
| other | Crashed | Neither a result nor a refusal. Say so |

Exit 2 carries the same weight here as it does for an unmapped role: a missing
adapter capability, an incomplete profile, a scan root that matched no files, or
a **disabled** audit (`backend_suite/engine/audit_discovery.DISABLED`) must not be
able to exit 0, because a baselined 0 is indistinguishable from a clean codebase.

### Audits that do not honour this yet

Documented rather than quietly fixed, because a contract that describes only the
compliant callers is the kind of documentation this repo keeps getting bitten by.
`repo_health.py` already compensates for the first group at runtime — it
downgrades an exit 1 with no findings envelope to `unclear` rather than
reporting it as findings — and its comment there says why.

| Audit | Deviation |
|---|---|
| `audit_accessibility.py` | Lines 104, 113, 119, 133 return **1** for "adapter implements no a11y checks", incomplete config, a missing scan directory, and a zero-file glob match — all four are "I could not look" and belong at 2. Its disabled refusal (line 77) is correct |
| `audit_focus_order.py` | Same four conditions, lines 88, 96, 102, 121, same deviation — including one that prints "Refusing to report a partial pass" and then exits 1 |
| `audit_reduced_motion.py` | Same four, lines 54, 63, 69, 79 |
| `audit_copy.py` | Line 196 returns **1** for `--selftest` failure, which is this script's own test failing rather than a project finding. Its disabled refusal (line 114) and its audit path (line 345) are correct |
| `audit_error_handling.py`, `audit_proposal_status.py` | `return 1 if critical else 0` — non-critical findings exit 0, so a caller reading only the exit code sees "clean" |

Compliant, for contrast — `audit_tokens.py` (brought into line in PR #122: a
missing scan directory, a zero-file glob match and config drift all exit **2**,
and it exits **1** when it has findings instead of always **0**),
`audit_contract_headers.py`, `audit_claude_md_drift.py`,
`audit_doc_staleness.py`, `audit_layer_boundaries.py`, `audit_adapter_pattern.py`,
`audit_reinvented_components.py`, all of which use 2 for a refusal.

## Handling a missing role

When a role you need is unmapped, you have exactly two acceptable moves:

1. **Stop and ask** which file plays that role — then offer to add the mapping.
2. **Degrade explicitly**: continue with a framework-neutral fallback *and say
   plainly, in the output, that you did so and why.*

What is never acceptable: guessing a conventional path, or quietly skipping the
part of the work that needed the document.

## Project archetypes

A repository is one of three kinds — `app`, `design-system`, `docs-site` —
declared as `project.projectKind` in `profile.json`. The kind selects which roles
are *expected*, so a package is never told it is missing a flows document.

**A kind outside that list is a refusal, and so is a question that needs the kind
from a project that never declared one.** Never fall back to `app`: assuming a
package is an app is what produces an empty flows document and an audit that
reports clean on documents it never looked for. `projectKind` stays optional, so
an existing profile keeps working — what is not allowed is guessing it.

**`workspace` is a separate boolean, not a fourth kind.** A monorepo is a
container *of* archetypes; as a kind it would force a repo holding an app and a
package to pick one and be wrong either way. Each role declares whether it
resolves once at workspace root or once per member.

`docs-site` has **no roles of its own**. That is deliberate and measured: no
docs-site repository has been surveyed, so the kind stays declarable — and
therefore refusable — rather than being given a speculative role set.

## The role vocabulary

Roles the templates and skills assume. A project maps the ones it has; **no
project is expected to have all of them**, and `roles.json` carries the full
machine-readable matrix of which apply to which archetype, plus each role's
template or the reason it has none.

**A role with no template is not covered.** `roles.json` maps roles to
*scaffolding*; 2 of the 36 roles have none yet, and `docs/CATALOG.md` names them
rather than counting registrations as coverage.

| Role | The document that… |
|---|---|
| `brief` | States what the product is and who it's for. Usually read-only to tooling |
| `entry-point` | The entry point that drives reading order for everything else. **Renamed from `instructions`**; the old name still resolves, in both directions, via the alias in `roles.json` |
| `component-schema` / `theming` / `patterns` / `responsive` / `adaptive-patterns` / `accessibility` / `changelog` / `deprecations` / `common-mistakes` / `gallery` / `figma` | The rest of the design-system vocabulary. Each is a real document measured in a real package. All but `adaptive-patterns` and `figma` have a template; `roles.json` records why those two do not |
| `documentation-rules` | Governs how docs themselves are structured and changed |
| `design` | An app's visual doc-of-record: principles, reuse rules, accepted exceptions, screen inventory. **App-only** (`na` for `design-system` and `docs-site`) — in a package, the visual system, the component pages and the token reference are the separate `tokens`, `theming`, `components` and `patterns` roles |
| `flows` | User flows and route documentation |
| `decisions` | The decisions log, including what was ruled out and why |
| `backlog` | What's in progress, shipped, deferred |
| `motion` | Motion and interaction specification |
| `brand-voice` | Voice, tone, and copy principles |
| `copy` | The copy inventory itself |
| `contributing` | How to work in the repo; component lookup table |
| `pr` | PR process, template, title conventions |
| `api` / `api-standard` | API surface, and the standard it's held to |
| `assets` | Asset inventory and pipeline |
| `builds` / `deployment` / `release` | Build, deploy, and release process |
| `production-readiness` | Internal readiness checklist |
| `promoting-components` | When and how a component becomes shared |
| `public-roadmap` | External-facing roadmap — what's shipped, in progress, and planned, for anyone outside the team. Distinct from `decisions`/`backlog`, which are internal |
| `rfc` | The proposal format for a change, argued before a decision is made — distinct from `decisions`, which records the outcome |
| `postmortem` | Structured record of a regression, including agent-caused ones — dispatch provenance, claimed-vs-shipped, verification tier at merge |
| `components` | The component reference — what exists, its API, its variants. **Usually external:** in an app consuming a shared design system, this document belongs to the design system, not the app |
| `tokens` | What the design tokens mean and how they are organised — the prose counterpart to the profile's `tokens.source` file pointer. **Usually external**, for the same reason as `components` |

Directory roles (via `--dir`): `specs`, `workingContext`, `plans`, `derived`,
`walkthroughs`, `tasks`.

### External roles

A role can be declared as owned by **another repository** — a design system
package, for instance. `resolve.py` prints a URL and exits **3**.

Exit 3 means *readable, not writable.* A skill that "fixes" documentation in a
repo the project doesn't own creates a change nobody asked for in a codebase
nobody is watching.

`components` and `tokens` are the two roles that are external more often than
not, and both were in live use before this table listed them — mapped under
`externalRoles` in both consumer manifests, and referenced by
`/promote-component`, while a reader of this document would have concluded
neither was a real role. Resolution was never affected (`resolve.py` reads the
manifest, so they resolved to exit 3 correctly all along); the gap was that the
vocabulary this file documents had fallen behind the vocabulary projects
actually use. A role with no template is normal and expected when the document
lives in another repository — `roles.json` maps roles to *scaffolding*, and
there is nothing to scaffold for a document this project does not own.

### Declined roles — exit 4

A role can be declared **deliberately absent**, with a reason, under
`declinedRoles` — the sibling of `externalRoles`, and modelled on it:

```json
"declinedRoles": {
  "motion": { "declined": "folded into THEMING.md §4 — no separate doc",
              "by": "the design lead", "on": "2026-09-15" }
}
```

`resolve.py` prints the reason on stdout and exits **4**. It is deliberately not
any of the other codes: not 2, because 2 means *a question only a human can
answer* and this one has been answered; not 1, because nothing is missing; not 0,
because there is no path to return.

**Declined is not passed.** A skill that hits exit 4 skips the check *and names
the role, the reason, and the decline in its report*. A check that silently
vanishes because a role was declined is the exact failure this suite exists to
prevent. The decline is dated and attributed so a three-year-old "does not apply"
can be re-examined rather than inherited forever — and `doctor.py` fails a
decline that carries no reason, because a reasonless decline is the same silence
it was meant to replace.

### Stubs — exit 5

A document that exists, is registered, and is **unwritten** used to resolve to
its path and exit 0, so a scaffolded stub read as a cleanly documented category
and `/review-docs` counted it as coverage.

A stub declares itself in its own frontmatter:

```markdown
---
status: stub
---
```

`resolve.py` still prints the path — whoever fills the document needs it — and
exits **5**. `doctor.py` lists stub roles and names the count in its healthy
line; `design_debt.py` reports them as debt and excludes them from the
written-document count. Declined and stub are different states on purpose: 4 is
*deliberately has no such document*, 5 is *has one, nobody wrote it*.

**Where a stub comes from, and how it stops being one.** The only thing that
writes that frontmatter is `bin/scaffold_doc.py`, which scaffolds **one role's
document per invocation** and registers it in the manifest:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/scaffold_doc.py" motion [--path docs/MOTION.md]
```

There is no bulk mode, and adding one would be a design change, not a
convenience: `init.py` writes the universal core only, and archetype-specific
documents are accepted one at a time (RFC-0002 §3d-ii). A stub nobody asked for
is coverage the project does not have.

A stub stops being a stub when **a human deletes the frontmatter block** — the
block itself says so, and there is deliberately no command that clears the
status without anyone reading the document. Delete it, then re-run `resolve.py
<role>`: exit 5 becomes exit 0, and `design_debt.py` moves it from debt into the
written count.

Templates never carry `status: stub`. A template is not a document; the status
is added at scaffold time.

## Adding a role

Add it to `roles` in `.backend-suite/docs.manifest.json`, then confirm:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"
```

`--all` shows the mapping; `doctor.py` proves every mapped path actually
resolves. A manifest can be valid JSON and point at three files that were
deleted last month — that has happened here, which is why the second check
exists.
