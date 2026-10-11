# Catalogue

**Generated — do not edit by hand.** Regenerate with `python3 plugins/backend-suite/bin/catalog.py`; CI fails if this file is stale.

A catalogue is a list of file-existence facts, and hand-written prose about those has already gone wrong three times in this project's history. So it is generated from the plugins' own frontmatter instead.

**38 skills · 2 agents · 4 hooks** across 2 plugins.

**19 documentation templates** across **19 roles** — 18 in `backend-suite`, 1 in `house-style`. 0 role(s) have no template and cannot be scaffolded: . Vocabulary by group: any 4, core 6, library 3, service 6. Roles applicable per archetype: library 18, service 19.

## How to read this

**Invocation** — `auto` means Claude may run it from plain language, without you naming it, because it is read-only or asks before writing. `explicit` means it waits for a real decision from you: brand voice, project-wide conventions, and generated content that someone has to approve.

**Maturity** is deliberately visible rather than buried:

| | Means |
|---|---|
| ✅ proven | Recorded evidence of a real end-to-end run |
| ⚪ unverified | **No such evidence found — not a claim it is broken.** It may work fine; nobody has confirmed it |
| ⚠️ experimental | Known rough edges. Read its own file before relying on it |
| ↗️ pointer | Not an implementation. Tells you where the real thing lives |
| ⛔ disabled | **Switched off. It refuses (exit 2) rather than running.** Not a confidence level — a decision, taken against measured evidence. Its own file states the reason and the bar for re-enabling it |

## `backend-suite`

### Audits — read-only, report-never-fix

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/audit-api-consistency` | auto | ✅ proven | Use when asked whether a component API is coherent, or before a release that changes one. Flags string sentinels, tap handlers without semantics, and two names for one idea. Read-only: reports findings, never edits. |
| `/audit-error-handling` | auto | ✅ proven | Use when asked about error-handling coverage, or before wiring a new endpoint. Checks every failure reaches the user: no call bypassing the shared guard, no raw exception text on screen, no unmatched failure state, no per-screen error widget. Read-only: reports findings, never edits. |
| `/audit-contract-headers` | auto | ✅ proven | Use when asked whether screen contracts or adapter interfaces are still accurate, or after adding or removing an adapter field. Checks each screen's contract header against its adapter: omitted fields, dangling entries, unread fields. Read-only: reports findings, never edits. |
| `/audit-mock-api` | auto | ✅ proven | Report-only drift audit for registered mock-API contracts — never edits a contract artifact, but writes its findings to .backend-suite/mock-api-findings.json (pass --out to redirect), and finds disagreement between the model, the fixture, the API docs and the mock server. Use when asked whether the mock API is in sync. |
| `/audit-doc-staleness` | auto | ⚪ unverified | Use when asked how stale a doc is by its own stated date, or before relying on an old doc. Flags docs whose last-updated footer/Date: field is past a threshold. Days since last edit, not proof the doc is still true. Read-only: reports findings, never edits. |
| `/audit-proposal-status` | auto | ⚪ unverified | Use when asked whether a proposal's status is current, or before relying on a roadmap/proposal doc's header. Checks the header's open-question count and framing against its own Decisions section markers; a cheaper, one-document /review-docs. Read-only: reports findings, never edits. |
| `/audit-layer-boundaries` | auto | ⚪ unverified | Mechanically check that no shared layer imports the feature code that consumes it — the layering inversion that blocks extracting that layer into a package. Rules and directories come from this project's arch-rules.json. Ratcheted against a committed baseline: new violations fail, known ones are listed. Never changes your code; saves its report to .backend-suite/layer-boundaries-findings.json on every run. Use when asked whether the layering still holds, or before an extraction. |
| `/audit-prose-flags` | auto | ⚪ unverified | Use when maintaining this plugin's own skills, or after renaming or removing a script flag. Checks every flag a skill's markdown names beside a bin/*.py script exists in that script. Suite-maintenance, not consumer-project. Read-only: reports findings, never edits. |
| `/audit-claude-md-drift` | auto | ⚪ unverified | Use when asked whether CLAUDE.md is still accurate, or before trusting a rule it states. Checks its prose against what enforces it: stale gate counts, rules whose script left CI, rules with no enforcement. Never edits, but runs the shell commands .backend-suite/claude_md_enforcement.json declares, so review that config like a hook. |

### Documentation lifecycle

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/review-docs` | auto | ⚪ unverified | Audit the project's documents against each other and against the codebase, reporting what is stale, out of sync, or missing. Reports read-only by default; applies mechanical auto-fixes and commits them only on your explicit confirmation. Use when asked whether documentation is up to date or if anything has drifted. |
| `/sync-docs` | explicit | ⚪ unverified | Take new information — client feedback, a call summary, a product decision, a direction change — and update the correct project documents. Use when asked to record a decision or reflect a change in the docs. |
| `/bootstrap-design-docs` | explicit | ⚪ unverified | Bootstrap a project's documentation layer one document at a time, by reverse-engineering what is already built and proposing each document for the human to accept or decline. The installer for a new project's documentation layer. Note: not yet verified against a real zero-docs project. |

### Discovery

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/survey` | auto | ⚪ unverified | Survey an unknown project — detected stack, candidate source roots, a document inventory with proposed roles, and an explicit list of what could not be determined. With --check, diff what is on disk against what the config declares, the one direction no existing check runs. Read-only: writes only .backend-suite/survey.json, and --check, --stdout and --json write nothing, and a default run writes only .backend-suite/survey.json, creating that directory if it is absent. |
| `/map-project` | explicit | ⚪ unverified | Propose the mappings a survey cannot: which document is really the API doc, which project kind this is (service or library), which candidate document source is the true one — each with the reasoning it was argued from. Every value it proposes is written with provenance `inferred` and nothing else, so no downstream check trusts it until a human ratifies. Proposes and argues; never decides. |

### Building — a mutation on the project's own contract

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/wire-endpoint` | explicit | ⚪ unverified | Wire a hardcoded or stub data source to a mocked GET endpoint in the shape the project already uses — fixture, contract registration, docs, test. Use when asked to wire up or connect a data source. |
| `/sync-mock-api` | explicit | ✅ proven | Regenerate the generated parts of a mock-API contract from its hand-edited fixture — API docs, mock entry, and derived artifacts. Use after editing a fixture. |

### Playbooks — multi-step, orchestrated flows

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/onboard-new-client` | explicit | ⚪ unverified | Playbook rather than a new capability: the ordered sequence of existing skills for standing up the documentation and contract foundation of a new client project or a greenfield area. Start here when onboarding a project. |
| `/run-chain` | explicit | ⚠️ experimental | Run a multi-skill playbook one step at a time, keeping its position across sessions and stopping at every checkpoint. Use when asked to run, resume, or check progress on a chain or playbook such as onboarding a new project. |

### Configuration

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/propose-config` | explicit | ⚪ unverified | Propose real values for the TODO sections init.py scaffolds (layer rules, the routes and TTL-map locations), each measured from this project's code with its evidence, and write a section only after the user confirms it. Writes .backend-suite/ config, so it is never invoked without an explicit instruction. Use after /map-project when /repo-health shows audits refusing on TODO placeholders. |

### Capture — what a session produced

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/log-decision` | explicit | ⚪ unverified | Draft an entry for the project's decision log in that log's own existing format, for review before anything is written. Use when asked to log, record, or write down a decision, or after /session-decisions surfaces one. |
| `/capture-backlog` | explicit | ⚪ unverified | Draft backlog entries in the project backlog's own existing format, for review before anything is written. Use when asked to add something to the backlog, file follow-up work, or capture what came up during a session. |
| `/ratify` | explicit | ⚪ unverified | Use when asked to ratify, approve, or sign off a profile field, or when doctor reports fields as UNTRUSTED. Records one field as 'declared' or 'approved', signed, dated and commit-stamped. Writes to .backend-suite/profile.json, so never invoked without an explicit instruction. |

### Maintenance — a project's debt and the suite's own health

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/design-debt` | auto | ⚪ unverified | Use when asked for an overall picture of design health or design debt across audits. Grades findings already collected in .backend-suite/findings/ per category; it runs no audit, so a category with no findings is missing data, and it names what to re-run. Read-only: reports, never fixes. |
| `/repo-health` | auto | ⚪ unverified | Use when starting a session on an unfamiliar project, or asked for overall audit/health status in one read. Runs every audit fresh and reports one JSON posture: configured, clean, findings, refused. Never changes your code, but saves every audit's report files as it runs. |
| `/cleanup-worktrees` | explicit | ⚪ unverified | Use after a session that fanned out worktree agents, or to find a worktree holding uncommitted work. Reports every git worktree (.claude/worktrees/ and ../suite-<topic>) and removes stale ones; refuses by name on locked, uncommitted, or unmerged ones. Dry-run by default; destructive under --apply. |
| `/upgrade-measure` | auto | ⚪ unverified | Use before upgrading the suite in a project, or on a suite PR before merging. Runs both versions' audits on throwaway copies and diffs exit codes and finding counts, checks two revisions for consumer breaks, and lists which projects are on which version. Read-only: never writes to the measured project. |
| `/upgrade-apply` | explicit | ⚪ unverified | Use only when explicitly asked to apply or migrate a suite upgrade, after /upgrade-measure and human approval. Syncs the profile schema copy, scaffolds a missing hooks map, names newly-required keys, re-baselines reviewed findings. Writes to .backend-suite/, one refusable action at a time; never rewrites profile.json. |

### PR workflow

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/design-review-pr` | auto | ⚪ unverified | Review a branch's changes against a base ref: run every live audit, keep only findings on changed lines (then elsewhere in changed files), and list every audit that could not check. Prints a markdown review; never edits code and never posts unless explicitly told to. Use when asked to design-review a PR or branch, or before opening a PR. |

### Other

Not assigned to a group in `catalog.py`. Visible rather than dropped.

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/audit-cache-ttl-coverage` | auto | ⚪ unverified | Report-only audit for per-endpoint cache TTL drift — routes whose action has no TTL map entry, and TTL map entries whose route no longer exists. Use when asked whether the cache TTL config still matches the routing table, after adding or removing a route, or when endpoints cache outside the declared policy. |
| `/audit-endpoint-parity` | auto | ⚪ unverified | Report-only audit comparing served endpoints against their OpenAPI annotations — routes whose controller method carries no docblock marker (absent from the generated spec) and annotated methods no route serves (phantom contract). Use when asked whether the API docs still match the routing table, after adding or removing an endpoint, or when the generated spec looks stale. |
| `/audit-error-shape` | auto | ⚪ unverified | Report-only audit for the error envelope — error-status responses authored outside the exception handler (callers branching on the envelope will not see their shape) and declared envelope keys missing from the handler itself. Use when asked whether error responses are consistent, after changing the exception handler, or when a client reports an error payload it cannot parse. |
| `/audit-rate-limit` | auto | ⚪ unverified | Report-only audit for inbound rate-limit coverage — endpoints with no limiter in their declaration and no global throttle, with documented exemptions carrying reasons. Use when asked which endpoints are rate-limited, after adding a route, or when deciding the API's protection policy. |
| `/audit-route-coverage` | auto | ⚪ unverified | Report-only audit resolving every declared route action to a real controller method — a route whose action string no longer resolves 500s on every request. Use when asked whether the routing table is intact, after renaming or moving a controller method, or when routes appear to have broken without a build error. |
| `/audit-test-network-coupling` | auto | ⚪ unverified | Report-only audit for tests that can reach a live service — tests referencing a live host with no recorded-client marker, and real-client fallbacks that go live when a recording is absent. Use when asked whether the suite is hermetic, after adding a test that fetches, or when CI behaves differently from local runs. |
| `/audit-toolchain-gates` | auto | ⚪ unverified | Report-only audit for the project's own test toolchain — required scripts absent from the manifest, scripts pointing at undeclared runner suites, and suites whose directory no longer exists (running zero tests while exiting green). Use when asked whether the test command actually runs tests, after renaming a testsuite or moving a test directory. |
| `/audit-versioning` | auto | ⚪ unverified | Report-only audit that the API's version statements agree — the versioned route file's name, the URL prefix it mounts under, and the controller namespace handlers resolve through. Use when asked whether versioning is consistent, before a version bump, or when endpoints appear on the wrong URL. |

### Agents

| Agent | Invocation | Maturity | What it does |
|---|---|---|---|
| `mock-api-auditor` | auto | ✅ proven | Use when asked to find hardcoded data sources that should be wired to a mock GET endpoint, fixtures with no contract, or mutations given a fake POST/PATCH. Needs judgment, so it complements the deterministic audit_mock_api.py drift check. Read-only: produces a Mock-API Completeness Report; never edits code, fixtures, or contracts.json. |
| `session-decisions` | auto | ⚪ unverified | Read-only sweep of the current working session for decisions that belong in the project's decision log and follow-up work that belongs in its backlog. Use near the end of a working session, before a PR, or when asked what was decided or what came up. Reports what it found and where it belongs; never writes to any document. |

### Hooks

Automatic by definition, so they carry no invocation tier. They are harness-only: they nudge, they never edit. Listed from `hooks/hooks.json`, which is what actually registers them — a hook script present but unregistered does nothing, and that is the failure worth catching.

| Event | Matcher | Script | Nudge |
|---|---|---|---|
| SessionStart | `startup|clear` | `session_start_onboarding.py` | Checking whether this project is set up for backend-suite... |
| PostToolUse | `Write|Edit` | `mock_api_reminders.py` | Checking for mock-API contract changes... |
| PostToolUse | `Write|Edit|Bash` | `audit_on_edit.py` | Running audits mapped to this change... |

## `house-style`

### Other

Not assigned to a group in `catalog.py`. Visible rather than dropped.

| Skill | Invocation | Maturity | What it does |
|---|---|---|---|
| `/draft-pr-description` | auto | ✅ proven | Draft a PR title and description from the actual diff and commit history, following the project's own PR template. Drafts only — never pushes, force-pushes, or opens the PR without an explicit go-ahead. |
| `/generate-client-readiness` | explicit | ✅ proven | Derive a client-facing production-readiness summary from the internal checklist and export it to PDF. A derived collateral: regenerate it rather than hand-editing the output. |

### Hooks

Automatic by definition, so they carry no invocation tier. They are harness-only: they nudge, they never edit. Listed from `hooks/hooks.json`, which is what actually registers them — a hook script present but unregistered does nothing, and that is the failure worth catching.

| Event | Matcher | Script | Nudge |
|---|---|---|---|
| PostToolUse | `Bash` | `pr_reminders.py` | Checking for PR-related commands... |

## What this catalogue does not tell you

Every row above is a file-existence fact, which is all a generator can honestly assert. **Capability limits are not listed here** — a claim that something *cannot* be done is not checkable from the filesystem, and a stale one of those already shipped in this file once. Read them where they are gated instead:

- **Per-language limits** — each adapter's module docstring in `backend_suite/adapters/`, beside the code and covered by that adapter's own self-test.
- **External toolchain** (Blender, `cwebp`, `rsvg-convert`) — run `pipeline.py check`, which probes for them rather than asserting anything.
- **Whether a component has ever actually been run** — the `maturity` column, and `verify.py` for the evidence behind it.

