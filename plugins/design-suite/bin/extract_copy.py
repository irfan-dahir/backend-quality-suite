#!/usr/bin/env python3
"""Extract user-facing copy into a structured inventory.

Thin entry point. This file's own docstring used to describe the split it never
implemented — *"this is the one project-specific seam… a future project would swap
this script for one that knows its own copy-storage convention, while the audit
heuristics that consume the inventory stay unchanged."* As of Phase 0b that split
is real:

  - readability scoring and microcopy classification live in
    `design_suite/engine/copy.py`, which knows no language
  - finding the strings is `design_suite/adapters/<lang>.extract_copy_strings`

Each inventory entry: {file, line, text, category, kind, word_count,
flesch_reading_ease}. `category` is a heuristic ("microcopy" vs "content"), not
authoritative: strings reached through a UI-chrome keyword argument are microcopy
by construction, and otherwise short strings are microcopy and longer ones are
content. What counts as a chrome keyword, and which strings are dynamic and so
unjudgeable, are both language facts the adapter decides.

`kind` is provenance, not judgement: the literal widget/keyword the string was
extracted through ("text" for a bare Text(...) literal, otherwise the keyword's
own name — "label", "title", "hintText", ...). Without it, two entries sharing
the same text (a nav label and a screen title both reading "Home") are
indistinguishable in any report built on the inventory.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/extract_copy.py" [--dir lib] [--out ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project          # noqa: E402
from design_suite.engine import pipelines as PIPE         # noqa: E402
from design_suite.engine.copy import build_inventory   # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    p.add_argument("--out", default=None,
                   help="defaults to <pipelines.copy>/inventory.json from the profile")
    args = p.parse_args()

    adapter, ctx, _ = for_project(REPO)
    # One builder, shared with audit_copy.py — see engine/copy.build_inventory
    # on why the gate rebuilds rather than reading this file back.
    inventory = build_inventory(REPO, adapter, ctx, args.dir)

    out_rel = args.out or PIPE.out_path(ctx.profile, "copy", "inventory.json")
    out_path = REPO / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inventory, indent=2) + "\n")

    n_files = len({e["file"] for e in inventory})
    n_skipped = sum(1 for e in inventory if e.get("category") == "dynamic")
    skipped_note = (f" ({n_skipped} skipped — dynamic/unjudgeable, see "
                    f"skip_reason)" if n_skipped else "")
    print(f"Extracted {len(inventory)} copy entries from {n_files} files "
          f"→ {out_path.relative_to(REPO)}{skipped_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
