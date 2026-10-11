# Harness support matrix — 2026-10-08

Research input for making the suite a harness-agnostic drop-in. Research only:
nothing here is implemented.

**Method.** Every row was read from the vendor's own documentation on
2026-10-08 via WebFetch (the org browser cannot reach external sites). Page
"last updated" dates are quoted where the page states one; most do not, so the
read date is the version. Fetches pass through a summarising model, so wording
is paraphrase, not quotation. Anything not confirmed on an official page is
marked **UNVERIFIED**. Per this repo's governing principle, an empty cell means
"not checked", never "not supported" — absence is written as `none documented`
only when the relevant official page was read and did not mention it.

**Two vendor changes found during research** that invalidate older notes:

- Windsurf docs (`docs.windsurf.com`) now redirect to `docs.devin.ai/desktop/…`;
  the product is documented as **Devin Desktop (formerly Windsurf)** and paths
  moved from `.windsurf/` to `.devin/` (legacy paths noted as historical).
- Codex docs (`developers.openai.com/codex/…`) now 308-redirect to
  `learn.chatgpt.com/docs/…`.

---

## AGENTS.md as a cross-tool convention

- Stewarded by the **Agentic AI Foundation under the Linux Foundation**;
  plain Markdown, no required fields; nearest file to the edited code wins;
  explicit chat prompt overrides all files. <https://agents.md/> (read
  2026-10-08). The site lists Codex, Copilot coding agent, VS Code, Cursor,
  Zed, Windsurf, Aider, opencode, RooCode, Amp, Gemini CLI and others as
  supporting it. **That list is self-reported by the site**; each row below
  checks the vendor's own doc instead. Two disagreements found: Aider's own
  conventions page does not mention auto-reading AGENTS.md, and Gemini CLI
  reads it only if `context.fileName` is configured.
- **Claude Code now reads AGENTS.md natively** (v2.1.277+) when no CLAUDE.md
  exists in cwd or above; if both exist it reads only CLAUDE.md unless the
  CLAUDE.md imports `@AGENTS.md` or the "Project instructions" setting is
  changed. <https://code.claude.com/docs/en/memory#agents-md>

## Agent Skills (SKILL.md) as a cross-tool convention

Open standard at <https://agentskills.io> (cited as the governing spec by
Cursor, VS Code, Gemini CLI). Common core: a directory containing `SKILL.md`
with YAML frontmatter `name` + `description`, optional `scripts/`,
`references/`, `assets/`; progressive disclosure (only name/description
preloaded). **The shared project path is `.agents/skills/`** — read by Codex,
Cursor, VS Code Copilot, Gemini CLI, opencode, Amp. `.claude/skills/` is also
read by VS Code, Cline, opencode, Amp.

## MCP prompts adoption

The MCP site's client feature table (`modelcontextprotocol.io/clients`) no
longer exists at that URL (it now serves the intro page) — **UNVERIFIED** from
a central source. Per vendor docs:

| Prompts surfaced to users | Tools only / prompts not documented |
|---|---|
| Claude Code (`/mcp__server__prompt`), Cursor, VS Code Copilot (`/<server>.<prompt>`), Zed (as slash commands), Devin Desktop/Windsurf | Copilot cloud/coding agent (explicitly tools only), Codex (not documented), Cline (not documented), opencode (not documented), Gemini CLI (UNVERIFIED — not on the pages read), Amp (not documented) |

Conclusion: **MCP prompts cannot be the primary carrier for guided chains.**
MCP tools are the only universally supported MCP primitive.

---

## Matrix

Legend for MCP: T tools, P prompts, R resources. "Project file" means a file
a repo can commit to declare the server.

### 1. Claude Code

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `CLAUDE.md` / `.claude/CLAUDE.md` / `CLAUDE.local.md`, ancestors at launch, subdirs on demand, `@path` imports, `.claude/rules/`; AGENTS.md natively if no CLAUDE.md (see above) | [memory](https://code.claude.com/docs/en/memory) |
| MCP | T+P+R (prompts as `/mcp__server__prompt`, resources via `@server:uri`); stdio, HTTP, SSE (deprecated), WS; project file `.mcp.json` `{"mcpServers":{…}}`, trust prompt required | [mcp](https://code.claude.com/docs/en/mcp) |
| Hooks | `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `PreCompact`, `FileChanged`, … in `.claude/settings.json` or plugin `hooks/hooks.json`; stdin JSON; exit 2 blocks; stdout JSON `hookSpecificOutput.additionalContext` (10k char cap), `systemMessage`, `continue` | [hooks](https://code.claude.com/docs/en/hooks) |
| Skills | `SKILL.md`; `.claude/skills/`, plugin `skills/` | [plugins-reference](https://code.claude.com/docs/en/plugins-reference) |
| Plugins | `.claude-plugin/plugin.json` + `skills/ commands/ agents/ hooks/hooks.json .mcp.json bin/`; installed via marketplaces; `${CLAUDE_PLUGIN_ROOT}` | [plugins-reference](https://code.claude.com/docs/en/plugins-reference) |
| Commands | `commands/*.md` (docs say prefer skills for new plugins) | same |

### 2. OpenAI Codex (CLI / IDE / app)

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `AGENTS.override.md` > `AGENTS.md` > `project_doc_fallback_filenames`, global `~/.codex/` then git root → cwd, concatenated root-down (nearer wins), one file per dir, 32 KiB cap (`project_doc_max_bytes`) | [agents-md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| MCP | T documented; server `instructions` read; P/R **not documented**; stdio + streamable HTTP; `~/.codex/config.toml` or project `.codex/config.toml` (trusted projects only), TOML `[mcp_servers.<name>]` | [mcp](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) |
| Hooks | `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `Stop`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `Subagent*`; `~/.codex/hooks.json`, `<repo>/.codex/hooks.json` or `[hooks]` in config.toml, plugin `hooks/hooks.json` (trust review); enabled by default; stdout plain text or JSON `additionalContext`, `systemMessage` — **same shape as Claude Code** | [hooks](https://learn.chatgpt.com/docs/hooks) |
| Skills | `SKILL.md` at `.agents/skills/` (cwd, parents, repo root), `~/.agents/skills`; `$name` explicit or implicit | [build-skills](https://learn.chatgpt.com/docs/build-skills) |
| Plugins | `.codex-plugin/plugin.json` + `skills/`, `.mcp.json`, `hooks/`; repo marketplace `.agents/plugins/marketplace.json` | [plugins/build](https://developers.openai.com/codex/plugins/build/) (search-result summary — treat detail as **UNVERIFIED** until read directly) |
| Commands | Custom prompts not in current docs; skills are the recommended route (**UNVERIFIED** whether legacy `~/.codex/prompts` still works) | [hooks](https://learn.chatgpt.com/docs/hooks) |

### 3. Cursor (IDE agent; CLI not separately checked)

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `.cursor/rules/*.mdc` (frontmatter `alwaysApply`, globs, `description`), `AGENTS.md` root + nested; order Team → Project → User. CLAUDE.md: **none documented** | [rules](https://cursor.com/docs/context/rules) |
| MCP | T+P+R (+roots, elicitation, apps); stdio, SSE, streamable HTTP; `.cursor/mcp.json` | [mcp](https://cursor.com/docs/context/mcp) |
| Hooks | `.cursor/hooks.json` `{version:1,hooks:{…}}`; `sessionStart` (out: `additional_context`, `env`), `postToolUse` (out: `additional_context`), `afterFileEdit` (no output fields), `preToolUse`, `stop`, … ; exit 2 blocks. Cloud agents skip `sessionStart` | [hooks](https://cursor.com/docs/agent/hooks) |
| Skills | `.cursor/skills/` or `.agents/skills/`; `/skill-name`; `disable-model-invocation` | [skills](https://cursor.com/docs/context/skills) |
| Plugins | Team marketplace mentioned; format **UNVERIFIED** | same |
| Commands | Skills replace legacy slash commands (migration supported); `.cursor/commands` **UNVERIFIED** | same |

### 4. GitHub Copilot

| Aspect | VS Code agent mode (page updated 2026-10-07) | Copilot cloud/coding agent |
|---|---|---|
| Instructions | `.github/copilot-instructions.md`, `*.instructions.md` (`applyTo`), `AGENTS.md` (nested experimental via `chat.useNestedAgentsMdFiles`, off by default), `CLAUDE.md` for Claude agent host — [custom-instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions) | Listed on agents.md; GitHub's own page **not read — UNVERIFIED** |
| MCP | T+P (`/<server>.<prompt>`)+R; `.vscode/mcp.json` (`"servers"`) or root `.mcp.json` (`"mcpServers"`) — [mcp-servers](https://code.visualstudio.com/docs/copilot/customization/mcp-servers) | **Tools only**, configured in repo Settings UI (JSON), `tools` allowlist required, no OAuth — [extend-coding-agent-with-mcp](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/extend-coding-agent-with-mcp) |
| Hooks | `.github/hooks/*.json`; `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop`, …; output `additionalContext`, `permissionDecision`, `continue`; Claude-format `.claude/settings.json` hooks behind `chat.useClaudeHooks` — [hooks](https://code.visualstudio.com/docs/copilot/customization/hooks) | `.github/hooks/*.json` `version:1`; `sessionStart`, `postToolUse`, `preToolUse`, …; output contract not on page read — [about-hooks](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks) |
| Skills | `.github/skills/`, `.claude/skills/`, `.agents/skills/`; `/name` — [agent-skills](https://code.visualstudio.com/docs/copilot/customization/agent-skills) | UNVERIFIED |
| Plugins | Extensions contribute skills via `chatSkills`; plugins can ship `hooks.json` | — |
| Commands | `.github/prompts/*.prompt.md` (deprecated for Agent Host; migrate to skills) — [prompt-files](https://code.visualstudio.com/docs/copilot/customization/prompt-files) | — |

### 5. Gemini CLI

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `GEMINI.md` default; `context.fileName` accepts string or array (e.g. `["AGENTS.md","GEMINI.md"]`); upward discovery to `.git` | [configuration](https://geminicli.com/docs/reference/configuration) |
| MCP | `mcpServers` in `.gemini/settings.json`: stdio `command`, SSE `url`, streamable HTTP `httpUrl`; T confirmed; P/R **UNVERIFIED** | same |
| Hooks | in `settings.json` `hooks`; `SessionStart`, `SessionEnd`, `BeforeAgent`, `AfterAgent`, `BeforeTool`, `AfterTool`, `PreCompress`, …; stdout JSON only; `hookSpecificOutput.additionalContext`, `systemMessage`; exit 2 blocks; matcher regex on tool names (`write_file`, `replace`) | [hooks/reference](https://geminicli.com/docs/hooks/reference/) |
| Skills | `.gemini/skills/` or `.agents/skills/`; activated via `activate_skill` with user approval | [skills](https://geminicli.com/docs/cli/skills/) |
| Plugins | Extensions: `gemini-extension.json` bundling MCP, commands, hooks, skills, context; `gemini extensions install <git-url>`; field schema **UNVERIFIED** (reference page not read) | [extensions](https://geminicli.com/docs/extensions/) |
| Commands | `.gemini/commands/**/*.toml` (`prompt`, `description`, `{{args}}`, `!{…}`, `@{…}`); subdir → `/a:b` | [custom-commands](https://geminicli.com/docs/cli/custom-commands/) |

### 6. Windsurf → Devin Desktop

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `.devin/rules/*.md` (modes always_on / model_decision / glob / manual; 12k chars/file), `AGENTS.md` directory-scoped | [memories](https://docs.devin.ai/desktop/cascade/memories) |
| MCP | T+P+R; stdio, streamable HTTP, SSE; **user-level only** `~/.config/devin/mcp_config.json`; 100-tool limit | [mcp](https://docs.devin.ai/desktop/cascade/mcp) |
| Hooks | `.devin/hooks.json`; `pre_*`/`post_write_code`, `post_read_code`, `post_run_command`, `post_cascade_response`, …; exit 2 blocks pre-hooks; **no session-start event and no documented context injection** | [hooks](https://docs.devin.ai/desktop/cascade/hooks) |
| Skills | `.devin/skills/<name>/SKILL.md`; `@skill-name`. `.agents/skills` **not documented** | [skills](https://docs.devin.ai/desktop/cascade/skills) |
| Plugins | none documented | — |
| Commands | "Workflows" are slash-command templates; path **UNVERIFIED** | [memories](https://docs.devin.ai/desktop/cascade/memories) |

### 7. Cline / Roo Code

| Aspect | Cline | Roo Code (page updated 2026-05-15) |
|---|---|---|
| Instructions | `.clinerules/` or `.cline/rules/`, `.cursorrules`, `.windsurfrules`, `AGENTS.md`; CLAUDE.md not documented — [cline-rules](https://docs.cline.bot/customization/cline-rules.md) | `.roo/rules/`, `.roo/rules-{mode}/`, `.roorules`, `AGENTS.md`/`AGENT.md` — [custom-instructions](https://roocodeinc.github.io/Roo-Code/features/custom-instructions) |
| MCP | T documented, P/R not documented; stdio, streamable HTTP, SSE; user-level `cline_mcp_settings.json` only — [mcp-overview](https://docs.cline.bot/mcp/mcp-overview.md) | `.roo/mcp.json` project file; capabilities UNVERIFIED |
| Hooks | SDK plugin hooks (`before_agent_start` can inject context, `tool_call_after`, `run_end`); in-process JS, not a shell/JSON contract — [sdk/plugins](https://docs.cline.bot/sdk/plugins) | UNVERIFIED |
| Skills | `.cline/skills/`, `.clinerules/skills/`, `.claude/skills/`; `/skill-name` — [skills](https://docs.cline.bot/customization/skills.md) | Referenced in nav; UNVERIFIED |
| Plugins | `AgentPlugin` export; `cline plugin install` (npm/git/local) | UNVERIFIED |
| Commands | Plugin commands; workflows UNVERIFIED | `.roo/commands` UNVERIFIED |

### 8. Zed (native agent)

| Aspect | Finding | Source |
|---|---|---|
| Instructions | **First match only**: `.rules`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.github/copilot-instructions.md`, `AGENT.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`; personal `~/.config/zed/AGENTS.md` | [instructions](https://zed.dev/docs/ai/instructions) |
| MCP | T+P (as slash commands); R mentioned not detailed; local command + remote HTTP; `context_servers` in `.zed/settings.json` | [mcp](https://zed.dev/docs/ai/mcp) |
| Hooks | none documented | — |
| Skills | Skills exist; paths UNVERIFIED | [instructions](https://zed.dev/docs/ai/instructions) |
| Plugins | Extensions can provide MCP servers; mechanism not read | — |
| Commands | MCP prompts only | — |

Note: a `.rules` or `.cursorrules` file in a project would shadow AGENTS.md in Zed.

### 9. Aider

| Aspect | Finding | Source |
|---|---|---|
| Instructions | No auto-discovery documented; `--read CONVENTIONS.md` or `read:` in `.aider.conf.yml` | [conventions](https://aider.chat/docs/usage/conventions.html) |
| MCP | **No native support** — open requests (e.g. #4506) | [issue #4506](https://github.com/Aider-AI/aider/issues/4506) |
| Hooks / Skills / Plugins / Commands | none documented | — |

### 10. Amp

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `AGENTS.md` from cwd up to `$HOME` and subtrees on read; fallback `AGENT.md` then `CLAUDE.md`; `globs` frontmatter | [agents-md](https://ampcode.com/docs/customize/agents-md) |
| MCP | `amp.mcpServers` in `.amp/settings.json` (workspace, needs approval) or user settings; local + remote; skills can bundle `mcp.json`; P/R not documented | [mcp](https://ampcode.com/docs/customize/mcp) |
| Hooks | Via plugins: `session.start`, `tool.call`, `tool.result`, `agent.end` (TS/JS in `.amp/plugins/`); context-injection API not confirmed | [plugins](https://ampcode.com/docs/customize/plugins) |
| Skills | `.agents/skills/`, `.claude/skills/` | [skills](https://ampcode.com/docs/customize/skills) |
| Commands | Plugins add command-palette actions; slash commands UNVERIFIED | [plugins](https://ampcode.com/docs/customize/plugins) |

### 11. opencode

| Aspect | Finding | Source |
|---|---|---|
| Instructions | `AGENTS.md` (walk up), else `CLAUDE.md`; global `~/.config/opencode/AGENTS.md`; extra files via `instructions` in `opencode.json` | [rules](https://opencode.ai/docs/rules/) |
| MCP | `mcp` in `opencode.json`, `type: local` (`command` array) / `remote`; tools only documented | [mcp-servers](https://opencode.ai/docs/mcp-servers/) |
| Hooks | JS/TS plugins in `.opencode/plugins/`: `session.created`, `file.edited`, `tool.execute.after`, …; documented context injection only on compaction | [plugins](https://opencode.ai/docs/plugins/) |
| Skills | `.opencode/skills/`, `.claude/skills/`, `.agents/skills/` | [skills](https://opencode.ai/docs/skills/) |
| Commands | `.opencode/commands/*.md` with frontmatter | [commands](https://opencode.ai/docs/commands/) |

---

## Recommendations

### Minimum generated artifact set

Ordered by harnesses covered per artifact:

1. **`AGENTS.md`** (generated, short, points at `{{doc:*}}` roles and the MCP
   tools). Read by Codex, Cursor, VS Code Copilot, Devin Desktop, Cline, Roo,
   Zed, Amp, opencode, and Claude Code when no CLAUDE.md exists. For
   Gemini CLI, ship `.gemini/settings.json` with
   `context.fileName: ["AGENTS.md","GEMINI.md"]`; for Claude Code projects
   that already have CLAUDE.md, add an `@AGENTS.md` import line. Aider: document
   `read: AGENTS.md` in `.aider.conf.yml`.
2. **One MCP server, tools-only contract** (the existing `mcp/` server). It is
   the only carrier for audits that reaches every harness except Aider. Ship
   per-harness declaration files from one source: `.mcp.json` (Claude Code,
   VS Code), `.vscode/mcp.json`, `.cursor/mcp.json`, `.codex/config.toml`,
   `.gemini/settings.json`, `.zed/settings.json`, `.amp/settings.json`,
   `opencode.json`, `.roo/mcp.json`. Devin Desktop and Cline are user-level
   only — print install instructions, do not write to `~`. Use the server's
   `instructions` field (Codex reads it) to restate the INERT rule.
3. **Skills at `.agents/skills/<name>/SKILL.md`** generated from the 52
   command/skill sources (frontmatter `name` + `description` only in the
   portable core; harness-specific keys like `disable-model-invocation` for
   `invocation: explicit` components). Covers Codex, Cursor, VS Code, Gemini,
   Amp, opencode. Mirror to `.claude/skills/` for Claude Code/Cline, and
   `.devin/skills/` for Devin Desktop. Skill bodies must call scripts via a
   resolvable path, not `${CLAUDE_PLUGIN_ROOT}` (only Claude Code substitutes it).
4. **Hooks for the Claude-shaped family** — Claude Code, Codex, VS Code
   (local), Gemini CLI, Cursor, Copilot cloud agent all accept "command gets
   JSON on stdin, returns JSON with additionalContext". One script with a thin
   per-harness output shim (Cursor uses `additional_context`; Gemini needs
   pure-JSON stdout) and per-harness registration files.

Not worth generating: `.cursor/rules/*.mdc`, `copilot-instructions.md`,
`.clinerules`, `.prompt.md`, Gemini `.toml` commands — each is covered by
AGENTS.md or skills, and every extra copy is drift.

### Feature portability

| Feature | Portable carrier | Harnesses | Degrades to |
|---|---|---|---|
| Session-start onboarding offer | `SessionStart` hook emitting additionalContext ("profile missing — offer /onboard") | Claude Code, Codex, VS Code local, Gemini, Cursor (not cloud), Copilot agent (contract UNVERIFIED) | AGENTS.md line: "if `.backend-suite/profile.json` is absent, offer onboarding before other work". Devin Desktop, Zed, Cline, Amp, opencode, Aider |
| After-edit audits | `PostToolUse`/`AfterTool`/`postToolUse` matched to edit tools, running the audit and returning findings as additionalContext | Claude Code, Codex, VS Code, Gemini, Cursor (`postToolUse`, not `afterFileEdit` which has no output) | Devin `post_write_code` can run the audit but cannot feed the model — write a report file and print to stderr. Elsewhere: AGENTS.md instruction to call the MCP audit tools after edits, and a git pre-commit hook (harness-independent) as the backstop |
| Guided chains with checkpoints | State in `.backend-suite/` (already how `run-chain` works) + MCP tools `chain_status` / `chain_advance` that refuse to advance without an explicit confirmation argument | All MCP-capable harnesses | Skill text alone (no MCP): the model must be told to stop; checkpoint enforcement is advisory. MCP prompts are not a reliable entry point (see above) |

### What must degrade gracefully (and visibly)

Under the governing principle, every degraded path must say so:

- **No hooks** → the onboarding offer and after-edit audits become
  instructions, not guarantees. `doctor`/`repo-health` should report
  "after-edit audits: NOT WIRED in this harness", never imply coverage.
- **No MCP (Aider)** → CLI scripts only; AGENTS.md lists the commands.
- **Hook can't inject context (Devin Desktop, Cursor `afterFileEdit`,
  opencode)** → findings go to a file plus stderr; the absence of model
  feedback is reported, not silent.
- **Instruction shadowing (Zed first-match, Claude Code CLAUDE.md-over-AGENTS.md,
  Gemini default GEMINI.md)** → the installer should detect the shadowing
  file and warn, since the generated AGENTS.md would otherwise be silently
  unread.
- **Explicit-tier components** → harnesses without
  `disable-model-invocation` (or equivalent) may auto-invoke a
  content-generating skill; those skills' own bodies must restate "require an
  explicit user request" as the floor.
- **`${CLAUDE_PLUGIN_ROOT}`** → only Claude Code expands it; generated
  artifacts need an install-time absolute path or a `.backend-suite/` shim.

## Open items (UNVERIFIED, worth a direct read before implementation)

Copilot cloud agent instruction files and hook output contract; Gemini CLI MCP
prompts/resources and `gemini-extension.json` schema; Codex plugin manifest
detail and legacy custom prompts; Cursor plugin format; Devin Desktop workflow
path and `.agents/skills` support; Roo Code skills/commands/hooks; Zed skill
paths; Amp plugin context-injection API; a current central MCP client-feature
table.
