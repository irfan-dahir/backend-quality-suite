"""Schema provider: Dart `fromJson` field-shape reader.

Extracts the field NAMES a Dart model reads off the wire — the source of
truth for an endpoint's SHAPE (values live in the fixture instead).

Convention this provider depends on (documented in
docs/context/plans/mock-api-hardening-and-portability.md Track C, and in
each model file that follows it): a model's TOP-LEVEL `fromJson` factory
must name its parameter `json` or `map`; any PRIVATE helper that parses a
nested object one level down (an item inside a list, a sub-object) must use
a DIFFERENT parameter name (e.g. `itemJson`, `rangeJson`). This provider
scans the whole file for `json['x']`/`map['x']` accesses rather than trying
to isolate just the top-level factory's body — two narrower attempts each
broke on a real model shape (a switch-based branch body, a field read
inside a delegated top-level helper) — so whole-file scanning is what's
proven robust. The naming convention is what keeps that whole-file scan
from also picking up nested fields it shouldn't: see loan_agreement_model.dart,
condition_report_model.dart, and tour_note_model.dart for worked
examples. A model that doesn't follow the convention (nested helpers also
named `json`) isn't registerable under this provider without renaming
those parameters first — see mock-api-hardening-and-portability.md's
Track A.5 for a concrete instance (visitor_profile_model.dart).
"""
from __future__ import annotations

import re
from pathlib import Path

FROM_JSON_FIELD_RE = re.compile(r"(?:json|map)\[['\"](\w+)['\"]\]")


def read_fields(model_file: Path) -> list[str]:
    """Field names as read anywhere in `model_file`, in first-appearance order."""
    text = model_file.read_text()
    seen: list[str] = []
    for field in FROM_JSON_FIELD_RE.findall(text):
        if field not in seen:
            seen.append(field)
    return seen
