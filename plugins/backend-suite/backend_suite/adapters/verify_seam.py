#!/usr/bin/env python3
"""Prove the scan engine is not shaped around any one language.

The engine's whole justification is that a second language plugs in without
touching it. That claim is easy to assert and easy to get wrong, so this builds
a minimal second language IN PROCESS — the same `Check` / `AdapterContext` /
`scan_tree` seam a real adapter uses — and runs the engine over a synthetic
fixture with it, asserting what comes back and, more importantly, what must NOT
come back, which is where a naive adapter fails.

    python3 backend_suite/adapters/verify_seam.py

Exit 0 = the seam holds. Exit 1 = the seam is broken.

## What this proves, and what it does not (read before trusting it)

Proves: the engine sweeps a second language through the adapter interface with
no engine changes, positive and negative cases both held, and every adapter
module the registry discovers exposes the structural contract (NAME,
FILE_GLOBS, checks()).

Does NOT prove: the `load("<name>")` discovery path against a SECOND shipped
language module, because no second language module ships right now — the UI
adapters left with the design domain and the `php` adapter is Phase D work
(tracked in docs/SWAP-PLAN.md). When it lands, extend this file with a
`load("php")` leg over the php fixture; until then, an adapter-free interim
that proves the interface is honest beats either a red gate or a green one
that proves nothing.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backend_suite.adapters import AdapterContext, Check, available, load  # noqa: E402
from backend_suite.engine.scan import scan_tree  # noqa: E402


# --------------------------------------------------------------------------- #
# The interim second language: a deliberately tiny one, so every expectation
# below is about the SEAM rather than about the language.
# --------------------------------------------------------------------------- #

# Prefixed with an underscore on purpose: the registry discovers adapters by
# the module-level NAME/FILE_GLOBS/checks contract, and an unprefixed copy of
# those names HERE made the seam test discover itself as an adapter named
# "verify_seam" — the registry being THAT structural is the point, and the
# reason this file has to stay off its own radar.
_STUB_NAME = "stublang"
_STUB_GLOBS = ("*.stub",)

# A "violation" in this toy language: a secret assigned as a plaintext literal.
# Correct usage assigns through ENV(...). The negative control is the load-
# bearing half: an adapter that flagged ENV("X") as a literal would report a
# correctly-written codebase as entirely broken.
VIOLATION = re.compile(r'(?<![\w.])password\s*=\s*"[^"]+"')
CORRECT = 'password = ENV("DB_PASSWORD")'


def _stub_checks(ctx: AdapterContext) -> list:
    return [
        Check(kind="plaintext-secret",
              pattern=VIOLATION,
              category="secrets"),
    ]


FIXTURE = """# synthetic stublang source
password = "hunter2"
password = ENV("DB_PASSWORD")
retry = 3
"""


def main() -> int:
    problems: list[str] = []

    # 1. The engine runs a second language through the seam, positives held.
    with tempfile.TemporaryDirectory() as raw:
        fixture = Path(raw)
        (fixture / "service.stub").write_text(FIXTURE)
        ctx = AdapterContext(repo=fixture, profile={}, exceptions={},
                             token_accessor=None)
        findings = scan_tree(fixture, fixture, _stub_checks(ctx), globs=_STUB_GLOBS)

        if not any(f["kind"] == "plaintext-secret" and "hunter2" in f["snippet"]
                   for f in findings):
            problems.append("expected a plaintext-secret finding for the literal "
                            "assignment, got none")
        # 2. Negatives held: correct usage in the same file must not be flagged.
        if any(CORRECT.split('"')[1] in f["snippet"] for f in findings):
            problems.append("ENV(...) assignment was flagged — a naive adapter "
                            "that cannot tell a literal from a reference")
        # 3. The engine did not flag the file it matched in by a foreign shape.
        if any(f["file"] != "service.stub" for f in findings):
            problems.append("a finding landed outside the adapter's FILE_GLOBS")

    # 4. Whatever the registry discovers loads and is structurally a valid
    #    adapter. `available()` + `load()` are the same path a project takes.
    problems_scope: list[str] = []
    names = available()
    for name in names:
        try:
            module = load(name)
        except Exception as exc:  # noqa: BLE001 — any load failure is the finding
            problems_scope.append(f"registered adapter {name!r} failed to load: {exc}")
            continue
        for attr in ("NAME", "FILE_GLOBS"):
            if not hasattr(module, attr):
                problems_scope.append(f"registered adapter {name!r} has no {attr} — "
                                      f"the registry would load it and then fail at "
                                      f"first use, which is the silent half of the seam")
        if not callable(getattr(module, "checks", None)):
            problems_scope.append(f"registered adapter {name!r} exposes no checks(ctx)")
    problems += problems_scope

    print(f"engine + {_STUB_NAME} adapter over a synthetic fixture: "
          f"{len(findings)} finding(s), 1 expected")
    print(f"registered adapters discovered by the registry: "
          f"{names or 'none (php is Phase D — see docs/SWAP-PLAN.md)'}")

    if problems:
        print("\nSEAM BROKEN:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\nSeam holds: the engine ran a second language with no engine changes.")
    if not names:
        print("Note: the load() discovery leg is proven live again when the php "
              "adapter lands; this interim proves the interface contract only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
