"""Shared helpers for sync_mock_api.py and audit_mock_api.py.

Source-of-truth chain per docs/context/plans/mock-api-integration.md's
"Contract automation" section:
  Model's field shape (schema provider) -> fixture (example VALUES,
  human-maintained) -> doc example block + mock example body (both
  generated from the fixture, via the doc/mock providers).

The field table's Notes column and the surrounding prose stay hand-written —
that's judgment, not shape, so neither script touches it.

This module is now thin orchestration: `mock_api/config.json` names which
provider implements each of the three project-specific seams (schema
reader, doc reader/writer, mock reader/writer — see
${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/providers/), and everything
below just resolves and calls
into whichever provider is configured. Swapping providers here — to point
this whole pipeline at a different project's stack — never requires
touching this file, sync_mock_api.py, or audit_mock_api.py. See
docs/context/plans/mock-api-hardening-and-portability.md Track C.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from design_suite.project import profile, project_root  # noqa: E402
from design_suite.engine import pipelines  # noqa: E402
from design_suite.engine.refusal import Refused  # noqa: E402
from typing import Any

REPO = project_root()

# The mock-API sidecar directory, resolved once from `pipelines.mockApi` in the
# profile rather than spelled into each engine. It used to be the literal
# "mock_api" in five files; on a project that keeps its mock API elsewhere every
# one of them read an absent file and reported nothing — the exact silence this
# suite forbids. Every other mockapi module imports MOCK_API from here, so the
# fallback name is written down once, in engine/pipelines.DEFAULTS.
def _profile_or_refuse(repo: Path) -> dict:
    """The profile, or a named exit 2. project.profile() raises SystemExit with
    a message, which exits 1 — the findings code — so a mock-API run on a
    project with no profile used to read as "found problems" rather than
    "could not look"."""
    try:
        return profile(repo)
    except SystemExit as exc:
        raise Refused(str(exc.code)) from None


MOCK_API = pipelines.resolve(REPO, _profile_or_refuse(REPO), "mockApi")
CONTRACTS_FILE = MOCK_API / "contracts.json"
CONFIG_FILE = MOCK_API / "config.json"

_PROVIDERS = "providers"


def _load_config() -> dict[str, Any]:
    # Absent config used to surface as a FileNotFoundError traceback (exit 1),
    # which hooks read as "drift found". No config means no mock API is
    # configured here: could not check, exit 2, named.
    if not CONFIG_FILE.is_file():
        raise Refused(
            f"no mock-API config at {CONFIG_FILE} (pipelines.mockApi/config.json) — "
            f"this project has not configured a mock API, so there is nothing to "
            f"audit for drift. Configure one, or do not run the mock-API audits.")
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except ValueError as exc:
        raise Refused(f"{CONFIG_FILE} is not valid JSON: {exc}")
    return {k: v for k, v in data.items() if not k.startswith("_")}


_config = _load_config()

_schema = importlib.import_module(f"{_PROVIDERS}.schema.{_config['schema_provider']}")
_doc = importlib.import_module(f"{_PROVIDERS}.doc.{_config['doc_provider']['kind']}")
_mock = importlib.import_module(f"{_PROVIDERS}.mock.{_config['mock_provider']['kind']}")

API_DOC_FILE = REPO / _config["doc_provider"]["file"]
COLLECTION_FILE = REPO / _config["mock_provider"]["file"]


def mock_server_urls(repo: Path) -> dict[str, str]:
    """`environment -> base URL` of this project's own mock server.

    `generate_openapi.py` used to hold one consumer's actual Postman mock-server
    endpoint in a module constant, so the `servers` block of EVERY generated
    spec pointed at that one project's mock. Not a credential — a Postman mock
    URL is unauthenticated — but a project literal in the universal engine, and
    functionally wrong for every consumer but one: the spec renders a "Try It"
    console that fires real requests at somebody else's server.

    Home is `<pipelines.mockApi>/config.json`, beside `mock_provider`, which is
    where the rest of this pipeline's project-specific wiring already lives and
    is already resolved through `.design-suite/profile.json`'s `pipelines.mockApi`.
    Deliberately NOT a field in `profile.json` itself: that file's own template
    tells the reader never to put a hostname in it, and a mock-server endpoint is
    exactly a hostname. The key is `servers`.

    Takes only a repo and loads its own section — the same shape, for the same
    reason, as `component_shape.design_system_package`: a caller that could pass
    the section would eventually pass the wrong one.

    An empty mapping means "this project has not declared one". Callers must not
    invent a URL to fill the gap; the absence is reported by
    `audit_mock_api.audit_openapi_coverage()` as `openapi_servers_undeclared`,
    so an unconfigured spec cannot read as a configured one.
    """
    path = pipelines.resolve(repo, profile(repo), "mockApi") / "config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    servers = data.get("servers") or {}
    if not isinstance(servers, dict):
        return {}
    return {str(env): str(url) for env, url in servers.items() if url}


def project_name(repo: Path) -> str:
    """This project's own name, for a generated artifact that must title itself.

    Refuses rather than substituting a placeholder. The generated spec's
    `info.title` used to be a hardcoded product name, so every consumer's spec
    announced itself as one particular client's API; a different hardcoded string
    would be the same defect with a new spelling. `project.name` is required by
    profile.schema.json, so a profile without it is broken, not merely terse.
    """
    name = ((profile(repo).get("project") or {}).get("name") or "").strip()
    if not name:
        raise Refused(
            "project.name is not set in .design-suite/profile.json — it is "
            "required by profile.schema.json, and nothing here may guess a "
            "product name on a project's behalf")
    return name


def load_contracts() -> dict[str, Any]:
    data = json.loads(CONTRACTS_FILE.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_fixture(contract: dict[str, Any]) -> dict[str, Any]:
    return json.loads((REPO / contract["fixture"]).read_text())


def _all_records(container: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Flattens a fixture/body into its list of individual records, given a
    contract's shape declaration:
      - "fixture_list_key" set: container[key] is a list of records.
      - "fixture_map_key" set: container[key] is a map of id -> list of
        records (e.g. an archive's tour notes, keyed by guideId) — every
        record across every key is flattened into one list.
      - neither set: the container itself is the one record (flat shape).
    """
    list_key = contract.get("fixture_list_key")
    if list_key is not None:
        return list(container[list_key])
    map_key = contract.get("fixture_map_key")
    if map_key is not None:
        records: list[dict[str, Any]] = []
        for records_list in container[map_key].values():
            records.extend(records_list)
        return records
    return [container]


def envelope_body(fixture: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """The v1 `{data, meta}` envelope (`docs/API_STANDARD.md` §2) wrapping a
    contract's fixture into what the wire actually returns. `meta.page` is
    added for contracts flagged `"paginated": true` in contracts.json (§3) —
    this is computed on the fly from the raw fixture, never stored back to
    disk: the fixture file stays the record-shape source of truth (what
    model-level tests parse directly), while this is what `sync_mock_api.py`
    and `generate_openapi.py` render as the doc/mock/spec example — the one
    place the envelope actually needs to appear.

    Per the static-mock rule (`mock_api/README.md`), the mock doesn't
    actually paginate live — `nextCursor` is always `null` (this response IS
    the whole fixture, so there genuinely is no next page to fetch) and
    `total` equals the record count. A real backend implementing this
    contract would compute both from its actual dataset; the mock's fixture
    already fits in one response, so this is not a simplification so much as
    the correct answer for a one-page-total resource."""
    list_key = contract.get("fixture_list_key")
    if list_key is not None:
        records = fixture[list_key]
        body: dict[str, Any] = {"data": records}
    else:
        map_key = contract.get("fixture_map_key")
        if map_key is not None:
            records = [r for rs in fixture[map_key].values() for r in rs]
            body = {"data": fixture[map_key]}
        else:
            return {"data": fixture}

    if contract.get("paginated"):
        body["meta"] = {
            "page": {"limit": len(records), "total": len(records), "nextCursor": None}
        }
    return body


def fixture_example_item(contract: dict[str, Any]) -> dict[str, Any]:
    """The record used for field-shape checks — the first record under
    whichever shape the contract declares (see _all_records)."""
    return _all_records(load_fixture(contract), contract)[0]


def fixture_all_keys(contract: dict[str, Any]) -> set[str]:
    """Union of field names across every record in the fixture.

    Nullable/optional fields (e.g. a notification's `deepLinkRoute`) may be
    absent from any single record — checking shape against only the first
    item would misreport them as missing from the model or mock. Shape
    checks should compare against the union across all records instead.
    """
    keys: set[str] = set()
    for item in _all_records(load_fixture(contract), contract):
        keys |= set(item.keys())
    return keys


def body_all_keys(contract: dict[str, Any], body: dict[str, Any]) -> set[str]:
    """Same union-of-keys logic as fixture_all_keys(), over an already-
    parsed v1-enveloped response body (the mock's or the doc example's)
    instead of the fixture file. Unwraps `data` first (see envelope_body) —
    every registered contract's actual wire body is the v1 envelope now,
    unlike the fixture file itself, which stays unwrapped."""
    data = body.get("data")
    if contract.get("fixture_map_key") is not None:
        records = [r for v in (data or {}).values() for r in v]
    elif isinstance(data, list):
        records = list(data)
    elif data is not None:
        records = [data]
    else:
        records = []
    keys: set[str] = set()
    for item in records:
        if isinstance(item, dict):
            keys |= set(item.keys())
    return keys


def model_fields(contract: dict[str, Any]) -> list[str]:
    """Field names as read anywhere in the model file, in first-appearance
    order — delegates to the configured schema provider. See
    ${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/providers/schema/dart_fromjson.py
    for the convention this depends on (nested-parser parameter naming)."""
    return _schema.read_fields(REPO / contract["model_file"])


def render_json_block(fixture: dict[str, Any]) -> str:
    return json.dumps(fixture, indent=2)


def find_mock_request(collection: dict[str, Any], folder_name: str, request_name: str):
    return _mock.find_request(collection, folder_name, request_name)


def load_collection() -> dict[str, Any]:
    return _mock.load(COLLECTION_FILE)


def save_collection(collection: dict[str, Any]) -> None:
    _mock.save(COLLECTION_FILE, collection)


def table_field_names(api_doc_text: str, anchor: str) -> list[str]:
    return _doc.read_table_fields(api_doc_text, anchor)
