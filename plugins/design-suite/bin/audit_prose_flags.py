#!/usr/bin/env python3
"""Every `--flag` a skill's markdown names next to a `bin/*.py` must really exist.

    python3 plugins/design-suite/bin/audit_prose_flags.py
    python3 plugins/design-suite/bin/audit_prose_flags.py --list   # what it harvested

Exit 0 when every documented flag is real, 1 when one is not, 2 when the scan
found nothing to check (an empty scan is not a pass).

## Why

`audit_skill_paths.py` already proves that every script a skill tells Claude to
run exists. That check passes on a line like

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py" --refresh

where the script is present and `--refresh` was never implemented. Claude runs
it, argparse exits 2, and the skill's recipe dies at step three — a documented
invocation that has never once worked. The path gate cannot see it, because the
path is fine.

This is the same class of bug as a hand-written catalogue: prose asserting a
fact about code, with nothing comparing the two.

## What it deliberately cannot catch

A **negated** claim. `map-project.md` saying "`--from-survey` does *not* exist"
would be wrong in the opposite direction, and nothing here would notice: the
flag is named, the flag is real, the sentence is still false. Detecting that
needs to read the sentence rather than the token, which is a judgement call and
so belongs in a review, not a gate. The commoner direction — prose naming a
flag that was renamed or never built — is what this catches, and it is worth
saying out loud which half is covered rather than letting the gate's green
imply both.

## How a flag is attributed to a script

Per line: find `bin/<script>.py`, then take the `--flags` that follow it *in
the same command*. The command ends at the first `)`, `|`, `&&`, `;`, backtick
or `#`, because these recipes are full of shapes like

    grep "$(... bin/resolve.py" --profile source.root)" --include="*.dart"

where `--profile` is the resolver's and `--include` is grep's. Truncating at
the `)` is what keeps the second one from being blamed on the first. Single-dash
flags are ignored entirely: they are almost always another tool's (`find -name`,
`grep -E`), and guessing would produce exactly the confident-wrong finding this
repo treats as worse than no finding.

## A flag passed to a script that parses nothing

A second rule, separate from the --help lookup. If the script a skill hands a
flag to has **no argument handling at all** — no argparse, getopt, optparse,
click/typer, no `sys.argv` — the flag is not rejected, it is silently ignored,
and the script runs its default behaviour. For a script with side effects the
side effects happen. `/audit-assets`, described as read-only, once ran
`export_palette.py --help` as a "harmless probe"; the script had no parser, so
`--help` did nothing and `main()` overwrote the consumer's `palette.json`. The
--help lookup could not see it: a script with no parser declares no flags, so
there was no list to look the flag up in.

This rule is decided **statically, from the AST, without running the script** —
running a script that may ignore `--help` is exactly the harm being detected.
It applies to any plugin-root-relative `.py` or `bin/*.py` the prose names
that resolves to a file, and to every long flag including `--help`.

Three outcomes, never two:

  * **parses** — the script, or a plugin-local module it imports (followed
    transitively), mentions argparse/getopt/optparse/click/typer or `sys.argv`.
    A helper merely *mentioning* argv is counted as the script parsing it; that
    errs toward "fine" only where delegation is genuinely plausible.
  * **parses nothing** — neither the script nor anything it imports from this
    plugin mentions any of those, and every other import is stdlib (which does
    not read argv on a script's behalf). This is a CRITICAL finding.
  * **cannot determine** — the script does not parse as Python, imports a
    module that is neither plugin-local nor stdlib (a third-party package
    could read argv), or uses `__import__`/`importlib` dynamically. Reported
    by name as unverifiable, never as "parses nothing" and never as fine.

**Its limit:** it catches scripts that parse *nothing*. It cannot catch a
script that parses *some* flags and still writes by default regardless of
which ones it was given — `foo.py --dry-run` where `--dry-run` exists but is
not consulted before the write. That needs a check of what the script does
with its parsed arguments, which is a different check and is not this one.

## An audit described as read-only whose script always writes

A third rule, about the audit commands' own descriptions rather than their
flags. If `commands/audit-<name>.md`'s frontmatter `description` claims the
audit is read-only ("Read-only", "never edits", "writes nothing", "never
writes") and does not say what it saves, while `bin/audit_<name>.py`'s `main()`
contains a file write that no `if`/loop/`except` guards, the description is
false on every run. Seven audit descriptions said exactly that before #156,
and an audit written afterwards by copying one of them repeated the line.

Measured before shipping (AST, `main()` only, writes = `write_text`,
`write_bytes`, `.write(`, `json.dump`, excluding stdout/stderr): on the tree
just before #156 it flags 6 descriptions, all true; on the tree after it flags
0 of the 7 audits with an unconditional write, because each now says "saves its
report to <path>". An earlier, broader candidate (any script a doc mentions,
any write) measured ~90% false positives — the scoping to the audit's own
script and to *unconditional* writes is what makes this one precise. Its limit:
a write inside a helper `main()` calls, or one that is conditional only in
effect, is not seen; a conditional write (`--out`, `--findings`,
`--update-baseline`) is deliberately not flagged, since "writes only under a
flag" is honest phrasing the rule cannot verify from the sentence.

Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import re
import subprocess
import sysconfig
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
PLUGINS = BIN.parents[1]
# This audit checks THIS plugin's own prose, not a consumer project's, so its
# envelope belongs beside this repo's root rather than at `project_root()` —
# which, for a suite-maintenance audit run from anywhere, would be someone
# else's repo.
SUITE_REPO = BIN.parents[2]

sys.path.insert(0, str(BIN.parents[0]))
from design_suite.engine import findings as F  # noqa: E402

# The fixture builder is reused rather than re-implemented: the probe project
# this gate needs and the project the eval cases run against must be the same
# shape, or a flag verified here is verified against a project no case ever sees.
_FIXTURE_BUILDER = BIN.parent / "evals" / "_fixtures" / "build_fixture.py"
_spec = importlib.util.spec_from_file_location("_build_fixture", _FIXTURE_BUILDER)
build_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_fixture)

# Where a skill's prose lives. Commands and agents are the two surfaces that
# instruct Claude to run something; plugin docs describe rather than instruct.
SCAN_GLOBS = ("*/commands/**/*.md", "*/agents/**/*.md")

SCRIPT = re.compile(r"bin/([A-Za-z0-9_]+)\.py")
# Any plugin-relative script, for the parses-nothing rule. Not limited to bin/:
# the defect that motivated it lived in design_suite/engine/assets/.
PLUGIN_SCRIPT = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/((?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py)")
LONG_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
# The first character that ends the command the script was invoked in.
COMMAND_END = re.compile(r"[)|;`#]|&&")

# Flags argparse gives every script for free, and flags that are a shell's
# end-of-options marker rather than a script's. Named so a reader can tell an
# exemption from an oversight.
UNIVERSAL = {"--help"}

# (script, flag) pairs that are documented on purpose despite not being in
# --help, each with the reason. Empty is the correct state; an entry here is a
# debt, not a convention.
EXEMPT: dict[tuple[str, str], str] = {}


def _help_text(script_path: Path, probe_root: Path) -> str | None:
    """`--help` for one script, or None if it will not produce one.

    Run against a fully scaffolded fixture project rather than a bare
    directory. Two things force that, and both were found by running this gate:

      * several scripts resolve `project_root()` at *import* time, so with no
        `.design-suite/` at all they exit 2 before argparse prints anything;
      * `audit_promotion_candidates.py` goes further and refuses at import
        unless the profile sets `audits.archRulesFile` — correctly, since an
        audit with no rules passes vacuously. Probed against an empty marker
        directory it produced no help text, and this gate's first run reported
        its real `--update-baseline` flag as nonexistent.

    A confident wrong finding is worse than none, which is why the probe root
    is the `app` fixture: the same scaffold a real adopter gets.
    """
    path = script_path
    if not path.is_file():
        return None
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(probe_root)
    try:
        proc = subprocess.run([sys.executable, str(path), "--help"], env=env,
                              cwd=str(probe_root), capture_output=True, text=True,
                              timeout=60)
    except subprocess.TimeoutExpired:
        return None
    return (proc.stdout or "") + (proc.stderr or "")


# What counts as argument handling. Any of these named in the script (or a
# plugin-local module it imports) means "parses".
PARSER_MODULES = {"argparse", "getopt", "optparse", "click", "typer", "fire", "docopt"}
_STDLIB_DIR = Path(sysconfig.get_paths()["stdlib"]).resolve()


def _is_stdlib(top: str) -> bool:
    if top in sys.builtin_module_names:
        return True
    try:
        spec = importlib.util.find_spec(top)
    except (ImportError, ValueError):
        return False
    if spec is None:
        return False
    if spec.origin in (None, "built-in", "frozen"):
        return spec.origin is not None
    origin = Path(spec.origin).resolve()
    return _STDLIB_DIR in origin.parents and "site-packages" not in origin.parts


def _local_module(name: str, script: Path, plugin_root: Path) -> Path | None:
    """The plugin-local file `name` refers to, or None if it is not local."""
    rel = Path(*name.split("."))
    for base in (script.parent, plugin_root, plugin_root / "bin"):
        for cand in (base / rel.with_suffix(".py"), base / rel / "__init__.py"):
            if cand.is_file():
                return cand
    return None


def argv_handling(script: Path, plugin_root: Path) -> tuple[str, str]:
    """('parses' | 'none' | 'unknown', reason). Static: the script is never run."""
    seen: set[Path] = set()
    todo = [script]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            return "unknown", f"{path.name} does not parse as Python ({e.msg})"
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    # Relative import: resolve against the importing file.
                    base = path.parent
                    for _ in range(node.level - 1):
                        base = base.parent
                    mod = node.module or ""
                    targets = ([mod] if mod else []) + [f"{mod}.{a.name}".strip(".")
                                                        for a in node.names]
                    for t in targets:
                        rel = Path(*t.split(".")) if t else Path()
                        for cand in (base / rel.with_suffix(".py"), base / rel / "__init__.py"):
                            if cand.is_file():
                                todo.append(cand)
                    continue
                names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
                if node.module == "sys" and any(a.name == "argv" for a in node.names):
                    return "parses", f"{path.name} imports sys.argv"
            elif isinstance(node, ast.Attribute) and node.attr == "argv":
                return "parses", f"{path.name} reads .argv"
            elif isinstance(node, ast.Name) and node.id in ("__import__",):
                return "unknown", f"{path.name} imports dynamically via __import__"
            for n in names:
                top = n.split(".")[0]
                if top in PARSER_MODULES:
                    return "parses", f"{path.name} imports {top}"
                if top == "importlib" and n not in ("importlib", "importlib.util"):
                    continue
                local = _local_module(n, path, plugin_root)
                if local is not None:
                    todo.append(local)
                    continue
                if top == "importlib":
                    # import_module/spec loading can pull in anything.
                    return "unknown", f"{path.name} loads modules dynamically via importlib"
                if _is_stdlib(top):
                    continue
                # A from-import of a name inside a resolved local package is fine.
                if "." in n and _local_module(n.rsplit(".", 1)[0], path, plugin_root):
                    continue
                return "unknown", (f"{path.name} imports {top}, which is neither "
                                   f"plugin-local nor stdlib and could read argv")
    return "none", "no argparse/getopt/optparse/click/sys.argv in it or its local imports"


def harvest(root: Path) -> list[tuple[Path, int, Path, str]]:
    """(file, line number, script path, flag) for every documented invocation.

    The script is resolved against the *markdown's own plugin*, not against
    this file's directory. `house-style` ships its own parity-tested
    `bin/resolve_role.py`, and blaming that name on `design-suite/bin/` made
    this gate report two unreadable-help entries for a script that is simply
    somewhere else.
    """
    found: list[tuple[Path, int, Path, str]] = []
    for pattern in SCAN_GLOBS:
        for md in sorted(root.glob(pattern)):
            # <root>/<plugin>/commands/... — the plugin owning this prose.
            plugin_root = root / md.relative_to(root).parts[0]
            for lineno, line in enumerate(md.read_text(encoding="utf-8",
                                                       errors="replace").splitlines(), 1):
                hits: dict[int, Path] = {}
                for match in SCRIPT.finditer(line):
                    hits[match.end()] = plugin_root / "bin" / f"{match.group(1)}.py"
                for match in PLUGIN_SCRIPT.finditer(line):
                    # Only scripts that resolve to a real file: a path that does
                    # not exist is audit_skill_paths.py's finding, not this one.
                    cand = plugin_root / match.group(1)
                    if match.end() not in hits and cand.is_file():
                        hits[match.end()] = cand
                for end_at, script in sorted(hits.items()):
                    tail = line[end_at:]
                    end = COMMAND_END.search(tail)
                    if end:
                        tail = tail[:end.start()]
                    for flag in LONG_FLAG.findall(tail):
                        found.append((md, lineno, script, flag))
    return found


READ_ONLY_CLAIM = re.compile(r"read-only|never edits|writes nothing|never writes", re.I)
STATES_WRITE = re.compile(r"\bsaves\b|\bwrites (?:its|only|a|the)\b", re.I)
_WRITE_ATTRS = {"write_text", "write_bytes", "write", "dump"}
_GUARDS = (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)


def unconditional_writes(script: Path) -> list[tuple[int, str]]:
    """File writes in `main()` that no if/loop/except guards."""
    try:
        tree = ast.parse(script.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return []
    hits: list[tuple[int, str]] = []

    def walk(node: ast.AST, guarded: bool) -> None:
        for child in ast.iter_child_nodes(node):
            g = guarded or isinstance(child, _GUARDS)
            if (not guarded and isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr in _WRITE_ATTRS):
                target = ast.unparse(child.func.value)
                if (target not in ("sys.stdout", "sys.stderr")
                        and (child.func.attr != "dump" or target == "json")):
                    hits.append((child.lineno, ast.unparse(child)[:70]))
            walk(child, g)

    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef) and fn.name == "main":
            walk(fn, False)
    return hits


def false_read_only_claims(root: Path) -> list[tuple[Path, Path, int, str]]:
    out = []
    for md in sorted(root.glob("*/commands/audit-*.md")):
        m = re.search(r"^description:(.*)$", md.read_text(), re.M)
        desc = m.group(1) if m else ""
        if not READ_ONLY_CLAIM.search(desc) or STATES_WRITE.search(desc):
            continue
        script = md.parent.parent / "bin" / (md.stem.replace("-", "_") + ".py")
        if script.is_file():
            for lineno, call in unconditional_writes(script):
                out.append((md, script, lineno, call))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(PLUGINS), help="directory of plugins to scan")
    ap.add_argument("--list", action="store_true",
                    help="print every (script, flag) pair harvested, check nothing")
    ap.add_argument("--findings", nargs="?", const=True, default=None,
                    help="also write the common findings envelope for /design-debt "
                         "(default .design-suite/findings/prose-flags.json)")
    args = ap.parse_args()

    pairs = harvest(Path(args.root))
    if not pairs:
        # An empty harvest looks identical to a clean one from the outside, and
        # the regex above is exactly the kind of thing that silently stops
        # matching. So nothing-found is a refusal, not a pass.
        print(f"no `bin/*.py --flag` invocation found under {args.root} at all. "
              f"Either the docs stopped naming scripts or this scan is broken — "
              f"nothing checked is not the same as everything correct.",
              file=sys.stderr)
        return 2

    if args.list:
        for md, lineno, script, flag in pairs:
            print(f"{md.relative_to(Path(args.root))}:{lineno}\t{script}.py\t{flag}")
        return 0

    findings: list[str] = []
    unhelpable: list[str] = []
    # Structured twins of the two lists above, collected alongside rather than
    # replacing them: the printed lines are this audit's long-standing output
    # and changing their shape is a reviewed decision, not a side effect of
    # adding an envelope (findings.py's ADDITIVE rule).
    records: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        probe = build_fixture.build("service", Path(tmp) / "probe", force=True)
        helps: dict[Path, str | None] = {}
        handling: dict[Path, tuple[str, str]] = {}
        for md, lineno, script, flag in pairs:
            name = script.name
            where = str(md.relative_to(Path(args.root)))
            if script.is_file():
                if script not in handling:
                    plugin_root = Path(args.root) / md.relative_to(Path(args.root)).parts[0]
                    handling[script] = argv_handling(script, plugin_root)
                kind, why = handling[script]
                if kind == "none":
                    # Before --help is ever run: running a script that ignores
                    # --help is the harm itself.
                    findings.append(f"{where}:{lineno}  {name} {flag}  — {name} parses "
                                    f"no arguments; the flag is ignored and the script "
                                    f"runs its default behaviour, side effects included")
                    records.append(F.make(
                        "prose-flags", "flag-to-argless-script",
                        f"{name} parses no arguments, so {flag} is silently ignored "
                        f"and the script runs its default behaviour — any side "
                        f"effects (writes) happen",
                        severity=F.CRITICAL, file=where, line=lineno, detail=why))
                    continue
                if kind == "unknown":
                    unhelpable.append(f"{where}:{lineno}  cannot determine whether "
                                      f"{name} parses arguments: {why}")
                    records.append(F.make(
                        "prose-flags", "argv-handling-undetermined",
                        f"cannot determine whether {name} parses arguments, so "
                        f"{flag} may be silently ignored",
                        severity=F.SHOULD_FIX, file=where, line=lineno, detail=why))
                    continue
            if script.parent.name != "bin":
                # Outside bin/ only the parses-nothing rule applies; the --help
                # lookup keeps its long-standing bin/ scope.
                continue
            if flag in UNIVERSAL or (name, flag) in EXEMPT:
                continue
            if script not in helps:
                helps[script] = _help_text(script, probe)
            text = helps[script]
            if text is None:
                # Reported, never skipped: a script whose --help cannot be read
                # is a script whose documented flags are unverifiable, and
                # silently passing them is the failure mode.
                unhelpable.append(f"{md.relative_to(Path(args.root))}:{lineno}  "
                                  f"{name} has no readable --help")
                records.append(F.make(
                    "prose-flags", "unreadable-help",
                    f"{name} has no readable --help, so {flag} cannot be verified",
                    severity=F.SHOULD_FIX,
                    file=str(md.relative_to(Path(args.root))), line=lineno,
                    detail="unverifiable is not the same as correct"))
                continue
            # Word-boundary match so `--check` is not satisfied by `--checkpoint`.
            if not re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text):
                findings.append(f"{md.relative_to(Path(args.root))}:{lineno}  "
                                f"{name} {flag}  — not in its --help")
                records.append(F.make(
                    "prose-flags", "nonexistent-flag",
                    f"{name} {flag} is documented here but is not in its --help",
                    severity=F.CRITICAL,
                    file=str(md.relative_to(Path(args.root))), line=lineno,
                    detail="a documented invocation that has never once worked"))

    for md, script, lineno, call in false_read_only_claims(Path(args.root)):
        where = str(md.relative_to(Path(args.root)))
        findings.append(f"{where}  description claims read-only, but "
                        f"{script.name}:{lineno} always writes ({call}) — say what "
                        f"it saves and where, e.g. \"Never changes your code; saves "
                        f"its report to <path> on every run.\"")
        records.append(F.make(
            "prose-flags", "false-read-only-claim",
            f"description claims read-only but {script.name}:{lineno} writes "
            f"unconditionally", severity=F.CRITICAL, file=where,
            detail="state what the audit writes and where"))

    checked = len({(s.name, f) for _, _, s, f in pairs})

    if args.findings:
        F.write(
            F.default_path(SUITE_REPO, "prose-flags") if args.findings is True
            else SUITE_REPO / args.findings,
            "prose-flags", records,
            # The sweep is over distinct (script, flag) pairs — the unit this
            # audit actually checks. Zero findings over zero pairs already
            # exits 2 above; `scanned` keeps that visible to the dashboard too.
            scanned=checked,
            suppressed=({"universal": sorted(UNIVERSAL),
                         "exempt": sorted(f"{n} {fl}" for n, fl in EXEMPT)}
                        if UNIVERSAL or EXEMPT else None),
        )

    for line in sorted(set(unhelpable)):
        print(f"  ?    {line}", file=sys.stderr)
    if findings:
        print(f"{len(set(findings))} documented flag(s) do not exist or are "
              f"passed to a script that parses no arguments:\n", file=sys.stderr)
        for line in sorted(set(findings)):
            print(f"  {line}", file=sys.stderr)
        print("\nEither implement the flag (or a parser) or fix the prose. A recipe whose third "
              "line exits 2 is a recipe nobody has run.", file=sys.stderr)
        return 1
    if unhelpable:
        return 1
    print(f"{checked} distinct (script, flag) pair(s) across {len(pairs)} mention(s) "
          f"all appear in their script's --help.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
