#!/usr/bin/env python3
"""PostToolUse check (Write|Edit): when a Dart data model or fixture
registered in mock_api/contracts.json is touched (or contracts.json
itself), run audit_mock_api.py for JUST that one contract and surface the
real pass/fail — not a static reminder — so the project's API document (role `api`) and the Postman
mock don't silently drift from the code (the failure this whole pipeline
exists to catch; see the mock-API integration plan).

Also *checks* mock_api/openapi.json (the Redoc-rendered spec — see
the decision log's (role `decisions`) "OpenAPI spec + Redoc doc page" entry) on the
same trigger, via `generate_openapi.py --check`. It reports drift and never
writes: this hook is `auto` tier and fires on every edit, and it has already
rewritten that tracked file and lost content once.

Deliberately scoped to the single contract that changed, not the full
sweep — the full multi-contract audit belongs to CI
(.github/workflows/flutter-test.yml), which runs once per push/PR. Running
that here on every Edit would duplicate the same work on a much tighter
loop for no benefit; this hook exists for instant, narrow feedback. The
spec check is repo-wide regardless (it's one combined document), but it's
cheap — a handful of JSON reads and no write at all.

Nothing here blocks and nothing here writes — even on a real finding, this
only surfaces it. It also names no repair: a drift finding says two sides
disagree, not which one is right, and the propagation script it used to
recommend deletes whatever the fixture has lost (issue #116).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MARKER = ".backend-suite"

# Two roots, and conflating them is what stopped this hook working. `parents[2]`
# resolved to the plugin's own `plugins/` directory, so CONTRACTS_FILE pointed at
# `<plugin>/plugins/mock_api/contracts.json`, which does not exist — and the
# `if not CONTRACTS_FILE.is_file(): return 0` guard below turned that into a
# silent no-op on every single edit. The hook was registered, appeared to be
# working, and had never once run its audit. This is the exact failure
# bin/_bootstrap.py was written to prevent; that helper cannot be imported from
# here (bin/ is not on the path in ${CLAUDE_PLUGIN_ROOT}/hooks/), but the
# backend_suite package beside it is, so the resolution is the shared one.
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _shared(module: str):
    """Import a backend_suite module from this plugin's own root.

    The hooks used to inline copies of project-root resolution and the scaffold
    placeholder test on the belief that nothing shared was importable from
    ${CLAUDE_PLUGIN_ROOT}/hooks/. That holds for bin/ (scripts, not a package)
    but not for backend_suite/: the installed plugin cache ships it beside
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


def _project_root() -> Path | None:
    """backend_suite.project.locate() — the engine's resolution, None if unfound."""
    return _shared("backend_suite.project").locate()


def _mock_api_dir(repo: Path, profile: dict) -> Path:
    """The project's mock-API directory, from `pipelines.mockApi` in its profile.

    This used to be the literal `"mock_api"`, which made the hook silently
    correct on exactly one project's layout: anywhere else `CONTRACTS_FILE` did
    not exist and the `is_file()` guard below turned the whole hook into a no-op
    — the same shape as the `parents[2]` bug documented above, and just as
    invisible. The plugin root is already resolved, so the shared resolver is
    importable from here even though `bin/_bootstrap` is not.

    Resolved per call, not at import time: an import-time failure (a malformed
    profile) used to escape every guard and fail the hook with a traceback.
    """
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    from backend_suite.engine import pipelines  # noqa: E402
    return pipelines.resolve(repo, profile, "mockApi")


def _load_profile(repo: Path) -> dict:
    profile = repo / MARKER / "profile.json"
    return json.loads(profile.read_text()) if profile.is_file() else {}


# --- once-per-session notices ---------------------------------------------
# Same mechanism as audit_on_edit.py (inlined — hooks cannot share bin/):
# zero-byte markers in the OS temp dir keyed by (session, project, state),
# never in the project tree, pruned after a week.
MARKER_TTL_SECONDS = 7 * 24 * 3600


def _state_dir() -> Path:
    override = os.environ.get("BACKEND_SUITE_HOOK_STATE_DIR")
    return Path(override) if override else Path(tempfile.gettempdir()) / "backend-suite-hook-notices"


def first_time_this_session(session: str, repo: Path, key: str) -> bool:
    digest = hashlib.sha256(f"mock-api\0{session}\0{repo}\0{key}".encode()).hexdigest()[:24]
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
        return True  # fail open: a repeated notice beats a lost one


def _session_key(data: dict) -> str:
    return str(data.get("session_id") or f"ppid-{os.getppid()}")


def _emit(message: str, to_claude: bool = False) -> None:
    """PostToolUse contract: JSON on stdout, exit 0. systemMessage -> user;
    hookSpecificOutput.additionalContext -> Claude."""
    out: dict = {"systemMessage": message}
    if to_claude:
        out["hookSpecificOutput"] = {"hookEventName": "PostToolUse",
                                     "additionalContext": message}
    print(json.dumps(out))


# The engines moved into the plugin when the four mock-API engines were ported out
# of the project repos; `mock_api/scripts/` in the project no longer holds either
# of these. Pointing at the project's copy is the second half of the same bug —
# it would have failed even with REPO resolved correctly.
AUDIT_SCRIPT = PLUGIN_ROOT / "backend_suite" / "engine" / "mockapi" / "audit_mock_api.py"
GENERATE_OPENAPI_SCRIPT = PLUGIN_ROOT / "backend_suite" / "engine" / "mockapi" / "generate_openapi.py"


def _find_contract_for(rel: str, contracts: dict) -> str | None:
    for name, contract in contracts.items():
        if name.startswith("_"):
            continue
        if contract.get("model_file") == rel or contract.get("fixture") == rel:
            return name
    return None


def main(data: dict) -> int:
    if data.get("tool_name") not in ("Write", "Edit"):
        return 0

    file_path = (data.get("tool_input", {}) or {}).get("file_path", "") or ""
    if not file_path:
        return 0

    repo = _project_root()
    if repo is None:
        # No .backend-suite/ at all. audit_on_edit.py announces that state once
        # per session; saying it here too would be the same notice twice.
        return 0

    try:
        rel = str(Path(file_path).resolve().relative_to(repo.resolve()))
    except ValueError:
        # Outside the project — another repo, a temp file. Not ours.
        return 0

    session = _session_key(data)
    profile = _load_profile(repo)
    contracts_file = _mock_api_dir(repo, profile) / "contracts.json"

    if not contracts_file.is_file():
        # Silent ONLY when the project never claimed a mock API. Many projects
        # have none, and the conventional default directory being absent is
        # then the correct state. But a profile that declares
        # pipelines.mockApi has said "audit my contracts" — its missing
        # registry means no edit is being checked, and that must be said.
        declared = (profile.get("pipelines", {}) or {}).get("mockApi")
        if declared and first_time_this_session(session, repo, "no-contracts"):
            _emit(f"backend-suite: profile.json declares pipelines.mockApi "
                  f"'{declared}', but {contracts_file.relative_to(repo)} does not "
                  f"exist — no mock-API contract is checked on edit, which is not "
                  f"the same as in sync. Register contracts there (see /wire-endpoint), "
                  f"or remove pipelines.mockApi if this project has no mock API.",
                  to_claude=True)
        return 0
    try:
        contracts = json.loads(contracts_file.read_text())
        if not isinstance(contracts, dict):
            raise ValueError("top level is not an object")
    except (OSError, ValueError) as exc:
        if first_time_this_session(session, repo, "malformed-contracts"):
            _emit(f"backend-suite: {contracts_file.relative_to(repo)} could not be "
                  f"read ({exc}) — no mock-API contract was checked.", to_claude=True)
        return 0

    is_contracts_file = rel == str(contracts_file.relative_to(repo))
    contract_name = None if is_contracts_file else _find_contract_for(rel, contracts)

    if contract_name is None and not is_contracts_file:
        # Registry present, this file is not in it: correct silence.
        return 0

    messages = []

    if contract_name is not None:
        # --out redirected to scratch, and this matters. It defaults to
        # .backend-suite/mock-api-findings.json, the whole-repo report: a
        # single-contract run writes only that contract's findings there, deleting
        # every other contract's. A narrow audit must never overwrite the file the
        # full sweep owns.
        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), contract_name,
             "--out", ".backend-suite/scratch/hook-mock-api.json"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            messages.append(f"'{contract_name}' contract: mock/doc/fixture still in sync.")
        else:
            # Name the finding, never a fix. This message lands in an agent's
            # edit loop, which is the highest-fix-rate channel in the suite — a
            # repair command printed here gets run almost every time. The drift
            # this audit reports is a disagreement between two sides, and the
            # one-way sync that used to be named here propagates fixture ->
            # mock/doc unconditionally: where the fixture was the rotted side it
            # DELETED correct data (issue #116). The findings already say what
            # differs and show both sides; the decision of which side is
            # authoritative belongs to the reader. Do not re-add a command.
            messages.append(
                f"'{contract_name}' contract drifted after editing {rel}:\n"
                f"{result.stdout.strip()}\n"
                "Read each finding and correct whichever side is out of date — "
                "these findings report a difference, not a direction."
            )

    # `--check`: report, never write. This used to regenerate and WRITE the spec
    # on every edit, justified by the derivation being pure — and the comment
    # that justified it also recorded that the purity assumption had already
    # failed once, when the first working run of this hook rewrote the committed
    # spec and LOST the curated per-code error examples. An `auto`-tier hook
    # firing on every Write/Edit is the wrong place to bet a tracked file on that
    # assumption holding: the blast radius of being wrong is a silent content
    # loss inside an unrelated edit, which is precisely the class of damage
    # issue #116 is about. Reporting costs the reader one line and cannot delete
    # anything; writing is `generate_openapi.py` run deliberately, by a human or
    # an explicit skill.
    #
    # Repo-wide rather than scoped, unlike the audit above, and that stays
    # correct: the spec is one combined document, not per-contract.
    spec_result = subprocess.run(
        [sys.executable, str(GENERATE_OPENAPI_SCRIPT), "--check"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    spec_line = spec_result.stdout.strip()
    if spec_line:
        if spec_result.returncode != 0:
            spec_line += (
                "\nRegenerate it deliberately with generate_openapi.py "
                "(this hook only reports; it does not write)."
            )
        messages.append(spec_line)

    if not messages:
        return 0

    print(json.dumps({"systemMessage": "\n".join(messages)}))
    return 0


def run(stdin_text: str) -> int:
    """Always 0 — a hook failure must never fail the edit — but an internal
    failure (a crash, a timed-out audit) is said once per session rather than
    left to read as "in sync"."""
    try:
        data = json.loads(stdin_text)
        if not isinstance(data, dict):
            return 0
    except Exception:
        return 0
    try:
        return main(data)
    except Exception as exc:  # noqa: BLE001
        try:
            root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
            if first_time_this_session(_session_key(data), root, "internal-error"):
                _emit(f"backend-suite: mock_api_reminders.py failed internally "
                      f"({type(exc).__name__}: {exc}) — the mock-API contract check "
                      f"did not run, so silence is not \"in sync\". The edit itself "
                      f"was not affected.", to_claude=True)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.stdin.read()))
    except Exception:
        sys.exit(0)
