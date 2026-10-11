#!/usr/bin/env python3
"""Prove the scan engine is not shaped around any one language.

The engine's whole justification is that a second language plugs in without
touching it. That claim is easy to assert and easy to get wrong, so two
deliberately different proofs run here:

  * the SHIPPED leg — the registry discovers `php`, `load("php")` returns
    it, and the engine sweeps a PHP fixture through its own
    `checks()` / `FILE_GLOBS`, positives and negatives both held. This is
    the path a consumer project takes, end to end. If the php adapter ever
    leaves the registry, this leg FAILS rather than skips: a second shipped
    language is the point, not an optional extra.
  * the MINIMAL leg — a deliberately tiny language built IN PROCESS through
    the same `Check` / `AdapterContext` / `scan_tree` seam, so every
    expectation is about the SEAM rather than about any real language's
    patterns.

plus a structural pass over whatever the registry discovers (NAME,
FILE_GLOBS, checks()), so an adapter that would load and then fail at first
use is caught here rather than on a consumer's repo.

    python3 backend_suite/adapters/verify_seam.py

Exit 0 = the seam holds. Exit 1 = the seam is broken.

What this does NOT prove: how either adapter behaves on a real codebase —
that is the consumer audits' job, run against real trees. This proves the
seam.
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
# The minimal in-process language: deliberately tiny, so every expectation
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

# The shipped leg's fixture: one planted debug call, one planted plaintext
# secret, and the correct shape for each living in the same file — the
# negatives are what make a pass mean anything.
PHP_FIXTURE = """<?php
// synthetic php fixture for the seam proof — positives and negatives both planted
Route::get('/health', function () {
    dd($response);
    $password = env('DB_PASSWORD');
    return response()->json(['message' => 'ok']);
});
$router->post('/session', function () {
    $legacy = $password = 'hunter2long';
    return response()->json(['message' => 'ok']);
});
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
    names = available()
    for name in names:
        try:
            module = load(name)
        except Exception as exc:  # noqa: BLE001 — any load failure is the finding
            problems.append(f"registered adapter {name!r} failed to load: {exc}")
            continue
        for attr in ("NAME", "FILE_GLOBS"):
            if not hasattr(module, attr):
                problems.append(f"registered adapter {name!r} has no {attr} — "
                                f"the registry would load it and then fail at "
                                f"first use, which is the silent half of the seam")
        if not callable(getattr(module, "checks", None)):
            problems.append(f"registered adapter {name!r} exposes no checks(ctx)")

    print(f"engine + {_STUB_NAME} adapter over a synthetic fixture: "
          f"{len(findings)} finding(s), 1 expected")
    print(f"registered adapters discovered by the registry: {', '.join(names)}")

    # 5. The load() discovery leg, live: the SHIPPED php adapter, discovered by
    #    the registry, sweeping a php fixture through its own checks and globs.
    if "php" not in names:
        problems.append("the php adapter is missing from the registry — this "
                        "file's shipped-language leg exists to prove a second "
                        "real language loads and sweeps; its absence is a "
                        "regression, not a skip")
    else:
        php = load("php")
        with tempfile.TemporaryDirectory() as raw:
            fixture = Path(raw)
            (fixture / "routes").mkdir()
            (fixture / "routes" / "api.php").write_text(PHP_FIXTURE)
            ctx = AdapterContext(repo=fixture, profile={}, exceptions={},
                                 token_accessor=None)
            php_findings = scan_tree(fixture, fixture, php.checks(ctx),
                                     globs=php.FILE_GLOBS)

            if not any(f["kind"] == "debug_statement" and "dd(" in f["snippet"]
                       for f in php_findings):
                problems.append("php leg: no debug_statement finding for the "
                                "planted dd() call")
            if not any(f["kind"] == "plaintext_secret"
                       and "hunter2long" in f["snippet"]
                       for f in php_findings):
                problems.append("php leg: no plaintext_secret finding for the "
                                "planted literal")
            # The negative control, same as the stub leg's: env('…') is a
            # config REFERENCE, the correct shape, and must never be flagged.
            if any("DB_PASSWORD" in f["snippet"] for f in php_findings):
                problems.append("php leg: env('DB_PASSWORD') was flagged — a "
                                "naive secret matcher that cannot tell a "
                                "literal from a config reference")
            if any(f["file"] != "routes/api.php" for f in php_findings):
                problems.append("php leg: a finding landed outside the "
                                "adapter's FILE_GLOBS")
            print(f"shipped php adapter over a php fixture: "
                  f"{len(php_findings)} finding(s), 2 expected")

    if problems:
        print("\nSEAM BROKEN:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\nSeam holds: the engine ran a second language with no engine "
          "changes, and the shipped php adapter loads and sweeps through the "
          "same seam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
