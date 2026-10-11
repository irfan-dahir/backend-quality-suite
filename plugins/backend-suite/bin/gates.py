#!/usr/bin/env python3
"""Run every gate CI would run, locally.

    python3 plugins/backend-suite/bin/gates.py           # run them all
    python3 plugins/backend-suite/bin/gates.py --list    # show what would run
    python3 plugins/backend-suite/bin/gates.py -k seam   # only gates matching a substring

Exit 0 = every gate passed.

## Why this exists

GitHub Actions is unavailable on this org for billing reasons, and has been for long
enough that hand-verification is the primary path rather than the fallback. Roadmap
row A5.

Before this, running the gates meant pasting a Python one-liner that parsed the
workflow — reconstructed from memory each time, in a slightly different shape. That
is the same class of problem as a hand-written catalogue: a list of facts that exists
in two places and drifts.

## It reads the workflow rather than restating it

The gate list is not duplicated here. It is parsed out of
`.github/workflows/validate.yml`, so a gate added to CI is picked up the same day
with no edit to this file, and a gate removed from CI stops running here too.

Restating the list would be the drift this project keeps finding: two sources of
truth for the same set of facts, agreeing right up until someone edits one.

## What it deliberately does not do

**Install anything.** An install line is never executed. But "contains `pip install`"
is not the same question as "cannot run here", and treating it as one cost this repo
a gate: the frontmatter gate — the one whose whole subject is a component being
silently dropped — was itself silently dropped on every local run for its entire
life, because its first line said `pip install --quiet pyyaml`. It would have passed.

So an install preamble is now *stripped* rather than used as a veto, and the step is
skipped only when a package it installs is genuinely not importable. That is a
measured fact about this machine, not a guess from a substring. A step that really
cannot run is still reported as skipped, by name and with the reason — never dropped,
never counted as a pass.

**Run non-`run` steps.** `uses:` steps (checkout, setup-python) are the runner's job
and have no local equivalent. They are listed under --list as skipped, so the count
of "gates" is never inflated by them.

Stdlib only, like everything else here — no PyYAML, because the workflow's step list
is a shallow structure and requiring a dependency to check for missing dependencies
would be its own joke.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github/workflows/validate.yml"

# A line that installs packages rather than checking anything. Matched on the
# whole line, so a step is only ever stripped of lines that really are installs.
INSTALL_LINE = re.compile(
    r"^\s*(?:sudo\s+)?(?:python3?\s+-m\s+)?pip3?\s+install\s+(?P<args>.*?)\s*$")

# Distribution name -> the module you actually import. Only the handful this
# workflow has ever installed; an unknown name falls back to itself, which is
# right far more often than not.
IMPORT_NAME = {
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "pillow": "PIL",
    "python-dateutil": "dateutil",
}


def _packages(install_args: str) -> list[str]:
    """Importable module names a `pip install <args>` line would provide."""
    names = []
    for token in install_args.split():
        if token.startswith("-"):
            continue  # --quiet, -U, and friends
        dist = re.split(r"[<>=!~\[]", token, 1)[0].strip().lower()
        if dist:
            names.append(IMPORT_NAME.get(dist, dist.replace("-", "_")))
    return names


def _importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # noqa: BLE001 - a broken parent package is a missing package
        return False


def executable_form(cmd: str) -> tuple[str | None, str | None]:
    """`(command-to-run, None)` or `(None, why-it-cannot-run)`.

    Install lines are dropped from the command and the packages they name are
    checked for real. The step runs when they are all already importable, and is
    skipped — named, with the reason — when they are not. The distinction the old
    substring veto could not draw is precisely the one that matters: "this step
    installs something" is not "this step cannot run here".
    """
    kept, missing = [], []
    for line in cmd.splitlines():
        m = INSTALL_LINE.match(line)
        if m:
            missing += [p for p in _packages(m.group("args")) if not _importable(p)]
        else:
            kept.append(line)
    if missing:
        return None, f"needs uninstalled {', '.join(sorted(set(missing)))}"
    rest = "\n".join(kept).strip()
    if not rest:
        return None, "nothing left to run once the install lines are removed"
    return "\n".join(kept), None


def steps() -> list[tuple[str, str | None]]:
    """[(name, run-command-or-None)] in workflow order, without PyYAML.

    Hand-parsed because the shape is shallow and fixed: a list of `- name:` /
    `- uses:` entries under a job's `steps:`, each optionally carrying a `run:`
    scalar or `run: |` block. Anything more structural than that should use a real
    parser — but adding a dependency here would defeat the point of a script whose
    job is to run when the environment is unhelpful.
    """
    if not WORKFLOW.is_file():
        raise SystemExit(f"no workflow at {WORKFLOW.relative_to(REPO)}")

    out: list[tuple[str, str | None]] = []
    name: str | None = None
    run_lines: list[str] | None = None
    run_indent = 0

    for raw in WORKFLOW.read_text().splitlines():
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())

        # Inside a `run: |` block — keep taking lines until the indent drops.
        if run_lines is not None:
            if stripped and indent <= run_indent:
                out.append((name or "?", "\n".join(run_lines)))
                name, run_lines = None, None
            else:
                run_lines.append(raw[run_indent + 2:] if len(raw) > run_indent else "")
                continue

        # `indent == 0` is the workflow's own `name:`, not a step's. Without this
        # it was reported as a runner-setup step, which inflated the count by one
        # and named something that is not a step at all.
        m = re.match(r"-?\s*name:\s*(.+)$", stripped) if indent > 0 else None
        if m:
            if name is not None:
                out.append((name, None))
            name = m.group(1).strip().strip("'\"")
            continue

        m = re.match(r"-?\s*uses:\s*(.+)$", stripped)
        if m:
            if name is not None:
                out.append((name, None))
                name = None
            else:
                out.append((m.group(1).split("@")[0], None))
            continue

        m = re.match(r"run:\s*\|\s*$", stripped)
        if m:
            run_lines, run_indent = [], indent
            continue

        m = re.match(r"run:\s*(.+)$", stripped)
        if m:
            out.append((name or m.group(1)[:50], m.group(1).strip()))
            name = None
            continue

    if run_lines is not None:
        out.append((name or "?", "\n".join(run_lines)))
    elif name is not None:
        out.append((name, None))
    return out


class GateResult(NamedTuple):
    """One finished gate. `ok` is the only thing a verdict may be derived from."""
    name: str
    command: str
    ok: bool
    returncode: int
    seconds: float
    stdout: str
    stderr: str


class Plan(NamedTuple):
    """What a run of this workflow would consist of, before anything is run.

    Three lists, never two: `skipped` exists so that a step which cannot run here
    has somewhere to be reported from. Folding it into `runnable` (by dropping it)
    is the bug this file's docstring is mostly about.
    """
    runnable: list[tuple[str, str]]   # (name, command-as-it-will-be-run)
    skipped: list[tuple[str, str]]    # (name, why-it-cannot-run-here)
    setup: list[str]                  # `uses:` steps — the runner's job, no local form


def plan(k: str | None = None) -> Plan:
    """Split the workflow's steps into runnable / skipped / runner-setup.

    Factored out of `main` so that a caller wanting the whole verdict (see
    `attest.py`) reuses this exact classification rather than re-deriving it.
    A second copy of "which steps can run here" is the same two-sources-of-truth
    problem that made this file parse the workflow instead of restating it.
    """
    all_steps = steps()
    setup = [n for n, c in all_steps if not c]
    runnable: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for name, cmd in all_steps:
        if not cmd:
            continue
        exe, why = executable_form(cmd)
        if exe is None:
            skipped.append((name, why or "cannot run here"))
        else:
            runnable.append((name, exe))
    if k:
        runnable = [(n, c) for n, c in runnable if k.lower() in n.lower()]
    return Plan(runnable, skipped, setup)


def run_plan(runnable: list[tuple[str, str]],
             on_result=None) -> list[GateResult]:
    """Run each (name, command) in order, returning a result per gate.

    `on_result` is called with each `GateResult` as it lands, so a caller can
    stream progress without this function owning a print format.
    """
    results: list[GateResult] = []
    for name, cmd in runnable:
        t0 = time.time()
        proc = subprocess.run(["bash", "-c", cmd], cwd=REPO,
                              capture_output=True, text=True)
        result = GateResult(name=name, command=cmd, ok=proc.returncode == 0,
                            returncode=proc.returncode, seconds=time.time() - t0,
                            stdout=proc.stdout or "", stderr=proc.stderr or "")
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show what would run, run nothing")
    ap.add_argument("-k", metavar="SUBSTR", help="only gates whose name contains SUBSTR")
    args = ap.parse_args()

    runnable, skipped, setup = plan(args.k)

    if args.list:
        print(f"{len(runnable)} gate(s) from {WORKFLOW.relative_to(REPO)}:\n")
        for n, c in runnable:
            print(f"  {n}\n      {c.splitlines()[0][:88]}")
        if setup:
            print(f"\n  runner-setup steps, no local equivalent ({len(setup)}): "
                  f"{', '.join(setup[:6])}")
        if skipped:
            print(f"\n  steps that cannot run here ({len(skipped)}):")
            for n, why in skipped:
                print(f"    SKIP {n} — {why}")
        return 0

    if not runnable:
        # A filter that matches nothing must not look like a clean run — the same
        # rule every audit in this plugin follows.
        print(f"no gate matched {args.k!r}. Nothing ran, which is not the same as "
              f"everything passing.", file=sys.stderr)
        return 2

    print(f"running {len(runnable)} gate(s) from {WORKFLOW.relative_to(REPO)}\n")

    def show(r: GateResult) -> None:
        print(f"  {'ok  ' if r.ok else 'FAIL'} {r.name[:66]:68} {r.seconds:5.1f}s")

    results = run_plan(runnable, on_result=show)
    failures = [r for r in results if not r.ok]

    if skipped:
        # Named and reasoned, never a bare count — a skipped gate that reads as a
        # silent pass is the failure this whole repo is organised against.
        print(f"\n  {len(skipped)} step(s) could not run here:")
        for n, why in skipped:
            print(f"    SKIP {n} — {why}")

    if failures:
        print(f"\n{len(failures)} gate(s) failed:\n", file=sys.stderr)
        for r in failures:
            print(f"--- {r.name}", file=sys.stderr)
            tail = (r.stderr or r.stdout).strip().splitlines()[-12:]
            for line in tail:
                print(f"    {line}", file=sys.stderr)
        return 1

    print(f"\nall {len(runnable)} gate(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
