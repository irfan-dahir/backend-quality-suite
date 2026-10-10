#!/usr/bin/env python3
"""Tests for audit_safe_repairers's matching, keyed against the two incidents
it exists to catch (issues #109, #116) plus the false-positive shapes its own
EXEMPT list already had to route around.

**These cases are written against the contract, not against current file
contents.** If the plugin's own text changes shape, these regex-level tests
still have to hold — they build strings, not read files — the same design
choice audit_skill_paths_test.py makes and for the same reason.

    python3 plugins/design-suite/bin/audit_safe_repairers_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only, no I/O beyond loading
the plugin's own regexes and its checked-in allowlist.
"""
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import audit_safe_repairers as sr  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def script_hit(text: str) -> str | None:
    m = sr.SCRIPT_RUN.search(text)
    return m.group(1) if m else None


def skill_hit(text: str) -> str | None:
    m = sr.SKILL_RUN.search(text)
    return m.group(1) if m else None


def fix_hit(text: str) -> str | None:
    m = sr.FIX_WITH.search(text)
    return m.group(1) if m else None


def main() -> int:
    print("check: the shapes that actually caused #109/#116 are caught")
    expect(script_hit("value drift — run `sync_mock_api.py <contract>` to fix it")
           == "sync_mock_api.py",
           "the #116 sentence names sync_mock_api.py")
    expect(fix_hit("Fix with: rm_everything.py --force") == "rm_everything.py",
           "an explicit 'Fix with:' sentence is caught")
    expect(skill_hit("run `/sync-mock-api` on the finding") == "/sync-mock-api",
           "a skill named as something to run is caught")

    print("check: the allowlist actually loaded has the entries this gate depends on")
    allowlist = sr.load_allowlist()
    expect("repair_tokens.py" in allowlist,
           "repair_tokens.py is a bare-script allowlist entry")
    expect("generate_openapi.py" in allowlist,
           "generate_openapi.py is a bare-script allowlist entry")
    expect("generate_openapi.py --check" not in allowlist,
           "no separate flagged entry exists once the bare script covers both "
           "forms (see the entry's own r1 for why they were merged)")
    for invocation, entry in allowlist.items():
        expect(len(entry.get("r1", "")) >= 20,
               f"{invocation}: r1 attestation is substantive, not a rubber stamp")
        expect(len(entry.get("r2", "")) >= 20,
               f"{invocation}: r2 attestation is substantive, not a rubber stamp")

    print("check: coverage respects bare-vs-flagged invocation keying")
    expect(sr._covered("repair_tokens.py", "--out t.patch", allowlist),
           "a bare-script entry covers every flag of that script")
    expect(sr._covered("generate_openapi.py", "", allowlist),
           "generate_openapi.py with no flag is covered (writes only its own "
           "single derived artifact — see the entry's r1)")
    expect(sr._covered("generate_openapi.py", "--check", allowlist),
           "generate_openapi.py --check is covered too")
    expect(not sr._covered("sync_mock_api.py", "", allowlist),
           "sync_mock_api.py is NOT covered — issue #116 is not resolved yet, "
           "and a concurrent change is making it loss-safe; allowlisting it "
           "here would attest to a refusal that does not exist")
    expect(not sr._covered("rm_everything.py", "", allowlist),
           "a script nobody ever vetted is not covered")

    print("check: EXEMPT distinguishes a prohibition from a recommendation "
          "using the same wording")
    # This is the control the task asks for: an already-allowlisted script
    # named in passing must not be treated any differently from one named as
    # a deliberate recommendation — both are accounted for once vetted. What
    # this gate CANNOT do is tell "recommends running X" apart from "mentions
    # X was run" for a script that is NOT allowlisted: both produce the same
    # SCRIPT_RUN match, and both fail alike. That is a real precision
    # tradeoff (documented in the module docstring's rule 3 and in this
    # file's own report), accepted because a missed genuine recommendation
    # costs more than a noisy exemption that has to be written down and
    # justified.
    reason = sr.exempt("audit-mock-api.md", "run `/sync-mock-api")
    expect(reason is not None,
           "the 'Auto-run' prohibition has a recorded EXEMPT reason")
    expect(reason is not None and "never do" in reason,
           "the reason explains this is a prohibition, not a recommendation")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("audit_safe_repairers: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
