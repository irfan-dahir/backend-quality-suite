#!/usr/bin/env python3
"""Project-root resolution: one source, one generated copy, every entry point agreeing.

This function decides which repository the audits point at. Getting it wrong
does not raise: it points a scanner at the plugin's own directory, or at a
subdirectory, and the audit reports zero findings — which is indistinguishable
from a clean codebase, the one outcome this suite exists to prevent.
`hooks/mock_api_reminders.py`'s own comment records that a wrong root once left
the hook "registered, appear[ing] to be working, and never once run its audit".

There used to be four hand-kept copies, and one fix had to land four times. Now:

  design_suite/project.py                  the source (project_root, locate, walk)
  bin/_bootstrap.py                        re-exports project_root
  hooks/audit_on_edit.py                   imports locate() from PLUGIN_ROOT
  hooks/mock_api_reminders.py              imports locate() from PLUGIN_ROOT
  house-style/bin/resolve_role.py   GENERATED walk() — it cannot import
                                           across per-plugin cache hashes

So this test checks three things: the generated copy is current
(`sync_house_style_walk.py --check`); no hook has grown an inlined walk again;
and every entry point still answers the same in every situation below — which
also pins the wrappers (env handling, refusal) the generator does not cover.

The not-found behaviour is a DELIBERATE divergence, not drift, so it is asserted
explicitly: an engine entry point must refuse loudly (SystemExit 2), while a
hook must not take the user's harness down over a project that simply has not
adopted the suite.

Every positive case is paired with a negative control, in the style of
resolve_test.py: a resolver that returned the same directory for everything
would pass a test that only ever asks about a configured project.

    python3 plugins/design-suite/bin/project_root_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import contextlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
PLUGINS = BIN.parents[1]
MARKER = ".design-suite"
FAILURES: list[str] = []

# (label, path, attribute). The label is what a failure names, so it has to be
# the file someone would go open — not a friendly alias.
COPIES = [
    ("bin/_bootstrap.py", BIN / "_bootstrap.py", "project_root"),
    ("hooks/audit_on_edit.py",
     PLUGINS / "design-suite" / "hooks" / "audit_on_edit.py", "project_root"),
    ("hooks/mock_api_reminders.py",
     PLUGINS / "design-suite" / "hooks" / "mock_api_reminders.py", "_project_root"),
    ("house-style/bin/resolve_role.py",
     PLUGINS / "house-style" / "bin" / "resolve_role.py", "project_root"),
]

# Copies that must REFUSE (SystemExit 2) rather than return None when no
# project is found. See the module docstring: this split is intentional.
MUST_REFUSE = {"bin/_bootstrap.py", "house-style/bin/resolve_role.py"}


def load(label: str, path: Path, attr: str):
    """Import a copy by file path and hand back its resolver.

    By path rather than by package, because two of the four are hook scripts
    that are never on `sys.path` in the layout they actually ship in — the very
    fact that makes them copies in the first place. Module names are prefixed so
    two files that both define `project_root` cannot shadow each other in
    `sys.modules` and make this test compare one copy against itself.
    """
    name = "_parity_" + label.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return getattr(module, attr)


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


@contextlib.contextmanager
def situation(cwd: Path, env: Path | None):
    """Put the process in the state these functions read: cwd and the env var.

    Both are restored, because a test that leaves the interpreter chdir'd into a
    deleted temp directory poisons every case after it in ways that look like
    real failures.
    """
    old_cwd = Path.cwd()
    old_env = os.environ.get("CLAUDE_PROJECT_DIR")
    os.chdir(cwd)
    if env is None:
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
    else:
        os.environ["CLAUDE_PROJECT_DIR"] = str(env)
    try:
        yield
    finally:
        os.chdir(old_cwd)
        if old_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old_env


def answer(fn) -> Path | str:
    """What a copy said, with a refusal rendered as a comparable value.

    A SystemExit is an answer too — "I could not tell you" — and it has to be
    compared across copies rather than crashing the runner.
    """
    try:
        return fn()
    except SystemExit as exc:
        return f"SystemExit({exc.code})"


def fixture(tmp: Path) -> tuple[Path, Path, Path, Path]:
    """A configured project, a deep subdirectory of it, a nested inner project,
    and an unconfigured directory that must never resolve to any of them."""
    project = tmp / "project"
    (project / MARKER).mkdir(parents=True)
    deep = project / "packages" / "ui" / "src"
    deep.mkdir(parents=True)
    inner = project / "packages" / "inner"
    (inner / MARKER).mkdir(parents=True)
    outside = tmp / "elsewhere"
    outside.mkdir()
    return project, deep, inner, outside


def structural() -> None:
    """Single-source checks: the generated copy is current, and no hook re-inlines."""
    print("check: the house-style copy of walk() is generated and current")
    import subprocess
    proc = subprocess.run([sys.executable, str(BIN / "sync_house_style_walk.py"), "--check"],
                          capture_output=True, text=True)
    expect(proc.returncode == 0,
           f"house-style/bin/resolve_role.py walk() is current "
           f"({(proc.stdout + proc.stderr).strip()})")

    print("check: hooks import the shared resolver instead of inlining it")
    for hook in ("audit_on_edit.py", "mock_api_reminders.py"):
        text = (PLUGINS / "design-suite" / "hooks" / hook).read_text()
        expect('_shared("design_suite.project").locate(' in text,
               f"hooks/{hook}: resolves via design_suite.project.locate()")
        expect("in (here, *here.parents)" not in text,
               f"hooks/{hook}: carries no inlined directory walk")


def main() -> int:
    structural()
    resolvers = [(label, load(label, path, attr)) for label, path, attr in COPIES]

    with tempfile.TemporaryDirectory() as raw:
        # Resolved because on macOS /tmp is a symlink to /private/tmp, and these
        # functions resolve() the cwd — comparing an unresolved fixture path
        # against a resolved answer fails for a reason that has nothing to do
        # with parity.
        tmp = Path(raw).resolve()
        project, deep, inner, outside = fixture(tmp)

        print("check: CLAUDE_PROJECT_DIR wins when it names a configured project")
        with situation(cwd=outside, env=project):
            for label, fn in resolvers:
                expect(answer(fn) == project,
                       f"{label}: honours CLAUDE_PROJECT_DIR over the cwd")

        print("check: a marker-less CLAUDE_PROJECT_DIR falls back to the cwd walk")
        # The negative control for the case above: if a copy returned the env
        # var unconditionally, the case above would still pass and this one
        # would hand the audits a directory with no profile in it.
        with situation(cwd=deep, env=outside):
            for label, fn in resolvers:
                expect(answer(fn) == project,
                       f"{label}: ignores an unconfigured CLAUDE_PROJECT_DIR")

        print("check: walks up to the project root, not the cwd")
        with situation(cwd=deep, env=None):
            for label, fn in resolvers:
                got = answer(fn)
                expect(got == project,
                       f"{label}: a deep subdirectory resolves to the project root")
                expect(got != deep,
                       f"{label}: does NOT report the subdirectory as the project")

        print("check: the nearest marker wins, not the outermost")
        with situation(cwd=inner, env=None):
            for label, fn in resolvers:
                expect(answer(fn) == inner,
                       f"{label}: a nested configured project resolves to itself")

        print("check: the walk stops at the nearest git root")
        # An unconfigured git repo nested inside a configured project must not
        # borrow the outer profile — every audit would grade the wrong project.
        # Both a `.git` directory (a clone) and a `.git` file (a submodule or
        # worktree) mark the boundary.
        for kind in ("dir", "file"):
            nested = project / "vendor" / f"nested-{kind}"
            nested_deep = nested / "src"
            nested_deep.mkdir(parents=True)
            if kind == "dir":
                (nested / ".git").mkdir()
            else:
                (nested / ".git").write_text("gitdir: /elsewhere\n")
            with situation(cwd=nested_deep, env=None):
                for label, fn in resolvers:
                    got = answer(fn)
                    expect(got != project,
                           f"{label}: unconfigured nested repo (.git {kind}) does NOT "
                           f"resolve to the outer project")
                    if label in MUST_REFUSE:
                        expect(got == "SystemExit(2)",
                               f"{label}: refuses with exit 2 at the nested git root "
                               f"(.git {kind})")
                    else:
                        expect(got is None,
                               f"{label}: returns None at the nested git root (.git {kind})")
            # CLAUDE_PROJECT_DIR is still Claude Code's own statement and wins.
            with situation(cwd=nested_deep, env=project):
                for label, fn in resolvers:
                    expect(answer(fn) == project,
                           f"{label}: CLAUDE_PROJECT_DIR still wins inside a nested "
                           f"repo (.git {kind})")

        print("check: a configured git root and its subdirectories still resolve")
        repo = tmp / "gitproject"
        (repo / ".git").mkdir(parents=True)
        (repo / MARKER).mkdir()
        repo_deep = repo / "a" / "b"
        repo_deep.mkdir(parents=True)
        with situation(cwd=repo_deep, env=None):
            for label, fn in resolvers:
                expect(answer(fn) == repo,
                       f"{label}: a subdirectory of a configured git repo resolves to it")
        inner_repo = repo / "packages" / "configured"
        (inner_repo / ".git").mkdir(parents=True)
        (inner_repo / MARKER).mkdir()
        with situation(cwd=inner_repo, env=None):
            for label, fn in resolvers:
                expect(answer(fn) == inner_repo,
                       f"{label}: a configured nested git repo resolves to itself")

        print("check: not found — divergence is deliberate and stays as documented")
        with situation(cwd=outside, env=None):
            for label, fn in resolvers:
                got = answer(fn)
                if label in MUST_REFUSE:
                    expect(got == "SystemExit(2)",
                           f"{label}: refuses with exit 2 rather than guessing")
                else:
                    expect(got is None,
                           f"{label}: returns None rather than killing the harness")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print(f"project_root: all {len(resolvers)} entry points agree; the generated copy is current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
