#!/usr/bin/env python3
"""Mechanical check for the Adapter Pattern import rule in
docs/INSTRUCTIONS.md §3: "Screens must never import BLoC, repositories,
data sources, or ApiClient directly." Pure Python regex, zero dependencies,
same portable-core pattern as audit_mock_api.py/audit_accessibility.py.

Scans the files matching adapterPattern.screensGlob (relative to the screens
dir; the dart adapter supplies a feature-first default, no other stack has one)
for imports matching adapterPattern.bannedImports. Which files are source and
how an import is spelled come from the language adapter (FILE_GLOBS,
IMPORT_RE). Files ending in adapterPattern.exemptSuffixes (dart default:
route-entry `_page_wrapper.dart`) are skipped.

Exit 0 only when >=1 in-scope file was scanned and none violates. Exit 2
(REFUSED, INERT) when it cannot check: no adapter, adapter cannot read imports,
TODO-placeholder rules, no scope for this stack, or zero files in scope.

This is a deterministic, unambiguous check (an import is either present or
not, no heuristic false positives), so any finding is treated as blocking.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_adapter_pattern.py" [--dir <screens dir>] [--out <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import MARKER, project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

sys.path.insert(0, str(REPO))
from design_suite.adapters import for_project  # noqa: E402
from design_suite.engine import imports as I  # noqa: E402
from design_suite.engine.arch import compiled_patterns, load  # noqa: E402
from design_suite.engine.refusal import Refused  # noqa: E402
from design_suite.project import profile as project_profile  # noqa: E402

AUDIT = "audit_adapter_pattern"

# What a screen may not import is a fact about this project's architecture, not
# about how to walk files, so it lives in .design-suite/arch-rules.json.
_RULES = load(REPO, "adapterPattern")
if I.placeholder(_RULES.get("bannedImports")) or I.placeholder(_RULES.get("screensGlob")):
    raise Refused(
        "adapterPattern in the architecture rules still holds init.py's TODO "
        "placeholders — there is no real rule to enforce yet. Fill it in or delete "
        "the section.", AUDIT)
BANNED_PATTERNS = compiled_patterns(_RULES.get("bannedImports") or [])
if not BANNED_PATTERNS:
    raise Refused("adapterPattern.bannedImports is empty — an audit with nothing "
                  "banned passes vacuously.", AUDIT)

# Which files are source, and how an import is spelled, are language facts:
# they come from the adapter. Used to be a hardcoded `*.dart` sweep and a Dart
# import regex, which on every other stack scanned nothing and printed
# "no violations found" with exit 0.
_ADAPTER, _CTX, _ = for_project(REPO)
IMPORT_RE = I.import_re(_ADAPTER, AUDIT)


def _scan_file(path: Path) -> list[dict]:
    findings = []
    rel = path.relative_to(REPO).as_posix()
    for lineno, target in I.import_targets(IMPORT_RE, path.read_text(errors="replace")):
        for label, pattern in BANNED_PATTERNS:
            if pattern.search(target):
                findings.append(
                    {
                        "file": rel,
                        "line": lineno,
                        "import": target,
                        "detail": (
                            f"{rel}:{lineno} imports {target!r} ({label}) — screens "
                            "must reach this layer only through an adapter."
                        ),
                    }
                )
    return findings


def _screens_glob() -> str:
    declared = _RULES.get("screensGlob") or getattr(_ADAPTER, "ADAPTER_PATTERN_SCREENS_GLOB", None)
    if not declared:
        raise Refused(
            f"no screens scope: set adapterPattern.screensGlob in the architecture "
            f"rules (a glob relative to the screens dir, e.g. '**/pages/**/*') — the "
            f"{_ADAPTER.NAME!r} adapter has no default layout to assume.", AUDIT)
    return declared


def _default_scan_dir() -> str:
    """Where this project keeps its screens, with no directory name assumed.

    `adapterPattern.screensDir` in the architecture rules wins. Absent that, the
    profile's `source.root` is used — the whole source tree rather than a guessed
    subdirectory of it, because scanning too widely reports real findings while
    scanning a directory that does not exist reports nothing at all, and only one
    of those two failures is visible.
    """
    if declared := _RULES.get("screensDir"):
        return str(declared)
    return str(project_profile(REPO).get("source", {}).get("root") or ".")


def main() -> int:
    parser = argparse.ArgumentParser()
    # `lib/features` used to be the default here, which is one project's layout
    # written into a universal plugin: on any project shaped differently the
    # directory did not exist, and the `return 2` below made that look like a
    # configuration error rather than what it was — a check that could never
    # have run. The location of screens is a fact about a project's
    # architecture, so it comes from arch-rules.json alongside the banned
    # imports this audit already reads from there, falling back to the profile's
    # own source root rather than to anybody's directory name.
    parser.add_argument(
        "--dir", default=None,
        help="defaults to adapterPattern.screensDir in the architecture rules, "
             "else the profile's source.root")
    # Default lives inside .design-suite/ (the profile marker directory, MARKER),
    # never under a guessed top-level project directory, which is what it was: one
    # project's layout baked into the universal plugin, and it created the
    # directory on projects that had none. Inside .design-suite/ the report is
    # also covered by the .gitignore bin/init.py scaffolds there; a .gitignore
    # only governs its own directory, so a report anywhere else could not be.
    # Not under findings/: that directory holds the common envelopes
    # /design-debt reads, and a raw report there would be read as a malformed one.
    parser.add_argument("--out", default=f"{MARKER}/adapter-pattern-findings.json",
                        help="where the raw report is written (default: %(default)s)")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(bare flag uses the default path)")
    args = parser.parse_args()

    scan_root = REPO / (args.dir or _default_scan_dir())
    if not scan_root.is_dir():
        raise Refused(f"no such directory: {scan_root}", AUDIT)

    glob = _screens_glob()
    exempt = tuple(_RULES.get("exemptSuffixes")
                   or getattr(_ADAPTER, "ADAPTER_PATTERN_EXEMPT_SUFFIXES", ()))
    findings: list[dict] = []
    scanned = 0
    for path in I.adapter_files(scan_root, _ADAPTER, glob):
        if exempt and path.name.endswith(exempt):
            continue
        scanned += 1
        findings.extend(_scan_file(path))

    if scanned == 0:
        # The silent-wrong case this audit used to have: nothing in scope was
        # read, so "no violations" would be a claim about nothing.
        raise Refused(
            f"0 {_ADAPTER.NAME} source files matched {glob!r} under "
            f"{scan_root.relative_to(REPO).as_posix() or '.'} — nothing in scope was "
            f"scanned. Set adapterPattern.screensDir / screensGlob to where this "
            f"project's screens live.", AUDIT)

    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2) + "\n")
    if args.findings:
        from design_suite.engine import findings as F
        F.write(
            F.default_path(REPO, "adapter_pattern") if args.findings is True
            else REPO / args.findings,
            "adapter_pattern",
            F.from_records("adapter_pattern", findings, category="adapter_pattern"),
            # Without this a genuine 0-finding pass is indistinguishable from an
            # audit that examined nothing, which is the failure this suite's
            # governing principle names first.
            scanned=scanned,
        )

    if not findings:
        print("audit_adapter_pattern: no violations found")
        return 0

    print(f"VIOLATIONS ({len(findings)}):")
    for f in findings:
        print(f"  {f['detail']}")
    print(f"\nFindings written to {args.out}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
