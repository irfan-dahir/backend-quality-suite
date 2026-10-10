"""Architecture-rule loading.

The four `scripts/audit_*.py` runners are portable in shape — walk files, match
imports, compare against a baseline, emit findings. What they enforce is not: the
banned imports, the layer directions, and the vetted name collisions are all facts
about one project's architecture. Those moved to `.design-suite/arch-rules.json`;
this module loads them.

An absent rules file is an error, not an empty rule set. A structural audit that
runs with nothing to enforce passes every time, which is the failure mode this
whole refactor keeps closing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from design_suite.engine.refusal import Refused  # noqa: E402

PROFILE = ".design-suite/profile.json"


def rules_path(repo: Path) -> str | None:
    """Where the profile says the architecture rules live."""
    profile_file = repo / PROFILE
    if not profile_file.is_file():
        return None
    try:
        profile = json.loads(profile_file.read_text())
    except (OSError, ValueError):
        return None
    return (profile.get("audits", {}) or {}).get("archRulesFile")


def load(repo: Path, section: str) -> dict:
    """One section of the rules file.

    Raises SystemExit with a usable message rather than returning {} — see the
    module docstring on why silence is the wrong default here.
    """
    rel = rules_path(repo)
    if not rel:
        raise Refused(
            f"{PROFILE} does not set audits.archRulesFile, so there are no architecture "
            f"rules to enforce. Refusing to run: an audit with no rules passes vacuously.")
    path = repo / rel
    if not path.is_file():
        raise Refused(f"architecture rules not found at {rel} (declared in {PROFILE})")
    try:
        rules = json.loads(path.read_text())
    except ValueError as exc:
        raise Refused(f"{rel} is not valid JSON: {exc}")
    if section not in rules:
        raise Refused(
            f"{rel} has no {section!r} section. Add it, or remove the audit that needs it — "
            f"do not leave a check that silently enforces nothing.")
    return rules[section]


def compiled_patterns(entries) -> list:
    """[(label, compiled regex)] from [{label, pattern}] config entries."""
    out = []
    for entry in entries:
        label = entry.get("label") or entry.get("pattern", "?")
        pattern = entry.get("pattern")
        if not pattern:
            continue
        out.append((label, re.compile(pattern)))
    return out
