#!/usr/bin/env python3
"""Mechanical accessibility scanner — flags rules the design system states but
never mechanically verified.

**DISABLED pending correct scoping — see `design_suite/engine/audit_discovery.DISABLED`
for the measured reason and the bar for re-enabling it.** It refuses with exit 2
rather than running; `--run-disabled` overrides that for re-measurement only. The
registry entry, not this docstring, is the single source of truth every reporting
surface reads.

Thin entry point. As of Phase 0b of the decoupling plan it holds no language
knowledge and no thresholds:

  - the sweep is `design_suite/engine/scan.py` (language-agnostic)
  - the widget patterns are `design_suite/adapters/<lang>.a11y_checks`
  - the thresholds come from the audit config's `accessibility_minimums`

Checks for Dart today: font_size (below the minimum text size),
icon_button_no_tooltip (an icon-only control with no accessible label), and
small_tap_target (a gesture wrapped in a box smaller than the minimum touch
target — heuristic; real layout constraints can override it, so it is for human
review rather than a hard violation).

Two deliberate behaviours worth knowing:

  * **A check that cannot be built is reported, not skipped.** If a threshold is
    absent from config, this exits non-zero naming the missing key. A scanner
    quietly running two of three checks and printing "0 findings" is the failure
    mode this whole refactor exists to remove.
  * **Zero findings and zero coverage look different.** The summary always states
    how many files were scanned, so a clean result cannot be confused with a
    sweep that matched nothing.

Contrast checking stays out of scope: it needs real colour maths against rendered
backgrounds, not a text scan. It lives in the design-system repository, with the
palette it audits.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_accessibility.py" [--dir lib] [--out ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project          # noqa: E402
from design_suite.engine import audit_discovery        # noqa: E402
from design_suite.engine import findings as F          # noqa: E402
from design_suite.engine.scan import scan_tree, source_files         # noqa: E402

AUDIT = Path(__file__).stem


def _refuse_disabled(entry: dict) -> int:
    """Exit 2 — "I could not look" — never 0, and never a findings envelope.

    Exit 2 is this repo's CapabilityError (docs/DOC-ROLES.md's exit-code
    contract). A disabled audit that exited 0 would be baselined as clean and
    would read, to every dashboard and every agent, exactly like a codebase with
    no accessibility violations in it. That is the one outcome this suite exists
    to prevent, so the refusal is loud and the reason travels with it.
    """
    print(f"{AUDIT}: DISABLED — {entry['reason']}\n", file=sys.stderr)
    print("Why:", file=sys.stderr)
    print(f"  {entry['detail']}\n", file=sys.stderr)
    print("Path back to enabling it:", file=sys.stderr)
    print(f"  {entry['pathBack']}\n", file=sys.stderr)
    print("This is a refusal (exit 2), not a clean result. Nothing was scanned, so "
          "nothing can be concluded about this project's accessibility from this run. "
          "`--run-disabled` runs it anyway, for re-measurement only.", file=sys.stderr)
    return 2


# The raw report's default home. It used to be `<pipelines.tokens>/a11y_findings.json`
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
DEFAULT_OUT = ".design-suite/accessibility-findings.json"


def _exclude_non_screen(findings: list, adapter, exceptions: dict) -> tuple[list, dict]:
    """Set aside findings in files the project declared are not screen UI.

    issue #104's measured false-positive class: every finding was a widget from a
    print/PDF-generation library, held to a SCREEN minimum. Which library that is
    — and whether a project has one — is the project's fact, so it is declared in
    `.design-suite/exceptions.json`, never written here:

        "accessibility": {"excludeFilesImporting": [
            {"import": "<import prefix>", "reason": "generated print output"}]}

    A file is excluded when any import target the adapter reads from it starts
    with a declared prefix. Excluded findings are produced first and then
    counted, so "suppressed by a declaration" never reads as "none found".
    """
    spec = (exceptions or {}).get("accessibility") or {}
    entries = spec.get("excludeFilesImporting") or []
    if not entries:
        return findings, {}
    rx = getattr(adapter, "IMPORT_RE", None)
    if rx is None:
        raise ValueError("accessibility.excludeFilesImporting is declared but the "
                         f"{adapter.NAME!r} adapter cannot read imports — refusing "
                         "to apply an exclusion it cannot evaluate")
    prefixes = []
    for e in entries:
        if not (isinstance(e, dict) and isinstance(e.get("import"), str) and e["import"]
                and isinstance(e.get("reason"), str) and e["reason"].strip()):
            raise ValueError("accessibility.excludeFilesImporting entries need a non-empty "
                             f"'import' prefix and a 'reason': {e!r}")
        prefixes.append(e["import"])
    cache: dict[str, str | None] = {}

    def excluded_by(rel: str) -> str | None:
        if rel not in cache:
            text = (REPO / rel).read_text(errors="replace")
            targets = [m.group(1) for m in rx.finditer(text)]
            cache[rel] = next((p for p in prefixes
                               if any(t.startswith(p) for t in targets)), None)
        return cache[rel]

    kept, counts = [], {}
    for f in findings:
        hit = excluded_by(f["file"])
        if hit is None:
            kept.append(f)
        else:
            counts[hit] = counts.get(hit, 0) + 1
    return kept, counts


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    p.add_argument("--out", default=None,
                   help=f"defaults to {DEFAULT_OUT}")
    p.add_argument("--findings", nargs="?", const=True, default=None,
                   help="also write the common findings envelope for /design-debt "
                        "(bare flag uses the default path)")
    p.add_argument("--run-disabled", action="store_true",
                   help="run this audit even though it is disabled — for re-measuring "
                        "its false-positive rate, not for reporting a result to anyone")
    args = p.parse_args()

    entry = audit_discovery.disabled_reason(AUDIT)
    if entry and not args.run_disabled:
        return _refuse_disabled(entry)
    if entry:
        print(f"{AUDIT}: DISABLED, running anyway because --run-disabled was passed. "
              f"{entry['reason']}. Treat every finding below as unmeasured.",
              file=sys.stderr)

    adapter, ctx, _ = for_project(REPO)
    if not hasattr(adapter, "a11y_checks"):
        print(f"the {adapter.NAME!r} adapter implements no accessibility checks — "
              "this audit cannot run for this project's language", file=sys.stderr)
        return 2  # could not look, not a finding — see DOC-ROLES.md's exit-code contract

    checkset = adapter.a11y_checks(ctx)
    if checkset.omitted:
        print("cannot run the accessibility audit — incomplete configuration:\n", file=sys.stderr)
        for reason in checkset.omitted:
            print(f"  {reason}", file=sys.stderr)
        print("\nRefusing to report a partial pass. Set the missing minimum(s) and re-run.",
              file=sys.stderr)
        return 2  # refusal, not a finding — this used to collide with the findings code (1)

    scan_dir = args.dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = REPO / scan_dir
    if not scan_root.is_dir():
        print(f"no such directory: {scan_root}", file=sys.stderr)
        return 2  # could not look — missing scan dir, not a finding

    skip = set()
    if theme := ctx.exceptions.get("themeFileToSkip"):
        skip.add(theme)

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    scanned = source_files(scan_root, globs)
    if not scanned:
        print(f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ "
              f"(globs: {', '.join(globs)}).\nReporting zero findings here would be "
              "indistinguishable from a clean codebase, so this is an error. Check that "
              "adapters.lang in the profile matches the language this tree is written in.",
              file=sys.stderr)
        return 2  # zero-file glob is a config mismatch, not a finding — do not collide with 1

    findings = scan_tree(scan_root, REPO, checkset, globs=globs, skip_files=skip)
    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    if generated:
        findings = [f for f in findings if not f["file"].endswith(generated)]
    try:
        findings, suppressed = _exclude_non_screen(findings, adapter, ctx.exceptions)
    except ValueError as exc:
        print(f"{AUDIT}: {exc}", file=sys.stderr)
        return 2
    findings.sort(key=lambda f: (f["file"], f["line"]))

    out_rel = args.out or DEFAULT_OUT
    out_path = REPO / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2) + "\n")

    if args.findings:
        # `scanned` matters more here than anywhere: this audit legitimately
        # reports zero on a compliant codebase, so the file count is the only
        # thing distinguishing that from an audit that examined nothing.
        F.write(
            F.default_path(REPO, "accessibility") if args.findings is True
            else REPO / args.findings,
            "accessibility",
            [F.make("accessibility", f["kind"],
                    f.get("snippet", "").split("\n")[0].strip(),
                    severity=F.SHOULD_FIX, file=f["file"], line=f["line"])
             for f in findings],
            scanned=len(scanned),
        )

    n_files = len({f["file"] for f in findings})
    # An absolute --out outside the project (a read-only re-measurement run)
    # used to crash here with ValueError — after the write, so exit 1 with a
    # traceback, read as findings.
    try:
        shown = out_path.relative_to(REPO)
    except ValueError:
        shown = out_path
    print(f"Found {len(findings)} accessibility findings across {n_files} files "
          f"→ {shown}")
    for prefix, n in sorted(suppressed.items()):
        print(f"  set aside {n} finding(s) in files importing {prefix!r} "
              f"(declared non-screen in exceptions.json accessibility.excludeFilesImporting)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
