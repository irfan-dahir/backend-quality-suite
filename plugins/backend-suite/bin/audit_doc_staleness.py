#!/usr/bin/env python3
"""How many days since a doc's own stated last-updated date — not verification.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_doc_staleness.py"

## What this claim is, and what it deliberately is not

Issue #84 asked for a "days since last verified" stamp per doc page. The
research posted on that issue split it into two different claims that must
stay separate:

1. **"Days since this doc's own stated last-updated date."** Purely textual —
   read a footer or header date, parse it, compute `(today - date).days`.
   Needs zero evidence-file infrastructure. **This script.**
2. **"Confirmed a human/agent verified the doc still matches reality."** A
   real verification claim — it needs something recording that a check
   actually happened, which is what `.backend-suite/evidence/<name>.json`
   (ROADMAP Workstream A1/A2, RFC-0001) is for. Not yet built. Out of scope
   here, on purpose.

This script computes only (1). **It never claims "verified."** A stated date
means someone edited the file on that date — it says nothing about whether
the doc still matches the codebase. Calling that "verified" would be exactly
the kind of overclaiming this suite's governing principle exists to prevent
(an audit that reports a comforting number nobody checked the meaning of is
worse than an audit that reports nothing).

## The convention it looks for

This repo's own doc templates (`templates/docs/*.template`) all end with the
same footer convention: a `_Last updated: <value>_` line (RFC, POSTMORTEM,
RELEASE, and every other templated doc use it — the label is consistent
across all of them; the *value* is not: most spell it
`<!-- DERIVED -->`/`<!-- DERIVED: ... -->`, an unfilled placeholder that
carries no date at all until a real one replaces it at generation time).

So a doc only has a usable staleness signal once that placeholder has been
replaced with a real `YYYY-MM-DD`. Three shapes are recognised, any of which
counts:

  * a footer: `_Last updated: 2026-08-01_` (also matches without the
    surrounding `_..._` emphasis, and independent of a trailing space before
    the closing underscore — templates are inconsistent about that detail)
  * a header field: `Date: 2026-08-01`
  * a header claim: `dated 2026-08-01` (the same phrasing
    `audit_proposal_status.py` already recognises in a proposal header)

A doc with none of these is reported as **"no staleness signal"** — skipped,
not scored as fresh and not treated as an error that blocks the rest of the
sweep. Per this plugin's governing principle, that must never look like "this
doc is fine."

## Reuse from #51

The date-parsing and day-diff arithmetic (`backend_suite.engine.dating`) was
factored out of `audit_proposal_status.py` (#51) for this script to share,
the same "factor, don't duplicate" call issue #60 already made for the
✅/🔴-heading parser. This script does not reimplement date math — it only
adds the footer/header label patterns specific to the "last updated" claim,
which #51's `DATED_RE` (a bare `dated YYYY-MM-DD` inside proposal prose) does
not cover on its own.

## Zero candidates is not the same as clean

A sweep that finds no doc with a usable dated footer/header could mean "every
doc in this project still carries the unfilled `<!-- DERIVED -->` placeholder"
or "this project spells the convention differently" — either way, that is not
the same fact as "checked N docs, all fresh," and must not exit clean. See
`main()`.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import _bootstrap  # noqa: E402,F401  (side effect: puts the plugin on sys.path)
from backend_suite.engine.dating import days_since, parse_iso_date  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402

HEADER_WINDOW = 40  # lines scanned for a header-style date field

# `_Last updated: 2026-08-01_`, `_Last updated: <!-- DERIVED -->_`, with or
# without the emphasis underscores and with or without a trailing space
# before the closing one — this repo's own templates vary on that detail.
# Anchored to the *start* of the line and to a value shaped like either an
# ISO date or an HTML-comment placeholder, deliberately not `.+?` for the
# value: this repo's own `commands/*.md` reference the convention inside
# shell snippets ("grep -oE '_Last updated: ...'"), and an unanchored,
# unrestricted match reads those as real footers. A real footer is always
# its own whole line; a snippet mentioning the convention is not.
FOOTER_RE = re.compile(r"^_?\**Last updated\**:\s*(<!--.*?-->|\d{4}-\d{2}-\d{2})\s*_?\s*$",
                       re.I | re.M)

# A header `Date:` field, e.g. `Date: 2026-08-01` or `**Date:** 2026-08-01`.
DATE_FIELD_RE = re.compile(r"^\s*(?:>\s*)?\*{0,2}Date\*{0,2}\s*:\s*(.+?)\s*$", re.I | re.M)

# The same "dated YYYY-MM-DD" phrasing audit_proposal_status.py's DATED_RE
# looks for in a proposal header — kept separate rather than imported since
# that one is proposal-specific by name and this script has no notion of
# proposals; the pattern itself is generic enough to duplicate cheaply.
DATED_PHRASE_RE = re.compile(r"\bdated\s+(\d{4}-\d{2}-\d{2})\b", re.I)


@dataclass(frozen=True)
class Finding:
    file: str
    check: str
    severity: str  # "should_fix" | "info"
    detail: str

    def as_dict(self) -> dict:
        return {"file": self.file, "check": self.check, "severity": self.severity,
                "detail": self.detail}


@dataclass(frozen=True)
class StatedDate:
    source: str          # "footer" | "header Date: field" | "header 'dated ...' phrase"
    raw: str             # the raw matched value, before date parsing
    date: datetime.date | None  # parsed date, or None if raw wasn't a real ISO date


def find_stated_date(text: str) -> StatedDate | None:
    """The first recognised last-updated signal in `text`, footer preferred.

    Returns None when nothing matches at all. Returns a `StatedDate` with
    `date=None` when a label matched but its value isn't a parseable ISO date
    (the common case: `<!-- DERIVED -->` still unfilled) — callers must
    report that as "no staleness signal", not silently skip it and not treat
    it as fresh.
    """
    footer_m = FOOTER_RE.search(text)
    if footer_m:
        raw = footer_m.group(1).strip()
        return StatedDate(source="footer", raw=raw, date=parse_iso_date(raw))

    header = "\n".join(text.splitlines()[:HEADER_WINDOW])
    field_m = DATE_FIELD_RE.search(header)
    if field_m:
        raw = field_m.group(1).strip()
        return StatedDate(source="header `Date:` field", raw=raw, date=parse_iso_date(raw))

    phrase_m = DATED_PHRASE_RE.search(header)
    if phrase_m:
        raw = phrase_m.group(1)
        return StatedDate(source="header \"dated ...\" phrase", raw=raw, date=parse_iso_date(raw))

    return None


def check_doc(rel_path: str, text: str, today: datetime.date,
              stale_days: int) -> tuple[Finding | None, str]:
    """Returns (finding-or-None, status) where status is one of:

    "stale", "fresh", "unparseable", "no_signal" — used by `main()` to tally
    the sweep honestly rather than only counting findings.
    """
    stated = find_stated_date(text)
    if stated is None:
        return None, "no_signal"

    if stated.date is None:
        return Finding(
            rel_path, "unparseable_date", "info",
            f"{rel_path} has a {stated.source} but its value ({stated.raw!r}) is not a "
            f"parseable YYYY-MM-DD date — likely an unfilled template placeholder. "
            f"No staleness signal."), "unparseable"

    age = days_since(stated.date, today)
    if age < 0:
        return Finding(
            rel_path, "future_dated", "info",
            f"{rel_path}'s {stated.source} states {stated.date.isoformat()}, which is "
            f"{-age} day(s) in the future relative to today ({today.isoformat()}). "
            f"Probably a typo, not a staleness signal worth trusting."), "unparseable"

    if age > stale_days:
        return Finding(
            rel_path, "stale_by_stated_date", "should_fix",
            f"{rel_path}'s {stated.source} states {stated.date.isoformat()} — "
            f"{age} day(s) ago, past the {stale_days}-day threshold. This is only "
            f"how long ago the doc was last edited by its own stated date, NOT "
            f"confirmation anyone has checked it still matches reality."), "stale"

    return None, "fresh"


def iter_markdown(scan_root: Path):
    for p in sorted(scan_root.rglob("*.md")):
        parts = set(p.relative_to(scan_root).parts)
        if parts & {".git", "node_modules", ".backend-suite"}:
            continue
        yield p


def run_audit(files: dict[str, str], today: datetime.date,
              stale_days: int) -> tuple[list[Finding], dict[str, int]]:
    """Returns (findings, tally) where tally counts every status, including
    docs with no signal at all — the sweep must account for every file it
    looked at, not just the ones that produced a finding.
    """
    findings: list[Finding] = []
    tally = {"stale": 0, "fresh": 0, "unparseable": 0, "no_signal": 0}
    for rel_path, text in files.items():
        finding, status = check_doc(rel_path, text, today, stale_days)
        tally[status] += 1
        if finding is not None:
            findings.append(finding)
    return findings, tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="repository root to scan (default: resolved project root)")
    parser.add_argument("--dir", help="subdirectory to scan instead of the whole repo, "
                                       "e.g. docs")
    parser.add_argument("--stale-days", type=int, default=90,
                         help="how old a doc's stated last-updated date can be before "
                              "stale_by_stated_date fires (default 90)")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD), for tests")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /quality-debt "
                             "(default .backend-suite/findings/doc-staleness.json)")
    args = parser.parse_args()

    if args.repo:
        repo = Path(args.repo).resolve()
        if not repo.is_dir():
            print(f"audit_doc_staleness: {repo} is not a directory", file=sys.stderr)
            return 2
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from backend_suite.project import project_root  # noqa: E402
        repo = project_root()

    scan_root = repo / args.dir if args.dir else repo
    if not scan_root.is_dir():
        print(f"audit_doc_staleness: {scan_root} does not exist", file=sys.stderr)
        return 2

    files = {p.relative_to(repo).as_posix(): p.read_text(errors="replace")
             for p in iter_markdown(scan_root)}

    if not files:
        print(f"audit_doc_staleness: no markdown files under {scan_root} — "
              f"INERT, not clean: refusing to report a pass on an empty sweep.",
              file=sys.stderr)
        return 2

    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.date.today())
    findings, tally = run_audit(files, today, args.stale_days)

    signalled = tally["stale"] + tally["fresh"]
    if signalled == 0:
        print(f"audit_doc_staleness: {len(files)} markdown file(s) scanned under "
              f"{scan_root}, none carried a parseable last-updated date (no filled "
              f"`_Last updated: YYYY-MM-DD_` footer, `Date:` field, or \"dated "
              f"YYYY-MM-DD\" header phrase — {tally['unparseable']} had the label but an "
              f"unfilled/unparseable value) — INERT, not clean: either every doc still "
              f"carries an unfilled template placeholder, or this project spells the "
              f"convention differently and this audit cannot see it.", file=sys.stderr)
        return 2

    if args.findings:
        # `scanned` is the file count, not the finding count: a zero-finding
        # envelope with no sweep size behind it grades as "?" rather than "A",
        # which is the whole point of the field.
        F.write(
            F.default_path(repo, "doc-staleness") if args.findings is True
            else repo / args.findings,
            "doc-staleness",
            F.from_records("doc-staleness", [f.as_dict() for f in findings],
                           category_key="check", severity_key="severity",
                           default_severity=F.FYI),
            scanned=len(files),
        )

    stale = [f for f in findings if f.check == "stale_by_stated_date"]
    info = [f for f in findings if f.check != "stale_by_stated_date"]

    for label, group in (("STALE (should fix)", stale), ("info", info)):
        if not group:
            continue
        print(f"\n{label} — {len(group)} finding(s):\n")
        for f in group:
            print(f"  {f.detail}")

    print(f"\naudit_doc_staleness: {len(files)} file(s) scanned, {signalled} with a "
          f"dated last-updated signal ({tally['fresh']} within {args.stale_days} days, "
          f"{tally['stale']} stale), {tally['unparseable']} with an unparseable/future "
          f"value, {tally['no_signal']} with no staleness signal at all. "
          f"Reminder: this is days-since-last-edited, not verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
