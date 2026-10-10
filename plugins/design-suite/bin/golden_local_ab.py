#!/usr/bin/env python3
"""Before/after golden comparison on one machine, for refactors that must not
change pixels.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py" snapshot   # before
    ... make the change ...
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py" check      # must be 0

## The gap this closes

A committed golden corpus is authored on whatever platform CI runs, so on a
different dev machine the comparator either skips or fails wholesale. That is
right for day-to-day work and leaves a hole exactly where it hurts most: a large
mechanical refactor whose entire claim is "this changed no rendering".

This closes it without touching the corpus. It renders the goldens on *this*
machine before the change, again after, and compares those two — a self-consistent
A/B where the platform difference cancels out because both sides came from the
same platform.

A byte match is a stronger claim than a tolerance match, and it is available here
precisely because both runs are local. That is the whole reason to do it this way
rather than trusting a 1% CI threshold: at 1%, a component can vanish inside the
budget of a mostly-empty frame.

## The corpus is restored no matter what

The committed images are stashed before rendering and put back in a `finally`,
including when the render fails. Leaving locally-rendered goldens in the working
tree would turn CI red for reasons that have nothing to do with the change — and
would look, to the next person, like the refactor broke something.

## Ported from `scripts/golden_local_ab.py` in the mobile app

Which is where the technique was proven, and where it had also quietly died: that
repo's Tier-1 files moved into the design-system package, `test/golden/` went with
them, and the script kept pointing at a directory that no longer existed. It never
complained, because nobody ran it.

So the corpus path and the render command come from the profile now, and the
project that has neither simply does not configure this — rather than owning a
tool aimed at nothing.
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from design_suite.project import need, profile  # noqa: E402

WORK = REPO / ".design-suite" / ".golden_local_ab"  # gitignored working area


def _render(command: list[str]) -> None:
    """Regenerate goldens from the current working tree, on this platform."""
    proc = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-4000:] + proc.stderr[-4000:])
        raise SystemExit("golden render failed — fix the tests first")


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _images(root: Path) -> dict[str, Path]:
    """Every image in the corpus, keyed by its path relative to the corpus root.

    Relative path, not filename: a per-platform corpus nests images in
    `goldens/<platform>/`, and keying on the bare name would silently compare a
    macOS render against its Linux namesake and call the difference a change.
    """
    return {p.relative_to(root).as_posix(): p
            for p in sorted(root.rglob("*.png"))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["snapshot", "check"])
    args = parser.parse_args()

    prof = profile(REPO)
    corpus = REPO / need(prof, "verification.goldensDir",
                         "is the corpus this compares before and after")
    command = need(prof, "verification.goldensUpdateCommand",
                   "is how this project re-renders its goldens")
    if not isinstance(command, list) or not command:
        raise SystemExit("verification.goldensUpdateCommand must be a non-empty argv "
                         "list — a shell string would need a shell to split it")
    if not corpus.is_dir():
        raise SystemExit(f"no corpus at {corpus.relative_to(REPO)}")

    baseline = WORK / "baseline"
    stash = WORK / "committed"
    WORK.mkdir(parents=True, exist_ok=True)

    # Preserve the committed corpus and put it back no matter what.
    _copy_tree(corpus, stash)
    try:
        _render(command)
        if args.mode == "snapshot":
            _copy_tree(corpus, baseline)
            print(f"golden_local_ab: baseline captured — {len(_images(baseline))} image(s)")
            return 0

        if not baseline.is_dir():
            raise SystemExit("no baseline — run `snapshot` before making changes")

        now, before = _images(corpus), _images(baseline)
        added = [k for k in now if k not in before]
        removed = [k for k in before if k not in now]
        differing = [k for k in now if k in before
                     and not filecmp.cmp(now[k], before[k], shallow=False)]

        for label, items in (("added", added), ("removed", removed),
                             ("DIFFERING", differing)):
            for name in items:
                print(f"  {label}: {name}")

        if differing or added or removed:
            print(f"\ngolden_local_ab: {len(differing)} differing, {len(added)} added, "
                  f"{len(removed)} removed")
            print("A pure refactor should report 0 of each. Inspect before proceeding.")
            return 1

        print(f"golden_local_ab: all {len(now)} image(s) byte-identical — "
              f"no visual change")
        return 0
    finally:
        _copy_tree(stash, corpus)
        shutil.rmtree(stash, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
