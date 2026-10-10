#!/usr/bin/env python3
"""Generate the integration harness's canned GET responses from the fixtures.

    python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/sync_integration_fixtures.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/sync_integration_fixtures.py" --check

## Why this is generated rather than written

`FakeBackendAdapter` hand-coded nine responses inline. The app calls **thirty**
endpoints, so the integration suite failed at the first screen that needed a
tenth — and every hand-written body was a third copy of data that already
existed twice, in `test/fixtures/` and in `docs/API.md`.

Unit tests read the fixtures directly with `File(...)`, which works because
`flutter test` runs on the host VM. **Integration tests run on the device**,
where the repo's filesystem does not exist. So the fixtures have to be compiled
in, which means generated Dart — the same answer `sync_mock_api.py` reaches for
the same reason.

## The envelope, which is the part that is easy to get wrong

Every fixture is stored in the **legacy** shape — a single-key wrapper like
`{"plans": [...]}` — because that is what `docs/API.md` documents and what the
mock server serves.

Every datasource has already migrated to the **v1** envelope: `dataList` reads
`{"data": [...]}`, `dataObject` reads `{"data": {...}}`, `dataMap` reads
`{"data": {key: [...]}}`.

Serving a fixture unchanged therefore throws a cast error rather than returning
no data, which is a confusing failure. This script does the translation, and it
reads which envelope each endpoint uses **from the datasource call site** rather
than from a hand-maintained table — so an endpoint that migrates envelopes
cannot leave this file behind.

The pre-existing hand-written `/v1/users/me/care-plans` response had exactly
this bug: it returned `{"carePlans": [...]}` against a `dataList` call site.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Resolved the same way as every other engine here, via mock_api_common. This
# file used to compute `parent.parent.parent` itself, which meant the plugin's
# own `design_suite/` package directory — not the project. Inside the app repo
# the two happened to coincide; once the engines were extracted they did not, and
# CONTRACTS then pointed at a file that does not exist. Every other script in
# this directory takes REPO from mock_api_common; this one rolling its own is
# what let it drift.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_api_common import MOCK_API, REPO  # noqa: E402

# Directory from `pipelines.mockApi` in the profile, not a literal — resolved
# once in mock_api_common. See engine/pipelines.py for why.
CONTRACTS = MOCK_API / "contracts.json"
OUT = REPO / "integration_test/fakes/fixture_responses.g.dart"

# Concatenated rather than an f-string on purpose: the regenerate line below
# contains `${CLAUDE_PLUGIN_ROOT}`, whose braces an f-string would try to
# interpolate.
BANNER = """// GENERATED — do not edit.
//
// Source: """ + str(CONTRACTS.relative_to(REPO)) + """ + test/fixtures/*.json
// Regenerate: python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/sync_integration_fixtures.py"
//
// Canned GET responses for the integration harness, already wrapped in the v1
// envelope each datasource expects. See the generator's docstring for why the
// fixtures cannot be served unchanged.
"""


def envelope_for(path: str) -> str | None:
    """Which `ApiEnvelope.*` the app uses at `path`, read from the call site.

    Two forms, and getting the first version of this wrong produced a wrong
    answer rather than no answer — which is the failure mode worth guarding,
    because a mis-detected envelope generates a body that throws a cast error
    at runtime instead of failing here.

    1. Direct:  `dio.get('/v1/memberships')` ... `ApiEnvelope.dataList(...)`
    2. Via a helper: `_fetchArchivables('/v1/archive/photographs')`, where the
       envelope lives in the helper body. Photographs, manuscripts and maps
       all go through one.

    A first draft accepted a bare `.get(path` as a match for every endpoint,
    so every path that shared a file with a helper inherited that helper's
    envelope. `/v1/archive/condition-report` came back as `dataList` when it is
    `dataObject`, and the generator caught it only because the fixture was not
    a list.
    """
    literal = f"'{path}'"
    for dart in sorted((REPO / "lib").rglob("*.dart")):
        src = dart.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(re.escape(literal), src):
            head = src[max(0, m.start() - 80):m.start()]
            tail = src[m.end():m.end() + 400]

            # Form 1 — the envelope follows the call directly.
            if re.search(r"\.(?:get|post|patch)\(\s*$", head):
                env = re.search(r"ApiEnvelope\.(\w+)\(", tail)
                if env:
                    return env.group(1)

            # Form 2 — passed to a private helper; read the helper's body.
            helper = re.search(r"(_\w+)\(\s*$", head)
            if helper:
                body = re.search(
                    rf"{helper.group(1)}\(String \w+\)[^{{]*\{{(.{{0,600}}?)\}}",
                    src,
                    re.S,
                )
                if body:
                    env = re.search(r"ApiEnvelope\.(\w+)\(", body.group(1))
                    if env:
                        return env.group(1)
    return None


def body_for(entry: dict, envelope: str) -> object:
    """Wrap a fixture in the envelope its datasource reads.

    Every branch **validates the shape it produces**. A mis-detected envelope
    or a fixture that has drifted then fails here, naming the file — rather
    than producing a plausible-looking body that throws a cast error somewhere
    inside a widget test, which is where the previous hand-written
    `/v1/users/me/care-plans` response failed.
    """
    fixture = json.loads((REPO / entry["fixture"]).read_text())
    key = entry.get("fixture_list_key")
    where = entry["fixture"]

    def unwrapped() -> object:
        if key:
            return fixture[key]
        # No declared key. A fixture with exactly one top-level key is a
        # wrapper (`{"conversations": {...}}`); one with several is the object
        # itself (`care_plan_current` has five).
        if isinstance(fixture, dict) and len(fixture) == 1:
            return next(iter(fixture.values()))
        return fixture

    if envelope == "dataList":
        items = unwrapped()
        if not isinstance(items, list):
            raise SystemExit(
                f"{where}: dataList needs a list, got {type(items).__name__}"
                f" (fixture_list_key={key!r})"
            )
        return {"data": items}

    if envelope == "dataMap":
        inner = unwrapped()
        if not isinstance(inner, dict) or not all(
            isinstance(v, list) for v in inner.values()
        ):
            raise SystemExit(
                f"{where}: dataMap needs a map of lists, got "
                f"{type(inner).__name__}"
            )
        return {"data": inner}

    if envelope == "dataObject":
        obj = fixture[key] if key else fixture
        if not isinstance(obj, dict):
            raise SystemExit(
                f"{where}: dataObject needs a map, got {type(obj).__name__}"
            )
        return {"data": obj}

    raise SystemExit(f"unhandled envelope {envelope!r} for {where}")


def render() -> str:
    contracts = json.loads(CONTRACTS.read_text())
    rows, skipped = [], []
    for name, entry in sorted(contracts.items()):
        if name.startswith("_") or "mock_request" not in entry:
            continue
        path = entry["mock_request"]
        env = envelope_for(path)
        if env is None:
            skipped.append((path, "no ApiEnvelope call site found"))
            continue
        payload = json.dumps(body_for(entry, env), separators=(",", ":"))
        rows.append((path, env, payload))

    out = [BANNER, "", "const Map<String, String> kFixtureResponses = {"]
    for path, env, payload in rows:
        out.append(f"  // {env}")
        out.append(f"  '{path}': r'''{payload}''',")
    out.append("};")
    if skipped:
        out.append("")
        out.append("// Not generated:")
        for path, why in skipped:
            out.append(f"//   {path} — {why}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    rendered = render()
    n = rendered.count("': r'''")

    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != rendered:
            print(
                "integration fixtures are stale — run\n"
                '  python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/mockapi/'
                'sync_integration_fixtures.py"',
                file=sys.stderr,
            )
            return 1
        print(f"sync_integration_fixtures --check: {n} endpoint(s) up to date")
        return 0

    OUT.write_text(rendered)
    print(f"wrote {OUT.relative_to(REPO)} — {n} endpoint(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
