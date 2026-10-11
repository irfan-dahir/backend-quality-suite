---
name: audit-error-shape
description: "Report-only audit for the error envelope — error-status responses authored outside the exception handler (callers branching on the envelope will not see their shape) and declared envelope keys missing from the handler itself. Use when asked whether error responses are consistent, after changing the exception handler, or when a client reports an error payload it cannot parse."
invocation: auto
maturity: unverified
---

# /audit-error-shape

> Needs an `errorShape` section in the architecture rules (`handlerGlob`,
> `envelopeKeys`, `sourceGlob`, `bypassPattern`). The bypass pattern is how
> THIS stack spells a direct error response — a refusal naming it is the
> tool asking for that fact.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_shape.py"
```

Clients branch on error payloads: the `type` they switch on, the `status`
they map, the `message` they show. Two drifts break that without failing a
build — a response authored outside the envelope's author, and a declared
key removed from the author. The key check is string-level (a net, not a
proof): it sees a key deleted from the handler file, not from one branch.

## Reading the output

- `error_shape_bypass` — a direct error-status response outside the
  handler. Either route it through the handler, or (if the hand-rolled
  shape is deliberate) exempt it with the reason so the divergence is a
  decision.
- `envelope_key_missing` — a declared key appears nowhere in the handler.
  Restore it, or change `envelopeKeys` with the team — the config is the
  contract clients read.

## What you must never do

- Widen `bypassPattern` until the findings stop; the pattern is the
  convention, and a convention nobody can state cannot be enforced
- Copy the handler's envelope into a controller to satisfy the audit —
  that is the drift this audit exists to catch
