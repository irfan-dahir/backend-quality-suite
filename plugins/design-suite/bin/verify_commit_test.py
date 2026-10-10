#!/usr/bin/env python3
"""Tests for verify.py's commit stamp on evidence records (#151).

Every refusal is paired with the positive it must not swallow: a record written
in a real git repo carries HEAD; one written outside a repo carries an explicit
cannot-determine (never an omitted field); a pre-#151 record reads as unknown,
never as current. All repos are synthetic temp dirs — no consumer evidence is
touched.

    python3 plugins/design-suite/bin/verify_commit_test.py

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
VERIFY = BIN / "verify.py"
sys.path.insert(0, str(BIN))
import verify  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def project(root: Path, *, repo: bool) -> Path:
    (root / ".design-suite").mkdir(parents=True)
    (root / "src.txt").write_text("a\n")
    if repo:
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "init")
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(root.parent)}
    return subprocess.run([sys.executable, str(VERIFY), *args, "--project-root", str(root)],
                          capture_output=True, text=True, env=env)


def record(root: Path, name: str) -> dict:
    return json.loads((root / ".design-suite" / "evidence" / f"{name}.json").read_text())


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Positive: inside a git repo, the record carries HEAD.
        r = project(tmp / "inrepo", repo=True)
        head = git(r, "rev-parse", "HEAD")
        p = run(r, "no-such-component-x")
        check(p.returncode == 2, "exit-code contract unchanged: unknown component still exits 2")
        va = record(r, "no-such-component-x")["verified_against"]
        check(va.get("commit") == head, "record in a git repo carries the HEAD commit")
        check(va.get("commit_status") == "recorded", "  ...with commit_status 'recorded'")
        check(verify.record_commit({"verified_against": va}) == ("recorded", head),
              "  ...and reads back as recorded at that sha")

        # Refusal: outside a git repo, cannot-determine is named, not omitted.
        n = project(tmp / "norepo", repo=False)
        run(n, "no-such-component-x")
        va = record(n, "no-such-component-x")["verified_against"]
        check("commit" in va and va["commit"] is None, "record outside git has commit key, null")
        check(va.get("commit_status") == "cannot-determine", "  ...and commit_status 'cannot-determine'")
        check(bool(va.get("commit_note")), "  ...and a named reason")
        check(verify.record_commit({"verified_against": va})[0] == "cannot-determine",
              "  ...and does not read back as recorded")

        # Legacy: a pre-#151 record reads as unknown, never as current.
        legacy = {"verified_against": {"project": "x", "path": "/x"}}
        check(verify.record_commit(legacy) == ("unknown", None), "pre-#151 record reads as unknown")
        check(verify.record_commit({"verified_against": {"commit": head}})[0] == "unknown",
              "  ...a bare sha without commit_status is not trusted as recorded")

        # Staleness report: current until a file moves, then stale; legacy stays unknown.
        out = run(r, "--staleness")
        check(out.returncode == 0 and "CURRENT" in out.stdout, "--staleness: untouched repo reads CURRENT")
        ev = r / ".design-suite" / "evidence"
        (ev / "legacy.json").write_text(json.dumps(legacy))
        (r / "src.txt").write_text("b\n")
        out = run(r, "--staleness")
        check("no-such-component-x: STALE" in out.stdout, "--staleness: a changed file flips it to STALE")
        check("legacy: UNKNOWN" in out.stdout, "--staleness: legacy record reads UNKNOWN, not CURRENT")
        out = run(n, "--staleness")
        check("CANNOT-DETERMINE" in out.stdout, "--staleness: non-repo record reads CANNOT-DETERMINE")
        empty = project(tmp / "empty", repo=False)
        check(run(empty, "--staleness").returncode == 2, "--staleness with no records refuses (exit 2)")

    print(f"\n{'FAILED' if FAILS else 'all passed'} ({len(FAILS)} failure(s))")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
