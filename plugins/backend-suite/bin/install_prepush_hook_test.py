#!/usr/bin/env python3
"""Tests for install_prepush_hook.py — installs nothing, removes cleanly, refuses loudly.

    python3 plugins/backend-suite/bin/install_prepush_hook_test.py

The three properties the task this was written for insisted on — opt-in,
uninstallable, never silent — are each tested against the case they must not
swallow:

  * it refuses to clobber a foreign hook  <->  it DOES install when there is none
  * --force replaces a foreign hook       <->  without --force the foreign hook
                                               is still byte-identical afterwards
  * --uninstall removes our shim          <->  --uninstall leaves a foreign hook
                                               completely alone
  * --status reports installed            <->  --status reports not-installed, and
                                               does not create anything by asking

A test that only checked the refusals would be satisfied by an installer that
never installed anything at all.

Exits 0 when every case holds, 1 otherwise. Stdlib only; every write goes to a
temporary directory.
"""
from __future__ import annotations

import io
import contextlib
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import install_prepush_hook as hook  # noqa: E402

FAILURES: list[str] = []

FOREIGN = "#!/bin/sh\n# husky, or a hand-written hook. Not ours.\nexit 0\n"


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def run(argv: list[str]) -> tuple[int, str]:
    """Call main(argv), capturing both streams — nothing here should be chatty to the test."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = hook.main(argv)
    return code, out.getvalue() + err.getvalue()


def fresh_repo(tmp: Path) -> Path:
    """A directory shaped enough like a git clone for the installer to accept it."""
    repo = tmp / "repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    return repo


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        print("check: nothing is installed until you ask")

        repo = fresh_repo(tmp)
        target = repo / ".git" / "hooks" / "pre-push"
        code, text = run(["--dir", str(repo), "--status"])
        expect(code == 1 and "not installed" in text,
               f"--status on a fresh repo says not installed, got {code}")
        expect(not target.exists(),
               "asking for --status did not create the hook as a side effect")

        print("check: install writes an executable shim that runs attest.py")

        code, text = run(["--dir", str(repo)])
        expect(code == 0, f"install exits 0, got {code}")
        expect(target.is_file(), "the pre-push hook now exists")
        body = target.read_text()
        expect(hook.SENTINEL in body, "the shim carries the sentinel that marks it ours")
        expect("attest.py" in body, f"the shim actually invokes attest.py")
        expect(target.stat().st_mode & 0o111, "the shim is executable, or git ignores it")
        expect("--no-verify" in body,
               "the shim names its own bypass rather than pretending it has none")

        code, text = run(["--dir", str(repo), "--status"])
        expect(code == 0 and "installed at" in text,
               f"--status now reports it installed and current, got {code}: {text!r}")

        print("check: installing twice is idempotent, not a duplicate or an error")

        code, text = run(["--dir", str(repo)])
        expect(code == 0 and "already installed" in text,
               f"a second install is a no-op, got {code}: {text!r}")

        print("check: uninstall removes it completely")

        code, text = run(["--dir", str(repo), "--uninstall"])
        expect(code == 0 and not target.exists(),
               f"--uninstall removes the shim, got {code}")
        code, text = run(["--dir", str(repo), "--uninstall"])
        expect(code == 0 and "no backend-suite pre-push hook" in text,
               "uninstalling twice is harmless and says so")

        print("check: a hook we did not write is never touched silently")

        repo2 = fresh_repo(tmp / "b")
        target2 = repo2 / ".git" / "hooks" / "pre-push"
        target2.write_text(FOREIGN)

        code, text = run(["--dir", str(repo2)])
        expect(code == 1, f"install refuses over a foreign hook, got {code}")
        expect(target2.read_text() == FOREIGN,
               "the foreign hook is byte-identical after the refusal")
        expect("refusing to overwrite" in text and "attest.py" in text,
               "the refusal says what to do instead, rather than just failing")

        code, text = run(["--dir", str(repo2), "--status"])
        expect(code == 1 and "written by something else" in text,
               f"--status distinguishes a foreign hook from no hook, got {text!r}")

        code, text = run(["--dir", str(repo2), "--uninstall"])
        expect(code == 0 and target2.read_text() == FOREIGN,
               "--uninstall leaves a hook it did not write completely alone")

        print("check: --force is the only way past that, and it works")

        code, text = run(["--dir", str(repo2), "--force"])
        expect(code == 0 and hook.SENTINEL in target2.read_text(),
               f"--force replaces the foreign hook, got {code}")

        print("check: an older version of our own shim is refreshed, not silently kept")

        stale = hook.SHIM_TEMPLATE.format(sentinel=hook.SENTINEL, attest="/old/path/attest.py")
        target2.write_text(stale)
        code, text = run(["--dir", str(repo2), "--status"])
        expect(code == 1 and "older version" in text,
               f"--status flags a stale shim rather than calling it current, got {text!r}")
        code, text = run(["--dir", str(repo2)])
        expect(code == 1 and "--force" in text,
               "refreshing a stale shim needs --force, and the message says so")
        code, text = run(["--dir", str(repo2), "--force"])
        expect(code == 0 and str(hook.ATTEST) in target2.read_text(),
               "--force refreshes the baked-in path")

        print("check: a directory that is not a git repo is refused, not guessed at")

        plain = tmp / "not-a-repo"
        plain.mkdir()
        code, text = run(["--dir", str(plain)])
        expect(code == 1 and "no .git" in text,
               f"a non-repo is refused with a reason, got {code}: {text!r}")
        expect(not (plain / ".git").exists(),
               "the refusal did not create a .git directory on the way out")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("install_prepush_hook.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
