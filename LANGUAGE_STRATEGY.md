# Language Support Strategy

> **Goal:** Support major backend languages/frameworks while maintaining zero-dep, stdlib-only architecture.

---

## Current State

| Language | Adapter | Capabilities | Status |
|---|---|---|---|
| **PHP** | `php.py` | 6 (routing, laravel_routing, eloquent_models, form_requests, api_resources, policies) | ✅ Shipped |
| **Laravel/Lumen** | Built on PHP | 5 extra capabilities | ✅ Shipped |
| **Others** | — | — | 📋 Planned |

---

## Language Support Strategy

### Design Principles

| Principle | Implementation |
|---|---|
| **Zero deps** | Adapters use only stdlib + regex/ast parsing |
| **Capability-driven** | Each adapter declares capabilities it implements |
| **Framework-aware** | Adapter detects framework (Laravel, Symfony, Express, FastAPI, etc.) |
| **Graceful degradation** | Missing capability = refusal (exit 2), not fake pass |
| **Seam-based** | Engine never imports adapters; capabilities requested via protocol |

---

## Phase 1: PHP Ecosystem (Current + Next)

| Framework | Detection | Capabilities | Status |
|---|---|---|---|
| **Laravel/Lumen** | `composer.json` + `artisan` | 11 capabilities | ✅ Done |
| **Symfony** | `composer.json` + `Kernel.php` | routing, services, DI, forms | 📋 Planned |
| **Slim/Laminas** | `composer.json` | routing, middleware | 📋 Planned |
| **Plain PHP** | `composer.json` only | routing (attributes), models | 📋 Planned |
| **WordPress** | `wp-config.php` | hooks, REST API | 📋 Low priority |

**Next:** Symfony support (2nd most popular PHP framework)

---

## Phase 2: Node.js / TypeScript

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
5. Framework-specific files (`nest-cli.json`, `fastify.config.js`)

---

## Phase 3: Go

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

---

## Phase 4: Python

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **FastAPI** | `pyproject.toml` + `fastapi` dep | routing, models, dependencies | 🥇 High |
| **Django** | `pyproject.toml`/`requirements.txt` + `django` | models, views, ORM, admin | 🥇 High |
| **Flask** | `pyproject.toml` + `flask` dep | routing, blueprints | 🥈 Medium |
| **Starlette** | `pyproject.toml` + `starlette` dep | routing, middleware | 🥈 Medium |
| **FastAPI + SQLAlchemy** | `sqlalchemy` dep | models, migrations | 🥈 Medium |

**Detection:** `pyproject.toml`, `requirements.txt`, `setup.py`, `poetry.lock`, imports

---

## Phase 5: Java / JVM

| Framework | Detection | Capabilities | Priority |
|---|---|---|---|
| **Spring Boot** | `pom.xml`/`build.gradle` + `spring-boot-starter-web` | controllers, services, JPA, config | 🥇 High |
| **Micronaut** | `build.gradle` + `io.micronaut` | controllers, DI, AOP | 🥈 Medium |
| **Quarkus** | `pom.xml` + `quarkus` | REST, Panache, config | 🥈 Medium |
| **Ktor** | `build.gradle` + `io.ktor` | routing, plugins | 🥉 Low |

**Detection:** `pom.xml`, `build.gradle`, `build.gradle.kts`, imports

---

## Capability Matrix (Target)

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

---

## Implementation Priority

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

---

## Adapter Template (New Language)

```python
# backend_suite/adapters/{lang}.py
from backend_suite.adapters.base import (
    AdapterContext, Capability, CapabilityError, CapabilityEvidence,
    Check, CheckSet, ErrorHandlingSyntax, LanguageAdapterProtocol
)

NAME = "{lang}"

FILE_GLOBS = ("**/*.{ext}",)

# 1. Capabilities this adapter implements
def capabilities(ctx: AdapterContext) -> list[Capability]:
    return [
        Capability(name="routing", profile_field="source.routesFile", why="..."),
        Capability(name="models", profile_field="source.root", why="..."),
        # ...
    ]

# 2. Capability detection
def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    # Return CapabilityEvidence(present=True, files=[...], why="...")
    # or raise CapabilityError

# 3. Checks (sweep-based)
def checks(ctx: AdapterContext) -> CheckSet:
    return {
        "check_name": Check(
            pattern=re.compile(...),
            category="category",
            severity="critical|should_fix|fyi"
        ),
    }

# 4. Structural extraction (for contract headers, etc.)
def class_fields(source: str, class_name: str) -> dict[str, int] | None:
    # Return {field_name: line_number}

def member_reads(source: str, receiver: str) -> set[str]:
    # Return set of member names read off receiver

# 5. Optional: error handling syntax
ERROR_HANDLING = ErrorHandlingSyntax(
    catch_var=re.compile(...),
    type_guard=lambda var, typ: re.compile(...),
    stringify=lambda var: re.compile(...),
    type_test=lambda cls: re.compile(...),
    string_quotes=("'", '"'),
    line_comment="//",
)
```

---

## Integration Checklist (Per Adapter)

- [ ] Implement `capabilities()` returning list of `Capability`
- [ ] Implement `detect_capability()` with evidence
- [ ] Implement `checks()` returning `CheckSet`
- [ ] Implement structural extraction (`class_fields`, `member_reads`, etc.)
- [ ] Add `ERROR_HANDLING` if language has try/catch
- [ ] Add to `backend_suite/adapters/__init__.py` loader
- [ ] Add `FILE_GLOBS` for the language
- [ ] Add capability tests in `tests/adapters/test_{lang}.py`
- [ ] Add `verify_seam.py` test case for the adapter
- [ ] Document capabilities in `docs/CONCEPTS.md` quick reference
- [ ] Add template `arch-rules-{framework}.json.template` if framework-specific

---

## Detection Strategy (Shared)

```python
def detect_framework(repo: Path) -> str | None:
    """
    Returns framework name or None.
    Checks in order of specificity:
    1. Framework-specific files (artisan, manage.py, pom.xml)
    2. Package manager files (composer.json, package.json, go.mod, pyproject.toml)
    3. Import patterns in source files
    """
    # Check for framework-specific marker files
    if (repo / "artisan").exists(): return "laravel"
    if (repo / "manage.py").exists(): return "django"
    if (repo / "pom.xml").exists(): 
        if "spring-boot" in (repo / "pom.xml").read_text(): return "spring-boot"
    # ... etc
```

---

## Testing Strategy

| Test Type | What it verifies |
|---|---|
| **Unit** | Each capability detection returns correct evidence |
| **Integration** | Adapter loads, capabilities() returns expected list |
| **Fixture** | Real project fixture → expected findings |
| **Negative** | Non-framework project → capabilities refused appropriately |
| **verify_seam** | Adapter passes `verify_seam.py` smoke test |

---

## Milestone Definition of Done

| Milestone | Criteria |
|---|---|
| **Alpha** | Adapter loads, capabilities() returns list, detect_capability works on fixture |
| **Beta** | All target capabilities implemented, fixture tests pass |
| **RC** | verify_seam.py passes, real project tested (jikan-rest equivalent) |
| **GA** | Documented in CONCEPTS.md, arch-rules template exists, verified on 2+ real projects |

---

## Decision Matrix: Next Adapter

| Factor | Weight | Symfony | Express | Gin | FastAPI | Spring Boot |
|---|---|---|---|---|---|---|
| **Market share** | 30% | 25% | 20% | 25% | 20% |
| **Team expertise** | 25% | High | High | Medium | High | Low |
| **Audit value** | 25% | High | High | High | High | High |
| **Complexity** | 20% | Medium | Low | Low | Medium | High |
| **Weighted score** | 100% | **8.25** | **7.75** | **7.25** | **7.75** | **5.75** |

**Recommendation:** **Symfony** first (highest score, PHP expertise), then **Express/Fastify** (Node.js huge market), then **Gin** (Go growing fast).