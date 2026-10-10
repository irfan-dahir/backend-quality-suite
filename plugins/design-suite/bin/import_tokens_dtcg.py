#!/usr/bin/env python3
"""Compare a DTCG `.tokens.json` against the tokens this project's code declares.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py"                    # file from profile tokens.dtcg.path
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py" --file design.tokens.json
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py" --json
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py" --write-report    # the only write

Reads a Design Tokens Format Module 2025.10 file (Final Community Group Report,
https://www.designtokens.org/tr/2025.10/format/) — e.g. a Figma variables
export, or a Tokens Studio / Style Dictionary file — and reports drift:

  missing_in_code   in the file, no matching token in code
  missing_in_file   in code, not in the file
  value_mismatch    both, different resolved value (or type)
  uncomparable      code token with no faithful DTCG form — not counted as a match
  ambiguous         two names on one side map to the same comparison key

Names match on a stack-neutral key (lower-case alphanumerics, `$root`
dropped): `color.primary` == `--color-primary` == `colorPrimary`. Values
compare after alias resolution on both sides; `rem` and `px` never compare
equal (no root font size is assumed).

Draft-era files (hex-string colours, "16px" strings, unprefixed `value`/`type`)
are refused unless `--accept-draft-forms` is passed.

**What it writes:** nothing by default (preview). `--write-report [PATH]`
writes one JSON report, default `.design-suite/dtcg-drift.json`. It never
writes to source or to the DTCG file.

Exit codes: 0 no drift · 1 drift (or uncomparable tokens) listed · 2 refused —
unreadable/invalid/unsupported DTCG input, or code tokens unreadable, named.
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

DEFAULT_REPORT = ".design-suite/dtcg-drift.json"
KINDS = ("missing_in_code", "missing_in_file", "value_mismatch", "uncomparable", "ambiguous")


def drift(file_tokens: dict, converted) -> dict:
    out = {k: [] for k in KINDS}
    fside: dict = {}
    for t in file_tokens.values():
        fside.setdefault(dtcg.name_key(t.path), []).append(t)
    cside: dict = {}
    for c in converted:
        cside.setdefault(dtcg.name_key(c.path), []).append(c)

    for key, ts in sorted(fside.items()):
        if len(ts) > 1:
            out["ambiguous"].append({"side": "file", "key": key,
                                     "names": [t.dotted for t in ts]})
    for key, cs in sorted(cside.items()):
        if len(cs) > 1:
            out["ambiguous"].append({"side": "code", "key": key,
                                     "names": [c.decl.name for c in cs]})
    for key in sorted(set(fside) | set(cside)):
        ts, cs = fside.get(key, []), cside.get(key, [])
        if len(ts) > 1 or len(cs) > 1:
            continue
        if not cs:
            out["missing_in_code"].append({"token": ts[0].dotted, "type": ts[0].type})
            continue
        c = cs[0]
        if c.reason is not None:
            out["uncomparable"].append({"name": c.decl.name, "file": c.decl.file,
                                        "raw": c.decl.raw, "reason": c.reason,
                                        "in_file": bool(ts)})
            continue
        if not ts:
            out["missing_in_file"].append({"name": c.decl.name, "file": c.decl.file,
                                           "type": c.type})
            continue
        t = ts[0]
        a, b = dtcg.canonical(t.type, t.resolved), dtcg.canonical(c.type, c.value)
        if a != b:
            out["value_mismatch"].append({
                "token": t.dotted, "name": c.decl.name, "file": c.decl.file,
                "file_type": t.type, "code_type": c.type,
                "file_value": t.resolved, "code_value": c.value, "code_raw": c.decl.raw})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--file", help="DTCG file (default: the profile's tokens.dtcg.path)")
    p.add_argument("--accept-draft-forms", action="store_true",
                   help="normalise pre-2025.10 draft forms instead of refusing them")
    p.add_argument("--json", action="store_true", help="print the drift report as JSON")
    p.add_argument("--write-report", nargs="?", const=DEFAULT_REPORT, default=None,
                   help=f"write the report (default path {DEFAULT_REPORT}); the only write")
    args = p.parse_args()

    adapter, ctx, _ = for_project(REPO)
    rel = args.file or (((ctx.profile.get("tokens") or {}).get("dtcg") or {}).get("path"))
    if not rel:
        print("REFUSED: no DTCG file — pass --file or set tokens.dtcg.path in "
              ".design-suite/profile.json. INERT, not clean.", file=sys.stderr)
        return 2
    try:
        file_tokens = dtcg.load(REPO / rel, legacy=args.accept_draft_forms)
    except dtcg.DtcgError as exc:
        print(f"REFUSED: {rel} is not a DTCG {dtcg.SPEC_VERSION} file this reader "
              f"accepts — {exc}", file=sys.stderr)
        return 2
    if not file_tokens:
        print(f"REFUSED: {rel} declares no tokens; zero drift against an empty file "
              f"would be meaningless.", file=sys.stderr)
        return 2
    try:
        converted = C.read(ctx, adapter.NAME)
    except CapabilityError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if not converted:
        print("REFUSED: the code's token source declares no tokens this reader "
              "recognises.", file=sys.stderr)
        return 2

    report = {"spec": dtcg.SPEC_URL, "file": rel, "file_tokens": len(file_tokens),
              "code_tokens": len(converted), **drift(file_tokens, converted)}
    total = sum(len(report[k]) for k in KINDS)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"DTCG drift: {rel} ({len(file_tokens)} tokens) vs code "
              f"({len(converted)} declarations)")
        for k in KINDS:
            print(f"  {k}: {len(report[k])}")
            for item in report[k]:
                print(f"    {json.dumps(item, default=str)}")
    if args.write_report:
        out = REPO / args.write_report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(f"wrote {args.write_report}", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
