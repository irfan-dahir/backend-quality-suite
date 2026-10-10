#!/usr/bin/env python3
"""PostToolUse nudge (Bash): when a git commit or gh pr create runs, point to the
project's PR document (role `pr`) and its pre-PR checklist — the single canonical
source for these checks. Never auto-invokes or auto-writes anything: the checklist
covers doc review, decision logging, and asset registration, each of which needs
human judgment, not a generated placeholder.

The document is resolved through .design-suite/docs.manifest.json rather than
named directly, so this hook says the right thing in a project whose PR document
lives somewhere else or is called something else. If the role is unmapped the hook
degrades to a generic reminder instead of citing a path that does not exist —
pointing a reader at a missing file is worse than not citing one.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TRIGGER_RE = re.compile(r"\bgit\s+commit\b|\bgh\s+pr\s+create\b")

# Resolved inline rather than by importing a shared helper: this file is destined
# for ${CLAUDE_PLUGIN_ROOT}, where a relative import from the consuming repo would
# not resolve. Reading the manifest works from either home.
MANIFEST = ".design-suite/docs.manifest.json"


def role_path(role: str) -> str | None:
    """Path this project maps to `role`, or None if unmapped/unavailable."""
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        candidate = base / MANIFEST
        if candidate.is_file():
            try:
                roles = json.loads(candidate.read_text()).get("roles", {})
            except (OSError, ValueError):
                return None
            return roles.get(role)
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    if data.get("tool_name") != "Bash":
        return 0

    command = (data.get("tool_input", {}) or {}).get("command", "") or ""
    if not TRIGGER_RE.search(command):
        return 0

    pr_doc = role_path("pr")
    where = f"{pr_doc}'s Pre-PR checklist" if pr_doc else "this project's pre-PR checklist"

    print(json.dumps({
        "systemMessage": (
            f"Reminder: work through {where} before this PR goes out "
            "(doc drift, decision logging, asset registration, code-quality "
            "checks — all in one place there)."
        )
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
