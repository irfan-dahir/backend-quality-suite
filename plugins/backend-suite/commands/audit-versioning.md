---
name: audit-versioning
description: "Report-only audit that the API's version statements agree — the versioned route file's name, the URL prefix it mounts under, and the controller namespace handlers resolve through. Use when asked whether versioning is consistent, before a version bump, or when endpoints appear on the wrong URL."
invocation: auto
maturity: unverified
---

# /audit-versioning

> Needs a `versioning` section in the architecture rules (`bootstrapGlob`,
> `routeFilePattern`, `prefixPattern`, `namespacePattern`,
> `namespaceVersionPattern`). Association is by nearest preceding group
> declaration — a nested routing file should not wire this audit.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_versioning.py"
```

A versioned API states its version in more than one place, and the
statements drift without failing at boot: a v5 routes file mounted under
the v4 prefix serves v5 code on the v4 URL, and a stale namespace resolves
handlers through the wrong version's tree.

## Reading the output

- `prefix_version_mismatch` — filename and URL prefix disagree. Callers
  reach one version's code on another's URL: critical, fix the mount.
- `namespace_version_mismatch` — the handler namespace is on another
  version than the file. Handlers resolve through the old tree, or fail to.

## What you must never do

- Change the prefix to match a filename without checking which URL
  callers hold — the prefix is the public contract and the filename is
  internal; usually the mount is what changes
