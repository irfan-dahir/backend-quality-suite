#!/usr/bin/env python3
"""Every live route has a cache TTL decision, and every TTL decision has a route.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_cache_ttl_coverage.py" [--out …] [--findings]

## Why this exists

A per-endpoint cache TTL map is the kind of config that drifts in both
directions silently, because nothing joins it to the routes it describes. The
middleware reads the map by route name at request time; a route missing from
the map does not fail — it quietly gets no per-endpoint TTL (the cache layer
falls through to its own default or to no caching), and a map entry whose
route was deleted keeps configuring an endpoint that no longer exists.

Measured on the first validation target (jikan-rest, Lumen, probed
2026-10-11): the TTL map in `config/jikan.php` carries 80 entries keyed
`Controller@method`, matching `HttpHelper::getRouteName`'s extraction from
each route's `uses` string. **27 live route actions have no entry** — the
`/full` and `/external` routes across anime, manga, person, producer, user
and club, every `RandomController` route, `SeasonController@now`, and more —
so those endpoints cache without the policy the map exists to express. And
**4 entries have no route**: `GenreController@mainAnime`,
`GenreController@mainManga`, `MagazineController@resource`,
`PersonController@seiyuu` — endpoints deleted from `routes/web.v4.php`,
their config rows left behind.

Both directions are findings for the same reason contract-header staleness
is: a config file that describes a routing table is a *copy* of that table,
and a copy nobody checks is a copy that has already started lying. The fix
direction differs — a missing entry is usually an oversight to fill in, a
stale entry is usually a row to delete — so they are separate kinds.

## The key space is the project's, not this engine's

How a route declares its action (`'uses' => 'Ctrl@method'`) and how the TTL
map spells its keys are framework facts. The project supplies both regexes
in its architecture rules (`cacheTtlCoverage.actionPattern` /
`ttlKeyPattern`); this audit only requires that each yields the same key
space, which is exactly the claim the middleware makes at runtime.

## What it refuses to do

Report clean on an empty sweep: routes or TTL config that cannot be found,
or an action pattern that extracts zero actions, exit 2 with the reason.
An audit that compared nothing and printed "0 violations" is the failure
mode every check in this suite is built around.
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

RULES = load(REPO, "cacheTtlCoverage")

ENVELOPE = "cache-ttl-coverage"


def _glob(key: str, why: str) -> list[Path]:
    pattern = RULES.get(key)
    if not pattern:
        raise Refused(f"cacheTtlCoverage.{key} is not set — {why}",
                      audit="audit_cache_ttl_coverage")
    found = sorted(REPO.glob(pattern))
    if not found:
        raise Refused(
            f"cacheTtlCoverage.{key} ({pattern!r}) matched no files — {why}. "
            f"An empty sweep would report clean having compared nothing.",
            audit="audit_cache_ttl_coverage")
    return found


def _regex(key: str, why: str) -> re.Pattern:
    pattern = RULES.get(key)
    if not pattern:
        raise Refused(f"cacheTtlCoverage.{key} is not set — {why}",
                      audit="audit_cache_ttl_coverage")
    try:
        return re.compile(pattern, re.M)
    except re.error as exc:
        raise Refused(f"cacheTtlCoverage.{key} is not a valid regex: {exc}",
                      audit="audit_cache_ttl_coverage")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    route_files = _glob("routesGlob", "the routes to check cannot be found")
    ttl_files = _glob("ttlConfigGlob", "the TTL config cannot be found")
    action_re = _regex("actionPattern",
                       "how a route spells its action key (usually "
                       "'Controller@method')")
    ttl_re = _regex("ttlKeyPattern", "how the TTL map spells its keys")
    exempt = RULES.get("exempt") or {}
    for action, why in exempt.items():
        if not isinstance(why, str) or not why.strip():
            raise Refused(
                f"cacheTtlCoverage.exempt[{action!r}] has no reason. An "
                f"exemption without a why is a finding nobody has to think "
                f"about again.", audit="audit_cache_ttl_coverage")

    actions: dict[str, tuple[str, int]] = {}
    for path in route_files:
        rel = path.relative_to(REPO).as_posix()
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            for match in action_re.finditer(line):
                actions.setdefault(match.group(1), (rel, line_no))

    ttl_keys: set[str] = set()
    for path in ttl_files:
        ttl_keys |= set(ttl_re.findall(path.read_text()))

    if not actions and not ttl_keys:
        raise Refused(
            "neither the routes nor the TTL config yielded a single key — the "
            "two patterns describe different key spaces, or this is not the "
            "map this audit thinks it is. Refusing to compare nothing.",
            audit="audit_cache_ttl_coverage")

    missing = sorted(set(actions) - ttl_keys - set(exempt))
    stale = sorted(ttl_keys - set(actions))
    covered_exempt = {k: exempt[k] for k in sorted(set(exempt) & set(actions))
                      if k in actions}

    records = []
    for key in missing:
        rel, line_no = actions[key]
        records.append(F.make(
            ENVELOPE, "route_missing_ttl",
            f"{key} has a live route ({rel}:{line_no}) but no "
            f"per_endpoint_cache_ttl entry — it caches outside the map's "
            f"policy.",
            severity=F.SHOULD_FIX, file=rel, line=line_no))
    for key in stale:
        records.append(F.make(
            ENVELOPE, "stale_ttl_entry",
            f"{key} is configured in the TTL map but no route declares it — "
            f"the endpoint it names is gone; delete the row.",
            severity=F.SHOULD_FIX))

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"route_missing_ttl": missing, "stale_ttl_entry": stale,
             "exempt": covered_exempt}, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "cache-ttl-coverage") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(route_files) + len(ttl_files),
            suppressed=covered_exempt or None,
        )

    print(f"  route actions       {len(actions)}")
    print(f"  ttl map entries     {len(ttl_keys)}")
    if covered_exempt:
        print(f"  exempt (with why)   {len(covered_exempt)}: "
              f"{', '.join(covered_exempt)}")
    if not records:
        print(f"\naudit_cache_ttl_coverage: every route action has a TTL entry "
              f"and every entry has a route")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
