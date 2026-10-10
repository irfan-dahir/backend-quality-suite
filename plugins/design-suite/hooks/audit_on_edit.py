#!/usr/bin/env python3
"""Config-driven PostToolUse runner: run the audit that cares about what changed.

Three hooks existed before this one, each hand-written, each re-implementing stdin
parsing, project-root resolution and the never-block discipline:

  design-suite/hooks/mock_api_reminders.py     Write|Edit → one mock-API contract
  house-style/hooks/pr_reminders.py     Bash       → pre-PR checklist nudge
  <project>/.claude/hooks/check_asset_registration.py

Adding a fourth trigger meant writing a fourth file. This runner reads the triggers
from `.design-suite/hooks.map.json` instead, so a new one is a config entry.

ADVISORY ONLY, and deliberately so. This never blocks a tool call, never writes a
file, and never fails a build — it surfaces what an audit said and stops. A hook
that can block turns every save into a gate, and the audits here report consistency
findings that need human judgment (see any audit skill's "documented exception"
sections), not pass/fail facts. Exit is always 0, including when an audit crashes:
a broken hook must not become a broken editor.

SCOPE IS MANDATORY, not a nicety. `mock_api_reminders.py` established the rule —
it audits the single contract that changed, because the full multi-contract sweep
belongs to CI, which runs once per push rather than once per keystroke. An entry
that shells out to a whole-repo audit on every Write re-runs CI's work on a far
tighter loop for no added signal. `scopeArg` is how an entry passes the changed
path down; an entry without one must set `wholeRepo: true` and say why, so the
cost is a decision someone made rather than an oversight.

## Other harnesses

`--harness <name>` (written by `design-suite hooks --harness X` into that
harness's hook config) selects an input/output adapter in harness_output.py.
The logic here is unchanged; only the payload is normalised on the way in and
the message formatted on the way out. No flag means `claude`, and the claude
path is the original code, byte for byte. For harnesses whose after-edit hook
cannot feed the model (Cursor `afterFileEdit`, Devin Desktop) findings go to
`.design-suite/hook-reports/` and stderr, and the message says the model did
not see them — the one place this hook writes, and only into an existing
`.design-suite/`.

Stdlib only, like every other script in this suite.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MARKER = ".design-suite"
MAP_FILE = f"{MARKER}/hooks.map.json"

# Matches mock_api_reminders.py's ceiling. An audit slower than this on a single
# changed file is mis-scoped, and the right fix is the entry, not a longer wait.
TIMEOUT_SECONDS = 30

# Set once by run(): which harness adapter formats output, and (for file-sink
# harnesses) which project to write the report into.
HARNESS = "claude"
_REPO: Path | None = None


def _shared(module: str):
    """Import a design_suite module from this plugin's own root.

    The hooks used to inline copies of project-root resolution and the scaffold
    placeholder test on the belief that nothing shared was importable from
    ${CLAUDE_PLUGIN_ROOT}/hooks/. That holds for bin/ (scripts, not a package)
    but not for design_suite/: the installed plugin cache ships it beside
    hooks/, one directory up from this file. Imported lazily, inside the call:
    a failure here raises into run(), which reports it once per session and
    still exits 0 — never a crashed edit, and never a silent fallback to a
    resolution that might answer differently.
    """
    import importlib
    plugin_root = str(Path(__file__).resolve().parents[1])
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    return importlib.import_module(module)


def project_root(start: Path | None = None) -> Path | None:
    """The repository being audited — never the plugin's own directory.

    design_suite.project.locate(): the engine's own resolution, with "not
    found" as None rather than exit 2, because a hook must not fail the edit.
    """
    return _shared("design_suite.project").locate(start)


def _is_placeholder(entry: dict) -> bool:
    return _shared("design_suite.scaffold").entry_is_placeholder(entry)


INIT_CMD = 'python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py"'
DOCTOR_CMD = 'python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"'




def load_map(repo: Path) -> tuple[list[dict], str | None, str | None]:
    """(live entries, unconfigured-state key, notice) for this project's map.

    Five states, and only one of them is silence that means something:

      absent map              -> "no-map"       say so (once per session)
      malformed JSON          -> "malformed"    say so
      empty / all disabled    -> "inert"        say so
      placeholder-only        -> "placeholder"  say so
      configured              -> None           entries returned; a non-match
                                                is correct silence

    Wording follows doctor.py's check_hooks_map_configured on purpose, so the
    hook and doctor describe the same state in the same words.
    """
    path = repo / MAP_FILE
    if not path.is_file():
        return [], "no-map", (
            f"design-suite: no {MAP_FILE} — nothing runs on save, and nothing says "
            f"so. An absent map is a legitimate choice, but it is not the same as a "
            f"project whose on-save audits are clean. Set one up with: "
            f"{INIT_CMD} --only hooks.map.json (then {DOCTOR_CMD} to check it).")
    try:
        data = json.loads(path.read_text())
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("'entries' is not a list")
    except (OSError, ValueError, AttributeError) as exc:
        return [], "malformed", (
            f"design-suite: {MAP_FILE} could not be read ({exc}) — no audits ran on "
            f"save. Fix the file, then check it with {DOCTOR_CMD}.")
    live = [e for e in entries if isinstance(e, dict) and not e.get("disabled")]
    if not live:
        which = "empty" if not entries else "every entry disabled"
        return [], "inert", (
            f"design-suite: hooks.map.json is registered but inert ({which}) — "
            f"audit_on_edit.py runs nothing on save and reports nothing, which is "
            f"indistinguishable from every audit passing. Add an entry (see "
            f"{DOCTOR_CMD} for a working one to copy).")
    if all(_is_placeholder(e) for e in live):
        names = ", ".join(repr(e.get("name", "?")) for e in live)
        return [], "placeholder", (
            f"design-suite: every live hooks.map.json entry is still scaffold text "
            f"({names}) — a TODO glob matches no file, so the hook fires on nothing "
            f"and stays silent, which reads exactly like a clean project. Run "
            f"{DOCTOR_CMD} for the fix.")
    return live, None, None


def load_entries(repo: Path) -> list[dict]:
    """Live entries only — kept for callers that do not care about state."""
    return load_map(repo)[0]


# --- once-per-session notices ---------------------------------------------
#
# PostToolUse fires on every edit, so an unconfigured notice must be said once
# per session, not once per save. The memory lives in the OS temp directory,
# never the project tree: a marker in .design-suite/ would be litter in the
# user's repo (and in the no-.design-suite case there is nowhere to put it).
# Markers are zero-byte files keyed by a hash of (session_id, project, state),
# so a new session — or a state change, e.g. map added but still empty — says
# it again. Markers older than a week are pruned on each write, so the
# directory stays bounded without a cleanup job. DESIGN_SUITE_HOOK_STATE_DIR
# overrides the location (tests use it).
MARKER_TTL_SECONDS = 7 * 24 * 3600


def _state_dir() -> Path:
    override = os.environ.get("DESIGN_SUITE_HOOK_STATE_DIR")
    return Path(override) if override else Path(tempfile.gettempdir()) / "design-suite-hook-notices"


def first_time_this_session(session: str, repo: Path, key: str) -> bool:
    """True exactly once per (session, project, key). Fails open: if the marker
    cannot be written, the notice is shown (repeat beats silence)."""
    digest = hashlib.sha256(f"{session}\0{repo}\0{key}".encode()).hexdigest()[:24]
    d = _state_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in d.glob("*.seen"):
            try:
                if now - old.stat().st_mtime > MARKER_TTL_SECONDS:
                    old.unlink()
            except OSError:
                pass
        fd = os.open(d / f"{digest}.seen", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def session_key(data: dict) -> str:
    # Claude Code passes session_id on every hook's stdin. The parent pid is a
    # fallback only — it is the harness process, so it is still session-scoped.
    return str(data.get("session_id") or f"ppid-{os.getppid()}")


def emit(message: str, to_claude: bool = False) -> None:
    """PostToolUse output contract: JSON on stdout with exit 0.

    `systemMessage` is shown to the user. `hookSpecificOutput.additionalContext`
    is added to Claude's context — used for notices, because Claude is the one
    making the edits and should know the audits are not running.
    """
    if HARNESS != "claude":
        _adapter().after_edit(HARNESS, message, to_claude, _REPO)
        return
    out: dict = {"systemMessage": message}
    if to_claude:
        out["hookSpecificOutput"] = {"hookEventName": "PostToolUse",
                                     "additionalContext": message}
    print(json.dumps(out))


def _adapter():
    """harness_output.py, imported lazily so a broken sibling cannot take the
    claude path down with it."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import harness_output
    return harness_output


def relative_to_repo(file_path: str, repo: Path) -> str | None:
    if not file_path:
        return None
    try:
        return str(Path(file_path).resolve().relative_to(repo.resolve()))
    except ValueError:
        # Outside the project entirely — another repo, a temp file, a dotfile in
        # $HOME. Not ours to audit.
        return None


def matches(entry: dict, tool: str, rel: str | None, command: str) -> bool:
    """Whether this entry wants to fire for what just happened.

    Two trigger shapes, because the two existing hooks have two shapes: a file
    glob (mock_api_reminders) and a command pattern (pr_reminders). Supporting
    only the first would have left pr_reminders unable to migrate.
    """
    globs = entry.get("glob")
    if globs:
        if tool not in ("Write", "Edit", "NotebookEdit") or rel is None:
            return False
        patterns = [globs] if isinstance(globs, str) else globs
        return any(fnmatch.fnmatch(rel, p) for p in patterns)

    pattern = entry.get("commandPattern")
    if pattern:
        if tool != "Bash":
            return False
        try:
            return re.search(pattern, command) is not None
        except re.error:
            return False

    return False


def _disabled_audit(command) -> tuple[str, dict] | None:
    """Ask the one registry whether this entry's command is switched off.

    Imported lazily and defensively. This file ships to ${CLAUDE_PLUGIN_ROOT}/hooks/
    and must survive being run from anywhere, so a failed import degrades to "not
    disabled" — the entry then runs and reports its own refusal, which is worse
    reporting but still never a false clean.
    """
    try:
        plugin_root = Path(__file__).resolve().parents[1]
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from design_suite.engine import audit_discovery
    except ImportError:
        return None
    return audit_discovery.disabled_in_command(command)


def run_entry(entry: dict, repo: Path, rel: str | None) -> str | None:
    """Run one entry's command and return what to tell the user, if anything."""
    command = entry.get("command")
    if not command:
        return None

    # A disabled audit is named, never run, and never silent. Running it would
    # produce exit 2 with a stderr wall on every save, and this hook would report
    # it as "found something" — a nudge to fix code that is fine, from a check
    # that has been switched off. Saying so once per trigger, in the entry's own
    # words, is the only honest option: staying quiet would leave the project
    # believing an audit is watching its edits when nothing is.
    if (hit := _disabled_audit(command)) is not None:
        audit, reason = hit
        return (f"{entry.get('name', '?')}: NOT RUN — {audit} is disabled. "
                f"{reason['reason']}. Nothing was checked, so this is not a clean "
                f"result. Remove the entry from {MAP_FILE}, or see the path back in "
                f"design_suite/engine/audit_discovery.DISABLED.")

    if isinstance(command, str):
        argv = command.split()
    else:
        argv = list(command)

    scope_arg = entry.get("scopeArg")
    if scope_arg and rel:
        # Every audit in bin/ takes `--dir`, not a file path — none of them can
        # audit a single file. So the useful narrow scope is the changed file's
        # containing directory, and an entry that assumed otherwise would fail on
        # `no such directory` for every edit.
        scope = rel if entry.get("scopeMode", "file") == "file" else str(Path(rel).parent)
        if scope_arg is not True:
            argv.append(str(scope_arg))
        argv.append(scope)
    elif not scope_arg and not entry.get("wholeRepo"):
        return (f"hooks.map entry '{entry.get('name', '?')}' has neither scopeArg nor "
                f"wholeRepo — refusing to run it repo-wide by accident. See "
                f"{MAP_FILE}.")

    argv = [os.path.expandvars(a) for a in argv]

    try:
        result = subprocess.run(
            argv, cwd=repo, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (f"'{entry.get('name', argv[0])}' exceeded {TIMEOUT_SECONDS}s and was stopped. "
                f"An audit this slow on one changed file is mis-scoped — narrow the entry.")
    except (OSError, ValueError) as exc:
        return f"'{entry.get('name', argv[0])}' could not run: {exc}"

    name = entry.get("name", argv[0])
    output = (result.stdout or "").strip()
    fix = entry.get("fixHint")

    # Two signals, because the audits genuinely have two behaviours. The copy gate
    # exits non-zero on a new violation — that is what makes it a gate. audit_tokens
    # exits 0 whether it found 144 things or none, because hardcoded values are a
    # consistency report rather than a build failure. An entry pointed at the second
    # kind with the default signal would report nothing forever, which is
    # indistinguishable from a clean codebase — the exact failure this suite keeps
    # designing against.
    if entry.get("reportWhen") == "findings":
        findings_path = entry.get("findingsPath")
        if not findings_path:
            return (f"hooks.map entry {name!r} sets reportWhen 'findings' but no "
                    f"findingsPath — there is nothing to read.")
        try:
            envelope = json.loads((repo / findings_path).read_text())
            records = envelope.get("findings", [])
        except (OSError, ValueError):
            return None
        if not records:
            return f"{name}: clean." if entry.get("reportClean") else None

        preview = "\n".join(
            f"  {r.get('file', '?')}:{r.get('line', '?')} — {r.get('category', '?')}"
            for r in records[:3]
        )
        more = f"\n  …and {len(records) - 3} more" if len(records) > 3 else ""
        message = (f"{name}: {len(records)} finding(s) in the directory "
                   f"{rel or 'that changed'} sits in.\n{preview}{more}")
        return message + (f"\nSee: {fix}" if fix else "")

    if result.returncode == 0:
        # Clean runs stay quiet unless the entry asks otherwise. A confirmation on
        # every save is noise that trains people to stop reading these.
        if entry.get("reportClean"):
            return f"{name}: clean."
        return None

    detail = output or (result.stderr or "").strip() or f"exit {result.returncode}"
    message = f"{name} found something after {rel or 'that command'}:\n{detail}"
    if fix:
        message += f"\nFix with: {fix}"
    return message


def main(data: dict) -> int:
    global _REPO
    start = None
    if HARNESS != "claude":
        start = _adapter().start_dir(HARNESS, data)
        data = _adapter().normalize(HARNESS, data)
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    command = tool_input.get("command", "") or ""
    session = session_key(data)

    repo = project_root(start)
    _REPO = repo
    if repo is None:
        # No .design-suite/ anywhere. Not silent: an installed suite that is
        # auditing nothing must not look like one that found nothing.
        where = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
        if first_time_this_session(session, where, "no-design-suite"):
            emit(f"design-suite: no {MARKER}/ in this project — the suite is installed "
                 f"but no on-save audits are configured, so nothing is checked on edit "
                 f"(this is not a clean result). Set it up with: {INIT_CMD}",
                 to_claude=True)
        return 0

    rel = relative_to_repo(file_path, repo)
    entries, state, notice = load_map(repo)
    if state is not None:
        if first_time_this_session(session, repo, state):
            emit(notice, to_claude=True)
        return 0

    messages = []
    for entry in entries:
        if not matches(entry, tool, rel, command):
            continue
        message = run_entry(entry, repo, rel)
        if message:
            messages.append(message)

    # A configured map with no matching entry is correct silence.
    if messages:
        emit("\n\n".join(messages))
    return 0


def run(stdin_text: str) -> int:
    """Entry point. Always returns 0 — a hook failure must never fail the edit —
    but an internal failure is said once per session, never passed off as clean."""
    try:
        data = json.loads(stdin_text)
        if not isinstance(data, dict):
            return 0
    except Exception:
        return 0
    try:
        return main(data)
    except Exception as exc:  # noqa: BLE001 — the whole point is to catch all
        try:
            root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
            if first_time_this_session(session_key(data), root, "internal-error"):
                emit(f"design-suite: audit_on_edit.py failed internally "
                     f"({type(exc).__name__}: {exc}) — mapped audits did not run, so "
                     f"silence after this edit is not a clean result. The edit itself "
                     f"was not affected.", to_claude=True)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Only touch the adapter module when a flag was given: the bare
        # invocation (the plugin's hooks.json) stays the original code path.
        try:
            HARNESS = _adapter().parse_harness(sys.argv[1:])
        except Exception as exc:  # noqa: BLE001 — unknown adapter is a hard error
            print(f"design-suite audit_on_edit.py: {exc}. The hook config is wrong; "
                  f"no audits ran on this edit.", file=sys.stderr)
            sys.exit(1)
    try:
        sys.exit(run(sys.stdin.read()))
    except Exception:
        sys.exit(0)
