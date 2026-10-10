#!/usr/bin/env python3
"""Four precisely-scoped semantics rules (issue #128), each from a shipped defect.

## Why this is not `audit_accessibility` under a new name

`audit_accessibility` is disabled (`design_suite/engine/audit_discovery.DISABLED`):
100% of its findings on two real projects were wrong, and on one it had zero
true-positive capacity, because its rules were *thresholds over shapes that are
only sometimes wrong* — a `fontSize:` literal is a defect on screen and nothing
in a PDF, and the scanner could not tell which. Nothing in this audit shares
that shape:

  * No thresholds, no `fontSize:`, no tap-target sizes, no config minimums.
    Every rule is about which semantics argument is or is not present, which is
    the same in every Flutter project.
  * Three rules (2, 3, 4) are structural: issue #128 argues there is no correct
    program with the shape, only an annotated exception. That argument is a
    claim, not a measurement — hence `maturity: unverified`.
  * The one rule that was measured wrong (rule 1, 40% false positives in the
    issue's own follow-up) is reported at **fyi** severity and never affects the
    exit code. It is a review prompt whose stated remedy is a rendered-semantics
    test, not a gate.
  * Each rule has a planted true positive, its named false positive, and a clean
    control in `audit_semantics_test.py`, so "finds nothing" is falsifiable here.

What this does NOT do: re-enable `audit_accessibility`, or clear its `pathBack`
bar. That bar (<=5% wrong AND non-zero true-positive capacity, re-measured on
real projects by an independent judge) applies to this audit's gating rules too
before anyone treats it as more than unverified.

## What it cannot see

A subtree built by a helper method (`child: _buildRow()`), an ancestor
`Semantics` in another file, and the rendered SemanticsNode tree. A rule that
cannot see its subtree does not fire; that gap is named in the report caveat.

## Escapes

Each rule is its own exceptions category in `.design-suite/exceptions.json`,
using the existing `allowlistFiles` / `allowlistRegions` / `reportAnyway`
machinery (`design_suite/engine/exceptions.py`) — e.g.

    {"selection_by_colour_only": {"allowlistFiles": [
        {"path": "lib/x/chip.dart", "reason": "selection published on ancestor"}]}}

Suppressed findings are counted and printed, never silently dropped.

Exit: 0 clean or fyi-only, 1 should_fix findings, 2 could not look.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_semantics.py" [--dir lib] [--out ...] [--findings]
"""
from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project          # noqa: E402
from design_suite.engine import exceptions as X        # noqa: E402
from design_suite.engine import findings as F          # noqa: E402
from design_suite.engine.scan import source_files      # noqa: E402

CAVEAT = ("Source-only: cannot see subtrees built by helper methods or other files, "
          "ancestor Semantics in a parent widget's file, or the rendered semantics "
          "tree. tappable_in_labelling_semantics is advisory (fyi) — confirm each "
          "with a rendered-semantics test before changing code.")


# The raw report's default home. It used to be `<pipelines.tokens>/semantics_findings.json`
# — the project's token-pipeline directory, at the project root, outside
# `.design-suite/` and so unreachable by the scaffolded `.design-suite/.gitignore`.
# The report quotes source lines, so every plain run left a tracked-by-default
# file of code excerpts in the client repository.
#
# `pipelines.tokens` deliberately does NOT win here: it names where the project
# keeps its token *pipeline* — authored, tracked content. A findings report is
# regenerable suite output, which is what `.design-suite/` holds and its
# .gitignore covers. Same precedent as audit_tokens / audit_adapter_pattern /
# audit_layer_boundaries. Not under `.design-suite/findings/`: /design-debt
# reads every file there as a common-findings envelope, and this list is not
# one (`--findings` writes that).
DEFAULT_OUT = ".design-suite/semantics-findings.json"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    p.add_argument("--out", default=None,
                   help=f"defaults to {DEFAULT_OUT}")
    p.add_argument("--findings", nargs="?", const=True, default=None,
                   help="also write the common findings envelope for /design-debt "
                        "(bare flag uses the default path)")
    args = p.parse_args()

    adapter, ctx, _ = for_project(REPO)
    rules = getattr(adapter, "semantics_findings", None)
    file_rules = getattr(adapter, "file_semantics_findings", None)
    if file_rules is not None:
        # Path-aware variant (tsx, web): only markup-capable files are read.
        rules = None
    if rules is None and file_rules is None:
        print(f"the {adapter.NAME!r} adapter implements no semantics rules — "
              "this audit cannot run for this project's language", file=sys.stderr)
        return 2

    scan_dir = args.dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = REPO / scan_dir
    if not scan_root.is_dir():
        print(f"no such directory: {scan_root}", file=sys.stderr)
        return 2

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    scanned = source_files(scan_root, globs)
    if not scanned:
        print(f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ "
              f"(globs: {', '.join(globs)}).\nReporting zero findings here would be "
              "indistinguishable from a clean codebase, so this is an error.",
              file=sys.stderr)
        return 2

    # An adapter spanning several file kinds reads only some of them for these
    # rules. A sweep that globbed files but read none is INERT, not clean.
    readable = getattr(adapter, "MARKUP_SUFFIXES", None)
    if readable is not None and not any(str(f).endswith(tuple(readable)) for f in scanned):
        print(f"the {adapter.NAME!r} adapter globbed {len(scanned)} file(s) under "
              f"{scan_dir}/ but none it can read for these rules "
              f"({', '.join(readable)}). Reporting zero findings would be "
              "indistinguishable from a clean codebase, so this is a refusal.",
              file=sys.stderr)
        return 2

    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    findings = []
    for path in scanned:
        rel = str(path.relative_to(REPO))
        if generated and rel.endswith(generated):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for f in (file_rules(rel, source) if file_rules else rules(source)):
            findings.append({"file": rel, **f})

    exceptions = ctx.exceptions
    kinds = getattr(adapter, "SEMANTICS_KINDS", ())
    findings, suppressed = X.partition(
        findings, {k: k for k in kinds},
        X.exemptions(exceptions), X.report_anyway(exceptions))
    findings.sort(key=lambda f: (f["file"], f["line"]))
    suppression = X.report(suppressed)

    out_rel = args.out or DEFAULT_OUT
    out_path = REPO / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "semantics") if args.findings is True
            else REPO / args.findings,
            "semantics",
            [F.make("semantics", f["kind"], f["snippet"],
                    severity=F.FYI if f["severity"] == "fyi" else F.SHOULD_FIX,
                    file=f["file"], line=f["line"])
             for f in findings],
            scanned=len(scanned),
            suppressed=suppression,
        )

    gating = [f for f in findings if f["severity"] != "fyi"]
    n_files = len({f["file"] for f in findings})
    try:
        shown = out_path.relative_to(REPO)
    except ValueError:
        shown = out_path
    print(f"Found {len(findings)} semantics findings ({len(gating)} should_fix, "
          f"{len(findings) - len(gating)} fyi) across {n_files} of {len(scanned)} "
          f"files → {shown}")
    for line in X.describe(suppression):
        print(line)
    print(getattr(adapter, "SEMANTICS_CAVEAT", None) or CAVEAT)
    return 1 if gating else 0


if __name__ == "__main__":
    sys.exit(main())
