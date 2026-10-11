#!/usr/bin/env python3
"""Does a proposal doc's own stated status still match what its body says?

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_proposal_status.py"

## What this is a cheaper variant of

`/review-docs` audits every document against every other document and against
the codebase — expensive, and the right tool when the question is "is anything
stale". This audit answers one narrower, mechanical question instead: **for a
document that declares itself a proposal with open questions or 🔴/✅ status
markers, does its own header still agree with its own body?**

That narrowness is what makes it cheap enough to run often. It never reads the
codebase, and it never compares one document to another — only a document
against itself.

## The convention it checks

Nothing in `DOC-ROLES.md` names a `proposal` role, and this audit does not add
one. A role is for "which file plays this part in this project" — proposals are
not one-per-project, they come and go, and a manifest entry would need updating
every time one is added or resolved. So detection is by **content convention**,
already in use by this repo's own `docs/ROADMAP.md`:

  * a header (the first ~40 lines) that frames the document as a live proposal —
    "Proposal, dated YYYY-MM-DD", an explicit `Status: open|resolved|superseded`
    field, or a stated count of open questions;
  * a body that resolves each one under a heading carrying a 🔴 (open) or ✅
    (resolved) marker — the exact shape of this repo's own
    `## Decisions (were 🔴, resolved 2026-08-10)` section.

A project that spells this differently gets nothing from this audit, honestly —
see "What this cannot check" below.

## Three checks, two severities

1. **`count_mismatch`** (critical) — the header states N open questions; the
   body's decision headings do not add up to N, or some remain marked 🔴 after
   the header claims resolution. An unambiguous count, not a judgement call.
2. **`reverse_claim`** (critical) — the header's prose claims resolution (e.g.
   "all resolved") while the body still carries a 🔴 heading. Same failure mode
   as (1), for documents that state resolution in prose rather than a number.
3. **`stale_framing`** (should_fix) — the header is fully consistent with the
   body (every decision *is* resolved) but the header still frames the document
   as an open proposal, dated well in the past. Not wrong, exactly — but a
   proposal that has been fully resolved for weeks and still reads as "not a
   record of work" is the header failing to keep up with its own document, and
   the exact case named in issue #51.

## What this cannot check

Whether a *downstream* condition the document names (a roadmap phase's "gate to
proceed", say) has actually been met is not decidable from the document's own
text — it requires reading the codebase or its history, which is exactly what
this audit exists to not do (that is `/review-docs`'s job, at higher cost). This
audit says so explicitly rather than silently passing: see `EXTERNAL_GATE_HINT`
below, surfaced whenever `stale_framing` fires on a doc that also has a
Sequencing/gate-shaped table, since that is the situation where a human is most
likely to also want that checked.

## Zero candidates is not the same as clean

A sweep that finds no proposal-shaped documents could mean "this project has
none right now" or "this project uses a convention this audit does not
recognise" — those are different facts and must not produce the same exit code
as "checked N documents, found nothing wrong". See `main()`.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import _bootstrap  # noqa: E402,F401  (side effect: puts the plugin on sys.path)
from backend_suite.engine.dating import days_since  # noqa: E402
from backend_suite.engine.decisions import find_decision_section  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402

HEADER_WINDOW = 40  # lines scanned for the header claim

PROPOSAL_MARKER_RE = re.compile(r"\bproposal\b", re.I)
STATUS_FIELD_RE = re.compile(r"^\s*(?:>\s*)?\*{0,2}Status\*{0,2}\s*:\s*(open|resolved|superseded)\b",
                              re.I | re.M)
OPEN_COUNT_RE = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
                            r"\s+open question", re.I)
RESOLVED_CLAIM_RE = re.compile(
    r"\ball\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*"
    r"open questions?\s+(?:were|was|are|is)\s+resolved"
    r"|\bresolved\s+the\s+same\s+day\b"
    r"|\bfully\s+resolved\b", re.I)
NOT_RECORD_RE = re.compile(r"not\s+a\s+record\s+of\s+work", re.I)
DATED_RE = re.compile(r"\bdated\s+(\d{4}-\d{2}-\d{2})\b", re.I)
GATE_TABLE_RE = re.compile(r"\bgate to proceed\b|\bblocked on\b", re.I)

_WORD_TO_INT = {w: i for i, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"])}


def _to_int(token: str) -> int:
    token = token.lower()
    return _WORD_TO_INT.get(token, None) if not token.isdigit() else int(token)


@dataclass(frozen=True)
class Finding:
    file: str
    check: str
    severity: str  # "critical" | "should_fix"
    detail: str

    def as_dict(self) -> dict:
        return {"file": self.file, "check": self.check, "severity": self.severity,
                "detail": self.detail}


@dataclass(frozen=True)
class DecisionTally:
    resolved: int
    open_: int
    resolved_date: str | None
    heading_line: int | None


def is_candidate(text: str) -> bool:
    """Does this document declare itself a proposal with a status convention?

    Deliberately conjunctive-or, not every-signal: a doc need only carry one of
    the recognised conventions to be in scope, because projects will not all
    spell this the same way and requiring all of them would silently exclude
    anyone who only uses part of it.
    """
    header = "\n".join(text.splitlines()[:HEADER_WINDOW])
    if STATUS_FIELD_RE.search(header):
        return True
    if PROPOSAL_MARKER_RE.search(header) and (OPEN_COUNT_RE.search(header)
                                               or RESOLVED_CLAIM_RE.search(header)
                                               or DATED_RE.search(header)):
        return True
    return False


def header_claim(text: str) -> dict:
    """What the header (first HEADER_WINDOW lines) says about its own status."""
    header = "\n".join(text.splitlines()[:HEADER_WINDOW])
    status_field = STATUS_FIELD_RE.search(header)
    open_count_m = OPEN_COUNT_RE.search(header)
    dated_m = DATED_RE.search(header)
    return {
        "status_field": status_field.group(1).lower() if status_field else None,
        "open_count": _to_int(open_count_m.group(1)) if open_count_m else None,
        "resolved_claim": bool(RESOLVED_CLAIM_RE.search(header)),
        "not_a_record": bool(NOT_RECORD_RE.search(header)),
        "dated": dated_m.group(1) if dated_m else None,
    }


def body_tally(text: str) -> DecisionTally | None:
    """Count 🔴/✅-marked decision headings under a Decisions section.

    Returns None when no Decisions-shaped section exists at all — that is a
    different situation from "a Decisions section with zero items" and callers
    must not conflate the two.

    Parsing itself lives in `backend_suite.engine.decisions` (shared with
    `bin/query_decisions.py`, issue #60) — this just re-shapes that section into
    the tally this audit's checks compare against a document's own header claim.
    """
    section = find_decision_section(text)
    if section is None:
        return None

    resolved_date_m = re.search(r"resolved\s+(\d{4}-\d{2}-\d{2})", section.heading_text, re.I)
    return DecisionTally(resolved=section.resolved_count, open_=section.open_count,
                          resolved_date=resolved_date_m.group(1) if resolved_date_m else None,
                          heading_line=section.heading_line)


def check_doc(rel_path: str, text: str, today: datetime.date, stale_days: int) -> list[Finding]:
    claim = header_claim(text)
    tally = body_tally(text)
    findings: list[Finding] = []

    if tally is None:
        # A doc opted into the convention (is_candidate said yes) but has no
        # decisions section to check it against. Per the suite's governing
        # principle this is a thing to report, not a quiet no-op: the header
        # makes a claim this audit cannot verify against anything.
        if claim["open_count"] is not None or claim["resolved_claim"] or claim["status_field"]:
            findings.append(Finding(
                rel_path, "unverifiable_claim", "should_fix",
                f"{rel_path} states a status in its header (open_count="
                f"{claim['open_count']!r}, status={claim['status_field']!r}, "
                f"resolved_claim={claim['resolved_claim']}) but has no `## Decisions` "
                f"(or similarly named) section with 🔴/✅ headings to check it against. "
                f"Cannot confirm — not the same as clean."))
        return findings

    total = tally.resolved + tally.open_

    # 1. count_mismatch — header's stated open-question count doesn't add up.
    if claim["open_count"] is not None:
        if claim["open_count"] != total:
            findings.append(Finding(
                rel_path, "count_mismatch", "critical",
                f"{rel_path} header states {claim['open_count']} open question(s); "
                f"the Decisions section (line {tally.heading_line}) accounts for "
                f"{total} ({tally.resolved} ✅, {tally.open_}\N{NO-BREAK SPACE}🔴). "
                f"Update whichever one is out of date."))
        elif tally.open_ > 0 and (claim["resolved_claim"] or
                                   claim["status_field"] == "resolved"):
            findings.append(Finding(
                rel_path, "count_mismatch", "critical",
                f"{rel_path} header claims resolution but {tally.open_} decision(s) in "
                f"the Decisions section (line {tally.heading_line}) are still marked "
                f"🔴 open."))

    # 2. reverse_claim — prose says resolved/closed, body disagrees, with no
    #    explicit count to already have caught it above.
    elif (claim["resolved_claim"] or claim["status_field"] == "resolved") and tally.open_ > 0:
        findings.append(Finding(
            rel_path, "reverse_claim", "critical",
            f"{rel_path} header claims all questions were resolved, but "
            f"{tally.open_} decision(s) in the Decisions section (line "
            f"{tally.heading_line}) are still marked 🔴 open."))

    elif claim["status_field"] == "open" and tally.open_ == 0 and total > 0:
        findings.append(Finding(
            rel_path, "reverse_claim", "critical",
            f"{rel_path} header declares `Status: open`, but every decision in "
            f"the Decisions section (line {tally.heading_line}) is marked ✅ "
            f"resolved. The header was not updated."))

    # 3. stale_framing — internally consistent, but the header's own framing
    #    has not caught up with its own resolved-ness.
    fully_resolved = total > 0 and tally.open_ == 0
    already_flagged_critical = any(f.severity == "critical" for f in findings)
    if fully_resolved and not already_flagged_critical and claim["dated"]:
        try:
            dated = datetime.date.fromisoformat(claim["dated"])
        except ValueError:
            dated = None
        if dated is not None:
            age = days_since(dated, today)
            if age > stale_days and (claim["not_a_record"] or
                                      claim["status_field"] not in (None, "resolved")):
                hint = ""
                if GATE_TABLE_RE.search(text):
                    hint = (" This document also names a downstream gate condition "
                            "(\"gate to proceed\" / \"blocked on\"); whether *that* has "
                            "actually happened is outside what this audit can check "
                            "from the text alone — verify it by hand.")
                findings.append(Finding(
                    rel_path, "stale_framing", "should_fix",
                    f"{rel_path} is dated {claim['dated']} ({age} days ago) and every "
                    f"decision in its Decisions section is now ✅ resolved, but the "
                    f"header still frames it as an open, not-yet-settled proposal. "
                    f"Worth refreshing the header to say so.{hint}"))
    return findings


def iter_markdown(scan_root: Path):
    for p in sorted(scan_root.rglob("*.md")):
        parts = set(p.relative_to(scan_root).parts)
        if parts & {".git", "node_modules", ".backend-suite"}:
            continue
        yield p


def run_audit(files: dict[str, str], today: datetime.date, stale_days: int) -> tuple[list[Finding], int]:
    """Returns (findings, candidates_checked)."""
    findings: list[Finding] = []
    candidates = 0
    for rel_path, text in files.items():
        if not is_candidate(text):
            continue
        candidates += 1
        findings += check_doc(rel_path, text, today, stale_days)
    return findings, candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="repository root to scan (default: resolved project root)")
    parser.add_argument("--dir", help="subdirectory to scan instead of the whole repo, "
                                       "e.g. docs/proposals")
    parser.add_argument("--stale-days", type=int, default=14,
                         help="how old a fully-resolved proposal's header can be before "
                              "stale_framing fires (default 14)")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD), for tests")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(default .backend-suite/findings/proposal-status.json)")
    args = parser.parse_args()

    if args.repo:
        repo = Path(args.repo).resolve()
        if not repo.is_dir():
            print(f"audit_proposal_status: {repo} is not a directory", file=sys.stderr)
            return 2
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from backend_suite.project import project_root  # noqa: E402
        repo = project_root()

    scan_root = repo / args.dir if args.dir else repo
    degraded = False
    if not args.dir:
        proposals_dir = repo / "docs" / "proposals"
        if proposals_dir.is_dir():
            scan_root = proposals_dir
        else:
            degraded = True  # no docs/proposals/ — falling back to a full markdown sweep

    if not scan_root.is_dir():
        print(f"audit_proposal_status: {scan_root} does not exist", file=sys.stderr)
        return 2

    files = {p.relative_to(repo).as_posix(): p.read_text(errors="replace")
             for p in iter_markdown(scan_root)}

    if not files:
        print(f"audit_proposal_status: no markdown files under {scan_root} — "
              f"INERT, not clean: refusing to report a pass on an empty sweep.",
              file=sys.stderr)
        return 2

    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.date.today())
    findings, candidates = run_audit(files, today, args.stale_days)

    if degraded:
        print(f"audit_proposal_status: no docs/proposals/ directory — degraded to scanning "
              f"every *.md under {scan_root} for the proposal-status convention "
              f"(a header naming itself a proposal, a `Status:` field, or a stated open-"
              f"question count) instead of a dedicated proposals directory.", file=sys.stderr)

    if candidates == 0:
        print(f"audit_proposal_status: {len(files)} markdown file(s) scanned under "
              f"{scan_root}, none matched the proposal-status convention (no `Status:` "
              f"field, no \"Proposal, dated ...\" header, no stated open-question count) — "
              f"INERT, not clean: either this project has no such documents right now, or "
              f"it spells the convention differently and this audit cannot see it.",
              file=sys.stderr)
        return 2

    if args.findings:
        # `scanned` is the proposal-shaped count, not the file count: this audit
        # only has an opinion about candidates, so grading a clean run against
        # every markdown file in the repo would overstate the sweep.
        F.write(
            F.default_path(repo, "proposal-status") if args.findings is True
            else repo / args.findings,
            "proposal-status",
            F.from_records("proposal-status", [f.as_dict() for f in findings],
                           category_key="check", severity_key="severity"),
            scanned=candidates,
        )

    critical = [f for f in findings if f.severity == "critical"]
    advisory = [f for f in findings if f.severity != "critical"]

    for label, group in (("CRITICAL", critical), ("should fix", advisory)):
        if not group:
            continue
        stream = sys.stderr if group is critical else sys.stdout
        print(f"\n{label} — {len(group)} finding(s):\n", file=stream)
        for f in group:
            print(f"  {f.detail}", file=stream)

    print(f"\naudit_proposal_status: {len(files)} file(s) scanned, {candidates} "
          f"proposal-shaped, {len(critical)} critical, {len(advisory)} advisory")
    # Same reasoning as audit_error_handling.py: exit code means "were there
    # findings", not "were there critical findings" — `return 1 if critical
    # else 0` let an advisory-only run exit 0 and read as clean to any
    # rc-only consumer. Severity still governs presentation above.
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
