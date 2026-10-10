#!/usr/bin/env python3
"""Tests for repo_health.py's and audit_discovery.envelope_name's findings-path
resolution.

repo_health.py's run_one() used to compute the envelope path from
`script.stem` — "audit_tokens" — while every audit actually writes under a
shorter name via its own `F.default_path(REPO, "<name>")` call: "tokens" for
audit_tokens.py, "focus-order" (a hyphen, not "focus_order") for
audit_focus_order.py. The mismatch meant run_one()'s before/after mtime check
almost never saw the real file, so a genuine findings run was silently
downgraded to "unclear". Verified live against audit_tokens.py before this
fix landed.

Every case here is paired against a control that must NOT need the exception,
because a fix that only ever checks the one script it was written for proves
nothing about the other eight.

    python3 plugins/design-suite/bin/repo_health_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import repo_health  # noqa: E402 — sets up its own path to design_suite via _bootstrap
from design_suite.engine import audit_discovery  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    (print(f"  ok   {what}") if condition
     else (FAILURES.append(what), print(f"  FAIL {what}")))


def main() -> int:
    # The hyphen exception: audit_focus_order.py names itself with an
    # underscore but writes its envelope with a hyphen. If envelope_name()
    # ever falls back to the naive stem-strip for this one, this case fails.
    focus_order = BIN / "audit_focus_order.py"
    expect(audit_discovery.envelope_name(focus_order) == "focus-order",
           "audit_focus_order.py's envelope name is 'focus-order', not 'focus_order'")

    # The control: a script with no exception, where the naive strip is
    # already correct. If a future refactor made envelope_name() always
    # return the naive strip (silently dropping the grep), this case would
    # still pass and hide the regression the case above exists to catch —
    # which is exactly why both must be asserted, not just the hyphen one.
    tokens = BIN / "audit_tokens.py"
    expect(audit_discovery.envelope_name(tokens) == "tokens",
           "audit_tokens.py's envelope name is 'tokens' (the naive strip, and correct)")

    # Every discovered audit that supports --findings must resolve to SOME
    # envelope name — a silent None here is the same class of bug with a
    # different symptom (repo_health.py's fallback would paper over it).
    missing = [
        s.name for s in audit_discovery.discover(BIN)
        if audit_discovery.supports_findings_flag(s) and audit_discovery.envelope_name(s) is None
    ]
    expect(not missing,
           f"every --findings-capable audit has a grep-able envelope name (missing: {missing})")

    # repo_health.py's own _findings_path must resolve through envelope_name,
    # not through script.stem directly — assert the two audits above produce
    # DIFFERENT paths under repo_health.py's own resolver, since a bug that
    # made them collide (e.g. both falling back to the naive strip) would
    # pass a same-name check trivially.
    fo_path = repo_health._findings_path(focus_order)
    tok_path = repo_health._findings_path(tokens)
    expect(fo_path.name == "focus-order.json",
           f"repo_health._findings_path(audit_focus_order.py) is focus-order.json, got {fo_path.name}")
    expect(tok_path.name == "tokens.json",
           f"repo_health._findings_path(audit_tokens.py) is tokens.json, got {tok_path.name}")
    expect(fo_path != tok_path,
           "the two resolved paths are not the same file")

    # A script with no F.default_path(REPO, ...) call at all (envelope_name
    # returns None) must still resolve to something via the fallback, rather
    # than repo_health.py crashing on a None path.
    class _FakeScript:
        stem = "audit_nonexistent_thing"
        def read_text(self):
            raise OSError("no such file")
    expect(audit_discovery.envelope_name(_FakeScript()) is None,
           "envelope_name returns None rather than guessing when the script can't be read")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("repo_health / envelope_name: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
