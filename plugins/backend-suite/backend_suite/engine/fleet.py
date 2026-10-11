"""Which projects use this suite, and what version each is on.

The registry `bin/installed_drift.py` already reads —
`~/.claude/plugins/installed_plugins.json` — records one entry per *install
scope*: one for the user scope, and one for every project directory the plugin
was ever installed into. That list is not a fleet, for two reasons, and both are
the whole content of this module:

1. **Worktrees inflate it.** An agent worktree under `<project>/.claude/worktrees/
   <name>` registers as its own project. Measured on this machine: six
   project-scope entries for `backend-suite` that are two repositories plus four
   worktrees of one of them. A fleet view that reports six projects is reporting
   a number nobody can act on — nobody upgrades a worktree.

2. **The same project appears once per plugin.** `backend-suite` and
   `house-style` each carry their own record for the same directory, and
   the two can be pinned to different commits — which is itself worth seeing, so
   they are folded into one row per project with a version per plugin rather
   than collapsed into a single version.

This module is pure: it takes the registry's own decoded contents and returns
rows. The file read stays in `bin/installed_drift.py`, which already owns it —
a second registry reader is a second thing to keep true.

Stdlib only, like everything else here.
"""
from __future__ import annotations

from pathlib import PurePosixPath

# The path segment Claude Code creates agent worktrees under. A worktree is not a
# deployment of the suite; it is a copy of one, and it disappears.
WORKTREE_SEGMENT = (".claude", "worktrees")


def real_project_root(path: str) -> str:
    """The project a registry `projectPath` really belongs to.

    `<repo>/.claude/worktrees/<name>` folds back to `<repo>`. Matched on the
    directory layout rather than on the branch or directory *name*, because the
    harness generates those names at dispatch time and this repo's own rules note
    that nothing may depend on their shape. The layout is the stable fact.

    Anything else is returned unchanged — including a path that merely contains
    `.claude` elsewhere, since the fold only fires on the two segments adjacent.
    """
    parts = PurePosixPath(path).parts
    for i in range(len(parts) - 2):
        if parts[i:i + 2] == WORKTREE_SEGMENT:
            return str(PurePosixPath(*parts[:i]))
    return path


def fleet(raw: dict[str, list[dict]], *, plugins: tuple[str, ...] | None = None) -> dict:
    """One row per real project, with each plugin's pinned version.

    `raw` is the registry's `plugins` object: `{"<name>@<marketplace>": [record]}`.
    User-scope records carry no `projectPath` and are reported separately — they
    are the machine's default, not a project's choice, and merging them into the
    project list would invent a project that does not exist.
    """
    projects: dict[str, dict] = {}
    user_scope: dict[str, dict] = {}
    for key, records in raw.items():
        if not isinstance(records, list):
            continue
        name = key.split("@", 1)[0]
        if plugins and name not in plugins:
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            pin = {
                "version": record.get("version"),
                "sha": record.get("gitCommitSha"),
                "lastUpdated": record.get("lastUpdated") or record.get("installedAt"),
                "installPath": record.get("installPath"),
            }
            raw_path = record.get("projectPath")
            if not raw_path:
                user_scope[name] = pin
                continue
            root = real_project_root(str(raw_path))
            entry = projects.setdefault(
                root, {"project": root, "plugins": {}, "registryEntries": 0,
                       "foldedWorktrees": []})
            entry["registryEntries"] += 1
            if str(raw_path) != root and str(raw_path) not in entry["foldedWorktrees"]:
                entry["foldedWorktrees"].append(str(raw_path))
            # Newest wins, so the answer does not depend on list order. A project
            # whose worktrees are pinned to an older commit is still on the newer
            # one; the worktree is the stale copy, not the project.
            existing = entry["plugins"].get(name)
            if existing is None or str(pin["lastUpdated"] or "") > str(existing["lastUpdated"] or ""):
                entry["plugins"][name] = pin

    rows = sorted(projects.values(), key=lambda r: r["project"])
    for row in rows:
        row["foldedWorktrees"].sort()
        versions = {p["version"] for p in row["plugins"].values()}
        # Two plugins from the same marketplace pinned to different commits is a
        # real, reportable state — the house-style plugin lagging the universal
        # one is how a consumer ends up with a command doc that names a script
        # the installed engine does not have.
        row["mixedVersions"] = len(versions) > 1
    return {
        "projects": rows,
        "userScope": user_scope,
        "projectCount": len(rows),
        "registryEntryCount": sum(r["registryEntries"] for r in rows),
    }
