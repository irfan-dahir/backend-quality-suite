#!/usr/bin/env python3
"""Roll every audit's findings into one per-category view of design debt.

Running four audits and holding four reports in your head is the problem this
solves. It reads `.backend-suite/findings/*.json` — the common envelope written by
`backend_suite/engine/findings.py` — and grades each audit's categories.

    python3 bin/quality_debt.py                 grade what has been collected
    python3 bin/quality_debt.py --json          same, machine-readable
    python3 bin/quality_debt.py --stale-only    just say which audits need re-running

PER-CATEGORY GRADES, NO COMPOSITE — a decision, not an omission. One number across
audits invites moving the number instead of fixing the codebase, and there is no
honest way to average a contrast pass-rate against a count of hardcoded colours.

This never runs an audit itself. Collection and grading stay separate so the
dashboard cannot be the reason an audit's output changed, which would put it in
conflict with `capture-baselines.sh`. `--stale-only` exists so the skill can tell
you what to run rather than deciding for you.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from backend_suite.engine import audit_discovery  # noqa: E402
from backend_suite.engine import doc_roles  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402

GRADE_MARK = {"A": "✅", "B": "✅", "C": "🟡", "D": "🔴", "F": "🔴", "?": "⚪", "!": "⚠️"}


def profile() -> dict:
    path = REPO / ".backend-suite/profile.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def expected_audits(prof: dict) -> list[str]:
    """Audits this project expects to have data for.

    Declared in the profile rather than inferred from what happens to be on disk:
    an audit that has never been run leaves no file, and inferring the expected
    set from existing files would make a never-run audit invisible — the same
    silent-absence failure the doc-role manifest exists to prevent.
    """
    return list(((prof.get("debt") or {}).get("audits")) or [])


def split_disabled(rows: list[dict], missing: list[str]) -> tuple[list[dict], list[str], list[tuple[str, dict]]]:
    """Pull disabled audits out of both the graded rows and the no-data list.

    A disabled audit must not be graded — any findings file it left behind is
    from a run of a check we have since established cannot be right, and a grade
    computed from it is a grade for nothing. It must not sit under "never
    collected" either: that reads as "someone forgot to run it", which invites
    running it. It gets its own section saying it was switched off and why.
    """
    names = {r["audit"] for r in rows} | set(missing)
    disabled = [(n, e) for n in sorted(names)
                if (e := audit_discovery.disabled_reason(n)) is not None]
    off = {n for n, _ in disabled}
    return ([r for r in rows if r["audit"] not in off],
            [m for m in missing if m not in off],
            disabled)


def doc_debt() -> dict:
    """Documentation coverage, counting stubs as debt rather than as coverage.

    A stub is a document that exists, is mapped, and is unwritten. Counted the
    obvious way — one mapped role, one documented category — it inflates the
    coverage number by exactly the documents nobody has written, which is the
    worst direction for a number to be wrong in. So `written` excludes stubs, and
    stubs appear under debt beside declines, which are excluded from both because
    a decline is a decision on record rather than work outstanding.
    """
    manifest_rel = ((profile().get("docs") or {}).get("manifest")
                    or ".backend-suite/docs.manifest.json")
    path = REPO / manifest_rel
    if not path.is_file():
        return {}
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    mapped = [r for r, rel in (manifest.get("roles") or {}).items() if isinstance(rel, str)]
    stubs = doc_roles.stub_roles(REPO, manifest)
    declined = doc_roles.declined_roles(manifest)
    return {
        "mapped": len(mapped),
        "written": len(mapped) - len(stubs),
        "stubs": stubs,
        "declined": [{"role": r, "reason": doc_roles.decline_reason(e)}
                     for r, e in sorted(declined.items())],
    }


def render_docs(docs: dict) -> list[str]:
    if not docs:
        return []
    lines = ["", f"Documentation: {docs['written']} of {docs['mapped']} mapped role(s) "
                 f"actually written."]
    for role in docs["stubs"]:
        lines.append(f"  🟡 {role} — STUB: registered but unwritten. Debt, not coverage")
    for entry in docs["declined"]:
        lines.append(f"  ▫ {entry['role']} — declined: "
                     f"{entry['reason'] or 'NO REASON RECORDED'} (not counted either way)")
    return lines


def render(rows: list[dict], missing: list[str], disabled: list[tuple[str, dict]] | None = None,
           docs: dict | None = None) -> str:
    disabled = disabled or []
    docs = docs or {}
    if not rows and not missing and not disabled:
        return "\n".join(
            ["No findings collected. Audits write them with `--findings`; see "
             f"{F.FINDINGS_DIR}/. Declare the expected set under `debt.audits` in "
             ".backend-suite/profile.json so a never-run audit is visible here."]
            + render_docs(docs))

    width_audit = max([len("AUDIT")] + [len(r["audit"]) for r in rows]) if rows else 5
    width_cat = max([len("CATEGORY")] + [len(str(r["category"])) for r in rows]) if rows else 8

    lines = []
    if rows:
        lines.append(f"{'AUDIT'.ljust(width_audit)}  {'CATEGORY'.ljust(width_cat)}  GRADE  DETAIL")
        lines.append(f"{'-' * width_audit}  {'-' * width_cat}  -----  ------")
        last_audit = None
        for row in rows:
            audit = row["audit"] if row["audit"] != last_audit else ""
            last_audit = row["audit"]
            mark = GRADE_MARK.get(row["grade"], " ")
            critical = "  ← has critical" if row.get("hasCritical") else ""
            lines.append(
                f"{audit.ljust(width_audit)}  {str(row['category']).ljust(width_cat)}  "
                f"{mark} {row['grade']}   {row['basis']}{critical}"
            )

    if missing:
        lines.append("")
        lines.append("No data (declared in profile, never collected):")
        for audit in missing:
            lines.append(f"  ⚪ {audit} — run its audit with --findings")

    if disabled:
        lines.append("")
        lines.append("Disabled — switched off suite-wide, NOT graded, and not a clean bill "
                     "of health for this category:")
        for name, entry in disabled:
            lines.append(f"  ⛔ {name} — {entry['reason']}")
            lines.append(f"     {entry['detail']}")
            lines.append(f"     path back: {entry['pathBack']}")

    lines += render_docs(docs)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--stale-only", action="store_true",
                    help="print only the audits with no collected findings")
    args = ap.parse_args()

    prof = profile()
    thresholds = (prof.get("debt") or {}).get("thresholds") or {}

    envelopes = F.read_all(REPO)
    present = {e.get("audit") for e in envelopes}
    missing = [a for a in expected_audits(prof) if a not in present]

    rows = F.summarize(envelopes, thresholds)
    rows, missing, disabled = split_disabled(rows, missing)
    docs = doc_debt()

    if args.stale_only:
        if args.json:
            print(json.dumps({"missing": missing,
                              "disabled": [{"audit": n, **e} for n, e in disabled]}, indent=2))
        else:
            # A disabled audit is not stale: re-running it is not the fix, and
            # saying so here is the difference between "nobody ran it" and
            # "it was switched off because it was wrong".
            print("\n".join(missing) if missing
                  else "Every declared audit has collected findings.")
            for name, entry in disabled:
                print(f"⛔ {name} — {entry['reason']} (do not re-run: {entry['pathBack']})")
        return 0

    if args.json:
        print(json.dumps({"rows": rows, "missing": missing,
                          "disabled": [{"audit": n, **e} for n, e in disabled],
                          "docs": docs}, indent=2))
        return 0

    print(render(rows, missing, disabled, docs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
