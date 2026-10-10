#!/usr/bin/env python3
"""Tests for doctor.py's per-field provenance enforcement (RFC-0002 §3b, §3h).

Paired assertions throughout, for the reason CLAUDE.md gives: a clean run proves
nothing, because a check that works and a check that no-ops both report zero. So
every case here plants a contradiction into an otherwise-healthy fixture and
asserts the exact finding, and the backward-compatibility cases assert that a
profile with NO provenance block still exits 0 *and still says so out loud*.

    python3 plugins/design-suite/bin/doctor_provenance_test.py

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


BASE = {
    "profileVersion": 1,
    "project": {"name": "Fixture", "framework": "none"},
    "adapters": {"lang": "dart"},
    "source": {"root": "lib", "fileGlob": "**/*.dart"},
    "tokens": {"source": {"kind": "file", "path": "lib/tokens.dart"},
               "accessor": "AppTokens"},
    "docs": {"manifest": ".design-suite/docs.manifest.json"},
}


def fixture(tmp: Path, provenance: dict | None) -> Path:
    """A project that is healthy in every respect except what a caller plants."""
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "lib" / "tokens.dart").touch()
    (root / ".design-suite" / "docs.manifest.json").write_text(json.dumps({"roles": {}}))
    (root / ".design-suite" / "profile.schema.json").write_text(SCHEMA.read_text())
    # A configured hooks map, because doctor now reports an absent/inert/scaffold
    # one as a finding (check_hooks_map_configured). These cases assert on the
    # PROVENANCE verdict via the exit code, so the fixture has to be healthy in
    # every other respect — an unrelated finding here would make "exits 0" mean
    # something this file never intended to measure. Its own check has its own
    # paired tests in doctor_hooks_map_test.py.
    (root / ".design-suite" / "hooks.map.json").write_text(json.dumps({
        "entries": [{"name": "fixture", "glob": ["*.dart"],
                     "command": ["echo", "hi"], "scopeArg": "--dir"}]
    }))
    profile = json.loads(json.dumps(BASE))
    if provenance is not None:
        profile["provenance"] = provenance
    (root / ".design-suite" / "profile.json").write_text(json.dumps(profile, indent=2))
    # A real repository, so verifiedAgainst.commit has something to resolve against.
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c",
                 "user.name=t", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(DOCTOR)], cwd=root,
                          capture_output=True, text=True)


def head(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def case(name: str, provenance: dict | None, mutate=None):
    """Build a fixture, optionally mutate it, run doctor, return (result, root)."""
    print(name)
    tmp = Path(tempfile.mkdtemp())
    root = fixture(tmp, provenance)
    if mutate:
        mutate(root)
    return run(root), root


def main() -> int:
    # 1. No provenance block at all — additive per §6, so it must not fail. But an
    #    empty provenance must never read as "all approved", which is the whole
    #    point of the count printing on a clean run.
    result, _ = case("no provenance block (an existing profile)", None)
    expect(result.returncode == 0, "exits 0 — the block is optional and additive")
    expect("0 of" in result.stdout and "provenance" in result.stdout,
           "still states 0 fields carry a human decision, rather than staying silent")
    expect("UNTRUSTED" in result.stdout,
           "names the unattributed fields as untrusted, not as approved")

    # 2. inferred is reported as untrusted, but is not itself a failure.
    result, _ = case("a field marked inferred", {"fields": {
        "source.root": {"state": "inferred", "evidence": "conventional for pubspec.yaml"}}})
    expect(result.returncode == 0, "inferred alone does not fail the profile")
    expect("source.root: inferred" in result.stdout,
           "reports the inferred field as untrusted with its evidence")

    # 3. CONTRADICTED by an edit after ratification. The value on disk is fine;
    #    what is false is the human's assertion about it.
    tmp = Path(tempfile.mkdtemp())
    root = fixture(tmp, None)
    prof = root / ".design-suite" / "profile.json"
    data = json.loads(prof.read_text())
    data["provenance"] = {"fields": {"source.root": {
        "state": "approved", "by": "someone", "on": "2026-01-01", "value": "src",
        "verifiedAgainst": {"commit": head(root)}}}}
    prof.write_text(json.dumps(data, indent=2))
    print("an approved value edited afterwards")
    result = run(root)
    expect(result.returncode == 1, "exits 1 — a ratification that no longer holds is fatal")
    expect("CONTRADICTED" in result.stdout and "'src'" in result.stdout,
           "names the ratified value the profile has since moved away from")

    # 4. CONTRADICTED by disk: the ratified path is gone. The paired negative
    #    matters more than the positive — the same fixture with the directory in
    #    place must NOT report it.
    prov = {"fields": {"source.root": {
        "state": "approved", "by": "someone", "on": "2026-01-01"}}}
    result, _ = case("an approved path that still exists", prov)
    expect(result.returncode == 0, "clean while the ratified path is on disk")
    expect("CONTRADICTED" not in result.stdout, "reports no contradiction when there is none")

    result, _ = case("the same profile with the ratified path deleted", prov,
                     mutate=lambda r: (r / "lib" / "tokens.dart").unlink()
                     or (r / "lib").rmdir())
    expect(result.returncode == 1, "exits 1 once the ratified path is gone")
    expect("CONTRADICTED" in result.stdout,
           "the dead path is reported as a false human assertion, not only as a typo")

    # 5. `contradicted` must be refused as a stored state — it is computed.
    result, _ = case("a hand-written 'contradicted' state",
                     {"fields": {"source.root": {"state": "contradicted"}}})
    expect(result.returncode == 1, "exits 1 on a stored 'contradicted'")
    expect("COMPUTED, never stored" in result.stdout,
           "says why, rather than only rejecting it as an unknown enum value")

    # 6. An entry for a field the profile does not have.
    result, _ = case("provenance for a field that is not in the profile",
                     {"fields": {"source.routesFile": {"state": "approved"}}})
    expect(result.returncode == 1, "exits 1 — ratifying a field nobody has")

    # 7. Staleness is measured in diffs. A stamp pointing at an older commit must
    #    say how far behind it is; a missing stamp must say it cannot be measured.
    tmp = Path(tempfile.mkdtemp())
    root = fixture(tmp, None)
    first = head(root)
    (root / "lib" / "later.dart").touch()
    subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "later"], capture_output=True)
    prof = root / ".design-suite" / "profile.json"
    data = json.loads(prof.read_text())
    data["provenance"] = {"fields": {"source.root": {
        "state": "approved", "verifiedAgainst": {"commit": first}}}}
    prof.write_text(json.dumps(data, indent=2))
    print("a stamp one commit behind HEAD")
    result = run(root)
    expect("1 commit(s) ago" in result.stdout,
           "measures staleness in commits, never in days")
    expect(result.returncode == 0, "staleness is reported, not fatal")

    result, _ = case("an approved field with no commit stamp",
                     {"fields": {"source.root": {"state": "approved"}}})
    expect("cannot be measured" in result.stdout,
           "an unstamped approval says staleness is unmeasurable rather than implying it is fresh")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  · {f}")
        return 1
    print("all provenance cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
