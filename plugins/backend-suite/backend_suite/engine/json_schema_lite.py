"""A stdlib-only JSON Schema (draft-04 subset) validator.

This suite is stdlib only, and `jsonschema` is not. The one schema we need to
validate against — SARIF 2.1.0, vendored under templates/vendor/sarif-2.1.0/ —
uses a small, fixed keyword set, so this implements exactly that set and
REFUSES on anything else rather than skipping it:

    $ref (local "#/..." only)  type  enum  required  properties
    additionalProperties  items  minItems  uniqueItems  minimum  maximum
    pattern  format (date-time, uri, uri-reference)  oneOf  anyOf

A validator that silently ignores a keyword it does not understand reports
"valid" for exactly the documents that keyword exists to reject — the governing
principle again. `UnsupportedKeyword` is raised at the first schema node using
one, so widening the vendored schema can never quietly widen what passes.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit

ANNOTATIONS = {"$schema", "id", "title", "description", "default", "definitions"}
SUPPORTED = {"$ref", "type", "enum", "required", "properties", "additionalProperties",
             "items", "minItems", "uniqueItems", "minimum", "maximum", "pattern",
             "format", "oneOf", "anyOf"}


class UnsupportedKeyword(Exception):
    pass


def _type_ok(value, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "null":
        return value is None
    raise UnsupportedKeyword(f"type {name!r}")


def _format_ok(value: str, fmt: str) -> bool:
    if fmt == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "T" in value
        except ValueError:
            return False
    if fmt == "uri":
        return bool(urlsplit(value).scheme) and " " not in value
    if fmt == "uri-reference":
        return " " not in value
    raise UnsupportedKeyword(f"format {fmt!r}")


def _resolve(root: dict, ref: str) -> dict:
    if not ref.startswith("#"):
        raise UnsupportedKeyword(f"non-local $ref {ref!r}")
    node = root
    for part in [p for p in ref[1:].split("/") if p]:
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _canon(value):
    import json
    return json.dumps(value, sort_keys=True)


def errors(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Every violation as `"<json-path>: <what>"`; empty means valid."""
    root = root if root is not None else schema
    unknown = set(schema) - SUPPORTED - ANNOTATIONS
    if unknown:
        raise UnsupportedKeyword(f"{sorted(unknown)} at schema for {path}")
    if "$ref" in schema:
        return errors(instance, _resolve(root, schema["$ref"]), root, path)

    out: list[str] = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(instance, n) for n in names):
            return [f"{path}: expected {names}, got {type(instance).__name__}"]
    if "enum" in schema and instance not in schema["enum"]:
        out.append(f"{path}: {instance!r} not in {schema['enum']}")
    if "oneOf" in schema:
        hits = sum(1 for s in schema["oneOf"] if not errors(instance, s, root, path))
        if hits != 1:
            out.append(f"{path}: matched {hits} of oneOf, need exactly 1")
    if "anyOf" in schema:
        if not any(not errors(instance, s, root, path) for s in schema["anyOf"]):
            out.append(f"{path}: matched none of anyOf")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                out.append(f"{path}: missing required {key!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            sub = f"{path}.{key}"
            if key in props:
                out += errors(value, props[key], root, sub)
            elif extra is False:
                out.append(f"{path}: additional property {key!r} not allowed")
            elif isinstance(extra, dict):
                out += errors(value, extra, root, sub)
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems"):
            seen = [_canon(v) for v in instance]
            if len(seen) != len(set(seen)):
                out.append(f"{path}: items not unique")
        if isinstance(schema.get("items"), dict):
            for i, value in enumerate(instance):
                out += errors(value, schema["items"], root, f"{path}[{i}]")
        elif "items" in schema:
            raise UnsupportedKeyword(f"tuple-form items at {path}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            out.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            out.append(f"{path}: {instance} > maximum {schema['maximum']}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            out.append(f"{path}: {instance!r} does not match {schema['pattern']!r}")
        if "format" in schema and not _format_ok(instance, schema["format"]):
            out.append(f"{path}: {instance!r} is not a valid {schema['format']}")
    return out
