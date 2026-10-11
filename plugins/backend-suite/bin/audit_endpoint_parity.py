#!/usr/bin/env python3
"""Every served endpoint is documented, and every documented endpoint is served.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_endpoint_parity.py" [--out …] [--findings]

## Why this exists

An OpenAPI spec generated from source annotations is only as true as the
join between the routing table and the annotated methods. Both sides drift
without failing: a route added with a controller method that never got its
annotation is served to callers and absent from the spec every client reads;
an annotated method whose route was removed keeps a phantom path in the
docs that 404s.

Measured on the first validation target (jikan-rest, probed 2026-10-11):
105 route actions in `routes/web.v4.php`, 100 of them carrying an
`@OA\Get(...)` docblock above the controller method (swagger-lume generates
`storage/api-docs/api-docs.json` from exactly those annotations — 100 paths
in the spec, matching). **Three served endpoints are undocumented**:
`InsightsController@main`, `InsightsController@trends`, and
`UserController@recentlyOnline` — real routes callers hit, invisible in the
documented contract. The reverse direction — annotated methods no route
uses — measured clean here, and the check stays because it is the direction
that rots when a route is renamed.

This audit compares at the **action** level (`Controller@method`), not by
reconstructing full URLs out of nested route groups: the action is the
stable join both sides already share — the routes declare it, the
controller method is where any annotation lives. Path-shape parity inside
the annotations is a different question and is not claimed here.

## What it refuses to do

- Run without `docMarkers` — a marker list that cannot match would report
  every endpoint undocumented, which is noise wearing a finding's clothes.
- Resolve an action whose controller file is absent from `controllerDirs`.
  That route is dead in a way this audit cannot describe; `route coverage`
  owns that defect, and guessing here would misfile it.
- Report clean on an empty sweep (no actions extracted).
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

RULES = load(REPO, "endpointParity")

ENVELOPE = "endpoint-parity"

# A docblock and the method it sits on, without letting the comment run past
# its own terminator into the next one: `(?:(?!\*/).)*` cannot cross `*/`, so
# a file header that merely mentions the marker never documents the method
# below it. Modifiers (`public`, `static`, `final`, `&`) sit between.
_ADJACENT = re.compile(
    r"/\*\*((?:(?!\*/).)*)\*/\s*(?:\w+\s+)*function\s+&?\s*(\w+)\s*\(",
    re.S)


def _glob(key: str, why: str) -> list[Path]:
    pattern = RULES.get(key)
    if not pattern:
        raise Refused(f"endpointParity.{key} is not set — {why}",
                      audit="audit_endpoint_parity")
    found = sorted(REPO.glob(pattern))
    if not found:
        raise Refused(
            f"endpointParity.{key} ({pattern!r}) matched no files — {why}. "
            f"An empty sweep would report clean having compared nothing.",
            audit="audit_endpoint_parity")
    return found


def _methods(path: Path) -> tuple[dict[str, bool], set[str]]:
    """(method -> carries a marker in its own adjacent docblock, all methods).

    Two scans because they answer different questions: adjacency finds what is
    documented; the plain declaration scan finds what EXISTS. A method with no
    docblock at all is undocumented, not dead — conflating the two would file
    a doc gap as a dead route.
    """
    source = path.read_text()
    documented: dict[str, bool] = {}
    for docblock, method in _ADJACENT.findall(source):
        documented.setdefault(
            method, any(m in docblock for m in RULES["docMarkers"]))
    declared = set(re.findall(r"function\s+&?\s*(\w+)\s*\(", source))
    return documented, declared


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    markers = RULES.get("docMarkers") or []
    if not markers:
        raise Refused(
            "endpointParity.docMarkers is empty — the strings that mark a "
            "method as documented (e.g. '@OA\\\\Get'). With none, every "
            "endpoint would read undocumented; refusing to generate that "
            "noise.", audit="audit_endpoint_parity")
    if not RULES.get("actionPattern"):
        raise Refused("endpointParity.actionPattern is not set — how a route "
                      "spells its action (controller and method captures)",
                      audit="audit_endpoint_parity")
    try:
        action_re = re.compile(RULES["actionPattern"])
    except re.error as exc:
        raise Refused(f"endpointParity.actionPattern is not a valid regex: "
                      f"{exc}", audit="audit_endpoint_parity")
    controller_dirs = [REPO / d for d in (RULES.get("controllerDirs") or [])]
    if not controller_dirs:
        raise Refused("endpointParity.controllerDirs is empty — where a "
                      "Controller class file is found",
                      audit="audit_endpoint_parity")

    route_files = _glob("routesGlob", "the routes to check cannot be found")
    actions: dict[str, tuple[str, str, str, int]] = {}
    for path in route_files:
        rel = path.relative_to(REPO).as_posix()
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            for match in action_re.finditer(line):
                controller, method = match.group(1), match.group(2)
                actions.setdefault(f"{controller}@{method}",
                                   (controller, method, rel, line_no))
    if not actions:
        raise Refused(
            "no route actions were extracted — the action pattern does not "
            "describe this routing table. Comparing nothing is not clean.",
            audit="audit_endpoint_parity")

    # Resolve each controller once: (documented map, all declared methods).
    per_controller: dict[str, tuple[dict[str, bool], set[str]]] = {}
    records = []
    for action, (controller, method, rel, line_no) in sorted(actions.items()):
        if controller not in per_controller:
            candidates = [d / f"{controller}.php" for d in controller_dirs]
            resolved = next((c for c in candidates if c.is_file()), None)
            if resolved is None:
                raise Refused(
                    f"{action} ({rel}:{line_no}) names controller "
                    f"{controller}, which exists in none of "
                    f"{RULES['controllerDirs']!r}. Route coverage owns dead "
                    f"routes; refusing to guess its documentation state.",
                    audit="audit_endpoint_parity")
            per_controller[controller] = _methods(resolved)
        documented, declared = per_controller[controller]
        if method not in declared:
            raise Refused(
                f"{action} ({rel}:{line_no}): {controller}.php declares no "
                f"function {method}() — the route is dead or renamed; route "
                f"coverage reports that defect, this audit refuses to call "
                f"it undocumented.", audit="audit_endpoint_parity")
        if not documented.get(method, False):
            records.append(F.make(
                ENVELOPE, "undocumented_endpoint",
                f"{action} is served (routes declared at {rel}:{line_no}) "
                f"but {controller}.{method}() carries no "
                f"{'/'.join(markers)} docblock — absent from the generated "
                f"API contract.",
                severity=F.SHOULD_FIX, file=rel, line=line_no))

    # The reverse: a documented method no route references. Compared as
    # controller-qualified actions — `Other@full` is not covered by a route
    # to `Anime@full` just because the method names match.
    for controller, (methods, _declared) in sorted(per_controller.items()):
        source = next(d / f"{controller}.php" for d in controller_dirs
                      if (d / f"{controller}.php").is_file())
        rel = source.relative_to(REPO).as_posix()
        for method, documented in sorted(methods.items()):
            if documented and f"{controller}@{method}" not in actions:
                records.append(F.make(
                    ENVELOPE, "phantom_documentation",
                    f"{controller}.{method}() carries a "
                    f"{'/'.join(markers)} docblock but no route action "
                    f"references it — the contract documents an endpoint "
                    f"the app does not serve.",
                    severity=F.SHOULD_FIX, file=rel))

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"undocumented": sorted(
                r["summary"].split(" ")[0] for r in records
                if r["category"] == "undocumented_endpoint"),
             "phantom": sorted(
                 r["summary"].split("(")[0] for r in records
                 if r["category"] == "phantom_documentation")},
            indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "endpoint-parity") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(route_files) + len(per_controller),
        )

    print(f"  route actions       {len(actions)}")
    print(f"  controllers read    {len(per_controller)}")
    if not records:
        print(f"\naudit_endpoint_parity: every served endpoint is documented "
              f"and every documented endpoint is served")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
