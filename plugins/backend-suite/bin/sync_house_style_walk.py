#!/usr/bin/env python3
"""Regenerate house-style's copy of backend_suite.project.walk().

Why a generated copy and not an import: house-style is installed into its
own plugin cache directory (`cache/<marketplace>/house-style/<hash>/`),
which does not contain backend_suite/, and the sibling backend-suite cache sits
under a different, per-version hash — possibly several, possibly none. There is
no path it could import from that is guaranteed to be the version installed
beside it. So the copy stays; hand-syncing it is what goes.

The copy is the root-finding *decision* only (walk). resolve_role.py's refusal
messages around it are its own and are not generated.

    python3 plugins/backend-suite/bin/sync_house_style_walk.py          # write
    python3 plugins/backend-suite/bin/sync_house_style_walk.py --check  # 0 current, 1 stale

Stdlib only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
SOURCE = BIN.parent / "backend_suite" / "project.py"
TARGET = BIN.parents[1] / "house-style" / "bin" / "resolve_role.py"
BEGIN = "# BEGIN GENERATED walk"
END = "# END GENERATED walk"


def walk_source() -> str:
    text = SOURCE.read_text()
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == "walk":
            return ast.get_source_segment(text, node)
    raise SystemExit(f"no walk() in {SOURCE} — refusing to generate an empty copy")


def expected_block() -> str:
    return (f"{BEGIN} — from backend-suite/backend_suite/project.py by\n"
            f"# backend-suite/bin/sync_house_style_walk.py. Do not hand-edit.\n"
            f"{walk_source()}\n{END}")


def render(current: str) -> str:
    start, stop = current.find(BEGIN), current.find(END)
    if start < 0 or stop < start:
        raise SystemExit(f"{TARGET} has no {BEGIN} ... {END} region — refusing to guess "
                         f"where the generated copy belongs")
    return current[:start] + expected_block() + current[stop + len(END):]


def main(argv: list[str]) -> int:
    current = TARGET.read_text()
    wanted = render(current)
    if "--check" in argv:
        if wanted != current:
            print(f"STALE: {TARGET.name}'s walk() differs from backend_suite.project.walk(). "
                  f"Run: python3 {Path(__file__).relative_to(BIN.parents[2])}")
            return 1
        print(f"current: {TARGET.name} walk() matches backend_suite.project")
        return 0
    if wanted != current:
        TARGET.write_text(wanted)
        print(f"regenerated walk() in {TARGET}")
    else:
        print("already current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
