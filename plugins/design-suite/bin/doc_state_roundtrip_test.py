#!/usr/bin/env python3
"""Round-trip test: the WRITERS of exit-4 and exit-5 state against their READER.

`resolve_test.py` already tests the readers thoroughly — but against manifests
and documents built by hand inside that test file. Nothing tested that
`decline_doc.py` and `scaffold_doc.py`, the only two producers of that state,
actually write what those readers parse. That is a seam where both sides can be
correct about a shape they no longer share: the writer emits a key or a status
string, the reader looks for a slightly different one, and the result is not an
error. A decline that stops being seen silently stops applying, and a stub that
stops being recognised resolves as exit 0 — a scaffolded blank file counted as
coverage. Both are the governing failure: silence that reads as a pass.

So each half is a genuine round trip — write with one binary, read with the
other, in one fixture project — and each is paired with its negative control: an
authored document in the same project that must still resolve 0, and a role that
was neither scaffolded nor declined, which must still be 2. Without those, a
resolver stuck on 4 and 5 would pass every interesting case.

    python3 plugins/design-suite/bin/doc_state_roundtrip_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
SCAFFOLD = BIN / "scaffold_doc.py"
DECLINE = BIN / "decline_doc.py"
RESOLVE = BIN / "resolve.py"
MANIFEST_REL = ".design-suite/docs.manifest.json"

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def run(script: Path, root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env, cwd=str(root))


def fixture(tmp: Path) -> Path:
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "docs").mkdir()
    # The control document: authored, no frontmatter, must keep resolving 0
    # while its neighbours are a stub and a decline.
    (root / "docs" / "DECISIONS.md").write_text("# Decisions\n\nWritten by hand.\n")
    (root / ".design-suite" / "profile.json").write_text(json.dumps({
        "project": {"name": "Fixture"},
        "docs": {"manifest": MANIFEST_REL},
    }))
    (root / ".design-suite" / MANIFEST_REL.split("/")[-1]).write_text(json.dumps({
        "roles": {"decisions": "docs/DECISIONS.md"},
    }, indent=2) + "\n")
    return root


def manifest(root: Path) -> dict:
    return json.loads((root / MANIFEST_REL).read_text())


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = fixture(Path(raw).resolve())

        print("check: control — an authored document resolves 0 before anything is written")
        base = run(RESOLVE, root, "decisions")
        expect(base.returncode == 0, "an authored, mapped document exits 0")
        unknown = run(RESOLVE, root, "design")
        expect(unknown.returncode == 2,
               "a role that is neither scaffolded nor declined exits 2, not 4 or 5")

        print("check: scaffold_doc writes state that resolve.py reads as a stub (exit 5)")
        wrote = run(SCAFFOLD, root, "design")
        expect(wrote.returncode == 0, f"scaffold_doc exits 0: {wrote.stderr.strip()[:200]}")
        # Registration is half the round trip: an unregistered stub resolves to
        # nothing at all, which reads as a role nobody has looked at.
        mapped = (manifest(root).get("roles") or {}).get("design")
        expect(isinstance(mapped, str), f"the role is registered in the manifest, got {mapped!r}")
        expect(mapped is not None and (root / mapped).is_file(),
               "the registered path is the file it actually wrote")

        got = run(RESOLVE, root, "design")
        expect(got.returncode == 5,
               f"the reader sees the written stub as exit 5, got {got.returncode}")
        expect(got.stdout.strip() == mapped,
               "the stub still prints its path — whoever fills it in needs it")
        # The control, re-asserted after the write: scaffolding one role must not
        # change the answer for another.
        expect(run(RESOLVE, root, "decisions").returncode == 0,
               "the authored neighbour still exits 0 after a stub is scaffolded")

        print("check: decline_doc writes state that resolve.py reads as declined (exit 4)")
        reason = "single-file repository, motion lives in the design system"
        declined = run(DECLINE, root, "motion", "--reason", reason, "--by", "lead")
        expect(declined.returncode == 0,
               f"decline_doc exits 0: {declined.stderr.strip()[:200]}")

        got = run(RESOLVE, root, "motion")
        expect(got.returncode == 4,
               f"the reader sees the written decline as exit 4, got {got.returncode}")
        expect(reason in got.stdout,
               "the reason survives the round trip verbatim — a skill prints it "
               "instead of skipping silently")

        print("check: the two states stay distinct")
        # If the writers shared a key, or the reader checked one before the
        # other, a scaffolded role could start answering 4 and a declined one 5.
        expect(run(RESOLVE, root, "design").returncode == 5,
               "the scaffolded role still answers 5 after a decline was recorded")
        expect(run(RESOLVE, root, "decisions").returncode == 0,
               "the authored document still answers 0 after both writes")

        print("check: a writer refuses to overwrite the other's state")
        clash = run(SCAFFOLD, root, "motion")
        expect(clash.returncode == 1,
               "scaffolding a declined role is refused — writing over it would "
               "silently reverse a recorded decision")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("scaffold_doc/decline_doc round trip: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
