#!/usr/bin/env python3
"""Resolve a doc role, for house-style skills only.

## Why this exists at all

`backend-suite/bin/resolve.py` is the real resolver and the only one that should
ever be extended. This is a deliberate, minimal duplicate, and the duplication
needs justifying because it is the kind of thing a future reader will want to
delete.

`house-style` cannot call backend-suite's copy:

  * `${CLAUDE_PLUGIN_ROOT}` points at *this* plugin, which has no `bin/` of its
    own beyond this file.
  * The plugin cache nests every plugin under its own version hash
    (`cache/<marketplace>/<plugin>/<hash>/`), so no sibling-relative path from
    here is stable across updates. `../../backend-suite/*/bin/resolve.py` depends
    on cache internals that are explicitly documented as ephemeral.
  * `resolve.py` imports `_bootstrap`, which puts backend-suite's package on
    `sys.path`. Copying the file alone would not work; copying the package would
    be a far worse duplication than this.

So the two house-style skills that need a doc role got one of: a broken resolve
step, or ~40 lines that re-read the manifest. This is the second.

## What is duplicated, and what is not

Only the lookup, which is a dict access — verified against `resolve.py`, which
prints `roles[role]` unjoined, so there is no path-joining logic to get wrong.
The exit codes are mirrored because skills branch on them:

    0  resolved, path on stdout
    2  unknown role, or no manifest — stop and ask, never guess a path
    3  role is owned by another repository — read it, never edit it
    4  role was declined, with a reason — skip the check AND say so, with the
       reason, in the report; declined is not passed
    5  the document is a stub: registered, mapped, unwritten. Path is still
       printed, but it is outstanding work, never coverage

Codes 4 and 5 are duplicated here for the same reason 2 and 3 are: a skill that
branches on exit codes must get the same answer whichever resolver it reached. A
house-style skill that treated a decline as "unknown role" would re-open a
settled decision, and one that treated a stub as exit 0 would report an empty
document as documentation — which is the whole failure these codes exist for.

Not duplicated, on purpose: `--all`, `--dirs`, `--reverse`, `--check`,
`--profile`, `--manifest`. House-style needs a role and a directory. If it ever
needs more than that, the right move is to reconsider the plugin split rather
than grow this file.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" pr
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" --dir derived
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MARKER = ".backend-suite"
MANIFEST = f"{MARKER}/docs.manifest.json"


def project_root() -> Path:
    """Same contract as backend_suite.project.project_root — exit rather than guess.

    A plain `cwd` fallback would silently treat a subdirectory as the whole
    project, which reports fewer findings and reads like an improvement.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (Path(env) / MARKER).is_dir():
        return Path(env)
    here = Path.cwd().resolve()
    # The decision is backend_suite.project's own walk(), generated below — not a
    # hand-kept lookalike. Only the refusal wording is local.
    found, git_root, _outer = walk(here)
    if found is not None:
        return found
    if git_root is not None:
        print(f"{git_root} is a git repository with no {MARKER}/ — refusing "
              f"to fall through to any configured project above it.",
              file=sys.stderr)
        raise SystemExit(2)
    print(f"no {MARKER}/ found from {here} upward — is this a configured project?",
          file=sys.stderr)
    raise SystemExit(2)


# BEGIN GENERATED walk — from backend-suite/backend_suite/project.py by
# backend-suite/bin/sync_house_style_walk.py. Do not hand-edit.
def walk(here: Path) -> tuple[Path | None, Path | None, Path | None]:
    """(configured root, blocking git root, outer configured root) from `here` up.

    The first is the answer when found. Otherwise the second is the nearest git
    root that has no marker (None if the walk hit the filesystem root), and the
    third is the configured directory above it that the walk refused to cross —
    reported so the refusal can name both, never returned as the answer.
    """
    chain = [here, *here.parents]
    for i, candidate in enumerate(chain):
        if (candidate / MARKER).is_dir():
            return candidate, None, None
        if (candidate / ".git").exists():
            outer = next((c for c in chain[i + 1:] if (c / MARKER).is_dir()), None)
            return None, candidate, outer
    return None, None, None
# END GENERATED walk


# Parity with the `aliases` in backend-suite's templates/docs/roles.json. This is
# a local copy for the same reason is_stub is: this script cannot import the
# engine across the plugin cache's per-plugin version hashes. Without it, a
# manifest written against the new vocabulary answers `entry-point` with exit 2
# — unknown role — while backend-suite's own resolver answers it fine, which is
# exactly the drift the parity test exists to catch.
ALIASES = {"instructions": "entry-point"}

# backend-suite's resolver follows the rename in BOTH directions
# (archetypes.canonical_role for old -> new, archetypes.aliases_of for new ->
# old), because the two directions are different real situations: a manifest
# written before the rename answering a skill written after it, and a manifest
# written after it answering a caller written before. This copy only had the
# forward map, so a pre-rename manifest answered `entry-point` with exit 2 while
# backend-suite's resolver answered it fine — a live parity gap, found by the
# alias assertions added to resolve_test.py rather than by anything in the field.
ALIASES_REVERSED = {new: old for old, new in ALIASES.items()}


def is_stub(path: Path) -> bool:
    """Parity with backend_suite.engine.doc_roles.is_stub — `status: stub` in the
    document's leading `---` frontmatter block."""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            if handle.readline().strip() != "---":
                return False
            for _ in range(200):
                line = handle.readline()
                if not line or line.strip() in ("---", "..."):
                    return False
                key, sep, value = line.partition(":")
                if sep and key.strip() == "status":
                    return value.strip().strip("\"'").lower() == "stub"
    except OSError:
        return False
    return False


def main(argv: list[str]) -> int:
    repo = project_root()
    path = repo / MANIFEST
    if not path.is_file():
        print(f"no manifest at {MANIFEST}", file=sys.stderr)
        return 2
    manifest = json.loads(path.read_text())

    if argv[:1] == ["--dir"]:
        if len(argv) < 2:
            print("--dir needs a name", file=sys.stderr)
            return 2
        dirs = manifest.get("directories", {})
        if argv[1] not in dirs:
            print(f"unknown directory role {argv[1]!r}. Known:", file=sys.stderr)
            for known in sorted(dirs):
                print(f"  {known}", file=sys.stderr)
            return 2
        print(dirs[argv[1]])
        return 0

    if not argv or argv[0].startswith("-"):
        print(f"usage: {Path(__file__).name} <role> | --dir <name>", file=sys.stderr)
        return 2

    role = argv[0]
    roles: dict[str, str] = manifest.get("roles", {})
    external = {k: v for k, v in manifest.get("externalRoles", {}).items()
                if not k.startswith("_")}

    declined = {k: v for k, v in (manifest.get("declinedRoles") or {}).items()
                if not k.startswith("_") and isinstance(v, dict)}

    # Before every other check, so a decline or a mapping written under the
    # canonical name still applies when a skill asks by the old one.
    if role not in roles and role not in external and role not in declined:
        for candidate in (ALIASES.get(role), ALIASES_REVERSED.get(role)):
            if candidate and (candidate in roles or candidate in external
                              or candidate in declined):
                role = candidate
                break

    if role in declined:
        entry = declined[role]
        reason = entry.get("declined") or "NO REASON RECORDED"
        print(reason)
        print(f"role {role!r} declined: {reason} — skip the check that needed it AND "
              f"say so, with this reason, in your report", file=sys.stderr)
        return 4

    if role in external:
        ref = external[role]
        print(f"{ref.get('repo', '')}/blob/main/{ref.get('path', '')}")
        print(f"role {role!r} is owned by another repository — do not edit it here",
              file=sys.stderr)
        return 3

    if role not in roles:
        print(f"unknown role {role!r}. Known roles:", file=sys.stderr)
        for known in sorted(roles):
            print(f"  {known}", file=sys.stderr)
        for known in sorted(external):
            print(f"  {known} (external)", file=sys.stderr)
        for known in sorted(declined):
            print(f"  {known} (declined)", file=sys.stderr)
        return 2

    print(roles[role])
    if is_stub(repo / roles[role]):
        print(f"role {role!r} maps to {roles[role]}, which is a stub — registered "
              f"but unwritten. Outstanding work, never coverage", file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
