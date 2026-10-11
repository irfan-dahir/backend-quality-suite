---
name: audit-route-coverage
description: "Report-only audit resolving every declared route action to a real controller method — a route whose action string no longer resolves 500s on every request. Use when asked whether the routing table is intact, after renaming or moving a controller method, or when routes appear to have broken without a build error."
invocation: auto
maturity: unverified
---

# /audit-route-coverage

> Needs a `routeCoverage` section in the architecture rules (`routesGlob`,
> `actionPattern`, `controllerDirs`). Refusals name the missing piece.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_route_coverage.py"
```

Route tables name their handlers (`'uses' => 'Ctrl@method'`) and nothing
checks the name still resolves until a caller hits the route. Every
declared action is resolved against the controller tree; closures (no
action string) cannot dangle by renaming and are counted, not checked.

## Reading the output

- `dead_route` — the action's controller file or method does not exist.
  This route 500s on every request: restore the target, fix the action
  string, or delete the route.

Severity is critical on purpose — a dead route is not latent drift, it is
a broken endpoint that ships with the next release.

## What you must never do

- Delete a dead route to make the audit green when callers may still hold
  its URL — a removed route is a breaking API change and belongs in the
  release notes, not a cleanup commit
