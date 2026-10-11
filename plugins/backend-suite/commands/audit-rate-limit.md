---
name: audit-rate-limit
description: "Report-only audit for inbound rate-limit coverage — endpoints with no limiter in their declaration and no global throttle, with documented exemptions carrying reasons. Use when asked which endpoints are rate-limited, after adding a route, or when deciding the API's protection policy."
invocation: auto
maturity: unverified
---

# /audit-rate-limit

> Needs a `rateLimit` section in the architecture rules (`routesGlob`,
> `actionPattern`, `protectionPattern`, `globalProtectionPattern`,
> `globalProtectionFiles`). Both patterns are how THIS stack declares
> protection — the audit recognises only what the project states.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_rate_limit.py"
```

A rate-limit policy lives in middleware and drifts silently: the API keeps
serving, just to whoever asks fastest. The audit checks every route action
against the project's own spellings of protection — a global throttle, or
a per-route limiter in the route's declaration window. Where nothing
protects and nothing is exempted, that is a finding: the policy is
unwritten, and the audit's job is to make it one.

## Reading the output

- `unprotected_endpoint` — no global throttle, no per-route limiter. Either
  protect it, or exempt it **with the reason** (open-by-design, static
  payload, abuse costs nothing). The exemption map is where a deliberate
  openness becomes a recorded decision instead of an absence.
- `global throttle none` in the summary is a fact about the whole app, not
  a finding — read it before triaging 100 individual ones.

## What you must never do

- Add a limiter to satisfy the audit without knowing what limit the
  endpoint's upstream can carry — a wrong number is not protection
- Exempt in bulk without reasons; that is the audit's config contract
  refusing to let silence look like a decision
