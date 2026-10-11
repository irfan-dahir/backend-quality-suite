# What you can run

**Generated — do not edit by hand.** Regenerate with `python3 plugins/backend-suite/bin/skills_catalog.py`; CI fails if this file is stale, exactly as it does for `docs/CATALOG.md`.

The user-facing companion to [CATALOG.md](./CATALOG.md). That one is organised for a maintainer, by plugin; this one is organised around what you type and whether you can trust the answer. Every row below is read from the components' own frontmatter, from `repo_health.py`'s audit discovery, and from each plugin's `hooks/hooks.json` — nothing here is typed by hand, because hand-written claims about this repo's own contents have been wrong repeatedly.

**30 slash commands · 2 agents · 9 audits · 4 hooks.**

### What the maturity markers mean

| Marker | Means |
|---|---|
| ✅ proven | There is recorded evidence of a real end-to-end run |
| ⚠️ use with review | Nobody has confirmed it end to end. Not a claim it is broken — read what it produces before acting on it |
| ⚠️ experimental | Known rough edges. Read its own file first |
| pointer — runs nothing here | Not an implementation. It tells you where the real thing lives |
| 🔴 off | Switched off. It refuses (exit 2) rather than running, for a measured reason stated in its own file |

## Commands that can fire on their own

These **16** are marked `invocation: auto`: Claude may run them from plain language, without you naming them, because they are read-only or ask before writing. You can still type them.

| Slash command | What it does | Fires | Maturity | Plugin |
|---|---|---|---|---|
| `/audit-api-consistency` | Use when asked whether a component API is coherent, or before a release that changes one. | auto | ✅ proven | `backend-suite` |
| `/audit-claude-md-drift` | Use when asked whether CLAUDE.md is still accurate, or before trusting a rule it states. | auto | ⚠️ use with review | `backend-suite` |
| `/audit-contract-headers` | Use when asked whether screen contracts or adapter interfaces are still accurate, or after adding or removing an adapter field. | auto | ✅ proven | `backend-suite` |
| `/audit-doc-staleness` | Use when asked how stale a doc is by its own stated date, or before relying on an old doc. | auto | ⚠️ use with review | `backend-suite` |
| `/audit-error-handling` | Use when asked about error-handling coverage, or before wiring a new endpoint. | auto | ✅ proven | `backend-suite` |
| `/audit-layer-boundaries` | Mechanically check that no shared/design-system layer imports the feature code that consumes it — the layering inversion that blocks extracting that layer into a package. | auto | ⚠️ use with review | `backend-suite` |
| `/audit-mock-api` | Report-only drift audit for registered mock-API contracts — never edits a contract artifact, but writes its findings to .backend-suite/mock-api-findings.json (pass --out… | auto | ✅ proven | `backend-suite` |
| `/audit-proposal-status` | Use when asked whether a proposal's status is current, or before relying on a roadmap/proposal doc's header. | auto | ⚠️ use with review | `backend-suite` |
| `/audit-prose-flags` | Use when maintaining this plugin's own skills, or after renaming or removing a script flag. | auto | ⚠️ use with review | `backend-suite` |
| `/design-debt` | Use when asked for an overall picture of design health or design debt across audits. | auto | ⚠️ use with review | `backend-suite` |
| `/design-review-pr` | Review a branch's changes against a base ref: run every live audit, keep only findings on changed lines (then elsewhere in changed files), and list every audit that… | auto | ⚠️ use with review | `backend-suite` |
| `/draft-pr-description` | Draft a PR title and description from the actual diff and commit history, following the project's own PR template. | auto | ✅ proven | `house-style` |
| `/repo-health` | Use when starting a session on an unfamiliar project, or asked for overall audit/health status in one read. | auto | ⚠️ use with review | `backend-suite` |
| `/review-docs` | Audit the project's documents against each other and against the codebase, reporting what is stale, out of sync, or missing. | auto | ⚠️ use with review | `backend-suite` |
| `/survey` | Survey an unknown project — detected stack, candidate source roots, ranked candidate token sources, a document inventory with proposed roles, and an explicit list of… | auto | ⚠️ use with review | `backend-suite` |
| `/upgrade-measure` | Use before upgrading the suite in a project, or on a suite PR before merging. | auto | ⚠️ use with review | `backend-suite` |

## Commands that wait for you to ask

These **14** are marked `invocation: explicit`: they generate content, set project-wide conventions, or touch brand, so they never start themselves. Type them.

| Slash command | What it does | Fires | Maturity | Plugin |
|---|---|---|---|---|
| `/bootstrap-design-docs` | Bootstrap a project's documentation layer one document at a time, by reverse-engineering what is already built and proposing each document for the human to accept or… | explicit | ⚠️ use with review | `backend-suite` |
| `/capture-backlog` | Draft backlog entries in the project backlog's own existing format, for review before anything is written. | explicit | ⚠️ use with review | `backend-suite` |
| `/cleanup-worktrees` | Use after a session that fanned out worktree agents, or to find a worktree holding uncommitted work. | explicit | ⚠️ use with review | `backend-suite` |
| `/generate-client-readiness` | Derive a client-facing production-readiness summary from the internal checklist and export it to PDF. | explicit | ✅ proven | `house-style` |
| `/log-decision` | Draft an entry for the project's decision log in that log's own existing format, for review before anything is written. | explicit | ⚠️ use with review | `backend-suite` |
| `/map-project` | Propose the mappings a survey cannot: which document is really the design doc, which project kind this is, which candidate token source is the true one — each with the… | explicit | ⚠️ use with review | `backend-suite` |
| `/onboard-new-client` | Playbook rather than a new capability: the ordered sequence of existing skills for standing up the design-system foundation of a new client project or a greenfield area. | explicit | ⚠️ use with review | `backend-suite` |
| `/propose-config` | Propose real values for the TODO sections init.py scaffolds (layer rules, the adapter seam, the animated-widget list, colour token names), each measured from this… | explicit | ⚠️ use with review | `backend-suite` |
| `/ratify` | Use when asked to ratify, approve, or sign off a profile field, or when doctor reports fields as UNTRUSTED. | explicit | ⚠️ use with review | `backend-suite` |
| `/run-chain` | Run a multi-skill playbook one step at a time, keeping its position across sessions and stopping at every checkpoint. | explicit | ⚠️ experimental | `backend-suite` |
| `/sync-docs` | Take new information — client feedback, a call summary, a product decision, a direction change — and update the correct project documents. | explicit | ⚠️ use with review | `backend-suite` |
| `/sync-mock-api` | Regenerate the generated parts of a mock-API contract from its hand-edited fixture — API docs, mock entry, and derived artifacts. | explicit | ✅ proven | `backend-suite` |
| `/upgrade-apply` | Use only when explicitly asked to apply or migrate a suite upgrade, after /upgrade-measure and human approval. | explicit | ⚠️ use with review | `backend-suite` |
| `/wire-endpoint` | Wire a hardcoded or stub data source to a mocked GET endpoint in the shape the project already uses — model, datasource, bloc, fixture, contract registration, docs, test. | explicit | ⚠️ use with review | `backend-suite` |

## Agents

All 2 are read-only, and that is checked rather than asserted: each one's `tools:` grant is `mock-api-auditor` → Read, Grep, Glob; `session-decisions` → Read, Grep, Glob. None is granted `Write`, `Edit` or `Bash`, so none can change a file. They report; you decide.

| Agent | What it does | Fires | Maturity | Plugin |
|---|---|---|---|---|
| `mock-api-auditor` | Use when asked to find hardcoded data sources that should be wired to a mock GET endpoint, fixtures with no contract, or mutations given a fake POST/PATCH. | auto | ✅ proven | `backend-suite` |
| `session-decisions` | Read-only sweep of the current working session for decisions that belong in the project's decision log and follow-up work that belongs in its backlog. | auto | ⚠️ use with review | `backend-suite` |

## Audits

**9 audits**, enumerated by `python3 plugins/backend-suite/bin/repo_health.py --list` — the same discovery `/repo-health` and the MCP audit server use, so this table cannot disagree with what actually runs.

**9 of them have a matching `/audit-…` command; 0 do not.** The ones that do not are not hidden and not broken — they are simply reachable another way: `/repo-health` (which runs all of them), the MCP audit server in `plugins/backend-suite/mcp/audit_server.py`, the edit-triggered hook, or running the script directly. The column below says which, per audit.

| Audit | Live? | Reachable how | Backing script |
|---|---|---|---|
| `audit_mock_api` | live | `/audit-mock-api`, `/repo-health`, MCP, or the script directly | `backend_suite/engine/mockapi/audit_mock_api.py` |
| `audit_api_consistency` | live | `/audit-api-consistency`, `/repo-health`, MCP, or the script directly | `bin/audit_api_consistency.py` |
| `audit_claude_md_drift` | live | `/audit-claude-md-drift`, `/repo-health`, MCP, or the script directly | `bin/audit_claude_md_drift.py` |
| `audit_contract_headers` | live | `/audit-contract-headers`, `/repo-health`, MCP, or the script directly | `bin/audit_contract_headers.py` |
| `audit_doc_staleness` | live | `/audit-doc-staleness`, `/repo-health`, MCP, or the script directly | `bin/audit_doc_staleness.py` |
| `audit_error_handling` | live | `/audit-error-handling`, `/repo-health`, MCP, or the script directly | `bin/audit_error_handling.py` |
| `audit_layer_boundaries` | live | `/audit-layer-boundaries`, `/repo-health`, MCP, or the script directly | `bin/audit_layer_boundaries.py` |
| `audit_proposal_status` | live | `/audit-proposal-status`, `/repo-health`, MCP, or the script directly | `bin/audit_proposal_status.py` |
| `audit_prose_flags` | live | `/audit-prose-flags`, `/repo-health`, MCP, or the script directly | `bin/audit_prose_flags.py` |

### The 0 switched off, and why

A disabled audit stays discoverable on purpose. A check that quietly stopped running looks exactly like a check that ran and found nothing, so every surface has to name it.

| Audit | Measured reason |
|---|---|

## Hooks

**4 hooks**, read from each plugin's `hooks/hooks.json` — the file that actually registers them, on `PostToolUse`, `SessionStart`. Every one is advisory: a `PostToolUse` hook prints a reminder after a tool call, a `SessionStart` hook adds a note to Claude's context when a session opens, and none of them edits, writes, blocks, or fails anything.

| Hook | Plugin | Fires on | What you see |
|---|---|---|---|
| `session_start_onboarding.py` | `backend-suite` | SessionStart on `startup\|clear` | Checking whether this project is set up for backend-suite... |
| `mock_api_reminders.py` | `backend-suite` | PostToolUse on `Write\|Edit` | Checking for mock-API contract changes... |
| `audit_on_edit.py` | `backend-suite` | PostToolUse on `Write\|Edit\|Bash` | Running audits mapped to this change... |
| `pr_reminders.py` | `house-style` | PostToolUse on `Bash` | Checking for PR-related commands... |

## Cheat sheet

Every slash command, by the job you came here to do. Names only.

*How this grouping is derived:* **no frontmatter field encodes a job-to-be-done** — components declare `name`, `description`, `invocation` and `maturity`, and nothing more. Rather than invent a second editorial list to drift against the first, the buckets come from two things that already exist: the command's own name (`audit-…`, `…-asset`, `…mock-api…`, which other gates already depend on), and failing that, `GROUPS` in `catalog.py` — the grouping already maintained for `docs/CATALOG.md`. Anything neither rule places lands in **Other**, visibly, rather than being dropped.

**Audit** (8) — `/audit-api-consistency` · `/audit-claude-md-drift` · `/audit-contract-headers` · `/audit-doc-staleness` · `/audit-error-handling` · `/audit-layer-boundaries` · `/audit-proposal-status` · `/audit-prose-flags`

**Document** (5) — `/bootstrap-design-docs` · `/capture-backlog` · `/log-decision` · `/review-docs` · `/sync-docs`

**Generate** (3) — `/design-debt` · `/generate-client-readiness` · `/wire-endpoint`

**Mock API** (2) — `/audit-mock-api` · `/sync-mock-api`

**Workflow** (5) — `/design-review-pr` · `/draft-pr-description` · `/onboard-new-client` · `/run-chain` · `/survey`

**Other** (7) — `/cleanup-worktrees` · `/map-project` · `/propose-config` · `/ratify` · `/repo-health` · `/upgrade-apply` · `/upgrade-measure`

30 of 30 commands placed.

