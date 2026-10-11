#!/usr/bin/env python3
"""The error envelope is the API's most-read contract; keep it true.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_shape.py" [--out …] [--findings]

## Why this exists

Callers branch on error payloads — the `type` a client switches on, the
`status` it maps to a screen, the `message` it shows verbatim. Two things
break that contract without failing a build:

1. **A response authored outside the envelope's author.** When the
   exception handler is the single place the envelope is written, a
   controller that answers `response()->json([...], 500)` directly ships an
   error shape no client switch covers. Nothing flags it: the response
   renders, the test asserting status 500 passes, and the caller's
   `error.type` read silently returns nothing.
2. **An envelope key removed from the author.** Refactors that restructure
   the handler drop keys the docs and clients still promise.

Measured on the first validation target (jikan-rest, Lumen, probed
2026-10-11): `app/Exceptions/Handler.php` authors 13 error branches and
every one carries `status`, `type`, `error` and `message` (`report_url` is
conditionally present and declared optional). The bypass direction found
real drift on the first probe: `InsightsController` answers with a
**hand-copied envelope** — `{'status': 403, 'type':
'InsightsRuntimeException', 'message': …}` — three times over, so any
change to the Handler's shape leaves those responses behind as silent
drift; and `app/Support/DefaultMediator.php` returns `{'message': …}, 500`
with **no** `status`, `type` or `error` at all, where a caller branching on
`error.type` gets nothing. `abort()` calls exist in this app and are NOT
bypasses: they throw, and the handler shapes them.

## What the check claims, precisely

The envelope-key check is **string-level**: a key present anywhere in the
handler file counts. It sees a key deleted from the file; it cannot see a
key dropped from one branch of thirteen — that needs a PHP parser this
audit deliberately does not have. Stated as a net, not a proof.

The bypass check is pattern-level and the pattern is the project's
(`errorShape.bypassPattern`): how a direct error response is spelled in
THIS stack. A pattern that matches nothing and a codebase with no bypasses
produce the same output, so the pattern's truth is the team's to hold —
the audit's job is to apply it everywhere consistently.

## What it refuses to do

Run with no envelope keys (a contract with no declared keys would check
nothing), with a handler glob matching nothing (the envelope's author must
exist to be compared against), or with a source glob matching nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from backend_suite.engine import findings as F  # noqa: E402
from backend_suite.engine.arch import load  # noqa: E402
from backend_suite.engine.refusal import Refused  # noqa: E402

RULES = load(REPO, "errorShape")

ENVELOPE = "error-shape"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    keys = RULES.get("envelopeKeys") or []
    if not keys:
        raise Refused(
            "errorShape.envelopeKeys is empty — the keys every error response "
            "promises (e.g. status, type, message, error). With none, the "
            "contract this audit guards is not stated anywhere.",
            audit="audit_error_shape")

    handler_glob = RULES.get("handlerGlob")
    if not handler_glob:
        raise Refused("errorShape.handlerGlob is not set — where the error "
                      "envelope is authored", audit="audit_error_shape")
    handlers = sorted(REPO.glob(handler_glob))
    if not handlers:
        raise Refused(
            f"errorShape.handlerGlob ({handler_glob!r}) matched no files — "
            f"the envelope's author is gone, and there is nothing to compare "
            f"responses against.", audit="audit_error_shape")

    source_glob = RULES.get("sourceGlob")
    if not source_glob:
        raise Refused("errorShape.sourceGlob is not set — where error "
                      "responses could be authored directly",
                      audit="audit_error_shape")
    sources = [p for p in sorted(REPO.glob(source_glob))
               if p not in handlers]
    if not sources:
        raise Refused(
            f"errorShape.sourceGlob ({source_glob!r}) matched no files "
            f"outside the handler. An empty sweep would report clean having "
            f"checked nothing.", audit="audit_error_shape")

    pattern = RULES.get("bypassPattern")
    if not pattern:
        raise Refused(
            "errorShape.bypassPattern is not set — how THIS stack spells a "
            "direct error-status response (the pattern is the project's "
            "convention, not this engine's guess).",
            audit="audit_error_shape")
    try:
        bypass_re = re.compile(pattern, re.S)
    except re.error as exc:
        raise Refused(f"errorShape.bypassPattern is not a valid regex: {exc}",
                      audit="audit_error_shape")

    handler_text = "\n".join(h.read_text() for h in handlers)
    missing_keys = [k for k in keys if k not in handler_text]

    records = []
    for key in missing_keys:
        records.append(F.make(
            ENVELOPE, "envelope_key_missing",
            f"the declared envelope key {key!r} appears nowhere in "
            f"{handler_glob} — every documented error response promises it, "
            f"and the author no longer writes it.",
            severity=F.SHOULD_FIX, file=handlers[0].relative_to(REPO).as_posix()))

    for path in sources:
        rel = path.relative_to(REPO).as_posix()
        for match in bypass_re.finditer(path.read_text()):
            line_no = path.read_text()[:match.start()].count("\n") + 1
            records.append(F.make(
                ENVELOPE, "error_shape_bypass",
                f"{rel}:{line_no} authors an error-status response directly, "
                f"outside {handler_glob} — callers branching on the envelope "
                f"({', '.join(keys)}) will not see its shape.",
                severity=F.CRITICAL, file=rel, line=line_no))

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"envelope_key_missing": missing_keys,
             "error_shape_bypass": sorted(
                 r["file"] for r in records
                 if r["category"] == "error_shape_bypass")},
            indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "error-shape") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(handlers) + len(sources),
        )

    print(f"  envelope keys       {', '.join(keys)}")
    print(f"  handler files       {len(handlers)}")
    print(f"  sources swept       {len(sources)}")
    if not records:
        print(f"\naudit_error_shape: the envelope carries every declared key "
              f"and no response bypasses it")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
