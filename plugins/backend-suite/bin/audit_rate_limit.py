#!/usr/bin/env python3
"""Which endpoints limit inbound callers, and where that decision is written.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_rate_limit.py" [--out …] [--findings]

## Why this exists

A public API's rate-limit policy lives in middleware, and middleware is
easy to register globally, forget per-route, or remove in a refactor that
looked like cleanup. When it drifts, the API still serves — it just serves
 whoever asks fastest, and the first notice is the abuse report.

Measured on the first validation target (jikan-rest, Lumen, probed
2026-10-11): **105 of 105 route actions have no inbound rate limiting**.
The app's only rate-limit machinery faces the other direction — it maps
the upstream MyAnimeList `RateLimitException` for callers
(`Handler.php`) and sleeps between indexer fetches — and its docs state
the upstream's limits; nothing limits inbound requests at all. That is a
deliberate-looking openness the project may well intend, but it is not
_written as a decision anywhere this suite can see_, and this audit's job
is to make it one: either protection lands, or the accepted endpoints get
exempted with their reasons. Silence stays impossible.

## How protection is recognised — the project says

Two patterns, because protection is declared in two places and either
counts:

- `globalProtectionPattern` — a declaration that covers every route
  (a throttle in the framework's global middleware stack). Matched against
  the bootstrap/config files named in `globalProtectionFiles`.
- `protectionPattern` — a per-route marker (a `throttle:` middleware
  chained on the route or its group, a per-endpoint limiter attribute).
  Matched against the route's own declaration window — the route's lines
  plus `windowLines` after, which is where chained middleware appears in
  the routing style this was written against.

Neither pattern is this engine's guess: they are the project's spellings of
its own protection, in the architecture rules.

## What it refuses to do

Run with no patterns (protection cannot be recognised by a check that
would call everything unprotected or everything protected), with a routes
glob matching nothing, or with an exempt entry that carries no reason.
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

RULES = load(REPO, "rateLimit")

ENVELOPE = "rate-limit"


def _compiled(key: str, why: str) -> re.Pattern:
    pattern = RULES.get(key)
    if not pattern:
        raise Refused(f"rateLimit.{key} is not set — {why}",
                      audit="audit_rate_limit")
    try:
        return re.compile(pattern, re.S)
    except re.error as exc:
        raise Refused(f"rateLimit.{key} is not a valid regex: {exc}",
                      audit="audit_rate_limit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    action_re = _compiled(
        "actionPattern", "how a route spells its action (controller and "
                         "method captures)")
    protection_re = _compiled(
        "protectionPattern", "how a per-route limiter is declared here")
    global_re = _compiled(
        "globalProtectionPattern", "how a limit covering every route is "
                                   "declared (a throttle in the global "
                                   "middleware stack)")
    global_files = [REPO / g for g in (RULES.get("globalProtectionFiles") or [])]
    window_lines = int(RULES.get("windowLines") or 4)
    exempt = RULES.get("exempt") or {}
    for action, why in exempt.items():
        if not isinstance(why, str) or not why.strip():
            raise Refused(
                f"rateLimit.exempt[{action!r}] has no reason — an exemption "
                f"without a why is a finding nobody has to think about again.",
                audit="audit_rate_limit")

    routes_glob = RULES.get("routesGlob")
    if not routes_glob:
        raise Refused("rateLimit.routesGlob is not set",
                      audit="audit_rate_limit")
    route_files = sorted(REPO.glob(routes_glob))
    if not route_files:
        raise Refused(
            f"rateLimit.routesGlob ({routes_glob!r}) matched no files. An "
            f"empty sweep would report clean having checked nothing.",
            audit="audit_rate_limit")

    globally_protected = any(global_re.search(p.read_text())
                             for p in global_files if p.is_file())

    actions: dict[str, tuple[str, str, int]] = {}
    for path in route_files:
        rel = path.relative_to(REPO).as_posix()
        lines = path.read_text().splitlines()
        for line_no, line in enumerate(lines, 1):
            for match in action_re.finditer(line):
                actions.setdefault(
                    f"{match.group(1)}@{match.group(2)}",
                    (rel, line_no,
                     "\n".join(lines[line_no - 1:line_no - 1 + window_lines])))
    if not actions:
        raise Refused(
            "no route actions were extracted — the action pattern does not "
            "describe this routing table. Comparing nothing is not clean.",
            audit="audit_rate_limit")

    unprotected = []
    for action, (rel, line_no, window) in sorted(actions.items()):
        if globally_protected or protection_re.search(window):
            continue
        if action in exempt:
            continue
        unprotected.append((action, rel, line_no))

    records = [
        F.make(ENVELOPE, "unprotected_endpoint",
               f"{action} has no inbound rate limit (declared at "
               f"{rel}:{line_no}) — no global throttle protects it and its "
               f"declaration carries no limiter.",
               severity=F.SHOULD_FIX, file=rel, line=line_no)
        for action, rel, line_no in unprotected]

    # Exempt actions are covered, not clean: the envelope names them with
    # their reasons, so a decision never reads as an absence of findings.
    covered_exempt = {a: why for a, why in sorted(exempt.items())
                      if a in actions}

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"unprotected_endpoint": [a for a, _, _ in unprotected],
             "globally_protected": globally_protected,
             "exempt": covered_exempt}, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "rate-limit") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(route_files),
            suppressed=covered_exempt or None,
        )

    print(f"  route actions       {len(actions)}")
    print(f"  global throttle     {'yes' if globally_protected else 'none'}")
    if covered_exempt:
        print(f"  exempt (with why)   {len(covered_exempt)}: "
              f"{', '.join(covered_exempt)}")
    if not records:
        print(f"\naudit_rate_limit: every route action carries or inherits a "
              f"limit")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
