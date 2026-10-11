---
name: wire-endpoint
description: "Wire a hardcoded or stub data source to a mocked GET endpoint in the shape the project already uses — model, datasource, bloc, fixture, contract registration, docs, test. Use when asked to wire up or connect a data source."
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

You wire one hardcoded/stub data source to a real (mocked) `GET` endpoint, in the exact shape every other endpoint in this app was wired in — model, datasource, bloc, fixture, contract registration, doc section, mock entry, test — so that no two designers' AI sessions produce differently-shaped integrations. This is the data-layer sibling of `/scaffold-screen`: that skill removes repetition from building a new screen's states; this one removes repetition (and drift risk) from connecting a screen to real data.

**You wire read-only GET flows only. You never invent example values, never fabricate a data shape the screen doesn't already consume, and never touch anything the decision rubric below flags as client-only state.** Reference: `{{dir:plans}}/mock-api-integration.md` (the original phased wiring effort), `{{dir:plans}}/mock-api-hardening-and-portability.md` (drift/enrichment/portability follow-on), `/sync-mock-api`, `/audit-mock-api`.

---

## Step 0 — The decision rubric: is this actually a GET candidate?

Before wiring anything, answer this. Getting it wrong was the single most common judgment call across every phase of the original wiring effort (`LabKitStatus`, Appointments' booking state, and the caregiver dev-menu's linked-patient list were all found to be **not** GET candidates, after initially looking like one).

**Ask: where does this data currently come from, and does changing it persist anywhere a server would plausibly own?**

| Signal | Verdict |
|---|---|
| A hardcoded `const`/stub list in a routes file or screen, read on load, never mutated by the user | ✅ Real GET candidate |
| A value the user can change in-session (book/cancel, check off, submit a form) that then needs to persist and reload correctly | ⚠️ The **initial load** is a GET candidate; the **mutation** is not (see the static-mock rule below) |
| A value only ever set by a dev-menu / scenario-switcher action (`grep` for where it's dispatched — if the only dispatcher is a debug/dev widget, not a real user flow) | ❌ Not a GET candidate — it's demo/dev state with no real backend equivalent yet |
| Data derived entirely from other already-wired features, with no fetch of its own (a "wrapper"/"aggregation" adapter) | ❌ Nothing to wire — confirm and move on |

If you're not sure, `grep` for every place the data's event/setter is dispatched from before proceeding — don't guess from the screen alone.

## Step 1 — The static-mock rule

The mock server (Postman, or whatever `mock_provider` is configured in `<pipelines.mockApi>/config.json`) has **zero scripting** — every request to a given endpoint returns the same canned example, always. This means:

The same `config.json` also holds `servers` — a `{environment: url}` map naming this project's own mock-server base URL(s), which is what the generated OpenAPI spec's `servers` block and its "Try It" console use. It lives there, never in the engine: a base URL compiled into the suite would point every consumer's spec at one project's server. A project that declares none gets a spec with no `servers` block and an `openapi_servers_undeclared` finding saying so.

- **Wire only the initial-load GET.** Anything that mutates in-session (booking, cancelling, checking off, sending a message, submitting a form) stays client-side state, exactly as it does today — do not invent a POST/PATCH just to make the flow feel "fully wired."
- If a screen has both a real initial load AND local mutation (e.g. "fetch appointments, then let the user book one locally"), wire only the fetch. State that explicitly in your summary so it's not mistaken for partial/incomplete work.

## Step 2 — Confirm the shape with the user

Ask (if not already given), same discipline as `/scaffold-screen`'s Step 0 — you scaffold structure and copy real data, you never invent either:

- The feature name and endpoint path (e.g. `GET /support/requests`).
- Which existing hardcoded data source currently backs the screen (a routes-file stub, a widget's local list, etc.) — this becomes the fixture's starting content, not invented data.
- Whether an entity/domain layer already exists for this data, or needs one alongside the model.

## Step 3 — Build the data layer, in this exact shape

Every wiring this session followed this structure — match it exactly so any two integrations in this codebase look the same:

1. **Model** (`<source.root>/<feature>/data/models/<name>_model.dart`) — a `fromJson(Map<String, dynamic> json)` factory. If the model has ANY nested object/list-item parsing, give each nested parser a **distinct parameter name** (`itemJson`, `rangeJson`, never `json`/`map`) — this is required for Step 6's contract registration to work; see `${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/providers/schema/dart_fromjson.py`'s docstring for why.
2. **Remote datasource** (`<source.root>/<feature>/data/datasources/<name>_remote_datasource.dart`) — abstract class + `Impl` calling `ApiClient.instance.dio.get('/your/path')`, parsing the response, with the standard `_mapError(DioException)` → `NoInternetException`/`ServerException`/`NetworkException` mapping (copy an existing datasource's `_mapError` verbatim — don't reinvent it).
3. **Bloc** (`<source.root>/<feature>/presentation/bloc/<name>_bloc.dart` + `_event.dart` + `_state.dart`) — mirrors `PlansCatalogBloc`'s shape exactly: states `Initial`/`Loading`/`Loaded(data)`/`LoadFailed(String message)`, one `<Name>FetchRequested` event, `_onFetch` emits Loading → awaits the datasource → emits Loaded or catches to LoadFailed.
4. **Router wiring** — add the bloc as a shared instance in `app_router.dart` (dispatch the initial fetch immediately after construction, same pattern as `_sharedHealthBloc`/`_carePlanCatalogBloc`), then thread it into the route builder and replace the hardcoded stub with `BlocBuilder`-sourced data.

## Step 4 — Extract the fixture from the real hardcoded data

Don't hand-type the fixture. Write a small throwaway Python script that regex-parses the actual Dart stub block being replaced (balanced-paren/bracket extraction + per-field regex) and dumps exact JSON to `test/fixtures/<name>_example.json` — this is how every fixture in this session was built, and it guarantees fidelity to what the screen already showed. Spot-check the extracted counts against the source before moving on.

## Step 5 — Write a fixture-backed model test

`test/features/<feature>/data/models/<name>_model_test.dart` loading `test/fixtures/<name>_example.json` and asserting `fromJson` parses every field correctly — same pattern as `membership_model_test.dart`. This is what keeps the fixture, the doc, and the mock from independently drifting later.

## Step 6 — Register the contract

Add an entry to `<pipelines.mockApi>/contracts.json` (see `/sync-mock-api`'s Step 1 for the exact shape: `model_file`, `fixture`, optional `fixture_list_key`/`fixture_map_key`, `api_doc_anchor`, `mock_folder`, `mock_request`). Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/sync_mock_api.py" <contract-name> --write
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/audit_mock_api.py" <contract-name>
```

`sync_mock_api.py` without `--write` only prints what it would do — this is
a brand-new contract with no prior mock/doc body, so there's nothing on the
target side yet for `--write` to lose (see `/sync-mock-api` for what
happens once one exists and the fixture is edited later).

If `audit` reports the model's fields don't resolve to a clean top-level set (every nested field showing up as "missing from fixture"), you skipped the distinct-parameter-name rule in Step 3 — fix the model, not the tooling.

If the fixture is small/moderate, `sync` will fully embed it in `{{doc:api}}`; if it's large, write a representative excerpt by hand under the endpoint's heading and note where the full fixture lives (see Library's or Health Measurements' section for the pattern) — either way, add the field table under the endpoint's own `#### ` heading, not by cross-referencing another section's table (the doc checker only ever looks under a contract's own anchor).

## Step 6b — Enrich the OpenAPI reference (`<pipelines.mockApi>/openapi_meta.json`)

`sync`/`audit` regenerate `<pipelines.mockApi>/openapi.json` automatically, but the generator can only *infer* structure from the fixture — it can't invent the prose, enums, and formats that make the browsable reference (`docs/api-reference.html`) actually useful. That context is authored **here, at registration time**, so it's never a later chore. See `<pipelines.mockApi>/OPENAPI.md` for the overlay format and merge rules.

Add to `<pipelines.mockApi>/openapi_meta.json` (all project-agnostic; the generator deep-merges it over the inferred spec):

1. **Operation description** — `operations.<contract-name>.description`: one sentence on what the endpoint returns. Every operation should have one.
2. **Tag prose** — if this endpoint's `mock_folder` is a *new* value, add `tags.<folder>` describing that resource group. Reuse the existing line if the folder is already present.
3. **Enums / formats** — for any field with a closed value set (a Dart `enum` or a `switch`-mapped string set in the model) or a date/time string, declare it under `schemas.<SchemaName>.properties.<field>` (`enum`, or `format: date-time`). The `<SchemaName>` is the model basename in PascalCase (`archivable_model.dart` → `Archivable`); contracts that share a model share one schema, so enrich it once. **Only annotate fields that actually exist in the fixture** — the audit flags orphan overlay entries.

Then re-run the audit and confirm no new `_openapi_meta` coverage/orphan findings for your contract:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/audit_mock_api.py"          # full run surfaces _openapi_meta coverage/orphan checks
```

(The audit's `openapi_*` findings are `should_fix`, never blocking — but the whole point of authoring here is to not add to that backlog.)

## Step 7 — Add the mock collection entry

Add a folder/request to the mock collection file (whatever `mock_provider.file` is configured to) with the example response body built from the fixture — `sync_mock_api.py` regenerates the body once the request exists; you still need to create the request/folder structure itself the first time. Copy an existing folder's request shape (headers, URL, `originalRequest`) rather than hand-authoring the Postman JSON schema from scratch.

## Step 8 — Verify and document

```bash
flutter analyze
flutter test
```

**Then, if this session has `mcp__Claude_Code_iOS_Simulator__control` available, verify the wired screen live rather than stopping at static checks** — `attach`, build (`flutter build ios --debug --simulator --dart-define-from-file=.env`) and `launch`, then navigate to the screen and confirm it loads and renders the real mock data with no overflow/layout break. Analyze and tests confirm the code compiles and the model parses correctly; they can't catch a layout that only breaks once real fixture-shaped data (a longer string, more list items) flows through it — this is exactly the class of bug a live check catches that static checks don't. Skip this step (and say so) if the tool isn't available in this session — it's optional, not a blocker for the wiring itself.

Update the living plan doc (`{{dir:plans}}/mock-api-integration.md` or its successor) with a short entry: what was wired, what stayed client-side and why (Step 1's static-mock rule), any tooling notes. Update `<pipelines.mockApi>/README.md`'s coverage table.

## Step 9 — Commit

One commit for the whole wiring (model + datasource + bloc + router + fixture + test + contract + doc + mock) — this is "one reviewed unit," same as `/sync-mock-api`'s rule for its two generated files, extended to the full wiring.

---

## What you must never do

- Wire a mutation (POST/PATCH/DELETE) to make a flow feel "complete" — the static-mock rule means only GET-and-display is in scope; mutations stay client-side
- Wire dev-menu/scenario-switcher-only state as if it were a real fetch — confirm the dispatcher first
- Hand-type a fixture instead of extracting it from the real hardcoded data being replaced
- Name a nested parser's parameter `json`/`map` — this silently breaks contract registration
- Skip the fixture-backed model test — it's what keeps this endpoint from drifting the way the pre-automation endpoints did (see `{{dir:plans}}/mock-api-hardening-and-portability.md` Track A)
- Invent field values, screen content, or a data shape not already consumed by the screen being wired
- Annotate a field/schema/tag in `openapi_meta.json` that the fixtures don't actually produce — the overlay only annotates inferred structure, never invents it (the audit flags orphans)
