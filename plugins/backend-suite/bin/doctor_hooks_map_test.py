#!/usr/bin/env python3
"""Tests for doctor.py's check_hooks_map_configured.

The measured bug: `templates/dot-backend-suite/hooks.map.json.template` shipped a
single TODO-shaped entry — name, glob and all. `init.py` substitutes only
{{PROJECT_NAME}}, so that TODO glob landed in the consuming project verbatim,
matched no file anyone ever saved, and `audit_on_edit.py` therefore ran nothing,
for ever, without complaint. The project had a hooks map on disk, believed its
edits were audited, and got the same silence a clean codebase produces. Nothing
reported it — which is this repo's governing failure with the suite's own
scaffold as the subject.

Paired assertions, per CLAUDE.md: a placeholder-only map must be flagged AND a
genuinely configured one must not be. Without the control case, a "healthy" run
after this change could mean either "checked and configured" or "the check
silently does nothing" — the exact ambiguity being fixed.

The shipped template itself is asserted on too, in both directions: it must not
be placeholder-shaped any more, and doctor must accept it as-is. A test that
only used hand-written fixtures would keep passing if someone put the TODO entry
back.

    python3 plugins/backend-suite/bin/doctor_hooks_map_test.py

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
TEMPLATE = (BIN.parent / "templates" / "dot-backend-suite"
            / "hooks.map.json.template")
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
    "docs": {"manifest": ".backend-suite/docs.manifest.json"},
}

# A live, non-placeholder entry: exactly the shape the template now ships, with
# a command that is cheap and certain to exist so this test measures the hooks-map
# check rather than any audit's behaviour.
CONFIGURED = {
    "name": "Source audit (on save)",
    "glob": ["*.dart"],
    "command": ["echo", "hi"],
    "scopeMode": "dir",
    "scopeArg": "--dir",
    "preCommit": False,
}

# The scaffold entry as it used to ship, TODOs intact.
PLACEHOLDER = {
    "name": "TODO: what the user sees, e.g. 'Source audit'",
    "glob": "TODO: e.g. 'lib/**/*.dart'",
    "command": ["echo", "hi"],
    "scopeMode": "dir",
    "scopeArg": "--dir",
}


def fixture(tmp: Path, hooks_map: dict | None) -> Path:
    """A project healthy in every respect except the hooks map it is given.

    `hooks_map` of None writes no map at all — the absent case. Provenance is
    left unattributed deliberately: doctor reports an unratified field as
    UNTRUSTED rather than a failure, so it does not perturb the exit code this
    test reads.
    """
    root = tmp / "project"
    (root / ".backend-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "lib" / "main.dart").touch()
    (root / ".backend-suite" / "docs.manifest.json").write_text(json.dumps({"roles": {}}))
    (root / ".backend-suite" / "profile.schema.json").write_text(SCHEMA.read_text())
    (root / ".backend-suite" / "profile.json").write_text(json.dumps(BASE_PROFILE, indent=2))
    if hooks_map is not None:
        (root / ".backend-suite" / "hooks.map.json").write_text(json.dumps(hooks_map))
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return root


def run(hooks_map: dict | None) -> subprocess.CompletedProcess:
    tmp = Path(tempfile.mkdtemp())
    root = fixture(tmp, hooks_map)
    return subprocess.run([sys.executable, str(DOCTOR)], cwd=root,
                          capture_output=True, text=True)


def main() -> int:
    print("check: a placeholder-only map is caught")
    out = run({"entries": [PLACEHOLDER]})
    expect(out.returncode == 1, "doctor exits 1 on a scaffold-only hooks map")
    expect("scaffold text" in out.stdout,
           "the report says the entries are still scaffold text")
    expect("TODO: what the user sees" in out.stdout,
           "the offending entry is named, not just counted")

    print("check: a genuinely configured map is NOT flagged (the control)")
    out = run({"entries": [CONFIGURED]})
    expect(out.returncode == 0, "doctor exits 0 on a configured hooks map")
    expect("scaffold text" not in out.stdout and "inert" not in out.stdout,
           "no hooks-map problem is reported for a real entry")

    print("check: one real entry beside a placeholder is enough")
    out = run({"entries": [PLACEHOLDER, CONFIGURED]})
    expect(out.returncode == 0,
           "a map that does something is not failed for also holding scaffold")

    print("check: an empty map is caught")
    out = run({"entries": []})
    expect(out.returncode == 1, "doctor exits 1 on an empty entries list")
    expect("inert" in out.stdout, "the report names the map as inert")

    print("check: an all-disabled map is caught, and named as disabled")
    out = run({"entries": [dict(CONFIGURED, disabled=True)]})
    expect(out.returncode == 1, "doctor exits 1 when every entry is disabled")
    expect("every entry disabled" in out.stdout,
           "the report distinguishes all-disabled from empty")

    print("check: an absent map is reported rather than passed over")
    out = run(None)
    expect(out.returncode == 1, "doctor exits 1 when there is no hooks map")
    expect("nothing runs on save" in out.stdout,
           "the report says plainly that nothing runs, rather than staying quiet")

    print("check: the SHIPPED template is live, not scaffold")
    shipped = json.loads(TEMPLATE.read_text())
    out = run(shipped)
    expect(out.returncode == 0,
           "doctor accepts the template this suite scaffolds into new projects")
    entries = [e for e in shipped.get("entries", []) if not e.get("disabled")]
    expect(bool(entries), "the template ships at least one live entry")
    expect(not any("TODO" in json.dumps(e) for e in entries),
           "no live template entry still contains a TODO")
    expect(not any(e.get("preCommit") for e in entries),
           "nothing in the template gates a commit by default")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("doctor_hooks_map_test: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
