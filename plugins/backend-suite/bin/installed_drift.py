#!/usr/bin/env python3
"""Compare what this repo *ships* against what is actually *installed* in the
Claude Code plugin cache, and report the difference.

    python3 plugins/backend-suite/bin/installed_drift.py
    python3 plugins/backend-suite/bin/installed_drift.py --json
    python3 plugins/backend-suite/bin/installed_drift.py --plugin backend-suite

## Why this exists

A user reads `docs/USER-GUIDE.md`, sees 41 commands, and invokes one — and it
is not there. The installed copy of the plugin is pinned to whatever commit was
current when `/plugin install` last ran; nothing in the running session says so.
Measured on this machine: the repo shipped 41 backend-suite commands while the
installed cache held 30. Eleven skills were documented, discoverable in the
catalogue, referenced by chains — and absent. There was no surface that could
tell you.

That is the governing principle's exact failure shape: the absence of a skill
is indistinguishable from the skill being present and simply not triggering.

## What it compares

For each plugin under `plugins/`, the set of `commands/*.md` stems, the set of
`agents/*.md` stems, and the set of `skills/*/` names, as shipped in the working
tree, against the same sets in the installed cache directory recorded for that
plugin in `~/.claude/plugins/installed_plugins.json`.

Content is deliberately NOT diffed. A stale-but-present command is a different
and much quieter problem than a missing one, and conflating them would make the
exit code useless. What is reported instead is the installed commit SHA and
whether this repo's HEAD is ahead of it, which is the actionable fact.

## Exit codes

    0   in sync — every shipped component is installed
    1   drift  — at least one shipped component is missing from the install,
                 or the install carries something the repo no longer ships
    2   cannot determine — no install record, no cache directory, unreadable
                 JSON, or the repo ships no components at all

Exit 2 is never collapsed into 0. "I could not look" and "I looked and it was
clean" are different answers, and a check that returns the second when it means
the first is the bug this whole repo is organised against. Every exit-2 path
prints the reason to stderr.

Stdlib only, like everything else in this directory.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
REPO = BIN.parents[2]

IN_SYNC, DRIFT, CANNOT_DETERMINE = 0, 1, 2

# Where Claude Code records what it actually installed. Overridable for tests.
DEFAULT_REGISTRY = Path.home() / ".claude" / "plugins" / "installed_plugins.json"

# The component kinds a user can invoke, and how each is enumerated on disk.
# A kind absent from BOTH sides is not drift; a kind present on one side only is.
KINDS = ("commands", "agents", "skills")


class CannotDetermine(Exception):
    """Raised when the comparison cannot be made at all.

    Carries the human-readable reason so the caller can print it rather than
    swallowing it — silence here would read as 'clean'.
    """


def _stems(root: Path, kind: str) -> set[str]:
    """Enumerate one kind of component under a plugin root.

    Returns an empty set when the directory does not exist, which is correct:
    a plugin that ships no agents has no agents to drift.
    """
    d = root / kind
    if not d.is_dir():
        return set()
    if kind == "skills":
        # A skill is a directory containing SKILL.md, not a flat file.
        return {p.name for p in d.iterdir() if p.is_dir() and (p / "SKILL.md").exists()}
    return {p.stem for p in d.glob("*.md")}


def shipped_plugins(repo: Path) -> dict[str, Path]:
    """Plugin roots in the working tree, keyed by plugin name.

    A directory only counts as a plugin if it carries `.claude-plugin/plugin.json`
    — the same marker the installer uses. A stray directory under `plugins/`
    must not be reported as an uninstalled plugin.
    """
    out: dict[str, Path] = {}
    base = repo / "plugins"
    if not base.is_dir():
        return out
    for p in sorted(base.iterdir()):
        manifest = p / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        try:
            name = json.loads(manifest.read_text()).get("name") or p.name
        except (OSError, json.JSONDecodeError):
            # A manifest we cannot read is not a plugin we can compare. Fall
            # back to the directory name rather than dropping it silently —
            # dropping it would hide a whole plugin's worth of drift.
            name = p.name
        out[str(name)] = p
    return out


def raw_records(registry: Path) -> dict[str, list[dict]]:
    """The registry's `plugins` object, decoded, with every scope's record intact.

    Split out of `installed_records` below (which collapses each key to a single
    winning record) because the fleet view needs the *uncollapsed* list: one
    entry per install scope is exactly the per-project detail it reports. Opening
    this file somewhere else to get that detail back would be a second registry
    reader, which is the duplication this module already exists to avoid.
    """
    if not registry.is_file():
        raise CannotDetermine(f"no install registry at {registry}")
    try:
        data = json.loads(registry.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CannotDetermine(f"install registry at {registry} is unreadable: {e}") from e

    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        raise CannotDetermine(f"install registry at {registry} has no 'plugins' object")
    return plugins


def installed_records(registry: Path) -> dict[str, dict]:
    """Read the install registry into {plugin_name: record}.

    The registry stores one list of records per `name@marketplace` key — one
    entry per scope (user, and one per project). They all point at the same
    install path in practice; the newest `lastUpdated` wins if they ever differ,
    so the answer does not depend on list order.
    """
    out: dict[str, dict] = {}
    for key, records in raw_records(registry).items():
        if not isinstance(records, list) or not records:
            continue
        name = key.split("@", 1)[0]
        best = max(records, key=lambda r: str(r.get("lastUpdated") or ""))
        out[name] = best
    return out


def _head_is_ahead_of(sha: str | None, repo: Path) -> bool | None:
    """True when HEAD is strictly ahead of `sha`, None when unknowable.

    None — not False — when the SHA is missing from this clone or git is not
    available. 'I cannot tell whether you are behind' must not render as 'you
    are up to date'.
    """
    if not sha:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", f"{sha}..HEAD"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return int(r.stdout.strip()) > 0
    except ValueError:
        return None


def compare(repo: Path = REPO, registry: Path = DEFAULT_REGISTRY,
            only: str | None = None) -> dict:
    """Build the full comparison. Raises CannotDetermine when it cannot be made."""
    shipped = shipped_plugins(repo)
    if only:
        shipped = {k: v for k, v in shipped.items() if k == only}
        if not shipped:
            raise CannotDetermine(f"no plugin named {only!r} under {repo / 'plugins'}")
    if not shipped:
        raise CannotDetermine(f"no plugins found under {repo / 'plugins'}")

    records = installed_records(registry)

    report: dict = {"repo": str(repo), "registry": str(registry), "plugins": []}
    for name, root in shipped.items():
        entry: dict = {"name": name, "kinds": {}, "missing_total": 0, "extra_total": 0}
        record = records.get(name)
        if record is None:
            entry["status"] = "not-installed"
            entry["reason"] = f"{name} has no record in the install registry"
            report["plugins"].append(entry)
            continue

        install_path = Path(str(record.get("installPath") or ""))
        entry["installed_sha"] = record.get("gitCommitSha")
        entry["installed_at"] = record.get("lastUpdated") or record.get("installedAt")
        entry["install_path"] = str(install_path)
        if not install_path.is_dir():
            entry["status"] = "cache-missing"
            entry["reason"] = f"recorded install path does not exist: {install_path}"
            report["plugins"].append(entry)
            continue

        entry["status"] = "compared"
        entry["head_ahead_of_install"] = _head_is_ahead_of(entry["installed_sha"], repo)
        for kind in KINDS:
            ship, inst = _stems(root, kind), _stems(install_path, kind)
            if not ship and not inst:
                continue
            missing, extra = sorted(ship - inst), sorted(inst - ship)
            entry["kinds"][kind] = {
                "shipped": len(ship), "installed": len(inst),
                "missing": missing, "extra": extra,
            }
            entry["missing_total"] += len(missing)
            entry["extra_total"] += len(extra)
        report["plugins"].append(entry)

    # A plugin we could not compare at all makes the whole run indeterminate.
    # Rolling it into "no drift found" is exactly the silence this guards.
    undetermined = [p for p in report["plugins"] if p["status"] != "compared"]
    report["undetermined"] = [p["name"] for p in undetermined]
    report["drifted"] = [
        p["name"] for p in report["plugins"]
        if p["status"] == "compared" and (p["missing_total"] or p["extra_total"])
    ]
    return report


def render(report: dict) -> list[str]:
    lines: list[str] = []
    for p in report["plugins"]:
        if p["status"] != "compared":
            lines.append(f"?  {p['name']}: {p['reason']}")
            continue
        head = f"{p['name']}  (installed {str(p.get('installed_sha') or '?')[:12]}"
        if p.get("installed_at"):
            head += f", {p['installed_at']}"
        head += ")"
        lines.append(head)
        for kind, k in p["kinds"].items():
            mark = "OK " if not (k["missing"] or k["extra"]) else "!! "
            lines.append(f"  {mark}{kind}: {k['shipped']} shipped, {k['installed']} installed")
            for m in k["missing"]:
                lines.append(f"       MISSING from install: {m}")
            for e in k["extra"]:
                lines.append(f"       only in install (repo no longer ships): {e}")
        if p.get("head_ahead_of_install") is True:
            lines.append("       HEAD is ahead of the installed commit — reinstall to pick up the difference")
        elif p.get("head_ahead_of_install") is None:
            lines.append("       could not tell whether HEAD is ahead of the installed commit")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    ap.add_argument("--plugin", help="compare only this plugin by name")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                    help="path to installed_plugins.json")
    ap.add_argument("--repo", type=Path, default=REPO, help="repository root")
    args = ap.parse_args(argv)

    try:
        report = compare(args.repo, args.registry, args.plugin)
    except CannotDetermine as e:
        # Exit 2, loudly. Never 0.
        if args.json:
            print(json.dumps({"status": "cannot-determine", "reason": str(e)}, indent=2))
        print(f"cannot determine installed-vs-shipped drift: {e}", file=sys.stderr)
        return CANNOT_DETERMINE

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n".join(render(report)))

    if report["undetermined"]:
        print(f"\ncannot determine drift for: {', '.join(report['undetermined'])}",
              file=sys.stderr)
        return CANNOT_DETERMINE
    if report["drifted"]:
        print(f"\ndrift found in: {', '.join(report['drifted'])}", file=sys.stderr)
        return DRIFT
    print("\nin sync: every shipped component is installed")
    return IN_SYNC


if __name__ == "__main__":
    sys.exit(main())
