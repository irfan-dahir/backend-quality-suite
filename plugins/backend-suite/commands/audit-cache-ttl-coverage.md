---
name: audit-cache-ttl-coverage
description: "Report-only audit for per-endpoint cache TTL drift — routes whose action has no TTL map entry, and TTL map entries whose route no longer exists. Use when asked whether the cache TTL config still matches the routing table, after adding or removing a route, or when endpoints cache outside the declared policy."
invocation: auto
maturity: unverified
---

# /audit-cache-ttl-coverage

> The project's architecture rules must carry a `cacheTtlCoverage` section
> (`routesGlob`, `actionPattern`, `ttlConfigGlob`, `ttlKeyPattern`, optional
> `exempt` with reasons). If the audit exits 2 saying one is missing, that is
> the tool working: help write the section rather than working around it.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_cache_ttl_coverage.py"
```

The TTL map (config keyed by route action, e.g. `Controller@method`) is a
**copy of the routing table**: the cache middleware reads it by route name at
request time. Copies drift in both directions and neither direction fails
loudly — a routed action missing from the map just caches outside the map's
policy, and an entry whose route was deleted keeps configuring an endpoint
that no longer exists. The audit compares both directions and reports each
kind separately, because the fix differs: fill the gap, or delete the row.

## Reading the output

- `route_missing_ttl` — a live route whose action has no TTL entry. Decide
  with the team whether the endpoint should be cached at all; if it should,
  add the entry with the TTL that endpoint's freshness warrants.
- `stale_ttl_entry` — the entry's route is gone. The honest fix is almost
  always deletion; keeping it re-licenses a config that no longer describes
  the app.
- `exempt` — routes the config exempts **with a written reason**. Read the
  reasons when the routing table changes: an exemption is a decision, not a
  parking space.

## What you must never do

- Add a TTL entry to silence the audit without knowing what TTL the endpoint
  deserves — a wrong TTL is a slower defect than a missing one
- Delete a `stale_ttl_entry` whose route might be served another way
  (feature-flagged, mounted elsewhere) before checking where the action name
  is referenced
- Edit the routes file or the TTL config from this audit's findings without
  confirmation — both are policy documents
