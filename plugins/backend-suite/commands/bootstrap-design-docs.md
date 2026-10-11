---
name: bootstrap-design-docs
description: "Bootstrap a project's documentation layer one document at a time, by reverse-engineering what is already built and proposing each document for the human to accept or decline. The installer for a new project's documentation layer. Note: not yet verified against a real zero-docs project."
invocation: explicit
maturity: unverified
---

# /bootstrap-design-docs

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You stand up the documentation layer of a project that has none, by
reverse-engineering what is already built and then **proposing one document at a
time** — each one accepted or declined by the human before you move on. It is the
entry point for RFC-0002 §3d-ii's propose-and-ratify flow.

**⚠️ Not verified end-to-end.** This skill needs a project with NO documentation
layer to prove itself against, and both consumers it has been installed on
already had one. Treat it as unverified against a real target until it has
actually been run on a project that needs it.

---

## 🔴 The one rule this skill exists to hold

**You propose documents one at a time. You never scaffold a set.**

There is no bulk mode here, and `${CLAUDE_PLUGIN_ROOT}/bin/scaffold_doc.py` ships
no `--all` for the same reason (RFC-0002 §3d-ii, decision 4): **a stub nobody
asked for reports as coverage the project does not have.** That is this suite's
governing failure wearing a friendly face, and mass-stubbing by way of a skill
that loops is the same failure with extra steps.

Concretely, in this skill:

- You may hold **at most one open proposal at a time**. Make it, wait for the
  answer, record the outcome, and only then consider the next role.
- **Never** iterate a list of roles calling `scaffold_doc.py` per item — not in a
  loop, not in a `for role in …` shell line, not by listing five roles and asking
  "shall I do these?" as one question. Five documents means five separate
  decisions, made at five separate moments.
- **Never** offer "scaffold the rest", "do the remaining ones", "accept all", or
  any phrasing that collapses several decisions into one answer. If the human
  asks for that, say no and explain why: the stubs would report as coverage
  nobody wrote.
- Stopping part-way through the applicable roles is a **normal, good outcome**,
  not an unfinished job. A project with three written documents and fifteen
  roles nobody has looked at is in an honest state; the same project with
  eighteen stubs is lying.
- The roles you have not proposed stay **absent** from the manifest. Absent means
  "nobody has looked yet", which is a real gap the suite is supposed to keep
  reporting — do not pre-register them to tidy the list.

---

## Step 0 — Preconditions

1. Confirm this is genuinely a zero-docs (or near-zero-docs) project. Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all --check`. A row marked
   `(missing)` is a role `init.py` registered whose file does not exist yet —
   that is a gap to bootstrap, not coverage (`--check` exits 1 when any is
   missing; that exit is the answer, not an error). A row marked `(stub)` is
   registered and unwritten. If the roles that matter already map to files with
   real content, **stop and say so** — this
   skill bootstraps, it does not audit or supplement (`/review-docs` is the tool
   for that case).
2. Confirm you are on a feature branch.
3. Confirm `.backend-suite/` exists. If it does not, run
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py"` first: that writes the universal
   core config, which is a precondition for everything below. `init.py` scaffolds
   config, never archetype documents — the two jobs stay separate on purpose.

## Step 1 — Establish the archetype, or say you cannot

Which roles even apply depends on what kind of repository this is. Read
`projectKind` from `.backend-suite/profile.json`:

```bash
python3 -c "import json,sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); \
from backend_suite.engine import archetypes; \
p=json.load(open('.backend-suite/profile.json')); \
print(archetypes.kind_of(p)); print(archetypes.roles_for(archetypes.kind_of(p), include_optional=False))"
```

- If it prints a kind and its expected roles, that list is the **universe you may
  propose from**. A role that is `na` for this kind is not proposable at all —
  proposing `deployment` to a `library` manufactures a deployment runbook for a
  thing that is never deployed.
- If it raises **`ArchetypeNotDeclared`**, the project has not said what it is.
  **Say that you do not know, and stop to ask.** Do not assume `service` —
  guessing `service` for a parser library is exactly the assumption
  `archetypes.py` refuses to make on your behalf, and it would put deployment
  runbooks into a repository that is never deployed. Offer the kinds
  (`service`, `library`), let the human declare one in the profile, and resume. You may proceed without a declared kind
  only if the human explicitly names the single role they want, and then you
  propose only that one.
- If it raises **`UnknownArchetype`**, the declared kind is outside the
  vocabulary. Report it and stop; a kind nobody defined has no role set.

Also check `archetypes.is_workspace(profile)`: a workspace is a container of
archetypes, so ask which sub-project this bootstrap is for rather than treating
the container as one thing.

## Step 2 — Reverse-engineer the evidence, before proposing anything

Gather what is actually in the repository, so every proposal you make is grounded
in something real. What to read depends on the archetype:

**Any archetype** — the entry-point file, the README, the directory layout, and
whatever config already declares conventions.

**`service`** — the route declarations and the handler entry points, the
error-handling machinery (the shared exception type every failure funnels
through), the config that declares conventions (auth, caching, rate limits),
and the migrations that shape the data.

**`library`** — the public entry points (the facade or top-level API), what the
package exports, and any existing release notes or CHANGELOG.

This step produces **notes, not files**. Nothing is written to disk here.

## Step 3 — Propose ONE document

Pick the **single** role with the strongest evidence behind it — the one you can
say the most true, specific things about. Then make one proposal, and stop:

> *(Illustration from a `service` project — `deployment` is `na` for a
> `library`, and `scaffold_doc.py` refuses it there.)*
>
> I propose `{{doc:api}}` for this project.
> Evidence: 42 route declarations in `<the route file>`, all serving JSON
> through shared resources, referenced by 3 doc files.
> Accepting scaffolds `docs/API.md` as a **stub** — registered, `status: stub`,
> resolving with exit 5 and counting as debt until someone writes it.
> Declining records that decision with your reason.
> Accept, decline, or skip for now?

Three outcomes, all first-class:

- **Accept** → Step 4a.
- **Decline** → Step 4b. This is a decision being recorded, not a failure.
- **Skip for now** → write nothing anywhere. The role stays absent from the
  manifest, which is how "nobody has looked yet" stays visible as a real gap.

Then, and only then, consider whether to propose another. Ask the human whether
they want to continue; if they stop, stop.

## Step 4a — Accept: scaffold exactly that one role

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/scaffold_doc.py" <role>
```

It writes the template with `status: stub` frontmatter and registers the role in
`docs.manifest.json`. Then tell the human plainly what state the project is now
in: the document **exists and is empty**, `resolve.py` exits 5 for that role, and
`/design-debt` counts it as debt until the frontmatter block is deleted by
whoever authors it.

If you already have enough reverse-engineered material to fill sections of it,
offer that content **section by section for confirmation** — and only delete the
stub frontmatter once the human has confirmed the document is genuinely written.
A reverse-engineered document describes what the code does today, which may not
be the intent; say so explicitly rather than presenting it as ratified.

The script refuses (exit 1) on an unknown role, a role with no template, a
destination that already exists, and a role already declined. Each refusal is a
real answer — relay it and stop, never work around it with `--force`.

## Step 4b — Decline: record the reason, in the manifest

A decline is only worth anything if the reason is recorded, because exit 4's
whole contract is that `resolve.py` prints that reason to a skill that then names
it in its report. Ask for the reason **in a sentence** — "we track deprecations
in the changelog's own notes" is a reason; "n/a" is silence with a label.

Add one entry under `declinedRoles` in `.backend-suite/docs.manifest.json`:

```json
"declinedRoles": {
  "deprecations": {
    "declined": "tracked in the changelog's own deprecation notes — no separate doc",
    "by": "<who decided>",
    "on": "<YYYY-MM-DD>"
  }
}
```

All three fields matter: the reason is what exit 4 prints, and `by`/`on` are what
let a three-year-old "does not apply" be re-examined rather than inherited
forever. Verify it took:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" <role>   # expect exit 4, reason on stdout
```

Never write a decline for a role the human did not explicitly decline, and never
batch declines — a decline is a decision with a reason attached, so it needs the
same one-at-a-time moment as an acceptance.

## Step 5 — Close out

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"` and
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all` — every accepted role
   should show, stubs marked as stubs, declines marked as declined.
2. Log the bootstrap in `{{doc:decisions}}` (exit 4 or 5 there is itself an
   answer — report it rather than working around it). Record which roles were
   accepted, which were declined and why, and — importantly — that the rest were
   **not offered yet**, so a later reader does not mistake a short list for a
   complete survey.
3. Report honestly: N documents scaffolded as stubs (debt, not coverage), M roles
   declined with reasons, and the remaining applicable roles still untouched.

---

## What you must never do

- Scaffold more than one document per accept/decline decision — no loop over
  `roles_for(kind)`, no "and the rest", no batch confirmation
- Assume an archetype for a project that declares no `projectKind` — say you do
  not know and ask
- Propose a role that is `na` for the declared archetype
- Record a decline without a reason, or invent a reason on the human's behalf
- Pre-register roles nobody has decided on, to make the manifest look complete
- Describe a freshly scaffolded stub as documentation the project has — it is
  registered debt until someone writes it
- Run against a project that already has real doc content — that is
  `/review-docs`'s job
- Write any doc content to disk before the user has confirmed it section by
  section
- Present a reverse-engineered description of current behaviour as validated
  intent — flag the difference explicitly
- Claim this skill has been verified end-to-end against a real zero-docs project
  until it actually has been
