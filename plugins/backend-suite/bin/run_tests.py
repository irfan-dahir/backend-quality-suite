#!/usr/bin/env python3
"""Run every `bin/*_test.py` in this plugin, and refuse to be silent about it.

    python3 plugins/backend-suite/bin/run_tests.py
    python3 plugins/backend-suite/bin/run_tests.py -k resolve   # substring filter
    python3 plugins/backend-suite/bin/run_tests.py -j 1         # serial, for debugging

Exit 0 only when at least one test file was discovered AND every one of them
passed AND none of them reported a skip. Exit 1 on a failure, exit 2 on the
situations where *nothing ran* — which is the whole reason this file exists.

## Why

Thirteen `*_test.py` files lived in this directory and nothing ran any of them:
not the workflow, not `gates.py`, not the pre-commit hook. They all passed by
hand, so nobody noticed that `gates.py` would have reported every gate green on
a tree where every test was broken. "Tested" bought no gate at all.

That is this repo's governing failure in its purest form — a check whose silence
is indistinguishable from a pass — so the runner is built against it:

  * **Discovery is a glob, and an empty glob is exit 2.** A runner that finds
    zero tests and prints nothing is the exact shape of the bug.
  * **A file that will not import fails.** Each file is compiled before it is
    run, so a syntax error is reported as a broken test rather than becoming a
    file that quietly stops contributing assertions. (Running it would also fail,
    but the compile pass names the cause instead of leaving it in a traceback.)
  * **A skip fails.** Eight of these files are `unittest`-based, and `unittest`
    exits 0 for a run that skipped every test, or that ran none at all. Both are
    parsed out of its summary and treated as failures.
  * **The count is printed.** A future reader must be able to tell 13-ran-all-
    passed from 0-ran-nothing-found, and the only way to tell those apart from
    the outside is a number.

The two test styles here (`unittest`, and a hand-rolled `expect()` helper) are
both supported without converting either: the contract this runner depends on is
just the exit code, plus `unittest`'s summary lines when they happen to be there.

## Parallelism

Files run concurrently (``-j N``, default = CPU count; ``-j 1`` is the old
serial loop). Every file is still its own ``python3`` process with cwd at the
repo root, so isolation is what it always was: no file shares an interpreter
with another. Results are collected and printed in **sorted discovery order**,
never completion order, so the output of a parallel run is byte-comparable to
a serial one apart from the timings. Each line's time is that file's own wall
time. A file whose worker dies without a result is a failure, not an absence:
the printed count is always the discovered count.

Stdlib only, like everything else in this directory — there is deliberately no
pytest dependency.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BIN = Path(__file__).resolve().parent
REPO = BIN.parents[2]

# `unittest`'s own summary, which is the only machine-readable thing it emits.
# "Ran 0 tests" and any skip count are failures here, not footnotes.
RAN = re.compile(r"^Ran (\d+) tests?", re.M)
SKIPPED = re.compile(r"skipped=(\d+)")


def discover(pattern: str | None) -> list[Path]:
    files = sorted(BIN.glob("*_test.py"))
    if pattern:
        files = [f for f in files if pattern.lower() in f.name.lower()]
    return files


def compiles(path: Path) -> str | None:
    """None if the file parses, else the reason it does not.

    Checked separately from running it so that an un-importable test file is
    reported as "this test is broken" rather than as an ordinary failure — the
    difference matters when deciding whether the code or the test regressed.
    """
    try:
        compile(path.read_text(), str(path), "exec")
    except SyntaxError as exc:
        return f"does not parse: {exc.msg} (line {exc.lineno})"
    except OSError as exc:
        return f"unreadable: {exc}"
    return None


def verdict(proc: subprocess.CompletedProcess) -> tuple[bool, str, int | None]:
    """(passed, why-not, assertion-count-if-known) for one finished test file."""
    blob = (proc.stdout or "") + (proc.stderr or "")
    ran = RAN.search(blob)
    count = int(ran.group(1)) if ran else None

    if proc.returncode != 0:
        return False, f"exit {proc.returncode}", count
    if count == 0:
        # unittest is perfectly happy to exit 0 having run nothing.
        return False, "ran 0 tests but exited 0", count
    skipped = SKIPPED.search(blob)
    if skipped and int(skipped.group(1)) > 0:
        return False, f"{skipped.group(1)} test(s) skipped — a skip is not a pass", count
    return True, "", count


def run_one(f: Path) -> tuple[str | None, subprocess.CompletedProcess | None, float]:
    """(broken-reason, finished-process, wall-seconds) for one test file.

    Never raises: anything that goes wrong launching the file becomes a
    BROKEN result, so a file cannot drop out of the report.
    """
    broken = compiles(f)
    if broken is not None:
        return broken, None, 0.0
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, str(f)], cwd=str(REPO),
                              capture_output=True, text=True)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        return f"could not run: {exc!r}", None, time.time() - t0
    return None, proc, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-k", metavar="SUBSTR", help="only test files whose name contains SUBSTR")
    ap.add_argument("-j", type=int, default=os.cpu_count() or 1, metavar="N",
                    help="test files to run at once (default: CPU count; 1 = serial)")
    ap.add_argument("--list", action="store_true", help="list what would run, run nothing")
    args = ap.parse_args()

    files = discover(args.k)
    if not files:
        where = f"matching {args.k!r} " if args.k else ""
        print(f"no test file {where}found in {BIN.relative_to(REPO)}/. Nothing ran, "
              f"which is not the same as everything passing.", file=sys.stderr)
        return 2

    if args.list:
        print(f"{len(files)} test file(s):")
        for f in files:
            print(f"  {f.name}")
        return 0

    jobs = max(1, args.j)
    print(f"running {len(files)} test file(s) from {BIN.relative_to(REPO)}/ "
          f"with {min(jobs, len(files))} worker(s)\n")
    failures: list[tuple[str, str, subprocess.CompletedProcess | None]] = []
    assertions = 0

    # Threads, not processes: each worker just blocks on its own subprocess.
    # pool.map yields in input order, so the report is deterministic.
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(run_one, files))
    if len(results) != len(files):  # belt and braces: none silently absent
        print(f"internal error: {len(files)} discovered, {len(results)} reported",
              file=sys.stderr)
        return 2

    for f, (broken, proc, elapsed) in zip(files, results):
        if broken is not None:
            print(f"  BROKEN {f.name:44} {broken}")
            failures.append((f.name, broken, proc))
            continue
        ok, why, count = verdict(proc)
        if count:
            assertions += count
        shown = f"{count} test(s)" if count is not None else "ok"
        print(f"  {'ok    ' if ok else 'FAIL  '}{f.name:44} "
              f"{shown if ok else why:26} {elapsed:5.1f}s")
        if not ok:
            failures.append((f.name, why, proc))

    # The count is the signal. Without it, this step's output on a tree where
    # discovery silently broke would be indistinguishable from a green run.
    tail = f", {assertions} unittest case(s)" if assertions else ""
    print(f"\n{len(files)} test file(s) ran{tail}; "
          f"{len(files) - len(failures)} passed, {len(failures)} failed.")

    if failures:
        print(f"\n{len(failures)} test file(s) failed:\n", file=sys.stderr)
        for name, why, proc in failures:
            print(f"--- {name}: {why}", file=sys.stderr)
            if proc is not None:
                lines = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
                for line in lines[-14:]:
                    print(f"    {line}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
