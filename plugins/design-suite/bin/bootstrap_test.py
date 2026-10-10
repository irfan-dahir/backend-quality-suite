#!/usr/bin/env python3
"""Tests for the project-root resolution every script in bin/ depends on.

`_bootstrap.py` exists because "where the suite lives" and "the project being
audited" stopped being the same directory once this became an installed plugin,
and its docstring records what happened when they were conflated: the audits
pointed at the plugin directory and reported 0 findings. That is the governing
failure of this repo — a wrong answer that looks exactly like a clean codebase —
so the resolution rule deserves a test even though it is fifteen lines.

Three cases, each paired with the control that makes it mean something:

  * CLAUDE_PROJECT_DIR wins — but only because there is a marker there; and a
    *deeper* cwd must not beat it, or the precedence is undefined.
  * walk-up finds the marked ancestor from a subdirectory — with the control
    that it finds the ANCESTOR and not the subdirectory itself, which is the
    exact "audits a subdirectory as if it were the project" failure the module
    warns about.
  * no marker anywhere is a hard exit, not a guess. Without this the other two
    cases would pass against a resolver that returned cwd unconditionally.

    python3 plugins/design-suite/bin/bootstrap_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import _bootstrap  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


@contextmanager
def at(cwd: Path, project_dir: str | None):
    """Run inside `cwd` with CLAUDE_PROJECT_DIR set or cleared, then put both back.

    Both are process-global, and leaving either changed would make this file's
    result depend on the order the runner happened to execute things in.
    """
    old_cwd = Path.cwd()
    old_env = os.environ.get("CLAUDE_PROJECT_DIR")
    os.chdir(cwd)
    if project_dir is None:
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
    else:
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
    try:
        yield
    finally:
        os.chdir(old_cwd)
        if old_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old_env


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        # resolve() because macOS hands out /var/folders/... symlinked from
        # /private/var — comparing an unresolved fixture path against the
        # resolver's output would fail for a reason that is not the code's.
        tmp = Path(raw).resolve()

        marked = tmp / "marked"
        (marked / _bootstrap.MARKER).mkdir(parents=True)
        (marked / "src" / "deep").mkdir(parents=True)

        other = tmp / "other"
        (other / _bootstrap.MARKER).mkdir(parents=True)

        unmarked = tmp / "unmarked"
        unmarked.mkdir()

        print("check: CLAUDE_PROJECT_DIR takes precedence")
        with at(marked / "src" / "deep", str(other)):
            expect(_bootstrap.project_root() == other,
                   "the env var wins over a marked directory above the cwd")

        print("check: walk-up from a subdirectory")
        with at(marked / "src" / "deep", None):
            found = _bootstrap.project_root()
            expect(found == marked,
                   f"finds the marked ancestor, not the cwd — got {found}")
            expect(found != marked / "src" / "deep",
                   "does not treat an unmarked subdirectory as the project root")

        print("check: an explicit --dir argument bypasses both")
        with at(marked, str(other)):
            expect(_bootstrap.project_root(str(unmarked)) == unmarked,
                   "an explicit path is honoured even with no marker in it — "
                   "the caller said where, so there is nothing to detect")

        print("check: no marker is a refusal, not a guess")
        with at(unmarked, None):
            try:
                found = _bootstrap.project_root()
            except SystemExit as exc:
                expect(exc.code == 2, f"exits 2 with no marker anywhere, got {exc.code}")
            else:
                # The negative control for everything above. A resolver that
                # fell back to cwd would satisfy the walk-up case by accident.
                expect(False, f"exits rather than guessing — it returned {found}")

        print("check: PLUGIN_ROOT points at the plugin, not the project")
        expect((_bootstrap.PLUGIN_ROOT / "bin" / "_bootstrap.py").is_file(),
               "PLUGIN_ROOT resolves to the directory containing bin/_bootstrap.py")
        expect(str(_bootstrap.PLUGIN_ROOT) in sys.path,
               "PLUGIN_ROOT is on sys.path, so `import design_suite` finds this copy")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("_bootstrap.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
