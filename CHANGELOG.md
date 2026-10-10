# AI Design Suite — Changelog

What changed in each version, written for the people who have to decide whether to repin.

Distinct from the decision log, which records *why* things were decided and is read by
contributors. This is read by **consumers** — projects that install `design-suite@ai-design-suite`
and pin a `design-suite--v*` tag — and it records *what they now have to do*.

Format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The heading shape
(`## [X.Y.Z] - YYYY-MM-DD`) is a machine contract, not a style preference:
`plugins/design-suite/bin/changelog_to_release_notes.py` parses it to produce GitHub release
notes, and a heading it cannot match makes a section unreleasable.

## What earns an entry

The bar is **consumer-visible**: if nothing outside this repository could observe the change, it
does not belong here. Internal refactors, test and eval-harness changes, and documentation fixes
normally fail that test — including them trains readers to skim, which is how a breaking change
gets missed.

Concretely, a consumer can observe: a skill or agent appearing, disappearing, or being renamed; a
script's exit-code contract; the shape of a findings envelope or any other output they parse; a
profile or manifest key they must write; a maturity or tier downgrade they relied on; and anything
the suite now refuses to do that it previously did.

## Rules that are not negotiable

1. **Breaking goes first**, always, even when it is the shortest section. It is the section a
   reader came for, and it is the one they must not be able to miss.
2. **A breaking entry states the consumer's action**, not just the change. "Renamed X to Y" leaves
   work undone; "Renamed X to Y — rename every call site" finishes the sentence.
3. **Omit empty sections** rather than writing "none".
4. **Entries are never edited after release.** Wrong information about a released version is
   corrected by a new entry in the next version, not by rewriting history.

## Severity and version number

| Kind of change | Version part it increments |
|---|---|
| A script's exit-code contract changes meaning for a value a caller already branches on | major |
| A findings-envelope or other parsed output field is removed or repurposed | major |
| A component is removed, renamed, or has its invocation tier raised from `auto` to `explicit` | major |
| A newly enforced rule that previously passed silently | major |
| A profile or manifest key becomes required | major |
| A default value changes, or a semantic doc role is repointed | major |
| A component is added, or an existing one gains an opt-in capability or flag | minor |
| A component's `maturity` is downgraded (`proven` → `unverified`, or to `disabled`) | minor |
| A finding is now correctly reported that was previously missed, or vice versa | patch |
| A refusal message, report wording, or generated documentation changes | patch |

Pre-1.0, a major-severity change increments the **minor** part, per SemVer §4.

## Unreleased vs. release-time

Entries land under `## [Unreleased]` **as changes merge**. A changelog written at release time is
written from `git log`, and `git log` does not know which changes a consumer can see. The two
approaches do not mix — half-accumulated entries plus a release-time sweep produces duplicates.

Acknowledged breaks accumulate in `consumer-compat-acks.json` (enforced by
`plugins/design-suite/bin/gate_consumer_compat.py`) and **graduate into the Unreleased section
here** rather than living in two places; the ack file is emptied when the release carrying them is
tagged.

> **Provenance of the `0.1.0` entry.** This changelog was started after `0.1.0` was already tagged,
> so that entry was reconstructed from git history rather than accumulated as the work landed. It is
> a summary of what the release contained, not a record kept at the time, and it is deliberately
> coarser than the entries below it will be. Nothing before `0.1.0` is covered — the suite had no
> releases before it.

---

## [Unreleased]

---

## [0.2.0] - 2026-10-09

The release that makes the suite safe to drop into a project it was not built inside. Audits that
used to pass silently on a stack they could not read now **refuse with exit 2**, reports moved
inside `.design-suite/`, and web, Swift and Kotlin projects get language adapters. Most of the
Breaking section is the suite becoming honest about what it did not check: a step that turns red
after repinning was, in almost every case, already not checking anything. Read
[Upgrading from 0.1.0](#upgrading-from-010) first.

### Upgrading from 0.1.0

Do these in order; each step makes the next one's output trustworthy.

1. **Repin.** Point your CI checkout and plugin install at `design-suite--v0.2.0`. Make sure the
   pinned checkout includes `bin/client_denylist.sha256` (a full checkout does) and runs inside a
   git working tree — `audit_skill_paths.py` refuses without both.
2. **Install the CLI** if you drive the suite outside Claude Code: `pipx install <suite checkout>`
   (or `uv tool install <suite checkout>`). Python 3.9 or newer. Then `design-suite harness`
   previews the hook, MCP and `AGENTS.md` wiring for other harnesses; `--apply` writes it.
3. **Re-grade exit codes in every CI step, hook and hooks-map entry that calls an audit.**
   0 = clean, 1 = findings, **2 = refused (could not check)**. Exit 2 must fail the step loudly.
   Never fold it into a pass, and never count it as findings. Many refusals moved from 1 to 2 and
   many former silent passes are now 2 — see Breaking for the full list.
4. **Check for nested repositories.** If you run the suite from an unconfigured git repository
   inside a configured one, tools now refuse with exit 2 instead of auditing the outer project.
   Either onboard the inner repository (`survey.py`, then `init.py --from-survey` inside it) or run
   from / set `CLAUDE_PROJECT_DIR` / pass `--project-root` to the outer one.
5. **Pick a language adapter.** Set `adapters.lang` in `.design-suite/profile.json` to a shipped
   adapter: `dart`, `tsx`, `web` (new — Vue, Svelte, CSS, SCSS), `swift` or `kotlin` (new,
   unverified). An unset, `TODO` or unknown value now refuses with exit 2. `design-suite
   propose-config` proposes values for scaffolded `TODO` sections. Fill in `arch-rules.json`
   placeholders (`adapterPattern.bannedImports`, `screensGlob` on non-Dart stacks,
   `layerBoundaries.rules`) and `token_categories.motion.animated_widgets`, or delete the
   sections — placeholders now refuse rather than silently match nothing.
6. **Move report files.** Audit reports now default to `.design-suite/`:

   | Audit | Old default | New default |
   |---|---|---|
   | `audit_tokens.py` | `<pipelines.tokens>/findings.json` | `.design-suite/tokens-findings.json` |
   | `audit_focus_order.py` | `<pipelines.tokens>/focus_order_findings.json` | `.design-suite/focus-order-findings.json` |
   | `audit_accessibility.py` | `<pipelines.tokens>/a11y_findings.json` | `.design-suite/accessibility-findings.json` |
   | `audit_mock_api.py` | `<pipelines.mockApi>/findings.json` | `.design-suite/mock-api-findings.json` |
   | `audit_adapter_pattern.py` | `scripts/adapter_pattern_findings.json` | `.design-suite/adapter-pattern-findings.json` |
   | `audit_layer_boundaries.py` | `scripts/layer_boundaries_findings.json` | `.design-suite/layer-boundaries-findings.json` |

   For each: `git rm --cached` (or delete) the old file, repoint anything that reads it, and add
   the new name to `.design-suite/.gitignore` if yours predates this release (re-scaffolding with
   `init.py` adds them). Or keep the old location with `--out <old path>`.
7. **Run each audit once and triage before gating.** Several audits now see files they never saw
   (non-`lib/` Dart roots, tsx/web/Swift/Kotlin sources). New exit-1 findings are leads to review,
   not regressions; review before any `--update-baseline`.
8. **Expect the session-start offer.** On an unconfigured project, Claude Code now offers
   onboarding once per session, and the after-edit hooks say once per session that they are
   unconfigured. To configure the hooks map: `init.py --only hooks.map.json`, fill it in, confirm
   with `doctor.py`.

### Breaking

- **Refusals that used to exit 1 now exit 2.** Exit 1 means findings, so these read as findings
  when nothing had been checked. Affected: `audit_unused_tokens.py`, `audit_unwired_roles.py`,
  `audit_api_consistency.py`, `audit_error_handling.py` and `audit_pattern_adoption.py` when their
  `arch-rules.json` section is missing; the mock-API tools when their `config.json` is missing or
  invalid (previously a traceback). Real findings still exit 1. **You must** treat 2 as "could not
  check" and fail loudly; stderr names what is missing.
- **Language adapter is required.** Any audit that needs an adapter exits 2 when `adapters.lang` is
  unset, a `TODO`, or unknown. **You must** set it to `dart`, `tsx`, `web`, `swift` or `kotlin`.
  Swift and Kotlin projects that wired audits expecting a permanent exit 2 will now get real
  exit-1 findings — triage the first run before gating on it, and exempt token-definition files
  via `exceptions.json` `color.allowlistFiles` if the adapter misses yours.
- **`audit_tokens.py` refuses a partial sweep.** With zero findings but files of a stack its
  adapter cannot read under the scan root (e.g. `.vue`/`.css` under a `tsx` project), it exits 2
  instead of 0. With findings it still exits 1 and lists the unscanned files on stderr. **You
  must** set `adapters.lang` to an adapter that covers them (`web` for Vue/Svelte/CSS/SCSS), or list
  the suffixes in `.design-suite/exceptions.json` `acknowledgedUnscanned` if skipping them is
  deliberate.
- **`audit_reduced_motion.py` now fails on findings.** It exits 1 when it reports unwired animated
  nodes (it exited 0, so every run graded clean), and 2 when
  `token_categories.motion.animated_widgets` still holds the scaffolded `TODO`. **You must** fix or
  except the findings — they were always there — and replace the placeholder with real names.
- **`audit_adapter_pattern.py` and `audit_layer_boundaries.py` refuse instead of passing on
  nothing.** They exit 2 when zero files are in scope, the adapter has no import syntax, the
  `arch-rules.json` section is missing or still holds `TODO` placeholders, `bannedImports` /
  `mustNotImport` is empty, or (adapter pattern, non-Dart) no `adapterPattern.screensGlob` is set.
  `audit_layer_boundaries.py` previously crashed with exit 1 on the scaffold. **You must** fill
  the rules (`from` or `fromGlob` plus `mustNotImport`; real `{label, pattern}` bannedImports;
  e.g. `screensGlob: "**/pages/**/*"`) or delete the sections. After filling a layer rule that
  never worked, run `--update-baseline` to record existing debt.
- **`audit_promotion_candidates.py` and `audit_reinvented_components.py` no longer sweep a fixed
  `lib/**/*.dart`.** They read `source.root`/`source.roots` and the adapter, and exit 2 when the
  adapter has no widget-shape support (every non-Dart stack), a declared root is missing, or
  nothing matched. **You must**, on Dart, declare `source.root(s)` and `adapters.lang: dart`, and
  review newly visible candidates before any `--update-baseline`; on other stacks, drop these
  audits from CI and hooks.
- **Nested repositories refuse.** Project-root resolution now stops at the nearest git root. Run
  from an unconfigured git repository nested in a configured one, every tool that resolves the
  project exits 2 naming both paths, where it previously audited the outer project; the hooks
  no-op there. Plain subdirectories, configured nested repositories and a configured
  `CLAUDE_PROJECT_DIR` resolve as before. **You must** onboard the inner repository, or run from /
  point `--project-root` or `CLAUDE_PROJECT_DIR` at the outer one.
- **`survey.py` runs on unconfigured projects.** Without `--project-root` it no longer requires
  `.design-suite/` and exits 0 where it used to exit 2; it surveys `CLAUDE_PROJECT_DIR`, else the
  git root, else the working directory, and never walks up to an enclosing configured repository.
  From a non-git directory under a configured one, or outside `CLAUDE_PROJECT_DIR`, it now exits 2.
  `--check` is unchanged. **You must** stop using survey's exit 2 to detect "not onboarded" — test
  for `.design-suite/` or use `survey.py --check` — and pass `--project-root` where you relied on
  the walk-up. `sourceStamp.projectRoot` in the output names what was surveyed.
- **Report files moved into `.design-suite/`** for `audit_tokens.py`, `audit_focus_order.py`,
  `audit_accessibility.py`, `audit_mock_api.py`, `audit_adapter_pattern.py` and
  `audit_layer_boundaries.py`. `pipelines.tokens` / `pipelines.mockApi` no longer decide where
  reports go. Contents, exit codes, the `--findings` envelope and baselines are unchanged. **You
  must** remove or untrack the old files, repoint readers, and update `.design-suite/.gitignore` —
  or pin the old path with `--out`. The table is in the upgrade guide above.
- **`audit_mock_api.py` gained a second refusal.** A contract whose `optional_fields` block cannot
  be parsed exits 2 (previously 2 meant only "unknown contract"). Projects that do not use
  `optional_fields` cannot hit it. **You must**, if you adopt it, treat 2 as refused and fail
  loudly; stderr names the contract and key.
- **`audit_accessibility.py`** exits 2 when an `excludeFilesImporting` entry lacks a non-empty
  `import` prefix or a `reason`. **You must** give every entry both. (The audit itself is
  disabled in this release — see Changed.)
- **`audit_focus_order.py` and the semantics checks now report on tsx/web** instead of refusing.
  **You must** triage the new findings, or except kinds via `exceptions.json` (e.g.
  `static_element_click_handler`) with a reason. Dart, Swift and Kotlin behaviour is unchanged.
- **`audit_skill_paths.py`** now also runs the hashed client-name denylist over every tracked file,
  can exit 1 on a hit anywhere in the tree, and exits 2 when `bin/client_denylist.sha256` is
  missing or `git ls-files` cannot run. Normally only this repository's own CI calls it. **You
  must** run it inside a git checkout of a release that ships the digest file; on a hit, replace
  the name with "this project" or a placeholder (the finding prints a digest prefix, never the
  name).
- **`hooks/audit_on_edit.py`** exits 1 when given a harness name `bin/harness_hooks.py` does not
  support, and prints a once-per-session notice when no hooks map is configured. Bare `hooks.json`
  invocations need no change. **You must**, for non-Claude harnesses, regenerate the hook config
  with `harness_hooks.py` and treat exit 1 as "hook misconfigured".

### Added

- **Language adapters**: `web` (Vue, Svelte, CSS, SCSS), plus `swift` and `kotlin` (maturity
  `unverified`). Focus-order, semantics and error-handling capabilities for `tsx`/`web`.
- **Session-start onboarding offer**: a SessionStart hook notices an unconfigured project and
  offers onboarding once; the after-edit hooks say once per session when they are unconfigured.
- **`design-suite` CLI**, installable with `pip install` from a suite checkout (tested in a
  virtualenv; `pipx` and `uv tool install` use the same mechanism but were not run), with a script locator for non-Claude harnesses. Subcommands include `mcp` (MCP server
  with onboarding and chain tools, preview/apply contract), `harness` (generated `AGENTS.md` block,
  MCP configs and skills mirror for other harnesses) and `propose-config` (inferred values for
  scaffolded `TODO` config sections).
- Portable session-start and after-edit hooks with per-harness adapters (`design-suite hooks`), and an
  opt-in git pre-commit fallback (`design-suite hooks --git`).
- SARIF 2.1.0 export (`bin/export_sarif.py`); audits that could not check appear as failed runs.
  Diff-scoped PR design review (`/design-review-pr`), which posts only with `--post` after you approve.
- DTCG 2025.10 token export and drift import (`bin/export_tokens_dtcg.py`,
  `bin/import_tokens_dtcg.py`).
- `audit_semantics.py` — four precisely scoped accessibility rules.
- `audit_pattern_adoption.py` — the half of port-pattern adoption a consumer can measure.
- `/audit-contrast` has a real implementation instead of pointing elsewhere.
- `audit_prose_flags` flags any flag passed to a script that parses no arguments.
- Evidence records are stamped with the commit they were verified at.
- `bin/eval_results_read.py` — refuses to let a dead eval run read as a measurement, including
  runs whose trace shows permission denials or that ended after one turn.
- `bin/attest.py` — runs every gate and prints the environment the verdict was reached under.
  Exit 0 verified, 1 a gate failed, 2 partial (not a pass).
- `bin/gate_consumer_compat.py` — fails a change that breaks consumers without a written migration
  note. This is what produced most of the Breaking section above.
- `LICENSE` (MIT) and a `license` field in both plugin manifests; a declared minimum Python
  version (3.9); this changelog.

### Changed

- `/audit-accessibility` and `/audit-copy` are **disabled** (maturity `disabled`): measured mostly
  false positives on real projects. Their scripts refuse with exit 2 and every report names them as
  disabled. Remove them from CI gates; they will return when re-scoped.
- All audits emit the **common findings envelope**. If you parse audit output directly, re-check
  your field access against it.
- Audit skill descriptions now state what each audit writes, instead of claiming "read-only".
- `maturity` and `invocation` values were re-audited against eval evidence; four descriptions that
  overclaimed were corrected. Read `docs/CATALOG.md` for current values.
- The `DESIGN.md` template is narrowed to the app archetype it is scaffolded for.
- `audit_tokens` skips copied third-party files (a licence-and-version banner), mock and fixture
  files, and Storybook stories, and prints every skipped file with its reason. To scan one anyway,
  list it under `scanSkipFiles.include` in `.design-suite/exceptions.json`.
- `house-style` 0.1.1: its role resolver stops at the nearest git root (matching the
  nested-repository change above), and `/generate-client-readiness` wording was tidied.

### Fixed

- Audits that described themselves as read-only no longer write into your project tree.
- `/review-docs` no longer commits while claiming to be read-only.
- `/map-project` actually performs the write it describes.
- Web adapter precision: many false-positive classes removed (stories, mock and fixture files,
  copied third-party stylesheets, dimension and graph data, HTML entities, theme palettes and
  colour maps, masks, `var()` fallbacks, custom-property definitions, canvas painting, `0ms`,
  off-screen hide hacks). On the latest set of public projects it was not tuned on, 3.9% of
  sampled findings were wrong overall, but two of five projects were still above 5% (8.3% and
  6.7%), so the adapter stays `unverified`. Planted violations were found 25 of 25. Measurements:
  `docs/MEASUREMENT-*-web-adapter*.md`.
- The bundled SARIF 2.1.0 schema now carries the exact OASIS copyright notice its licence
  requires (`templates/vendor/sarif-2.1.0/NOTICE`); it stays under OASIS terms, not MIT.
- Kotlin token-definition scope, sizes and reduced-motion import lines; Swift palette sites;
  alias-aware multi-rule layer boundaries.
- Vendored and generated directories are skipped visibly rather than silently.
- `survey` ranks UI roots by evidence, drops the workspace root, and seeds the UI stack rather than
  a server's.
- `audit_unwired_roles` sweeps the package that defines the roles, so they are no longer reported
  unwired just because they were not scanned.
- `audit_mock_api` no longer reports an optional field's absence as drift where a record could not
  carry it.
- `audit_promotion_candidates` resolves the design-system package from the one profile section
  that declares it.
- Hooks resolve the project from the harness's start directory.
- Named refusals for placeholder accessibility minimums and a missing mock-API profile.
- `propose-config --apply all` with nothing proposed exits 2, not 0.
- `bin/cleanup_worktrees.py` considers every worktree and reports its own by absolute path.
- The understand-existing-project chain no longer stalls part-way.

---

## [0.1.0] - 2026-09-17

The first tagged release, and the point at which the suite became something a consumer could pin.

Everything before this tag was the extraction: the suite grew inside a single Flutter application,
and `0.1.0` is where it finished becoming project-agnostic — **252 hardcoded documentation paths
went to 0**, and every project-specific fact moved into a `.design-suite/` profile in the consuming
repository.

### Added

- **Two plugins in one marketplace.** `design-suite` is the universal engine and installs into any
  project; `house-style` carries org letterhead, PR process and client-readiness
  reporting, and installs into internal projects only — so a client-facing repository takes the
  engine without inheriting internal branding.
- **The context layer and doc-role resolution.** Skills refer to documents by *role*
  (`{{doc:design}}`) and resolve the role per project through `bin/resolve.py` and a
  `docs.manifest.json`, instead of naming a path. An unresolvable role is an error, never a guess.
- **The three-layer architecture** — a stdlib-only engine holding zero project literals, language
  adapters behind declared seams (`dart.py`, `tsx.py`), and CLI entry points that hold no language
  knowledge. Four CI gates enforce that no project literal reaches the engine.
- **The audit set** — design tokens, unused tokens, unwired semantic roles, reduced motion, focus
  order, contract headers, error handling, adapter pattern, layer boundaries, API consistency,
  reinvented components, promotion candidates, doc staleness, proposal status, prose flags,
  CLAUDE.md drift, and mock-API contract drift. All read-only: they report findings and never edit.
- **Capability negotiation and `INERT`.** An audit that cannot answer for the current stack raises
  `CapabilityError` rather than returning `False` or an empty set, and an audit that skipped itself
  reports `INERT` rather than being baselined clean.
- **Documentation scaffolding** — a template per doc role, `/bootstrap-design-docs` to propose a
  documentation layer one document at a time, and `/map-project` and `/survey` to inspect an unknown
  project without writing to it.
- **Per-field provenance and ratification.** Every profile field records whether it was inferred by
  a machine or ratified by a human; `bin/doctor.py` reports unratified fields as untrusted and a
  ratified field the tree no longer agrees with as `CONTRADICTED` and fatal.
- **`bin/preflight.py`** — which skills can run against this project, and what blocks the rest,
  answered before a consumer finds out one skill at a time.
- **Mock-API contract automation** — `/wire-endpoint`, `/sync-mock-api`, drift auditing, and OpenAPI
  generation.
- **The asset pipeline** — `/add-asset`, `/generate-asset`, `/animate-asset`, with provenance and
  licence recorded per asset.
- **Copy and brand voice** — `/establish-brand-voice` and `/rewrite-copy`.
- **Generated catalogues.** `docs/CATALOG.md`, `docs/SKILLS.md` and the field guide are generated
  from component frontmatter and gated, because hand-written counts were wrong four separate times.
  Every component declares an `invocation` tier (`auto`/`explicit`, decided by blast radius rather
  than difficulty) and a `maturity` (`proven`/`unverified`/`experimental`/`pointer`/`disabled`).
- **An eval suite**, and the free gates that check its fixtures really produce the state their cases
  branch on.
- **The version and pinning contract** — this tag, and the statement of what a consumer pinning it
  is entitled to expect.

### Changed

- `/audit-accessibility` and `/audit-copy` ship as **`disabled`**, not as low-confidence. Measured
  on two real projects, accessibility produced 100% false positives with zero true-positive capacity
  on one of them, and 73% of copy's commit-gating findings were wrong. Both refuse with exit 2
  rather than running, and every reporting surface names them as disabled — their silence must not
  read as a pass. The measured reasons and the bar for re-enabling each are in their command files.
