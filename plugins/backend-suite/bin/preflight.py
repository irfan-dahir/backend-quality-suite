#!/usr/bin/env python3
"""Which skills can actually run against this project, and what blocks the rest.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py"             # human summary
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py" --json      # machine-readable
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py" --skill review-docs
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py" --strict    # exit 1 if anything is BLOCKED
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py" --selftest  # prove detection still fires

`--skill` takes any component name, agents included. With no readable
`.backend-suite/docs.manifest.json` it refuses rather than reporting an empty
clean run.

## What this is for

Two distinct jobs, and it is worth being precise about which is which.

**For someone adopting the suite:** answers "will these skills work on my
project?" before they find out one at a time — every skill and agent in every
installed plugin, which is why the totals live in `docs/CATALOG.md` (generated)
rather than being restated here. A skill needing a `motion` role the
project has not mapped is knowable in advance, and much cheaper to learn here.

**As evidence:** turns "unverified" into a specific claim. Most skills in this
plugin are prompt-only — no script to execute — so "run it end-to-end" needs a real
task and a human reviewing real output. That cannot be faked into existence by a
harness. What a harness *can* establish is that every precondition a skill declares
is satisfiable here.

## What a PASS does and does not mean

    PASS      every doc role, directory role and script the skill names resolves.
              It is capable of running here.
    BLOCKED   something it needs is missing. It would stop partway, or stop at the
              first step.

**A PASS is not a claim the skill works.** It says the skill will not fall over on a
missing precondition. Whether its output is *correct* is a judgement about generated
content, which no script settles — that is what `maturity: proven` means in the
catalogue, and preflight deliberately does not upgrade it.

Stated this plainly because the temptation to launder a green harness into "proven"
is exactly the failure this suite is built around: a check that reports nothing must
never be indistinguishable from a clean result.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402

PLUGINS = PLUGIN_ROOT.parent

DOC_REF = re.compile(r"\{\{doc:([a-z0-9-]+)\}\}")
DIR_REF = re.compile(r"\{\{dir:([a-zA-Z0-9-]+)\}\}")
PLUGIN_SCRIPT = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+)")
TRAILING = ".,;:)`\"'"


def manifest(repo: Path) -> dict:
    path = repo / ".backend-suite/docs.manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError:
        return {}


def components() -> list[tuple[str, str, Path]]:
    """(plugin, kind, path) for every skill and agent in every installed plugin."""
    out = []
    for plugin in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        for kind, sub in (("skill", "commands"), ("agent", "agents")):
            for f in sorted((plugin / sub).glob("*.md")):
                out.append((plugin.name, kind, f))
    return out


def inspect(path: Path, plugin: Path, repo: Path, man: dict) -> dict:
    text = path.read_text()
    roles = man.get("roles", {}) or {}
    external = {k: v for k, v in (man.get("externalRoles", {}) or {}).items()
                if not k.startswith("_")}
    dirs = man.get("directories", {}) or {}

    blockers: list[str] = []
    notes: list[str] = []

    needed_roles = sorted(set(DOC_REF.findall(text)))
    for role in needed_roles:
        if role in external:
            notes.append(f"role {role!r} is external — readable, never writable")
            continue
        if role not in roles:
            blockers.append(f"doc role {role!r} is not mapped in docs.manifest.json")
        elif not (repo / roles[role]).exists():
            blockers.append(f"doc role {role!r} maps to {roles[role]}, which is missing")

    needed_dirs = sorted(set(DIR_REF.findall(text)))
    for name in needed_dirs:
        if name not in dirs:
            blockers.append(f"directory role {name!r} is not mapped")

    scripts = sorted({m.group(1).rstrip(TRAILING) for m in PLUGIN_SCRIPT.finditer(text)})
    for rel in scripts:
        if not (plugin / rel).exists():
            blockers.append(f"script ${{CLAUDE_PLUGIN_ROOT}}/{rel} does not exist")

    meta_match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = {}
    if meta_match:
        for line in meta_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip("\"'")

    return {
        "name": meta.get("name", path.stem),
        "invocation": meta.get("invocation", "?"),
        "maturity": meta.get("maturity", "?"),
        "roles": needed_roles,
        "dirs": needed_dirs,
        "scripts": scripts,
        "blockers": blockers,
        "notes": notes,
        "status": "PASS" if not blockers else "BLOCKED",
    }


def selftest() -> int:
    """Prove preflight can BLOCK, on a synthetic project. Runs in CI.

    Without this the harness is worthless as evidence: a checker that only ever
    reports PASS is indistinguishable from one whose detection is broken, which is
    the exact failure this suite is built around. So a deliberately incomplete
    project is constructed and the expected blockers asserted.

    Synthetic rather than a real repo on purpose — unproven tooling does not get
    pointed at a real project.
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    (tmp / ".backend-suite").mkdir()
    # `api` is mapped but the file is absent; `decisions` is mapped and present;
    # every other role is unmapped. `derived` is deliberately the only directory.
    # Both roles must be ones the shipped components actually reference via
    # `{{doc:…}}` — the assertion below is only meaningful if some component
    # needs the missing one.
    (tmp / ".backend-suite/docs.manifest.json").write_text(json.dumps({
        "roles": {"api": "docs/API.md", "decisions": "docs/DECISIONS.md"},
        "directories": {"derived": "docs/derived"},
    }))
    (tmp / "docs").mkdir()
    (tmp / "docs/DECISIONS.md").write_text("# Decisions\n")

    man = manifest(tmp)
    results = []
    for plugin_name, kind, path in components():
        r = inspect(path, PLUGINS / plugin_name, tmp, man)
        r["plugin"], r["kind"] = plugin_name, kind
        results.append(r)

    problems = []
    blocked = [r for r in results if r["status"] == "BLOCKED"]
    # The role vocabulary's size, read from the source of truth rather than
    # hardcoded: a literal here went stale the moment the vocabulary was
    # re-domained, and a stale number in a selftest's own failure text is a
    # small lie in the one place that exists to tell the truth.
    _vocab = json.loads((PLUGIN_ROOT / "templates/docs/roles.json").read_text())
    _nroles = len(_vocab["roles"])
    if not blocked:
        problems.append(
            f"nothing was BLOCKED on a project mapping 2 of {_nroles} roles — detection is "
            "not working, and every PASS elsewhere is therefore meaningless")

    # The mapped-but-missing file must be caught, not just the unmapped roles.
    if not any("maps to docs/API.md, which is missing" in b
               for r in results for b in r["blockers"]):
        problems.append("a role mapped to a nonexistent file was not reported")

    # A role that is present must never be reported.
    if any("'decisions'" in b for r in results for b in r["blockers"]):
        problems.append("'decisions' is mapped and present but was reported as a blocker")

    # Scripts live in the plugin, not the project, so they must still all resolve.
    if any("does not exist" in b and "CLAUDE_PLUGIN_ROOT" in b
           for r in results for b in r["blockers"]):
        problems.append("a plugin script was reported missing — scripts are "
                        "plugin-relative and do not depend on the project")

    print(f"preflight selftest: {len(blocked)}/{len(results)} blocked on a synthetic "
          f"project mapping 2 of {_nroles} roles")
    if problems:
        print("\nSELFTEST FAILED:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("preflight detects missing preconditions, so a PASS carries information.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--skill", metavar="NAME", help="one component only")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if anything is BLOCKED")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the checker can BLOCK, on a synthetic project")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    repo = project_root()
    man = manifest(repo)
    if not man:
        print(f"no readable .backend-suite/docs.manifest.json under {repo} — "
              "nothing to check preconditions against", file=sys.stderr)
        return 2

    results = []
    for plugin_name, kind, path in components():
        r = inspect(path, PLUGINS / plugin_name, repo, man)
        if args.skill and r["name"] != args.skill:
            continue
        r["plugin"], r["kind"] = plugin_name, kind
        results.append(r)

    if args.skill and not results:
        print(f"no component named {args.skill!r}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"project": str(repo), "results": results}, indent=2))
        return 1 if (args.strict and any(r["blockers"] for r in results)) else 0

    passed = [r for r in results if r["status"] == "PASS"]
    blocked = [r for r in results if r["status"] == "BLOCKED"]

    print(f"preflight against {repo}")
    print(f"{len(passed)}/{len(results)} component(s) have every precondition satisfied.\n")

    for r in results:
        mark = "✅" if r["status"] == "PASS" else "🔴"
        label = f"/{r['name']}" if r["kind"] == "skill" else r["name"]
        print(f"{mark} {label:28} {r['maturity']:<12} "
              f"{len(r['roles'])} role(s), {len(r['scripts'])} script(s)")
        for b in r["blockers"]:
            print(f"      ✗ {b}")
        for n in r["notes"]:
            print(f"      · {n}")

    if blocked:
        print(f"\n{len(blocked)} blocked. Map the missing roles in "
              f"docs.manifest.json, or accept that those skills cannot run here.")

    print("\nA PASS means the skill will not stop on a missing precondition. It is "
          "NOT a claim\nthat its output is correct — that is what maturity: proven "
          "means, and preflight\ndoes not upgrade it.")
    return 1 if (args.strict and blocked) else 0


if __name__ == "__main__":
    sys.exit(main())
