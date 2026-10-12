# Language Support Strategy

> **Goal:** Support major backend languages/frameworks while maintaining zero-dep, stdlib-only architecture.

---

## Current State

| Language | Adapter | Capabilities | Status |
|---|---|---|---|
| **PHP** | `php.py` | `routing`, `laravel_routing`, `eloquent_models`, `form_requests`, `api_resources`, `policies`, `symfony_routing`, `symfony_di`, `symfony_forms`, `symfony_doctrine`, `symfony_security`, `symfony_twig` | ✅ Shipped |
| **Node.js/TypeScript** | `node.py` | `routing`, `models`, `validation`, `middleware`, `dependency_injection`, `api_resources`, `policies` + framework-gated `express/fastify/nestjs/hono/koa/adonis_routing` | ✅ Shipped |
| **Rust** | `rust.py` | `routing`, `models`, `validation`, `middleware`, `api_resources`, `policies` + framework-gated `axum/actix/rocket/poem/warp_routing` | ✅ Shipped |
| **Go** | `go.py` | `routing`, `models`, `validation`, `middleware`, `api_resources`, `policies` + framework-gated `gin/echo/chi/fiber_routing` | ✅ Shipped |
| **Python** | — | — | 📋 Planned |

Where a capability column says "framework-gated", the capability is offered only to projects
that read as that framework — a plain Rust crate is neither measured nor excused for Axum
routing it never claimed.

---

## Design Principles (unchanged)

| Principle | Implementation |
|---|---|
| **Zero deps** | Adapters use only stdlib + regex parsing |
| **Capability-driven** | Each adapter declares the capabilities it implements |
| **Framework-aware** | Adapter detects framework (Laravel, Symfony, Express, Axum, etc.) |
| **Graceful degradation** | Missing capability = refusal (exit 2), not fake pass |
| **Seam-based** | Engine never imports adapters; capabilities requested via protocol |

---

## Phase 1: PHP Ecosystem (Shipped)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Laravel/Lumen** | `composer.json` + `artisan` | `routing`, `laravel_routing`, `eloquent_models`, `form_requests`, `api_resources`, `policies` | ✅ Shipped |
| **Symfony** | `composer.json` + `Kernel.php` + `config/routes.*` | `symfony_routing`, `symfony_di`, `symfony_forms`, `symfony_doctrine`, `symfony_security`, `symfony_twig` | ✅ Shipped (0.3.0) |
| **Plain PHP** | `composer.json` only | routing (attributes), models | ✅ Shipped |
| **Slim/Laminas** | `composer.json` | routing, middleware | 📋 Planned |
| **WordPress** | `wp-config.php` | hooks, REST API | 📋 Low priority |

_Symfony gating is conservative: a `symfony/*` component dependency alone does **not** make a
tree a Symfony application — only `symfony/framework-bundle` plus `Kernel.php` and
`config/routes.*`/`config/services.*` do._

---

## Phase 2: Node.js / TypeScript (Shipped)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Express** | `package.json` + `express` dep | routing, middleware, error handling | ✅ Shipped |
| **Fastify** | `package.json` + `fastify` dep | routing, schemas, hooks | ✅ Shipped |
| **NestJS** | `package.json` + `@nestjs/core` | controllers, guards, pipes, DI | ✅ Shipped |
| **Hono** | `package.json` + `hono` dep | routing, middleware | ✅ Shipped |
| **Koa** | `package.json` + `koa` dep | middleware, routing | ✅ Shipped |
| **AdonisJS** | `package.json` + `@adonisjs/core` | controllers, validators, ORM | ✅ Shipped |
| **Plain TS/JS** | `tsconfig.json`/`package.json` | basic routing | ✅ Shipped |

**Detection strategy:**
1. `package.json` dependencies
2. Import patterns (`import express from 'express'`, `require('express')`)
3. Framework-specific files (`nest-cli.json`, `fastify.config.js`)

---

## Phase 3: Go (Shipped)

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

---

## Phase 4: Python (Planned)

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **FastAPI** | `pyproject.toml` + `fastapi` dep | routing, models, dependencies | 🥇 High |
| **Django** | `pyproject.toml`/`requirements.txt` + `django` | models, views, ORM, admin | 🥇 High |
| **Flask** | `pyproject.toml` + `flask` dep | routing, blueprints | 🥈 Medium |
| **Starlette** | `pyproject.toml` + `starlette` dep | routing, middleware | 🥈 Medium |

**Detection:** `pyproject.toml`, `requirements.txt`, `setup.py`, `poetry.lock`, imports

---

## Phase 5: Rust (Shipped)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Axum** | `Cargo.toml` + `axum` dep | routing (`Router::new().route`), models | ✅ Shipped |
| **Actix Web** | `Cargo.toml` + `actix-web` dep | routing (`#[get(…)]`, `web::resource`), middleware | ✅ Shipped |
| **Rocket** | `Cargo.toml` + `rocket` dep | routing (`#[get(…)]` + `routes![…]`) | ✅ Shipped |
| **Poem** | `Cargo.toml` + `poem` dep | routing (`Route::new()`) | ✅ Shipped |
| **Warp** | `Cargo.toml` + `warp` dep | routing (`warp::path(…)`) | ✅ Shipped |

**Detection:** `Cargo.toml` dependencies + `use` paths.

Two honest refusals, not omissions:

- `IMPORT_TARGETS = "module"` — a Rust `use` names a *module path*, not a file path, so
  `audit_layer_boundaries` **refuses (exit 2)** rather than resolving every import as
  external and printing a confident zero.
- `dependency_injection` is deliberately absent — Rust has no DI-container idiom, and
  declaring the capability would invent a boolean. Shared state (`State<AppState>`,
  `web::Data<T>`) is followed structurally via `typed_member_reads` instead.

> **Java/JVM was dropped, not deferred** (issue #18, closed as not-planned). The zero-dep
> seam is at its most fragile on Java (annotation processors on top of a split
> `pom.xml`/`build.gradle`/`build.gradle.kts` surface), and the decision-matrix scoring
> ranked Spring Boot lowest of every candidate. Rust — whose routing is explicit and whose
> manifest is a single `Cargo.toml` — replaced it as the fourth language.

---

## Capability Matrix (Shipped vs Planned)

| Capability | PHP | Node/TS | Rust | Go | Python |
|---|---|---|---|---|---|
| **routing** | ✅ | ✅ | ✅ | ✅ | 📋 |
| **models/ORM** | ✅ (Eloquent) | ✅ (Prisma/TypeORM/Sequelize/Mongoose/MikroORM) | ✅ (sea-orm/sqlx derives) | ✅ (structural follows) | 📋 (SQLAlchemy/Django ORM) |
| **validation** | ✅ (FormRequest) | ✅ (Zod/class-validator/Joi/Yup) | ✅ (validator derives) | ✅ (go-playground/validator) | 📋 (Pydantic) |
| **framework routing** | ✅ (laravel/symfony_routing) | ✅ (express/fastify/nestjs/hono/koa/adonis_routing) | ✅ (axum/actix/rocket/poem/warp_routing) | ✅ (gin/echo/chi/fiber_routing) | 📋 (FastAPI/Django) |
| **contract headers** | ✅ | ✅ | ✅ | ✅ | 📋 |
| **layer boundaries** | ✅ | ✅ | ✅ (refuses: module imports) | ✅ (refuses: module imports) | 📋 |
| **route coverage** | ✅ | ✅ | ✅ | ✅ | 📋 |
| **cache TTL** | ✅ (Laravel) | 📋 | 📋 | 📋 | 📋 |

---

## Implementation Status

| Phase | Adapter | Status |
|---|---|---|
| 1 | PHP (Laravel, Symfony) | ✅ Shipped |
| 2 | Node.js/TypeScript | ✅ Shipped (v0.2.0) |
| 5 | Rust (Axum, Actix Web, Rocket, Poem, Warp) | ✅ Shipped |
| 3 | Go (Gin, Echo, Chi, Fiber) | ✅ Shipped |
| 4 | Python (FastAPI, Django, Flask, Starlette) | 📋 Next |

---

## Adapter Template (New Language)

A real adapter is written against the seam contracts in `backend_suite/adapters/base.py`.
Structural discovery registers it by itself — there is no registry line to edit:

```python
# backend_suite/adapters/{lang}.py  — module-level NAME/FILE_GLOBS/checks() make it discoverable
import re

from .base import (
    AdapterContext,
    Capability,
    CapabilityError,
    CapabilityEvidence,
    Check,
    CheckSet,
    ErrorHandlingSyntax,
    ApiConsistencySyntax,
)

NAME = "{lang}"

FILE_GLOBS = ("src/**/*.{ext}",)        # plus GENERATED_SUFFIXES if the language ships generated files

# 1. Sweep checks — built under checks(), never at import time.
def checks(ctx: AdapterContext) -> CheckSet:
    # Return CheckSet(checks=[...], omitted=[...]). A check you could not build
    # goes in `omitted`, never silently dropped: a missing threshold cannot quietly
    # reduce coverage.
    return CheckSet(
        checks=[
            Check(kind="debug_statement", pattern=re.compile(r"…"),
                  category="should_fix"),
        ],
    )

# 2. Capability negotiation — which profile fields back which questions.
def capabilities(ctx: AdapterContext) -> list:
    # list[Capability]. Framework-specific capabilities are filtered by _looks_*()
    # detectors. ctx may be None when a caller is probing capability names only.
    ...

def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    # Return CapabilityEvidence(present=..., files=[...], why=...), or
    # raise CapabilityError(name, adapter, why) when the question is unanswerable.
    # Never invent a boolean: "no" and "cannot tell" must stay distinguishable.
    ...

# 3. Structural extraction — feeds contract-headers and api-consistency audits.
def block_comments(source: str) -> list: ...
def blank_comments(source: str) -> str: ...
def class_fields(source: str, class_name: str) -> dict | None: ...
def class_members(source: str, class_name: str) -> dict: ...
def member_reads(source: str, receiver: str) -> set: ...
def receiver_aliases(source: str, receiver: str) -> set: ...
def typed_member_reads(source: str, types: set) -> dict: ...

# 4. Error-handling model — "which failures look handled".
ERROR_HANDLING = ErrorHandlingSyntax(
    catch_var=re.compile(r"…"),
    type_guard=lambda var, typ: re.compile(r"…"),
    stringify=lambda var: re.compile(r"…"),
    type_test=lambda cls: re.compile(r"…"),
    string_quotes=("'", '"'),
    line_comment="//",
    # plus block_comment_start/end when the language has block comments
)

# 5. Response-shape consistency (api-consistency audit).
API_CONSISTENCY = ApiConsistencySyntax(
    action_pattern=re.compile(r"…"),
    route_literal=re.compile(r"…"),
    user_facing=lambda var: re.compile(r"…"),
    compared=lambda var: re.compile(r"…"),
    tappable=re.compile(r"…"),
)

# 6. Layer-boundary import semantics.
IMPORT_RE = re.compile(r"…")
IMPORT_TARGETS = "file"   # "file" when imports name file paths; "module" when they name modules
```

The protocol an adapter must satisfy is `LanguageCapabilityProtocol` in `base.py`.

---

## Integration Checklist (Per Adapter)

- [ ] Module-level `NAME`, `FILE_GLOBS`, and `def checks(` — structural discovery registers
      the adapter by itself; there is no `__init__.py` loader edit
- [ ] Implement `capabilities()` / `detect_capability()` with evidence and `CapabilityError`
      for unanswerable questions
- [ ] Implement `blank_comments()` / `block_comments()` for the language's comment grammar
      (nested block comments, raw strings, and lifetimes are what bite)
- [ ] Implement the contract-extraction surface (`class_fields`, `member_reads`, …)
- [ ] Declare `ERROR_HANDLING` and `API_CONSISTENCY` for the audits that consume them
- [ ] Set `IMPORT_TARGETS` honestly (`"module"` for `use`-style imports — refuse, don't guess)
- [ ] Add `bin/{lang}_adapter_test.py` — `run_tests.py` discovers it; test through the real
      registry (`for_project`/`scan_tree`), not around it
- [ ] Add a `verify_seam.py` leg — a **shipped** adapter's leg fails rather than skips
- [ ] Map the language's root manifest to the adapter in `survey.py` MANIFESTS; extend the
      `survey_test.py` reachability control
- [ ] Run `attest.py` until only the 2 documented known-red test files fail
- [ ] Document capabilities in `docs/CONCEPTS.md` and `LANGUAGE_STRATEGY.md`; add the
      consumer-facing change to `CHANGELOG.md`
- [ ] Add an `arch-rules-{framework}.json.template` when the language has framework-specific
      audit rules

---

## Detection Strategy (Shared)

Adapters detect frameworks in order of specificity:

1. Manifest markers (`artisan`, `nest-cli.json`, `[dependencies] axum = …`)
2. Framework-specific files (`config/routes.*`, `Kernel.php`, `nest-cli.json`)
3. Import/use patterns in source files

Each detector is **conservative**: a *library* that merely depends on a framework's
components is not classified as an *application* of it, or it would be offered
(loud) capabilities it never uses and every `survey --check` would report
`declared-capability-unused`.

---

## Testing Strategy

| Test Type | Where | What it verifies |
|---|---|---|
| **Unit** | `bin/{lang}_adapter_test.py` | Each capability returns correct evidence; refusals throw `CapabilityError` |
| **Integration** | `bin/{lang}_adapter_test.py` | Adapter loads through `for_project`; `capabilities()` returns the expected list |
| **Negative** | `bin/{lang}_adapter_test.py` | Non-framework project → framework capabilities not offered; empty tree → refusal, not clean |
| **Sweep** | `bin/{lang}_adapter_test.py` | `checks()` positives and negatives through `scan_tree` |
| **Seam** | `verify_seam.py` | Adapter passes the shipped-adapter sweeps (stublang + php + node + rust) |
| **Survey** | `survey_test.py` | The root manifest proposes the adapter (`adapter_reachability()`) |

---

## Milestone Definition of Done

| Milestone | Criteria |
|---|---|
| **Alpha** | Adapter loads, `capabilities()` returns a list, `detect_capability` works on a fixture |
| **Beta** | All target capabilities implemented, adapter test file passes |
| **RC** | `verify_seam.py` leg passes; real project measured through the suite |
| **GA** | Documented in CONCEPTS.md, changelog entry written, `survey.py` proposes it |

---

## Why each language shipped, in order

The decision matrix below is now **historical** — every row marked shipped has shipped. It was
used to pick the sequence; the one contestant that never shipped (Spring Boot/Java) is exactly
the row that scored lowest, and Java was later dropped outright (issue #18, not-planned) in
favour of Rust, which is a better fit for a stdlib-only regex seam.

| Factor | Weight | Symfony | Express | Gin | FastAPI | axum (Rust) |
|---|---|---|---|---|---|---|
| **Market share** | 30% | 25% | 20% | 25% | 20% | 15% |
| **Team expertise** | 25% | High | High | Medium | High | Medium |
| **Audit value** | 25% | High | High | High | High | High |
| **Complexity** | 20% | Medium | Low | Low | Medium | Medium |
| **Weighted score** | 100% | **8.25** | **7.75** | **7.25** | **7.75** | **7.00** |

**Shipped in order:** Symfony → Express (as the Node adapter's framework) → axum (as the Rust
adapter's framework) → Gin (as the Go adapter's framework). **Next:** FastAPI/Django (Python).