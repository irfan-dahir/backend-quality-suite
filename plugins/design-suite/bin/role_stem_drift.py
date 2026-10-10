#!/usr/bin/env python3
"""Report where a hand-maintained stem->role table has drifted from the vocabulary.

    python3 plugins/design-suite/bin/role_stem_drift.py

Exit 0 = the hand table proposes every role the vocabulary declares and no role
it does not. Exit 1 = drift, itemised. Exit 2 = could not look — the table could
not be located or parsed, which is not a pass.

## Why this is a reporter and not a fix

The fix is `design_suite/engine/role_stems.py`: derive the map from
`templates/docs/roles.json` instead of keeping a second copy beside it. Once
`survey.py` calls `role_stems.role_for_stem()`, this script reports nothing
forever, because the drift it measures becomes unrepresentable.

Until that one-line swap lands, this exists so the drift is *loud*. The failure
mode being fixed is a survey that proposes no role for a document whose filename
is a role name, and then reports a coverage number as though it had looked —
this repo's governing principle, in the surface that bootstraps every new
project. A gap nobody can see is the whole bug; a gap with an exit code is work.

## How it reads the table

By AST, not by import. `survey.py` is a CLI with import-time side effects and an
owner, and a drift reporter that executes the thing it is auditing is one
refactor away from being the reason a gate cannot run. Parsing the literal also
means this keeps working if the table moves, as long as the name survives.

Stdlib only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import project_root  # noqa: F401,E402  (puts the plugin on sys.path)

from design_suite.engine import role_stems  # noqa: E402

BIN = Path(__file__).resolve().parent
TABLE_NAME = "ROLE_BY_STEM"
DEFAULT_SOURCE = BIN / "survey.py"


def hand_table(source: Path) -> dict[str, tuple]:
    """The literal `ROLE_BY_STEM` dict out of a source file.

    Raises LookupError rather than returning `{}`. An empty table and a table
    this function failed to find look identical to every caller downstream, and
    "found nothing" reported as "nothing to report" is the exact bug.
    """
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise LookupError(f"cannot parse {source}: {exc}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if TABLE_NAME not in names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError as exc:
            raise LookupError(f"{TABLE_NAME} in {source} is not a literal: {exc}") from exc
        if not isinstance(value, dict) or not value:
            raise LookupError(f"{TABLE_NAME} in {source} is empty or not a dict")
        return value
    raise LookupError(f"no {TABLE_NAME} assignment in {source}")


def report(table: dict[str, tuple], label: str) -> int:
    missing = role_stems.unreachable_roles(table)
    retired = role_stems.retired_roles(table)
    derived = role_stems.stem_map()

    print(f"role stems: {label}")
    print(f"  {len(table)} stem(s) proposing "
          f"{len({e[0] for e in table.values()})} distinct role(s)")
    print(f"  derived map: {len(derived)} stem(s) proposing "
          f"{len({e[0] for e in derived.values()})} distinct role(s)")

    if not missing and not retired:
        print("  no drift: every declared role is reachable, and no stem names a "
              "role the vocabulary has retired.")
        return 0

    if missing:
        print(f"\n  ✗ {len(missing)} declared role(s) NO stem can propose — a "
              f"document named after one of these is surveyed as unmapped:",
              file=sys.stderr)
        for role in missing:
            print(f"      {role}", file=sys.stderr)
    if retired:
        print(f"\n  ✗ {len(retired)} stem(s) propose a role the vocabulary no "
              f"longer declares — resolve.py would exit 2 on these:", file=sys.stderr)
        for stem, role in retired:
            print(f"      {stem} -> {role}", file=sys.stderr)
    print(f"\n  Fix: call design_suite.engine.role_stems.role_for_stem() instead of "
          f"maintaining {TABLE_NAME}. A derived map cannot drift.", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    source = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_SOURCE
    try:
        table = hand_table(source)
    except LookupError as exc:
        # Exit 2, per the audit exit-code contract in docs/DOC-ROLES.md: this is
        # "I could not look", and it must never be baselined as a clean run.
        print(f"role stems: could not read the table — {exc}", file=sys.stderr)
        return 2
    try:
        rel = source.relative_to(Path(__file__).resolve().parents[3])
    except ValueError:
        rel = source
    return report(table, str(rel))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
