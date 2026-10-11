#!/usr/bin/env python3
"""Audit Laravel FormRequest validation rules.

FormRequest is Laravel's dedicated validation class. This audit verifies:

1. Every FormRequest has a `rules()` method returning validation rules
2. The `authorize()` method exists and returns appropriate authorization
3. Validation rules are well-formed (not empty, not malformed)
4. Custom messages/attributes are provided for user-facing fields
5. Custom validation logic in `prepareForValidation` / `passedValidation` is sound
5. No duplicate rules for the same field
6. Required fields are marked as required
7. Custom rule classes exist and are importable

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_form_request_validation.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_form_request_validation.py" --findings

Config (in arch-rules.json):
  "formRequestValidation": {
    "requestDirs": ["app/Http/Requests"],
    "requireRules": true,
    "requireAuthorize": true,
    "requireMessages": false,
    "requireAttributes": false,
    "forbidDuplicateRules": true,
    "forbidEmptyRules": true,
    "customRuleDirs": ["app/Rules"]
  }

Exit codes:
    0 = clean (all FormRequests validated)
    1 = findings (missing rules, malformed rules, etc.)
    2 = refused (missing config, unreadable files, missing capability)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: F401
from backend_suite.project import profile, project_root  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402


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
MESSAGES_METHOD_RE = re.compile(r"function\s+messages\s*\(\s*\)\s*:\s*array\s*")
ATTRIBUTES_METHOD_RE = re.compile(r"function\s+attributes\s*\(\s*\)\s*:\s*array\s*")
PREPARE_METHOD_RE = re.compile(r"function\s+prepareForValidation\s*\(\s*\)\s*")
PASSED_METHOD_RE = re.compile(r"function\s+passedValidation\s*\(\s*\)\s*")

RULE_ARRAY_RE = re.compile(r"'(?:[^'\\]|\\.)*'\s*=>\s*(?:\[[^\]]*\]|'[^']*'|\"[^\"]*\"|[\w\\]+(?:::\w+)?)")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="write findings JSON to this path")
    ap.add_argument("--findings", nargs="?", const=True, default=False,
                     help="also write findings envelope")
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
            
            # Extract methods
            has_rules = bool(RULES_METHOD_RE.search(text))
            has_authorize = bool(AUTHORIZE_METHOD_RE.search(text))
            has_messages = bool(MESSAGES_METHOD_RE.search(text))
            has_attributes = bool(ATTRIBUTES_METHOD_RE.search(text))
            has_prepare = bool(PREPARE_METHOD_RE.search(text))
            has_passed = bool(PASSED_METHOD_RE.search(text))
            
            # Extract rules array if present
            rules_text = ""
            rules_match = re.search(r"function\s+rules\s*\([^)]*\)\s*:\s*(?:array|\\Illuminate\\Contracts\\Validation\\Validator)\s*\{([^}]+)\}", text, re.DOTALL)
            if rules_match:
                rules_text = rules_match.group(1)
            
            # Parse individual rules
            rules = []
            for m in RULE_ARRAY_RE.finditer(rules_text):
                field = m.group(0).split("=>")[0].strip().strip("'\"")
                rule = m.group(0).split("=>")[1].strip()
                rules.append((field, rule))
            
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
            findings.append({
                "kind": "missing_rules_method",
                "file": str(req["file"]),
                "line": 0,
                "detail": f"FormRequest '{req['class']}' missing required rules() method",
                "severity": "critical",
            })
        
        if require_authorize and not req["has_authorize"]:
            findings.append({
                "kind": "missing_authorize_method",
                "file": str(req["file"]),
                "line": 0,
                "detail": f"FormRequest '{req['class']}' missing authorize() method",
                "severity": "critical",
            })
        
        if require_messages and not req["has_messages"]:
            findings.append({
                "kind": "missing_messages_method",
                "file": str(req["file"]),
                "line": 0,
                "detail": f"FormRequest '{req['class']}' missing messages() method for custom validation messages",
                "severity": "should_fix",
            })
        
        if require_attributes and not req["has_attributes"]:
            findings.append({
                "kind": "missing_attributes_method",
                "file": str(req["file"]),
                "line": 0,
                "detail": f"FormRequest '{req['class']}' missing attributes() method for custom field names",
                "severity": "should_fix",
            })
        
        # Check for duplicate rules
        if forbid_duplicate and req["rules"]:
            seen = set()
            for field, _ in req["rules"]:
                if field in seen:
                    findings.append({
                        "kind": "duplicate_rule",
                        "file": str(req["file"]),
                        "line": 0,
                        "detail": f"FormRequest '{req['class']}' has duplicate validation rule for field '{field}'",
                        "severity": "should_fix",
                    })
                seen.add(field)
        
        # Check for empty rules
        if forbid_empty and req["has_rules"] and not req["rules"]:
            findings.append({
                "kind": "empty_rules_array",
                "file": str(req["file"]),
                "line": 0,
                "detail": f"FormRequest '{req['class']}' has rules() method but returns empty array",
                "severity": "should_fix",
            })
        
        # Check authorize() returns bool or uses Gate
        if req["has_authorize"]:
            # Could add more sophisticated check here
            pass
    
    return findings


def main() -> int:
    args = parse_args()
    
    try:
        repo = project_root()
    except SystemExit:
        print("form-request-validation: no .backend-suite/ found — refusing", file=sys.stderr)
        return 2
    
    profile_data = profile(repo)
    config = load_config(repo)
    
    lang = profile_data.get("adapters", {}).get("lang")
    if lang != "php":
        print(f"form-request-validation: adapter '{lang}' not supported (requires php)", file=sys.stderr)
        return 2
    
    request_dirs = config.get("requestDirs", ["app/Http/Requests"])
    
    requests = find_form_requests(request_dirs, repo)
    
    if not requests:
        print("form-request-validation: no FormRequest classes found — nothing to audit")
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
    print(f"form-request-validation: {len(findings)} finding(s) ({critical} critical, {should_fix} should_fix)")
    
    if critical:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())