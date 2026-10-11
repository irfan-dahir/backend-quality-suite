---
name: audit-test-network-coupling
description: "Report-only audit for tests that can reach a live service — tests referencing a live host with no recorded-client marker, and real-client fallbacks that go live when a recording is absent. Use when asked whether the suite is hermetic, after adding a test that fetches, or when CI behaves differently from local runs."
invocation: auto
maturity: unverified
---

# /audit-test-network-coupling

> Needs a `testNetworkCoupling` section in the architecture rules
> (`testsGlob`, `liveHostPattern`, `mockClientPattern`,
> `fallbackPattern`). The markers are the project's own spellings of
> "these requests are recorded".

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_test_network_coupling.py"
```

Hermeticity that depends on a setup step being remembered is a decision.
A host string inside a test is not automatically coupling — if the file
routed its requests through the project's recorded client, the URL is a
recorded request, and the audit counts it as such rather than flagging it.
The two findings are the two real shapes: a test talking to the service as
written, and a fallback construction that goes live whenever a recording
is missing — the run looks offline while it happens.

## Reading the output

- `live_network_test` — no recorded-client marker. Route the test through
  the fixture client, or record the response first.
- `network_fallback` — a real-client construction in the test tree. If the
  record-on-first-use design is deliberate, exempt it **with the reason**
  (CI pre-clones the recordings so the miss path never fires) — the point
  is that the fallback's existence is a known, stated fact.

## What you must never do

- Delete a fallback to make the audit green without checking what depends
  on first-use recording
- Treat "it passed locally" as proof of hermeticity — a populated fixture
  store is exactly the state that hides this
