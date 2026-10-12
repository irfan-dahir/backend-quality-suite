# Backend Quality Suite

> **A drop-in backend auditing suite** — checks your code against your documents and tells you where they've drifted apart.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-538%20cases%20%7C%2061%20passed-brightgreen)](#test-status)
[![Release](https://img.shields.io/badge/Release-v0.3.0-orange)](#release)

---

## TL;DR

```bash
# Install
pip install git+https://github.com/irfan-dahir/backend-quality-suite.git

# In your Laravel/Lumen project
backend-suite survey
backend-suite init --from-survey
# Edit .backend-suite/arch-rules.json (copy from template)
backend-suite audit route-model-binding --findings
backend-suite audit form-request-validation --findings
backend-suite quality-debt
```

**What it does:** Audits your backend code against your documentation (API specs, RFCs, decisions, changelogs) and reports drift. No auto-fixes — you decide.

---

## Quick Start

| Step | Command | Purpose |
|------|---------|---------|
| 1️⃣ Install | `pip install git+https://github.com/irfan-dahir/backend-quality-suite.git` | Install CLI |
| 2️⃣ Survey | `backend-suite survey` | Detects stack, source root, docs |
| 3️⃣ Init | `backend-suite init --from-survey` | Creates `.backend-suite/` config |
| 4️⃣ Configure | Edit `.backend-suite/arch-rules.json` | Use [Laravel template](templates/dot-backend-suite/arch-rules-laravel.json.template) |
| 5️⃣ Audit | `backend-suite audit route-model-binding --findings` | Run first Laravel audit |

---

## What It Does

| ✅ Does | ❌ Doesn't |
|--------|-----------|
| Reports drift between code & docs | Auto-fix code |
| Grades findings (🔴/🟡/🔵) | Guess your stack |
| Refuses when it can't check (exit 2) | Pretend to pass |
| Gates on evidence, not assertions | Assume clean = good |

**Exit codes:** `0` = clean, `1` = findings, `2` = refused (could not check)

---

## Plugins

| Plugin | Scope | Install |
|--------|-------|---------|
| **`backend-suite`** | Universal engine — audits, docs, mock-API | Any project |
| `house-style` | Org conventions, letterhead, PR reminders | Internal only |

```bash
claude plugin install backend-suite@backend-quality-suite
# Internal only:
claude plugin install house-style@backend-quality-suite
```

---

## What Ships Today

| Category | Audits | Status |
|----------|--------|--------|
| **Laravel/PHP** | `route-model-binding`, `form-request-validation`, `layer-boundaries`, `api-consistency`, `contract-headers`, `route-coverage`, `cache-ttl-coverage` | ✅ Shipped |
| **Core** | `error-handling`, `api-consistency`, `contract-headers`, `layer-boundaries` | ✅ Shipped |
| **Docs** | `doc-staleness`, `proposal-status`, `claude-md-drift`, `prose-flags` | ✅ Shipped |
| **Mock API** | `audit-mock-api`, `sync-mock-api` | ✅ Shipped |
| **Meta** | `quality-debt`, `repo-health`, `verify`, `survey`, `doctor` | ✅ Shipped |

**Language adapters:** `php` (Laravel/Lumen + plain PHP), `node` (Express, Fastify, NestJS, Hono, Koa, AdonisJS), and `rust` (Axum, Actix Web, Rocket, Poem, Warp) ship. Go and Python are planned — see [LANGUAGE_STRATEGY.md](LANGUAGE_STRATEGY.md).

---

## Architecture (3 Layers)

```
plugins/backend-suite/
├── commands/ agents/ hooks/ docs/   # Skills, agents, hooks, docs
├── bin/                              # CLI entry points (no language knowledge)
└── backend_suite/
    ├── engine/      # LAYER 1: stdlib-only, zero project literals
    ├── adapters/    # LAYER 2: stack seams (php.py, node.py, rust.py ship)
    └── project.py   # Resolves project under audit

<your-repo>/.backend-suite/           # LAYER 3: data only
├── profile.json          # adapter, source globs, exemptions
├── docs.manifest.json    # role → path map
└── baselines/            # recorded audit output (the oracle)
```

**Principle:** Each layer knows less about specifics than the layer above.

---

## Key Principles

| # | Principle | What it means |
|---|-----------|---------------|
| 1 | **Report, never auto-fix** | Audits produce findings; human decides |
| 2 | **One direction of truth** | Skills read context layer, write derived artifacts |
| 3 | **Zero dependencies** | Stdlib-only Python, no install step |
| 4 | **No project literals** | Engine has zero project-specific paths/names |
| 5 | **Silence ≠ clean** | Every check produces finding OR error — never silence |

---

## Documentation Map

| Doc | Purpose |
|-----|---------|
| [ONBOARDING.md](ONBOARDING.md) | Zero to first audit in ~20 min |
| [docs/CATALOG.md](docs/CATALOG.md) | All skills/agents/hooks with tier & maturity (generated) |
| [docs/CONCEPTS.md](docs/CONCEPTS.md) | Vocabulary: context layer, seams, capabilities, oracle |
| [docs/ADOPTING.md](docs/ADOPTING.md) | Adopting on a new stack + Laravel migration guide |
| [docs/USER-GUIDE.md](docs/USER-GUIDE.md) | Complete user guide + quick starts |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Workstreams, status, decisions |
| [docs/ADOPTING.md](docs/ADOPTING.md#migrating-from-lumen-to-laravel) | **Laravel migration guide** |

---

## Install

### Via pip (any environment)
```bash
pip install git+https://github.com/irfan-dahir/backend-quality-suite.git
backend-suite --help
```

### Via Claude Code
```bash
claude plugin marketplace add irfan-dahir/backend-quality-suite
claude plugin install backend-suite@backend-quality-suite
```

### Requirements
- **Python 3.9+** (uses `str.removeprefix`, `from __future__ import annotations`)
- **Zero runtime deps** — stdlib only

---

## Test Status

```
63 test files | 538 cases | 61 passed | 2 failed (documented)
eval_suite_lint: 14/14 clean
eval_fixture_selftest: 6/6 fixtures
```

**2 documented failures** — fixture-pinned tests requiring upstream git revisions not in this fork. Auto-heal on first `backend-suite--v*` tag.

---

## CI / Gates

```bash
# Run all gates locally
python3 plugins/backend-suite/bin/gates.py
```

16 gates in `.github/workflows/validate.yml` — manifests, commands, catalogue, skills, repairers, preflight, consumer-compat, tests, evals, Python compile, engine seam.

---

## Release

```bash
git tag backend-suite--v0.3.0
git push origin main --tags
```

Release notes auto-generated via `changelog_to_release_notes.py`.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Irfan Dahir.

---

## Quick Links

| Need to... | Go to |
|------------|-------|
| First audit in 20 min | [ONBOARDING.md](ONBOARDING.md) |
| All commands/agents | [CATALOG.md](docs/CATALOG.md) |
| Architecture & vocab | [CONCEPTS.md](docs/CONCEPTS.md) |
| Adopt on new stack | [ADOPTING.md](docs/ADOPTING.md) |
| Laravel migration | [ADOPTING.md#migrating-from-lumen-to-laravel](docs/ADOPTING.md#migrating-from-lumen-to-laravel) |
| Laravel quick start | [USER-GUIDE.md](docs/USER-GUIDE.md) |
| What's next | [ROADMAP.md](docs/ROADMAP.md) |

---

**Repo:** https://github.com/irfan-dahir/backend-quality-suite  
**Tag:** `backend-suite--v0.3.0`  
**Install:** `pip install git+https://github.com/irfan-dahir/backend-quality-suite.git`