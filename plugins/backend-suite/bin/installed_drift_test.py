#!/usr/bin/env python3
"""Tests for installed_drift.py's exit-code contract.

The whole value of this script is that exit 2 ("I could not look") never gets
reported as exit 0 ("I looked and it was clean"). Every case below is built on
a synthetic repo + registry in a temp directory, so none of it depends on what
happens to be installed on the machine running the test.

Each drift case is paired with an in-sync control built the same way, because a
detector that only ever fires is as useless as one that never does.

    python3 plugins/backend-suite/bin/installed_drift_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import installed_drift as D  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    if condition:
        print(f"  ok   {what}")
    else:
        FAILURES.append(what)
        print(f"  FAIL {what}")


def make_plugin(root: Path, name: str, commands: list[str],
                agents: list[str] | None = None,
                skills: list[str] | None = None) -> Path:
    """Build a plugin tree with a real manifest and the named components."""
    p = root / name
    (p / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (p / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}))
    (p / "commands").mkdir(exist_ok=True)
    for c in commands:
        (p / "commands" / f"{c}.md").write_text("---\ndescription: x\n---\nbody\n")
    for a in (agents or []):
        (p / "agents").mkdir(exist_ok=True)
        (p / "agents" / f"{a}.md").write_text("---\ndescription: x\n---\nbody\n")
    for s in (skills or []):
        (p / "skills" / s).mkdir(parents=True, exist_ok=True)
        (p / "skills" / s / "SKILL.md").write_text("---\ndescription: x\n---\nbody\n")
    return p


def write_registry(path: Path, entries: dict[str, str | None]) -> None:
    """entries maps plugin name -> installPath (None = recorded but path absent)."""
    plugins = {}
    for name, install_path in entries.items():
        plugins[f"{name}@test-marketplace"] = [{
            "scope": "user",
            "installPath": install_path if install_path is not None else "/nonexistent/path",
            "version": "abc123",
            "gitCommitSha": "abc123def456",
            "installedAt": "2026-01-01T00:00:00.000Z",
            "lastUpdated": "2026-01-02T00:00:00.000Z",
        }]
    path.write_text(json.dumps({"version": 2, "plugins": plugins}))


def run(tmp: Path, shipped: list[str], installed: list[str] | None,
        **kw) -> int:
    """Build a repo+cache pair and return installed_drift's exit code."""
    repo = tmp / "repo"
    (repo / "plugins").mkdir(parents=True, exist_ok=True)
    make_plugin(repo / "plugins", "demo", shipped, **kw)

    registry = tmp / "installed_plugins.json"
    if installed is None:
        write_registry(registry, {})           # nothing installed at all
    else:
        cache = tmp / "cache" / "demo"
        cache.mkdir(parents=True, exist_ok=True)
        make_plugin(tmp / "cache", "demo", installed, **kw)
        write_registry(registry, {"demo": str(cache)})
    return D.main(["--repo", str(repo), "--registry", str(registry)])


def main() -> int:
    # --- the control: identical sets are exit 0 ------------------------------
    with tempfile.TemporaryDirectory() as t:
        expect(run(Path(t), ["a", "b", "c"], ["a", "b", "c"]) == D.IN_SYNC,
               "identical shipped and installed command sets exit 0")

    # --- the measured bug: shipped commands absent from the install ----------
    with tempfile.TemporaryDirectory() as t:
        expect(run(Path(t), ["a", "b", "c"], ["a"]) == D.DRIFT,
               "commands shipped but not installed exit 1")

    # --- the reverse: the install carries something the repo dropped ---------
    with tempfile.TemporaryDirectory() as t:
        expect(run(Path(t), ["a"], ["a", "removed"]) == D.DRIFT,
               "a command only in the install exits 1")

    # --- agents and skills drift too, not just commands ----------------------
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a"], agents=["auditor"], skills=["s1", "s2"])
        cache = tmp / "cache" / "demo"
        make_plugin(tmp / "cache", "demo", ["a"], agents=["auditor"], skills=["s1"])
        registry = tmp / "installed_plugins.json"
        write_registry(registry, {"demo": str(cache)})
        code = D.main(["--repo", str(repo), "--registry", str(registry)])
        expect(code == D.DRIFT, "a skill directory missing from the install exits 1")

        report = D.compare(repo, registry)
        expect(report["plugins"][0]["kinds"]["skills"]["missing"] == ["s2"],
               "the missing skill is named in the report, not just counted")
        expect(report["plugins"][0]["kinds"]["agents"]["missing"] == [],
               "an agent present on both sides is not reported as missing")

    # --- exit 2: the paths that must never render as 0 -----------------------
    with tempfile.TemporaryDirectory() as t:
        expect(run(Path(t), ["a", "b"], None) == D.CANNOT_DETERMINE,
               "a plugin with no install record exits 2, not 0")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a"])
        registry = tmp / "installed_plugins.json"
        write_registry(registry, {"demo": None})  # recorded, but path is gone
        expect(D.main(["--repo", str(repo), "--registry", str(registry)]) == D.CANNOT_DETERMINE,
               "a recorded install path that does not exist exits 2, not 0")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a"])
        missing = tmp / "no-such-registry.json"
        expect(D.main(["--repo", str(repo), "--registry", str(missing)]) == D.CANNOT_DETERMINE,
               "a missing install registry exits 2, not 0")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a"])
        bad = tmp / "installed_plugins.json"
        bad.write_text("{not json at all")
        expect(D.main(["--repo", str(repo), "--registry", str(bad)]) == D.CANNOT_DETERMINE,
               "an unparseable install registry exits 2, not 0")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "repo" / "plugins").mkdir(parents=True)  # no plugins inside
        registry = tmp / "installed_plugins.json"
        write_registry(registry, {})
        expect(D.main(["--repo", str(tmp / "repo"), "--registry", str(registry)]) == D.CANNOT_DETERMINE,
               "a repo that ships no plugins exits 2, not 0")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a"])
        registry = tmp / "installed_plugins.json"
        write_registry(registry, {"demo": str(tmp / "cache" / "demo")})
        expect(D.main(["--repo", str(repo), "--registry", str(registry),
                       "--plugin", "nope"]) == D.CANNOT_DETERMINE,
               "--plugin naming nothing exits 2, not 0")

    # A directory under plugins/ without a manifest is not a plugin, so its
    # absence from the cache is not drift.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a"])
        (repo / "plugins" / "stray" / "commands").mkdir(parents=True)
        cache = tmp / "cache" / "demo"
        make_plugin(tmp / "cache", "demo", ["a"])
        registry = tmp / "installed_plugins.json"
        write_registry(registry, {"demo": str(cache)})
        expect(D.main(["--repo", str(repo), "--registry", str(registry)]) == D.IN_SYNC,
               "a manifest-less directory under plugins/ is not counted as a plugin")

    # --- the report names what is missing, in machine-readable form ----------
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = tmp / "repo"
        (repo / "plugins").mkdir(parents=True)
        make_plugin(repo / "plugins", "demo", ["a", "b", "c"])
        cache = tmp / "cache" / "demo"
        make_plugin(tmp / "cache", "demo", ["a"])
        registry = tmp / "installed_plugins.json"
        write_registry(registry, {"demo": str(cache)})
        report = D.compare(repo, registry)
        cmds = report["plugins"][0]["kinds"]["commands"]
        expect(cmds["missing"] == ["b", "c"], "missing commands are named and sorted")
        expect(cmds["shipped"] == 3 and cmds["installed"] == 1,
               "both counts are reported so 3-vs-1 is distinguishable from 0-vs-0")
        expect(report["drifted"] == ["demo"], "the drifted plugin is named in the report")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all installed_drift cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
