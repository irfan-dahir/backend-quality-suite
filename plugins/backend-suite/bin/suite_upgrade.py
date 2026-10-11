#!/usr/bin/env python3
"""Move a project between suite versions as a measured, reversible operation.

    # 1. What would change, on an unchanged tree — read-only, writes nothing
    python3 plugins/backend-suite/bin/suite_upgrade.py measure \\
        --consumer /path/to/project --from <rev> --to <rev>

    # 2. Apply the migration — plans by default, writes only under --apply
    python3 plugins/backend-suite/bin/suite_upgrade.py apply \\
        --consumer /path/to/project [--only sync-schema] [--apply]

    # 3. Pre-merge compatibility check, for THIS repo's own CI
    python3 plugins/backend-suite/bin/suite_upgrade.py compat --from <rev> --to <rev>

    # 4. Fleet view — which projects are on which version
    python3 plugins/backend-suite/bin/suite_upgrade.py fleet

`--json` on any subcommand emits the full report.

## Exit codes — the same contract as everything else here

    0   clean       nothing would change / nothing to do
    1   findings    there is something to report, and it is a real result
    2   refused     could not determine, or an action refused to run
    3   external    reserved (a revision owned by another repository)
    4   declined    the caller excluded every action
    5   stub        reserved

**Cannot-determine is 2 and is never collapsed into 0.** A migration check that
cannot see the old version must not report "compatible" — the whole reason this
tool exists is that a merge reached live client CI carrying four breaking changes
and every surface stayed quiet. Silence and a clean bill of health must not look
the same (CLAUDE.md; docs/CONCEPTS.md).

## Why `compat` is the one that matters

`measure` tells one project what an upgrade would do to it, after the change has
shipped. `compat` runs on a pull request, before it merges, and names the change
that will do it — `audit_tokens` flipping from always-0 to 1-on-findings,
`audit_error_handling` widening from critical-only to any finding, two audits
entering `DISABLED`, `--update-baseline` starting to refuse without
`--accept-new`. Those four are not hypotheticals; they are what happened, and
`e14048a..ba7029e` is the range they happened in, which is the fixture this
check's own test runs against.

Stdlib only, like everything else in this directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: E402

import installed_drift  # noqa: E402
from backend_suite.engine import fleet as fleet_engine  # noqa: E402
from backend_suite.engine import migrate, upgrade  # noqa: E402
from backend_suite.engine.upgrade import CannotDetermine  # noqa: E402

REPO = PLUGIN_ROOT.parents[1]

CLEAN, FINDINGS, REFUSED, EXTERNAL, DECLINED, STUB = 0, 1, 2, 3, 4, 5

MARK = {
    "clean": "✅", "unchanged": "✅", "applied": "✅",
    "findings": "🟡", "count-changed": "🟡", "planned": "🟡",
    "exit-changed": "🔴", "status-changed": "🔴", "critical": "🔴",
    "should-fix": "🟡", "refused": "⚪", "skipped": "⚪",
    "no-answer-either-side": "⚪", "disabled": "⛔", "absent": "⛔",
    "crashed": "🔴", "failed": "🔴",
}


def _emit(report: dict, lines: list[str], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n".join(lines))


# ------------------------------------------------------------------- 1. measure


def cmd_measure(args: argparse.Namespace) -> int:
    report = migrate.measure(
        Path(args.consumer), Path(args.repo), getattr(args, "from"), args.to,
        only=args.k, timeout=args.timeout, workdir=args.workdir,
    )
    lines = [
        f"{report['consumer']}",
        f"  old: {report['old']['rev']} ({report['old']['sha'][:12]})",
        f"  new: {report['new']['rev']} ({report['new']['sha'][:12]})",
        "",
        report["note"],
        "",
        f"{'AUDIT':<32}  {'BEFORE':<22}  {'AFTER':<22}  VERDICT",
        f"{'-' * 32}  {'-' * 22}  {'-' * 22}  -------",
    ]

    def cell(side: dict) -> str:
        count = "-" if side["findingsCount"] is None else str(side["findingsCount"])
        return f"{MARK.get(side['status'], '?')} {side['status']:<9} {count:>5} found"

    for row in report["audits"]:
        lines.append(
            f"{row['audit']:<32}  {cell(row['before']):<22}  "
            f"{cell(row['after']):<22}  {MARK.get(row['verdict'], '')} {row['verdict']}"
        )
    lines.append("")
    if report["changed"]:
        lines.append(f"{len(report['changed'])} audit(s) answer differently under the "
                     f"new version on an unchanged tree: {', '.join(report['changed'])}")
        lines.append("A verdict that changed without the code changing is the upgrade's "
                     "cost, not the project's regression.")
    else:
        lines.append("No audit answers differently under the new version.")
    lines.append("Neither run touched the consumer's own tree. Delete the scratch trees "
                 "above to undo this entirely.")
    _emit(report, lines, args.json)
    return FINDINGS if report["changed"] else CLEAN


# --------------------------------------------------------------------- 2. apply


def cmd_apply(args: argparse.Namespace) -> int:
    report = migrate.apply(
        Path(args.consumer), Path(args.plugin or PLUGIN_ROOT),
        write=args.apply, only=tuple(args.only or ()), skip=tuple(args.skip or ()),
        accept_new_for=tuple(args.accept_new_for or ()), timeout=args.timeout,
    )
    lines = [
        f"{report['consumer']}",
        f"  migrating to the suite at {report['plugin']}",
        f"  {'WRITING' if report['wrote'] else 'PLAN ONLY — nothing is written without --apply'}",
        "",
    ]
    for row in report["actions"]:
        lines.append(f"{MARK.get(row['status'], '?')} {row['action']:<26} "
                     f"{row['status']:<9} {row['detail']}")
        for target in row.get("writes", []):
            lines.append(f"      writes: {target}")
    lines.append("")
    if report["refused"]:
        lines.append("Refused action(s) did not run and are not satisfied: "
                     + ", ".join(report["refused"]))
    if report["failed"]:
        lines.append("Failed action(s): " + ", ".join(report["failed"]))
    if report["pending"] and not report["wrote"]:
        lines.append("Re-run with --apply to take the planned actions. "
                     "profile.json is never rewritten by any of them.")
    _emit(report, lines, args.json)

    if all(r["status"] == "skipped" for r in report["actions"]):
        return DECLINED
    if report["refused"] or report["failed"]:
        return REFUSED
    if report["pending"]:
        return FINDINGS
    return CLEAN


# -------------------------------------------------------------------- 3. compat


def cmd_compat(args: argparse.Namespace) -> int:
    report = upgrade.compare(Path(args.repo), getattr(args, "from"), args.to)
    lines = [
        f"{report['old']['rev']} ({report['old']['sha'][:12]})  ->  "
        f"{report['new']['rev']} ({report['new']['sha'][:12]})",
        "",
    ]
    for side in ("old", "new"):
        for note in report[side]["notes"]:
            lines.append(f"note ({side}): {note}")
    if report["old"]["notes"] or report["new"]["notes"]:
        lines.append("")

    if not report["findings"]:
        lines.append("No consumer-visible change found between these revisions.")
    for finding in report["findings"]:
        lines.append(f"{MARK.get(finding['severity'], '?')} {finding['category']}: "
                     f"{finding['subject']}")
        lines.append(f"   {finding['detail']}")
        if "before" in finding:
            lines.append(f"   before: {finding['before']}")
            lines.append(f"   after:  {finding['after']}")
    lines.append("")
    lines.append(f"{report['counts']['critical']} critical, "
                 f"{report['counts']['should-fix']} should-fix.")
    if report["findings"]:
        lines.append("Each of these changes what a consumer's CI reports on a tree "
                     "that did not change. Say so in the PR, or fix it before merging.")
    _emit(report, lines, args.json)
    return FINDINGS if report["findings"] else CLEAN


# --------------------------------------------------------------------- 4. fleet


def cmd_fleet(args: argparse.Namespace) -> int:
    raw = installed_drift.raw_records(Path(args.registry))
    report = fleet_engine.fleet(
        raw, plugins=tuple(args.plugin) if args.plugin else None)
    if not report["projects"]:
        raise CannotDetermine(
            f"no project-scope install of "
            f"{', '.join(args.plugin) if args.plugin else 'any plugin'} in "
            f"{args.registry} — an empty fleet and an unreadable registry must "
            f"not read the same, so this is a refusal, not 'zero projects'")

    lines = [f"{report['projectCount']} project(s), folded from "
             f"{report['registryEntryCount']} registry entries", ""]
    for row in report["projects"]:
        lines.append(row["project"])
        for name, pin in sorted(row["plugins"].items()):
            lines.append(f"    {name:<22} {str(pin['version']):<16} "
                         f"{pin['lastUpdated'] or '?'}")
        if row["mixedVersions"]:
            lines.append("    !! plugins pinned to different versions in the same project")
        if row["foldedWorktrees"]:
            lines.append(f"    ({len(row['foldedWorktrees'])} worktree entr"
                         f"{'y' if len(row['foldedWorktrees']) == 1 else 'ies'} "
                         f"folded into this project)")
    if report["userScope"]:
        lines.append("")
        lines.append("user scope (this machine's default, not a project):")
        for name, pin in sorted(report["userScope"].items()):
            lines.append(f"    {name:<22} {str(pin['version']):<16} "
                         f"{pin['lastUpdated'] or '?'}")
    versions = {p["version"] for row in report["projects"]
                for p in row["plugins"].values()}
    lines.append("")
    if len(versions) > 1:
        lines.append(f"{len(versions)} distinct version(s) in the fleet — an upgrade "
                     f"is not one operation.")
    _emit(report, lines, args.json)
    return FINDINGS if len(versions) > 1 else CLEAN


# ----------------------------------------------------------------------- argv


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", help="run both versions' audits against copies "
                                       "of a consumer tree and diff them")
    m.add_argument("--consumer", required=True, help="the consumer project root")
    m.add_argument("--from", required=True, help="the suite revision it is on now")
    m.add_argument("--to", required=True, help="the suite revision it would move to")
    m.add_argument("--repo", default=str(REPO), help="this suite repository")
    m.add_argument("-k", metavar="SUBSTR", help="only audits whose name contains SUBSTR")
    m.add_argument("--timeout", type=float, default=120.0, help="per-audit timeout")
    m.add_argument("--workdir", type=Path, default=None,
                   help="where to put the scratch copies (default: a temp dir)")
    m.set_defaults(func=cmd_measure)

    a = sub.add_parser("apply", help="take the migration actions, one at a time")
    a.add_argument("--consumer", required=True, help="the consumer project root")
    a.add_argument("--plugin", default=None,
                   help="the suite version to migrate to (default: this one)")
    a.add_argument("--apply", action="store_true",
                   help="actually write. Without it, nothing is written")
    a.add_argument("--only", action="append", choices=migrate.ACTIONS,
                   help="run only this action (repeatable)")
    a.add_argument("--skip", action="append", choices=migrate.ACTIONS,
                   help="skip this action (repeatable)")
    a.add_argument("--accept-new-for", action="append", metavar="AUDIT",
                   help="pass --accept-new when re-baselining this audit, because "
                        "a human reviewed its new findings (repeatable, per audit)")
    a.add_argument("--timeout", type=float, default=120.0)
    a.set_defaults(func=cmd_apply)

    c = sub.add_parser("compat", help="flag changes between two suite revisions "
                                      "that would break a consumer")
    c.add_argument("--from", required=True, help="the revision consumers are on")
    c.add_argument("--to", required=True, help="the revision about to merge")
    c.add_argument("--repo", default=str(REPO), help="this suite repository")
    c.set_defaults(func=cmd_compat)

    f = sub.add_parser("fleet", help="which projects use the suite, and on what version")
    f.add_argument("--registry", default=str(installed_drift.DEFAULT_REGISTRY),
                   help="path to installed_plugins.json")
    f.add_argument("--plugin", action="append",
                   help="restrict to this plugin by name (repeatable)")
    f.set_defaults(func=cmd_fleet)

    # Enumerate every subcommand's flags in the top-level --help, generated from
    # the parsers themselves rather than restated. Two reasons, and neither is
    # cosmetic: argparse hides a subparser's options behind `<sub> --help`, so a
    # reader (and `audit_prose_flags.py`, which harvests a documented flag and
    # checks it against `--help`) cannot see that `--consumer` is real; and a
    # hand-written list here would be a second copy of the flag set, which is the
    # drift this repo keeps finding. Built from `sub.choices`, so a flag added
    # above appears here with no edit.
    epilog = ["flags by subcommand (see `<subcommand> --help` for detail):"]
    for name, parser in sub.choices.items():
        options = sorted({
            opt for action in parser._actions for opt in action.option_strings
            if opt.startswith("--") and opt != "--help"
        })
        epilog.append(f"  {name}: {' '.join(options)}")
    ap.epilog = "\n".join(epilog)
    ap.formatter_class = argparse.RawDescriptionHelpFormatter
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CannotDetermine, installed_drift.CannotDetermine) as exc:
        # Exit 2, loudly, always. Never 0 — see this module's docstring.
        if args.json:
            print(json.dumps({"status": "cannot-determine", "reason": str(exc)},
                             indent=2))
        print(f"cannot determine: {exc}", file=sys.stderr)
        return REFUSED


if __name__ == "__main__":
    sys.exit(main())
