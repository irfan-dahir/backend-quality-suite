#!/usr/bin/env python3
"""The whole verdict, on this machine, with the conditions it was reached under.

    python3 plugins/design-suite/bin/attest.py            # run everything, one verdict
    python3 plugins/design-suite/bin/attest.py --list     # the plan and the environment, run nothing
    python3 plugins/design-suite/bin/attest.py --json     # the same attestation, machine-readable

Exit codes:

    0   VERIFIED    every gate ran here, and every gate passed
    1   FAILED      a gate ran and failed
    2   PARTIAL     something could not run, or could not be determined

**2 is not a softer 0.** A run that could not execute part of itself is not a
run that passed, and the whole point of this file is that nobody downstream can
tell those apart from an exit code alone unless we make them different.

## Why this exists

GitHub Actions is unavailable here and is staying that way. That makes the local
run the authority rather than the fallback, and an authority has obligations a
stopgap does not:

  * **One command, one verdict.** Before this, "is the tree good?" meant knowing
    to invoke `gates.py`, `run_tests.py` and `gate_consumer_compat.py`, and knowing
    how to combine three exit codes. Two of those three turned out to already be
    gates inside `gates.py` — which is good, but nothing *checked* that they
    still were, so the knowledge that you could stop running them by hand was
    never safe to act on. `coverage()` below now checks it every run.

  * **A verdict with its conditions attached.** CI's real product was not the
    checkmark, it was the *fixed environment* the checkmark was earned in. A
    local run has no such fixture: it happens on whatever Python, whatever
    installed packages and whatever git state the developer has. So the
    environment is reported as part of the verdict, every time, and a gate whose
    result depended on something environmental says so by name.

## What this CANNOT tell you — read this before trusting a green run

A clean-checkout CI run and this are not the same claim, and no amount of local
tooling closes the gap. Specifically:

  * **It sees your working tree, not the commit.** Uncommitted edits — including
    files you have not added — are what most gates read. A green attestation on
    a dirty tree says nothing about what a reviewer will actually receive.
    `gate_consumer_compat.py` is the sharpest case: it diffs *committed git
    blobs*, so it is structurally blind to uncommitted work, and can report
    clean on a tree whose uncommitted edits are a consumer break.
  * **It sees your installed packages.** A gate that passes because a package
    happens to be importable here may be skipped, or fail, elsewhere.
  * **It sees your Python.** One version, one platform. A syntax or stdlib
    behaviour that differs on another is not observed.
  * **It cannot prove the absence of a stale artifact** that exists only in your
    checkout — an untracked file a gate reads, a generated file you regenerated
    locally but did not commit.

These are reported as LIMITS on every run, not buried here, because a limit that
only lives in a docstring is a limit nobody applies at the moment they need it.

Stdlib only, like everything else in this directory.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import gates  # noqa: E402  - the gate list and its runner, never a second copy

REPO = gates.REPO

VERIFIED, FAILED, PARTIAL = 0, 1, 2

# Verification entry points that must not quietly stop being run. Each is a
# script a developer would otherwise have to remember to invoke by hand; the
# point of a single entry point is that they no longer have to, and that promise
# is only safe while the workflow really does invoke them. If one drops out of
# the workflow, this reports it as uncovered and the run is PARTIAL — never a
# pass, because "you can stop running it yourself" would have become false
# without anything saying so.
#
# A suite-maintenance constant, like gates.py's own hardcoded workflow path:
# this file is about THIS repository's verification story, not a consumer's.
MUST_BE_COVERED = {
    "plugins/design-suite/bin/run_tests.py":
        "every bin/*_test.py — without it a broken test suite reads as green",
    "plugins/design-suite/bin/gate_consumer_compat.py":
        "unacknowledged consumer-breaking changes since the last release",
}

# Shell words that begin a line but are not programs to look for on PATH.
_NOT_A_PROGRAM = {
    "if", "then", "fi", "else", "elif", "for", "do", "done", "while", "until",
    "case", "esac", "echo", "cd", "set", "exit", "export", "local", "return",
    "test", "[", "[[", ":", "true", "false", "printf", "read", "shift",
}

# The limits, as data, so --json carries them too. Prose lives in the docstring;
# this is the short form a reader sees at the bottom of every single run.
LIMITS = [
    "reads your WORKING TREE, not the commit a reviewer will receive — "
    "uncommitted or untracked edits are included, and are not what CI would see",
    "gate_consumer_compat.py diffs COMMITTED git blobs, so it is blind to "
    "uncommitted work: it can report clean on a tree whose pending edits break a consumer",
    "reads the packages and tools installed on THIS machine — a gate that ran "
    "here may be skipped or fail elsewhere",
    "ran on one Python and one platform (reported above); behaviour that differs "
    "on another was not observed",
]


def _git(*args: str) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


# `cmd <<'PY'` / `cmd <<-EOF` — the opener of an inline heredoc. Most gates in
# this workflow pipe a Python program into `python3 -` exactly this way.
_HEREDOC_OPEN = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*$")


def strip_heredocs(cmd: str) -> str:
    """Drop inline heredoc bodies, keeping the lines that are actually shell.

    Without this, "the first word of each line" walks straight into the embedded
    Python and reports `import`, `from` and `except` as programs missing from
    PATH. That is not harmless noise: it is a tool inventing a dependency the
    gates never had and then announcing it absent — confident nonsense, in the
    one file whose job is to say what the environment really was.
    """
    out, terminator = [], None
    for line in cmd.splitlines():
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        out.append(line)
        m = _HEREDOC_OPEN.search(line)
        if m:
            terminator = m.group(1)
    return "\n".join(out)


def programs(commands: list[str]) -> dict[str, str | None]:
    """External programs the gate commands invoke -> where they resolve, or None.

    Derived from the commands themselves rather than from a hardcoded list, so a
    gate that starts shelling out to a new tool is reported without an edit here.
    First word of each shell line, after heredoc bodies are removed, minus shell
    keywords and anything that is not a bare program name. A heuristic, and the
    output says so: tuned to under-report (a tool invoked mid-pipeline is missed)
    rather than to invent dependencies that were never there.
    """
    found: dict[str, str | None] = {}
    for cmd in commands:
        for line in strip_heredocs(cmd).splitlines():
            token = line.strip().split(" ")[0] if line.strip() else ""
            if not token or token in _NOT_A_PROGRAM:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.+-]+", token):
                continue  # a path, a variable, a quoted string — not a bare name
            found.setdefault(token, shutil.which(token))
    return found


def environment(commands: list[str]) -> dict:
    """Everything about this machine that a gate's result could have depended on."""
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    dirty = [line for line in (status or "").splitlines() if line.strip()]
    return {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "git": {
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": head,
            "describe": _git("describe", "--tags", "--always", "--dirty"),
            "latestReleaseTag": _git("describe", "--tags", "--abbrev=0"),
            "dirtyEntries": len(dirty),
            # Porcelain v1 is a two-column status then a space; slicing a fixed
            # 3 clips the first character whenever the status column is only
            # one wide. Strip instead of counting characters.
            "dirtyFiles": [line[2:].strip() for line in dirty[:20]],
        },
        "programs": programs(commands),
    }


def coverage() -> list[tuple[str, str, bool]]:
    """(script, why-it-matters, is-it-invoked-by-some-gate) for each must-cover entry.

    Asks gates.py for the command list rather than re-reading the workflow — one
    parser, as everywhere else here.
    """
    commands = [cmd for _, cmd in gates.steps() if cmd]
    return [(path, why, any(path in cmd for cmd in commands))
            for path, why in sorted(MUST_BE_COVERED.items())]


def attest(run: bool = True) -> dict:
    """Build the attestation. With run=False, plan and environment only."""
    runnable, skipped, setup = gates.plan()
    env = environment([cmd for _, cmd in runnable])
    cov = coverage()
    uncovered = [(p, why) for p, why, ok in cov if not ok]

    report = {
        "verdict": None,
        "workflow": str(gates.WORKFLOW.relative_to(REPO)),
        "environment": env,
        "coverage": [{"script": p, "why": why, "invokedByAGate": ok}
                     for p, why, ok in cov],
        "gatesPlanned": len(runnable),
        "gatesSkipped": [{"name": n, "reason": why} for n, why in skipped],
        "runnerSetupSteps": setup,
        "limits": LIMITS,
        "results": [],
    }

    if not runnable:
        # No gate at all is never a pass, for the same reason gates.py exits 2 on
        # a filter that matched nothing.
        report["verdict"] = "PARTIAL"
        report["reason"] = ("no gate was runnable at all — nothing ran, which is "
                            "not the same as everything passing")
        return report

    if not run:
        report["verdict"] = "NOT RUN"
        report["reason"] = (f"--list: {len(runnable)} gate(s) planned, none executed. "
                            f"This is the plan and the environment, not a verdict.")
        return report

    results = gates.run_plan(runnable)
    report["results"] = [
        {"name": r.name, "ok": r.ok, "returncode": r.returncode,
         "seconds": round(r.seconds, 2),
         "tail": ((r.stderr or r.stdout).strip().splitlines()[-12:] if not r.ok else [])}
        for r in results
    ]

    failed = [r for r in results if not r.ok]
    if failed:
        report["verdict"] = "FAILED"
        report["reason"] = f"{len(failed)} gate(s) failed"
    elif skipped or uncovered:
        # Everything that DID run passed — and that is not the same claim as
        # "this tree is verified", so it does not get the same exit code.
        bits = []
        if skipped:
            bits.append(f"{len(skipped)} gate(s) could not run here")
        if uncovered:
            bits.append(f"{len(uncovered)} verification entry point(s) no gate invokes")
        report["verdict"] = "PARTIAL"
        report["reason"] = "; ".join(bits)
    else:
        report["verdict"] = "VERIFIED"
        report["reason"] = (f"all {len(results)} gate(s) ran and passed, under the "
                            f"environment recorded above")
    return report


def render(report: dict) -> list[str]:
    env = report["environment"]
    git = env["git"]
    # Built outside the f-string: the fallback text contains quotes, and nesting
    # them inside an f-string expression is a syntax error before Python 3.12.
    release_tag = git["latestReleaseTag"] or (
        "NONE — the consumer-compat baseline cannot be derived without one")
    out = [
        f"attesting {REPO}",
        f"  workflow            {report['workflow']}",
        "",
        "ENVIRONMENT — the conditions this verdict is conditional on",
        f"  python              {env['python']['implementation']} "
        f"{env['python']['version']} ({env['python']['executable']})",
        f"  platform            {env['platform']['system']} "
        f"{env['platform']['release']} {env['platform']['machine']}",
        f"  git branch          {git['branch'] or 'unknown'}",
        f"  git HEAD            {(git['head'] or 'unknown')[:12]} "
        f"({git['describe'] or 'no description'})",
        f"  latest release tag  {release_tag}",
    ]

    if git["dirtyEntries"]:
        out.append(f"  working tree        DIRTY — {git['dirtyEntries']} uncommitted "
                   f"entr{'y' if git['dirtyEntries'] == 1 else 'ies'}. Gates read "
                   f"these; a reviewer will not.")
        for f in git["dirtyFiles"]:
            out.append(f"                        {f}")
    else:
        out.append("  working tree        clean")

    missing = [p for p, where in env["programs"].items() if where is None]
    present = [p for p, where in env["programs"].items() if where is not None]
    out.append(f"  programs on PATH    {', '.join(sorted(present)) or 'none detected'}")
    if missing:
        # Named, never a count. A gate that needed one of these and ran anyway
        # produced a result that depended on its absence.
        out.append(f"  NOT on PATH         {', '.join(sorted(missing))} — any gate "
                   f"invoking one of these did not get the tool it named")
    out.append("                      (first word of each gate command line; "
               "under-reports tools invoked mid-pipeline)")
    out.append("")

    out.append("COVERAGE — entry points a developer would otherwise run by hand")
    for row in report["coverage"]:
        mark = "ok  " if row["invokedByAGate"] else "GAP "
        out.append(f"  {mark} {row['script']}")
        out.append(f"        {row['why']}")
        if not row["invokedByAGate"]:
            out.append("        NO GATE INVOKES IT — running this command is not "
                       "sufficient on its own any more.")
    out.append("")

    if report["results"]:
        out.append(f"GATES — {len(report['results'])} from {report['workflow']}")
        for r in report["results"]:
            out.append(f"  {'ok  ' if r['ok'] else 'FAIL'} {r['name'][:66]:68} "
                       f"{r['seconds']:5.1f}s")
        out.append("")

    if report["gatesSkipped"]:
        out.append(f"COULD NOT RUN — {len(report['gatesSkipped'])} gate(s), named "
                   f"rather than dropped:")
        for row in report["gatesSkipped"]:
            out.append(f"  SKIP {row['name']} — {row['reason']}")
        out.append("")

    out.append(f"VERDICT: {report['verdict']} — {report.get('reason', '')}")
    out.append("")
    out.append("LIMITS — what this run could not have caught, however green it is:")
    for limit in report["limits"]:
        out.append(f"  - {limit}")
    return out


def exit_code(report: dict) -> int:
    return {"VERIFIED": VERIFIED, "FAILED": FAILED}.get(report["verdict"], PARTIAL)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="report the plan and the environment, run no gate")
    ap.add_argument("--json", action="store_true",
                    help="emit the attestation as JSON")
    # There is deliberately no -k. A filtered run is by definition not the whole
    # verdict, and this command's entire contract is that it is. Use gates.py -k
    # while iterating, and this before you push.
    args = ap.parse_args(argv)

    report = attest(run=not args.list)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n".join(render(report)))

    if args.list:
        return VERIFIED if report["verdict"] == "NOT RUN" else PARTIAL
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
