#!/usr/bin/env python3
"""Generate per-harness files (AGENTS.md block, MCP configs, skills mirror) into a project.

    backend-suite harness                 preview: list what would be written, write nothing
    backend-suite harness --apply         write exactly the previewed files
    backend-suite harness --check         exit 0 current, 1 stale, 2 cannot determine
    backend-suite harness --diff          preview with full new content of each file
    backend-suite harness --project DIR   target DIR instead of the current directory

Explicit tier: --apply writes into the project root (AGENTS.md, .cursor/, .vscode/,
.codex/, .gemini/, opencode.json, .aider.conf.yml, .agents/skills/, .devin/skills/;
plus .mcp.json and .claude/skills/ only with --include-claude — by default they are
skipped because the Claude plugin already provides both). Every MCP config runs
`backend-suite mcp`, so the CLI must be on PATH; preview warns when it is not, so it runs only on a direct request. Text outside
the generated markers, and every JSON key the suite does not own, is preserved.
It never writes outside the project: user-level-only harnesses (Devin Desktop,
Cline) and formats the research doc leaves unverified (Zed's entry shape) are
printed as instructions instead.

Exit codes: 0 done / current; 1 --check found stale files; 2 could not determine
(a file it refused to touch, e.g. JSON with comments, or a hand-written SKILL.md).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: E402

from backend_suite import harness_files as H  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--project", default=".")
    ap.add_argument("--include-claude", action="store_true",
                    help="also generate .mcp.json and .claude/skills/ (off by default: "
                         "the Claude plugin already provides both)")
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"harness: {project} is not a directory", file=sys.stderr)
        return 2

    plan = H.build_plan(project, PLUGIN_ROOT, args.include_claude)

    if args.check:
        for rel in sorted(plan.writes):
            print(f"STALE      {rel}")
        for rel, why in plan.refusals:
            print(f"CANNOT DETERMINE  {rel}: {why}")
        if plan.refusals:
            return 2
        if plan.writes:
            print(f"harness --check: {len(plan.writes)} generated file(s) stale or "
                  f"missing — run `backend-suite harness --apply`.")
            return 1
        print(f"harness --check: {len(plan.unchanged)} generated file(s) current.")
        return 0

    verb = "wrote" if args.apply else "would write"
    for rel in sorted(plan.writes):
        state = "update" if (project / rel).exists() else "create"
        print(f"{verb} ({state})  {rel}")
        if args.diff and not args.apply:
            print("    | " + plan.writes[rel].rstrip("\n").replace("\n", "\n    | "))
        if args.apply:
            p = project / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(plan.writes[rel], encoding="utf-8")
    print(f"unchanged: {len(plan.unchanged)} file(s)")
    for rel, why in plan.refusals:
        print(f"REFUSED  {rel}: {why}", file=sys.stderr)
    if plan.instructions:
        print("\nDo by hand (not written):")
        for i in plan.instructions:
            print(f"  - {i}")
    if plan.warnings:
        print("\nWiring warnings:")
        for w in plan.warnings:
            print(f"  ! {w}")
    if not args.apply and plan.writes:
        print("\nPreview only — nothing written. Re-run with --apply to write these files.")
    return 2 if plan.refusals else 0


if __name__ == "__main__":
    sys.exit(main())
