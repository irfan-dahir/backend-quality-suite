#!/usr/bin/env python3
"""Sync the mock API — regenerate docs/API.md's example JSON and the Postman
collection's example response body for a contract from its fixture, instead
of hand-editing both (the exact drift that hit GET /plans after a recovery
revert — see docs/context/plans/mock-api-integration.md).

Source of truth chain: the Dart model's fromJson defines field SHAPE; the
fixture (test/fixtures/<name>.json) carries example VALUES and is the one
file a human edits by hand. This script propagates the fixture into the two
generated artifacts. It never touches the field table's Notes column or the
surrounding prose in docs/API.md — those need human judgment, not generation.

Usage:
    python3 ".../sync_mock_api.py" <contract-name>               # dry run (default)
    python3 ".../sync_mock_api.py" <contract-name> --check       # same as above, explicitly
    python3 ".../sync_mock_api.py" <contract-name> --write       # actually modify files
    python3 ".../sync_mock_api.py" <contract-name> --write --allow-loss

## Issue #116 — why this file refuses instead of just overwriting

Measured on a real consumer: this script propagates fixture -> mock/docs
unconditionally, treating the fixture as authoritative. Twice, the fixture was
the side that had *rotted* — it had lost a `weekday: 1` field and a PDF
attachment's `url` that only existed on the mock/docs side — and running this
script deleted that correct data from the repository. A weekly item with a
null `weekday` silently drops out of adherence scoring; an emptied `url`
silently drops a download button. Both are real breakage hiding behind a
script that printed nothing alarming.

Do not "simplify" this back to an unconditional overwrite. See gh issue #116,
and `design_suite/engine/token_repair.py` / `bin/repair_tokens.py`, the
precedent this contract is extracted from: emit, don't apply, and refuse
rather than guess when the premise cannot be determined.

## The contract (R1-R5)

R1 — emit, never apply, by default. The bare command and `--check` are the
     same dry-run behavior: show what would change (or exactly what would be
     lost), and exit 1 if there is drift. `--check` is kept only so existing
     invocations (CI, muscle memory) that already pass it keep working
     unchanged — it adds nothing `--write`'s absence doesn't already mean.
     `--write` is the only flag that touches a file.

R2 — every run prints a machine-readable `direction: fixture -> {...}`
     header, so no future finding text or human can be confused about which
     way data is expected to flow.

R3 — loss refusal. Before writing, this diffs the existing target body
     against the new (fixture-derived) one. Any key or non-null value present
     in the old body but absent or null in the new one is a loss: `--write`
     refuses (exit 2) and prints exactly what would be lost. A key that is
     new in the fixture-derived body is never a loss — the fixture legitimately
     growing richer is the common case and must sail through untouched.
     `--allow-loss` is the explicit override.

R4 — `--check` (and the bare dry run) name the same losses `--write` would
     refuse on, not just "differs" — so a dry run is actually informative.

R5 — refuse (exit 2) rather than guess when the fixture or an existing target
     body cannot be parsed, or the contract mapping (unknown contract, no
     fixture key, no matching Postman request) doesn't resolve.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_openapi import main as generate_openapi_main
from mock_api_common import (
    API_DOC_FILE,
    COLLECTION_FILE,
    envelope_body,
    find_mock_request,
    fixture_all_keys,
    load_collection,
    load_contracts,
    load_fixture,
    model_fields,
    render_json_block,
    save_collection,
    table_field_names,
)

REFUSED = 2


def refuse(message: str) -> int:
    print(f"REFUSING: {message}", file=sys.stderr)
    return REFUSED


def _parse_or_none(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def _brief(value: object, limit: int = 80) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def find_losses(old: Any, new: Any, path: str = "") -> list[tuple[str, Any]]:
    """Keys/values present (non-null) in `old` but absent or null in `new`.

    Deliberately asymmetric — see the module docstring's #116 discussion. A
    key present in `new` but not `old` is growth, not loss, and never
    appears here. Only dicts and lists recurse; a scalar-vs-scalar value
    change (rather than a removal) is not a "loss" by this contract's
    definition — R3 is about data disappearing, not about values differing,
    which `audit_mock_api.py`'s `*_values` findings already cover without
    naming a direction.
    """
    losses: list[tuple[str, Any]] = []
    if isinstance(old, dict):
        new_d = new if isinstance(new, dict) else {}
        for key, old_value in old.items():
            child = f"{path}.{key}" if path else key
            if key not in new_d:
                if old_value is not None:
                    losses.append((child, old_value))
                continue
            new_value = new_d[key]
            if new_value is None and old_value is not None:
                losses.append((child, old_value))
                continue
            losses.extend(find_losses(old_value, new_value, child))
    elif isinstance(old, list):
        new_l = new if isinstance(new, list) else []
        for i, old_value in enumerate(old):
            child = f"{path}[{i}]"
            if i >= len(new_l):
                if old_value is not None:
                    losses.append((child, old_value))
                continue
            losses.extend(find_losses(old_value, new_l[i], child))
    return losses


def check_table_drift(contract: dict, fixture: dict) -> list[str]:
    fields = model_fields(contract)
    all_keys = fixture_all_keys(contract)
    anchor = contract.get("api_doc_anchor")
    documented = (
        set(table_field_names(API_DOC_FILE.read_text(), anchor)) if anchor else set(fields)
    )
    missing = [f for f in fields if f not in documented]
    extra_in_fixture = [f for f in all_keys if f not in fields]
    warnings = []
    if missing:
        warnings.append(
            f"Model fields not in the API.md table (add rows by hand): {missing}"
        )
    if extra_in_fixture:
        warnings.append(
            f"Fixture has fields the model doesn't read (drop from fixture or "
            f"add to model): {extra_in_fixture}"
        )
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("--write", action="store_true",
                         help="actually modify docs/API.md and the collection. "
                              "Without this, nothing is written (R1).")
    parser.add_argument("--check", action="store_true",
                         help="no-op: the dry run this performs is already the "
                              "default without --write. Kept so existing "
                              "invocations that already pass --check keep working.")
    parser.add_argument("--allow-loss", action="store_true",
                         help="proceed with --write even though syncing would "
                              "delete a key/value that only exists on the "
                              "target (mock/docs) side (R3).")
    args = parser.parse_args()

    try:
        contracts = load_contracts()
    except Exception as e:
        return refuse(f"could not parse the contract registry: {e}")

    if args.contract not in contracts:
        print(f"Unknown contract {args.contract!r}. Known: {list(contracts)}")
        return REFUSED
    contract = contracts[args.contract]

    try:
        fixture = load_fixture(contract)
    except Exception as e:
        return refuse(f"could not parse the fixture for {args.contract!r}: {e}")

    try:
        body = envelope_body(fixture, contract)
    except Exception as e:
        return refuse(f"could not derive the wire body for {args.contract!r} — "
                       f"the contract mapping does not resolve: {e}")

    anchor = contract.get("api_doc_anchor")
    targets = ["mock"] + (["docs"] if anchor else [])
    # R2: printed on every run, unconditionally, before any drift/loss
    # computation — so it survives even a refusal below.
    print(f"direction: fixture -> {{{', '.join(targets)}}}", file=sys.stderr)

    # --- docs/API.md target -------------------------------------------------
    doc_changed = False
    doc_losses: list[tuple[str, Any]] = []
    new_doc_text = None
    if anchor:
        try:
            text = API_DOC_FILE.read_text()
        except Exception as e:
            return refuse(f"could not read {API_DOC_FILE}: {e}")
        idx = text.find(anchor)
        if idx == -1:
            return refuse(f"anchor {anchor!r} not found in docs/API.md")
        section = text[idx:]
        fence_start = section.find("```json")
        if fence_start == -1:
            return refuse(f"no ```json block found under {anchor!r}")
        fence_end = section.find("```", fence_start + len("```json"))
        abs_start = idx + fence_start + len("```json\n")
        abs_end = idx + fence_end
        old_block = text[abs_start:abs_end].rstrip("\n")
        new_block = render_json_block(body)
        doc_changed = old_block.strip() != new_block.strip()
        new_doc_text = text[:abs_start] + new_block + "\n" + text[abs_end:]
        if doc_changed:
            old_doc_parsed = _parse_or_none(old_block)
            if old_doc_parsed is None:
                return refuse("docs/API.md's existing example block under "
                               f"{anchor!r} is not valid JSON — cannot determine "
                               "whether syncing would lose data")
            doc_losses = find_losses(old_doc_parsed, body)

    # --- Postman collection target ------------------------------------------
    try:
        collection = load_collection()
    except Exception as e:
        return refuse(f"could not parse {COLLECTION_FILE}: {e}")
    req = find_mock_request(collection, contract["mock_folder"], contract["mock_request"])
    if req is None:
        return refuse(
            f"request {contract['mock_request']!r} not found in folder "
            f"{contract['mock_folder']!r} — the contract mapping does not resolve"
        )
    old_collection_body = req["response"][0]["body"]
    new_collection_body = render_json_block(body)
    collection_changed = old_collection_body.strip() != new_collection_body.strip()
    collection_losses: list[tuple[str, Any]] = []
    if collection_changed:
        old_collection_parsed = _parse_or_none(old_collection_body)
        if old_collection_parsed is None:
            return refuse("the Postman example body is not valid JSON — cannot "
                           "determine whether syncing would lose data")
        collection_losses = find_losses(old_collection_parsed, body)

    all_losses = ([("docs", path, val) for path, val in doc_losses] +
                  [("mock", path, val) for path, val in collection_losses])

    warnings = check_table_drift(contract, fixture)

    def print_losses(stream, prefix: str = "  ") -> None:
        for target, path, old_value in all_losses:
            print(f"{prefix}[{target}] {path}: {_brief(old_value)}", file=stream)

    if not args.write:
        # R1/R4: bare command and --check are the same dry run.
        if doc_changed or collection_changed:
            print(f"[sync-mock-api] {args.contract}: OUT OF SYNC with fixture")
            if doc_changed:
                print("  - docs/API.md example block differs from fixture")
            if collection_changed:
                print("  - mock_api collection example differs from fixture")
            if all_losses:
                print("  LOSSES a --write would refuse on without --allow-loss:")
                print_losses(sys.stdout)
            else:
                print("  (no losses — the fixture side only adds/changes values)")
            for w in warnings:
                print(f"  ! {w}")
            return 1
        print(f"[sync-mock-api] {args.contract}: in sync")
        return 0

    # --write from here on.
    if all_losses and not args.allow_loss:
        print("REFUSING to write: syncing would delete data that exists only on "
              "the target (mock/docs) side. This is the exact failure measured "
              "in issue #116 — the fixture was the rotted side, and an "
              "unconditional overwrite deleted a real `weekday` value and a "
              "real PDF `url`. Pass --allow-loss if this loss is intentional.",
              file=sys.stderr)
        print_losses(sys.stderr, prefix="  would lose ")
        return REFUSED

    if doc_changed:
        API_DOC_FILE.write_text(new_doc_text)
        print("Updated docs/API.md example block")
    if collection_changed:
        req["response"][0]["body"] = new_collection_body
        save_collection(collection)
        # COLLECTION_FILE, not a literal: the collection's path already comes
        # from `mock_provider.file` in the mock-API config.
        print(f"Updated {COLLECTION_FILE.name} example body")
    if not doc_changed and not collection_changed:
        print(f"[sync-mock-api] {args.contract}: already in sync")
    if all_losses:
        print("NOTE: proceeded with --allow-loss. The following existed only on "
              "the target side and is now gone:")
        print_losses(sys.stdout)
    for w in warnings:
        print(f"! {w}")

    # Keep the generated OpenAPI spec (a fifth artifact off the same
    # fixture) current too — regenerated in-process, not shelled out to,
    # so a single `sync_mock_api.py <contract> --write` run is the one
    # command that brings doc + mock + spec back in sync.
    generate_openapi_main([])
    return 0


if __name__ == "__main__":
    sys.exit(main())
