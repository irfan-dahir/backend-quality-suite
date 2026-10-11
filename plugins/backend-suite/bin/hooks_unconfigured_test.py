#!/usr/bin/env python3
"""Tests: the PostToolUse hooks say when they are unconfigured — once per session.

A hook that does nothing because it is unconfigured must not look like a hook
that ran and found nothing. But PostToolUse fires on every edit, so the notice
must appear once per session, not per save. Covered here, against synthetic
projects in temp dirs, run as real subprocesses with real stdin:

  audit_on_edit.py
    no .backend-suite/          -> one notice
    .backend-suite/, no map     -> one notice
    empty / placeholder map    -> one notice
    configured, no match       -> silent (correct silence)
    second edit, same session  -> silent; new session -> notice again
    internal exception         -> exit 0, one notice naming the failure
  mock_api_reminders.py
    no pipelines.mockApi, no contracts -> silent
    declared but missing contracts     -> one notice
    malformed profile (used to crash at import) -> exit 0
  both: nothing written into the project tree.

    python3 plugins/backend-suite/bin/hooks_unconfigured_test.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
AUDIT = HOOKS / "audit_on_edit.py"
MOCK = HOOKS / "mock_api_reminders.py"
FAILURES: list[str] = []


def expect(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        FAILURES.append(what)


def snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def run(hook: Path, project: Path, state: Path, session: str = "s1",
        file: str = "lib/a.dart", extra_env: dict | None = None) -> tuple[int, list[dict]]:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update({"CLAUDE_PROJECT_DIR": str(project),
                "DESIGN_SUITE_HOOK_STATE_DIR": str(state)})
    env.update(extra_env or {})
    payload = {"session_id": session, "tool_name": "Edit",
               "tool_input": {"file_path": str(project / file)}}
    r = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=project, env=env, timeout=60)
    msgs = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    return r.returncode, msgs


def project(tmp: Path, name: str, map_data=None, backend_suite=True, profile=None) -> Path:
    p = tmp / name
    (p / "lib").mkdir(parents=True)
    (p / "lib" / "a.dart").write_text("// x\n")
    if backend_suite:
        (p / ".backend-suite").mkdir()
        if map_data is not None:
            (p / ".backend-suite" / "hooks.map.json").write_text(json.dumps(map_data))
        if profile is not None:
            (p / ".backend-suite" / "profile.json").write_text(
                profile if isinstance(profile, str) else json.dumps(profile))
    return p


def once(hook: Path, proj: Path, state: Path, label: str, needle: str) -> None:
    before = snapshot(proj)
    code, msgs = run(hook, proj, state)
    expect(code == 0, f"{label}: exit 0")
    expect(len(msgs) == 1 and needle in msgs[0].get("systemMessage", ""),
           f"{label}: one notice mentioning {needle!r} (got {msgs})")
    expect(bool(msgs) and "additionalContext" in msgs[0].get("hookSpecificOutput", {}),
           f"{label}: notice also reaches Claude via additionalContext")
    code, msgs = run(hook, proj, state)
    expect(code == 0 and msgs == [], f"{label}: second edit same session is silent")
    code, msgs = run(hook, proj, state, session="s2")
    expect(len(msgs) == 1, f"{label}: a new session hears it again")
    expect(snapshot(proj) == before, f"{label}: nothing written into the project tree")


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        state = tmp / "_state"

        print("audit_on_edit.py")
        once(AUDIT, project(tmp, "bare", backend_suite=False), state,
             "no .backend-suite", "no .backend-suite/")
        once(AUDIT, project(tmp, "nomap"), state, "no map", "no .backend-suite/hooks.map.json")
        once(AUDIT, project(tmp, "empty", {"entries": []}), state, "empty map", "inert (empty)")
        once(AUDIT, project(tmp, "disabled", {"entries": [{"name": "x", "glob": "lib/**",
             "command": "true", "scopeArg": True, "disabled": True}]}), state,
             "all-disabled map", "every entry disabled")
        once(AUDIT, project(tmp, "todo", {"entries": [{"name": "TODO", "glob": "TODO: e.g. 'lib/**'",
             "command": "true", "scopeArg": True}]}), state, "placeholder map", "scaffold text")
        badjson = project(tmp, "badjson")
        (badjson / ".backend-suite" / "hooks.map.json").write_text("{nope")
        once(AUDIT, badjson, state, "malformed map", "could not be read")

        configured = project(tmp, "configured", {"entries": [{"name": "real",
            "glob": "docs/**", "command": "false", "wholeRepo": True}]})
        before = snapshot(configured)
        code, msgs = run(AUDIT, configured, state)
        expect(code == 0 and msgs == [], "configured map, no matching entry: silent")
        expect(snapshot(configured) == before, "configured: nothing written into the tree")

        # Positive control: a matching entry still reports, so "silent" above
        # is the matcher deciding, not the hook being dead.
        firing = project(tmp, "firing", {"entries": [{"name": "real", "glob": "lib/**",
            "command": "false", "wholeRepo": True}]})
        code, msgs = run(AUDIT, firing, state)
        expect(code == 0 and len(msgs) == 1 and "real found something" in msgs[0]["systemMessage"],
               "configured map, matching entry: reports (control)")

        # Internal exception: a glob of the wrong type crashes `matches`.
        crash = project(tmp, "crash", {"entries": [{"name": "c", "glob": 42,
            "command": "true", "wholeRepo": True}]})
        code, msgs = run(AUDIT, crash, state)
        expect(code == 0, "internal exception: exit 0 (edit not failed)")
        expect(len(msgs) == 1 and "failed internally" in msgs[0]["systemMessage"],
               f"internal exception: said once ({msgs})")
        code, msgs = run(AUDIT, crash, state)
        expect(code == 0 and msgs == [], "internal exception: not repeated in session")

        print("mock_api_reminders.py")
        quiet = project(tmp, "m-quiet", {"entries": []})
        before = snapshot(quiet)
        code, msgs = run(MOCK, quiet, state)
        expect(code == 0 and msgs == [], "no mockApi declared, no contracts: silent")
        expect(snapshot(quiet) == before, "m-quiet: nothing written into the tree")
        once(MOCK, project(tmp, "m-declared", profile={"pipelines": {"mockApi": "api_mock"}}),
             state, "mockApi declared, contracts missing", "does not exist")
        code, msgs = run(MOCK, project(tmp, "m-none", backend_suite=False), state)
        expect(code == 0 and msgs == [], "no .backend-suite: silent (audit_on_edit owns it)")
        code, msgs = run(MOCK, project(tmp, "m-badprofile", profile="{nope"), state)
        expect(code == 0, "malformed profile: exit 0 (used to crash at import)")
        expect(len(msgs) == 1 and "failed internally" in msgs[0]["systemMessage"],
               "malformed profile: said, not silent")

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
