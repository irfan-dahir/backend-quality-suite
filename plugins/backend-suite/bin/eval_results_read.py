#!/usr/bin/env python3
"""Refuse to let a recorded eval run read as a measurement when it is not one.

    python3 plugins/backend-suite/bin/eval_results_read.py --latest
    python3 plugins/backend-suite/bin/eval_results_read.py 2026-09-23T12-17-45-460Z
    python3 plugins/backend-suite/bin/eval_results_read.py <dir> --json
    python3 plugins/backend-suite/bin/eval_results_read.py --list

Exit 0 when every case in the run is quotable, 1 when at least one is not,
2 when the reader could not look at all. Stdlib only, like everything in this
directory.

## Why this exists

All 18 gates are static. `eval_suite_lint.py` reads case directories and grader
frontmatter; `eval_fixture_selftest.py` builds fixtures. **Neither ever opens
`evals/results/`**, so nothing checked that a recorded run measured anything,
and three distinct failures shipped through that gap (issue #143). Each was
caught by a human reading `aggregate-result.json` by hand, after quoting a wrong
number at least once:

  1. **A 0-turn arm credited for inaction.** All four `promote-component` cases
     ran their `without` arm at `turns: 0` in every run they ever produced — a
     bare slash command does not resolve without the plugin, so the arm ended
     before turn 1 and banked each case's absence-grader fraction for free. An
     absence grader passes loudest against a transcript that does not exist.
     The reported deltas (+0.33, +0.33, +0.20, 0.00) measured nothing.
  2. **Aborted runs scored rather than reported INERT** (#135). 45 runs died on
     `exit 1: You've hit your session limit` and still carried scores; one case
     scored 0.25 across six runs that produced nothing at all.
  3. **A ceiling that skips graders.** `--max-cost-usd` drops the LLM `criteria`
     graders and still reports `partial: false`. A skipped grader scores 0, so
     the case reads as a plugin failure rather than as an unasked question.

All three are one bug wearing three coats: **a run that measured nothing looked
exactly like a run that measured a low score.** That is this repo's governing
principle — an audit that reports nothing must never be indistinguishable from a
clean codebase — applied to the eval results themselves.

## What it refuses, and what it must not swallow

Every refusal below is paired with the positive case it must not swallow. A
reader that flags everything is as useless as one that flags nothing, so each
rule is written against a real artifact on both sides.

| Refusal | Must NOT flag |
|---|---|
| arm with every run at `turns: 0` → the case is **ONE-ARMED**, its Δ withheld | a live arm that merely scored low, or a short-but-nonzero arm |
| every run of every arm carries an `error` → **VOID**, not a score | a case where one run of several errored — that is noise, reported as a caveat, and the surviving runs stay quotable |
| `skippedPaidGraders: true`, or a grader whose `explanation` contains `skipped:` → **UNQUOTABLE**, score withheld | a grader that merely *failed*; failing is a result |
| `partial: true` on the run | a complete run |
| a permission denial in the trace or final message ("don't ask mode", "denied by the sandbox") → **UNQUOTABLE** | the skill name `fewer-permission-prompts`, which every run's skill list mentions |
| `turns: 1`, or a final message that is a background-task follow-up ("the background command has now finished") → **UNQUOTABLE** | a short multi-turn run whose final message is the answer |

A single-arm run (`ablation` other than `with-without`) is not one-armed by
defect — there was never a second arm to lose — so its surviving arm is quoted
with no Δ and no complaint.

## Gate, or command?

**Command.** `plugins/*/evals/results/` is gitignored (correctly: a result
embeds the last message, which quotes the fixture), so there is no committed
artifact for a gate to run against, and a gate that silently finds no results
directory is the very failure this file exists to name. The gate count stays at
18 and `CLAUDE.md` rule 3 is unchanged. What IS gated is this file's own
behaviour: `eval_results_read_test.py` runs under `run_tests.py`, which
`attest.py` already wires, so the reader cannot rot unnoticed even though the
data it reads is not in the tree.

Run it before quoting a number out of a results directory. That instruction is
in `evals/README.md`, where a person reading about results already is.

## Exit codes

Per `docs/DOC-ROLES.md`'s audit exit-code contract: **1 means I looked and this
is wrong, 2 means I could not look.** A missing directory, a missing or
unparseable `aggregate-result.json`, or a schema this reader does not understand
is 2 — never 0. Codes 3/4/5 belong to the doc-role resolver's states (absent,
stub) and have no meaning here, so they are deliberately not used rather than
given a second, local definition.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BIN = Path(__file__).resolve().parent
PLUGIN = BIN.parent
DEFAULT_RESULTS = PLUGIN / "evals" / "results"
AGGREGATE = "aggregate-result.json"

# The one schema this reader has been read against. A newer one may move the
# keys it depends on, and guessing would produce a confident wrong verdict.
KNOWN_SCHEMA_VERSIONS = {1}

SKIP_MARKER = "skipped:"

# A run whose agent was refused the tools it needed measured the harness's
# permission mode, not the plugin. Seen in real runs as "denied by don't-ask
# mode", "Bash is denied in this session", "denied by the sandbox". Written
# narrowly: the skill name `fewer-permission-prompts`, which every run lists,
# must never match.
PERMISSION_DENIAL_RE = re.compile(
    r"don['\u2019]?t[- ]ask(?: permission)? mode"
    r"|\bdenied by (?:the )?(?:current |session['\u2019]?s? )?"
    r"(?:permission|sandbox)"
    r"|\b(?:is|was|were|are|been) (?:blanket[- ]|all )?denied\b"
    r"|\bpermission denial"
    r"|\bdenied (?:it|them|both|that|those|all|reads?)\b"
    r"|\b(?:under|by) (?:this|the) (?:session['\u2019]?s? |current )?"
    r"permission mode\b",
    re.IGNORECASE)

# A final message that is a follow-up to a background task the agent started
# earlier is not the answer the graders were written against — the real answer
# was an earlier message, and the graders scored the postscript.
BACKGROUND_FOLLOWUP_RE = re.compile(
    r"\bbackground (?:command|task|job|shell|process)\b[^\n]{0,80}?"
    r"\b(?:has |had )?(?:now )?(?:finished|completed|returned|exited)\b",
    re.IGNORECASE)


class CannotDetermine(Exception):
    """Exit 2. Not a verdict — the absence of one."""


# --------------------------------------------------------------------------
# Locating the run


def resolve_dir(arg: str | None, latest: bool, root: Path) -> Path:
    if latest:
        if arg:
            raise CannotDetermine("--latest takes no positional argument.")
        runs = list_runs(root)
        if not runs:
            raise CannotDetermine(
                f"--latest: no run containing {AGGREGATE} under {root}. "
                f"Nothing to read is not a clean result.")
        return runs[-1]
    if not arg:
        raise CannotDetermine(
            "Name a results directory, or pass --latest. "
            "Reading an unspecified run would be reading no run.")
    cand = Path(arg)
    if not cand.is_dir():
        cand = root / arg
    if not cand.is_dir():
        raise CannotDetermine(f"{arg}: no such results directory (looked at "
                              f"{Path(arg)} and {root / arg}).")
    return cand


def list_runs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / AGGREGATE).is_file())


def load(run_dir: Path) -> dict[str, Any]:
    path = run_dir / AGGREGATE
    if not path.is_file():
        raise CannotDetermine(
            f"{run_dir}: no {AGGREGATE}. The directory exists, so an eyeball "
            f"says 'results are there' — but there is no measurement in it.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise CannotDetermine(f"{path}: cannot read ({exc}).") from exc
    except json.JSONDecodeError as exc:
        raise CannotDetermine(f"{path}: not valid JSON ({exc}).") from exc
    if not isinstance(data, dict):
        raise CannotDetermine(f"{path}: top level is {type(data).__name__}, "
                              f"expected an object.")
    version = data.get("schemaVersion")
    if version not in KNOWN_SCHEMA_VERSIONS:
        raise CannotDetermine(
            f"{path}: schemaVersion {version!r}, and this reader has only been "
            f"read against {sorted(KNOWN_SCHEMA_VERSIONS)}. Refusing to quote a "
            f"shape it has not seen — a key that moved would be reported as a "
            f"clean zero.")
    if not isinstance(data.get("cases"), list):
        raise CannotDetermine(f"{path}: no 'cases' list.")
    if not data["cases"]:
        raise CannotDetermine(
            f"{path}: zero cases. A run that executed nothing is not a run "
            f"that found nothing.")
    return data


# --------------------------------------------------------------------------
# Reading one run


def final_message(run: dict[str, Any]) -> str:
    """The run's last message, as the graders recorded it in `evidence`."""
    return "\n".join(str(g.get("evidence") or "")
                     for g in run.get("graders") or [] if isinstance(g, dict))


def trace_text(run: dict[str, Any]) -> str:
    """The trace, if it still exists. It lives under a tmp dir and is usually
    gone; absence is not evidence of a clean trace, which is why the final
    message is checked as well."""
    path = run.get("tracePath")
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def not_measured_flags(run: dict[str, Any]) -> list[str]:
    """Reasons a run that completed and scored still measured nothing."""
    flags: list[str] = []
    for source, text in (("trace", trace_text(run)),
                         ("final message", final_message(run))):
        m = PERMISSION_DENIAL_RE.search(text)
        if m:
            flags.append(
                f"permission denial in {source} ({m.group(0)!r}) — the agent "
                f"was refused tools it needed; this measured the harness's "
                f"permission mode, not the plugin")
            break
    if run.get("turns") == 1:
        flags.append("turns: 1 — a single turn cannot have done the task; "
                     "the graders scored whatever the first reply was")
    m = BACKGROUND_FOLLOWUP_RE.search(final_message(run))
    if m:
        flags.append(
            f"final message is a background-task follow-up ({m.group(0)!r}) — "
            f"the graders scored a postscript, not the answer")
    return flags


def run_flags(run: dict[str, Any]) -> list[str]:
    """Every reason this single run's numbers must not be quoted."""
    flags: list[str] = []
    if not run.get("error"):
        flags += [f"NOT MEASURED: {f}" for f in not_measured_flags(run)]
    if run.get("error"):
        flags.append(f"error: {run['error']}")
    if run.get("turns") == 0:
        flags.append("turns: 0 — the arm ended before turn 1; "
                     "absence graders banked their weight for free")
    if run.get("skippedPaidGraders"):
        flags.append("skippedPaidGraders: true — paid graders were not run, "
                     "and a grader that did not run scores 0")
    for grader in run.get("graders") or []:
        if SKIP_MARKER in (grader.get("explanation") or ""):
            flags.append(
                f"grader {grader.get('name')!r} skipped "
                f"({(grader.get('explanation') or '').strip()}) — it scores 0, "
                f"so the case reads as a plugin failure it was never asked about")
    return flags


def read_arm(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(runs, list) or not runs:
        return {"state": "MISSING", "n": 0, "errored": 0, "dead": 0,
                "flags": ["arm has no runs"], "score": None}
    errored = [r for r in runs if r.get("error")]
    dead = [r for r in runs if not r.get("error") and r.get("turns") == 0]
    flags: list[str] = []
    for i, r in enumerate(runs):
        flags += [f"run {i + 1}/{len(runs)}: {f}" for f in run_flags(r)]

    if len(errored) == len(runs):
        state = "VOID"          # every run aborted; #135's shape
    elif len(errored) + len(dead) == len(runs):
        state = "DEAD"          # nothing errored, nothing happened either
    elif errored or dead:
        state = "DEGRADED"      # some runs survived; quotable with a caveat
    else:
        state = "LIVE"

    live = [r for r in runs if not r.get("error") and r.get("turns") != 0]
    score = None
    if live:
        score = sum(float(r.get("score") or 0.0) for r in live) / len(live)
    return {"state": state, "n": len(runs), "errored": len(errored),
            "dead": len(dead), "flags": flags, "score": score,
            "turns": [r.get("turns") for r in runs]}


def read_case(case: dict[str, Any], two_armed: bool) -> dict[str, Any]:
    arms = case.get("arms")
    if not isinstance(arms, dict) or not arms:
        return {"name": case.get("name", "<unnamed>"), "verdict": "VOID",
                "arms": {}, "delta": None, "quotable": False,
                "reasons": ["no arms recorded — nothing ran"]}

    read = {name: read_arm(runs) for name, runs in arms.items()}
    reasons: list[str] = []
    for name, a in read.items():
        reasons += [f"[{name}] {f}" for f in a["flags"]]

    usable = {n: a for n, a in read.items() if a["state"] in ("LIVE", "DEGRADED")}
    skipped_graders = any(SKIP_MARKER in f or "skippedPaidGraders" in f
                          for f in reasons)
    not_measured = any("NOT MEASURED:" in f for f in reasons)

    if not usable:
        verdict, delta, quotable = "VOID", None, False
    elif skipped_graders or not_measured:
        verdict, delta, quotable = "UNQUOTABLE", None, False
    elif two_armed and len(usable) < len(read):
        verdict, delta, quotable = "ONE-ARMED", None, False
    elif not two_armed:
        verdict, delta, quotable = "SINGLE-ARM", None, True
    elif "with" in usable and "without" in usable:
        verdict, quotable = "QUOTABLE", True
        delta = usable["with"]["score"] - usable["without"]["score"]
    else:
        verdict, delta, quotable = "ONE-ARMED", None, False

    return {"name": case.get("name", "<unnamed>"), "verdict": verdict,
            "arms": read, "delta": delta, "quotable": quotable,
            "reasons": reasons,
            "scores": {n: a["score"] for n, a in read.items()}}


def read_run(data: dict[str, Any]) -> dict[str, Any]:
    suite = data.get("suite") or {}
    ablation = suite.get("ablation")
    two_armed = ablation == "with-without"
    cases = [read_case(c, two_armed) for c in data["cases"]
             if isinstance(c, dict)]
    reasons: list[str] = []
    if data.get("partial"):
        reasons.append("partial: true — the run did not finish; "
                       "its aggregates cover only what completed")
    quotable = bool(cases) and all(c["quotable"] for c in cases) and not reasons
    return {"startedAt": data.get("startedAt"), "ablation": ablation,
            "caseFilter": suite.get("caseFilter"),
            "claudeVersion": data.get("claudeVersion"),
            "costUsd": data.get("costUsd"), "cases": cases,
            "runReasons": reasons, "quotable": quotable}


# --------------------------------------------------------------------------
# Reporting


def fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def report(verdict: dict[str, Any], run_dir: Path) -> None:
    print(f"eval results: {run_dir}")
    print(f"  started {verdict['startedAt']}  claude {verdict['claudeVersion']}"
          f"  ablation {verdict['ablation']}"
          f"  filter {verdict['caseFilter'] or '(all)'}")
    for line in verdict["runReasons"]:
        print(f"  !! {line}")
    print()
    for case in verdict["cases"]:
        arms = "  ".join(
            f"{n}={fmt(a['score'])} turns={a['turns']} [{a['state']}]"
            for n, a in case["arms"].items())
        delta = (f"Δ {case['delta']:+.3f}" if case["delta"] is not None
                 else "Δ WITHHELD")
        print(f"  {case['verdict']:<11} {case['name']}")
        print(f"              {arms}   {delta}")
        for line in case["reasons"]:
            print(f"              - {line}")
    print()
    bad = [c for c in verdict["cases"] if not c["quotable"]]
    if verdict["quotable"]:
        print(f"QUOTABLE: all {len(verdict['cases'])} case(s) measured "
              f"something on both arms. The deltas above may be quoted.")
    else:
        print(f"NOT QUOTABLE: {len(bad)} of {len(verdict['cases'])} case(s) "
              f"did not measure what their score claims. Do not quote a number "
              f"from this run without saying which.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read an eval results directory and refuse to let it read "
                    "as a measurement when it is not one.")
    ap.add_argument("run", nargs="?",
                    help="results directory, or a run id under evals/results/")
    ap.add_argument("--latest", action="store_true",
                    help="read the most recent run under the results root")
    ap.add_argument("--list", action="store_true",
                    help="list runs that carry an aggregate-result.json")
    ap.add_argument("--results-root", default=str(DEFAULT_RESULTS),
                    help="override the results root (default: %(default)s)")
    ap.add_argument("--json", action="store_true",
                    help="emit the verdict as JSON instead of prose")
    args = ap.parse_args()

    root = Path(args.results_root)
    try:
        if args.list:
            runs = list_runs(root)
            if not runs:
                raise CannotDetermine(
                    f"no run containing {AGGREGATE} under {root}.")
            for path in runs:
                print(path.name)
            return 0
        run_dir = resolve_dir(args.run, args.latest, root)
        verdict = read_run(load(run_dir))
    except CannotDetermine as exc:
        print(f"CANNOT DETERMINE: {exc}", file=sys.stderr)
        print("Exit 2, not 0: a reader that cannot find or parse the file must "
              "not report clean.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"dir": str(run_dir), **verdict}, indent=2))
    else:
        report(verdict, run_dir)
    return 0 if verdict["quotable"] else 1


if __name__ == "__main__":
    sys.exit(main())
