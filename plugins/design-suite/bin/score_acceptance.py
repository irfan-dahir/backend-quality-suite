#!/usr/bin/env python3
"""Score the suite's own checks against a list of bugs known to be real.

A check's own report cannot tell you whether it works. The only thing that can is
a set of defects somebody has already confirmed, left in place, and written down
— which is what RFC-0002's decision 2 did deliberately, and what this script
turns into a number.

    python3 plugins/design-suite/bin/score_acceptance.py \
        --spec docs/proposals/RFC-0002-2b-acceptance.json \
        --project portal=<path> --project mobile=<path>

## Why the spec is a file and the roots are arguments

The expectations name real repositories, so the spec lives in the consuming
repo's `docs/`. This script is in the universal plugin and therefore knows the
name of no project: it is handed roots, and refuses to run on a spec whose
projects it was not given. A spec mapping to a missing root scores nothing rather
than scoring everything it *could* reach and printing a total that looks like a
full run.

## Read-only

Both tools it drives write nothing: `survey --check` is explicitly safe to point
at a repository you do not own, and `doctor` only reads. Pointing this at a
client checkout changes nothing in it.

Exit codes follow `docs/DOC-ROLES.md`: 0 when every expectation is met, 1 when
any is missed, 2 when the spec or the roots make the question unanswerable —
never a score of zero dressed up as a pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
SURVEY = BIN / "survey.py"
DOCTOR = BIN / "doctor.py"


class Unanswerable(RuntimeError):
    """Exit 2. The score could not be computed, which is not a score of zero."""


def survey_findings(root: Path) -> list[dict]:
    out = subprocess.run([sys.executable, str(SURVEY), "--project-root", str(root),
                          "--check", "--json"], capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise Unanswerable(f"survey --check refused on {root}: {out.stderr.strip()}")
    try:
        return json.loads(out.stdout)["findings"]
    except (ValueError, KeyError) as exc:
        raise Unanswerable(f"survey --check produced no readable JSON for {root}: {exc}")


def doctor_output(root: Path) -> str:
    # doctor resolves its project from the working directory rather than a flag.
    out = subprocess.run([sys.executable, str(DOCTOR)], cwd=str(root),
                         capture_output=True, text=True)
    return out.stdout + out.stderr


def match_survey(findings: list[dict], match: dict) -> tuple[bool, str]:
    hits = [f for f in findings
            if f.get("kind") == match["kind"]
            and match.get("pathContains", "") in str(f.get("path", ""))
            and (not match.get("requireProseMention") or f.get("proseMentions"))]
    need = match.get("minCount", 1)
    if len(hits) >= need:
        paths = ", ".join(str(h.get("path")) for h in hits[:4])
        return True, f"{len(hits)} × {match['kind']}: {paths}"
    return False, (f"{len(hits)} of {need} required {match['kind']} finding(s) "
                   f"matching {match.get('pathContains', '')!r}")


def match_doctor(output: str, match: dict) -> tuple[bool, str]:
    needle = match["stdoutContains"]
    for line in output.splitlines():
        if needle in line:
            return True, line.strip()
    return False, f"doctor never printed {needle!r}"


def score(spec: dict, roots: dict[str, Path]) -> list[dict]:
    missing = sorted(set(spec.get("projects", {})) - set(roots))
    if missing:
        raise Unanswerable(
            f"spec names project(s) {missing} and no --project gave a root for them. "
            f"Refusing to score a subset: a partial run and a full run print the same "
            f"kind of number.")

    survey_cache: dict[str, list[dict]] = {}
    doctor_cache: dict[str, str] = {}
    results = []
    for exp in spec["expectations"]:
        project = exp["project"]
        root = roots.get(project)
        if root is None:
            raise Unanswerable(f"expectation {exp['id']} names unknown project {project!r}")
        tool = exp["tool"]
        if tool == "survey-check":
            if project not in survey_cache:
                survey_cache[project] = survey_findings(root)
            met, detail = match_survey(survey_cache[project], exp["match"])
        elif tool == "doctor":
            if project not in doctor_cache:
                doctor_cache[project] = doctor_output(root)
            met, detail = match_doctor(doctor_cache[project], exp["match"])
        else:
            raise Unanswerable(f"expectation {exp['id']} names unknown tool {tool!r}")
        results.append({**exp, "caught": met, "detail": detail})

    # Every project gets a total, including one no expectation happened to
    # exercise: the score is only half the result, and a check that catches six
    # bugs by reporting six hundred things has caught nothing.
    for project, root in roots.items():
        survey_cache.setdefault(project, survey_findings(root))

    for project, findings in sorted(survey_cache.items()):
        results.append({"_totals": project, "findings": len(findings)})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True, help="acceptance spec JSON")
    ap.add_argument("--project", action="append", default=[], metavar="KEY=PATH",
                    help="root for a project the spec names; repeatable")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    roots: dict[str, Path] = {}
    for pair in args.project:
        if "=" not in pair:
            print(f"score: --project wants KEY=PATH, got {pair!r}", file=sys.stderr)
            return 2
        key, path = pair.split("=", 1)
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            print(f"score: {key}: {path} is not a directory", file=sys.stderr)
            return 2
        roots[key] = root

    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        results = score(spec, roots)
    except Unanswerable as exc:
        print(f"score: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"score: spec unreadable: {exc}", file=sys.stderr)
        return 2

    expectations = [r for r in results if "_totals" not in r]
    totals = [r for r in results if "_totals" in r]
    caught = sum(1 for r in expectations if r["caught"])

    if args.json:
        print(json.dumps({"spec": spec.get("name"), "caught": caught,
                          "of": len(expectations), "results": results}, indent=2))
    else:
        print(f"{spec.get('name')} — {caught} of {len(expectations)}\n")
        for r in expectations:
            print(f"  {'✔' if r['caught'] else '✗'} {r['id']}  [{r['project']}/{r['tool']}]")
            print(f"      {r['bug']}")
            print(f"      {r['detail']}")
        print()
        for t in totals:
            # Printed beside the score because a check that catches everything by
            # reporting everything has not earned anything: the ratio is the
            # other half of the result (#104's ≤5%-wrong bar).
            print(f"  {t['_totals']}: {t['findings']} total survey --check finding(s)")
        print(f"\n{caught} of {len(expectations)} known bug(s) caught.")
    return 0 if caught == len(expectations) else 1


if __name__ == "__main__":
    sys.exit(main())
