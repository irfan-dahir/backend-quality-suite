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
| **E — Multi-language** | 📋 Planned | Symfony, Node.js, Go, Python, Java adapters (see LANGUAGE_STRATEGY.md) |
| **New: Laravel audits** | ✅ Done | `audit_route_model_binding`, `audit_form_request_validation` |
| **New: Harness integration** | ✅ Done | AGENTS.md, MCP configs for 11 harnesses, pre-commit hook |

---

## Workstream E — Multi-Language Support (from LANGUAGE_STRATEGY.md)

### Phase 1: PHP Ecosystem (Current + Next)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Laravel/Lumen** | `composer.json` + `artisan` | 11 capabilities | ✅ Done |
| **Symfony** | `composer.json` + `Kernel.php` | routing, services, DI, forms | 📋 Planned (Issue #14) |
| **Slim/Laminas** | `composer.json` | routing, middleware | 📋 Planned |
| **Plain PHP** | `composer.json` only | routing (attributes), models | 📋 Planned |
| **WordPress** | `wp-config.php` | hooks, REST API | 📋 Low priority |

**Next:** Symfony support (2nd most popular PHP framework)

### Phase 2: Node.js / TypeScript

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **Express** | `package.json` + `express` dep | routing, middleware, error handling | 🥇 High |
| **Fastify** | `package.json` + `fastify` dep | routing, schemas, hooks | 🥇 High |
| **NestJS** | `package.json` + `@nestjs/core` | controllers, guards, pipes, DI | 🥇 High |
| **Hono** | `package.json` + `hono` dep | routing, middleware | 🥈 Medium |
| **Koa** | `package.json` + `koa` dep | middleware, routing | 🥈 Medium |
| **AdonisJS** | `package.json` + `@adonisjs/core` | controllers, validators, ORM | 🥈 Medium |
| **Plain TS/JS** | `tsconfig.json`/`package.json` | basic routing | 🥉 Low |

**Detection strategy:**
1. `package.json` dependencies
2. Import patterns (`import express from 'express'`)
3. Framework-specific files (`nest-cli.json`, `fastify.config.js`)

### Phase 3: Go

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **Gin** | `go.mod` + `github.com/gin-gonic/gin` | routing, middleware, binding | 🥇 High |
| **Echo** | `go.mod` + `github.com/labstack/echo` | routing, middleware, binding | 🥇 High |
| **Chi** | `go.mod` + `github.com/go-chi/chi` | routing, middleware | 🥈 Medium |
| **Fiber** | `go.mod` + `github.com/gofiber/fiber` | routing, middleware | 🥈 Medium |
| **Standard lib** | `go.mod` only | `http.Handler` | 🥉 Low |

**Detection strategy:**
1. `go.mod` + imports (`import "github.com/gin-gonic/gin"`)
2. Go AST parsing (`go/ast`, `go/parser`)

### Phase 4: Python

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **FastAPI** | `pyproject.toml` + `fastapi` dep | routing, models, dependencies | 🥇 High |
| **Django** | `pyproject.toml`/`requirements.txt` + `django` | models, views, ORM, admin | 🥇 High |
| **Flask** | `pyproject.toml` + `flask` dep | routing, blueprints | 🥈 Medium |
| **Starlette** | `pyproject.toml` + `starlette` dep | routing, middleware | 🥈 Medium |
| **FastAPI + SQLAlchemy** | `sqlalchemy` dep | models, migrations | 🥈 Medium |

**Detection:** `pyproject.toml`, `requirements.txt`, `setup.py`, `poetry.lock`, imports

### Phase 5: Java / JVM

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **Spring Boot** | `pom.xml`/`build.gradle` + `spring-boot-starter-web` | controllers, services, JPA, config | 🥇 High |
| **Micronaut** | `build.gradle` + `io.micronaut` | controllers, DI, AOP | 🥈 Medium |
| **Quarkus** | `pom.xml` + `quarkus` | REST, Panache, config | 🥈 Medium |
| **Ktor** | `build.gradle` + `io.ktor` | routing, plugins | 🥉 Low |

**Detection:** `pom.xml`, `build.gradle`, `build.gradle.kts`, imports

### Capability Matrix (Target)

| Capability | PHP | Node/TS | Go | Python | Java |
|---|---|---|---|---|---|
| **routing** | ✅ | 📋 | 📋 | 📋 | 📋 |
| **models/ORM** | ✅ (Eloquent) | 📋 (Prisma/TypeORM/Sequelize) | 📋 (GORM) | 📋 (SQLAlchemy/Django ORM) | 📋 (JPA/Hibernate) |
| **validation** | ✅ (FormRequest) | 📋 (Zod/class-validator) | 📋 (go-playground/validator) | 📋 (Pydantic) | 📋 (Bean Validation) |
| **routing signatures** | ✅ (Laravel+base) | 📋 (Express/Fastify/Nest) | 📋 (Gin/Echo) | 📋 (FastAPI/Django) | 📋 (Spring) |
| **contract headers** | ✅ | 📋 | 📋 | 📋 | 📋 |
| **layer boundaries** | ✅ | 📋 | 📋 | 📋 | 📋 |
| **route coverage** | ✅ | 📋 | 📋 | 📋 | 📋 |
| **cache TTL** | ✅ | 📋 | 📋 | 📋 | 📋 |

### Implementation Priority

| Quarter | Focus | Deliverable |
|---|---|---|
| **Q1** | Symfony PHP adapter | 5 capabilities |
| **Q1** | Express/Fastify/NestJS Node adapter | 8 capabilities |
| **Q2** | Gin/Echo Go adapter | 6 capabilities |
| **Q2** | FastAPI/Django Python adapter | 8 capabilities |
| **Q3** | Spring Boot Java adapter | 7 capabilities |
| **Q3** | Remaining PHP frameworks (Symfony, Slim) | 6 capabilities |
| **Q4** | Go frameworks (Echo, Chi, Fiber) | 6 capabilities |
| **Q4** | Python frameworks (Django, Flask) | 6 capabilities |

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
| **B1** Third adapter (tsx) | 📋 Deferred | No non-Flutter consumer; PHP adapter is the seam-proof |
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
| 9 | Laravel Adapter Quick Reference in CONCEPTS.md | 📋 Planned | |
| 10 | ROADMAP.md current status | ✅ Updated | This file |
| 14 | Symfony adapter (PHP) | 📋 Planned | Tracked in LANGUAGE_STRATEGY.md Phase 1 |
| 15 | Node.js/TypeScript adapter | ✅ Done | Released in v0.2.0 |
| 16 | Go adapter | 📋 Planned | Tracked in LANGUAGE_STRATEGY.md Phase 3 |
| 17 | Python adapter | 📋 Planned | Tracked in LANGUAGE_STRATEGY.md Phase 4 |
| 18 | Java/JVM adapter | 📋 Planned | Tracked in LANGUAGE_STRATEGY.md Phase 5 |
| 19 | ROADMAP.md multi-language update | ✅ Done | This update |
| 21 | `audit_form_request_validation` crash fix | ✅ Done | Fixed in commit 943a353 |

---

## Next Priority Work

| Priority | Work | Rationale |
|---|---|---|
| 1 | Lumen → Laravel migration guide (ADOPTING.md) | Real adoption blocker |
| 2 | Laravel Adapter Quick Reference in CONCEPTS.md | Documentation parity |
| 3 | Symfony PHP adapter (Phase 1) | 2nd most popular PHP framework; highest decision-matrix score |
| 4 | Node.js/TypeScript adapter (Phase 2) | Huge market; Express/Fastify/NestJS |
| 5 | Go adapter (Phase 3) | Growing fast; Gin/Echo |
| 6 | Python adapter (Phase 4) | FastAPI/Django high value |
| 7 | Java/JVM adapter (Phase 5) | Spring Boot enterprise demand |

---

## Test Baseline

```
62 test files | 525 cases | 60 passed | 2 failed (documented)
eval_suite_lint: 14/14 clean
eval_fixture_selftest: 6/6 fixtures
```

The two failing tests are documented fixture-pinned cases that require a tagged release to auto-heal.

---

## Deployment Notes

- **Repo**: https://github.com/irfan-dahir/backend-quality-suite (public)
- **Install**: `pip install git+https://github.com/irfan-dahir/backend-quality-suite.git`
- **CLI**: `backend-suite` command after install
- **Tag**: `backend-suite--v0.1.0`
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

_Last updated: 2026-10-12 (commit 6409d51)_