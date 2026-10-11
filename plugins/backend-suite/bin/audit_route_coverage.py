#!/usr/bin/env python3
"""A declared route whose action no longer exists is a request-time fatal.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_route_coverage.py" [--out …] [--findings]

## Why this exists

Route tables declare their handlers by name (`'uses' => 'Ctrl@method'`), and
nothing checks that the name still resolves until a caller hits the route.
The controller rename that looked local — method extracted, class moved into
a versioned subdirectory, action string left behind — turns into a 500 on
the one endpoint the change forgot, discovered by users rather than by CI.

Measured on the first validation target (jikan-rest, Lumen, probed
2026-10-11): 103 unique route actions in `routes/web.v4.php`, every one
resolving to a method on a controller file under the `V4DB` namespace — the
clean direction measured honestly, which is what makes this audit worth
keeping as regression detection rather than deleting for having nothing to
report. The defect class is real in this stack: the same project's TTL map
still carries four entries (`GenreController@mainAnime`,
`MagazineController@resource`, `PersonController@seiyuu`, …) naming
endpoints whose routes were already deleted — proof that action names out
live their targets here.

Routes whose handler is a closure (no `uses` string) are not this audit's
subject: they have no name to resolve, so they cannot dangle by renaming.
They are counted in the summary, so a sweep over a closure-only routes file
reads as what it is rather than as an empty comparison.

## What it refuses to do

Report clean on an empty sweep: a routes glob that matches nothing, or an
action pattern that extracts nothing, exits 2 with the reason.
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

RULES = load(REPO, "routeCoverage")

ENVELOPE = "route-coverage"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    pattern = RULES.get("actionPattern")
    if not pattern:
        raise Refused(
            "routeCoverage.actionPattern is not set — how a route spells its "
            "action, with controller and method captures",
            audit="audit_route_coverage")
    try:
        action_re = re.compile(pattern)
    except re.error as exc:
        raise Refused(f"routeCoverage.actionPattern is not a valid regex: "
                      f"{exc}", audit="audit_route_coverage")
    controller_dirs = [REPO / d for d in (RULES.get("controllerDirs") or [])]
    if not controller_dirs:
        raise Refused("routeCoverage.controllerDirs is empty — where a "
                      "Controller class file is found",
                      audit="audit_route_coverage")

    routes_glob = RULES.get("routesGlob")
    if not routes_glob:
        raise Refused("routeCoverage.routesGlob is not set",
                      audit="audit_route_coverage")
    route_files = sorted(REPO.glob(routes_glob))
    if not route_files:
        raise Refused(
            f"routeCoverage.routesGlob ({routes_glob!r}) matched no files. "
            f"An empty sweep would report clean having resolved nothing.",
            audit="audit_route_coverage")

    actions: dict[str, tuple[str, str, str, int]] = {}
    router_calls = 0
    action_instances = 0
    for path in route_files:
        rel = path.relative_to(REPO).as_posix()
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            router_calls += len(re.findall(
                r"\$router->(?:get|post|put|patch|delete|any)\s*\(", line))
            for match in action_re.finditer(line):
                controller, method = match.group(1), match.group(2)
                actions.setdefault(f"{controller}@{method}",
                                   (controller, method, rel, line_no))
                action_instances += 1
    # A router call with no action string is a closure handler: no name to
    # resolve, so nothing for this audit to check — but counted, so the
    # summary cannot read as a sweep that saw nothing.
    closure_routes = max(0, router_calls - action_instances)
    if not actions:
        raise Refused(
            "no route actions were extracted — either every handler here is "
            "a closure (nothing for this audit to resolve) or the action "
            "pattern does not describe this routing table. Comparing nothing "
            "is not clean; for a closure-only API this audit has no subject "
            "and should not be wired into CI.", audit="audit_route_coverage")

    declared: dict[str, set[str]] = {}
    records = []
    for action, (controller, method, rel, line_no) in sorted(actions.items()):
        if controller not in declared:
            source = next(
                (d / f"{controller}.php" for d in controller_dirs
                 if (d / f"{controller}.php").is_file()), None)
            if source is None:
                records.append(F.make(
                    ENVELOPE, "dead_route",
                    f"{action} is declared at {rel}:{line_no} but no "
                    f"{controller}.php exists in "
                    f"{RULES['controllerDirs']!r} — this route 500s on every "
                    f"request.", severity=F.CRITICAL, file=rel, line=line_no))
                declared[controller] = set()
                continue
            declared[controller] = set(
                re.findall(r"function\s+&?\s*(\w+)\s*\(",
                           source.read_text()))
        if method not in declared[controller]:
            records.append(F.make(
                ENVELOPE, "dead_route",
                f"{action} is declared at {rel}:{line_no} but "
                f"{controller}.php declares no function {method}() — this "
                f"route 500s on every request.",
                severity=F.CRITICAL, file=rel, line=line_no))

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"dead_route": sorted(r["summary"].split(" ")[0] for r in records)},
            indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "route-coverage") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(route_files) + len(declared),
        )

    print(f"  route actions       {len(actions)}")
    print(f"  controllers read    {len(declared)}")
    if closure_routes:
        print(f"  closure handlers    {closure_routes} "
              f"(no action name — not resolvable, not reportable)")
    if not records:
        print(f"\naudit_route_coverage: every declared action resolves to a "
              f"controller method")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
