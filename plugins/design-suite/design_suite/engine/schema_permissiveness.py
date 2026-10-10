"""Where a document validates against nothing, and says nothing about it.

A JSON Schema object with `properties` and no `additionalProperties: false`
accepts every key nobody thought to describe. Validation still passes — loudly,
in the sense that it prints success — while the keys that matter most are the
ones going unchecked, because a key nobody described is usually a key nobody
implemented either.

## Why this reports the instantiated hole, not every hole

Reporting every permissive object turns a two-line schema review into a wall.
The finding here is narrower and evidence-backed: an object is reported only when
the document being validated *actually carries keys* that the schema does not
describe and does not forbid. That is the difference between "this could drift"
and "this has drifted, and validation is silent about it" — RFC-0002 §2b's fourth
row, where `tokens` gained `roleSource` and `roleAccessor` and the schema never
knew.

Keys beginning with `_` are excluded: this suite's configs use them for prose
comments by convention, and a convention that is deliberately unschemaed is not
a hole.
"""
from __future__ import annotations

KIND = "schema-accepts-undescribed-keys"


def _permissive(node: dict) -> bool:
    """True when this object schema accepts keys it does not describe.

    A value for `additionalProperties` that is itself a schema (`{"$ref": …}`)
    constrains the extras and is not permissive — only absent or `true` is.
    """
    extra = node.get("additionalProperties")
    return extra is None or extra is True


def _undescribed(schema_node: dict, instance: dict) -> list[str]:
    described = set(schema_node.get("properties", {}))
    for combinator in ("allOf", "anyOf", "oneOf"):
        for branch in schema_node.get(combinator, []) or []:
            if isinstance(branch, dict):
                described |= set(branch.get("properties", {}))
    patterns = schema_node.get("patternProperties")
    if patterns:
        # Any pattern at all could be the one describing these keys; matching
        # them here would mean reimplementing a regex dialect to guess.
        return []
    return sorted(k for k in instance
                  if k not in described and not k.startswith("_"))


def findings(schema: dict, instance: dict, schema_name: str,
             instance_name: str, trail: str = "") -> list[dict]:
    """Every place `instance` carries keys `schema` neither describes nor forbids."""
    out: list[dict] = []
    if not isinstance(schema, dict) or not isinstance(instance, dict):
        return out

    if schema.get("properties") and _permissive(schema):
        extras = _undescribed(schema, instance)
        if extras:
            out.append({
                "kind": KIND,
                "path": f"{schema_name}: {trail or '(root)'}",
                "keys": extras,
                "why": f"{instance_name} sets {', '.join(extras)} at "
                       f"{trail or 'the document root'}, and this object in {schema_name} "
                       f"has no `additionalProperties: false`. Those keys validate against "
                       f"nothing — validation reports success without having checked them.",
            })

    for key, child_schema in (schema.get("properties") or {}).items():
        child = instance.get(key)
        if isinstance(child_schema, dict) and isinstance(child, dict):
            out.extend(findings(child_schema, child, schema_name, instance_name,
                                f"{trail}.{key}" if trail else key))
    return out
