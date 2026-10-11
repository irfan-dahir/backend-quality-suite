#!/usr/bin/env python3
"""One JSON document summarising the run-health of every audit, agent-first.

    python3 plugins/backend-suite/bin/repo_health.py                 human table
    python3 plugins/backend-suite/bin/repo_health.py --json           the dashboard
    python3 plugins/backend-suite/bin/repo_health.py --json > .backend-suite/repo-health.json

An agent starting a session on this repo should not have to run N audit
commands to learn its posture. This runs every `audit_*.py` fresh — bare, no
flags an agent would have to already know to pass — and reports, per audit:

  * `ran`             did the process even complete, or did it crash
  * `status`          "clean" | "findings" | "refused" | "crashed" |
                       "disabled" (switched off suite-wide in
                       `backend_suite.engine.audit_discovery.DISABLED`; not run,
                       listed with its reason, never rendered as a pass), from the
                       audit's OWN exit code (0 / 1 / 2 / anything else) —
                       never re-derived from parsing stdout, which is exactly
                       the kind of guess the exit-code convention exists to
                       replace
  * `severities`      counts by critical / should-fix / fyi, from the common
                       findings envelope (`backend_suite/engine/findings.py`)
                       when the audit supports `--findings`; `null` — not
                       `{}` — when it does not, so "no severities" is never
                       confused with "counted and found none"
  * `configured`      false when `status == "refused"`: this project has not
                       given the audit what it needs (missing profile keys,
                       an adapter without the capability, an empty sweep).
                       Refused is never reported as passed, and never
                       reported as crashed.
  * `timestamp`       when THIS run happened, per audit, not one blanket
                       timestamp for the whole document — a 40-second audit
                       run before a 2-second one and an agent diffing two
                       dashboards should be able to tell which entry is stale.

## Relationship to /quality-debt (quality_debt.py) — read this before extending either

They look similar and answer different questions on purpose:

  quality_debt.py     grades EXISTING `.backend-suite/findings/*.json` files.
                      Never runs an audit — deliberately, so the dashboard
                      itself can never be the reason a baselined audit's
                      output changes. Answers "how much debt, by category,
                      last time each audit ran". Silent about an audit that
                      has never been run unless the profile declares it
                      under `debt.audits`.

  repo_health.py      RUNS every audit fresh, this instant, and reports
                      whether it ran at all, separately from what it found.
                      Answers "if I did nothing else right now, which audits
                      would even work on this project" — a question
                      quality_debt.py cannot answer, because a project that
                      has literally never run any audit has no findings
                      files for it to read, and it does not execute code to
                      go find out.

Concretely: `quality_debt.py` treats a config problem and "nobody has run this
yet" identically — both are just an absent file. This treats a config error
as a distinct, reportable status (`refused`) it cannot see any other way
without executing the audit.

This is genuinely additive, not a second aggregator competing with the first:
it writes the same `--findings` envelopes quality_debt.py already reads, so
running this also means `/quality-debt` has fresh data afterward.

## Why this is not folded into quality_debt.py as a flag

`--dashboard` on `quality_debt.py` would have to secretly start running code
from a script whose entire documented contract — restated three times in its
own docstring and its skill file — is that it never does. That contract is
load-bearing for `capture-baselines.sh`: an audit's baselined output must only
move when something *reviews and re-baselines* it, never as a side effect of
someone asking "what's my design debt". A flag that runs audits would make
`python3 quality_debt.py` and `python3 quality_debt.py --dashboard` have
different truthfulness properties depending on a flag easy to forget, which
is the sort of footgun this whole suite exists to design out.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402

REPO = project_root()

from backend_suite.engine import findings as F  # noqa: E402
from backend_suite.engine import audit_discovery  # noqa: E402
from backend_suite import harness_files  # noqa: E402
from backend_suite.engine import harness_hooks  # noqa: E402

BIN = Path(__file__).resolve().parent

STATUS_BY_CODE = {0: "clean", 1: "findings"}  # 2 -> "refused", handled specially


def discover() -> list[Path]:
    """Every `audit_*.py` this plugin ships, minus tests and non-audits.

    Kept as a thin wrapper (rather than inlining `audit_discovery.discover()`
    at call sites) so this stays the one obvious place a caller of this module
    looks for "what audits exist".
    """
    return audit_discovery.discover(BIN)


def _findings_path(script: Path) -> Path:
    # The envelope name an audit writes under is not always its stem with
    # `audit_` stripped (audit_focus_order.py writes "focus-order", a hyphen,
    # not "focus_order") — grepped from the script's own source so this can
    # never drift the way a second hand-maintained name-mapping would. See
    # audit_discovery.envelope_name's docstring for the incident this fixes.
    name = audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_")
    return F.default_path(REPO, name)


def _supports_findings_flag(script: Path) -> bool:
    return audit_discovery.supports_findings_flag(script)


def _severity_counts(envelope: dict | None) -> dict | None:
    if envelope is None:
        return None
    counts = {s: 0 for s in F.SEVERITIES}
    for record in envelope.get("findings", []):
        sev = record.get("severity")
        if sev in counts:
            counts[sev] += 1
    return counts


def _disabled_row(script: Path, entry: dict) -> dict:
    """A disabled audit is listed, never run, and never rendered as clean.

    Dropping it from the table would make "switched off because it was 100%
    wrong" indistinguishable from "this project has no accessibility problems".
    So it gets its own status — not `clean`, not `refused` (which means *this
    project* did not configure it), not `crashed` — and carries its reason.
    """
    return {
        "audit": script.stem,
        "ran": False,
        "status": "disabled",
        "configured": None,
        "exitCode": None,
        "durationSeconds": 0.0,
        "supportsFindingsEnvelope": _supports_findings_flag(script),
        "severities": None,
        "findingsCount": None,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "message": entry["reason"],
        "disabledDetail": entry["detail"],
        "disabledPathBack": entry["pathBack"],
    }


def run_one(script: Path, timeout: float) -> dict:
    entry = audit_discovery.disabled_reason(script)
    if entry:
        return _disabled_row(script, entry)

    audit = script.stem
    supports_findings = _supports_findings_flag(script)
    findings_path = _findings_path(script)
    before_mtime = findings_path.stat().st_mtime if findings_path.is_file() else None

    cmd = [sys.executable, str(script)]
    if supports_findings:
        cmd.append("--findings")

    started = datetime.now(timezone.utc)
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout,
        )
        code = proc.returncode
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        timed_out = False
    except subprocess.TimeoutExpired:
        code, tail, timed_out = None, [f"timed out after {timeout:.0f}s"], True
    duration = time.time() - t0

    if timed_out:
        status, ran, configured = "crashed", False, None
    elif code == 0:
        status, ran, configured = "clean", True, True
    elif code == 1:
        status, ran, configured = "findings", True, True
    elif code == 2:
        status, ran, configured = "refused", True, False
    else:
        status, ran, configured = "crashed", False, None

    envelope = None
    if supports_findings and findings_path.is_file():
        after_mtime = findings_path.stat().st_mtime
        # Only trust the envelope if this run actually touched it — a script
        # that crashed before writing must not report a stale file's counts
        # as if they came from this run.
        if before_mtime is None or after_mtime != before_mtime:
            try:
                envelope = json.loads(findings_path.read_text())
            except (OSError, ValueError):
                envelope = None

    # Exit 1 is documented as "findings" (`audit_contract_headers.py`'s own
    # comment: "1 means I looked and this is wrong, 2 means I could not
    # look"). Issue #119 closed the gap for audit_focus_order, audit_
    # reduced_motion, audit_accessibility, and audit_tokens — a could-not-
    # look condition in those four now always exits 2, so exit 1 from them
    # always carries a real envelope. This downgrade stays in place as a
    # safety net for the audits #119 did not touch (still free to fall
    # through to a bare exit 1 with no envelope on a config problem); it
    # should simply never fire for the four fixed audits going forward.
    # Once every audit in the suite honours the contract, this branch can be
    # deleted rather than simplified further — there will be nothing left to
    # guess about.
    if status == "findings" and supports_findings and envelope is None:
        status, configured = "unclear", None

    row = {
        "audit": audit,
        "ran": ran,
        "status": status,
        "configured": configured,
        "exitCode": code,
        "durationSeconds": round(duration, 2),
        "supportsFindingsEnvelope": supports_findings,
        "severities": _severity_counts(envelope),
        "findingsCount": None,
        "timestamp": started.isoformat(timespec="seconds"),
    }
    if envelope is not None:
        row["findingsCount"] = len(envelope.get("findings", []))
        row["reports"] = envelope.get("reports", F.REPORTS_VIOLATIONS)
        if envelope.get("scanned") is not None:
            row["scanned"] = envelope["scanned"]
    if status in ("crashed", "refused", "unclear"):
        row["message"] = tail[-1] if tail else None
    return row


MARK = {"clean": "✅", "findings": "🟡", "refused": "⚪", "crashed": "🔴",
        "unclear": "⚠️", "disabled": "⛔"}


def render(rows: list[dict]) -> str:
    width = max([len("AUDIT")] + [len(r["audit"]) for r in rows])
    lines = [f"{'AUDIT'.ljust(width)}  STATUS     FINDINGS  TIME   NOTE",
             f"{'-' * width}  ---------  --------  -----  ----"]
    for r in rows:
        mark = MARK.get(r["status"], "?")
        findings = "-" if r["findingsCount"] is None else str(r["findingsCount"])
        note = r.get("message") or ""
        lines.append(
            f"{r['audit'].ljust(width)}  {mark} {r['status']:<8} {findings:>8}  "
            f"{r['durationSeconds']:5.1f}s  {note}"
        )
    n_clean = sum(1 for r in rows if r["status"] == "clean")
    n_findings = sum(1 for r in rows if r["status"] == "findings")
    n_refused = sum(1 for r in rows if r["status"] == "refused")
    n_crashed = sum(1 for r in rows if r["status"] == "crashed")
    n_unclear = sum(1 for r in rows if r["status"] == "unclear")
    n_disabled = sum(1 for r in rows if r["status"] == "disabled")
    lines.append("")
    lines.append(
        f"{len(rows)} audit(s): {n_clean} clean, {n_findings} with findings, "
        f"{n_refused} not configured for this project, {n_unclear} unclear "
        f"(exited nonzero without a findings envelope), {n_crashed} crashed, "
        f"{n_disabled} disabled (did not run at all)."
    )
    if n_crashed:
        lines.append("A crash is not a pass — see exitCode/message for the crashed row(s).")
    if n_unclear:
        lines.append("Unclear rows are a gap in that audit's own exit-code discipline, "
                      "not something this dashboard can resolve.")
    if n_disabled:
        lines.append("")
        lines.append("Disabled audits did not run and tell you NOTHING about this project — "
                     "read them as a gap in coverage, not as a pass:")
        for r in rows:
            if r["status"] != "disabled":
                continue
            lines.append(f"  ⛔ {r['audit']}: {r.get('disabledDetail', r.get('message', ''))}")
            lines.append(f"     path back: {r.get('disabledPathBack', '')}")
    return "\n".join(lines)


def render_list(scripts: list[Path]) -> str:
    """The discovered audits as TSV, for a caller that cannot import Python.

    `capture-baselines.sh` is bash and used to carry its own hand-written list of
    eight audits. That second registry is what broke the oracle: `discover()`
    grew to 17 audits and two of the eight became DISABLED, so the documented
    pre-refactor check reported `BASELINE FAILED` on a healthy repo. A registry
    with two copies has no answer to "what audits exist", so this is the seam —
    one line per audit, tab-separated, no formatting a shell has to parse:

        <stem>\t<live|disabled>\t<yes|no findings flag>\t<reason or ->\t<path>\t<envelope name or ->

    `<path>` is relative to the plugin root, not just a stem, because not every
    audit lives in `bin/` — `audit_mock_api.py` lives at
    `backend_suite/engine/mockapi/audit_mock_api.py` (issue #120). A caller that
    assumed `bin/<stem>.py` got "No such file or directory" for that one audit,
    which is the same "discovered but then dropped anyway" bug one layer later.

    `<envelope name>` exists for the identical reason: `capture-baselines.sh`
    used to build the findings-artifact path as `<stem>.json`
    (`audit_tokens.json`), but the audit writes `tokens.json` — the same bug
    fixed in `_findings_path()` above (issue #123's PR), duplicated here because
    the shell script could not call that function and had to guess for itself.

    Deliberately not JSON: every consumer of this is a `while IFS=$'\\t' read`
    loop, and adding a JSON dependency to a zero-dependency shell script would
    just move the coupling somewhere harder to see.
    """
    lines = []
    for script in scripts:
        entry = audit_discovery.disabled_reason(script)
        supports = _supports_findings_flag(script)
        lines.append("\t".join((
            script.stem,
            "disabled" if entry else "live",
            "yes" if supports else "no",
            entry["reason"] if entry else "-",
            str(script.resolve().relative_to(PLUGIN_ROOT)),
            (audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_"))
            if supports else "-",
        )))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("-k", metavar="SUBSTR", help="only audits whose name contains SUBSTR")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="per-audit timeout in seconds (default 120)")
    ap.add_argument("--list", action="store_true",
                    help="enumerate the discovered audits as TSV and exit, running none")
    args = ap.parse_args()

    scripts = discover()
    if args.k:
        scripts = [s for s in scripts if args.k.lower() in s.stem.lower()]
    if args.list and scripts:
        print(render_list(scripts))
        return 0
    if not scripts:
        print(f"no audit matched {args.k!r}. Nothing ran, which is not the same as "
              f"everything passing.", file=sys.stderr)
        return 2

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [run_one(script, args.timeout) for script in scripts]

    document = {
        "schemaVersion": F.SCHEMA_VERSION,
        "generatedAt": generated_at,
        "repo": str(REPO),
        "audits": rows,
        # Which harnesses would not see the AGENTS.md instructions (NOT WIRED /
        # SHADOWED). Listed, never folded into a pass.
        "harnessWiring": [{"harness": h, "status": st, "detail": d}
                          for h, st, d in harness_files.wiring(REPO)],
        # Per harness: WIRED / NOT WIRED / UNKNOWN for session-start and
        # after-edit, plus git pre-commit. Never implies coverage it cannot see.
        "hookWiring": harness_hooks.status(REPO),
    }

    if args.json:
        print(json.dumps(document, indent=2))
    else:
        print(render(rows))
        for w in document["harnessWiring"]:
            print(f"harness wiring: {w['harness']}: {w['status']} — {w['detail']}")
        print()
        print(harness_hooks.render(document["hookWiring"]))

    return 1 if any(r["status"] == "crashed" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
