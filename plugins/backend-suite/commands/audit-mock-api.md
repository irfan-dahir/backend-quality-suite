---
name: audit-mock-api
description: "Report-only drift audit for registered mock-API contracts — never edits a contract artifact, but writes its findings to .backend-suite/mock-api-findings.json (pass --out to redirect), and finds disagreement between the model, the fixture, the API docs and the mock server. Use when asked whether the mock API is in sync."
invocation: auto
maturity: proven
---

# /audit-mock-api

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the read-only drift auditor for mock-API contracts registered in
`<pipelines.mockApi>/contracts.json` — the sibling of `/audit-tokens` and
`/audit-assets`, scoped to the four-way relationship between a Dart model,
its fixture, `{{doc:api}}`, and the Postman collection.

**You report; you never write. Use `/sync-mock-api` to fix what this finds.**

---

## Step 0 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/audit_mock_api.py"            # every registered contract
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/audit_mock_api.py" plans       # one contract
```

Findings are written to `.backend-suite/mock-api-findings.json` (ignored by the
`.gitignore` `init.py` scaffolds there; `--out <path>` still wins) and printed.
It used to default to `<pipelines.mockApi>/findings.json` at the project root, a
tracked file every run dirtied — if an old copy is still tracked, `git rm --cached` it. Exit code is
`1` if any 🔴 critical finding exists (useful for CI / a pre-commit gate),
`0` otherwise, and **`2` refused** — the run could not establish what it was
supposed to check (an unknown contract name, or a contract whose
`optional_fields` block it cannot parse; see below). A `2` is not a pass and
must never be reported as one.

## What it checks, per contract

| Check | Severity | Meaning |
|---|---|---|
| `model_vs_fixture` | 🔴 / 🟡 | A field the model reads has no value in the fixture. 🔴 when the field is required, or is optional and at least one fixture record meets its declared condition; 🟡 when the field is declared unconditionally optional |
| `model_vs_doc_table` | 🟡 | A model field isn't documented in the `{{doc:api}}` table (needs a human-written Notes entry) |
| `model_vs_mock` | 🔴 / 🟡 | A model field is missing from the Postman example, under the same severity rule as `model_vs_fixture` |
| `optional_field_not_exercised` | 🔵 | A conditionally-optional field is absent **and no record on that side satisfies its condition** — so its absence was not checked, rather than checked and found clean. Not a finding; not a pass either |
| `fixture_vs_model` | 🟡 | The fixture has a field the model never reads — stale, or the model is behind |
| `mock_vs_fixture` | 🔴 | The Postman example's field set doesn't match the fixture's |
| `mock_vs_fixture_values` | 🔴 | Same fields, but the Postman example's **values** differ from the fixture — the exact class of drift that hit `GET /plans` this session (a revert silently rolled back the mock while the fixture/doc moved on) |
| `doc_vs_fixture_values` | 🔴 | `{{doc:api}}`'s example block values differ from the fixture |
| `doc_example_parse` / `mock_body_parse` | 🔴 | The example under the doc anchor, or the mock's response body, isn't valid JSON |

## Declaring an optional field's condition (issue #117)

A model's optional field is often meaningful for only *some* records — a
`weekday` that only an item on a weekly cadence ever carries. Without knowing
that, the audit reported a 🔴 for every contract whose fixture happened to hold
no such record, and there was no edit to those fixtures that would resolve it.
An unactionable 🔴 sitting beside real ones is how a reader learns to skim.

The condition is **declared, never inferred** — inferring it is the hard part,
and inferring it wrong would buy a second false-positive mode to replace the
first. Declare it on the contract in `<pipelines.mockApi>/contracts.json`:

```json
"optional_fields": {
  "weekday": {
    "when": {"field": "cadence", "equals": "weekly"},
    "why":  "only weekly items carry a due weekday"
  },
  "note": {}
}
```

- `{"when": {...}}` — absence is 🔴 only when at least one record on that side
  satisfies the predicate; otherwise you get the single 🔵 notice above.
  `equals` matches one value, `in` matches a list; exactly one of the two.
- `{}` — unconditionally optional. Absence is still reported, at 🟡.
- **Absent entirely** — the field is required, and its absence is 🔴, exactly as
  before. A project that declares nothing sees no change, so this mechanism can
  never quiet a check by itself.
- Anything the audit cannot parse is a **refusal (exit 2)**, never a guess in
  either direction.

## Step 1 — Report

Follow the `/review-docs` report shape: 🔴 Critical / 🟡 Should Fix / 🔵 FYI, one
finding per bullet, then a summary count. This skill never applies a fix.

**Do not point a `*_values` finding at `/sync-mock-api`.** Those findings prove
the two sides *disagree*; they do not establish which side is right, and that is
a judgement about intent that lives in neither file. `/sync-mock-api` propagates
fixture → mock/docs, so recommending it for a disagreement silently elects the
fixture as authoritative — which, on a fixture that was the rotted side, deleted
correct data from the repository (issue #116). Quote both sides from the finding
detail, which already names what each one holds, and let the reader decide.

Findings that are one-directional — `model_vs_mock`, `mock_vs_fixture`'s
"only in fixture" half, `openapi_vs_fixtures` — do have a defensible repair
direction and may name one.

---

## What you must never do

- Write to `{{doc:api}}`, the Postman collection, the fixture, or the model
- Auto-run `/sync-mock-api` on the user's behalf — report the finding, let
  them choose to fix it (a value drift might mean the fixture is stale, not
  the mock — that's a judgment call)
- Treat a `🟡 fixture_vs_model` finding as "the fixture is wrong" without
  checking whether the model is actually the one that's behind
