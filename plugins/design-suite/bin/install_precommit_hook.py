#!/usr/bin/env python3
"""Wire bin/run_precommit_audits.py into a project's real git commit path.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/install_precommit_hook.py" [--dir .] [--force] [--uninstall]

Opt-in, one-time, and separate from init.py's template-copy loop on purpose: init.py
scaffolds config that lives inside the project and is safe to overwrite with
--force; this script writes into `.git/`, which is not something to touch just
because someone re-ran onboarding. A project adopts the pre-commit gate by running
this once, same as `pre-commit install` is a separate step from writing
`.pre-commit-config.yaml`.

## Two ways in, chosen by what the project already has

If `.pre-commit-config.yaml` already exists, this project has opted into the
`pre-commit` framework (https://pre-commit.com) for *something* already — adding a
second, unrelated mechanism (`.git/hooks/pre-commit`) would silently clobber
whatever `pre-commit install` put there, or leave two hook runners racing depending
on install order. So this appends a `local` hook entry to the existing file instead,
idempotently (checked by id, not by byte-diffing the YAML — this suite runs stdlib
only, no PyYAML, so the entry is emitted as a fixed block and matched by a marker
comment).

Otherwise this writes `.git/hooks/pre-commit` directly: a small POSIX shell shim
whose only job is to exec run_precommit_audits.py. It is a shim rather than a copy
because git hooks run outside any Claude Code session — there is no
CLAUDE_PLUGIN_ROOT to expand — so the script's absolute path is resolved once, now,
and baked into the shim. If the plugin is later reinstalled at a different path,
re-run this installer; the shim says as much if the baked-in path stops resolving.

Refuses to overwrite a `.git/hooks/pre-commit` it did not write, unless --force —
a hand-written or Husky-managed hook already there is not this suite's to replace
silently. Every write is marked with the same sentinel line so a second run of this
installer (or --uninstall) can recognise its own work.

Stdlib only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import PLUGIN_ROOT  # noqa: E402

RUNNER = PLUGIN_ROOT / "bin" / "run_precommit_audits.py"
SENTINEL = "# design-suite:precommit-hook"
PRE_COMMIT_FRAMEWORK_MARKER = "# design-suite:precommit-hook (pre-commit framework)"

SHIM_TEMPLATE = """#!/bin/sh
{sentinel}
# Installed by plugins/design-suite/bin/install_precommit_hook.py.
# Runs this project's own fast/invariant audits — see .design-suite/hooks.map.json
# entries with "preCommit": true. Re-run the installer if this path stops
# resolving (e.g. the plugin was reinstalled elsewhere).
exec python3 "{runner}"{flags} "$@"
"""

FRAMEWORK_BLOCK = """  - repo: local
    hooks:
      - id: design-suite-precommit-audits
        name: design-suite pre-commit audits
        {marker}
        entry: python3 "{runner}"{flags}
        language: system
        pass_filenames: false
        stages: [commit]
"""


def _flags(refusals: str | None) -> str:
    # Only a non-default choice is baked in, so a default install stays
    # byte-identical to one made before --refusals existed.
    return " --refusals warn" if refusals == "warn" else ""


def install_git_hook(hooks_dir: Path, force: bool, refusals: str | None = None) -> int:
    target = hooks_dir / "pre-commit"
    shim = SHIM_TEMPLATE.format(sentinel=SENTINEL, runner=RUNNER, flags=_flags(refusals))

    if target.exists():
        existing = target.read_text() if target.is_file() else ""
        if SENTINEL in existing:
            if existing == shim:
                print(f"already installed: {target}")
                return 0
            if not force:
                print(f"{target} is an older version of this hook — pass --force to "
                      f"refresh it.", file=sys.stderr)
                return 1
        elif not force:
            print(f"{target} already exists and was not written by this installer — "
                  f"refusing to overwrite it. Pass --force if you want it replaced, or "
                  f"merge the two by hand (see {RUNNER} for what to call).",
                  file=sys.stderr)
            return 1

    hooks_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(shim)
    target.chmod(0o755)
    print(f"wrote {target}")
    print(f"pre-commit will now run any hooks.map.json entry with \"preCommit\": true. "
          f"List them with: python3 \"{RUNNER}\" --list")
    return 0


def uninstall_git_hook(hooks_dir: Path) -> int:
    target = hooks_dir / "pre-commit"
    if not target.is_file() or SENTINEL not in target.read_text():
        print(f"no design-suite pre-commit hook installed at {target}.")
        return 0
    target.unlink()
    print(f"removed {target}")
    return 0


def install_framework_config(config_path: Path, force: bool,
                             refusals: str | None = None) -> int:
    block = FRAMEWORK_BLOCK.format(marker=PRE_COMMIT_FRAMEWORK_MARKER, runner=RUNNER,
                                   flags=_flags(refusals))
    text = config_path.read_text()

    if PRE_COMMIT_FRAMEWORK_MARKER in text:
        print(f"already present in {config_path}.")
        return 0

    lines = text.splitlines(keepends=True)
    if not any(line.strip().startswith("repos:") for line in lines):
        print(f"{config_path} has no top-level 'repos:' key — this does not look like "
              f"a pre-commit framework config. Refusing to guess where to insert the "
              f"hook; add it by hand using the block in {Path(__file__).name}.",
              file=sys.stderr)
        return 1

    new_text = text.rstrip("\n") + "\n" + block
    config_path.write_text(new_text)
    print(f"appended a local hook entry to {config_path}.")
    print(f"run `pre-commit install` (the framework's own installer) so git actually "
          f"calls it — this script only edits the config, the same as it would for "
          f"any other hand-added hook entry.")
    return 0


def uninstall_framework_config(config_path: Path) -> int:
    text = config_path.read_text()
    if PRE_COMMIT_FRAMEWORK_MARKER not in text:
        print(f"no design-suite entry found in {config_path}.")
        return 0
    # Cut from the 'repo: local' line that precedes our marker (within that
    # block) to the next top-level '- repo:' entry or end of file.
    text_out = text
    start = text_out.find("  - repo: local")
    while start != -1:
        window_end = text_out.find("\n  - repo:", start + 1)
        window = text_out[start: window_end if window_end != -1 else len(text_out)]
        if PRE_COMMIT_FRAMEWORK_MARKER in window:
            text_out = text_out[:start] + text_out[window_end if window_end != -1 else len(text_out):]
            break
        start = text_out.find("  - repo: local", start + 1)
    config_path.write_text(text_out)
    print(f"removed design-suite entry from {config_path}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="project root (default: current directory)")
    ap.add_argument("--force", action="store_true",
                     help="overwrite a pre-commit hook this installer did not write")
    ap.add_argument("--uninstall", action="store_true", help="remove what this installer wired")
    ap.add_argument("--refusals", choices=("block", "warn"), default=None,
                     help="whether an audit that refuses (exit 2) blocks the commit "
                          "(default: block). Either way the refusal is reported loudly.")
    args = ap.parse_args()

    if not RUNNER.is_file():
        print(f"no runner at {RUNNER} — plugin install looks broken.", file=sys.stderr)
        return 1

    repo = Path(args.dir).resolve()
    git_dir = repo / ".git"
    if not git_dir.exists():
        print(f"{repo} has no .git — not a git repository (or worktree) root.",
              file=sys.stderr)
        return 1

    framework_config = repo / ".pre-commit-config.yaml"
    if framework_config.is_file():
        if args.uninstall:
            return uninstall_framework_config(framework_config)
        return install_framework_config(framework_config, args.force, args.refusals)

    # A plain .git/ has hooks/ directly; a worktree's .git is a file pointing
    # elsewhere. Either way this is the one place both layouts keep hooks by
    # default (core.hooksPath, if set, is deliberately not chased here — a
    # project customising that already knows how its hooks are wired).
    hooks_dir = git_dir / "hooks" if git_dir.is_dir() else _worktree_hooks_dir(git_dir)
    if hooks_dir is None:
        print(f"could not resolve a hooks directory from {git_dir}.", file=sys.stderr)
        return 1

    if args.uninstall:
        return uninstall_git_hook(hooks_dir)
    return install_git_hook(hooks_dir, args.force, args.refusals)


def _worktree_hooks_dir(git_file: Path) -> Path | None:
    """Resolve hooks/ for a linked worktree, whose .git is a pointer file."""
    try:
        text = git_file.read_text().strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = (git_file.parent / gitdir).resolve()
    # Linked worktrees share hooks with the common dir (.git/worktrees/<name>/..
    # has no hooks/ of its own); commondir points at it.
    commondir_file = gitdir / "commondir"
    if commondir_file.is_file():
        common = Path(commondir_file.read_text().strip())
        if not common.is_absolute():
            common = (gitdir / common).resolve()
        return common / "hooks"
    return gitdir / "hooks"


if __name__ == "__main__":
    sys.exit(main())
