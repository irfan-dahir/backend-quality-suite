"""Mock provider: Postman collection reader/writer.

Addresses a single endpoint's canned example response by (folder name,
request name) within a Postman collection JSON export. An endpoint's
example body lives at `response[0]['body']` (a JSON-encoded string) on the
matched request item.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load(collection_file: Path) -> dict[str, Any]:
    return json.loads(collection_file.read_text())


def save(collection_file: Path, collection: dict[str, Any]) -> None:
    collection_file.write_text(json.dumps(collection, indent=2, ensure_ascii=False) + "\n")


def find_request(collection: dict[str, Any], folder_name: str, request_name: str) -> dict[str, Any] | None:
    for folder in collection.get("item", []):
        if folder.get("name") == folder_name:
            for req in folder.get("item", []):
                if req.get("name") == request_name:
                    return req
    return None


def read_body(request: dict[str, Any]) -> str:
    return request["response"][0]["body"]


def write_body(request: dict[str, Any], new_body: str) -> bool:
    """Returns True if the body actually changed."""
    old_body = request["response"][0]["body"]
    changed = old_body.strip() != new_body.strip()
    request["response"][0]["body"] = new_body
    return changed
