#!/usr/bin/env python3
"""Export this project's declared design tokens as a DTCG `.tokens.json`.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/export_tokens_dtcg.py"                 # preview to stdout
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/export_tokens_dtcg.py" --out design.tokens.json

Format: W3C Design Tokens Community Group, Design Tokens Format Module 2025.10
(Final Community Group Report — stable, not a W3C Recommendation),
https://www.designtokens.org/tr/2025.10/format/ . Style Dictionary v4+ reads
this format natively.

**What it writes:** nothing unless `--out` is given; then exactly that one
file (and `--report`, if given). It never edits a source file.

Tokens come from the profile's `tokens.source`, read per `adapters.lang`
(see `design_suite/engine/code_tokens.py` for what each stack can say).
A declaration that has no faithful DTCG form is **not dropped**: it is listed
on stderr, in `--report`, and in the exported file's root
`$extensions["io.github.irfan-dahir.design-suite"].unrepresentable`.

Exit codes (DOC-ROLES.md audit contract):
  0  every declared token exported
  1  exported, but some declarations are unrepresentable (listed)
  2  could not read the tokens at all, or no tokens found — refused, named
"""
from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import project_root  # noqa: E402

REPO = project_root()

from design_suite.adapters import for_project                 # noqa: E402
from design_suite.adapters.base import CapabilityError        # noqa: E402
from design_suite.engine import code_tokens as C              # noqa: E402
from design_suite.engine import dtcg                          # noqa: E402


def export(converted):
    """(document, unrepresentable list, notes list)."""
    taken: dict = {}
    ok, bad = [], []
    for c in converted:
        if c.reason is None and c.path in taken:
            c.reason = f"its DTCG path {'.'.join(c.path)} collides with {taken[c.path]}"
        if c.reason is not None:
            bad.append({"name": c.decl.name, "file": c.decl.file, "raw": c.decl.raw,
                        "reason": c.reason})
            continue
        taken[c.path] = c.decl.name
        ok.append(c)
    all_paths = {c.path for c in ok}
    by = {c.decl.name: c for c in ok}
    entries, notes = [], []
    for c in ok:
        ext = {"name": c.decl.name}
        if c.note:
            ext["note"] = c.note
            notes.append({"name": c.decl.name, "note": c.note})
        if c.alias is not None:
            if c.alias not in by:
                bad.append({"name": c.decl.name, "file": c.decl.file, "raw": c.decl.raw,
                            "reason": f"aliases {c.alias}, which was not exported"})
                continue
            value = dtcg.alias_ref(by[c.alias].path, all_paths)
        else:
            value = c.value
        entries.append((c.path, c.type, value, None, {C.EXT: ext}))
    doc = dtcg.build(entries)
    doc["$extensions"] = {C.EXT: {
        "spec": dtcg.SPEC_URL,
        "unrepresentable": [b["name"] for b in bad],
    }}
    return doc, bad, notes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", help="write the .tokens.json here (default: print, write nothing)")
    p.add_argument("--report", help="also write a JSON report of what was and was not exported")
    args = p.parse_args()

    adapter, ctx, _ = for_project(REPO)
    try:
        converted = C.read(ctx, adapter.NAME)
    except CapabilityError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if not converted:
        print("REFUSED: the token source declares no tokens this reader recognises. "
              "An empty export would be indistinguishable from a project with no "
              "tokens, so nothing is written.", file=sys.stderr)
        return 2

    doc, bad, notes = export(converted)
    try:
        dtcg.parse(json.loads(json.dumps(doc)))  # the exporter must read its own output
    except dtcg.DtcgError as exc:
        print(f"REFUSED: generated document fails validation ({exc}) — an exporter bug",
              file=sys.stderr)
        return 2

    text = json.dumps(doc, indent=2) + "\n"
    exported = len(converted) - len(bad)
    if args.out:
        out = REPO / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"wrote {args.out}: {exported} token(s), DTCG {dtcg.SPEC_VERSION}", file=sys.stderr)
    else:
        sys.stdout.write(text)
        print(f"preview only — {exported} token(s); pass --out to write", file=sys.stderr)
    if args.report:
        (REPO / args.report).write_text(json.dumps(
            {"spec": dtcg.SPEC_URL, "exported": exported, "unrepresentable": bad,
             "mapped_with_note": notes}, indent=2) + "\n")
    for n in notes:
        print(f"  note: {n['name']}: {n['note']}", file=sys.stderr)
    if bad:
        print(f"{len(bad)} declaration(s) NOT exported — no faithful DTCG form:", file=sys.stderr)
        for b in bad:
            print(f"  {b['file']}: {b['name']} = {b['raw']}  ({b['reason']})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
