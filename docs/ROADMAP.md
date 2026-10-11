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
| **New: Laravel audits** | ✅ Done | `audit_route_model_binding`, `audit_form_request_validation` |
| **New: Harness integration** | ✅ Done | AGENTS.md, MCP configs for 11 harnesses, pre-commit hook |

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
| 10 | ROADMAP.md current status | 🔄 This file | |

---

## Next Priority Work

| Priority | Work | Rationale |
|---|---|---|
| 1 | Lumen → Laravel migration guide (ADOPTING.md) | Real adoption blocker |
| 2 | Laravel Adapter Quick Reference in CONCEPTS.md | Documentation parity |
| 9 | Update ROADMAP.md (this file) | Keep it current |
| 7 | Lumen → Laravel migration guide | Adoption blocker |
| 9 | Laravel Adapter Quick Reference | Documentation parity |

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

_Last updated: 2026-10-11 (commit fb07b1f)_