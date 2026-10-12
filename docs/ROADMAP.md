# Roadmap

> **Status: Active development.** This document reflects the current state of work. Items marked ✅ are done; items marked 🔄 are in progress; items marked 📋 are planned.

---

## Current Status Summary

| Workstream | Status | Summary |
|---|---|---|
| **A — Verification** | ✅ Mostly done | A1 (`verify.py`) built; A2/A3 unblocked; evidence-backed maturity gated |
| **B — Portability** | ✅ PHP/Laravel done | PHP adapter shipped with 6 capabilities; Laravel routing signatures; 5 new capabilities |
| **C — Migration** | ✅ Mostly done | C1/C2/C4 done; C3 audit-first; C5 pending |
| **D — Defects** | 🔄 Partially done | D1/D4/D5 done; D2/D3 N/A for PHP |
| **E — Multi-language** | ✅ PHP/Node/Rust/Go shipped | Python adapter planned; Java dropped, Rust shipped in its place (see LANGUAGE_STRATEGY.md) |
| **New: Laravel audits** | ✅ Done | `audit_route_model_binding`, `audit_form_request_validation` |
| **New: Harness integration** | ✅ Done | AGENTS.md, MCP configs for 11 harnesses, pre-commit hook |

---

## Workstream E — Multi-Language Support (from LANGUAGE_STRATEGY.md)

### Phase 1: PHP Ecosystem (Current + Next)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Laravel/Lumen** | `composer.json` + `artisan` | 11 capabilities | ✅ Done |
| **Symfony** | `composer.json` + `Kernel.php` | routing, services, DI, forms | ✅ Shipped (Issue #14) |
| **Slim/Laminas** | `composer.json` | routing, middleware | 📋 Planned |
| **Plain PHP** | `composer.json` only | routing (attributes), models | ✅ Shipped |
| **WordPress** | `wp-config.php` | hooks, REST API | 📋 Low priority |

**Done:** Symfony support (2nd most popular PHP framework), shipped in 0.3.0.

### Phase 2: Node.js / TypeScript

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Express** | `package.json` + `express` dep | routing, middleware, error handling | ✅ Shipped |
| **Fastify** | `package.json` + `fastify` dep | routing, schemas, hooks | ✅ Shipped |
| **NestJS** | `package.json` + `@nestjs/core` | controllers, guards, pipes, DI | ✅ Shipped |
| **Hono** | `package.json` + `hono` dep | routing, middleware | ✅ Shipped |
| **Koa** | `package.json` + `koa` dep | middleware, routing | ✅ Shipped |
| **AdonisJS** | `package.json` + `@adonisjs/core` | controllers, validators, ORM | ✅ Shipped |
| **Plain TS/JS** | `tsconfig.json`/`package.json` | basic routing | ✅ Shipped |

The whole phase shipped with `node` (v0.2.0 and extended since). **Detection strategy:**
1. `package.json` dependencies
2. Import patterns (`import express from 'express'`, `require('express')`)
3. Framework-specific files (`nest-cli.json`, `fastify.config.js`)

### Phase 3: Go

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Gin** | `go.mod` require + `github.com/gin-gonic/gin` | routing, middleware, binding | ✅ Shipped |
| **Echo** | `go.mod` require + `github.com/labstack/echo` | routing, middleware, binding | ✅ Shipped |
| **Chi** | `go.mod` require + `github.com/go-chi/chi` | routing, middleware | ✅ Shipped |
| **Fiber** | `go.mod` require + `github.com/gofiber/fiber` | routing, middleware | ✅ Shipped |
| **Standard lib** | `go.mod` only | `net/http` Handle/HandleFunc/ServeMux | ✅ Shipped |

**Detection:** `go.mod` require lines (skipping the `module` directive's own path) or source
imports; versioned module subpaths (`/v2`…`/v8`) resolve to the base module.

Two honest refusals, not omissions:

- `IMPORT_TARGETS = "module"` — a Go `import` names a *package path*, not a file path, so
  `audit_layer_boundaries` **refuses (exit 2)** rather than resolving every same-module
  import as external and printing a confident zero.
- Base `routing` is dynamic rather than `net/http`-only: `r.GET("/orders", …)` and `mux.HandleFunc`
  both count, the way Rust's base set recognises `Router::new().route(…)` across every framework.

### Phase 4: Python

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **FastAPI** | `pyproject.toml` + `fastapi` dep | routing, models, dependencies | 🥇 High |
| **Django** | `pyproject.toml`/`requirements.txt` + `django` | models, views, ORM, admin | 🥇 High |
| **Flask** | `pyproject.toml` + `flask` dep | routing, blueprints | 🥈 Medium |
| **Starlette** | `pyproject.toml` + `starlette` dep | routing, middleware | 🥈 Medium |
| **FastAPI + SQLAlchemy** | `sqlalchemy` dep | models, migrations | 🥈 Medium |

**Detection:** `pyproject.toml`, `requirements.txt`, `setup.py`, `poetry.lock`, imports

### Phase 5: Rust (Shipped)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Axum** | `Cargo.toml` + `axum` dep | routing, models, validation | ✅ Shipped |
| **Actix Web** | `Cargo.toml` + `actix-web` dep | routing, middleware | ✅ Shipped |
| **Rocket** | `Cargo.toml` + `rocket` dep | routing (attributes) | ✅ Shipped |
| **Poem** | `Cargo.toml` + `poem` dep | routing (`Route::new()`) | ✅ Shipped |
| **Warp** | `Cargo.toml` + `warp` dep | routing (`warp::path`) | ✅ Shipped |

**Detection:** `Cargo.toml` dependencies + `use` paths. `IMPORT_TARGETS` is `module`, so
`audit_layer_boundaries` refuses (exit 2) rather than resolving `use` paths as files.

> **Java/JVM was dropped, not deferred** (issue #18, closed as not-planned): the zero-dep seam
> is at its most fragile on annotation processors and the split `pom.xml`/`build.gradle`/
> `build.gradle.kts` surface, and the decision matrix scored Spring Boot lowest. Rust replaced
> it as the fourth language.

### Capability Matrix (Shipped vs Planned)

| Capability | PHP | Node/TS | Rust | Go | Python |
|---|---|---|---|---|---|
| **routing** | ✅ | ✅ | ✅ | ✅ | 📋 |
| **models/ORM** | ✅ (Eloquent) | ✅ (Prisma/TypeORM/Sequelize) | ✅ (sea-orm/sqlx derives) | ✅ (structural follows) | 📋 (SQLAlchemy/Django ORM) |
| **validation** | ✅ (FormRequest) | ✅ (Zod/class-validator) | ✅ (validator derives) | ✅ (go-playground/validator) | 📋 (Pydantic) |
| **routing signatures** | ✅ (Laravel+base) | ✅ (Express/Fastify/Nest) | ✅ (Axum/Actix/Rocket/Poem/Warp) | ✅ (Gin/Echo/Chi/Fiber) | 📋 (FastAPI/Django) |
| **contract headers** | ✅ | ✅ | ✅ | ✅ | 📋 |
| **layer boundaries** | ✅ | ✅ | ✅ (refuses: module imports) | ✅ (refuses: module imports) | 📋 |
| **route coverage** | ✅ | ✅ | ✅ | ✅ | 📋 |
| **cache TTL** | ✅ (Laravel) | 📋 | 📋 | 📋 | 📋 |

### Implementation Priority

| Phase | Adapter | Status |
|---|---|---|
| 1 | PHP (Laravel, Symfony) | ✅ Shipped |
| 2 | Node.js/TypeScript | ✅ Shipped (v0.2.0) |
| 5 | Rust (Axum, Actix Web, Rocket, Poem, Warp) | ✅ Shipped |
| 3 | Go (Gin, Echo, Chi, Fiber) | ✅ Shipped |
| 4 | Python (FastAPI, Django, Flask, Starlette) | 📋 Next |

### Design Principles

| Principle | Implementation |
|---|---|
| **Zero deps** | Adapters use only stdlib + regex/ast parsing |
| **Capability-driven** | Each adapter declares capabilities it implements |
| **Framework-aware** | Adapter detects framework (Laravel, Symfony, Express, FastAPI, etc.) |
| **Graceful degradation** | Missing capability = refusal (exit 2), not fake pass |
| **Seam-based** | Engine never imports adapters; capabilities requested via protocol |

### Adapter Template (New Language)

See `LANGUAGE_STRATEGY.md` for the full adapter template and integration checklist.

---

## Completed Work (as of this commit)

### Workstream A — Verification ✅

| Item | Status | Notes |
|---|---|---|
| **A1** `bin/verify.py <component>` | ✅ Done | Runs mechanical parts, writes evidence to `.backend-suite/evidence/` |
| **A2** Evidence-backed maturity | ✅ Done | `catalog.py` gates `proven` on evidence file |
| **A3** Zero-result guard | ✅ Done | Audits refuse on empty sweeps (exit 2) |
| **A4** Oracle records what changed | 📋 Planned | |
| **A5** Single local CI command | 📋 Planned | |

### Workstream B — Portability ✅

| Item | Status | Notes |
|---|---|---|
| **B1** Third adapter (tsx) | ✅ Superseded | The seam-proof is three shipped adapters — php, node, rust (Workstream E) |
| **B2** `/onboard-new-client` | ✅ Done | `survey → init --from-survey` works |
| **B3** Cross-consumer drift check | 📋 Planned | |
| **B4** Two-plugin split | ✅ Resolved | Stays two (backend-suite + house-style) |
| **B5** Derive PROJECT_NAMES | 📋 Planned | |

### Workstream C — Migration ✅

| Item | Status | Notes |
|---|---|---|
| C1 `skeleton-auditor` | ✅ Moved | |
| C2 `check_asset_registration.py` | ✅ Moved | |
| C3 Asset pipeline | 📋 Audit first | |
| C4 `/cut-release` | ✅ Stays | Stack-specific |
| C5 `mock_api/config.json` | 📋 Fix | Not in profile audits list |

### Workstream D — Defects

| Item | Status | Notes |
|---|---|---|
| D1 `token_categories.sizing` | ✅ Fixed | Pattern added, 14 occurrences measured |
| D2 styled-components | 📋 N/A | N/A for PHP |
| D3 JSX text | 📋 N/A | N/A for PHP |
| D4 `promotion_candidates` | ✅ Baselined | |
| D5 12 duplicate widgets | ✅ Baselined | |

### New Work Completed

| Feature | Status | Details |
|---|---|---|
| Laravel adapter | ✅ Done | 6 capabilities: routing, laravel_routing, eloquent_models, form_requests, api_resources, policies |
| `audit_route_model_binding` | ✅ Done | Implicit/explicit bindings, resource routes, controller signatures |
| `audit_form_request_validation` | ✅ Done | Missing rules/authorize, duplicate/empty rules |
| Laravel arch-rules template | ✅ Done | `arch-rules-laravel.json.template` |
| Harness integration | ✅ Done | AGENTS.md, MCP for 11 harnesses, pre-commit hook |
| Harness matrix doc | ✅ Done | 11 tools in `research/harness-support-matrix-2026-10-08.md` |

---

## Open Issues

| # | Issue | Status | Effort |
|---|---|---|---|
| 1 | Laravel quick-start guide in USER-GUIDE.md | ✅ Done | Done |
| 2 | Minimal arch-rules.json template | ✅ Done | `arch-rules-laravel.json.template` |
| 3 | `audit-form-request-validation.py` backing script | ✅ Done | |
| 4 | Route-model-binding controller resolution | ✅ Done | Pre-compiled regexes |
| 5 | `audit_prose_flags` false positives | ✅ Done | Fixed plugin root detection |
| 6 | `suite_upgrade_test.py` fixture dependency | ✅ Skipped | Fixture revisions don't exist in fork |
| 7 | Lumen → Laravel migration guide | 📋 Planned | |
| 8 | Wire harness for plugin itself | ✅ Done | AGENTS.md, MCP, pre-commit |
| 9 | Laravel Adapter Quick Reference in CONCEPTS.md | ✅ Done | Section exists in docs/CONCEPTS.md |
| 10 | ROADMAP.md current status | ✅ Updated | This file |
| 14 | Symfony adapter (PHP) | ✅ Done | Shipped in 0.3.0 |
| 15 | Node.js/TypeScript adapter | ✅ Done | Released in v0.2.0 |
| 16 | Go adapter | ✅ Done | Shipped as the fifth language adapter |
| 17 | Python adapter | 📋 Planned | Tracked in LANGUAGE_STRATEGY.md Phase 4 |
| 18 | Java/JVM adapter | ✅ Closed not-planned | Dropped; Rust shipped in its place |
| 19 | ROADMAP.md multi-language update | ✅ Done | This update |
| 21 | `audit_form_request_validation` crash fix | ✅ Done | Fixed in commit 943a353 |
| 25 | Rust adapter | ✅ Done | Shipped as the fourth language adapter |
| 26 | Sync stale docs (README, ONBOARDING, ROADMAP, LANGUAGE_STRATEGY) | 🔄 In progress | This branch |

---

## Next Priority Work

| Priority | Work | Rationale |
|---|---|---|
| 1 | Python adapter (Phase 4) | FastAPI/Django high value |
| 2 | Heal the two documented known-red test files (`suite_upgrade_test.py`, `gate_consumer_compat_test.py`) | Pinned to fixture revisions not in this fork's lineage; they auto-heal on the next release tag |
| 3 | Tag the next release (`backend-suite--v0.4.0`) from the `[Unreleased]` changelog | Releases the rust and go adapters and the toolchain gates to consumers; heals the known-red baseline |

---

## Test Baseline

```
63 test files | 538 cases | 61 passed | 2 failed (documented)
eval_suite_lint: 14/14 clean
eval_fixture_selftest: 6/6 fixtures
```

The two failing tests are documented fixture-pinned cases that require a tagged release to auto-heal.

---

## Deployment Notes

- **Repo**: https://github.com/irfan-dahir/backend-quality-suite (public)
- **Install**: `pip install git+https://github.com/irfan-dahir/backend-quality-suite.git`
- **CLI**: `backend-suite` command after install
- **Tag**: `backend-suite--v0.3.0`
- **CI**: 16 gates in `.github/workflows/validate.yml`

---

## Principles (Unchanged)

1. **Report, never auto-fix** — audits produce findings; human decides
2. **One direction of truth** — skills read context layer, write derived artifacts
3. **Zero dependencies** — stdlib-only Python, no install step
4. **No project literals** — path/token names in engine code = bug
5. **Silence must be impossible** — every check produces finding or error, never shrug

The governing principle: **an audit that reports nothing must never be indistinguishable from a check that did not run.**

---

_Last updated: 2026-10-12_