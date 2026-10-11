#!/usr/bin/env python3
"""Query a project's decision log(s) at read time — no synced index file.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/query_decisions.py"                # list all
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/query_decisions.py" --open
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/query_decisions.py" --resolved
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/query_decisions.py" --keyword tsx
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/query_decisions.py" --json

## Why a query tool and not a synced index (issue #60)

A separate `decisions-index.json` duplicating the markdown log is exactly the
drift risk the suite's governing principle exists to rule out: a stale index
and a caught-up one look identical until someone checks, and every entry filed
by hand or via `/log-decision` would need to *also* touch the index or it goes
silently out of date. So this reads the project's existing decision-log
markdown directly, at query time. No second file, nothing to keep in sync.

## The convention it parses

`docs/ROADMAP.md`'s own `## Decisions` section (a heading per decision carrying
a ✅/🔴 status marker, prose reasoning underneath) is the target shape. The
parser — `DECISION_SECTION_HEADING_RE` / `ENTRY_HEADING_RE` in
`backend_suite/engine/decisions.py` — is shared with
`bin/audit_proposal_status.py` (issue #51), which vetted this convention
against this repo's own ROADMAP.md first. #51 asks "is this doc's header
consistent with its own body"; this asks "what decisions exist, across
however many decision documents this project has, open or resolved, matching
a keyword" — same parser, different question.

## Finding the log(s): role first, explicit degrade second

`decisions` is a registered doc role (see `docs/DOC-ROLES.md`) — normally
resolved the same way every other skill resolves a doc:

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions --check

But this tool tolerates the two situations `resolve.py`'s own contract calls
out as legitimate rather than treating either as a silent empty result:

* **unmapped role, no manifest at all** (exit 2) — this project has not (yet)
  told the suite where its decision log lives. Rather than stopping cold (a
  query tool has no document to write into, unlike `/log-decision`, so it can
  usefully degrade instead of only asking), it falls back to the conventions
  the issue #60 research found in use: a `docs/decisions/` directory of
  per-decision files, or a full markdown sweep for the ✅/🔴 heading
  convention (the same degrade `audit_proposal_status.py` performs when
  `docs/proposals/` doesn't exist). Either fallback is announced on stderr —
  never silent.
* **role mapped but the file is missing** (exit 1) — reported as a project
  defect and treated as `CapabilityError`-shaped: a hard non-zero exit, never
  an empty list dressed up as "no decisions".

Finding **zero** parseable decision sections anywhere is `INERT` (exit 2), not
a clean "0 decisions" answer — those are different facts. A filter (`--open`,
`--keyword`) that matches nothing *after* decisions were found and parsed is a
legitimate answer and exits 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side effect: puts the plugin on sys.path)
import resolve as _resolve  # noqa: E402  (bin/resolve.py — reused, not reimplemented)
from backend_suite.engine.decisions import DecisionEntry, find_all_decision_sections  # noqa: E402

CONVENTIONAL_DIR = "docs/decisions"


def _iter_markdown(scan_root: Path):
    for p in sorted(scan_root.rglob("*.md")):
        parts = set(p.relative_to(scan_root).parts)
        if parts & {".git", "node_modules", ".backend-suite"}:
            continue
        yield p


def resolve_sources(repo: Path, forced_file: str | None) -> tuple[list[Path], bool]:
    """Return (files to parse, degraded) or raise SystemExit with a clear message.

    `degraded` means a fallback convention was used instead of a mapped role —
    always announced to the caller, never silently substituted.
    """
    if forced_file:
        forced_path = repo / forced_file
        if not forced_path.is_file():
            print(f"query_decisions: --file {forced_file} does not exist", file=sys.stderr)
            raise SystemExit(2)
        return [forced_path], False

    manifest_path = repo / _resolve.DEFAULT_MANIFEST
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        roles = manifest.get("roles", {})
        external = {k: v for k, v in manifest.get("externalRoles", {}).items()
                    if not k.startswith("_")}

        if "decisions" in external:
            ref = external["decisions"]
            print(f"query_decisions: role 'decisions' is owned by another repository "
                  f"({ref.get('repo', '')}/{ref.get('path', '')}) — read-only, not editable "
                  f"from here.", file=sys.stderr)
            raise SystemExit(3)

        if "decisions" in roles:
            mapped = repo / roles["decisions"]
            if not mapped.is_file():
                print(f"query_decisions: role 'decisions' maps to {roles['decisions']}, "
                      f"which does not exist. Reporting as a project defect, not scanning "
                      f"a guessed path instead.", file=sys.stderr)
                raise SystemExit(1)
            return [mapped], False

    # Unmapped role (or no manifest at all): degrade explicitly rather than
    # guess a path or stop cold — a read-only query tool can usefully fall back
    # where a document-writing skill (log-decision) cannot.
    decisions_dir = repo / CONVENTIONAL_DIR
    if decisions_dir.is_dir():
        files = list(_iter_markdown(decisions_dir))
        print(f"query_decisions: 'decisions' role is not mapped in "
              f"{_resolve.DEFAULT_MANIFEST} — degraded to the conventional "
              f"{CONVENTIONAL_DIR}/ directory ({len(files)} file(s)) instead of a mapped "
              f"document.", file=sys.stderr)
        return files, True

    all_md = list(_iter_markdown(repo))
    print(f"query_decisions: 'decisions' role is not mapped and no {CONVENTIONAL_DIR}/ "
          f"directory exists — degraded to scanning every *.md under {repo} for the "
          f"✅/🔴 decision-heading convention instead of a dedicated decision log.",
          file=sys.stderr)
    return all_md, True


def collect_entries(files: list[Path], repo: Path) -> list[tuple[str, DecisionEntry]]:
    """(source path relative to repo, entry) for every ✅/🔴 heading found."""
    out: list[tuple[str, DecisionEntry]] = []
    for path in files:
        text = path.read_text(errors="replace")
        rel = path.relative_to(repo).as_posix()
        for section in find_all_decision_sections(text):
            for entry in section.entries:
                out.append((rel, entry))
    return out


def entry_to_dict(source: str, entry: DecisionEntry) -> dict:
    return {
        "source": source,
        "line": entry.line,
        "resolved": entry.resolved,
        "marker": entry.marker,
        "number": entry.number,
        "title": entry.title,
        "date": entry.date,
        "body": entry.body,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="repository root (default: resolved project root)")
    parser.add_argument("--file", help="parse this file instead of resolving the 'decisions' "
                                        "role or scanning conventional locations")
    status = parser.add_mutually_exclusive_group()
    status.add_argument("--open", action="store_true", dest="open_only",
                         help="only 🔴 open decisions")
    status.add_argument("--resolved", action="store_true", dest="resolved_only",
                         help="only ✅ resolved decisions")
    parser.add_argument("--keyword", "--topic", dest="keyword",
                         help="case-insensitive substring match against heading or body")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()

    if args.repo:
        repo = Path(args.repo).resolve()
        if not repo.is_dir():
            print(f"query_decisions: {repo} is not a directory", file=sys.stderr)
            return 2
    else:
        repo = _resolve.REPO

    try:
        files, degraded = resolve_sources(repo, args.file)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if not files:
        print(f"query_decisions: no markdown files found to parse under {repo} — "
              f"INERT, not clean: refusing to report a pass on an empty sweep.",
              file=sys.stderr)
        return 2

    entries = collect_entries(files, repo)
    if not entries:
        print(f"query_decisions: {len(files)} file(s) scanned, none contained a "
              f"`## Decisions`-shaped section with ✅/🔴 headings — INERT, not clean: "
              f"either this project has no decisions logged yet, or it spells the "
              f"convention differently and this tool cannot see it.", file=sys.stderr)
        return 2

    filtered = entries
    if args.open_only:
        filtered = [(s, e) for s, e in filtered if not e.resolved]
    if args.resolved_only:
        filtered = [(s, e) for s, e in filtered if e.resolved]
    if args.keyword:
        filtered = [(s, e) for s, e in filtered if e.matches(args.keyword)]

    if args.json:
        print(json.dumps({
            "degraded": degraded,
            "sources": sorted({s for s, _ in entries}),
            "total_found": len(entries),
            "matched": len(filtered),
            "decisions": [entry_to_dict(s, e) for s, e in filtered],
        }, indent=2))
    else:
        if degraded:
            print("(degraded: see stderr for why)", file=sys.stderr)
        for source, entry in filtered:
            marker = entry.marker
            number = f"{entry.number} " if entry.number else ""
            date = f" ({entry.date})" if entry.date else ""
            print(f"{marker} {number}{entry.title}{date}  [{source}:{entry.line}]")
        print(f"\nquery_decisions: {len(entries)} decision(s) found across {len(files)} "
              f"file(s), {len(filtered)} matched the given filter(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
