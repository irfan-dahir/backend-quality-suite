#!/usr/bin/env python3
"""A doc template must not carry guidance for an archetype its role is `na` for.

Issue #95 found `DESIGN.md.template` app-shaped. Two fixes then landed at once
and contradicted each other: `roles.json` marked `design` as `na` for
`design-system` and `docs-site` (so `scaffold_doc.py` refuses to write it
there), while the template grew per-archetype rows telling a design-system
package how to fill it in. That guidance was unreachable, and it re-stated the
very conflation #95 measured — the visual system, the component pages and the
token reference folded into one file. Nothing compared the two, so nothing
noticed.

Templates branch on archetype with table rows that open with a fixed phrase per
kind. This test reads those rows and checks each against the role's declared
applicability. The control: the two templates that legitimately branch on
every archetype (entry-point, documentation-rules) must still be *found*
branching — otherwise a phrase change would make this test pass vacuously.

    python3 plugins/design-suite/bin/template_archetypes_test.py

Exit 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "templates" / "docs"

# The row openers templates use for each archetype. Keep in step with the
# templates; the control below fails if they drift apart.
ROW_OPENERS = {
    "library": "| A published package (library) |",
    "service": "| A deployed API or data service |",
}

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def branches(template: Path) -> set[str]:
    lines = template.read_text().splitlines()
    return {kind for kind, opener in ROW_OPENERS.items()
            if any(line.startswith(opener) for line in lines)}


def main() -> int:
    spec = json.loads((DOCS / "roles.json").read_text())
    roles = {k: v for k, v in spec["roles"].items() if not k.startswith("_")}

    seen: dict[str, set[str]] = {}
    for role, entry in roles.items():
        for key in ("template", "pageTemplate"):
            name = entry.get(key)
            if not name:
                continue
            found = branches(DOCS / name)
            seen[role] = seen.get(role, set()) | found
            for kind in sorted(found):
                expect(entry["archetypes"].get(kind) != "na",
                       f"{name}: carries {kind!r} guidance, and role {role!r} applies to {kind!r}")

    print("\ncontrol — the branching detector still sees the templates that branch:")
    for role in ("entry-point", "documentation-rules"):
        expect(seen.get(role) == set(ROW_OPENERS),
               f"{role}: all archetype rows detected (got {sorted(seen.get(role, set()))})")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("template archetype guidance agrees with roles.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
