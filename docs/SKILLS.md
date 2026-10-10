# What you can run

**Generated — do not edit by hand.** Regenerate with `python3 plugins/design-suite/bin/skills_catalog.py`; CI fails if this file is stale, exactly as it does for `docs/CATALOG.md`.

The user-facing companion to [CATALOG.md](./CATALOG.md). That one is organised for a maintainer, by plugin; this one is organised around what you type and whether you can trust the answer. Every row below is read from the components' own frontmatter, from `repo_health.py`'s audit discovery, and from each plugin's `hooks/hooks.json` — nothing here is typed by hand, because hand-written claims about this repo's own contents have been wrong repeatedly.

**58 slash commands · 4 agents · 22 audits · 4 hooks.**

### What the maturity markers mean

| Marker | Means |
|---|---|
| ✅ proven | There is recorded evidence of a real end-to-end run |
| ⚠️ use with review | Nobody has confirmed it end to end. Not a claim it is broken — read what it produces before acting on it |
| ⚠️ experimental | Known rough edges. Read its own file first |
| pointer — runs nothing here | Not an implementation. It tells you where the real thing lives |
| 🔴 off | Switched off. It refuses (exit 2) rather than running, for a measured reason stated in its own file |

## Commands that can fire on their own

These **32** are marked `invocation: auto`: Claude may run them from plain language, without you naming them, because they are read-only or ask before writing. You can still type them.

| Slash command | What it does | Fires | Maturity | Plugin |
|---|---|---|---|---|
| `/audit-adapter-pattern` | Mechanically check that screens never import the layers they are supposed to reach only through an adapter — state-management, repositories, data sources, HTTP clients. | auto | ⚠️ use with review | `design-suite` |
| `/audit-api-consistency` | Use when asked whether a component API is coherent, or before a release that changes one. | auto | ✅ proven | `design-suite` |
| `/audit-assets` | Audit the asset library for drift: manifest entries with no rendered file, orphan files with no manifest entry, unregistered assets, stale palette, and missing… | auto | ⚠️ use with review | `design-suite` |
| `/audit-claude-md-drift` | Use when asked whether CLAUDE.md is still accurate, or before trusting a rule it states. | auto | ⚠️ use with review | `design-suite` |
| `/audit-contract-headers` | Use when asked whether screen contracts or adapter interfaces are still accurate, or after adding or removing an adapter field. | auto | ✅ proven | `design-suite` |
| `/audit-contrast` | Use when asked whether colour contrast is compliant, or before shipping a palette change. | auto | ⚠️ use with review | `design-suite` |
| `/audit-doc-staleness` | Use when asked how stale a doc is by its own stated date, or before relying on an old doc. | auto | ⚠️ use with review | `design-suite` |
| `/audit-error-handling` | Use when asked about error-handling coverage, or before wiring a new endpoint. | auto | ✅ proven | `design-suite` |
| `/audit-focus-order` | Best-effort, source-only check of focus/tab traversal order against visual layout order — Stack/Positioned mismatches and explicit traversal overrides (autofocus… | auto | ⚠️ use with review | `design-suite` |
| `/audit-layer-boundaries` | Mechanically check that no shared/design-system layer imports the feature code that consumes it — the layering inversion that blocks extracting that layer into a package. | auto | ⚠️ use with review | `design-suite` |
| `/audit-mock-api` | Report-only drift audit for registered mock-API contracts — never edits a contract artifact, but writes its findings to .design-suite/mock-api-findings.json (pass --out… | auto | ✅ proven | `design-suite` |
| `/audit-pattern-adoption` | Count which design-system patterns this project actually calls, and fail on ones it claims but never reaches for. Read-only: reports findings, never edits. | auto | ⚠️ use with review | `design-suite` |
| `/audit-promotion-candidates` | Use when asked what should be promoted into the design system, or what was reinvented under a different noun. | auto | ⚠️ use with review | `design-suite` |
| `/audit-proposal-status` | Use when asked whether a proposal's status is current, or before relying on a roadmap/proposal doc's header. | auto | ⚠️ use with review | `design-suite` |
| `/audit-prose-flags` | Use when maintaining this plugin's own skills, or after renaming or removing a script flag. | auto | ⚠️ use with review | `design-suite` |
| `/audit-reduced-motion` | Use when asked to check reduced-motion support or accessibility of animations. | auto | ⚠️ use with review | `design-suite` |
| `/audit-reinvented-components` | Use when asked what has been rebuilt instead of reused. | auto | ⚠️ use with review | `design-suite` |
| `/audit-semantics` | Four precisely-scoped Flutter semantics rules, each from a defect that shipped (issue #128) — error text never announced, selection shown by colour alone… | auto | ⚠️ use with review | `design-suite` |
| `/audit-tokens` | Mechanically audit source for hardcoded design values that should route through design tokens — colours, spacing, radii, durations, curves. | auto | ✅ proven | `design-suite` |
| `/audit-unused-tokens` | Use when asked which design tokens are unused, or before pruning a palette. | auto | ⚠️ use with review | `design-suite` |
| `/audit-unwired-roles` | Use when asked whether the theming contract is real, or which design-system colour roles a project never uses. | auto | ✅ proven | `design-suite` |
| `/design-debt` | Use when asked for an overall picture of design health or design debt across audits. | auto | ⚠️ use with review | `design-suite` |
| `/design-review-pr` | Review a branch's changes against a base ref: run every live audit, keep only findings on changed lines (then elsewhere in changed files), and list every audit that… | auto | ⚠️ use with review | `design-suite` |
| `/draft-pr-description` | Draft a PR title and description from the actual diff and commit history, following the project's own PR template. | auto | ✅ proven | `house-style` |
| `/generate-walkthrough` | Produce a narrated screenshot or video walkthrough of one named user flow, for stakeholder demos. | auto | ⚠️ experimental | `design-suite` |
| `/import-tokens-dtcg` | Report drift between a W3C DTCG (2025.10) token file — a Figma variables, Tokens Studio or Style Dictionary export — and the tokens this project's code declares: missing… | auto | ⚠️ use with review | `design-suite` |
| `/repo-health` | Use when starting a session on an unfamiliar project, or asked for overall audit/health status in one read. | auto | ⚠️ use with review | `design-suite` |
| `/review-docs` | Audit the project's documents against each other and against the codebase, reporting what is stale, out of sync, or missing. | auto | ⚠️ use with review | `design-suite` |
| `/scaffold-screen` | Generate a new screen pre-wired with the three standard states — loading, error, content — using the components the project has already standardized on. | auto | ⚠️ use with review | `design-suite` |
| `/suggest-component` | Use when asked which component to use, whether one already covers a need, or to compare candidates. | auto | ⚠️ use with review | `design-suite` |
| `/survey` | Survey an unknown project — detected stack, candidate source roots, ranked candidate token sources, a document inventory with proposed roles, and an explicit list of… | auto | ⚠️ use with review | `design-suite` |
| `/upgrade-measure` | Use before upgrading the suite in a project, or on a suite PR before merging. | auto | ⚠️ use with review | `design-suite` |

## Commands that wait for you to ask

These **26** are marked `invocation: explicit`: they generate content, set project-wide conventions, or touch brand, so they never start themselves. Type them.

| Slash command | What it does | Fires | Maturity | Plugin |
|---|---|---|---|---|
| `/add-asset` | Add a purchased 3D asset to the library: register it in the manifest with provenance and licence, recolour and render it, optimise, and bundle it. | explicit | ⚠️ use with review | `design-suite` |
| `/animate-asset` | Add baked motion to an existing asset: pick a preset, render the frame sequence, encode an animated file plus a static reduce-motion poster, and bundle both. | explicit | ⚠️ use with review | `design-suite` |
| `/audit-accessibility` | DISABLED pending correct scoping — measured 100% false positives on two real projects (issue #104), and zero true-positive capacity on one of them. | explicit | 🔴 off | `design-suite` |
| `/audit-copy` | DISABLED pending re-scoping — 73% of its commit-gating findings were wrong, measured on two real projects (issues #104, #109). | explicit | 🔴 off | `design-suite` |
| `/bootstrap-design-docs` | Bootstrap a project's documentation layer one document at a time, by reverse-engineering what is already built and proposing each document for the human to accept or… | explicit | ⚠️ use with review | `design-suite` |
| `/capture-backlog` | Draft backlog entries in the project backlog's own existing format, for review before anything is written. | explicit | ⚠️ use with review | `design-suite` |
| `/cleanup-worktrees` | Use after a session that fanned out worktree agents, or to find a worktree holding uncommitted work. | explicit | ⚠️ use with review | `design-suite` |
| `/establish-brand-voice` | Establish or update the project's brand voice and terminology glossary — the source of truth copy audits check against. Never rewrites existing copy. | explicit | ⚠️ use with review | `design-suite` |
| `/establish-interaction-spec` | Establish or update motion and haptic/sound conventions — the source of truth the token audit measures durations and curves against. | explicit | ⚠️ use with review | `design-suite` |
| `/export-tokens-dtcg` | Export this project's declared design tokens as a W3C Design Tokens Community Group (DTCG 2025.10) .tokens.json that Figma, Tokens Studio and Style Dictionary can read. | explicit | ⚠️ use with review | `design-suite` |
| `/generate-asset` | Generate a new asset from a script we author rather than a purchased source — SVG, Blender, or the shapes icon-as-data kind — then render, optimise and bundle it. | explicit | ⚠️ use with review | `design-suite` |
| `/generate-client-readiness` | Derive a client-facing production-readiness summary from the internal checklist and export it to PDF. | explicit | ✅ proven | `house-style` |
| `/golden-local-ab` | Prove a refactor changed no pixels by rendering the golden corpus on this machine before and after and comparing the two byte-for-byte. | explicit | ✅ proven | `design-suite` |
| `/log-decision` | Draft an entry for the project's decision log in that log's own existing format, for review before anything is written. | explicit | ⚠️ use with review | `design-suite` |
| `/map-project` | Propose the mappings a survey cannot: which document is really the design doc, which project kind this is, which candidate token source is the true one — each with the… | explicit | ⚠️ use with review | `design-suite` |
| `/onboard-new-client` | Playbook rather than a new capability: the ordered sequence of existing skills for standing up the design-system foundation of a new client project or a greenfield area. | explicit | ⚠️ use with review | `design-suite` |
| `/promote-component` | Move a component from an application into the shared design system, or demote one back. | explicit | ⚠️ use with review | `design-suite` |
| `/propose-config` | Propose real values for the TODO sections init.py scaffolds (layer rules, the adapter seam, the animated-widget list, colour token names), each measured from this… | explicit | ⚠️ use with review | `design-suite` |
| `/ratify` | Use when asked to ratify, approve, or sign off a profile field, or when doctor reports fields as UNTRUSTED. | explicit | ⚠️ use with review | `design-suite` |
| `/repair-tokens` | Use when asked to fix, repair, or auto-tokenise the findings /audit-tokens reported. | explicit | ⚠️ use with review | `design-suite` |
| `/rewrite-copy` | Draft or rewrite user-facing copy so it is on-brand and on-terminology, and does not read as machine-written. Never applies a change without showing it first. | explicit | ⚠️ use with review | `design-suite` |
| `/run-chain` | Run a multi-skill playbook one step at a time, keeping its position across sessions and stopping at every checkpoint. | explicit | ⚠️ experimental | `design-suite` |
| `/sync-docs` | Take new information — client feedback, a call summary, a product decision, a direction change — and update the correct project documents. | explicit | ⚠️ use with review | `design-suite` |
| `/sync-mock-api` | Regenerate the generated parts of a mock-API contract from its hand-edited fixture — API docs, mock entry, and derived artifacts. | explicit | ✅ proven | `design-suite` |
| `/upgrade-apply` | Use only when explicitly asked to apply or migrate a suite upgrade, after /upgrade-measure and human approval. | explicit | ⚠️ use with review | `design-suite` |
| `/wire-endpoint` | Wire a hardcoded or stub data source to a mocked GET endpoint in the shape the project already uses — model, datasource, bloc, fixture, contract registration, docs, test. | explicit | ⚠️ use with review | `design-suite` |

## Agents

All 4 are read-only, and that is checked rather than asserted: each one's `tools:` grant is `design-auditor` → Read, Grep, Glob; `design-critic` → Read, Grep, Glob; `mock-api-auditor` → Read, Grep, Glob; `session-decisions` → Read, Grep, Glob. None is granted `Write`, `Edit` or `Bash`, so none can change a file. They report; you decide.

| Agent | What it does | Fires | Maturity | Plugin |
|---|---|---|---|---|
| `design-auditor` | Use when asked to audit, review, or check a built screen, flow, or component for design-system compliance against the doc-of-record and tokens, or to find undocumented… | auto | ⚠️ use with review | `design-suite` |
| `design-critic` | Use when asked to critique or give feedback on a design, mockup, screenshot, or proposed screen before it is built (not existing code). | explicit | ⚠️ use with review | `design-suite` |
| `mock-api-auditor` | Use when asked to find hardcoded data sources that should be wired to a mock GET endpoint, fixtures with no contract, or mutations given a fake POST/PATCH. | auto | ✅ proven | `design-suite` |
| `session-decisions` | Read-only sweep of the current working session for decisions that belong in the project's decision log and follow-up work that belongs in its backlog. | auto | ⚠️ use with review | `design-suite` |

## Audits

**22 audits**, enumerated by `python3 plugins/design-suite/bin/repo_health.py --list` — the same discovery `/repo-health` and the MCP audit server use, so this table cannot disagree with what actually runs.

**22 of them have a matching `/audit-…` command; 0 do not.** The ones that do not are not hidden and not broken — they are simply reachable another way: `/repo-health` (which runs all of them), the MCP audit server in `plugins/design-suite/mcp/audit_server.py`, the edit-triggered hook, or running the script directly. The column below says which, per audit.

| Audit | Live? | Reachable how | Backing script |
|---|---|---|---|
| `audit_accessibility` | 🔴 off | `/audit-accessibility`, `/repo-health`, MCP, or the script directly | `bin/audit_accessibility.py` |
| `audit_adapter_pattern` | live | `/audit-adapter-pattern`, `/repo-health`, MCP, or the script directly | `bin/audit_adapter_pattern.py` |
| `audit_api_consistency` | live | `/audit-api-consistency`, `/repo-health`, MCP, or the script directly | `bin/audit_api_consistency.py` |
| `audit_claude_md_drift` | live | `/audit-claude-md-drift`, `/repo-health`, MCP, or the script directly | `bin/audit_claude_md_drift.py` |
| `audit_contract_headers` | live | `/audit-contract-headers`, `/repo-health`, MCP, or the script directly | `bin/audit_contract_headers.py` |
| `audit_contrast` | live | `/audit-contrast`, `/repo-health`, MCP, or the script directly | `bin/audit_contrast.py` |
| `audit_copy` | 🔴 off | `/audit-copy`, `/repo-health`, MCP, or the script directly | `bin/audit_copy.py` |
| `audit_doc_staleness` | live | `/audit-doc-staleness`, `/repo-health`, MCP, or the script directly | `bin/audit_doc_staleness.py` |
| `audit_error_handling` | live | `/audit-error-handling`, `/repo-health`, MCP, or the script directly | `bin/audit_error_handling.py` |
| `audit_focus_order` | live | `/audit-focus-order`, `/repo-health`, MCP, or the script directly | `bin/audit_focus_order.py` |
| `audit_layer_boundaries` | live | `/audit-layer-boundaries`, `/repo-health`, MCP, or the script directly | `bin/audit_layer_boundaries.py` |
| `audit_pattern_adoption` | live | `/audit-pattern-adoption`, `/repo-health`, MCP, or the script directly | `bin/audit_pattern_adoption.py` |
| `audit_promotion_candidates` | live | `/audit-promotion-candidates`, `/repo-health`, MCP, or the script directly | `bin/audit_promotion_candidates.py` |
| `audit_proposal_status` | live | `/audit-proposal-status`, `/repo-health`, MCP, or the script directly | `bin/audit_proposal_status.py` |
| `audit_prose_flags` | live | `/audit-prose-flags`, `/repo-health`, MCP, or the script directly | `bin/audit_prose_flags.py` |
| `audit_reduced_motion` | live | `/audit-reduced-motion`, `/repo-health`, MCP, or the script directly | `bin/audit_reduced_motion.py` |
| `audit_reinvented_components` | live | `/audit-reinvented-components`, `/repo-health`, MCP, or the script directly | `bin/audit_reinvented_components.py` |
| `audit_semantics` | live | `/audit-semantics`, `/repo-health`, MCP, or the script directly | `bin/audit_semantics.py` |
| `audit_tokens` | live | `/audit-tokens`, `/repo-health`, MCP, or the script directly | `bin/audit_tokens.py` |
| `audit_unused_tokens` | live | `/audit-unused-tokens`, `/repo-health`, MCP, or the script directly | `bin/audit_unused_tokens.py` |
| `audit_unwired_roles` | live | `/audit-unwired-roles`, `/repo-health`, MCP, or the script directly | `bin/audit_unwired_roles.py` |
| `audit_mock_api` | live | `/audit-mock-api`, `/repo-health`, MCP, or the script directly | `design_suite/engine/mockapi/audit_mock_api.py` |

### The 2 switched off, and why

A disabled audit stays discoverable on purpose. A check that quietly stopped running looks exactly like a check that ran and found nothing, so every surface has to name it.

| Audit | Measured reason |
|---|---|
| `audit_accessibility` | disabled — 100% false positives measured on two projects (issue #104) |
| `audit_copy` | disabled — 73% of commit-gating findings wrong, measured on two projects (issues #104, #109) |

## Hooks

**4 hooks**, read from each plugin's `hooks/hooks.json` — the file that actually registers them, on `PostToolUse`, `SessionStart`. Every one is advisory: a `PostToolUse` hook prints a reminder after a tool call, a `SessionStart` hook adds a note to Claude's context when a session opens, and none of them edits, writes, blocks, or fails anything.

| Hook | Plugin | Fires on | What you see |
|---|---|---|---|
| `session_start_onboarding.py` | `design-suite` | SessionStart on `startup\|clear` | Checking whether this project is set up for design-suite... |
| `mock_api_reminders.py` | `design-suite` | PostToolUse on `Write\|Edit` | Checking for mock-API contract changes... |
| `audit_on_edit.py` | `design-suite` | PostToolUse on `Write\|Edit\|Bash` | Running audits mapped to this change... |
| `pr_reminders.py` | `house-style` | PostToolUse on `Bash` | Checking for PR-related commands... |

## Cheat sheet

Every slash command, by the job you came here to do. Names only.

*How this grouping is derived:* **no frontmatter field encodes a job-to-be-done** — components declare `name`, `description`, `invocation` and `maturity`, and nothing more. Rather than invent a second editorial list to drift against the first, the buckets come from two things that already exist: the command's own name (`audit-…`, `…-asset`, `…mock-api…`, which other gates already depend on), and failing that, `GROUPS` in `catalog.py` — the grouping already maintained for `docs/CATALOG.md`. Anything neither rule places lands in **Other**, visibly, rather than being dropped.

**Audit** (21) — `/audit-accessibility` · `/audit-adapter-pattern` · `/audit-api-consistency` · `/audit-claude-md-drift` · `/audit-contract-headers` · `/audit-contrast` · `/audit-copy` · `/audit-doc-staleness` · `/audit-error-handling` · `/audit-focus-order` · `/audit-layer-boundaries` · `/audit-pattern-adoption` · `/audit-promotion-candidates` · `/audit-proposal-status` · `/audit-prose-flags` · `/audit-reduced-motion` · `/audit-reinvented-components` · `/audit-semantics` · `/audit-tokens` · `/audit-unused-tokens` · `/audit-unwired-roles`

**Document** (8) — `/bootstrap-design-docs` · `/capture-backlog` · `/establish-brand-voice` · `/establish-interaction-spec` · `/log-decision` · `/review-docs` · `/rewrite-copy` · `/sync-docs`

**Generate** (8) — `/design-debt` · `/generate-client-readiness` · `/generate-walkthrough` · `/promote-component` · `/repair-tokens` · `/scaffold-screen` · `/suggest-component` · `/wire-endpoint`

**Assets** (4) — `/add-asset` · `/animate-asset` · `/audit-assets` · `/generate-asset`

**Mock API** (2) — `/audit-mock-api` · `/sync-mock-api`

**Workflow** (5) — `/design-review-pr` · `/draft-pr-description` · `/onboard-new-client` · `/run-chain` · `/survey`

**Other** (10) — `/cleanup-worktrees` · `/export-tokens-dtcg` · `/golden-local-ab` · `/import-tokens-dtcg` · `/map-project` · `/propose-config` · `/ratify` · `/repo-health` · `/upgrade-apply` · `/upgrade-measure`

58 of 58 commands placed.

