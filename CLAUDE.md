# Claude Instructions — Backend Quality Suite

This repo's documentation is already the instruction layer. This file exists only
to say **what to read, in what order, and which rules are not written down
anywhere else.** It deliberately does not restate what those documents say — a
second copy of the rules is a second copy to drift.

---

## Read before writing anything

| Order | Document | Why |
|---|---|---|
| 1 | [README.md](./README.md) | What this is, the suite's invariants, honest status |
| 2 | [docs/CONCEPTS.md](./docs/CONCEPTS.md) | The vocabulary. Context layer, doc roles, seams, capability negotiation, the oracle, INERT |
| 3 | [docs/CATALOG.md](./docs/CATALOG.md) | Every component with its tier and maturity. **Generated — never hand-edit** |
| 4 | [docs/ROADMAP.md](./docs/ROADMAP.md) | Workstreams, sequencing, resolved decisions |

Those four are the baseline. **Then branch — read only what the task needs.**
The task types are `docs/CATALOG.md`'s own group names, so there is no second
taxonomy to keep in sync. A group with no row here needs the baseline and
nothing else.

| Task type — CATALOG group | Read | Skip |
|---|---|---|
| Fix or extend an audit — *Audits* | [CONCEPTS.md#the-finding-that-shapes-everything](./docs/CONCEPTS.md#the-finding-that-shapes-everything) and [#inert-and-the-governing-principle](./docs/CONCEPTS.md#inert-and-the-governing-principle); that audit's own `plugins/backend-suite/commands/<name>.md` | CATALOG, ROADMAP — neither decides what an audit may report |
| Author a skill, agent, or hook — *Building*, *Capture*, *Maintenance*, *Playbooks (`run-chain`)* | [Writing a new skill, agent, hook, or script](#writing-a-new-skill-agent-hook-or-script) below; [CONCEPTS.md#invocation-tiers--auto-and-explicit](./docs/CONCEPTS.md#invocation-tiers--auto-and-explicit); `GROUPS` in [`bin/catalog.py`](./plugins/backend-suite/bin/catalog.py) | CATALOG — it is generated *from* the frontmatter you are about to write |
| Adopt the suite in a consumer project, or add a component to one — *Playbooks (`onboard-new-client`)* | [ONBOARDING.md](./ONBOARDING.md), [docs/ADOPTING.md](./docs/ADOPTING.md), and [DOC-ROLES.md](./plugins/backend-suite/docs/DOC-ROLES.md) for doc-role vocabulary and the exit-code contract | ROADMAP — it sequences this repo's work, not a consumer's |
| Add or amend a project convention — *Capture* | [CONCEPTS.md#doc-roles-and-role-resolution](./docs/CONCEPTS.md#doc-roles-and-role-resolution); the relevant `capture-backlog`, `log-decision`, or `ratify` command file | CATALOG, ROADMAP |

Two rules keep the map from becoming the cost it exists to avoid:

- **`Skip` never names a document the baseline table does not.** An explicit skip
  is a stronger claim than an omission, and a stronger claim can rot — so it may
  only name those four, which age with that table rather than independently.
- **Group names are borrowed, not generated.** They are the literal strings in
  `GROUPS` (`bin/catalog.py`), which `docs/CATALOG.md` is generated from — never
  hand-edit either to match this. Nothing enforces the sync; it is a manual
  coupling, acceptable because a renamed group leaves every pointer in its row
  correct. The label goes stale, the map does not break. A label qualified by a
  component name — *Playbooks (`run-chain`)* — means that group's members split
  across rows; both halves are listed in the same `GROUPS` entry, so the split
  is checkable there rather than being this table's private opinion.

[`known-traps.json`](./known-traps.json) is deliberately in no row: it applies to
every task equally, and giving it one would imply the other rows may skip it.

The rest of this file's "rules that live only here" are also machine-queryable,
extracted into [`known-traps.json`](./known-traps.json) (schema:
[`plugins/backend-suite/templates/known-traps.schema.json`](./plugins/backend-suite/templates/known-traps.schema.json)).
Read it the way you'd read this file — it's this repo's own populated instance
of the known-traps registry, not a substitute for the prose below. A consumer
project's own instance lives at `.backend-suite/known-traps.json`, scaffolded by
`bin/init.py`.

---

## The governing principle

**An audit that reports nothing must never be indistinguishable from a clean
codebase.**

Everything else here is downstream of that. Unknown adapter → hard error.
Unresolvable doc role → say so and stop. Self-skipping audit → `INERT`, never
baselined clean. Cannot answer → `CapabilityError`, never `False` and never an
empty set.

It is stated at length in [CONCEPTS.md](./docs/CONCEPTS.md#the-finding-that-shapes-everything)
because it was learned the expensive way, twice.

---

## Rules that live only here

1. **`main` is the integration branch.** Cut a feature branch from it. Never
   commit, push, or merge directly to `main` — including for CI, tooling, or
   docs-only changes.

   **Name explicitly-created branches `<type>/issue-N-<slug>`** — `<type>` is
   `feat` or `fix`, chosen the same way commit-message prefixes already are
   (new capability vs. bug fix); `docs` is also fine for a docs-only change.
   `N` is the GitHub issue number the branch addresses, and `<slug>` is a
   short kebab-case description. This applies equally to a human cutting a
   branch by hand and to an orchestrator naming a branch it hands to a
   dispatched agent — it's how this session's own branches (and the worktree
   convention in rule 4) are already named.

   This does **not** apply to the Agent tool's own `isolation: "worktree"`
   option: it generates its own directory and branch names
   (`.claude/worktrees/agent-<hex>`, branch `worktree-agent-<hex>`) at
   dispatch time, before any project convention can apply, and there is no
   hook or config in this repo (or documented in Claude Code) to override
   that. Don't rename those branches or fight the harness — just don't rely
   on their names for anything. `bin/cleanup_worktrees.py` already does this
   correctly: it identifies agent worktrees by directory location
   (`.claude/worktrees/`) rather than by branch-name prefix, so it keeps
   working even if that prefix changes.

2. **Every push, PR, and merge needs its own explicit go-ahead**, asked for at
   the moment it happens. Approval to work on a branch is not approval to push
   it; approval to push is not approval to open a PR; approval to open a PR is
   not approval to merge.

3. **The local run is the authority, not a fallback.** GitHub Actions is
   unavailable and staying that way, so there is no CI verdict to wait for and
   a missing check is never a pass. One command is the whole verdict:

   ```bash
   python3 plugins/backend-suite/bin/attest.py
   ```

   It runs every gate and prints the environment the verdict was reached under,
   because a local pass is a claim with conditions attached. Underneath, it
   parses `.github/workflows/validate.yml` and
   runs 16 of the 16 gates, with none skipped —
   `run_tests.py` and `gate_consumer_compat.py` are among them, so you do not
   run those separately, and `attest.py` fails the run if either ever stops
   being wired. Exit 0 verified, 1 a gate failed,
   **2 partial — which is not a pass.** Use `gates.py -k` while iterating.

   **What it cannot tell you:** it reads your working tree, not the commit a
   reviewer receives; `gate_consumer_compat.py` diffs committed blobs, so
   uncommitted work is invisible to it; and it saw one Python on one machine.
   Commit first, then attest. Opt in to running it on every push with
   `python3 plugins/backend-suite/bin/install_prepush_hook.py` — `--uninstall`
   removes it, and it never overwrites a hook it did not write.

   **Known-red in this fork, by design.** Two test files pin regression fixture
   revisions (`e14048a`, `ba7029e`) from the upstream lineage that this
   repository's squashed history does not carry: `suite_upgrade_test.py` and
   `gate_consumer_compat_test.py`. Their cases that run against that fixture —
   in the former the `CompatAgainstTheRealRegression`, `CompatRefusals` and
   `Measure` classes, in the latter `GateBites` and the `CliExitCodes` cases
   that pass `--from`/`--to` fixture revisions — fail here rather than skip,
   because "an unavailable fixture is not a passing check" is the suite's own
   rule. That failure is the documented state, not a regression to fix or a
   fixture to fake. Every other gate and test must pass; a run whose only
   failures are these named cases is this fork's clean.

4. **The main clone is often dirty with another session's work.** Check
   `git status` before doing anything. If it is not clean on the branch you
   want, use a worktree rather than stashing or switching:

   ```bash
   git worktree add ../suite-<topic> main
   ```

   Never stage, commit, or stash a file you did not create.

5. **Regenerate, don't edit, anything generated.** `docs/CATALOG.md` comes from
   component frontmatter via `bin/catalog.py`; template coverage counts come from
   `templates/docs/roles.json`. Hand-written coverage claims here have been wrong three separate
   times, which is why they are generated and gated.

6. **Every PR carries a `Verification-Tier:` trailer in its description**
   (`.github/PULL_REQUEST_TEMPLATE.md`), mirroring the `Co-Authored-By:` commit
   trailer convention — `unverified` / `self-tested` / `cross-verified` /
   `human-reviewed`, vocabulary from
   `plugins/backend-suite/templates/verification-tier.schema.json` (issue #55). A
   PR takes the **lowest** tier among its bundled commits, never the highest or
   an average. An agent may self-report `unverified` or `self-tested` about its
   own work but must never self-assign `cross-verified` or `human-reviewed` —
   those require an actual independent party, not the author's own say-so.
   Presence (not truthfulness) can be spot-checked with
   `python3 plugins/backend-suite/bin/check_pr_verification_trailer.py <pr-number>`;
   this is a manual script, not a CI gate — CI is dead per rule 3, and issue
   #59's research is why it stays that way rather than becoming a gate.

---

## Writing a new skill, agent, hook, or script

The full rationale is in [CONCEPTS.md](./docs/CONCEPTS.md); the short form is
that **no project literal may appear in the universal plugin**, and six CI rules
enforce it.

| Never write | Write instead |
|---|---|
| `docs/API.md` | `{{doc:api}}`, resolved via `bin/resolve.py` |
| `.backend-suite/resolve.py`, `plugins/backend-suite/bin/…` | `${CLAUDE_PLUGIN_ROOT}/bin/…` |
| `src/`, `composer.json`, `routes/` | Read it from `.backend-suite/profile.json` |
| The consumer project's name | "this project", or the profile's `project.name` |
| A language-specific regex in an engine | A module in `backend_suite/adapters/` |
| A project's accepted exception as a constant | `.backend-suite/exceptions.json` |

`house-style` is org-scope by definition and is exempt from the
project-name rule. It also cannot reach `backend-suite`'s resolver across the
plugin cache's per-plugin version hashes, so it ships its own parity-tested
`bin/resolve_role.py` — extend `resolve.py`, never that copy.

Every component declares its **invocation tier** — frontmatter key `invocation`,
not `tier`; `catalog.py` reads `invocation`, no component carries a `tier` key,
and a frontmatter key by that name would be silently ignored — as `auto` /
`explicit`, plus `maturity`
(`proven` / `unverified` / `experimental` / `pointer` / `disabled`) in its
frontmatter. `disabled` is not a confidence level: it means the component is
switched off — its backing script refuses with exit 2, and every reporting
surface names it as disabled rather than letting its silence read as a pass.
The registry is `backend_suite/engine/audit_discovery.DISABLED`, and each entry
carries the measured reason and the bar for re-enabling it. Tier
is decided by **blast radius, not difficulty**: read-only and report-only run
automatically, content-generating and convention-setting stay explicit.

**A new audit has no template — it is written by copying an existing
`commands/audit-*.md`, and it inherits that doc's claims along with its shape.**
So its `description` must state what *this* audit's script writes, never a
copied "Read-only". Exactly one of three claims, checked against the script:

| The script… | Say | Invocation |
|---|---|---|
| writes nothing | "Writes nothing; reports findings only." | `auto` |
| writes only its own report — always, or only under a flag | "Never changes your code; saves its report to `<path>` on every run." / "…saves a report only with `--out`." | `auto` |
| changes the user's files | say which files | `explicit` |

`audit_prose_flags.py` fails the build when an audit's description claims
read-only while `bin/audit_<name>.py`'s `main()` writes unconditionally. It
cannot see a write behind a flag or inside a helper — those are still on you.

---

## Before claiming a refactor was behaviour-preserving

Capture the oracle first, and know what it cannot tell you:

```bash
bash plugins/backend-suite/bin/capture-baselines.sh
```

A 0-finding baseline proves nothing — 0-before and 0-after look identical
whether the check works or not. Plant a broken file and confirm the audit catches
it.
