---
name: wire-endpoint
description: "Wire a hardcoded or stub data source to a mocked GET endpoint in the shape the project already uses — fixture, contract registration, docs, test. Use when asked to wire up or connect a data source."
argument-hint: "<endpoint>"
invocation: explicit
maturity: unverified
---

# /wire-endpoint

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

You wire one hardcoded/stub data source to a real (mocked) `GET` endpoint, in the exact shape every other endpoint in this project was wired in — fixture, contract registration, doc section, mock entry, test — so that no two sessions produce differently-shaped integrations. This removes repetition (and drift risk) from connecting a consumer to real data.

**You wire read-only GET flows only. You never invent example values, never fabricate a data shape the endpoint does not already return, and never touch anything the decision rubric below flags as client-only state.** Reference: `{{dir:plans}}/mock-api-integration.md` (the original phased wiring effort), `{{dir:plans}}/mock-api-hardening-and-portability.md` (drift/enrichment/portability follow-on), `/sync-mock-api`, `/audit-mock-api`.

---

## Step 0 — The decision rubric: is this actually a GET candidate?

Before wiring anything, answer this. Getting it wrong was the single most common judgment call across every phase of the original wiring effort (three candidates were found to be **not** GET candidates, after initially looking like one).

**Ask: where does this data currently come from, and does changing it persist anywhere a server would plausibly own?**

| Signal | Verdict |
|---|---|
| A hardcoded array/stub in a route closure or controller method, read on load, never mutated | ✅ Real GET candidate |
| A value the user can change in-session (submit a form, toggle state, check off) that then needs to persist and reload correctly | ⚠️ The **initial load** is a GET candidate; the **mutation** is not (see the static-mock rule below) |
| A value only ever set by a dev-menu / scenario-switcher action (`grep` for where it is dispatched — if the only dispatcher is a debug endpoint or a seeded test path, not a real flow) | ❌ Not a GET candidate — it's demo/dev state with no real backend equivalent yet |
| Data derived entirely from other already-wired features, with no fetch of its own (an aggregation/wrapper service) | ❌ Nothing to wire — confirm and move on |

If you're not sure, `grep` for every place the data is dispatched from before proceeding — don't guess from the route alone.

## Step 1 — The static-mock rule

The mock server (Postman, or whatever `mock_provider` is configured in `<pipelines.mockApi>/config.json`) has **zero scripting** — every request to a given endpoint returns the same canned example, always. This means:

The same `config.json` also holds `servers` — a `{environment: url}` map naming this project's own mock-server base URL(s), which is what the generated OpenAPI spec's `servers` block and its "Try It" console use. It lives there, never in the engine: a base URL compiled into the suite would point every consumer's spec at one project's server. A project that declares none gets a spec with no `servers` block and an `openapi_servers_undeclared` finding saying so.

- **Wire only the initial-load GET.** Anything that mutates in-session (submitting, toggling, sending, checking off) stays where it is — do not invent a POST/PATCH just to make the flow feel "fully wired."
- If an endpoint has both a real initial load AND local mutation (e.g. "fetch orders, then let the user acknowledge one locally"), wire only the fetch. State that explicitly in your summary so it's not mistaken for partial/incomplete work.

## Step 2 — Confirm the shape with the user

Ask (if not already given) — you scaffold structure and copy real data, you never invent either:

- The feature name and endpoint path (e.g. `GET /support/requests`).
- Which existing hardcoded data source currently backs the response (a route closure's array, a controller method's literal, a seeded fixture — `grep` the route file and the controller for the payload) — this becomes the fixture's starting content, not invented data.
- Whether a model class already exists for this data, or needs one alongside the service.

## Step 3 — Build the data layer, in this exact shape

Every wiring this session followed this structure — match it exactly so any two integrations in this codebase look the same:

1. **Model** (`<source.root>/<feature>/Models/<name>.php` — follow the project's own namespace and path convention) — a class whose **public instance properties are the wire shape**: that is what `json_encode` emits, and it is what the mock-api schema provider (`php_model_fields`) reads. Typed (`public string $id;`), readonly (`public readonly int $ttl;`), untyped legacy (`public $title;` — common in older model classes), and promoted constructor properties all count. `private`/`protected`/`static` members are **not** on the wire and must never carry response data.
   A nested object or list item is **its own model class** (`OrderLine`, `PaginationMeta`) with the same public-property shape. The provider reads one file per model, so a nested shape is declared by its class — never by parsing inline, and never by a catch-all `array` property hoping the values sort themselves out.
2. **Service** (`<source.root>/<feature>/Services/<name>Service.php`) — the method that produces the data (a repository call, an upstream client call, or — while the backend is unbuilt — the hardcoded data being replaced, kept verbatim and moved here). Match the project's existing service idiom rather than inventing a new one.
3. **Controller** (`<source.root>/<feature>/Http/Controllers/<name>Controller.php`) — a read-only action returning the model (or a list of it) through the project's standard response shape. Copy a neighbouring controller's response construction verbatim; don't introduce a new envelope the rest of the app doesn't use.
4. **Route wiring** — register `GET /path` → controller action in the project's routes file, matching the file's existing style, and delete the stub that previously served the path. A leftover stub is how two sources of truth start.

## Step 4 — Extract the fixture from the real hardcoded data

Don't hand-type the fixture. Write a small throwaway Python script that regex-parses the actual PHP stub being replaced (balanced-paren/bracket extraction + per-field regex) and dumps exact JSON to `<source.testRoot>/fixtures/<name>_example.json` — this is how every fixture in this session was built, and it guarantees fidelity to what the endpoint already returned. Spot-check the extracted counts against the source before moving on.

## Step 5 — Write a fixture-backed model test

`<source.testRoot>/<feature>/<name>_model_test.php` (the project's test-suite convention — PHPUnit in a Lumen/Laravel tree) loading `<source.testRoot>/fixtures/<name>_example.json` and asserting every fixture key lands on a public property of the model — same pattern as the project's existing model/JSON tests. This is what keeps the fixture, the doc, and the mock from independently drifting later.

## Step 6 — Register the contract

Add an entry to `<pipelines.mockApi>/contracts.json` for a PHP project (check how the project's other contracts are spelled and copy that shape):

```json
"orders_list": {
  "model_file": "app/Http/Models/Order.php",
  "fixture": "tests/fixtures/orders_example.json",
  "fixture_list_key": "orders",
  "api_doc_anchor": "#### `GET /orders`",
  "mock_folder": "Orders",
  "mock_request": "GET /orders"
}
```

And in `<pipelines.mockApi>/config.json`, the schema seam names the provider this model's convention:

```json
"schema_provider": "php_model_fields"
```

See `/sync-mock-api`'s Step 1 for the exact entry shape (`optional_fields`, `fixture_map_key`, `paginated` included). Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/sync_mock_api.py" <contract-name> --write
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/audit_mock_api.py" <contract-name>
```

`sync_mock_api.py` without `--write` only prints what it would do — this is
a brand-new contract with no prior mock/doc body, so there's nothing on the
target side yet for `--write` to lose (see `/sync-mock-api` for what
happens once one exists and the fixture is edited later).

If `audit` reports the model's fields don't resolve to a clean top-level set (every nested field showing up as "missing from fixture"), a shape is being parsed that the provider can't see — a nested object declared inline instead of as its own model class (Step 3), or a property the response actually builds through `toArray()`/a serializer. Fix the model (or write the `php_toarray.py` provider the convention needs); don't hack the fixture.

If the fixture is small/moderate, `sync` will fully embed it in `{{doc:api}}`; if it's large, write a representative excerpt by hand under the endpoint's heading and note where the full fixture lives (see the existing service sections for the pattern) — either way, add the field table under the endpoint's own `#### ` heading, not by cross-referencing another section's table (the doc checker only ever looks under a contract's own anchor).

## Step 6b — Enrich the OpenAPI reference (`<pipelines.mockApi>/openapi_meta.json`)

`sync`/`audit` regenerate `<pipelines.mockApi>/openapi.json` automatically, but the generator can only *infer* structure from the fixture — it can't invent the prose, enums, and formats that make the browsable reference (`docs/api-reference.html`) actually useful. That context is authored **here, at registration time**, so it's never a later chore. See `<pipelines.mockApi>/OPENAPI.md` for the overlay format and merge rules.

Add to `<pipelines.mockApi>/openapi_meta.json` (all project-agnostic; the generator deep-merges it over the inferred spec):

1. **Operation description** — `operations.<contract-name>.description`: one sentence on what the endpoint returns. Every operation should have one.
2. **Tag prose** — if this endpoint's `mock_folder` is a *new* value, add `tags.<folder>` describing that resource group. Reuse the existing line if the folder is already present.
3. **Enums / formats** — for any field with a closed value set (a PHP 8.1 `enum`, or a string set the model constrains) or a date/time string, declare it under `schemas.<SchemaName>.properties.<field>` (`enum`, or `format: date-time`). The `<SchemaName>` is the model class name in PascalCase (`Order.php` → `Order`); contracts that share a model share one schema, so enrich it once. **Only annotate fields that actually exist in the fixture** — the audit flags orphan overlay entries.

Then re-run the audit and confirm no new `_openapi_meta` coverage/orphan findings for your contract:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/audit_mock_api.py"          # full run surfaces _openapi_meta coverage/orphan checks
```

(The audit's `openapi_*` findings are `should_fix`, never blocking — but the whole point of authoring here is to not add to that backlog.)

## Step 7 — Add the mock collection entry

Add a folder/request to the mock collection file (whatever `mock_provider.file` is configured to) with the example response body built from the fixture — `sync_mock_api.py` regenerates the body once the request exists; you still need to create the request/folder structure itself the first time. Copy an existing folder's request shape (headers, URL, `originalRequest`) rather than hand-authoring the Postman JSON schema from scratch.

## Step 8 — Verify and document

```bash
# whatever this project's scripts are — check composer.json, don't assume
composer test            # the project's PHPUnit suite (Step 5's test included)
php -l app/Http/Controllers/OrdersController.php   # or the project's static-analysis step
```

**If this session can run the app locally (`php -S` / `lumen serve` / the project's server script), hit the route through it rather than stopping at static checks** — confirm the response body matches the fixture key-for-key. The suite proves the model parses and the route resolves; it can't catch a response shape that only diverges once the app actually serializes it (a property the controller adds, an envelope the mock doesn't have). Skip this step (and say so) if running the server isn't possible in this session — it's optional, not a blocker for the wiring itself.

Update the living plan doc (`{{dir:plans}}/mock-api-integration.md` or its successor) with a short entry: what was wired, what stayed client-side and why (Step 1's static-mock rule), any tooling notes. Update `<pipelines.mockApi>/README.md`'s coverage table.

## Step 9 — Commit

One commit for the whole wiring (model + service + controller + route + fixture + test + contract + doc + mock) — this is "one reviewed unit," same as `/sync-mock-api`'s rule for its two generated files, extended to the full wiring.

---

## What you must never do

- Wire a mutation (POST/PATCH/DELETE) to make a flow feel "complete" — the static-mock rule means only GET-and-display is in scope; mutations stay client-side
- Wire dev-menu/scenario-switcher-only state as if it were a real fetch — confirm the dispatcher first
- Hand-type a fixture instead of extracting it from the real hardcoded data being replaced
- Declare a nested object inline in the model instead of as its own model class — the schema provider reads one file per model, so an inline shape reads as "missing from fixture" on every audit
- Put response data on a `private`/`protected`/`static` property — it is not on the wire (`json_encode` doesn't emit it), and wiring a fixture to it produces drift the mock will flag
- Skip the fixture-backed model test — it's what keeps this endpoint from drifting the way the pre-automation endpoints did (see `{{dir:plans}}/mock-api-hardening-and-portability.md` Track A)
- Invent field values, response content, or a data shape the endpoint being wired doesn't already return
- Annotate a field/schema/tag in `openapi_meta.json` that the fixtures don't actually produce — the overlay only annotates inferred structure, never invents it (the audit flags orphans)
