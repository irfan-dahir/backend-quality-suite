"""Per-harness input/output adapters for the suite's two portable hooks.

    session_start_onboarding.py --harness <name>
    audit_on_edit.py            --harness <name>

The hook LOGIC (classify a project, decide which audits to run, word the
notice) is harness-neutral and lives in those two files. This module only does
the two harness-specific things: turn the harness's stdin payload into the
Claude-shaped dict the logic already reads, and turn the logic's message into
whatever that harness's hook contract accepts on stdout.

## The adapter is chosen, never guessed

`--harness` is written into the generated hook config by
`backend-suite hooks --harness X`. Nothing here sniffs environment variables to
work out which harness is calling: Cursor, Codex and Gemini all set variables
that overlap with Claude Code's, and an adapter picked by guess would emit a
shape the real caller silently ignores — findings produced, never delivered,
indistinguishable from a clean edit. Absent `--harness` means `claude`,
because the plugin's own hooks/hooks.json predates the flag and Claude Code's
behaviour must stay byte-identical. An unknown name is a hard error.

## Contracts, from docs/research/harness-support-matrix-2026-10-08.md

  claude   stdout JSON `systemMessage` / `hookSpecificOutput.additionalContext`
  codex    "same shape as Claude Code" (stdout JSON additionalContext, systemMessage)
  vscode   `.github/hooks/*.json`; output `additionalContext`
  gemini   stdout JSON only; `hookSpecificOutput.additionalContext`, `systemMessage`;
           after-edit event is `AfterTool`
  cursor   `sessionStart` / `postToolUse` output `additional_context`
  cursor-after-edit, devin
           `afterFileEdit` has no output fields; Devin Desktop documents no
           context injection and no session-start event. Findings cannot reach
           the model, so they are written under `.backend-suite/` and to stderr,
           and the message says the model did not see them.

The INPUT payload shapes of every harness except Claude Code are UNVERIFIED —
the research read output contracts, not stdin schemas. `normalize()` therefore
looks for a file path under every plausible key and treats any payload that
carries one as an edit; it never invents a path.

Stdlib only; must not import bin/ (not on the path from hooks/).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HARNESSES = ("claude", "codex", "vscode", "gemini", "cursor",
             "cursor-after-edit", "devin")
# Harnesses whose after-edit hook has no channel back to the model.
FILE_SINK = ("cursor-after-edit", "devin")
REPORT_DIR = ".backend-suite/hook-reports"


class UnknownHarness(ValueError):
    pass


def parse_harness(argv: list[str]) -> str:
    """`--harness X` / `--harness=X` from argv; `claude` when absent."""
    name = None
    for i, arg in enumerate(argv):
        if arg == "--harness":
            if i + 1 >= len(argv):
                raise UnknownHarness("--harness needs a value")
            name = argv[i + 1]
        elif arg.startswith("--harness="):
            name = arg.split("=", 1)[1]
    if name is None:
        return "claude"
    if name not in HARNESSES:
        raise UnknownHarness(f"unknown harness {name!r}; expected one of "
                             f"{', '.join(HARNESSES)}")
    return name


# --- input -----------------------------------------------------------------

_TOOL_ALIASES = {
    # Gemini CLI tool names (matcher examples in the research doc).
    "write_file": "Write", "replace": "Edit", "run_shell_command": "Bash",
}
_CANONICAL = {"Write", "Edit", "NotebookEdit", "Bash"}
_PATH_KEYS = ("file_path", "path", "absolute_path", "filePath")
_CMD_KEYS = ("command", "command_line", "cmd")


def _first(d, keys):
    if not isinstance(d, dict):
        return ""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def normalize(harness: str, data: dict) -> dict:
    """Return the Claude-shaped payload audit_on_edit's logic reads.

    `claude` is returned untouched — byte-identical behaviour is the contract.
    """
    if harness == "claude":
        return data
    nests = [data.get("tool_input"), data.get("tool_info"), data.get("input"), data]
    file_path = next((p for p in (_first(n, _PATH_KEYS) for n in nests) if p), "")
    command = next((c for c in (_first(n, _CMD_KEYS) for n in nests) if c), "")
    tool = str(data.get("tool_name") or "")
    tool = _TOOL_ALIASES.get(tool, tool)
    if harness == "cursor-after-edit" or (harness == "devin" and file_path):
        tool = "Edit"
    elif tool not in _CANONICAL:
        tool = "Edit" if file_path else ("Bash" if command else tool)
    session = (data.get("session_id") or data.get("conversation_id")
               or data.get("trajectory_id") or "")
    out = {"tool_name": tool,
           "tool_input": {"file_path": file_path, "command": command}}
    if session:
        out["session_id"] = str(session)
    return out


def start_dir(harness: str, data: dict) -> Path | None:
    """Where a non-Claude harness says the project is, if its payload says.

    `cwd` and Cursor's `workspace_roots` are tried; the env var is the caller's
    business (Claude Code sets CLAUDE_PROJECT_DIR). Returns None for `claude`
    so the existing resolution order is untouched.
    """
    if harness == "claude":
        return None
    roots = data.get("workspace_roots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str):
        return Path(roots[0])
    cwd = data.get("cwd")
    return Path(cwd) if isinstance(cwd, str) and cwd else None


# --- output ----------------------------------------------------------------

def session_start(harness: str, text: str) -> None:
    """Deliver a session-start notice. Writes nothing to disk, on every path."""
    if harness in ("claude", "codex", "vscode", "gemini"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": text}}))
    elif harness == "cursor":
        print(json.dumps({"additional_context": text}))
    else:
        # No session-start event with a model channel exists for this harness.
        # Never write a file from session start — stderr only, and say so.
        print(f"backend-suite ({harness}): this harness has no session-start "
              f"context channel, so the model was NOT told: {text}", file=sys.stderr)


def after_edit(harness: str, message: str, to_model: bool,
               repo: Path | None) -> None:
    """Deliver an after-edit message in this harness's contract.

    For `claude` this is exactly the pre-adapter emit(): `systemMessage`
    always, `additionalContext` only for notices. Other Claude-shaped
    harnesses always get additionalContext too — the research names it as the
    portable carrier for findings, and there is no prior behaviour to keep.
    """
    if harness == "claude":
        out: dict = {"systemMessage": message}
        if to_model:
            out["hookSpecificOutput"] = {"hookEventName": "PostToolUse",
                                         "additionalContext": message}
        print(json.dumps(out))
    elif harness in ("codex", "gemini"):
        event = "AfterTool" if harness == "gemini" else "PostToolUse"
        print(json.dumps({"systemMessage": message, "hookSpecificOutput": {
            "hookEventName": event, "additionalContext": message}}))
    elif harness == "vscode":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": message}}))
    elif harness == "cursor":
        print(json.dumps({"additional_context": message}))
    else:
        write_report(harness, message, repo)


def report_path(harness: str, repo: Path) -> Path:
    return repo / REPORT_DIR / f"after-edit-{harness}.txt"


def write_report(harness: str, message: str, repo: Path | None) -> None:
    """File-sink delivery: `.backend-suite/hook-reports/` (only if the project
    already has `.backend-suite/`) plus stderr, naming the missing channel."""
    where = "not written (no .backend-suite/ in this project)"
    if repo is not None and (repo / ".backend-suite").is_dir():
        path = report_path(harness, repo)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            path.write_text(f"[{stamp}] backend-suite after-edit ({harness})\n"
                            f"{message}\n")
            where = f"written to {path}"
        except OSError as exc:
            where = f"could not be written ({exc})"
    print(f"backend-suite ({harness}): this harness's after-edit hook cannot feed "
          f"the model — it has NOT seen this. Report {where}.\n{message}",
          file=sys.stderr)

