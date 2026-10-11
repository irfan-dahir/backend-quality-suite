#!/usr/bin/env python3
"""Audit Laravel FormRequest validation classes.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_form_request_validation.py" [--out ...] [--baseline-write] [--findings ...]

Config (in arch-rules.json):
  "formRequestValidation": {
    "requestDirs": ["app/Http/Requests"],
    "requireRules": true,
    "requireAuthorize": true,
    "requireMessages": false,
    "requireAttributes": false,
    "forbidDuplicateRules": true,
    "forbidEmptyRules": true
  }

Exit codes:
    0 = clean
    1 = findings
    2 = refused (missing config, unreadable files, missing capability)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: F401  (puts backend_suite on sys.path)
from backend_suite.project import profile, project_root  # noqa: E402
from backend_suite.adapters import load as load_adapter  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402
from backend_suite.engine import arch  # noqa: E402
from backend_suite.adapters.base import AdapterContext, CapabilityError  # noqa: E402

MARKER = "form_request_validation"

FORM_REQUEST_CLASS_RE = re.compile(
    r"\bclass\s+(\w+)\s+extends\s+FormRequest\b"
)
USE_FORM_REQUEST_RE = re.compile(
    r"use\s+Illuminate\\Foundation\\Http\\FormRequest\b"
)
RULES_METHOD_RE = re.compile(
    r"function\s+rules\s*\(\s*\)\s*:\s*(?:array|\\Illuminate\\Contracts\\Validation\\Validator)\s*"
)
AUTHORIZE_METHOD_RE = re.compile(
    r"function\s+authorize\s*\(\s*\)\s*:\s*(?:bool|\\Illuminate\\Contracts\\Auth\\Access\\Authorizable)\s*"
)
MESSAGES_METHOD_RE = re.compile(r"function\s+messages\s*\(\s*\)\s*:\s*array\s*\{")
ATTRIBUTES_METHOD_RE = re.compile(r"function\s+attributes\s*\(\s*\)\s*:\s*array\s*\{")
PREPARE_METHOD_RE = re.compile(r"function\s+prepareForValidation\s*\(\s*\)\s*\{")
PASSED_METHOD_RE = re.compile(r"function\s+passedValidation\s*\(\s*\)\s*\{")

# Matches array entries: 'field' => 'rules' or "field" => "rules"
# Pattern: 'field' => [rules] or 'field' => 'rules' or "field" => "rules" or "field" => ClassName::method
RULE_ARRAY_RE = re.compile(
    r"['\"]([^'\"\\]*(?:\\.[^'\"\\]*)*)['\"]\s*=>\s*(?:\[[^\]]*\]|['\"][^'\"]*['\"]|[\w\\]+(?:::\w+)?)"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="write findings as JSON here")
    ap.add_argument("--findings", nargs="?", const=True, default=False,
                     help="also write findings envelope (default: .backend-suite/findings/form-request-validation.json)")
    ap.add_argument("--baseline-write", action="store_true",
                     help="write baseline (not yet implemented)")
    return ap.parse_args()


def load_config(repo: Path) -> dict:
    arch_rules = repo / ".backend-suite" / "arch-rules.json"
    if not arch_rules.is_file():
        return {}
    try:
        data = json.loads(arch_rules.read_text())
        return data.get("formRequestValidation", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def find_form_requests(request_dirs: list[str], repo: Path) -> list[dict]:
    """Find all FormRequest classes and extract their structure."""
    requests = []
    for d in request_dirs:
        for path in (repo / d).rglob("*.php"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if not USE_FORM_REQUEST_RE.search(text):
                continue

            class_match = FORM_REQUEST_CLASS_RE.search(text)
            if not class_match:
                continue

            class_name = class_match.group(1)
            rel_path = path.relative_to(repo)

            has_rules = bool(RULES_METHOD_RE.search(text))
            has_authorize = bool(AUTHORIZE_METHOD_RE.search(text))
            has_messages = bool(MESSAGES_METHOD_RE.search(text))
            has_attributes = bool(ATTRIBUTES_METHOD_RE.search(text))
            has_prepare = bool(PREPARE_METHOD_RE.search(text))
            has_passed = bool(PASSED_METHOD_RE.search(text))

            rules_text = ""
            rules_match = re.search(r"function\s+rules\s*\([^)]*\)\s*:\s*(?:array|\\Illuminate\\Contracts\\Validation\\Validator)\s*\{([^}]+)\}", text, re.DOTALL)
            if rules_match:
                rules_text = rules_match.group(1)

            rules = []
            for m in RULE_ARRAY_RE.finditer(rules_text):
                field = m.group(1).strip()
                rules.append((field, m.group(0)))

            requests.append({
                "class": class_name,
                "file": path,
                "rel_path": rel_path,
                "has_rules": has_rules,
                "has_authorize": has_authorize,
                "has_messages": has_messages,
                "has_attributes": has_attributes,
                "has_prepare": has_prepare,
                "has_passed": has_passed,
                "rules": rules,
                "text": text,
            })
    return requests


def audit_requests(requests: list[dict], config: dict) -> list[dict]:
    findings = []
    require_rules = config.get("requireRules", True)
    require_authorize = config.get("requireAuthorize", True)
    require_messages = config.get("requireMessages", False)
    require_attributes = config.get("requireAttributes", False)
    forbid_duplicate = config.get("forbidDuplicateRules", True)
    forbid_empty = config.get("forbidEmptyRules", True)

    for req in requests:
        rel = req["rel_path"]
        class_name = req["class"]

        if require_rules and not req["has_rules"]:
            detail = f"FormRequest '{class_name}' missing required rules() method"
            findings.append({
                "kind": "missing_rules_method",
                "file": str(rel),
                "line": 0,
                "detail": detail,
                "severity": "critical",
            })

        if require_authorize and not req["has_authorize"]:
            detail = f"FormRequest '{class_name}' missing authorize() method"
            findings.append({
                "kind": "missing_authorize_method",
                "file": str(rel),
                "line": 0,
                "detail": detail,
                "severity": "critical",
            })

        if require_messages and not req["has_messages"]:
            detail = f"FormRequest '{class_name}' missing messages() method for custom validation messages"
            findings.append({
                "kind": "missing_messages_method",
                "file": str(rel),
                "line": 0,
                "detail": detail,
                "severity": "should_fix",
            })

        if require_attributes and not req["has_attributes"]:
            detail = f"FormRequest '{class_name}' missing attributes() method for custom field names"
            findings.append({
                "kind": "missing_attributes_method",
                "file": str(rel),
                "line": 0,
                "detail": detail,
                "severity": "should_fix",
            })

        if forbid_duplicate and req["rules"]:
            seen = set()
            for field, _ in req["rules"]:
                if field in seen:
                    detail = f"FormRequest '{class_name}' has duplicate validation rule for field '{field}'"
                    findings.append({
                        "kind": "duplicate_rule",
                        "file": str(req["rel_path"]),
                        "line": 0,
                        "detail": detail,
                        "severity": "should_fix",
                    })
                seen.add(field)

        if forbid_empty and req["has_rules"] and not req["rules"]:
            detail = f"FormRequest '{class_name}' has rules() method but returns empty array"
            findings.append({
                "kind": "empty_rules_array",
                "file": str(req["rel_path"]),
                "line": 0,
                "detail": detail,
                "severity": "should_fix",
            })

    return findings


def main() -> int:
    args = parse_args()

    try:
        repo = project_root()
    except SystemExit:
        print(f"{MARKER}: no .backend-suite/ found -- refusing", file=sys.stderr)
        return 2

    profile_data = profile(repo)
    lang = profile_data.get("adapters", {}).get("lang")
    if lang != "php":
        print(f"{MARKER}: adapter '{lang}' not supported (requires php)", file=sys.stderr)
        return 2

    try:
        adapter = load_adapter("php")
    except SystemExit as exc:
        print(f"{MARKER}: {exc}", file=sys.stderr)
        return 2

    # Check capability with the project context (not a bare None): the php
    # adapter offers form_requests only to projects that read as Laravel, so a
    # library like jikan honestly REFUSES here rather than crashing.
    caps = adapter.capabilities(AdapterContext(repo=repo, profile=profile_data,
                                               exceptions={}))
    if not any(c.name == "form_requests" for c in caps):
        print(f"{MARKER}: php adapter does not expose form_requests capability", file=sys.stderr)
        return 2

    config = load_config(repo)
    request_dirs = config.get("requestDirs", ["app/Http/Requests"])

    requests = find_form_requests(request_dirs, repo)

    if not requests:
        print(f"{MARKER}: no FormRequest classes found under {request_dirs} -- nothing to audit")
        return 0

    findings = audit_requests(requests, config)

    if args.out:
        out_path = repo / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(findings, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(repo, "form_request_validation") if args.findings is True else repo / args.findings,
            "form_request_validation",
            [F.make("form_request_validation", f.get("kind", "form_request_validation"),
                    f.get("detail") or "", severity=F.CRITICAL if f.get("severity") == "critical" else F.SHOULD_FIX,
                    file=f.get("file"), line=f.get("line"))
             for f in findings],
        )

    critical = sum(1 for f in findings if f.get("severity") == "critical")
    should_fix = sum(1 for f in findings if f.get("severity") == "should_fix")
    print(f"{MARKER}: {len(findings)} finding(s) ({critical} critical, {should_fix} should_fix)")

    if critical:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())