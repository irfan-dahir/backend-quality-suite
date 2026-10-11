"""Per-harness hook registration: what to write, where, and whether it is wired.

Every path and format here is taken from
docs/research/harness-support-matrix-2026-10-08.md; each harness's `doc` names
the section whose Hooks row (and vendor link) it came from. Where that document does
not state a format completely, the harness is `instructions`-only: the snippet
is printed for a human to place after checking the vendor page, and nothing is
written. Writing a config file in a guessed shape would produce a hook the
harness silently ignores — a wired-looking project that audits nothing.

  harness   mode          file                    source of the format
  claude    plugin        (plugin hooks/hooks.json) the plugin wires itself
  codex     write         .codex/hooks.json       "same shape as Claude Code"
  cursor    instructions  .cursor/hooks.json      top level {version:1,hooks:{…}}
                                                  stated; per-entry shape is not
  vscode    instructions  .github/hooks/*.json    file location stated; schema not
  gemini    instructions  .gemini/settings.json   `hooks` key, AfterTool, matcher
                                                  regex stated; nesting is not
  devin     instructions  .devin/hooks.json       events stated; schema not

Status is reported per harness and per behaviour as WIRED / NOT WIRED /
UNKNOWN. UNKNOWN is used where the wiring lives outside the project tree (a
Claude Code plugin enabled at user scope) — it is never rounded up to WIRED.

Stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

WIRED, NOT_WIRED, UNKNOWN = "WIRED", "NOT WIRED", "UNKNOWN"
SESSION_SCRIPT = "session_start_onboarding.py"
EDIT_SCRIPT = "audit_on_edit.py"
PRECOMMIT_SENTINEL = "# backend-suite:precommit-hook"
RESEARCH = "docs/research/harness-support-matrix-2026-10-08.md"

HARNESSES: dict[str, dict] = {
    "claude": {
        "mode": "plugin", "file": ".claude/settings.json",
        "doc": "§1 Claude Code Hooks row (vendor link there)",
    },
    "codex": {
        "mode": "write", "file": ".codex/hooks.json",
        "doc": "§2 OpenAI Codex Hooks row (vendor link there)",
        "note": "Codex reads project hooks only for trusted projects; plugin hooks "
                "go through a trust review.",
    },
    "cursor": {
        "mode": "instructions", "file": ".cursor/hooks.json",
        "doc": "§3 Cursor Hooks row (vendor link there)",
        "unverified": "the shape of each entry inside a hook list. Top level "
                      "{version:1,hooks:{…}} and the event names are documented. "
                      "Use postToolUse (has additional_context), not afterFileEdit "
                      "(no output fields). Cloud agents skip sessionStart.",
    },
    "vscode": {
        "mode": "instructions", "file": ".github/hooks/backend-suite.json",
        "doc": "§4 GitHub Copilot (VS Code) Hooks row (vendor link there)",
        "unverified": "the JSON schema of a .github/hooks/*.json file. Location, "
                      "event names (SessionStart, PostToolUse) and the "
                      "additionalContext output are documented.",
    },
    "gemini": {
        "mode": "instructions", "file": ".gemini/settings.json",
        "doc": "§5 Gemini CLI Hooks row (vendor link there)",
        "unverified": "the nesting under the settings.json `hooks` key. The events "
                      "(SessionStart, AfterTool), the tool-name matcher regex "
                      "(write_file|replace) and the JSON-only stdout are documented.",
    },
    "devin": {
        "mode": "instructions", "file": ".devin/hooks.json",
        "doc": "§6 Windsurf → Devin Desktop Hooks row (vendor link there)",
        "unverified": "the .devin/hooks.json schema. post_write_code exists; there "
                      "is no session-start event and no documented context "
                      "injection, so findings go to .backend-suite/hook-reports/ and "
                      "stderr — the model does not see them.",
    },
}


def command(hooks_dir: Path, script: str, harness: str) -> str:
    return f'python3 "{hooks_dir / script}" --harness {harness}'


def snippet(harness: str, hooks_dir: Path) -> dict:
    """The config this harness needs. For `write` harnesses it is exactly what
    `--apply` writes; for `instructions` harnesses it is a best-effort sketch
    whose UNVERIFIED parts are named in HARNESSES[h]['unverified']."""
    s = lambda script, h=harness: command(hooks_dir, script, h)  # noqa: E731
    if harness in ("claude", "codex"):
        return {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": s(SESSION_SCRIPT)}]}],
            "PostToolUse": [{"hooks": [{"type": "command", "command": s(EDIT_SCRIPT)}]}],
        }}
    if harness == "cursor":
        return {"version": 1, "hooks": {
            "sessionStart": [{"command": s(SESSION_SCRIPT)}],
            "postToolUse": [{"command": s(EDIT_SCRIPT)}],
        }}
    if harness == "vscode":
        return {"hooks": {
            "SessionStart": [{"type": "command", "command": s(SESSION_SCRIPT)}],
            "PostToolUse": [{"type": "command", "command": s(EDIT_SCRIPT)}],
        }}
    if harness == "gemini":
        return {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": s(SESSION_SCRIPT)}]}],
            "AfterTool": [{"matcher": "write_file|replace",
                           "hooks": [{"type": "command", "command": s(EDIT_SCRIPT)}]}],
        }}
    if harness == "devin":
        return {"hooks": {"post_write_code": [{"command": s(EDIT_SCRIPT)}]}}
    raise KeyError(harness)


def merge_into(existing: dict, ours: dict) -> tuple[dict, bool]:
    """Append our Claude-shaped event groups to an existing hooks file.

    Returns (merged, changed). A group is skipped when any command already in
    that event names our script — re-running --apply is idempotent and never
    duplicates or rewrites someone else's entries.
    """
    merged = json.loads(json.dumps(existing))
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("existing 'hooks' is not an object")
    changed = False
    for event, groups in ours["hooks"].items():
        current = hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError(f"existing hooks.{event} is not a list")
        script = SESSION_SCRIPT if event == "SessionStart" else EDIT_SCRIPT
        if script in json.dumps(current):
            continue
        current.extend(groups)
        changed = True
    return merged, changed


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _has(text: str, script: str, harness: str) -> bool:
    """Our script with this harness's --harness flag appears in the text."""
    for line in text.splitlines():
        if script in line and f"--harness {harness}" in line:
            return True
    return False


def status(repo: Path) -> dict:
    """{harness: {"sessionStart": S, "afterEdit": S, "detail": str}} plus "git"."""
    out: dict = {}
    for h, spec in HARNESSES.items():
        if h == "claude":
            enabled = False
            for name in ("settings.json", "settings.local.json"):
                try:
                    data = json.loads(_text(repo / ".claude" / name) or "{}")
                except ValueError:
                    data = {}
                plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
                if isinstance(plugins, dict) and any(
                        k.split("@")[0] == "backend-suite" and v
                        for k, v in plugins.items()):
                    enabled = True
            st = WIRED if enabled else UNKNOWN
            detail = ("backend-suite plugin enabled in .claude/ settings; its "
                      "hooks/hooks.json wires both" if enabled else
                      "wired by the plugin's hooks/hooks.json when the plugin is "
                      "enabled — not enabled in this project's .claude/ settings, "
                      "and user-scope settings were not checked")
            out[h] = {"sessionStart": st, "afterEdit": st, "detail": detail}
            continue
        if h == "vscode":
            text = "\n".join(_text(p) for p in sorted((repo / ".github" / "hooks").glob("*.json")))
            where = ".github/hooks/*.json"
        else:
            text = _text(repo / spec["file"])
            where = spec["file"]
        ss = WIRED if _has(text, SESSION_SCRIPT, h) else NOT_WIRED
        ae = WIRED if _has(text, EDIT_SCRIPT, h) else NOT_WIRED
        if h == "devin":
            ss = NOT_WIRED  # no session-start event exists in Devin Desktop
        detail = f"checked {where} for a backend-suite command with --harness {h}"
        if h == "devin":
            detail += "; Devin Desktop has no session-start event, and after-edit " \
                      "findings cannot reach the model even when wired"
        out[h] = {"sessionStart": ss, "afterEdit": ae, "detail": detail}

    git_hook = repo / ".git" / "hooks" / "pre-commit"
    framework = repo / ".pre-commit-config.yaml"
    wired = PRECOMMIT_SENTINEL in _text(git_hook) or PRECOMMIT_SENTINEL in _text(framework)
    out["git"] = {"preCommit": WIRED if wired else NOT_WIRED,
                  "detail": "checked .git/hooks/pre-commit and .pre-commit-config.yaml "
                            "(core.hooksPath not followed)"}
    return out


def render(st: dict) -> str:
    lines = ["hook wiring per harness (a NOT WIRED harness gets no onboarding offer "
             "and no after-edit audits — nothing there is checked):"]
    for h, row in st.items():
        if h == "git":
            lines.append(f"  {'git':<8} pre-commit: {row['preCommit']:<10} ({row['detail']})")
            continue
        lines.append(f"  {h:<8} session-start: {row['sessionStart']:<10} "
                     f"after-edit: {row['afterEdit']:<10} ({row['detail']})")
    return "\n".join(lines)
