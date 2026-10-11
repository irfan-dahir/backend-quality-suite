#!/usr/bin/env python3
"""A markdown design review of a branch's changes against a base ref.

    python3 bin/design_review_pr.py main                 review HEAD + working tree vs main
    python3 bin/design_review_pr.py origin/main --out review.md
    python3 bin/design_review_pr.py main --envelopes .backend-suite/findings
                                                         reuse collected envelopes, run nothing
    python3 bin/design_review_pr.py main --post 123      ALSO post it as a PR comment (gh)

Runs every live audit that emits the common findings envelope, then keeps only
what touches the diff: findings on changed lines first, then findings elsewhere
in changed files, then — always — every audit that could not check. Findings in
untouched files are counted, never silently dropped ("12 elsewhere, not shown").

WHAT IT WRITES. Prints the review to stdout (or `--out`). Audit envelopes go to a
temporary directory, not `.backend-suite/findings/`, so `/design-debt`'s data is
not replaced by a diff-scoped run — but an audit that saves its own raw report on
every run (e.g. audit_tokens) still does that, exactly as when run by hand.

IT NEVER POSTS ANYTHING unless `--post <PR>` is passed, and then only through
`gh pr comment`. Posting is outward-facing; the skill doc requires the user's
explicit confirmation, per post, before an agent passes that flag.

Why the audits run on the whole project and are then filtered, rather than being
pointed at the changed files: none of them takes a file list, and several are
cross-file by nature (an unused token is unused across the project, not within
one file). Filtering a whole-project run is the only scoping that does not change
what each audit means.

Not scoped, and said so: an audit without `--findings` has no `{file, line}`
records to filter, so it is listed as unscopable rather than run and reported as
clean. Untracked files are not in `git diff`, so they are not reviewed.

Exit 0 review printed, nothing on changed lines; 1 findings on changed lines;
2 could not review (bad ref, not a git repo, or no audit managed to check
anything — a review of nothing is not a clean review). Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _bootstrap import project_root  # noqa: E402

from backend_suite.engine import audit_discovery  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402

BIN = Path(__file__).resolve().parent
MARK = {F.CRITICAL: "🔴", F.SHOULD_FIX: "🟡", F.FYI: "🔵"}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class ReviewError(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ReviewError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.returncode}")
    return proc.stdout


def changed_lines(repo: Path, base: str) -> dict[str, set[int]]:
    """{path relative to `repo`: added/modified line numbers} vs merge-base(base, HEAD).

    Compared against the working tree, so uncommitted edits are reviewed too. A
    file that only lost lines maps to an empty set: changed, with no line to pin.
    """
    toplevel = Path(_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
    _git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    merge_base = _git(repo, "merge-base", base, "HEAD").strip()
    diff = _git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", merge_base)
    prefix = repo.resolve().relative_to(toplevel).as_posix()
    prefix = "" if prefix == "." else prefix + "/"

    out: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None
            if target != "/dev/null" and target.startswith("b/"):
                path = target[2:]
                if path.startswith(prefix):
                    current = path[len(prefix):]
                    out.setdefault(current, set())
        elif line.startswith("--- ") or current is None:
            continue
        elif (m := HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            out[current].update(range(start, start + count))
    return out


def _status(code: int | None) -> str:
    return {0: "clean", 1: "findings", 2: "refused"}.get(code, "crashed")


def run_audits(repo: Path, out_dir: Path, scripts: list[Path], timeout: float) -> list[dict]:
    rows = []
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    for script in scripts:
        name = audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_")
        entry = audit_discovery.disabled_reason(script)
        if entry:
            rows.append({"audit": script.stem, "status": "disabled",
                         "reason": f"{entry['reason']} (path back: {entry['pathBack']})"})
            continue
        if not audit_discovery.supports_findings_flag(script):
            rows.append({"audit": script.stem, "status": "unscopable",
                         "reason": "emits no findings envelope, so its results cannot be "
                                   "scoped to changed lines; not run"})
            continue
        path = out_dir / f"{name}.json"
        t0 = time.time()
        try:
            proc = subprocess.run([sys.executable, str(script), "--findings", str(path)],
                                  cwd=repo, env=env, capture_output=True, text=True,
                                  timeout=timeout)
            code, tail = proc.returncode, (proc.stderr or proc.stdout or "").strip().splitlines()
        except subprocess.TimeoutExpired:
            code, tail = None, [f"timed out after {timeout:.0f}s"]
        status = _status(code)
        envelope = None
        if status in ("clean", "findings") and path.is_file():
            try:
                envelope = json.loads(path.read_text())
            except (OSError, ValueError):
                envelope = None
        if status == "findings" and envelope is None:
            status = "unclear"
        row = {"audit": script.stem, "status": status, "exitCode": code,
               "seconds": round(time.time() - t0, 1), "envelope": envelope}
        if status not in ("clean", "findings"):
            flagged = [t for t in tail if re.search(r"REFUS|INERT|refus|does not|no ", t)]
            row["reason"] = (flagged or tail or [f"exit {code}"])[0]
        rows.append(row)
    return rows


def rows_from_envelopes(directory: Path) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.json")):
        try:
            env = json.loads(path.read_text())
        except (OSError, ValueError):
            rows.append({"audit": path.stem, "status": "unclear", "reason": "unreadable envelope"})
            continue
        if not isinstance(env, dict) or "findings" not in env:
            rows.append({"audit": path.stem, "status": "unclear", "reason": "not a findings envelope"})
            continue
        rows.append({"audit": env.get("audit", path.stem),
                     "status": "findings" if env["findings"] else "clean", "envelope": env})
    return rows


def _norm(file: str, repo: Path) -> str:
    p = Path(file)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return Path(os.path.normpath(p.as_posix())).as_posix()


def classify(rows: list[dict], changed: dict[str, set[int]], repo: Path) -> dict:
    on_line, in_file, elsewhere = [], [], 0
    empty_sweeps = []
    for row in rows:
        env = row.get("envelope")
        if env is None:
            continue
        records = env.get("findings", [])
        if not records and env.get("reports") == F.REPORTS_CHECKS:
            empty_sweeps.append((row["audit"], "checks-polarity audit recorded no checks"))
        elif not records and not env.get("scanned"):
            empty_sweeps.append((row["audit"], "no findings and nothing recorded as scanned"))
        for record in records:
            if record.get("passed") is True:
                continue
            file = record.get("file")
            path = _norm(file, repo) if file else None
            if path is None or path not in changed:
                elsewhere += 1
                continue
            item = {**record, "audit": env.get("audit", row["audit"]), "file": path}
            line = record.get("line")
            (on_line if isinstance(line, int) and line in changed[path] else in_file).append(item)
    key = lambda r: (list(F.SEVERITIES).index(r.get("severity", F.SHOULD_FIX))
                     if r.get("severity") in F.SEVERITIES else 1, r["file"], r.get("line") or 0)
    return {"onLine": sorted(on_line, key=key), "inFile": sorted(in_file, key=key),
            "elsewhere": elsewhere, "emptySweeps": empty_sweeps}


def _fmt(r: dict) -> str:
    where = f"`{r['file']}:{r['line']}`" if r.get("line") else f"`{r['file']}`"
    return (f"- {MARK.get(r.get('severity'), '🟡')} {where} — {r.get('summary', '').strip()} "
            f"_({r['audit']} / {r.get('category', '?')})_")


def render(base: str, changed: dict, rows: list[dict], c: dict) -> str:
    ran = [r for r in rows if r["status"] in ("clean", "findings")]
    couldnt = [r for r in rows if r["status"] not in ("clean", "findings")]
    out = [f"## Design review vs `{base}`", "",
           f"{len(changed)} changed file(s); {len(ran)} audit(s) checked, "
           f"{len(couldnt)} could not check (listed below — not a pass).", ""]
    out.append(f"### Findings on changed lines ({len(c['onLine'])})")
    out += [_fmt(r) for r in c["onLine"]] or ["_None._"]
    out += ["", f"### Elsewhere in changed files ({len(c['inFile'])})"]
    out += [_fmt(r) for r in c["inFile"]] or ["_None._"]
    out += ["", f"{c['elsewhere']} finding(s) in files this change does not touch — not shown."]
    out += ["", f"### Could not check ({len(couldnt) + len(c['emptySweeps'])})"]
    if not couldnt and not c["emptySweeps"]:
        out.append("_Every audit checked._")
    for r in couldnt:
        out.append(f"- ⚪ **{r['audit']}** — {r['status']}: {r.get('reason') or 'no reason given'}")
    for audit, why in c["emptySweeps"]:
        out.append(f"- ⚪ **{audit}** — ran, but {why}; not counted as clean")
    out += ["", "_Report-only: generated by backend-suite `design_review_pr.py`; nothing was "
                "changed. Audits run on the whole project and are filtered to this diff._"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", help="base ref to diff against, e.g. main or origin/main")
    ap.add_argument("--repo", help="project root (default: the detected project)")
    ap.add_argument("-k", metavar="SUBSTR", help="only audits whose name contains SUBSTR")
    ap.add_argument("--timeout", type=float, default=120.0, help="per-audit timeout, seconds")
    ap.add_argument("--envelopes", metavar="DIR",
                    help="use findings envelopes already in DIR instead of running audits")
    ap.add_argument("--out", metavar="FILE", help="write the review here instead of stdout")
    ap.add_argument("--post", metavar="PR",
                    help="ALSO post the review as a comment on PR via `gh pr comment`. "
                         "Outward-facing: only with the user's explicit go-ahead")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve() if args.repo else project_root()
    try:
        changed = changed_lines(repo, args.base)
    except ReviewError as exc:
        print(f"design_review_pr: cannot diff against {args.base!r}: {exc}", file=sys.stderr)
        return 2

    if args.envelopes:
        directory = Path(args.envelopes)
        if not directory.is_dir():
            print(f"design_review_pr: --envelopes {directory} is not a directory", file=sys.stderr)
            return 2
        rows = rows_from_envelopes(directory)
    else:
        scripts = audit_discovery.discover(BIN)
        if args.k:
            scripts = [s for s in scripts if args.k.lower() in s.stem.lower()]
        with tempfile.TemporaryDirectory(prefix="design-review-") as tmp:
            rows = run_audits(repo, Path(tmp), scripts, args.timeout)

    c = classify(rows, changed, repo)
    text = render(args.base, changed, rows, c)
    if args.out:
        Path(args.out).write_text(text)
    else:
        sys.stdout.write(text)

    checked = [r for r in rows if r["status"] in ("clean", "findings")]
    if not checked:
        print("design_review_pr: no audit managed to check anything — this review covers "
              "nothing, which is not a clean review.", file=sys.stderr)
        return 2

    if args.post:
        proc = subprocess.run(["gh", "pr", "comment", str(args.post), "--body-file", "-"],
                              cwd=repo, input=text, text=True, capture_output=True)
        if proc.returncode != 0:
            print(f"design_review_pr: gh pr comment failed: {proc.stderr.strip()}", file=sys.stderr)
            return 2
        print(f"design_review_pr: posted to PR {args.post}", file=sys.stderr)
    return 1 if c["onLine"] else 0


if __name__ == "__main__":
    sys.exit(main())
