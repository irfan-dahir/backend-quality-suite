"""One shape for what every audit found, so something can aggregate them.

Each audit grew its own output shape, which was fine while each was read alone:

    audit_tokens        {"file", "line", "kind", "snippet"}
    audit_contrast      {"name", "source", "ratio", "min_ratio", "passed"}
    extract_copy        {"file", "line", "text", "category", "word_count", ...}
    audit_promotion_*   nothing — writes a baseline, no findings file at all

Nothing can grade a project's design debt across audits that disagree about what a
finding *is*. This module defines the common envelope they all additionally emit.

ADDITIVE, DELIBERATELY. No audit's existing `--out` output changes shape, because
`capture-baselines.sh` diffs that output byte-for-byte against
`.design-suite/baselines/` and a change there is a reviewed decision, not a side
effect of adding a dashboard. Audits gain `--findings <path>`; they keep `--out`.

Same rule applies to the optional `verification` field on make(): a finding that
omits it is byte-identical to what it was before that field existed. See
templates/verification-tier.schema.json for the tier vocabulary
(unverified/self-tested/cross-verified/human-reviewed) and why a claim's
verification tier is a different, smaller problem than a whole component's
maturity (docs/ROADMAP.md Workstream A2).

TWO POLARITIES, because two exist. Most audits report violations — every record is
something wrong, and zero records is a clean result. Contrast reports *checks* —
every combination it knows about, most of them passing, and zero records means the
audit never ran rather than that the project is perfect. Grading the second like
the first would score a project with no contrast data as flawless.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_VERSION = 1

# Mirrors the 🔴/🟡/🔵 vocabulary every audit skill already reports in, so a
# finding does not change severity language between the script and the skill.
CRITICAL = "critical"
SHOULD_FIX = "should-fix"
FYI = "fyi"
SEVERITIES = (CRITICAL, SHOULD_FIX, FYI)

# "violations": records are problems; none is clean.
# "checks":     records are assertions carrying `passed`; none means it did not run.
REPORTS_VIOLATIONS = "violations"
REPORTS_CHECKS = "checks"

# Verification-tier vocabulary for a single finding's `verification` field, shared
# with templates/verification-tier.schema.json (that file is the canonical, hand-
# maintained schema; these constants exist so a caller of make() can validate
# against the same vocabulary without parsing JSON at runtime). Ordered weakest to
# strongest: UNVERIFIED is asserted with nothing run; SELF_TESTED is the same
# agent running something informal on itself; CROSS_VERIFIED is an independent
# check — a second agent, a formal test suite, a gate script; HUMAN_REVIEWED is a
# person looking at it. This is deliberately NOT the same vocabulary as a
# component's proven/unverified/experimental/pointer tier (CLAUDE.md, catalog.py)
# or a per-project component's stable/experimental/deprecated/unverified status
# (component-maturity.schema.json) — those grade a whole component; this tags one
# claim. See docs/ROADMAP.md Workstream A2 for the related, component-level
# version of "proven is currently a word someone typed".
UNVERIFIED = "unverified"
SELF_TESTED = "self-tested"
CROSS_VERIFIED = "cross-verified"
HUMAN_REVIEWED = "human-reviewed"
VERIFICATION_TIERS = (UNVERIFIED, SELF_TESTED, CROSS_VERIFIED, HUMAN_REVIEWED)

FINDINGS_DIR = ".design-suite/findings"

# Grade boundaries. Violation counts are per category, not per project, because a
# category with 3 findings and one with 140 should not average into one number the
# user cannot act on — which is why the dashboard grades per category and refuses
# to compute a composite.
_VIOLATION_BANDS = ((0, "A"), (5, "B"), (20, "C"), (60, "D"))
_PASS_RATE_BANDS = ((1.0, "A"), (0.95, "B"), (0.85, "C"), (0.70, "D"))


def make(audit: str, category: str, summary: str, *,
         severity: str = SHOULD_FIX, file: str | None = None, line: int | None = None,
         detail: str | None = None, passed: bool | None = None,
         verification: dict | None = None) -> dict:
    """One finding in the common shape.

    `category` is the audit's own subdivision — token kind, check name, rule id.
    It is what the dashboard grades on, so an audit that reports everything under
    one category gets one grade, which is usually not what its author wanted.

    `verification` is optional and additive, per templates/verification-tier.schema.json:
    a `{"tier": ..., "ranWhat": ..., "verifiedBy": ..., "timestamp": ..., "notes": ...}`
    dict tagging how well-checked this specific finding is, distinct from the
    audit's own severity. `tier` must be one of VERIFICATION_TIERS, and every tier
    but UNVERIFIED requires `ranWhat` — mirroring the schema's own constraint here
    so a caller gets the error at construction time, not only when something later
    validates the JSON.
    """
    if severity not in SEVERITIES:
        raise ValueError(f"severity {severity!r} not one of {SEVERITIES}")
    record = {"audit": audit, "category": category, "severity": severity, "summary": summary}
    if file is not None:
        record["file"] = file
    if line is not None:
        record["line"] = line
    if detail is not None:
        record["detail"] = detail
    if passed is not None:
        record["passed"] = passed
    if verification is not None:
        tier = verification.get("tier")
        if tier not in VERIFICATION_TIERS:
            raise ValueError(f"verification tier {tier!r} not one of {VERIFICATION_TIERS}")
        if tier != UNVERIFIED and not verification.get("ranWhat"):
            raise ValueError(f"verification tier {tier!r} requires 'ranWhat'")
        record["verification"] = verification
    return record


def from_records(audit: str, records: list[dict], *,
                 category_key: str | None = None, category: str | None = None,
                 summary_key: str = "detail", severity_key: str | None = None,
                 default_severity: str = SHOULD_FIX) -> list[dict]:
    """Adapt an audit's own `{file, line, …}` records to the common shape.

    Ten of the fourteen audits already produce a list of dicts carrying a file, a
    line, and some prose — they just disagree about what the other keys are called
    (`kind`, `check`, `rule`, or nothing at all). Without this, each retrofit is
    four near-identical lines of dict comprehension, and the fourth one to be
    written gets a key wrong.

    `category_key` names the field to group by; `category` supplies a constant for
    audits that report one kind of thing and so have no such field. Exactly one is
    expected — grouping everything under "uncategorised" grades an audit as a
    single row, which is almost never what its author wanted.

    Severities are normalised here rather than at each call site: audits spell
    them `should_fix` while the envelope uses `should-fix`, and that mismatch
    silently fails make()'s validation.
    """
    if not category_key and not category:
        raise ValueError(f"{audit}: pass category_key or category, not neither")

    out = []
    for record in records:
        severity = default_severity
        if severity_key and record.get(severity_key):
            candidate = str(record[severity_key]).replace("_", "-").lower()
            severity = candidate if candidate in SEVERITIES else default_severity
        out.append(make(
            audit,
            record.get(category_key) or category if category_key else category,
            str(record.get(summary_key) or record.get("detail") or "").strip()
            or f"{audit} finding",
            severity=severity,
            file=record.get("file"),
            line=record.get("line"),
        ))
    return out


def write(path: Path, audit: str, findings: list[dict], *,
          reports: str = REPORTS_VIOLATIONS, scanned: int | None = None,
          suppressed: dict | None = None) -> None:
    """Write the envelope, creating the findings directory if needed.

    `scanned` — how many files or checks the audit actually looked at — is what
    separates "found nothing" from "ran against nothing". An audit pointed at a
    path that no longer exists reports zero findings, which is indistinguishable
    from a clean result unless the count of what it examined comes with it. That
    exact failure has happened here before: /review-docs check C read a router
    file that had been split, found zero routes, and reported clean.

    `suppressed` — what a documented exception hid, and which entry hid it — is
    the same argument one step further in. An audit that applies a project's
    accepted exceptions reports fewer findings than it found, and without this a
    reader cannot tell a category the project exempted from a category that is
    genuinely clean. Optional and additive: an envelope written without it is
    byte-identical to what it was before the field existed.
    """
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "audit": audit,
        "reports": reports,
        "findings": findings,
    }
    if scanned is not None:
        payload["scanned"] = scanned
    if suppressed:
        payload["suppressed"] = suppressed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def default_path(repo: Path, audit: str) -> Path:
    return repo / FINDINGS_DIR / f"{audit}.json"


def read_all(repo: Path) -> list[dict]:
    """Every envelope in the findings directory, oldest-schema-first tolerant.

    A file that is not a valid envelope is skipped with a note rather than
    aborting the whole dashboard — one malformed audit output should cost its own
    row, not every other audit's.
    """
    directory = repo / FINDINGS_DIR
    if not directory.is_dir():
        return []
    envelopes = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            envelopes.append({"audit": path.stem, "error": "unreadable or not JSON"})
            continue
        if not isinstance(data, dict) or "findings" not in data:
            envelopes.append({"audit": path.stem, "error": "not a findings envelope"})
            continue
        data.setdefault("audit", path.stem)
        data.setdefault("reports", REPORTS_VIOLATIONS)
        envelopes.append(data)
    return envelopes


def _band(value, bands, higher_is_better: bool) -> str:
    for threshold, letter in bands:
        if (value >= threshold) if higher_is_better else (value <= threshold):
            return letter
    return "F"


def grade_category(reports: str, records: list[dict], overrides: dict | None = None) -> dict:
    """Grade one category. Returns count, grade, and what the grade was based on.

    Overrides come from the project profile, not from here: 140 token findings in
    a 500-file codebase and 140 in a 40-file one are not the same condition, and
    the engine has no way to know which it is looking at.
    """
    if reports == REPORTS_CHECKS:
        total = len(records)
        if total == 0:
            return {"count": 0, "grade": "?", "basis": "no checks recorded — did this audit run?"}
        passed = sum(1 for r in records if r.get("passed"))
        rate = passed / total
        bands = (overrides or {}).get("passRateBands") or _PASS_RATE_BANDS
        bands = [tuple(b) for b in bands]
        return {
            "count": total - passed,
            "grade": _band(rate, bands, higher_is_better=True),
            "basis": f"{passed}/{total} checks pass ({rate:.0%})",
        }

    count = len(records)
    bands = (overrides or {}).get("violationBands") or _VIOLATION_BANDS
    bands = [tuple(b) for b in bands]

    # Severity split, when there is one. Without it a category of entirely
    # accepted debt grades identically to a category of fresh breakage, and the
    # dashboard would appear to contradict a gate that just reported clean.
    actionable = sum(1 for r in records if r.get("severity") in (CRITICAL, SHOULD_FIX))
    basis = f"{count} finding{'s' if count != 1 else ''}"
    if count and actionable == 0:
        basis += " (all known debt)"
    elif actionable != count:
        basis += f" ({actionable} new, {count - actionable} known debt)"

    return {
        "count": count,
        "grade": _band(count, bands, higher_is_better=False),
        "basis": basis,
    }


def summarize(envelopes: list[dict], thresholds: dict | None = None) -> list[dict]:
    """Per-audit, per-category grades.

    No composite score, by decision: a single number invites optimising the number
    rather than the codebase, and averaging a 26-check contrast pass rate against a
    144-finding token sweep produces a figure that means nothing in either unit.
    """
    thresholds = thresholds or {}
    rows = []
    for envelope in envelopes:
        audit = envelope.get("audit", "?")
        if envelope.get("error"):
            rows.append({"audit": audit, "category": "—", "grade": "!",
                         "count": 0, "basis": envelope["error"]})
            continue

        reports = envelope.get("reports", REPORTS_VIOLATIONS)
        findings = envelope.get("findings", [])
        by_category: dict[str, list[dict]] = {}
        for record in findings:
            by_category.setdefault(record.get("category", "uncategorised"), []).append(record)

        if not by_category:
            # "clean" is only meaningful with the size of the sweep behind it.
            # Zero findings from an audit that examined nothing is the silent
            # failure this suite has already been bitten by twice.
            scanned = envelope.get("scanned")
            if reports == REPORTS_CHECKS:
                basis, grade = "no checks recorded — did this audit run?", "?"
            elif scanned:
                basis, grade = f"clean across {scanned} files", "A"
            else:
                basis, grade = "no findings, but nothing recorded as scanned", "?"
            rows.append({"audit": audit, "category": "—", "grade": grade,
                         "count": 0, "basis": basis,
                         "scanned": envelope.get("scanned")})
            continue

        overrides = thresholds.get(audit, {})
        for category in sorted(by_category):
            records = by_category[category]
            result = grade_category(reports, records,
                                    overrides.get(category) or overrides.get("_default"))
            worst = CRITICAL if any(r.get("severity") == CRITICAL for r in records) else None
            rows.append({
                "audit": audit,
                "category": category,
                "grade": result["grade"],
                "count": result["count"],
                "basis": result["basis"],
                "hasCritical": worst is not None,
                "scanned": envelope.get("scanned"),
            })
    return rows
