#!/usr/bin/env python3
"""Generate an OpenAPI 3.0 spec (mock_api/openapi.json) from
mock_api/contracts.json + each contract's fixture, enriched by a hand-authored
overlay (mock_api/openapi_meta.json) — rendered as a single browsable, testable
page via Scalar at docs/api-reference.html (Scalar chosen over Redoc because
Redoc's live-request "Try It" console is a paid-only feature — see
mock_api/OPENAPI.md's "Interactivity requirement" section).

This is a generated artifact alongside the doc example, mock example, and model
test — all sourced from the same fixture, so it can't independently drift the
way a hand-authored spec (or one converted from the Postman collection, which
carries no schema/type info) would. See docs/DECISIONS.md and mock_api/OPENAPI.md.

Two layers, kept strictly separate so the engine stays project-agnostic:

  STRUCTURE (inferred, deterministic) — every path, schema, and property comes
  from the fixtures + generic contract fields (`model_file`, `mock_folder`,
  `fixture_list_key`/`fixture_map_key`, `mock_request`). No Dart coupling.
  Field TYPES are inferred from the fixture's JSON values (no provider captures
  types — the schema provider reads names only). Contracts that share a
  `model_file` collapse to ONE reusable component schema referenced by `$ref`
  from each endpoint's response wrapper (e.g. `archivable_model.dart` powers
  /archive/photographs, /manuscripts, /maps → one `Archivable` schema).

  CONTEXT (curated) — descriptions, enums, formats, tag prose, and the `info`
  block a fixture value can't express live in mock_api/openapi_meta.json and are
  deep-merged on top. The overlay never invents structure; it only annotates
  paths/schemas/properties that the inferred layer already produced. That keeps
  the round-trip equality check in audit_mock_api.py deterministic.

Every registered contract is a GET (the static-mock rule — mutations never
round-trip against a static mock, so they're never registered), so the spec
only ever needs `get` operations.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/generate_openapi.py" [--check]

    --check   Don't write anything; exit 1 if mock_api/openapi.json would
              change. Used by audit_mock_api.py's spec-drift check.

Can also be imported and called in-process from sync_mock_api.py, so a
per-contract sync keeps the spec current too.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_api_common import (MOCK_API, REPO, _all_records, envelope_body,
                             load_contracts, load_fixture, mock_server_urls,
                             project_name)

# MOCK_API, not a literal: the directory comes from `pipelines.mockApi` in the
# profile — see mock_api_common.
OPENAPI_FILE = MOCK_API / "openapi.json"
OPENAPI_META_FILE = MOCK_API / "openapi_meta.json"
MUTATION_CONTRACTS_FILE = MOCK_API / "mutation_contracts.json"


def _rel(path) -> str:
    """Project-relative spelling of a resolved path, for messages a human reads.

    These messages used to hardcode "mock_api/openapi.json" while the code wrote
    wherever the profile said, so on a project that moved the directory the tool
    reported updating a file it had not touched.
    """
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)

# Leaf keys the overlay may set on an inferred property. Deliberately excludes
# "type"/"properties"/"items" — the overlay annotates structure, never redefines
# it (see the module docstring's STRUCTURE vs CONTEXT split).
_PROPERTY_OVERLAY_KEYS = frozenset(
    {"description", "enum", "format", "minimum", "maximum", "example", "deprecated"}
)


def _pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[_\-]", name) if part)


def _schema_name_for(model_file: str) -> str:
    """Reusable component-schema name derived from a model file's basename, so
    contracts sharing a model collapse to one schema. `archivable_model.dart` ->
    `Archivable`, `condition_report_model.dart` -> `ConditionReport`,
    `membership_model.dart` -> `Membership`. Project-agnostic: `model_file` is a
    generic contract field (a TS project would point it at a `.ts` path; the
    basename rule still holds)."""
    base = Path(model_file).stem  # e.g. "archivable_model"
    if base.endswith("_model"):
        base = base[: -len("_model")]
    return _pascal_case(base)


def _infer_schema(value: Any) -> dict[str, Any]:
    """Recursively infers a JSON Schema fragment from a single fixture value.

    Documentation-grade inference, not strict validation: an empty array's items
    are left untyped (`{}`) rather than guessed, and a `null` produces an
    untyped nullable placeholder — there's no signal in one example to do
    better. Object `required` is computed by _infer_object_from_records at the
    top level, not here (a nested object seen once can't tell optional apart
    from required)."""
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        return {"nullable": True}
    if isinstance(value, list):
        return {
            "type": "array",
            "items": _infer_schema(value[0]) if value else {},
        }
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: _infer_schema(v) for k, v in value.items()},
        }
    return {}


def _infer_object_from_records(records: list[Any]) -> dict[str, Any]:
    """Infers ONE object schema from all records that share a model.

    - properties: union of keys across every record (so an optional field
      present in only some records still appears), each inferred from the first
      record that carries a non-null value for it (a typed inference always
      beats a `null` placeholder).
    - required: the intersection — keys present in EVERY record. Present-in-some
      is optional. Pure fixture analysis, no type-source needed.
    Keys are sorted for deterministic, diff-friendly output.
    """
    dict_records = [r for r in records if isinstance(r, dict)]
    presence: dict[str, int] = {}
    prop_schema: dict[str, dict[str, Any]] = {}
    for rec in dict_records:
        for key, val in rec.items():
            presence[key] = presence.get(key, 0) + 1
            current = prop_schema.get(key)
            if current is None or (current == {"nullable": True} and val is not None):
                prop_schema[key] = _infer_schema(val)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {k: prop_schema[k] for k in sorted(prop_schema)},
    }
    total = len(dict_records)
    required = sorted(k for k, count in presence.items() if count == total)
    if required:
        schema["required"] = required
    return schema


def _response_schema(contract: dict[str, Any], ref: str) -> dict[str, Any]:
    """The v1 `{data, meta}` envelope (`docs/API_STANDARD.md` §2) for one
    endpoint, wrapping a `$ref` to the shared item schema under `data`
    according to the contract's declared shape (mirrors
    mock_api_common._all_records/envelope_body). `meta` isn't declared here
    — no registered contract's list needs `meta.page` today."""
    list_key = contract.get("fixture_list_key")
    if list_key is not None:
        return {
            "type": "object",
            "required": ["data"],
            "properties": {"data": {"type": "array", "items": {"$ref": ref}}},
        }
    map_key = contract.get("fixture_map_key")
    if map_key is not None:
        return {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": {"$ref": ref}},
                }
            },
        }
    return {
        "type": "object",
        "required": ["data"],
        "properties": {"data": {"$ref": ref}},
    }


def _summary_for(name: str, contract: dict[str, Any]) -> str:
    anchor = contract.get("api_doc_anchor")
    if anchor:
        # e.g. "#### `GET /care-plan/current`" -> "GET /care-plan/current"
        match = re.search(r"`([^`]+)`", anchor)
        if match:
            return match.group(1)
    return name.replace("_", " ")


def load_overlay() -> dict[str, Any]:
    """The curated context layer. Absent/empty is fine — the generator still
    produces a valid (if terse) spec, so a fresh project needn't author it
    before the pipeline works. `_`-prefixed keys (e.g. `_comment`) are stripped."""
    if not OPENAPI_META_FILE.is_file():
        return {}
    data = json.loads(OPENAPI_META_FILE.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _apply_schema_overlay(schema: dict[str, Any], overlay: dict[str, Any] | None) -> None:
    """Merges curated annotations onto an inferred component schema in place:
    a schema-level `description`, and per-property leaf keys (description, enum,
    format, minimum, …). Only annotates properties that already exist — it can't
    add fields the fixture didn't produce."""
    if not overlay:
        return
    if overlay.get("description"):
        schema["description"] = overlay["description"]
    props = schema.get("properties", {})
    for prop_name, meta in overlay.get("properties", {}).items():
        if prop_name in props:
            props[prop_name].update(
                {k: v for k, v in meta.items() if k in _PROPERTY_OVERLAY_KEYS}
            )


def _apply_response_overlay(responses: dict[str, Any], overlay: dict[str, Any] | None) -> None:
    """Merge curated annotations onto the shared error responses, in place.

    The examples this carries were once hardcoded here — realistic bodies keyed by
    error code, with copy like "Your session has expired." Removing them when this
    engine was made project-agnostic was right: that is a product's voice, and
    every project's differs. But nothing replaced them, so the port silently
    stripped them from the generated spec and left no way to put them back.

    Annotation only, deliberately: a project may add `description`, `examples`, or
    `headers` to a response the engine already produces, and may not invent a new
    response or replace its `schema`. Structure stays inferred, so the round-trip
    equality check in audit_mock_api.py stays deterministic — the same division of
    labour `_apply_schema_overlay` keeps for schemas.
    """
    if not overlay:
        return
    for name, meta in overlay.items():
        target = responses.get(name)
        if target is None:
            # A response the engine does not generate. Ignored rather than added:
            # the overlay annotates, and inventing structure here is how the
            # generated spec and the audit's expectation drift apart.
            continue
        if meta.get("description"):
            target["description"] = meta["description"]
        examples = meta.get("examples")
        if examples:
            body = target.setdefault("content", {}).setdefault("application/json", {})
            body.setdefault("examples", {}).update(examples)
        headers = meta.get("headers")
        if headers:
            target.setdefault("headers", {}).update(headers)


def load_mutation_contracts() -> dict[str, Any]:
    """The hand-authored mutation registry (`mock_api/mutation_contracts.json`)
    — the mutation counterpart to `contracts.json`'s GET registry. Absent is
    fine (empty dict), same as `load_overlay`."""
    if not MUTATION_CONTRACTS_FILE.is_file():
        return {}
    data = json.loads(MUTATION_CONTRACTS_FILE.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _mutation_schema(entry: dict[str, Any], example_key: str, schemas: dict[str, Any]) -> dict[str, Any]:
    """Schema for a mutation's request or response body: a `$ref` to an
    existing component when `<example_key minus '_example'>_ref` names one
    (the mutation returns/accepts the exact shape a GET contract already
    produces), otherwise inferred from the entry's own example. Per
    `entry["partial"]`, a request/response schema for a partial-update PATCH
    doesn't mark every example key `required` — a single example can't tell
    optional apart from required for a partial update."""
    ref_key = example_key.replace("example", "ref")
    ref_name = entry.get(ref_key)
    if ref_name:
        return {"$ref": f"#/components/schemas/{ref_name}"}
    schema = _infer_schema(entry[example_key])
    if not entry.get("partial") and schema.get("type") == "object":
        schema["required"] = sorted(schema.get("properties", {}))
    return schema


def build_mutation_paths(
    paths: dict[str, Any], schemas: dict[str, Any], used_folders: set[str]
) -> None:
    """Adds every hand-authored mutation contract as a path operation,
    merging into `paths` alongside the fixture-inferred GET operations built
    earlier (a path like `/v1/users/me/consents` ends up with both `get` and
    `patch`). Mutations get the same `4XX`/`5XX` -> `ClientError`/
    `ServerError` treatment as GETs; the static-mock rule is otherwise
    unaffected — this only makes the *contract* machine-readable."""
    for name, entry in sorted(load_mutation_contracts().items()):
        operation: dict[str, Any] = {
            "operationId": name,
            "summary": entry.get("summary", name.replace("_", " ")),
            "responses": {
                "4XX": {"$ref": "#/components/responses/ClientError"},
                "5XX": {"$ref": "#/components/responses/ServerError"},
            },
        }
        if entry.get("description"):
            operation["description"] = entry["description"]
        folder = entry.get("mock_folder")
        if folder:
            operation["tags"] = [folder]
            used_folders.add(folder)
        if entry.get("path_params"):
            operation["parameters"] = [
                {
                    "name": param,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
                for param in entry["path_params"]
            ]
        if "request_example" in entry:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": _mutation_schema(entry, "request_example", schemas),
                        "example": entry["request_example"],
                    }
                },
            }
        status = entry.get("response_status", "200")
        response: dict[str, Any] = {"description": "Successful response"}
        if "response_example" in entry or entry.get("response_ref"):
            response["content"] = {
                "application/json": {
                    "schema": _mutation_schema(entry, "response_example", schemas),
                }
            }
            if "response_example" in entry:
                response["content"]["application/json"]["example"] = entry["response_example"]
        operation["responses"] = {status: response, **operation["responses"]}

        paths.setdefault(entry["path"], {})[entry["method"]] = operation


def build_spec() -> dict[str, Any]:
    contracts = load_contracts()
    overlay = load_overlay()

    # Group contracts by model_file so shared models become one reusable schema.
    groups: dict[str, dict[str, Any]] = {}
    name_to_schema: dict[str, str] = {}
    for name, contract in sorted(contracts.items()):
        schema_name = _schema_name_for(contract["model_file"])
        name_to_schema[name] = schema_name
        group = groups.setdefault(
            schema_name, {"model_file": contract["model_file"], "records": []}
        )
        if group["model_file"] != contract["model_file"]:
            raise ValueError(
                f"Schema-name collision '{schema_name}': "
                f"{group['model_file']} vs {contract['model_file']}. "
                "Two different models resolve to the same component name — "
                "rename one model file or extend _schema_name_for."
            )
        group["records"].extend(_all_records(load_fixture(contract), contract))

    schema_overlay = overlay.get("schemas", {})
    schemas: dict[str, Any] = {}
    for schema_name, group in groups.items():
        schemas[schema_name] = _infer_object_from_records(group["records"])
        _apply_schema_overlay(schemas[schema_name], schema_overlay.get(schema_name))

    # One reusable error schema — the structured {"error": {code, message,
    # fields?}} contract every endpoint returns on failure per
    # docs/API_STANDARD.md §9 (see lib/core/network/api_error_mapper.dart).
    schemas["Error"] = {
        "type": "object",
        "required": ["error"],
        "properties": {
            "error": {
                "type": "object",
                "required": ["code", "message"],
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Stable, machine-readable SCREAMING_SNAKE_CASE identifier.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Human-readable error message, safe to show a user or log.",
                    },
                    "fields": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Present only for validation errors (422-class) — maps field name to a human-readable problem description.",
                    },
                },
            }
        },
    }

    # `Error` is hand-built above rather than inferred from a fixture, so it is not
    # in `groups` and the overlay loop never reaches it. Its curated annotations —
    # notably the enum of codes a real backend may return — still belong in the
    # project's overlay like any other. They sit one level down, under `error`,
    # because _apply_schema_overlay only annotates a schema's own top-level
    # `properties`.
    #
    # This call was lost when the engine was ported out of the project repos. The
    # effect was silent and one-directional: regenerating dropped the curated enum
    # and left a generic description, so every run quietly degraded a committed
    # spec that nothing regenerates on a schedule. Restored here, not worked around
    # in the overlay file, because the overlay is project data and this is engine
    # behaviour every project depends on.
    _apply_schema_overlay(
        schemas["Error"]["properties"]["error"], schema_overlay.get("Error")
    )

    op_overlay = overlay.get("operations", {})
    paths: dict[str, Any] = {}
    used_folders: set[str] = set()
    for name, contract in sorted(contracts.items()):
        ref = f"#/components/schemas/{name_to_schema[name]}"
        this_op = op_overlay.get(name, {})
        operation: dict[str, Any] = {
            "operationId": name,
            "summary": this_op.get("summaryOverride") or _summary_for(name, contract),
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": _response_schema(contract, ref),
                            "example": envelope_body(load_fixture(contract), contract),
                        }
                    },
                },
                "4XX": {"$ref": "#/components/responses/ClientError"},
                "5XX": {"$ref": "#/components/responses/ServerError"},
            },
        }
        folder = contract.get("mock_folder")
        if folder:
            operation["tags"] = [folder]
            used_folders.add(folder)
        if this_op.get("description"):
            operation["description"] = this_op["description"]
        paths[contract["mock_request"]] = {"get": operation}

    build_mutation_paths(paths, schemas, used_folders)

    tag_prose = overlay.get("tags", {})
    tags = []
    for folder in sorted(used_folders):
        tag: dict[str, Any] = {"name": folder}
        if tag_prose.get(folder):
            tag["description"] = tag_prose[folder]
        tags.append(tag)

    # Derived from the project's own profile, never a constant: this default used
    # to be one client's product name, so every consumer's generated spec titled
    # itself after that client. The overlay's `info.title` still wins.
    default_info = {
        "title": f"{project_name(REPO)} API Reference",
        "version": "1.0.0",
        "description": (
            f"Generated from {_rel(MOCK_API)}/contracts.json + test/fixtures/*.json, "
            f"enriched by {_rel(OPENAPI_META_FILE)} — do not hand-edit; run "
            "generate_openapi.py. Operations are grouped by resource tag. Every "
            "endpoint may also return a 4xx/5xx error whose body is "
            '`{"error": {"code", "message", "fields"?}}`. See docs/API.md '
            "for the full prose methodology this spec complements."
        ),
    }
    info = {**default_info, **overlay.get("info", {})}

    security_overlay = overlay.get("security", {})
    security_schemes = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": security_overlay.get("description") or (
                "Every request carries an access token, matching the app's real "
                "auth flow — but this mock server does not validate it, so any "
                "string works here."
            ),
        }
    }

    responses = {
        "ClientError": {
            "description": (
                'Client error (4xx) — bad request or resource not found. Body '
                'is `{"error": {"code", "message", "fields"?}}`. Maps to '
                "NetworkException in the app."
            ),
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
        "ServerError": {
            "description": (
                'Server error (5xx). Body is `{"error": {"code", "message"}}`. '
                "Maps to ServerException in the app."
            ),
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
    }

    _apply_response_overlay(responses, overlay.get("responses"))

    # `servers` is emitted only for the environments this project declares in
    # <pipelines.mockApi>/config.json — see mock_api_common.mock_server_urls for
    # why it is read rather than held here. An undeclared server omits the key
    # (OpenAPI 3 permits that) rather than inventing a URL; the omission is
    # REPORTED by audit_mock_api's `openapi_servers_undeclared` check, so it
    # cannot read as configured.
    servers = [
        {"url": url, "description": env}
        for env, url in sorted(mock_server_urls(REPO).items())
    ]

    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": info,
        **({"servers": servers} if servers else {}),
        "tags": tags,
        "security": [{"bearerAuth": []}],
        "paths": dict(sorted(paths.items())),
        "components": {
            "schemas": dict(sorted(schemas.items())),
            "responses": responses,
            "securitySchemes": security_schemes,
        },
    }
    external_docs = overlay.get("externalDocs")
    if external_docs:
        spec["externalDocs"] = external_docs
    return spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    spec = build_spec()
    new_text = json.dumps(spec, indent=2) + "\n"
    old_text = OPENAPI_FILE.read_text() if OPENAPI_FILE.is_file() else None
    changed = old_text != new_text

    if args.check:
        if changed:
            print(f"[generate-openapi] {_rel(OPENAPI_FILE)} is OUT OF SYNC")
            return 1
        print(f"[generate-openapi] {_rel(OPENAPI_FILE)} is in sync")
        return 0

    if changed:
        OPENAPI_FILE.write_text(new_text)
        print(f"Updated {_rel(OPENAPI_FILE)} ({len(spec['paths'])} paths)")
    else:
        print("[generate-openapi] already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
