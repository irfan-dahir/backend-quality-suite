"""Applying a project's accepted exceptions to a set of findings.

Lives in the engine rather than in one audit because two tools consult the same
file and disagreeing about what it means is worse than either reading it wrong:
`audit_tokens.py` decides what to report, `repair_tokens.py` decides what to
rewrite. A literal the project exempted but the repairer rewrites anyway is the
band-1 failure RFC-0003 §7 resolution 3 puts at a 0% ceiling.

Contains no project literals and no language knowledge — the shape of an
exceptions file is suite vocabulary, the paths inside it are the project's.

    exceptions.json -> { <category>: { allowlistFiles:  [ {path, reason, ...} ],
                                       allowlistRegions:[ {path, scope, ...} ],
                                       reportAnyway:    [ {path, reason} ] } }

`allowlistFiles` and `allowlistRegions` differ only in how much of the named path
the prose says is exempt; both are applied at path granularity, because `scope` is
written for a human and nothing can check it against the code. Reading the first
and not the second was worth 30% of audit_tokens' findings on the measured
project (issue #108, measured in #104) — a project documented a decision and the
engine re-reported it every run.
"""
from __future__ import annotations

import fnmatch

ALLOWLIST_KEYS = ("allowlistFiles", "allowlistRegions")

# A category's opt-out from its own allowlists: paths the project has declared
# must keep being reported. It outranks both keys above, because a region entry
# may name a glob, and a glob that quietly grows to cover a known-open item would
# turn a tracked debt into silence.
REPORT_ANYWAY_KEY = "reportAnyway"


def matches(rel: str, pattern: str) -> bool:
    """Whether a repo-relative path is covered by an exception's `path`.

    Glob rather than equality because a real region entry reads
    `lib/features/chat/**`. `fnmatch`'s `*` crosses directory separators, so `**`
    and `*` behave the same here — deliberately not tightened, since the looser
    reading is the one an author writing `**` expects.
    """
    return rel == pattern or fnmatch.fnmatchcase(rel, pattern)


def exemptions(raw: dict) -> dict:
    """Category → the exception entries that exempt a path from it."""
    out = {}
    for category, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        entries = [
            dict(entry, exceptionKey=key)
            for key in ALLOWLIST_KEYS
            for entry in (spec.get(key) or [])
            if isinstance(entry, dict) and entry.get("path")
        ]
        if entries:
            out[category] = entries
    return out


def report_anyway(raw: dict) -> dict:
    """Category → paths no exception in that category may suppress."""
    out = {}
    for category, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        paths = {
            entry["path"]
            for entry in (spec.get(REPORT_ANYWAY_KEY) or [])
            if isinstance(entry, dict) and entry.get("path")
        }
        if paths:
            out[category] = paths
    return out


def covering_entry(rel: str, category: str | None, exempt: dict,
                   protected: dict) -> dict | None:
    """The exception entry exempting `rel` from `category`, or None.

    An untagged check (no category) honours no allowlist, matching the Check
    contract in adapters/base.py — an exception is always scoped to the category
    that documented it, so a file allowed to hold brand colours is still held to
    the spacing rules.
    """
    if not category:
        return None
    if any(matches(rel, path) for path in protected.get(category, ())):
        return None
    return next((e for e in exempt.get(category, ())
                 if matches(rel, e["path"])), None)


def partition(findings: list, categories: dict, exempt: dict,
              protected: dict) -> tuple[list, list]:
    """Split findings into those reported and those a documented exception covers.

    Filtering happens here rather than inside the sweep so that a suppressed
    finding is *produced first and then set aside*. Skipping the check outright is
    cheaper and loses the only number that matters to someone auditing the audit:
    how much a given exception is actually hiding.
    """
    kept, suppressed = [], []
    for finding in findings:
        category = categories.get(finding["kind"])
        entry = covering_entry(finding["file"], category, exempt, protected)
        if entry is None:
            kept.append(finding)
        else:
            suppressed.append({**finding, "category": category, "exception": entry})
    return kept, suppressed


def report(suppressed: list) -> dict:
    """How many findings each exception entry hid, grouped by entry.

    Callers carry this alongside what they did report, so that "suppressed by a
    documented exception" and "no finding" are never the same reading. An
    exception that hides nothing is worth seeing too, but it cannot be counted
    from here — it leaves no trace in the findings — so only what was actually
    hidden is reported.
    """
    groups: dict = {}
    for record in suppressed:
        entry = record["exception"]
        key = (record["category"], entry["exceptionKey"], entry["path"],
               entry.get("scope") or "")
        row = groups.setdefault(key, {
            "category": record["category"],
            "exceptionKey": entry["exceptionKey"],
            "path": entry["path"],
            "scope": entry.get("scope"),
            "reason": entry.get("reason"),
            "appliedBy": entry.get("appliedBy"),
            "count": 0,
            "kinds": [],
        })
        row["count"] += 1
        if record["kind"] not in row["kinds"]:
            row["kinds"].append(record["kind"])
    rows = sorted(groups.values(), key=lambda r: (r["category"], r["path"]))
    for row in rows:
        row["kinds"].sort()
    return {"count": len(suppressed), "byException": rows}


def describe(suppression: dict) -> list:
    """Lines saying what was hidden, for printing beside what was reported.

    Empty when nothing was suppressed: there is nothing to disclose, and a line
    saying so on every run of every project trains the reader to skip it.
    """
    if not suppression["count"]:
        return []
    rows = suppression["byException"]
    lines = [f"Suppressed {suppression['count']} further finding(s) under "
             f"{len(rows)} documented exception(s):"]
    for row in rows:
        where = row["path"] + (f" — {row['scope']}" if row.get("scope") else "")
        lines.append(f"  {row['count']:>3}  {row['category']}.{row['exceptionKey']}"
                     f"  {where}")
    if stale := [r for r in rows if r.get("appliedBy") == "reader"]:
        # The entry says a human applies it; the engine just did. A note rather
        # than an error: the metadata is wrong, the exception is not.
        lines.append(
            f"Note: {len(stale)} of the above "
            f"{'entry claims' if len(stale) == 1 else 'entries claim'} "
            f"\"appliedBy\": \"reader\", but the engine applied "
            f"{'it' if len(stale) == 1 else 'them'} — update that field to "
            "\"script\".")
    return lines
