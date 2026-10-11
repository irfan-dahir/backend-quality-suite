---
name: audit-endpoint-parity
description: "Report-only audit comparing served endpoints against their OpenAPI annotations — routes whose controller method carries no docblock marker (absent from the generated spec) and annotated methods no route serves (phantom contract). Use when asked whether the API docs still match the routing table, after adding or removing an endpoint, or when the generated spec looks stale."
invocation: auto
maturity: unverified
---

# /audit-endpoint-parity

> Needs an `endpointParity` section in the architecture rules
> (`routesGlob`, `actionPattern`, `controllerDirs`, `docMarkers`). A refusal
> naming a missing key is the tool working: help write the section.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_endpoint_parity.py"
```

The OpenAPI spec is generated from source annotations, so its truth is the
join between the routing table and the annotated controller methods. The
audit compares at the action level (`Controller@method`) — the stable join
both sides share — in both directions.

## Reading the output

- `undocumented_endpoint` — a served route whose method carries no
  annotation marker: callers hit it, the generated contract omits it. Add
  the annotation (with the response shape it actually returns) or, if the
  endpoint is internal, decide that with the team rather than by omission.
- `phantom_documentation` — an annotated method no route uses: the spec
  documents an endpoint the app does not serve. Almost always a route that
  was renamed — fix the annotation or delete it.

A refusal naming a missing controller file means the route is dead — that
is route coverage's finding, and this audit refuses to misfile it.

## What you must never do

- Add a stub annotation to silence `undocumented_endpoint` — a documented
  wrong shape is worse than an undocumented right one
- Delete an annotated method on the strength of `phantom_documentation`
  alone; check nothing else dispatches to it
