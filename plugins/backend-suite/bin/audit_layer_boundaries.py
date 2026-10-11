#!/usr/bin/env python3
"""Mechanical layer-boundary check.

Rule, source, and banned import roots all come from this project's
`.backend-suite/arch-rules.json` `layerBoundaries` section (see
`backend_suite.engine.arch`) — nothing here names a project's directory layout.
A typical rule reads: nothing under the "from" directory may import the
"mustNotImport" roots. An optional per-rule `"why"` string supplies the
rationale shown in violation messages (e.g. a pointer to that project's own
extraction-plan doc); without one, the message falls back to a generic
"a package cannot import its consumer".

The shape this was written against: a design-system layer slated for
extraction into a standalone package. A package cannot import its consumer,
so every such import is a blocker for that extraction, and more immediately
it is a layering inversion: a "shared" component depending on one feature's
private UI or domain entities.

Two import forms are both caught, since the repo mixes them:
    import 'package:example_app/features/archive/...';      (absolute)
    import '../../app/theme/app_theme.dart';                (relative)

## No exceptions

`lib/app/theme/{app_theme,ds_colors}.dart` used to be allowed here — every
shared component imported them, and that was a not-yet-moved dependency rather
than a true inversion. Phase 2 moved both into `package:ds_flutter`, so those
imports now resolve to a third-party package and are invisible to this check.
The exception is gone and the rule is absolute again.

## The ratchet

Known violations live in a committed baseline. The script fails only on
violations NOT in that baseline, so existing debt doesn't block work while new
debt is rejected outright. As Phase 0b of the extraction plan removes each
violation, run with --update-baseline to shrink the file. When the baseline
reaches [], delete it and this becomes an absolute rule.

--update-baseline refuses when the run also found violations that are NOT yet
baselined, because writing `current` would have recorded them as accepted debt
without anyone deciding that. Pass --accept-new to say you mean it.

Deterministic (an import is either present or not — no heuristic false
positives), so any *new* finding is treated as blocking. Same portable-core
pattern and zero dependencies as audit_adapter_pattern.py / audit_mock_api.py.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_layer_boundaries.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_layer_boundaries.py" --update-baseline
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_layer_boundaries.py" --out /tmp/findings.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import MARKER, project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from backend_suite.adapters import for_project  # noqa: E402
from backend_suite.engine.arch import load      # noqa: E402
from backend_suite.engine import imports as I   # noqa: E402
from backend_suite.engine import ratchet        # noqa: E402
from backend_suite.engine.refusal import Refused  # noqa: E402
from backend_suite.engine import aliases as aliases_mod  # noqa: E402

AUDIT = "audit_layer_boundaries"

_RULES = load(REPO, "layerBoundaries")
_rules_list = _RULES.get("rules") or []
if not _rules_list:
    raise Refused("layerBoundaries.rules is empty — no layer rule to enforce.", AUDIT)
# init.py scaffolds this section with "TODO: ..." values. Before, that reached
# `_RULE["from"]` as KeyError (exit 1, read as findings). A placeholder rule is
# a rule nobody has written: could not check, exit 2.
if I.placeholder(_RULES.get("baseline")):
    raise Refused("layerBoundaries.baseline still holds init.py's TODO placeholders.", AUDIT)


def _root(value: str) -> str:
    """'lib/data/**' -> 'lib/data/' : a glob-shaped root is matched as a prefix."""
    value = value.split("*", 1)[0]
    return value if not value or value.endswith("/") else value + "/"


class Rule:
    """One `layerBoundaries.rules[i]`. Every rule is enforced — this used to
    read `rules[0]` only, so a second rule was configuration that did nothing
    while the run printed clean."""

    def __init__(self, i: int, raw: dict):
        where = f"layerBoundaries.rules[{i}]"
        if not isinstance(raw, dict) or I.placeholder(raw):
            raise Refused(
                f"{where} still holds init.py's TODO placeholders — there is no real "
                f"layer rule yet. Fill in from/fromGlob and mustNotImport, or delete it.",
                AUDIT)
        # `from` (a directory) or `fromGlob` (the scaffold's spelling) — both accepted.
        self.from_dir = raw.get("from")
        self.from_glob = raw.get("fromGlob")
        if not (self.from_dir or self.from_glob):
            raise Refused(f"{where} names neither 'from' nor 'fromGlob' — no layer to check.",
                          AUDIT)
        self.label = self.from_dir or self.from_glob
        self.dir = REPO / (self.from_dir or _root(self.from_glob) or ".")
        must = raw.get("mustNotImport")
        if not must:
            raise Refused(f"{where}.mustNotImport is empty — nothing banned, so the audit "
                          f"would pass vacuously.", AUDIT)
        self.banned = tuple(_root(m) for m in ([must] if isinstance(must, str) else must))
        self.why = raw.get("why", "a package cannot import its consumer")
        self.name = raw.get("label") or f"rules[{i}]"


RULES = [Rule(i, r) for i, r in enumerate(_rules_list)]
BANNED_ROOTS = tuple(dict.fromkeys(b for r in RULES for b in r.banned))
BASELINE_PATH = REPO / (_RULES.get("baseline") or f"{MARKER}/baselines/layer-boundaries.json")

# Source files and import syntax are language facts: from the adapter. Used to
# be `rglob("*.dart")`, which on any other stack scanned nothing.
_ADAPTER, _CTX, _ = for_project(REPO)
IMPORT_RE = I.import_re(_ADAPTER, AUDIT)
I.require_path_imports(_ADAPTER, AUDIT)

# Package-absolute imports (`package:<self>/...`): only stacks with a package
# prefix (dart) have them, and there it is derived from pubspec — a hardcoded
# name silently stops matching the moment the package is renamed.
if hasattr(_ADAPTER, "package_prefix"):
    PACKAGE_PREFIX = _ADAPTER.package_prefix(_CTX)
    if not PACKAGE_PREFIX:
        raise Refused("could not determine this package's import prefix — refusing to "
                      "run a boundary audit that would match nothing and report clean",
                      AUDIT)
    _PKG_SRC = "lib/"
else:
    PACKAGE_PREFIX = None
    _PKG_SRC = ""

# Path aliases (`@/data/api` via tsconfig `paths` / vite `resolve.alias`).
# Unresolved, an alias import reads as a third-party package and every
# violation written through it is missed silently. An alias config that
# exists but cannot be read is a refusal, never "no aliases".
try:
    ALIASES = aliases_mod.load(REPO)
except aliases_mod.AliasConfigError as e:
    raise Refused(f"path-alias config could not be parsed — {e}. Imports through "
                  f"those aliases cannot be resolved, so a clean result would be "
                  f"unfounded.", AUDIT)


def _rel(resolved: Path) -> str | None:
    try:
        return resolved.relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return None  # escaped the repo entirely; not something we police


def _resolve(target: str, source: Path) -> str | None:
    """Resolve an import target to a repo-relative POSIX path, or None if the
    target is external (SDK, third-party package)."""
    if PACKAGE_PREFIX and target.startswith(PACKAGE_PREFIX):
        return _PKG_SRC + target[len(PACKAGE_PREFIX):]
    if target.startswith((".", "/")):
        resolved = (source.parent / target).resolve() if target.startswith(".") \
            else (REPO / target.lstrip("/")).resolve()
        return _rel(resolved)
    aliased = ALIASES.resolve(target)
    if aliased is not None:
        return _rel(aliased)
    if target.startswith(aliases_mod.ALIAS_SHAPED):
        raise Refused(
            f"{source.relative_to(REPO).as_posix()} imports '{target}', which is shaped "
            f"like a path alias, but no tsconfig/jsconfig `paths` or vite/webpack "
            f"`resolve.alias` defines it"
            + (f" (read: {', '.join(ALIASES.sources)})" if ALIASES.sources else "")
            + " — refusing rather than treating it as a third-party package.", AUDIT)
    # Bare specifier: repo-rooted only if it literally names a banned root
    # (e.g. 'src/data/x' with a baseUrl); otherwise a third-party package.
    if target.startswith(BANNED_ROOTS):
        return target
    return None


def _scan_file(path: Path, rule: Rule) -> list[dict]:
    findings: list[dict] = []
    rel = path.relative_to(REPO).as_posix()
    for lineno, raw in I.import_targets(IMPORT_RE, path.read_text(errors="replace")):
        target = _resolve(raw, path)
        if target is None or not target.startswith(rule.banned):
            continue
        findings.append(
            {
                "file": rel,
                "line": lineno,
                "import": target,
                "rule": rule.name,
                "detail": (
                    f"{rel}:{lineno} imports {target} — nothing under {rule.label} "
                    f"may import {', '.join(rule.banned)} ({rule.why})."
                ),
            }
        )
    return findings


def _key(finding: dict) -> str:
    """Baseline identity. Deliberately excludes the line number so that
    unrelated edits shifting a file's lines don't spuriously read as new
    violations — the (file, import) pair is what actually identifies one."""
    return f"{finding['file']} -> {finding['import']}"


def main() -> int:
    parser = argparse.ArgumentParser()
    # Default lives inside .backend-suite/ (the profile marker directory, MARKER),
    # never under a guessed top-level project directory, which is what it was: one
    # project's layout baked into the universal plugin, and it created the
    # directory on projects that had none. Inside .backend-suite/ the report is
    # also covered by the .gitignore bin/init.py scaffolds there; a .gitignore
    # only governs its own directory, so a report anywhere else could not be.
    # Not under findings/: that directory holds the common envelopes
    # /design-debt reads, and a raw report there would be read as a malformed one.
    parser.add_argument("--out", default=f"{MARKER}/layer-boundaries-findings.json",
                        help="where the raw report is written (default: %(default)s)")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(bare flag uses the default path)")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to match reality. Use after removing violations.",
    )
    parser.add_argument(
        "--accept-new", action="store_true",
        help="with --update-baseline, deliberately accept violations that are not "
             "yet baselined. Without it the write is refused rather than absorbing "
             "a regression nobody was shown.",
    )
    args = parser.parse_args()

    findings: list[dict] = []
    scanned: set[Path] = set()
    for rule in RULES:
        if not rule.dir.is_dir():
            raise Refused(f"{rule.name}: no such directory: {rule.dir}", AUDIT)
        files = (I.adapter_files(REPO, _ADAPTER, rule.from_glob)
                 if rule.from_glob and not rule.from_dir
                 else I.adapter_files(rule.dir, _ADAPTER))
        if not files:
            raise Refused(
                f"{rule.name}: 0 {_ADAPTER.NAME} source files under {rule.label} — "
                f"nothing in the layer was scanned, so 'no violations' would be a "
                f"claim about nothing.", AUDIT)
        scanned.update(files)
        for path in files:
            findings.extend(_scan_file(path, rule))
    scanned_files = sorted(scanned)

    (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
    (REPO / args.out).write_text(json.dumps(findings, indent=2) + "\n")
    if args.findings:
        from backend_suite.engine import findings as F
        F.write(
            F.default_path(REPO, "layer_boundaries") if args.findings is True
            else REPO / args.findings,
            "layer_boundaries",
            F.from_records("layer_boundaries", findings, category="layer_boundary"),
            # See adapter_pattern: 0 findings and 0 coverage must not read alike.
            scanned=len(scanned_files),
        )

    current = {_key(f) for f in findings}
    # Loaded before the write, not after: --update-baseline has to know what is
    # NEW in order to refuse to absorb it. See backend_suite.engine.ratchet.
    baseline = set(json.loads(BASELINE_PATH.read_text())) if BASELINE_PATH.exists() else set()

    if args.update_baseline:
        refusal = ratchet.refusal("audit_layer_boundaries", current, baseline,
                                  unit="violation")
        if refusal and not args.accept_new:
            print(refusal, file=sys.stderr)
            return 2
        BASELINE_PATH.write_text(json.dumps(sorted(current), indent=2) + "\n")
        print(f"audit_layer_boundaries: baseline updated — {len(current)} known violation(s)")
        return 0

    new = sorted(current - baseline)
    fixed = sorted(baseline - current)

    if fixed:
        print(f"{len(fixed)} baselined violation(s) no longer present — nice:")
        for k in fixed:
            print(f"  - {k}")
        print("  Run with --update-baseline to lock the improvement in.\n")

    if new:
        print(f"NEW LAYER-BOUNDARY VIOLATIONS ({len(new)}):")
        by_key = {}
        for f in findings:
            by_key.setdefault(_key(f), f)
        for k in new:
            print(f"  {by_key[k]['detail']}")
        print(f"\nFindings written to {args.out}")
        return 1

    print(
        f"audit_layer_boundaries: no new violations "
        f"({len(current)} baselined, no exceptions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
