"""Pluggable providers for the mock-API contract-automation engine.

Three seams, one module each, selected by `mock_api/config.json`:
  - schema/  — reads a model's field SHAPE from source code (today: Dart `fromJson`).
  - doc/     — reads/writes the human-facing contract doc (today: docs/API.md markdown).
  - mock/    — reads/writes the mock server's example data (today: a Postman collection).

Each seam is the part of this tooling that's project-specific — a TypeScript
project would swap in a different schema provider, an OpenAPI-native project
a different doc provider, an MSW-based project a different mock provider —
without touching `mock_api_common.py`'s orchestration or `sync_mock_api.py`/
`audit_mock_api.py`. See docs/context/plans/mock-api-hardening-and-portability.md
Track C for the design rationale.
"""
