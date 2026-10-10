#!/usr/bin/env python3
"""Report-only drift check across a contract's four artifacts: the Dart
model's fromJson field names (shape source of truth), the fixture's example
values, docs/API.md's field table + example block, and the Postman
collection's example response body.

Never edits a contract artifact (model, fixture, docs, collection) — see
sync_mock_api.py for the generator. It DOES write exactly one file on every
run: its findings list, to `--out` (default `.design-suite/mock-api-findings.json`,
ignored by the .gitignore bin/init.py scaffolds there), merged so a scoped run
replaces only the contracts it re-audited. With `--findings` it also writes a
findings envelope. It used to default to `<pipelines.mockApi>/findings.json` at
the project root — a tracked file every run dirtied; `--out` still wins.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/audit_mock_api.py" [contract-name ...] [--out .design-suite/mock-api-findings.json]

    With no contract name, audits every contract in mock_api/contracts.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from design_suite.project import profile, project_root  # noqa: E402
from design_suite.engine import pipelines  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_openapi import OPENAPI_FILE, _rel, build_spec, load_overlay
from mock_api_common import (
    API_DOC_FILE,
    CONFIG_FILE,
    _all_records,
    body_all_keys,
    envelope_body,
    find_mock_request,
    fixture_all_keys,
    load_collection,
    load_contracts,
    load_fixture,
    model_fields,
    table_field_names,
)


def _walk_postman_items(items):
    """Yields every leaf request item in a Postman collection tree (folders
    have an "item" key holding children; requests don't)."""
    for it in items:
        if "item" in it:
            yield from _walk_postman_items(it["item"])
        else:
            yield it


def audit_postman_mock_matching() -> list[dict]:
    """Repo-wide check (not per-contract) — Postman's mock server matches an
    incoming request against each saved response's OWN embedded
    `originalRequest` (method + url), not the parent request item you edit
    in the Postman UI. A path-rewrite pass that updates only the parent
    (e.g. adding a `/v1` prefix) silently leaves `originalRequest` stale —
    the collection looks correct in Postman's editor, `sync_mock_api.py`
    and `generate_openapi.py` both stay green (neither reads
    `originalRequest`), and the drift is invisible until someone actually
    builds a live mock server from the collection and every request 404s
    with Postman's own "no matching requests" error.

    Runs over every leaf item in the collection — registered GET contracts
    AND mutations AND anything else — since the bug can hit any of them
    equally and mutations aren't covered by the per-contract loop above."""
    findings: list[dict] = []
    collection = load_collection()
    for it in _walk_postman_items(collection.get("item", [])):
        req = it.get("request")
        if not req:
            continue
        req_url = req.get("url", {})
        req_raw = req_url.get("raw") if isinstance(req_url, dict) else req_url
        req_method = req.get("method")
        for resp in it.get("response", []):
            orig = resp.get("originalRequest", {})
            orig_url = orig.get("url", {})
            orig_raw = orig_url.get("raw") if isinstance(orig_url, dict) else orig_url
            orig_method = orig.get("method")
            if orig_raw != req_raw or orig_method != req_method:
                findings.append(
                    {
                        "contract": "_postman_collection",
                        "check": "postman_original_request_stale",
                        "severity": "critical",
                        "detail": (
                            f"{it.get('name')!r} example {resp.get('name')!r}: "
                            f"originalRequest is {orig_method} {orig_raw!r} but the "
                            f"parent request is {req_method} {req_raw!r} — Postman's "
                            "mock server will match on the stale originalRequest, not "
                            "what the editor shows. Re-save this example (or run the "
                            "originalRequest-sync fix) before creating a mock server."
                        ),
                    }
                )
    return findings


# Matches a Postman variable/vault reference (`{{name}}` or `{{vault:name}}`)
# whose inner name looks credential-shaped. Deliberately broad (should_fix,
# not critical) — a heuristic for a human to glance at, not a hard rule,
# since a variable named e.g. `{{access_token_field_name}}` used as a plain
# label wouldn't actually be a leak. Doesn't match our own known-safe
# placeholders (`{{url}}`, plain JWT-shaped example strings, `<...>` angle-
# bracket placeholders) since those never contain these keywords.
_CREDENTIAL_VAR_PATTERN = re.compile(
    r"\{\{\s*(?:vault:)?[^}]*(key|secret|token|password|credential)[^}]*\}\}",
    re.IGNORECASE,
)

# Known-safe references the pattern would otherwise flag. `{{access_token}}` is
# the collection-wide Bearer variable every request's Authorization header
# carries by design (see mock_api/OPENAPI.md's interactivity requirement) — a
# placeholder the reader fills in, never a baked-in secret. Match on the inner
# name only, case-insensitively.
_SAFE_CREDENTIAL_VARS = {"access_token"}


def _inner_var_name(match: "re.Match") -> str:
    return match.group(0).strip("{} ").removeprefix("vault:").strip().lower()


def _scan_value_for_credential_refs(value, where: str, findings: list[dict]) -> None:
    if isinstance(value, str):
        for match in _CREDENTIAL_VAR_PATTERN.finditer(value):
            if _inner_var_name(match) in _SAFE_CREDENTIAL_VARS:
                continue
            findings.append(
                {
                    "contract": "_postman_collection",
                    "check": "postman_credential_variable_reference",
                    "severity": "should_fix",
                    "detail": (
                        f"{where}: found {match.group(0)!r} — a Postman variable/vault "
                        "reference whose name looks credential-shaped, sitting in a "
                        "saved request/response value. If this resolves to a real "
                        "secret (e.g. a Supabase service-role key), it doesn't belong "
                        "in mock example data — replace with a plain placeholder "
                        "string instead."
                    ),
                }
            )
    elif isinstance(value, dict):
        for v in value.values():
            _scan_value_for_credential_refs(v, where, findings)
    elif isinstance(value, list):
        for v in value:
            _scan_value_for_credential_refs(v, where, findings)


def audit_postman_credential_refs() -> list[dict]:
    """Repo-wide check — scans every saved request/response in the Postman
    collection for a variable reference that looks like it resolves to a
    real credential (see `_CREDENTIAL_VAR_PATTERN`). Motivated by finding a
    live `{{supabase_service_role_api_key_...}}` reference sitting in a
    saved mock response's `accessToken` field — this class of thing is easy
    to introduce by accident (autofill, copy-pasting a real request) and
    easy to miss since the collection still "looks" fine in the Postman UI
    and the mock still serves fine (the reference either resolves silently
    to the real secret, or renders as a literal unresolved `{{...}}` string
    depending on scope — neither is what a mock example should contain)."""
    findings: list[dict] = []
    collection = load_collection()
    for it in _walk_postman_items(collection.get("item", [])):
        req = it.get("request")
        if req:
            _scan_value_for_credential_refs(req, f"{it.get('name')!r} request", findings)
        for resp in it.get("response", []):
            _scan_value_for_credential_refs(
                resp.get("body"), f"{it.get('name')!r} example {resp.get('name')!r} body", findings
            )
            _scan_value_for_credential_refs(
                resp.get("header"),
                f"{it.get('name')!r} example {resp.get('name')!r} headers",
                findings,
            )
    return findings


# --- Showing both sides of a difference -------------------------------------
#
# These exist so a "these two disagree" finding can be actionable WITHOUT naming
# a direction to repair in. See issue #116: the previous wording pointed at a
# one-way propagation script, and a reader who followed it lost data whenever the
# side the script treats as authoritative was the rotted one. The honest
# replacement is not a vaguer message — it is a more specific one that shows what
# each side actually holds and leaves the judgement where it belongs.

_MAX_SHOWN = 8


def _side_only(label: str, a: set, b: set) -> str:
    """Render the keys `a` has and `b` lacks, or '' when there are none."""
    extra = sorted(a - b)
    if not extra:
        return ""
    shown = extra[:_MAX_SHOWN]
    suffix = f" (+{len(extra) - len(shown)} more)" if len(extra) > len(shown) else ""
    return f"; {label}: {shown}{suffix}"


def _brief(value: object, limit: int = 60) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _value_diffs(left: object, right: object, left_name: str, right_name: str) -> str:
    """A compact, direction-free listing of where two JSON bodies disagree.

    Walks both structures in parallel and reports each differing leaf as
    `path: <left_name>=... / <right_name>=...`. Naming both sides is the point:
    a reader can see that one side holds a real value and the other holds null
    or a placeholder, which is exactly the information a one-way "just sync it"
    instruction destroyed.
    """
    diffs: list[str] = []

    def walk(a: object, b: object, path: str) -> None:
        if len(diffs) > _MAX_SHOWN:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                child = f"{path}.{key}" if path else key
                if key not in a:
                    diffs.append(f"{child}: absent in {left_name}, "
                                 f"{right_name}={_brief(b[key])}")
                elif key not in b:
                    diffs.append(f"{child}: {left_name}={_brief(a[key])}, "
                                 f"absent in {right_name}")
                else:
                    walk(a[key], b[key], child)
            return
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diffs.append(f"{path or '(root)'}: {left_name} has {len(a)} item(s), "
                             f"{right_name} has {len(b)}")
                return
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
            return
        if a != b:
            diffs.append(f"{path or '(root)'}: {left_name}={_brief(a)}, "
                         f"{right_name}={_brief(b)}")

    walk(left, right, "")
    if not diffs:
        return ""
    shown = diffs[:_MAX_SHOWN]
    suffix = f"; +{len(diffs) - len(shown)} more difference(s)" if len(diffs) > len(shown) else ""
    return " — " + "; ".join(shown) + suffix


def audit_openapi_spec() -> list[dict]:
    """One repo-wide check (not per-contract) — the generated OpenAPI spec
    is a single combined document, unlike the per-contract doc/mock
    examples, so it's audited once per run rather than folded into
    audit_contract()."""
    expected = json.dumps(build_spec(), indent=2) + "\n"
    actual = OPENAPI_FILE.read_text() if OPENAPI_FILE.is_file() else None
    if actual == expected:
        return []
    return [
        {
            "contract": "_openapi_spec",
            "check": "openapi_vs_fixtures",
            "severity": "should_fix",
            # Name the narrow, purely-derivational repair, not the skill that
            # wraps it. /sync-mock-api demands a contract name and rewrites that
            # contract's doc and mock example from its fixture *before* it
            # regenerates the spec — so pointing at the skill turns a
            # spec-regeneration finding into a fixture-wins propagation the
            # finding never measured. generate_openapi.py alone is the fix here.
            "detail": (
                f"{OPENAPI_FILE.name} is out of sync with contracts.json/fixtures — "
                "regenerate it with generate_openapi.py (--check to see the drift first)"
            ),
        }
    ]


# Scalar property names that almost always denote a closed value set. A
# string property with one of these names but no `enum` in the overlay is very
# likely under-documented — flagged as should_fix so coverage grows over time.
_ENUMISH_NAMES = frozenset({"type", "status", "source", "state", "cadence", "role"})


def audit_openapi_coverage() -> list[dict]:
    """Repo-wide checks that the curated overlay (mock_api/openapi_meta.json)
    stays complete AND honest as fixtures evolve. Non-blocking (should_fix):

    - COVERAGE: every operation should carry a description; every tag (folder)
      should carry prose; enum-ish scalar properties should declare their enum.
    - ORPHANS: every overlay key should still point at a real contract, tag,
      schema, or property — a fixture rename shouldn't silently strand prose.

    Only runs on a full audit (no per-contract filter) — it reasons about the
    whole generated spec, not one endpoint."""
    findings: list[dict] = []
    spec = build_spec()
    overlay = load_overlay()

    contract_names = set(load_contracts())
    used_folders = {t["name"] for t in spec.get("tags", [])}
    schema_names = {n for n in spec["components"]["schemas"] if n != "Error"}
    schema_props = {
        n: set(spec["components"]["schemas"][n].get("properties", {}).keys())
        for n in schema_names
    }

    def finding(check: str, detail: str) -> dict:
        return {
            "contract": "_openapi_meta",
            "check": check,
            "severity": "should_fix",
            "detail": detail,
        }

    # --- coverage ---
    # The spec omits `servers` when the project declares none (see
    # generate_openapi.build_spec). Omission has to be REPORTED, or a spec whose
    # "Try It" console has nowhere to send a request looks exactly like one that
    # is correctly configured — the silence this suite forbids. It used to look
    # configured for everyone, because the engine held one client's mock URL.
    if not spec.get("servers"):
        findings.append(
            finding(
                "openapi_servers_undeclared",
                "the spec declares no servers, so its 'Try It' console has no "
                "base URL — add a `servers` map ({environment: url}) to "
                f"{_rel(CONFIG_FILE)}",
            )
        )

    for path, item in spec["paths"].items():
        for op in item.values():
            if not op.get("description"):
                findings.append(
                    finding(
                        "openapi_op_undocumented",
                        f"operation {op['operationId']} ({path}) has no description — "
                        f"add operations.{op['operationId']}.description to openapi_meta.json",
                    )
                )
    for folder in sorted(used_folders):
        if not overlay.get("tags", {}).get(folder):
            findings.append(
                finding(
                    "openapi_tag_undocumented",
                    f"tag '{folder}' has no description — add tags.{folder} to openapi_meta.json",
                )
            )
    for schema_name in sorted(schema_names):
        props = spec["components"]["schemas"][schema_name].get("properties", {})
        for prop_name, prop in props.items():
            if (
                prop_name in _ENUMISH_NAMES
                and prop.get("type") == "string"
                and "enum" not in prop
            ):
                findings.append(
                    finding(
                        "openapi_enum_missing",
                        f"{schema_name}.{prop_name} looks like a closed value set but "
                        f"declares no enum — add schemas.{schema_name}.properties.{prop_name}.enum",
                    )
                )

    # --- orphans (overlay pointing at structure that no longer exists) ---
    for op_name in overlay.get("operations", {}):
        if op_name not in contract_names:
            findings.append(
                finding(
                    "openapi_meta_orphan",
                    f"operations.{op_name} in openapi_meta.json is not a known contract",
                )
            )
    for tag_name in overlay.get("tags", {}):
        if tag_name not in used_folders:
            findings.append(
                finding(
                    "openapi_meta_orphan",
                    f"tags.{tag_name} in openapi_meta.json matches no endpoint's mock_folder",
                )
            )
    for schema_name, schema_meta in overlay.get("schemas", {}).items():
        if schema_name not in schema_names:
            findings.append(
                finding(
                    "openapi_meta_orphan",
                    f"schemas.{schema_name} in openapi_meta.json matches no generated schema",
                )
            )
            continue
        for prop_name in schema_meta.get("properties", {}):
            if prop_name not in schema_props[schema_name]:
                findings.append(
                    finding(
                        "openapi_meta_orphan",
                        f"schemas.{schema_name}.properties.{prop_name} in openapi_meta.json "
                        "matches no inferred property",
                    )
                )

    return findings


# ─── docs/API_STANDARD.md conformance (report-only — see that doc's "What
# conforms and what doesn't, mechanically" section) ────────────────────────

_SNAKE_CASE_KEY = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")
# Pre-formatted display dates, e.g. "Jul 18, 2026" / "May 15, 2026" — the
# standard requires ISO-8601 instead (see API_STANDARD.md §5).
_DISPLAY_DATE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")
# Pre-formatted currency strings, e.g. "$299" / "$149.95" — the standard
# requires a {amount, currency} object instead (see API_STANDARD.md §6).
_DISPLAY_MONEY = re.compile(r"^\$[\d,]+(\.\d{2})?$")

# API_STANDARD.md §8: <three-letter-prefix>_<opaque-token>. The token itself
# may contain further underscores (e.g. a readable slug-as-token,
# `prv_sarah_chen`) — only the prefix/token separator is significant.
_ID_FORMAT = re.compile(r"^[a-z]{3}_[A-Za-z0-9_]+$")
# §3's own carve-out: small/bounded resources don't need meta.page. Records
# beyond this count are the practical line between "a user's own consent
# flags" and "a list that grows without bound in a real system."
_PAGINATION_RECORD_THRESHOLD = 10


def _walk_standard_violations(value, path: str, findings: list[tuple[str, str]]) -> None:
    """Recursively scans a fixture value for casing/date/money violations,
    collecting (kind, path) pairs. `path` is a dotted breadcrumb for the
    finding detail, not a real JSON path expression."""
    if isinstance(value, dict):
        for key, sub in value.items():
            if _SNAKE_CASE_KEY.match(key):
                findings.append(("snake_case_key", f"{path}.{key}" if path else key))
            _walk_standard_violations(sub, f"{path}.{key}" if path else key, findings)
    elif isinstance(value, list):
        for item in value:
            _walk_standard_violations(item, path, findings)
    elif isinstance(value, str):
        if _DISPLAY_DATE.match(value):
            findings.append(("display_date", path))
        elif _DISPLAY_MONEY.match(value):
            findings.append(("display_money", path))


def audit_api_standard(name: str, contract: dict) -> list[dict]:
    """Checks one contract's fixture + path against docs/API_STANDARD.md.
    Non-blocking (should_fix) by design — see that doc's "What conforms and
    what doesn't, mechanically" section: the whole surface is expected to
    fail this today. It exists to give the Phase 2 migration a mechanical,
    per-contract inventory, not to gate anything before that migration
    happens."""
    findings: list[dict] = []
    fixture = load_fixture(contract)

    violations: list[tuple[str, str]] = []
    _walk_standard_violations(fixture, "", violations)
    for kind, where in violations:
        findings.append(
            {
                "contract": name,
                "check": f"api_standard_{kind}",
                "severity": "should_fix",
                "detail": {
                    "snake_case_key": f"fixture key '{where}' is snake_case — API_STANDARD.md §4 requires camelCase",
                    "display_date": f"fixture value at '{where}' is a pre-formatted display date — API_STANDARD.md §5 requires ISO-8601",
                    "display_money": f"fixture value at '{where}' is a pre-formatted currency string — API_STANDARD.md §6 requires {{amount, currency}}",
                }[kind],
            }
        )

    request_path = contract.get("mock_request", "")
    if not request_path.startswith("/v1"):
        findings.append(
            {
                "contract": name,
                "check": "api_standard_unversioned_path",
                "severity": "should_fix",
                "detail": f"'{request_path}' has no /v1 prefix — API_STANDARD.md §1",
            }
        )

    if "data" not in envelope_body(fixture, contract):
        # Should be unreachable — envelope_body always produces a "data"
        # key — but kept as a regression guard rather than removed, in case
        # a future contract shape isn't handled by envelope_body.
        findings.append(
            {
                "contract": name,
                "check": "api_standard_envelope",
                "severity": "should_fix",
                "detail": (
                    "envelope_body(fixture, contract) produced no 'data' key — "
                    "API_STANDARD.md §2 requires the {data, meta} envelope"
                ),
            }
        )

    records = _all_records(fixture, contract)
    is_list_shaped = contract.get("fixture_list_key") or contract.get("fixture_map_key")
    if (
        is_list_shaped
        and len(records) > _PAGINATION_RECORD_THRESHOLD
        and not contract.get("paginated")
    ):
        findings.append(
            {
                "contract": name,
                "check": "api_standard_pagination_missing",
                "severity": "should_fix",
                "detail": (
                    f"{len(records)} records, no meta.page and no \"paginated\": true "
                    f"in contracts.json — API_STANDARD.md §3 requires cursor-based "
                    f"pagination on lists that grow unbounded"
                ),
            }
        )

    seen_bad_ids: set[str] = set()
    for record in records:
        record_id = record.get("id")
        if isinstance(record_id, str) and not _ID_FORMAT.match(record_id) and record_id not in seen_bad_ids:
            seen_bad_ids.add(record_id)
            findings.append(
                {
                    "contract": name,
                    "check": "api_standard_id_format",
                    "severity": "should_fix",
                    "detail": (
                        f"id '{record_id}' doesn't match "
                        f"<three-letter-prefix>_<opaque-token> — API_STANDARD.md §8"
                    ),
                }
            )

    return findings


# --- Optional fields and the conditions that make them expected --------------
#
# Issue #117, measured on a real consumer. `model_vs_fixture` / `model_vs_mock`
# reported a *critical* finding for every model field absent from the fixture,
# with no notion of whether the field is optional or whether any record in that
# fixture could carry one. A model's `int? weekday` is only ever set on items
# with `cadence: "weekly"`; on a contract whose fixture holds no weekly item at
# all, the pair of criticals was unfixable noise — there is no edit to that
# fixture that resolves it short of inventing a record. A critical nobody can
# act on is how a reader learns to skim the whole list.
#
# The conditioning predicate is DECLARED, never inferred. Inferring "weekday
# matters when cadence == weekly" from source is exactly the hard part, and
# getting it wrong would buy a second false-positive mode to replace the first.
# A project that declares nothing keeps today's behaviour, so this change
# silences nothing on its own — which is the point. The declaration lives on
# the contract in `contracts.json`:
#
#     "optional_fields": {
#       "weekday": {"when": {"field": "cadence", "equals": "weekly"},
#                   "why": "only weekly items carry a due weekday"},
#       "note":    {}
#     }
#
# `{}` means unconditionally optional: absence is still reported, but at
# `should_fix` rather than `critical` (issue #117 option 2). A `when` predicate
# means absence is `critical` only when at least one record on that side
# actually satisfies the predicate — otherwise the field was never exercised,
# and the run says so at `fyi` ONCE for the field rather than twice, once per
# direction (option 3).
#
# That `fyi` is not decoration. A check that quietly stops checking is
# indistinguishable from a check that passed, which is this repo's governing
# failure; the not-exercised notice is what keeps the skip visible. Do not
# "tidy" it into silence.

_WHEN_KEYS = frozenset({"field", "equals", "in"})


class ContractDeclarationError(Exception):
    """A contract's `optional_fields` block cannot be understood.

    Raised, never swallowed: a malformed declaration must refuse (exit 2), not
    degrade to "no field is optional" (which over-reports) nor to "every field
    is optional" (which under-reports). Cannot-determine is a refusal.
    """


def optional_fields(name: str, contract: dict) -> dict[str, dict | None]:
    """`{field: when-predicate-or-None}` for a contract, validated.

    `None` is an unconditionally-optional field; a dict is its predicate.
    Anything this function cannot fully understand raises rather than being
    dropped — see ContractDeclarationError.
    """
    raw = contract.get("optional_fields")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ContractDeclarationError(
            f"contract {name!r}: 'optional_fields' must be an object mapping "
            f"field name -> {{}} or {{\"when\": ...}}, got {type(raw).__name__}")
    out: dict[str, dict | None] = {}
    for field, spec in raw.items():
        if not isinstance(spec, dict):
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}] must be an "
                f"object, got {type(spec).__name__}")
        unknown = set(spec) - {"when", "why"}
        if unknown:
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}] has unknown "
                f"key(s) {sorted(unknown)} — only 'when' and 'why' are understood")
        when = spec.get("when")
        if when is None:
            out[field] = None
            continue
        if not isinstance(when, dict):
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}].when must be an "
                f"object, got {type(when).__name__}")
        unknown = set(when) - _WHEN_KEYS
        if unknown:
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}].when has unknown "
                f"key(s) {sorted(unknown)} — understood: {sorted(_WHEN_KEYS)}")
        if "field" not in when:
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}].when needs a "
                f"'field' naming the conditioning field")
        if ("equals" in when) == ("in" in when):
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}].when needs "
                f"exactly one of 'equals' or 'in'")
        if "in" in when and not isinstance(when["in"], list):
            raise ContractDeclarationError(
                f"contract {name!r}: optional_fields[{field!r}].when.in must be "
                f"a list")
        out[field] = when
    return out


def _predicate_holds(record: object, when: dict) -> bool:
    """Whether one record is a case that would carry the optional field."""
    if not isinstance(record, dict):
        return False
    value = record.get(when["field"])
    if "equals" in when:
        return value == when["equals"]
    return value in when["in"]


def _body_records(contract: dict, body: dict) -> list:
    """The individual records inside an already-parsed v1-enveloped body.

    The record-list counterpart to mock_api_common.body_all_keys(), which
    already does this unwrapping but only returns the union of key names — the
    predicate needs the records themselves, not their key set.
    """
    data = body.get("data")
    if contract.get("fixture_map_key") is not None:
        return [r for v in (data or {}).values() for r in v]
    if isinstance(data, list):
        return list(data)
    if data is not None:
        return [data]
    return []


def _exercising(records: list, when: dict) -> int:
    """How many records satisfy `when` — i.e. could legitimately carry the field."""
    return sum(1 for r in records if _predicate_holds(r, when))


def _absence_finding(name: str, check: str, field: str, when: dict | None,
                     exercising: int, where: str) -> dict | None:
    """The finding for `field` being absent from `where`, at the severity its
    declaration earns — or None when the field was never exercised there, in
    which case the caller emits one `fyi` instead of one finding per direction."""
    if when is None:
        # Declared optional with no condition: still reported, because absence
        # is still information, but it is not a contract break (#117 option 2).
        return {
            "contract": name,
            "check": check,
            "severity": "should_fix",
            "detail": (f"optional model field '{field}' has no value in the "
                       f"{where} — declared optional, so not a contract break, "
                       f"but nothing in the {where} exercises it"),
        }
    if exercising == 0:
        return None
    return {
        "contract": name,
        "check": check,
        "severity": "critical",
        "detail": (
            f"model field '{field}' is absent from the {where}, but "
            f"{exercising} record(s) there satisfy its declared condition "
            f"(expected when {json.dumps(when, sort_keys=True)})"),
    }


def audit_contract(name: str, contract: dict) -> list[dict]:
    findings = []
    fields = model_fields(contract)
    fixture = load_fixture(contract)
    # Union across every fixture record, not just the first — nullable
    # fields (e.g. a notification's optional deepLinkRoute) may be absent
    # from any single record without being missing from the contract.
    fixture_keys = fixture_all_keys(contract)
    anchor = contract.get("api_doc_anchor")
    # Contracts with no anchor (e.g. Library — the fixture is too large to
    # usefully inline in docs/API.md) document a hand-written representative
    # example instead; skip doc-table/doc-example checks entirely for them
    # rather than flagging every field as "undocumented".
    documented = set(table_field_names(API_DOC_FILE.read_text(), anchor)) if anchor else set(fields)

    collection = load_collection()
    req = find_mock_request(collection, contract["mock_folder"], contract["mock_request"])
    mock_keys: set[str] = set()
    if req is not None:
        try:
            mock_body = json.loads(req["response"][0]["body"])
            mock_keys = body_all_keys(contract, mock_body)
        except Exception:
            findings.append(
                {
                    "contract": name,
                    "check": "mock_body_parse",
                    "severity": "critical",
                    "detail": "Postman example body is not valid JSON matching the fixture shape",
                }
            )

    # Issue #117. Declared per contract, validated, never inferred — a
    # malformed block raises out of here and main() turns it into a refusal.
    optional = optional_fields(name, contract)
    fixture_records = _all_records(fixture, contract)
    mock_records: list = []
    if mock_keys:
        try:
            mock_records = _body_records(contract, json.loads(req["response"][0]["body"]))
        except Exception:
            mock_records = []

    for field in fields:
        is_optional = field in optional
        when = optional.get(field)
        fixture_exercising = _exercising(fixture_records, when) if when else 0
        mock_exercising = _exercising(mock_records, when) if when else 0
        absent_from_fixture = field not in fixture_keys
        absent_from_mock = bool(mock_keys) and field not in mock_keys

        if not is_optional:
            # Required field: unchanged behaviour, deliberately. #117 is about
            # optional fields; a genuinely missing required field is still a
            # contract break and must still gate.
            if absent_from_fixture:
                findings.append({
                    "contract": name,
                    "check": "model_vs_fixture",
                    "severity": "critical",
                    "detail": f"model field '{field}' has no value in the fixture",
                })
            if absent_from_mock:
                findings.append({
                    "contract": name,
                    "check": "model_vs_mock",
                    "severity": "critical",
                    "detail": f"model field '{field}' is missing from the Postman example",
                })
        else:
            reports = []
            if absent_from_fixture:
                reports.append(_absence_finding(
                    name, "model_vs_fixture", field, when, fixture_exercising, "fixture"))
            if absent_from_mock:
                reports.append(_absence_finding(
                    name, "model_vs_mock", field, when, mock_exercising,
                    "Postman example"))
            real = [r for r in reports if r is not None]
            findings.extend(real)
            if reports and not real:
                # Conditionally-optional and nothing on either side could carry
                # it. Not a finding — but say so out loud, once, rather than
                # letting a skipped check read as a passed one.
                findings.append({
                    "contract": name,
                    "check": "optional_field_not_exercised",
                    "severity": "fyi",
                    "detail": (
                        f"optional model field '{field}' is absent, and no record "
                        f"satisfies its declared condition "
                        f"({json.dumps(when, sort_keys=True)}) — nothing here "
                        f"could carry one, so its absence was NOT checked "
                        f"rather than checked and found clean"),
                })

        if field not in documented:
            findings.append(
                {
                    "contract": name,
                    "check": "model_vs_doc_table",
                    "severity": "should_fix",
                    "detail": f"model field '{field}' is not documented in the docs/API.md table",
                }
            )

    for field in fixture_keys - set(fields):
        findings.append(
            {
                "contract": name,
                "check": "fixture_vs_model",
                "severity": "should_fix",
                "detail": f"fixture has field '{field}' the model never reads — stale or model is behind",
            }
        )

    if mock_keys and mock_keys != fixture_keys:
        findings.append(
            {
                "contract": name,
                "check": "mock_vs_fixture",
                "severity": "critical",
                # A differ-finding must not name a one-way repair. This check
                # measures that two sides disagree; it cannot measure which side
                # is right, because that is a judgement about intent. The old
                # text ended "run sync_mock_api.py <name>", and sync propagates
                # fixture -> mock unconditionally: where the fixture was the
                # rotted side, following this finding DELETED correct fields from
                # the mock (issue #116, measured on a real consumer). Show both
                # sides, name no direction. Do not re-add a repair command here.
                "detail": (
                    f"Postman example keys {sorted(mock_keys)} differ from fixture "
                    f"keys {sorted(fixture_keys)}"
                    f"{_side_only('only in mock', mock_keys, fixture_keys)}"
                    f"{_side_only('only in fixture', fixture_keys, mock_keys)}"
                    ". Update whichever one is out of date."
                ),
            }
        )

    if req is not None and not any(f["check"] == "mock_body_parse" for f in findings):
        try:
            mock_body = json.loads(req["response"][0]["body"])
            if mock_body != envelope_body(fixture, contract):
                findings.append(
                    {
                        "contract": name,
                        "check": "mock_vs_fixture_values",
                        "severity": "critical",
                        # No repair command, deliberately. This finding proves a
                        # disagreement, not an authority: whichever side rotted
                        # is a judgement about intent that this check cannot
                        # make. Naming a one-way sync here once deleted correct
                        # values from the mock (#116). Show both sides instead.
                        "detail": (
                            "Postman example values differ from the fixture"
                            + _value_diffs(mock_body, envelope_body(fixture, contract),
                                           "mock", "fixture")
                            + ". Update whichever one is out of date."
                        ),
                    }
                )
        except Exception:
            pass

    idx = -1
    api_doc_text = ""
    if anchor:
        api_doc_text = API_DOC_FILE.read_text()
        idx = api_doc_text.find(anchor)
    if idx != -1:
        section = api_doc_text[idx:]
        fence_start = section.find("```json")
        if fence_start != -1:
            fence_end = section.find("```", fence_start + len("```json"))
            block_text = section[fence_start + len("```json\n") : fence_end]
            try:
                doc_example = json.loads(block_text)
                if doc_example != envelope_body(fixture, contract):
                    findings.append(
                        {
                            "contract": name,
                            "check": "doc_vs_fixture_values",
                            "severity": "critical",
                            # Same rule as the two findings above: a differ
                            # finding names no direction of repair. The doc
                            # block and the fixture disagree; which of them is
                            # stale is not something this check can observe, and
                            # asserting it by naming a one-way sync is how #116
                            # lost data. Show both sides, decide nothing.
                            "detail": (
                                "the API document's example block differs from the fixture"
                                + _value_diffs(doc_example,
                                               envelope_body(fixture, contract),
                                               "doc", "fixture")
                                + ". Update whichever one is out of date."
                            ),
                        }
                    )
            except Exception:
                findings.append(
                    {
                        "contract": name,
                        "check": "doc_example_parse",
                        "severity": "critical",
                        "detail": "docs/API.md's example block under this anchor is not valid JSON",
                    }
                )

    return findings


def _load_existing_findings(path: Path) -> list[dict]:
    """Whatever a previous run already wrote at `path`, or [] if there's
    nothing there yet or it isn't readable JSON. Used only to preserve other
    contracts' entries across a scoped run — never treated as ground truth
    for anything this run itself measures."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


# Pseudo-contract keys used by the repo-wide (not per-contract) checks. A
# full audit always recomputes all of these from scratch, so they're treated
# as "owned by this run" the same way a named contract is.
_REPO_WIDE_CONTRACT_KEYS = {
    "_postman_collection", "_openapi_spec", "_openapi_meta",
}


# Inside .design-suite/ like every other audit's raw report, where the scaffolded
# .gitignore covers it. Not under findings/ (that holds the common envelopes).
DEFAULT_OUT = ".design-suite/mock-api-findings.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contracts", nargs="*")
    parser.add_argument("--out", default=None,
                        help=f"defaults to {DEFAULT_OUT}")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(bare flag uses the default path)")
    args = parser.parse_args()

    all_contracts = load_contracts()
    names = args.contracts or list(all_contracts)

    all_findings: list[dict] = []
    for name in names:
        if name not in all_contracts:
            print(f"Unknown contract {name!r}. Known: {list(all_contracts)}")
            return 2
        try:
            all_findings.extend(audit_contract(name, all_contracts[name]))
        except ContractDeclarationError as exc:
            # Exit 2, not 0 and not 1: the audit could not determine what it was
            # supposed to check. Falling back to "assume nothing is optional"
            # would report a clean-looking list of criticals from a premise the
            # run never established.
            print(f"REFUSING: {exc}", file=sys.stderr)
            return 2
        all_findings.extend(audit_api_standard(name, all_contracts[name]))

    all_findings.extend(audit_openapi_spec())
    # Coverage/orphan/mock-matching checks reason about the whole spec,
    # overlay, or collection, so they only make sense on a full audit —
    # skip them when auditing a subset.
    if not args.contracts:
        all_findings.extend(audit_openapi_coverage())
        all_findings.extend(audit_postman_mock_matching())
        all_findings.extend(audit_postman_credential_refs())

    out_rel = args.out or DEFAULT_OUT
    out_path = project_root() / out_rel

    # F3 / issue #116's sibling bug: a run scoped to one contract used to
    # overwrite this shared, tracked file with ONLY that contract's
    # findings, silently deleting every other contract's recorded findings.
    # Fix: merge rather than overwrite — keep whatever this run did NOT
    # recompute, replace only the entries for what it did. This makes the
    # file correct regardless of scope, so a scoped caller (e.g. the
    # PostToolUse hook in hooks/mock_api_reminders.py) no longer has to
    # route around the shared path by writing to scratch instead — fixing it
    # once here beats every scoped caller reimplementing the same care.
    recomputed_keys = set(names)
    if not args.contracts:
        # A full audit always recomputes the repo-wide checks too, even when
        # they find nothing this time — so a fixed repo-wide finding is
        # dropped, not left stale.
        recomputed_keys |= _REPO_WIDE_CONTRACT_KEYS
    existing = _load_existing_findings(out_path)
    kept = [f for f in existing if f.get("contract") not in recomputed_keys]
    merged_findings = kept + all_findings
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged_findings, indent=2))

    if args.findings:
        from design_suite.engine import findings as F
        # Grouped by check, not by contract. A dashboard row per contract would
        # be 24 rows that each say "one thing is wrong somewhere"; a row per
        # check says which KIND of drift this project has, which is actionable.
        # No file/line: the unit of a mock-API finding is a contract, and
        # inventing a source location for it would be a false precision.
        F.write(
            F.default_path(project_root(), "mock_api") if args.findings is True
            else project_root() / args.findings,
            "mock_api",
            F.from_records("mock_api", all_findings,
                           category_key="check", severity_key="severity"),
        )

    if not all_findings:
        print(f"/audit-mock-api: {len(names)} contract(s) checked, no drift found")
        return 0

    critical = [f for f in all_findings if f["severity"] == "critical"]
    should_fix = [f for f in all_findings if f["severity"] == "should_fix"]
    # Printed, not dropped. This tier carries the "a check did not run" notices
    # (#117's optional_field_not_exercised); a record that exists in the
    # findings file but never in the run's own output is the silence this
    # suite forbids. Anything that is neither critical nor should_fix lands
    # here, so a future severity cannot go unprinted by omission.
    fyi = [f for f in all_findings if f["severity"] not in ("critical", "should_fix")]

    if critical:
        print(f"CRITICAL ({len(critical)}):")
        for f in critical:
            print(f"  [{f['contract']}] {f['check']}: {f['detail']}")
    if should_fix:
        print(f"Should fix ({len(should_fix)}):")
        for f in should_fix:
            print(f"  [{f['contract']}] {f['check']}: {f['detail']}")
    if fyi:
        print(f"FYI — not findings, but not checks that passed either ({len(fyi)}):")
        for f in fyi:
            print(f"  [{f['contract']}] {f['check']}: {f['detail']}")
    print(f"\nFindings written to {out_rel}")
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
