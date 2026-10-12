# Backend Quality Suite — Changelog

What changed in each version, written for the people who have to decide whether to repin.

Distinct from the decision log, which records *why* things were decided and is read by
contributors. This is read by **consumers** — projects that install `backend-suite@backend-quality-suite`
and pin a `backend-suite--v*` tag — and it records *what they now have to do*.

Format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The heading shape
(`## [X.Y.Z] - YYYY-MM-DD`) is a machine contract, not a style preference.

## What earns an entry

The bar is **consumer-visible**: if nothing outside this repository could observe the change, it
does not belong here. Internal refactors, test and eval-harness changes, and documentation fixes
normally fail that test — including them trains readers to skim, which is how a breaking change
gets missed.

Concretely, a consumer can observe: a script or agent appearing, disappearing, or being renamed; a
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

---

## [Unreleased]

### Added

- **Go language adapter** (`backend_suite/adapters/go.py`) — fifth shipped language
  adapter: Gin, Echo, Chi, and Fiber routing, plus the base capability set (models,
  validation, middleware, api_resources, policies). A project with a root `go.mod` is now
  proposed `go` by `survey.py`; set `adapters.lang: go`. The adapter refuses
  `audit_layer_boundaries` (exit 2) because a Go `import` names a package path, not a file
  path. The error model follows errors-as-values (`if err != nil`, `errors.As`, `%+v`
  stringify), and members read off untyped container extracts (`c.MustGet("key").(X)`
  vs a plain `MustGet`) are distinguished so service reads resolve without inventing types.

- **Rust language adapter** (`backend_suite/adapters/rust.py`) — fourth shipped language
  adapter: Axum, Actix Web, Rocket, Poem, and Warp routing, plus the base capability set
  (models, validation, middleware, api_resources, policies). A project with a root
  `Cargo.toml` is now proposed `rust` by `survey.py`; set `adapters.lang: rust`. The adapter
  refuses `audit_layer_boundaries` (exit 2) because `use` names a module path, not a file
  path, and deliberately has no `dependency_injection` capability — Rust has no DI-container
  idiom and declaring one would invent a boolean.

- **Toolchain gates** — a project's declared `checkScripts` now run as gates beside the
  suite's own audits (`audit_toolchain_gates.py`), closing the gap where a project's own
  failing checks could not fail its CI.

### Fixed

- **PHP adapter: Symfony capability gating** — having a `symfony/*` component as a dependency
  no longer classifies the tree as a Symfony *application*. `symfony_di / symfony_forms /
  symfony_doctrine / symfony_security / symfony_twig` are offered only on a full-stack signal
  (`symfony/framework-bundle` + `Kernel.php` + `config/routes.*` or `config/services.*`).
  Projects that merely consume Symfony components stop reporting `declared-capability-unused`
  on `source.root`.

- **`audit_endpoint_parity`** — swagger-php 6 `#[OA\...]` attribute markers are now
  recognized alongside the annotation forms (`@OA\...`), so documented endpoint parity is
  still measured on PHP 8 projects using attributes.

---

## [0.3.0] - 2026-10-12

Symfony capability gating in PHP adapter; `audit_form_request_validation` crash fix; ROADMAP multi-language strategy.

### Fixed

- **`audit_form_request_validation.py` crash** — the audit was the only script missing the standard
  `sys.path` bootstrap (`from _bootstrap import PLUGIN_ROOT`), causing `ModuleNotFoundError` on every
  direct invocation. It also called `adapter.capabilities(None)` instead of a real `AdapterContext`,
  which would crash inside the PHP adapter's `_looks_laravel()`. Both fixed: the audit now boots
  correctly, checks the `form_requests` capability with a proper context, and **refuses cleanly
  (exit 2)** on non-Laravel projects with "php adapter does not expose form_requests capability"
  instead of crashing.

- **`audit_skill_paths.py` gate** — added exemption for the same provenance-docstring pattern
  already exempted in `audit_error_handling.py`, so the gate no longer reports an unexplained
  dead path on the audit's own file.

### Added

- **PHP adapter: Symfony capability gating** — Laravel-only capabilities (`laravel_routing`,
  `eloquent_models`, `form_requests`, `api_resources`, `policies`) now only offered when project
  reads as Laravel (composer.json `laravel/framework` or `illuminate/*`, `artisan` script, or
  `Illuminate\` namespace). Symfony capabilities (`symfony_routing`, `symfony_di`, `symfony_forms`,
  `symfony_doctrine`, `symfony_security`, `symfony_twig`) only offered when project reads as
  Symfony (composer.json `symfony/framework-bundle`, `Kernel.php`, or `config/routes.yaml`).

- **LANGUAGE_STRATEGY.md** — multi-language support plan covering PHP (Symfony, Slim), Node.js/TypeScript,
  Go (Gin, Echo), Python (FastAPI, Django), Java (Spring Boot), with capability matrix,
  implementation template, decision matrix (weighted scoring), and milestone definitions
  (Alpha/Beta/RC/GA).

- **ROADMAP.md** — added Workstream E (Multi-language) with Phases 1-5, Capability Matrix across
  5 languages, Implementation Priority by quarter, and updated Open Issues table.

### Changed

- **`verify_seam.py`** — seam proof now exercises the shipped `node` adapter alongside `php`,
  proving the engine runs three languages (stublang, php, node) through the same seam with no
  engine changes.

- **Issues #14, #15, #19, #21 closed** — Symfony adapter delivered, Node.js adapter released in
  v0.2.0, ROADMAP updated, FormRequest crash fixed.

---

## [0.2.0] - 2026-10-11

Third shipped language adapter: **Node.js/TypeScript** (Express, Fastify, NestJS, Hono, Koa, AdonisJS).
Laravel adapter capability gating fixed. Survey now maps `package.json` to `node` adapter.

### Breaking

- **Survey mapping changed:** `package.json` now proposes the `node` language adapter instead of the
  design-suite-era `tsx` UI adapter (which this plugin never shipped). Projects that relied on the
  old mapping will now receive `adapters.lang: node` in their scaffolded profile. **You must** run
  `survey.py` again on Node.js/TypeScript projects, or set `adapters.lang: node` manually. The old
  `tsx` adapter does not exist in this plugin and would refuse with exit 2.

### Added

- **Node.js/TypeScript language adapter** (`plugins/backend-suite/backend_suite/adapters/node.py`):
  - 7 base capabilities: `routing`, `models`, `validation`, `middleware`, `dependency_injection`,
    `api_resources`, `policies`
  - 6 framework-specific capabilities (gated behind framework detection):
    `express_routing`, `fastify_routing`, `nestjs_routing`, `hono_routing`, `koa_routing`,
    `adonis_routing`
  - Structural extraction: `class_fields`, `class_members`, `member_reads`, `receiver_aliases`,
    `typed_member_reads` (handles TypeScript constructor parameter properties)
  - `ERROR_HANDLING` syntax: catch_var (typed/untyped), type_guard, stringify (String(),
    template literals, concatenation), type_test
  - `API_CONSISTENCY` syntax: user_facing, defaulted, compared, tappable (@Controller/@Get/@Post)
  - Fixtures: `express`, `nestjs` (zero-state, scaffoldable via `build_fixture.py`)
  - Sweep checks: `debug_statement` (console.log/debugger), `plaintext_secret`

- **PHP adapter: Symfony capability gating** — Laravel-only capabilities (`laravel_routing`,
  `eloquent_models`, `form_requests`, `api_resources`, `policies`) now only offered when project
  reads as Laravel (composer.json `laravel/framework`, `artisan` script, or `Illuminate\` namespace).
  Symfony capabilities (`symfony_routing`, `symfony_di`, `symfony_forms`, `symfony_doctrine`,
  `symfony_security`, `symfony_twig`) only offered when project reads as Symfony (composer.json
  `symfony/framework-bundle`, `Kernel.php`, or `config/routes.yaml`).

- **LANGUAGE_STRATEGY.md** — multi-language support plan covering PHP (Symfony, Slim), Node.js/TypeScript,
  Go (Gin, Echo), Python (FastAPI, Django), Java (Spring Boot), with capability matrix,
  implementation template, decision matrix, and milestone definitions.

- **Eval fixtures** for Express, NestJS, and Symfony frameworks with scaffold shims.

### Changed

- **README.md** — major rewrite for scanability: badges, TL;DR, capability tables, quick links.
- **survey.py** — `package.json` now maps to `node` adapter; `adapter_reachability()` control
  ensures every shipped adapter is reachable from some manifest.
- **verify_seam.py** — seam proof now exercises the shipped `node` adapter alongside `php`.
- **survey_test.py** — expects `language_adapters() == ["node", "php"]` and `node` proposed for
  `package.json` projects.
- **survey_source_roots_test.py** — uses Dart fixture for "mapped adapter not present" control
  (since `node` now ships and is mapped to `package.json`).

### Fixed

- **PHP adapter capability gating** — Laravel capabilities no longer offered on non-Laravel PHP
  projects (was: offered on any PHP tree with `source.root`). `detect_capability` now scans the
  declared `source.routesFile` in addition to `source.root` for routing evidence.
- **suite_upgrade_test.py** — fixture-pinned tests now raise `SkipTest` with message instead of
  passing; run_tests.py correctly reports them as "skipped — a skip is not a pass".

---

## [0.1.0] - 2026-09-17

First public release of the re-domained backend-quality-suite (formerly ai-design-suite, then
ai-backend-suite). PHP language adapter with Laravel/Lumen support, capability negotiation, and
audit engine.

### Added

- **PHP language adapter** — stdlib-only, zero dependencies, Laravel/Lumen backend support.
- **Capability negotiation** — `capabilities(ctx)` and `detect_capability(ctx, name)` protocol;
  audits raise `CapabilityError` (exit 2) instead of faking a pass when a capability is unsupported.
- **Laravel capabilities** — `laravel_routing`, `eloquent_models`, `form_requests`, `api_resources`,
  `policies` with detection via composer.json, artisan, or `Illuminate\` namespace.
- **Base capability** — `routing` (Route facade, `$router` closures, PHP 8 attributes).
- **Audit engine** — `scan_tree` seam, `Check` declarative model, common findings envelope.
- **Sweep checks** — `debug_statement` (dd/dump/var_dump), `plaintext_secret`.
- **Structural extraction** — `class_fields`, `class_members`, `member_reads`, `receiver_aliases`,
  `typed_member_reads` (with `CapabilityError` on `::class` bindings).
- **Audit syntaxes** — `ERROR_HANDLING` (catch, instanceof, stringify), `API_CONSISTENCY`
  (user_facing, defaulted, compared, tappable).
- **Contract-header audits** — `audit_layer_boundaries`, `audit_error_handling`,
  `audit_api_consistency`, `audit_contract_headers`.
- **Laravel-specific audits** — `audit_route_model_binding`, `audit_form_request_validation`.
- **Arch-rules template** — `.backend-suite/arch-rules-laravel.json.template`.
- **Documentation** — `docs/CONCEPTS.md` (Laravel quick ref), `docs/ADOPTING.md` (migration guide
  section), `docs/USER-GUIDE.md` (Laravel quick start), `docs/ROADMAP.md` (current status).
- **Eval infrastructure** — `build_fixture.py`, `eval_suite_lint.py`, `eval_fixture_selftest.py`,
  `verify_seam.py` (proves engine is not language-shaped).
- **Survey system** — `survey.py` discovers stack, proposes `adapters.lang`, `source.root`,
  `source.fileGlob`; `init.py --from-survey` scaffolds profile.
- **Pre-commit hook** — `.git/hooks/pre-commit` runs audits on staged files via `hooks.map.json`.
- **GitHub release** — repo public at https://github.com/irfan-dahir/backend-quality-suite,
  release `backend-suite--v0.1.0` published with notes.

### Changed

- **Repository identity** — white-label branding, copyright "Irfan Dahir", marketplace
  `irfan-dahir/backend-quality-suite`, install `backend-suite@backend-quality-suite`.
- **Zero PHP runtime dependencies** — PHP support is a Python static-analysis adapter; no
  Composer/Artisan required to run the suite.
- **Old ai-backend-suite issue links** replaced with local RFC section references
  ("recorded in RFC-000X §N").
- **MEASUREMENT-\* docs** (12 files from design-suite era) deleted.
- **Lumen→Laravel migration guide** dropped per user decision.

### Fixed

- **survey.py crash** — derived collaterals now skipped instead of crashing on missing keys.
- **audit_prose_flags** — harvest finds plugin root by walking up to directory containing
  `commands/`/`agents/`; help text runs from workspace root (walks up to `.git`).
- **audit_route_model_binding** — controller resolution completed; records `scanned` count.
- **Empty-sweep refusal** — audits exit 2 when no files in scope instead of reporting clean.
- **Exemption reasons** — all exemptions now require written reasons.

---

> **Note:** The 0.1.0 entry was reconstructed from git history after the tag was created.
> Nothing before 0.1.0 is covered — this suite began its public life at that tag.