#!/usr/bin/env python3
"""Flag animated nodes with no reduced-motion signal wired nearby.

Thin entry point, same shape as `audit_tokens.py`:

  - the sweep lives in `design_suite/engine/scan.py` (language-agnostic)
  - what counts as "animated" and what a reduced-motion signal looks like lives
    in `design_suite/adapters/<lang>.py`'s `reduced_motion_checks`, selected by
    `adapters.lang` in `.design-suite/profile.json`
  - which *widget names* count as animated is config, not code:
    `token_categories.motion.animated_widgets` in the design-audit config file
    named by `audits.configFile` in the profile. This file never hardcodes a
    widget list — see CLAUDE.md's "no project literal in the universal plugin"
    table.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reduced_motion.py" [--dir lib] [--out ...]

Exits 2 (could not look, not a silent zero-finding pass) when:
  - the adapter matches no files under the scan root
  - the adapter cannot build the check at all because the config's
    `animated_widgets` list is missing, empty, or still the scaffolded TODO
    placeholder — this is "cannot answer", never "nothing is animated"

Exits 1 when it found an unwired animated node, 0 only when it scanned and found
none.
"""
from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project          # noqa: E402
from design_suite.engine import findings as F          # noqa: E402
from design_suite.engine.scan import scan_tree, source_files         # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    p.add_argument("--out", default=".design-suite/reduced-motion-findings.json")
    p.add_argument("--findings", nargs="?", const=True, default=None,
                   help="also write the common findings envelope for /design-debt "
                        "(bare flag uses the default path)")
    args = p.parse_args()

    adapter, ctx, _all_checks = for_project(REPO)

    if not hasattr(adapter, "reduced_motion_checks"):
        print(f"the {adapter.NAME!r} adapter does not implement reduced_motion_checks — "
              "cannot audit reduced-motion wiring for this stack.", file=sys.stderr)
        return 2  # could not look, not a finding — see DOC-ROLES.md's exit-code contract

    checks = adapter.reduced_motion_checks(ctx)

    if checks.omitted:
        print("cannot audit reduced-motion wiring — this is a refusal, not a clean "
              "result:\n", file=sys.stderr)
        for reason in checks.omitted:
            print(f"  {reason}", file=sys.stderr)
        return 2  # refusal, not a finding — this used to collide with the findings code (1)

    scan_dir = args.dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = REPO / scan_dir
    if not scan_root.is_dir():
        print(f"no such directory: {scan_root}", file=sys.stderr)
        return 2  # could not look — missing scan dir, not a finding

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    scanned = source_files(scan_root, globs)
    if not scanned:
        print(f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ "
              f"(globs: {', '.join(globs)}).\nReporting zero findings here would be "
              "indistinguishable from a clean codebase, so this is an error. Check that "
              "adapters.lang in the profile matches the language this tree is written in.",
              file=sys.stderr)
        return 2  # zero-file glob is a config mismatch, not a finding — do not collide with 1

    found = scan_tree(scan_root, REPO, checks, globs=globs)
    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    if generated:
        found = [f for f in found if not f["file"].endswith(generated)]
    found.sort(key=lambda f: (f["file"], f["line"]))

    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(found, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "reduced_motion") if args.findings is True
            else REPO / args.findings,
            "reduced_motion",
            [F.make("reduced_motion", f["kind"], f.get("snippet", "").split("\n")[0].strip(),
                    file=f["file"], line=f["line"])
             for f in found],
            scanned=len(scanned),
        )

    n_files = len({f["file"] for f in found})
    print(f"Found {len(found)} unwired-animation finding(s) across {n_files} files "
          f"→ {out_path.relative_to(REPO)}")
    # Findings are should_fix and travel via --out, so the exit code is the only
    # signal a hook gets. Returning 0 here (missed by issue #119's sweep, which
    # fixed the same line in audit_tokens.py) made a planted violation read as
    # `clean` in repo_health.py and every hooks.map consumer.
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
