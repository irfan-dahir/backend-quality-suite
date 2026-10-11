#!/usr/bin/env python3
"""Tests for doctor.py's check_fix_hints_are_safe (issue F2's consumer-side half).

audit_safe_repairers.py vets what the PLUGIN recommends as a fix. A project's
own `.design-suite/hooks.map.json` can recommend a fix too — `fixHint` (shown to
a human) and `repair.command` (actually EXECUTED at commit time by
run_precommit_audits.py) — and nothing was checking those before this. This is
the same "reports nothing but looks like a pass" trap one layer down: a project
could write `fixHint: "some-destructive-script.sh"` and doctor would say
"profile healthy".

Paired assertions, per CLAUDE.md: an unlisted fixHint must be flagged, and an
allowlisted one (or a plain diagnostic instruction with nothing script-shaped
in it) must not be — otherwise a "healthy" run after this change could mean
either "checked and clean" or "the check silently does nothing", which is
exactly the ambiguity the whole suite exists to forbid.

    python3 plugins/design-suite/bin/doctor_fix_hints_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
DOCTOR = BIN / "doctor.py"
SCHEMA = BIN.parent / "templates" / "profile.schema.json"
FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


BASE_PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture", "framework": "none"},
    "adapters": {"lang": "dart"},
    "source": {"root": "lib", "fileGlob": "**/*.dart"},
    "tokens": {"source": {"kind": "file", "path": "lib/tokens.dart"},
               "accessor": "AppTokens"},
    "docs": {"manifest": ".design-suite/docs.manifest.json"},
}


def fixture(tmp: Path, hooks_map: dict) -> Path:
    """A project healthy in every respect except the hooks.map.json it is given.

    Provenance is deliberately left unattributed — this test is about
    fixHint/repair.command, not about the provenance gate, and doctor already
    treats an unratified field as UNTRUSTED rather than a hard failure, so it
    does not interfere with reading the exit code for THIS check.
    """
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "lib" / "tokens.dart").touch()
    (root / ".design-suite" / "docs.manifest.json").write_text(json.dumps({"roles": {}}))
    (root / ".design-suite" / "profile.schema.json").write_text(SCHEMA.read_text())
    (root / ".design-suite" / "profile.json").write_text(json.dumps(BASE_PROFILE, indent=2))
    (root / ".design-suite" / "hooks.map.json").write_text(json.dumps(hooks_map))
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return root


def run(hooks_map: dict) -> subprocess.CompletedProcess:
    tmp = Path(tempfile.mkdtemp())
    root = fixture(tmp, hooks_map)
    return subprocess.run([sys.executable, str(DOCTOR)], cwd=root,
                          capture_output=True, text=True)


def main() -> int:
    print("check: an unvetted fixHint is flagged")
    out = run({"entries": [
        {"name": "bad-fix", "glob": "*.dart", "command": ["echo", "hi"],
         "fixHint": "some-destructive-script.sh --apply"},
    ]})
    expect(out.returncode == 1, "doctor exits 1 on an unvetted fixHint")
    expect("some-destructive-script.sh" in out.stdout,
           "the offending script is named in the output")
    expect("bad-fix" in out.stdout, "the offending entry name is named too")

    print("check: an unvetted repair.command is flagged, and named as executing")
    out = run({"entries": [
        {"name": "bad-repair", "glob": "*.dart", "command": ["echo", "hi"],
         "repair": {"command": ["some-destructive-script.sh"],
                    "filesArg": "--files"}},
    ]})
    expect(out.returncode == 1, "doctor exits 1 on an unvetted repair.command")
    expect("COMMIT TIME" in out.stdout,
           "the report distinguishes a live-execution repair from an advisory "
           "fixHint")

    print("check: a fixHint naming a vetted plugin script is NOT flagged")
    out = run({"entries": [
        {"name": "good-fix", "glob": "*.dart", "command": ["echo", "hi"],
         "fixHint": "${CLAUDE_PLUGIN_ROOT}/bin/generate_openapi.py"},
    ]})
    expect(out.returncode == 0,
           "doctor exits 0 when the fixHint names an allowlisted script")
    expect("safe-repairers allowlist" not in out.stdout,
           "no fixHint safety problem is reported")

    print("check: a fixHint with nothing script-shaped in it is left alone")
    out = run({"entries": [
        {"name": "plain-note", "glob": "*.dart", "command": ["echo", "hi"],
         "fixHint": "ask a human to look at this"},
    ]})
    expect(out.returncode == 0,
           "doctor exits 0 when fixHint names no script or skill at all")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("doctor_fix_hints_test: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
