"""Findings envelopes -> one SARIF 2.1.0 log, one run per audit.

SARIF is how GitHub code scanning (and most other review UIs) ingests static
analysis. The trap in exporting to it is that a SARIF run with an empty
`results` array is rendered as "no alerts" — exactly the reading this suite
exists to prevent for an audit that refused, was INERT, crashed, or is
DISABLED. So every audit this project expects is given a run, and an audit that
could not check is represented as an invocation with `executionSuccessful:
false` and a `toolExecutionNotifications` entry naming why. "Could not check"
stays visibly different from "checked, nothing found" all the way into the UI.

Mapping decisions:

  severity       critical -> error, should-fix -> warning, fyi -> note
  ruleId         "<audit>/<category-slug>" — stable across runs because both
                 halves are the audit's own vocabulary, never a counter
  tool name      "backend-suite/<audit>" per run, so a code-scanning upload has
                 distinct tools and categories rather than N runs of one tool
                 (GitHub rejects several runs sharing a tool+category)
  locations      relative to `%SRCROOT%`; a finding with no file has no
                 location (it is not given a fake one — some consumers, GitHub
                 included, may then drop it, which the export notes per run)
  checks         a "checks"-polarity envelope (contrast) exports failed checks
                 as results and passed ones as `kind: "pass"`; zero records is
                 "did not run", never clean
  fingerprint    partialFingerprints["backendSuite/v1"] hashes audit, category,
                 file and summary — not the line — so an unrelated edit above a
                 finding does not reopen it as new
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from . import findings as F

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA_URI = ("https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/"
                    "sarif-schema-2.1.0.json")
SRCROOT = "%SRCROOT%"

LEVEL = {F.CRITICAL: "error", F.SHOULD_FIX: "warning", F.FYI: "note"}

# repo_health.py statuses. Only these mean "the audit looked".
RAN_OK = {"clean", "findings"}


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text).strip()).strip("-").lower()
    return s or "uncategorised"


def rule_id(audit: str, category: str) -> str:
    return f"{slug(audit)}/{slug(category)}"


def _relative_uri(file: str, repo: Path | None) -> tuple[str, bool]:
    """(uri, is_relative). Relative URIs carry `%SRCROOT%`."""
    p = Path(file)
    if p.is_absolute():
        if repo is not None:
            try:
                p = p.resolve().relative_to(repo.resolve())
            except ValueError:
                return p.resolve().as_uri(), False
        else:
            return p.as_uri(), False
    posix = PurePosixPath(p.as_posix())
    parts = [x for x in posix.parts if x not in (".", "")]
    return quote("/".join(parts)), True


def _fingerprint(audit: str, record: dict) -> str:
    key = "\x1f".join(str(record.get(k, "")) for k in ("category", "file", "summary"))
    return hashlib.sha256(f"{audit}\x1f{key}".encode()).hexdigest()[:32]


def _result(audit: str, record: dict, repo: Path | None) -> dict:
    category = record.get("category", "uncategorised")
    text = record.get("summary") or f"{audit} finding"
    if record.get("detail") and record["detail"] != text:
        text = f"{text}\n\n{record['detail']}"
    result: dict = {
        "ruleId": rule_id(audit, category),
        "level": LEVEL.get(record.get("severity"), "warning"),
        "message": {"text": text},
        "partialFingerprints": {"backendSuite/v1": _fingerprint(audit, record)},
    }
    if record.get("passed") is True:
        result["kind"] = "pass"
        result["level"] = "none"
    if record.get("file"):
        uri, relative = _relative_uri(str(record["file"]), repo)
        artifact = {"uri": uri}
        if relative:
            artifact["uriBaseId"] = SRCROOT
        physical: dict = {"artifactLocation": artifact}
        line = record.get("line")
        if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
            physical["region"] = {"startLine": line}
        result["locations"] = [{"physicalLocation": physical}]
    return result


def _notification(text: str, level: str = "error") -> dict:
    return {"level": level, "message": {"text": text}}


def build_run(audit: str, *, envelope: dict | None, status: str | None,
              reason: str | None = None, exit_code: int | None = None,
              version: str | None = None, repo: Path | None = None) -> dict:
    """One SARIF run for one audit.

    `status` is a repo_health.py status when known ("clean", "findings",
    "refused", "crashed", "unclear", "disabled"), or None when only the envelope
    on disk is known. An audit that did not successfully look never contributes
    results — a stale envelope from an earlier run is not what it found now.
    """
    driver: dict = {"name": f"backend-suite/{audit}", "rules": []}
    if version:
        driver["version"] = version
    run: dict = {
        "tool": {"driver": driver},
        "automationDetails": {"id": f"backend-suite/{audit}/"},
        "results": [],
        "columnKind": "unicodeCodePoints",
        "originalUriBaseIds": {SRCROOT: {"description": {
            "text": "The root of the repository the audits ran against."}}},
    }
    notes: list[dict] = []
    ok = True
    props: dict = {"status": status}

    if status is not None and status not in RAN_OK:
        ok = False
        words = {
            "refused": "Audit refused (exit 2): this project has not given it what it needs, "
                       "or its sweep was empty (INERT). It did not check anything",
            "disabled": "Audit is DISABLED suite-wide and did not run. It checked nothing",
            "crashed": "Audit crashed or timed out. It checked nothing",
            "unclear": "Audit exited 1 but wrote no findings envelope, so what it found "
                       "cannot be represented here",
        }
        base = words.get(status, f"Audit status {status!r}: not a successful check")
        notes.append(_notification(f"{base}." + (f" Reason: {reason}" if reason else "")))
        envelope = None
    elif envelope is None:
        ok = False
        if status in RAN_OK:
            if status == "clean":
                ok = True
                notes.append(_notification(
                    "Audit exited 0 but emits no findings envelope; zero results is taken "
                    "from its exit code alone.", "note"))
            else:
                notes.append(_notification(
                    "Audit reported findings (exit 1) but emits no findings envelope, so they "
                    "cannot be represented as SARIF results."))
        else:
            notes.append(_notification(
                reason or "No findings envelope collected for this audit — it was never run, "
                          "or it refused. Zero results here does NOT mean clean."))
    elif envelope.get("error"):
        ok = False
        notes.append(_notification(f"Findings envelope unusable: {envelope['error']}."))
        envelope = None

    if envelope is not None:
        records = envelope.get("findings", [])
        reports = envelope.get("reports", F.REPORTS_VIOLATIONS)
        props["reports"] = reports
        if envelope.get("scanned") is not None:
            props["scanned"] = envelope["scanned"]
        if envelope.get("suppressed"):
            props["suppressed"] = envelope["suppressed"]
        if not records:
            if reports == F.REPORTS_CHECKS:
                ok = False
                notes.append(_notification(
                    "Checks-polarity audit recorded no checks — it did not run, which is "
                    "not a pass."))
            elif not envelope.get("scanned"):
                ok = False
                notes.append(_notification(
                    "No findings, and nothing recorded as scanned — indistinguishable from "
                    "an audit that examined nothing, so not reported as clean."))
        rules: dict[str, dict] = {}
        for record in records:
            if reports == F.REPORTS_VIOLATIONS and record.get("passed") is True:
                continue
            result = _result(audit, record, repo)
            rules.setdefault(result["ruleId"], {
                "id": result["ruleId"],
                "name": slug(record.get("category", "uncategorised")),
                "shortDescription": {"text": f"{audit}: {record.get('category', 'uncategorised')}"},
                "defaultConfiguration": {"level": LEVEL.get(record.get("severity"), "warning")},
            })
            run["results"].append(result)
        driver["rules"] = [rules[k] for k in sorted(rules)]
        no_loc = sum(1 for r in run["results"] if "locations" not in r)
        if no_loc:
            notes.append(_notification(
                f"{no_loc} result(s) have no file location; some SARIF consumers (GitHub "
                f"code scanning among them) may not display them.", "warning"))

    invocation: dict = {"executionSuccessful": ok}
    if exit_code is not None:
        invocation["exitCode"] = exit_code
    if notes:
        invocation["toolExecutionNotifications"] = notes
    run["invocations"] = [invocation]
    run["properties"] = {"backendSuite": {k: v for k, v in props.items() if v is not None}}
    return run


def build_log(runs: list[dict]) -> dict:
    return {"$schema": SARIF_SCHEMA_URI, "version": SARIF_VERSION, "runs": runs}
