#!/usr/bin/env python3
"""Mechanical focus-order audit — a screen's traversal order vs. its visual order.

## What this checks, and what it cannot

A screen reader / Tab key walks widgets in **traversal order**; a sighted user
reads in **visual order** (top-to-bottom, left-to-right). The two silently
diverge whenever a widget is positioned away from where it was declared —
absolute positioning, a transform, or an explicit traversal override — and that
divergence is invisible to visual QA, because the screen still *looks* right.

This suite operates on source, not a running app: there is no rendered DOM to
walk, no live focus ring to Tab through, no computed layout. So this audit is
**best-effort and structural**, not a rendered-order walk, and it says so before
reporting anything:

  * `stack_order_mismatch` — the one case a text scan can genuinely catch. A
    `Stack`'s `Positioned` children are Flutter's direct equivalent of CSS
    absolute positioning, and their `top`/`left` literals are visible in source.
    When a later-declared `Positioned` sits visually above/left of an
    earlier one, default (`WidgetOrderTraversalPolicy`) traversal will visit
    them out of reading order. Heuristic, not certain — see the docstring on
    `design_suite.adapters.dart.stack_order_findings` for exactly what it
    cannot see (Transform, computed offsets, RTL, non-inline Stacks).

  * `autofocus_override` / `explicit_traversal_order` — every place traversal
    is overridden explicitly (`autofocus: true`, `FocusTraversalOrder(...)`).
    These are not defects by themselves — an explicit override is often exactly
    what's wanted — but they are exactly where a *mistaken* one gets introduced,
    and correctness cannot be judged from text alone. Flagged for review, at FYI
    severity, same posture as `small_tap_target` in audit_accessibility.py.

**What this audit cannot see at all, by construction**: a Row/Column reordered
via `Flex`'s `order`, offsets computed from `MediaQuery`/`LayoutBuilder`/an
animation value, a `Transform.translate` shift, an `OverlayEntry`, a Stack built
by a helper method rather than written inline, or anything about actual runtime
focus order (which `FocusTraversalPolicy` a `FocusTraversalGroup` up the tree
installs, which decides whether a screen even reads in declaration order to
begin with). None of that is silently skipped and reported clean — it is named
here and in the report's caveat line, because this suite's rule is that an
audit that finds nothing must never look like an audit that checked everything.

If a genuinely rendered/runtime focus walk is ever wanted, it needs a Flutter
integration-test harness (`WidgetTester` + `FocusScope`) driving a real
widget tree — a different tool from this one, which never renders anything.

Config: `.design-suite/exceptions.json` may set `focusOrderFilesToSkip` (a file
path) the same way `audit_accessibility.py` honours `themeFileToSkip`. Which
widgets count as "focusable" for the `stack_order_mismatch` check — scoping the
check to Positioned blocks that actually matter for tab order — is configurable
via the audit config's `focus_order.focusableWidgets`; unset, it falls back to
`design_suite.adapters.dart.FOCUSABLE_DEFAULT`. A missing list is a reasonable
default, not a missing hard threshold (unlike `min_text_sp`/`min_touch_target_dp`
in audit_accessibility.py), so it does not omit the check.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_focus_order.py" [--dir lib] [--out ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project          # noqa: E402
from design_suite.engine import findings as F          # noqa: E402
from design_suite.engine.scan import scan_tree, source_files  # noqa: E402


# The raw report's default home. It used to be `<pipelines.tokens>/focus_order_findings.json`
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
DEFAULT_OUT = ".design-suite/focus-order-findings.json"


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
    if not hasattr(adapter, "focus_order_checks"):
        print(f"the {adapter.NAME!r} adapter implements no focus-order checks — "
              "this audit cannot run for this project's language", file=sys.stderr)
        return 2  # could not look, not a finding — see DOC-ROLES.md's exit-code contract

    checkset = adapter.focus_order_checks(ctx)
    if checkset.omitted:
        print("cannot run the focus-order audit — incomplete configuration:\n", file=sys.stderr)
        for reason in checkset.omitted:
            print(f"  {reason}", file=sys.stderr)
        print("\nRefusing to report a partial pass.", file=sys.stderr)
        return 2  # refusal, not a finding — this used to collide with the findings code (1)

    scan_dir = args.dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = REPO / scan_dir
    if not scan_root.is_dir():
        print(f"no such directory: {scan_root}", file=sys.stderr)
        return 2  # could not look — missing scan dir, not a finding

    skip = set()
    if skip_file := ctx.exceptions.get("focusOrderFilesToSkip"):
        skip.add(skip_file)

    focusable = (
        (ctx.audit_config.get("focus_order", {}) or {}).get("focusableWidgets")
        or getattr(adapter, "FOCUSABLE_DEFAULT", ())
    )

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    scanned = source_files(scan_root, globs)
    if not scanned:
        print(f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ "
              f"(globs: {', '.join(globs)}).\nReporting zero findings here would be "
              "indistinguishable from a clean codebase, so this is an error. Check that "
              "adapters.lang in the profile matches the language this tree is written in.",
              file=sys.stderr)
        return 2  # zero-file glob is a config mismatch, not a finding — do not collide with 1

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

    findings = scan_tree(scan_root, REPO, checkset, globs=globs, skip_files=skip)

    # Path-aware variant: an adapter spanning several file kinds (tsx, web)
    # needs the path to know which files hold markup at all.
    file_check = getattr(adapter, "file_focus_findings", None)
    if file_check is not None:
        for path in scanned:
            rel = str(path.relative_to(REPO))
            if rel in skip:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for f in file_check(rel, source):
                findings.append({"file": rel, "line": f["line"], "kind": f["kind"],
                                  "snippet": f["snippet"]})

    stack_check = getattr(adapter, "stack_order_findings", None)
    if stack_check is not None:
        for path in scanned:
            rel = str(path.relative_to(REPO))
            if rel in skip:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for f in stack_check(source, focusable):
                findings.append({"file": rel, "line": f["line"], "kind": f["kind"],
                                  "snippet": f["snippet"]})

    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    if generated:
        findings = [f for f in findings if not f["file"].endswith(generated)]
    findings.sort(key=lambda f: (f["file"], f["line"]))

    out_rel = args.out or DEFAULT_OUT
    out_path = REPO / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "focus-order") if args.findings is True
            else REPO / args.findings,
            "focus-order",
            [F.make("focus-order", f["kind"],
                    f.get("snippet", "").split("\n")[0].strip(),
                    severity=F.FYI, file=f["file"], line=f["line"])
             for f in findings],
            scanned=len(scanned),
        )

    n_files = len({f["file"] for f in findings})
    print(f"Found {len(findings)} focus-order findings across {n_files} files "
          f"→ {out_path.relative_to(REPO)}")
    print(getattr(adapter, "FOCUS_ORDER_CAVEAT", None) or
          "Best-effort, source-only: catches Stack/Positioned order mismatches and "
          "explicit traversal overrides. Cannot see Transform, computed offsets, "
          "Flex `order`, or actual runtime traversal — see this script's docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
