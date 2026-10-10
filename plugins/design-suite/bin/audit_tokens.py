#!/usr/bin/env python3
"""Flag hardcoded design values that should route through design tokens instead.

Thin entry point. As of Phase 0b of the decoupling plan, this file holds no
language knowledge at all:

  - the sweep lives in `design_suite/engine/scan.py` (language-agnostic)
  - what a violation *looks like* lives in `design_suite/adapters/<lang>.py`,
    selected by `adapters.lang` in `.design-suite/profile.json`
  - which files are exempt lives in `.design-suite/exceptions.json`

It previously held `Color(0x...)`, `EdgeInsets.all(`, `BorderRadius.circular(`,
`Duration(milliseconds:`, `Curves.` and `AppTokens.` as module constants, which
meant it could only ever audit a Flutter project. The regexes are unchanged; they
moved to the Dart adapter.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens.py" [--dir lib] [--out ...]

Checks come from the adapter. For Dart today: color, edge_insets, border_radius,
duration, curve, entrance_curve.

Exits 1 if the design-audit config's token list has drifted from the design
system's real tokens — a token the audit does not list is one it can never flag.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project, uncovered_files  # noqa: E402
from design_suite.engine import exceptions as X        # noqa: E402
from design_suite.engine import findings as F          # noqa: E402
from design_suite.engine.scan import (scan_tree, source_files, skip_dirs_from,  # noqa: E402
                                      scan_skip_file_includes)       # noqa: E402


def _config_drift(adapter, ctx) -> list[str]:
    """Whether the design-audit config's token list matches the real tokens.

    The list cannot be generated — the config is mostly prose about what a
    violation looks like — so it is checked instead, in both directions. A listed
    name that no longer exists is as bad as an unlisted token: the first sends a
    reviewer looking for something that is gone.
    """
    config_rel = (ctx.profile.get("audits", {}) or {}).get("configFile")
    if not config_rel:
        return []
    config_path = REPO / config_rel
    if not config_path.is_file():
        return [f"{config_rel} is declared in the profile but does not exist"]

    try:
        parsed = json.loads(config_path.read_text())
    except ValueError as exc:
        return [f"{config_rel} is not valid JSON: {exc}"]
    groups = parsed.get("token_categories", {}).get("color", {}).get("names", {})
    listed = {n for v in groups.values() if isinstance(v, list) for n in v}

    real = adapter.token_names(ctx) if hasattr(adapter, "token_names") else None
    if real is None:
        # Undeterminable, not empty. Reporting every listed token as stale here
        # would turn "the package is not resolved" into a wall of false findings.
        return []

    problems = []
    if missing := sorted(real - listed):
        problems.append(
            f"{config_rel} does not list {len(missing)} colour token(s): "
            f"{', '.join(missing)}. A token the design audit does not know about "
            "is one it will never flag a violation of."
        )
    if stale := sorted(listed - real):
        problems.append(
            f"{config_rel} lists {len(stale)} token(s) that no longer exist: "
            f"{', '.join(stale)}. Reviewers will look for something that is gone."
        )
    return problems


# The raw report's default home. It used to be `<pipelines.tokens>/findings.json`
# — the project's own token-pipeline directory, at the project root, outside
# `.design-suite/` and so unreachable by the scaffolded `.design-suite/.gitignore`.
# The report quotes source lines, so every plain run left a tracked-by-default
# file of code excerpts in the client repository.
#
# `pipelines.tokens` deliberately does NOT win here. That key names where the
# project keeps its token *pipeline* (generator, sources) — authored, tracked
# content. A findings report is regenerable suite output, which is what
# `.design-suite/` holds and its .gitignore covers. Same precedent as
# audit_adapter_pattern / audit_layer_boundaries / audit_reduced_motion. Not
# under `.design-suite/findings/`: /design-debt reads every file there as a
# common-findings envelope, and this list is not one (`--findings` writes that).
DEFAULT_OUT = ".design-suite/tokens-findings.json"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    p.add_argument("--out", default=None,
                   help=f"defaults to {DEFAULT_OUT}")
    p.add_argument("--findings", nargs="?", const=True, default=None,
                   help="also write the common findings envelope for /design-debt "
                        "(bare flag uses the default path)")
    args = p.parse_args()

    adapter, ctx, checks = for_project(REPO)

    scan_dir = args.dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = REPO / scan_dir
    if not scan_root.is_dir():
        print(f"no such directory: {scan_root}", file=sys.stderr)
        return 2  # could not look — missing scan dir, not a finding

    exceptions = ctx.exceptions
    skip = set()
    if theme := exceptions.get("themeFileToSkip"):
        skip.add(theme)

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    skip_dirs = skip_dirs_from(exceptions)
    scanned = source_files(scan_root, globs, skip_dirs)
    if not scanned:
        print(f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ "
              f"(globs: {', '.join(globs)}).\nReporting zero findings here would be "
              "indistinguishable from a clean codebase, so this is an error. Check that "
              "adapters.lang in the profile matches the language this tree is written in.",
              file=sys.stderr)
        return 2  # zero-file glob is a config mismatch, not a finding — do not collide with 1

    findings = scan_tree(scan_root, REPO, checks, globs=globs, skip_files=skip,
                         skip_dirs=skip_dirs,
                         file_filter=getattr(adapter, "non_product_file", None),
                         include_files=scan_skip_file_includes(exceptions))
    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    if generated:
        findings = [f for f in findings if not f["file"].endswith(generated)]
    findings, suppressed = X.partition(
        findings,
        {check.kind: check.category for check in checks},
        X.exemptions(exceptions),
        X.report_anyway(exceptions),
    )
    findings.sort(key=lambda f: (f["file"], f["line"]))
    suppression = X.report(suppressed)

    out_rel = args.out or DEFAULT_OUT
    out_path = REPO / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2) + "\n")

    if args.findings:
        # Additive. `--out` above keeps its shape byte-for-byte because
        # capture-baselines.sh diffs it; this is a second file, not a rewrite.
        # Severity is uniform here on purpose: which token kinds matter more is a
        # judgment the /audit-tokens skill makes against the project's documented
        # exceptions, and encoding one project's answer in the engine is the
        # coupling this suite spent a refactor removing.
        F.write(
            F.default_path(REPO, "tokens") if args.findings is True
            else REPO / args.findings,
            "tokens",
            [F.make("tokens", f["kind"], f.get("snippet", "").split("\n")[0].strip(),
                    file=f["file"], line=f["line"])
             for f in findings],
            scanned=len(scanned),
            suppressed=suppression,
        )

    if problems := _config_drift(adapter, ctx):
        print("the design-audit config is out of step with the tokens:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 2  # could not trust this run's findings — config drift, not a finding itself

    unscanned = uncovered_files(scan_root, adapter, exceptions)
    if unscanned:
        listing = ", ".join(f"{n} {suffix}" for suffix, n in unscanned.items())
        print(f"NOT SCANNED under {scan_dir}/: {listing} — files of a stack the "
              f"{adapter.NAME!r} adapter does not read (it globs {', '.join(globs)}).",
              file=sys.stderr)
        if not findings:
            # Zero findings over a partial sweep is the governing failure: a
            # Vue project on `tsx` printed "Found 0" while every hardcoded value
            # sat in .vue/.css files this adapter never opened.
            print("Zero findings over a partial sweep is INERT, not clean. Pick an "
                  "adapter that covers these files (e.g. 'web' for .vue/.svelte/"
                  ".css/.scss), or record the decision in exceptions.json "
                  "`acknowledgedUnscanned`.", file=sys.stderr)
            return 2

    n_files = len({f["file"] for f in findings})
    # An absolute --out is how this audit is run read-only against a project it
    # must not write into, so the path it reports cannot assume it is under REPO.
    try:
        shown = out_path.relative_to(REPO)
    except ValueError:
        shown = out_path
    print(f"Found {len(findings)} hardcoded-value findings across {n_files} files "
          f"→ {shown}")
    # On the same surface as the count above, deliberately: silence here would
    # make a documented exception and a clean file read identically to whoever is
    # deciding whether to trust this audit.
    for line in X.describe(suppression):
        print(line)
    # Findings travel via --out, so this exit code is the only signal a caller
    # gets without reading that file back — it must carry the finding count.
    # This used to always `return 0`, which made a hardcoded-value hit
    # indistinguishable from a clean run for every consumer hook wired to it.
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
