#!/usr/bin/env python3
"""Opt into running the whole local verdict before every push.

    python3 plugins/design-suite/bin/install_prepush_hook.py            # install
    python3 plugins/design-suite/bin/install_prepush_hook.py --status   # is it wired?
    python3 plugins/design-suite/bin/install_prepush_hook.py --uninstall
    python3 plugins/design-suite/bin/install_prepush_hook.py --force    # replace an older shim

Installs nothing unless you run it. Removes cleanly with --uninstall. Refuses to
overwrite a pre-push hook it did not write.

## Why pre-push and not pre-commit

`install_precommit_hook.py` already exists and does this shape for *consumer*
projects: it wires the fast, per-commit audits into `.git/hooks/pre-commit`. This
is deliberately a sibling rather than an extension of it, because the two answer
different questions at different costs:

  * pre-commit runs on every commit and must stay fast, so it runs the subset of
    audits marked `preCommit` in `hooks.map.json`.
  * this runs `attest.py` — the whole gate set, minutes not seconds — and only at
    the moment the work is about to leave the machine. With Actions unavailable,
    a push is the last point at which anything mechanical can still object.

Putting the full suite on pre-commit would get it disabled within a day, and a
disabled hook reads exactly like a passing one. Putting it on pre-push costs the
developer the wait once per push, which is the same wait CI used to cost them
and which nobody has to sit and watch.

The hooks-directory resolution (plain clone vs. linked worktree) is imported from
`install_precommit_hook.py` rather than copied — it is the same question with the
same answer, and this repo has been bitten by second copies of things.

## The escape hatch, and why it is loud

`git push --no-verify` skips this, as it skips any hook. That is deliberate and
not worth fighting: a hook that cannot be bypassed gets uninstalled instead, and
an uninstalled hook is silent. What the shim does instead is make the bypass
*legible* — it prints what it is about to run and why, so skipping it is a
decision somebody made rather than a default they drifted into.

Stdlib only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import PLUGIN_ROOT  # noqa: E402
from install_precommit_hook import _worktree_hooks_dir  # noqa: E402  - one copy, not two

ATTEST = PLUGIN_ROOT / "bin" / "attest.py"
SENTINEL = "# design-suite:prepush-attest"

SHIM_TEMPLATE = """#!/bin/sh
{sentinel}
# Installed by plugins/design-suite/bin/install_prepush_hook.py.
# Runs the full local gate run — the authority for this repo, with GitHub Actions
# unavailable. Re-run the installer if this path stops resolving (e.g. the plugin
# was reinstalled elsewhere).
#
# Exit 0 = verified. Exit 1 = a gate failed. Exit 2 = partial: something could not
# run, which is NOT a pass. All three block the push except 0.
echo "pre-push: running the full local gate run (design-suite attest)."
echo "          this is the authority here — Actions is unavailable."
echo "          bypass with 'git push --no-verify' if you mean to."
exec python3 "{attest}"
"""


def status(hooks_dir: Path) -> int:
    target = hooks_dir / "pre-push"
    if not target.is_file():
        print(f"not installed: no hook at {target}")
        return 1
    text = target.read_text()
    if SENTINEL not in text:
        print(f"not installed: {target} exists but was written by something else — "
              f"this installer will not touch it without --force.")
        return 1
    current = text == SHIM_TEMPLATE.format(sentinel=SENTINEL, attest=ATTEST)
    print(f"installed at {target}" + ("" if current else " (an older version — "
                                      "re-run with --force to refresh it)"))
    return 0 if current else 1


def install(hooks_dir: Path, force: bool) -> int:
    target = hooks_dir / "pre-push"
    shim = SHIM_TEMPLATE.format(sentinel=SENTINEL, attest=ATTEST)

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
            # Somebody else's hook. Replacing it silently would be this suite
            # deciding, on their behalf, that its check matters more than theirs.
            print(f"{target} already exists and was not written by this installer — "
                  f"refusing to overwrite it. Pass --force to replace it, or merge "
                  f"the two by hand: the hook only needs to run\n"
                  f"    python3 \"{ATTEST}\"\n"
                  f"and propagate its exit code.", file=sys.stderr)
            return 1

    hooks_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(shim)
    target.chmod(0o755)
    print(f"wrote {target}")
    print("every `git push` from this clone now runs the full gate set first. "
          "Exit 2 (partial) blocks the push too — it is not a softer pass.")
    print(f"remove it with: python3 {Path(__file__).name} --uninstall")
    return 0


def uninstall(hooks_dir: Path) -> int:
    target = hooks_dir / "pre-push"
    if not target.is_file() or SENTINEL not in target.read_text():
        print(f"no design-suite pre-push hook installed at {target}.")
        return 0
    target.unlink()
    print(f"removed {target}")
    return 0


def hooks_dir_for(repo: Path) -> Path | None:
    git_dir = repo / ".git"
    if not git_dir.exists():
        return None
    return git_dir / "hooks" if git_dir.is_dir() else _worktree_hooks_dir(git_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="repository root (default: cwd)")
    ap.add_argument("--force", action="store_true",
                    help="replace a pre-push hook this installer did not write")
    ap.add_argument("--uninstall", action="store_true", help="remove what this wired")
    ap.add_argument("--status", action="store_true",
                    help="report whether the hook is installed and current; change nothing")
    args = ap.parse_args(argv)

    if not ATTEST.is_file():
        print(f"no attest.py at {ATTEST} — plugin install looks broken.", file=sys.stderr)
        return 1

    repo = Path(args.dir).resolve()
    hooks = hooks_dir_for(repo)
    if hooks is None:
        print(f"{repo} has no .git — not a git repository (or worktree) root.",
              file=sys.stderr)
        return 1

    if args.status:
        return status(hooks)
    if args.uninstall:
        return uninstall(hooks)
    return install(hooks, args.force)


if __name__ == "__main__":
    sys.exit(main())
