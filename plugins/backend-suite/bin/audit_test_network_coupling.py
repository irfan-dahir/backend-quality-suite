#!/usr/bin/env python3
"""Tests that can reach a live service — directly, or through a silent fallback.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_test_network_coupling.py" [--out …] [--findings]

## Why this exists

A hermetic test suite is one whose recordings are always present; a suite
that silently fetches when a recording is missing is an offline-looking
suite with a network in it. Two shapes produce that:

1. **A test constructing a real client** — the URL is live and nothing
   intercepts it. CI runs it as-is: green when the service is up, red when
   it is not, and flaky in whatever way the upstream feels like today.
2. **A recording-backed client with a live fallback** — requests are
   served from fixtures until one recording is absent, at which point the
   request goes out for real, gets written to the fixture store, and the
   suite passes. Nobody is told the run touched the network.

Measured on the first validation target (jikan, the PHP parser library,
probed 2026-10-11): **0 of 41** host-referencing test files construct a
live client — the suite's `TestCase` injects a `MockHttpClient` over
`HttpFilesystemCacheClientCallback`, and the `myanimelist.net` URLs inside
tests are recorded request URLs, not live calls. The measured coupling is
shape 2, and it is exactly as described: the callback builds a **real
Symfony client when none is injected** (`$httpClient ??
HttpClient::create()`, and `TestCase` never injects one), and its invoke
method fetches live whenever the fixture file for a request hash is
missing. `composer link-fixtures` clones the recordings so the miss path
never fires in CI — a fresh checkout that skips that script runs the whole
suite live while it looks offline.

Both shapes are findings here for the same reason: hermeticity that
depends on remembering a setup step is a decision, and decisions get
exempted with a reason (`exempt` in the config) rather than assumed.

## What the check claims

The mock markers (`mockClientPattern`) are the project's own spellings of
"this file's requests are recorded". A host-referencing file carrying one
is counted as recorded and named in the summary — documented-clean, not
green: the count says how much of the suite depends on that claim.
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

RULES = load(REPO, "testNetworkCoupling")

ENVELOPE = "test-network-coupling"


def _compiled(key: str, why: str) -> re.Pattern:
    pattern = RULES.get(key)
    if not pattern:
        raise Refused(f"testNetworkCoupling.{key} is not set — {why}",
                      audit="audit_test_network_coupling")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise Refused(f"testNetworkCoupling.{key} is not a valid regex: {exc}",
                      audit="audit_test_network_coupling")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    host_re = _compiled("liveHostPattern", "the live host(s) tests must not "
                                           "reach on their own")
    mock_re = _compiled("mockClientPattern",
                        "the markers that prove a file's requests are "
                        "recorded (MockHttpClient, a cache callback, "
                        "extending the recorded TestCase)")
    fallback_re = _compiled(
        "fallbackPattern",
        "the construction that CAN go live when a recording is absent (e.g. "
        "HttpClient::create)")
    exempt = RULES.get("exempt") or {}
    for name, why in exempt.items():
        if not isinstance(why, str) or not why.strip():
            raise Refused(
                f"testNetworkCoupling.exempt[{name!r}] has no reason — an "
                f"exemption without a why is a finding nobody has to think "
                f"about again.", audit="audit_test_network_coupling")

    tests_glob = RULES.get("testsGlob")
    if not tests_glob:
        raise Refused("testNetworkCoupling.testsGlob is not set",
                      audit="audit_test_network_coupling")
    tests = sorted(REPO.glob(tests_glob))
    if not tests:
        raise Refused(
            f"testNetworkCoupling.testsGlob ({tests_glob!r}) matched no "
            f"files. An empty sweep would report clean having checked "
            f"nothing.", audit="audit_test_network_coupling")

    records = []
    host_referencing = 0
    recorded = 0
    for path in tests:
        rel = path.relative_to(REPO).as_posix()
        source = path.read_text()
        mentions_host = bool(host_re.search(source))
        has_fallback = fallback_re.search(source)
        if has_fallback and rel not in exempt:
            line_no = source[:has_fallback.start()].count("\n") + 1
            records.append(F.make(
                ENVELOPE, "network_fallback",
                f"{rel}:{line_no} constructs a real HTTP client — requests "
                f"go live whenever a recording is absent, and the run looks "
                f"offline while it happens.",
                severity=F.FYI, file=rel, line=line_no))
        if not mentions_host:
            continue
        host_referencing += 1
        if mock_re.search(source):
            recorded += 1
            continue
        if rel in exempt:
            recorded += 1
            continue
        records.append(F.make(
            ENVELOPE, "live_network_test",
            f"{rel} references a live host with no recorded-client marker — "
            f"this test talks to the service as written.",
            severity=F.SHOULD_FIX, file=rel))

    covered_exempt = {n: why for n, why in sorted(exempt.items())}

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"live_network_test": sorted(
                r["file"] for r in records
                if r["category"] == "live_network_test"),
             "network_fallback": sorted(
                 r["file"] for r in records
                 if r["category"] == "network_fallback"),
             "recorded_host_references": recorded}, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "test-network-coupling") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(tests),
            suppressed=covered_exempt or None,
        )

    print(f"  test files          {len(tests)}")
    print(f"  reference a host    {host_referencing} "
          f"({recorded} through recorded clients)")
    if covered_exempt:
        print(f"  exempt (with why)   {len(covered_exempt)}: "
              f"{', '.join(covered_exempt)}")
    if not records:
        print(f"\naudit_test_network_coupling: no test reaches the live "
              f"service and no fallback can")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
