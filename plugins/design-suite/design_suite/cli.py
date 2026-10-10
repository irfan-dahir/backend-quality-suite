"""`design-suite` — one command that reaches every bin/ script, from any harness.

    design-suite list                      every subcommand and the script it runs
    design-suite where                     the resolved suite root, and how it was found
    design-suite mcp                       start the MCP server (stdio) from the located root
    design-suite audit tokens [args...]    -> bin/audit_tokens.py [args...]
    design-suite doctor [args...]          -> bin/doctor.py [args...]
    python3 -m design_suite ...            same thing, without installing

## Thin dispatch, nothing else

Every subcommand is one row mapping a name to one existing `bin/` script. The
arguments after it are passed through untouched, the script runs with the same
interpreter, cwd and environment, and its exit code is returned unchanged — 0/1/2
and the 3/4/5 some scripts use mean exactly what the script says they mean. No
logic lives here; a behaviour change belongs in the script.

`design-suite <sub> --help` is answered here, from the script's own docstring,
without running it. Many scripts resolve the project root at import time, so
their own `--help` refuses outside a profiled project; help that only works
inside a project is help that does not work.

## Locating the suite — one order, never a guess

Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}`; no other harness does. The
root is resolved in exactly this order, and `design-suite where` prints which
step answered:

  1. **package** — the plugin tree this `design_suite` package sits in: the copy
     an installed `design-suite` on PATH runs (pip/pipx/uv), or a checkout run
     with `python3 -m design_suite`.
  2. **DESIGN_SUITE_HOME** — an env var naming a plugin root.
  3. **CLAUDE_PLUGIN_ROOT** — set by Claude Code.
  4. otherwise **refuse, exit 2**, naming every step tried.

A step counts only if its directory really holds the suite (`bin/_bootstrap.py`).
An env var that is *set* but points somewhere invalid is a refusal, not a
fall-through: someone meant it, and silently using a different root instead would
be the guess this order exists to rule out.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

MARKER = Path("bin") / "_bootstrap.py"
EXIT_REFUSED = 2

# name -> (script in bin/, one-line purpose). Audits are not listed: `audit <name>`
# maps to bin/audit_<name>.py for every such script that exists, so a new audit is
# reachable the day it lands. cli_test.py asserts every row here reaches a file.
COMMANDS: dict[str, tuple[str, str]] = {
    "survey": ("survey.py", "survey an unknown project; --check diffs disk against config"),
    "init": ("init.py", "scaffold .design-suite/ from templates"),
    "map": ("map_project.py", "propose the mappings a survey cannot (provenance: inferred)"),
    "propose-config": ("propose_config.py", "propose values for scaffolded TODO config sections from code evidence (preview by default)"),
    "resolve": ("resolve.py", "resolve a doc role or profile key to a path"),
    "doctor": ("doctor.py", "check the profile and environment; report what is untrusted"),
    "ratify": ("ratify.py", "record a profile field as a human decision"),
    "repo-health": ("repo_health.py", "run every audit fresh; one JSON posture document"),
    "design-debt": ("design_debt.py", "roll audit findings into per-category grades"),
    "harness": ("harness.py", "preview/apply/check generated per-harness files (AGENTS.md, MCP configs, skills)"),
    "chain": ("chain.py", "run or resume a multi-step playbook"),
    "repair-tokens": ("repair_tokens.py", "emit a reviewable token-repair diff (never applies it)"),
    "scaffold-doc": ("scaffold_doc.py", "scaffold one project document from its template"),
    "decline-doc": ("decline_doc.py", "record a declined document role"),
    "query-decisions": ("query_decisions.py", "query the project's decision log"),
    "quick-ref": ("quick_ref.py", "print the project quick reference"),
    "preflight": ("preflight.py", "pre-work checks"),
    "verify": ("verify.py", "verify a commit's claims"),
    "upgrade": ("suite_upgrade.py", "upgrade a project's .design-suite/ to this suite version"),
    "installed-drift": ("installed_drift.py", "compare installed suite against the source"),
    "extract-copy": ("extract_copy.py", "extract user-facing copy strings"),
    "golden-local-ab": ("golden_local_ab.py", "byte-compare golden renders before/after"),
    "precommit": ("run_precommit_audits.py", "run the pre-commit audit set"),
    "hooks": ("harness_hooks.py", "wire hooks per harness (--status | --harness X [--apply] | --git)"),
    "install-precommit-hook": ("install_precommit_hook.py", "install the pre-commit hook"),
    "install-prepush-hook": ("install_prepush_hook.py", "install the pre-push hook"),
    "cleanup-worktrees": ("cleanup_worktrees.py", "remove stale agent worktrees (dry-run default)"),
    "skills-catalog": ("skills_catalog.py", "list skills with tier and maturity"),
    # Suite-maintenance: meaningful in a checkout of this repo, not a consumer project.
    "attest": ("attest.py", "suite repo: run every gate, print the verdict and environment"),
    "gates": ("gates.py", "suite repo: run CI gates locally"),
    "test": ("run_tests.py", "suite repo: run every bin/*_test.py"),
    "catalog": ("catalog.py", "suite repo: regenerate docs/CATALOG.md"),
}


class Refusal(Exception):
    pass


def _valid(root: Path) -> bool:
    return (root / MARKER).is_file()


def locate(env: "dict[str, str] | None" = None, package_dir: "Path | None" = None
           ) -> "tuple[Path, str]":
    """Return (root, how). Raise Refusal naming every step tried."""
    env = os.environ if env is None else env
    pkg = (package_dir or Path(__file__).resolve().parent).parent
    tried = []
    if _valid(pkg):
        return pkg, "package"
    tried.append(f"package: {pkg} has no {MARKER}")
    for var in ("DESIGN_SUITE_HOME", "CLAUDE_PLUGIN_ROOT"):
        val = env.get(var)
        if not val:
            tried.append(f"{var}: not set")
            continue
        root = Path(val).expanduser()
        if _valid(root):
            return root.resolve(), var
        raise Refusal(f"{var} is set to {val!r}, but that is not a design-suite root "
                      f"(no {MARKER}). Fix or unset it; not falling through to a guess.")
    raise Refusal("could not locate the design-suite root. Tried, in order:\n  "
                  + "\n  ".join(tried)
                  + "\nInstall it (pipx install / uv tool install) or set DESIGN_SUITE_HOME.")


def audits(root: Path) -> "dict[str, str]":
    return {p.stem[len("audit_"):].replace("_", "-"): p.name
            for p in sorted((root / "bin").glob("audit_*.py"))
            if not p.stem.endswith("_test")}


def table(root: Path) -> "dict[str, tuple[str, str]]":
    """Every reachable subcommand: name -> (script, purpose)."""
    rows = dict(COMMANDS)
    for name, script in audits(root).items():
        rows[f"audit {name}"] = (script, "audit (read-only)")
    return rows


def docstring(script: Path) -> str:
    try:
        return ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or ""
    except (SyntaxError, OSError, UnicodeDecodeError):
        return ""


USAGE = ("usage: design-suite <subcommand> [args...]\n"
         "       design-suite list | where | mcp | audit <name> [args...]\n"
         "Run `design-suite list` for every subcommand; `<subcommand> --help` for one.")


def main(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    try:
        root, how = locate()
    except Refusal as e:
        print(f"design-suite: {e}", file=sys.stderr)
        return EXIT_REFUSED

    head, rest = argv[0], argv[1:]
    if head == "where":
        print(f"{root}\t(resolved via {how})")
        return 0
    rows = table(root)
    if head == "mcp":
        server = root / "mcp" / "audit_server.py"
        if not server.is_file():
            print(f"design-suite: MCP server not found at {server}.", file=sys.stderr)
            return EXIT_REFUSED
        return subprocess.call([sys.executable, str(server), *rest])
    if head == "list":
        width = max(len(n) for n in rows)
        for name, (script, purpose) in rows.items():
            print(f"{name:<{width}}  bin/{script:<32} {purpose}")
        return 0
    if head == "audit":
        if not rest or rest[0] in ("-h", "--help"):
            print("usage: design-suite audit <name> [args...]\naudits: "
                  + ", ".join(audits(root)))
            return 0 if rest else EXIT_REFUSED
        head, rest = f"audit {rest[0]}", rest[1:]
    if head not in rows:
        print(f"design-suite: unknown subcommand {head!r}. Run `design-suite list`.",
              file=sys.stderr)
        return EXIT_REFUSED
    script = root / "bin" / rows[head][0]
    if not script.is_file():
        print(f"design-suite: {head!r} maps to {script}, which does not exist.",
              file=sys.stderr)
        return EXIT_REFUSED
    if rest[:1] in (["-h"], ["--help"]):
        print(f"usage: design-suite {head} [args...]   (runs bin/{script.name})\n")
        print(docstring(script) or rows[head][1])
        return 0
    return subprocess.call([sys.executable, str(script), *rest])


if __name__ == "__main__":
    raise SystemExit(main())
