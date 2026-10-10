#!/usr/bin/env python3
"""Tests for resolve.py's exit-code contract, and its parity copy in house-style.

Every case here is paired against a negative control, because an exit-code check
that only ever sees the interesting input proves nothing: a stub assertion passes
just as happily against a resolver that returns 5 for everything. So each new code
is tested beside a document that must NOT produce it — a written document that
must still exit 0, and a role that is neither declined nor stubbed.

`house-style/bin/resolve_role.py` is a deliberate duplicate that cannot
import the real resolver (plugin-cache version hashes; see its docstring), so the
codes skills branch on are asserted against BOTH binaries from one fixture. That
is the only thing keeping the copy honest.

    python3 plugins/design-suite/bin/resolve_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
RESOLVE = BIN / "resolve.py"
HOUSE_STYLE = BIN.parents[1] / "house-style" / "bin" / "resolve_role.py"
FAILURES: list[str] = []


def run(script: Path, root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env, cwd=str(root))


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def fixture(tmp: Path) -> Path:
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "DESIGN.md").write_text("# Design\n\nWritten.\n")
    (root / "docs" / "FLOWS.md").write_text("---\nstatus: stub\n---\n\nTODO\n")
    # A document whose frontmatter exists but says something else: `status:` is not
    # a synonym for "stub", and a check keyed on the key rather than the value would
    # report every front-mattered document in a project as unwritten.
    (root / "docs" / "DECISIONS.md").write_text("---\nstatus: living\n---\n\nReal.\n")
    (root / "docs" / "ENTRY.md").write_text("# Start here\n\nWritten.\n")
    (root / ".design-suite" / "docs.manifest.json").write_text(json.dumps({
        "roles": {"design": "docs/DESIGN.md", "flows": "docs/FLOWS.md",
                  "decisions": "docs/DECISIONS.md",
                  # Mapped under the CURRENT name, so asking by the OLD one
                  # exercises the forward alias direction.
                  "entry-point": "docs/ENTRY.md"},
        "externalRoles": {"components": {"repo": "https://example.invalid/ds",
                                         "path": "COMPONENTS.md"}},
        "declinedRoles": {
            "_comment": "ignored, same convention as externalRoles",
            "motion": {"declined": "folded into theming", "by": "lead", "on": "2026-09-15"},
        },
        "directories": {},
    }))
    return root


def alias_fixture(tmp: Path, name: str, manifest: dict) -> Path:
    """A minimal project whose manifest is written one way round, so the resolver
    has to follow the rename to answer at all."""
    root = tmp / name
    (root / ".design-suite").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "ENTRY.md").write_text("# Start here\n\nWritten.\n")
    (root / ".design-suite" / "docs.manifest.json").write_text(json.dumps(manifest))
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))

        # The rename bridge, asserted against both resolvers because the alias
        # table itself lives in two places — templates/docs/roles.json's
        # `aliases`, and resolve_role.py's local ALIASES constant, whose own
        # comment calls a divergence here "exactly the drift the parity test
        # exists to catch". Until now the test asserted no such thing.
        #
        # Both directions are asserted, and they are genuinely different cases:
        # a manifest written before the rename has to answer a skill written
        # after it, and a manifest written after it has to answer a skill (or a
        # chain, or a consumer's own script) written before. One-directional
        # alias handling passes the first and fails the second.
        legacy = alias_fixture(Path(tmp), "legacy", {
            "roles": {"instructions": "docs/ENTRY.md"},
        })
        declined_alias = alias_fixture(Path(tmp), "declined-alias", {
            "roles": {},
            "declinedRoles": {"entry-point": {"declined": "single-file repo",
                                              "by": "lead", "on": "2026-09-16"}},
        })

        for script in (RESOLVE, HOUSE_STYLE):
            name = script.name
            print(f"check: {name} role aliases")

            result = run(script, root, "instructions")
            expect(result.returncode == 0,
                   f"{name}: the old name 'instructions' still resolves (exit 0)")
            expect(result.stdout.strip() == "docs/ENTRY.md",
                   f"{name}: 'instructions' resolves to the 'entry-point' mapping")

            result = run(script, legacy, "entry-point")
            expect(result.returncode == 0,
                   f"{name}: 'entry-point' resolves against a pre-rename manifest")
            expect(result.stdout.strip() == "docs/ENTRY.md",
                   f"{name}: reverse alias finds the old 'instructions' mapping")

            # A decline recorded under one name must still be seen when a skill
            # asks by the other, or the decline silently stops applying — the
            # exact hazard resolve.py's own comment names.
            result = run(script, declined_alias, "instructions")
            expect(result.returncode == 4,
                   f"{name}: a decline on 'entry-point' answers 'instructions' with 4")
            expect("single-file repo" in result.stdout,
                   f"{name}: the aliased decline still prints its recorded reason")

        for script in (RESOLVE, HOUSE_STYLE):
            name = script.name
            print(f"check: {name} exit codes")

            result = run(script, root, "design")
            expect(result.returncode == 0, f"{name}: a written document exits 0")
            expect(result.stdout.strip() == "docs/DESIGN.md", f"{name}: prints its path")

            result = run(script, root, "decisions")
            expect(result.returncode == 0,
                   f"{name}: frontmatter with a non-stub status still exits 0")

            result = run(script, root, "flows")
            expect(result.returncode == 5, f"{name}: a stub exits 5, not 0")
            expect(result.stdout.strip() == "docs/FLOWS.md",
                   f"{name}: a stub still prints its path — whoever fills it needs it")

            result = run(script, root, "motion")
            expect(result.returncode == 4, f"{name}: a declined role exits 4, not 2")
            expect("folded into theming" in result.stdout,
                   f"{name}: prints the recorded reason, so a skill can put it in its report")

            result = run(script, root, "components")
            expect(result.returncode == 3, f"{name}: external is still 3")

            result = run(script, root, "nosuch")
            expect(result.returncode == 2, f"{name}: an unknown role is still 2")
            expect("motion" in result.stderr,
                   f"{name}: lists declined roles when rejecting an unknown one")

        print("check: --all marks the states apart")
        out = run(RESOLVE, root, "--all").stdout
        expect("docs/FLOWS.md\t(stub)" in out, "--all marks the stub")
        expect("docs/DESIGN.md\n" in out, "--all leaves a written document unmarked")
        expect("(declined)" in out, "--all lists the declined role")

        print("check: --all marks a mapped-but-absent file, and --check exits 1 on it")
        manifest_path = root / ".design-suite" / "docs.manifest.json"
        original = manifest_path.read_text()
        m = json.loads(original)
        m["roles"]["backlog"] = "docs/NOT_WRITTEN_YET.md"
        manifest_path.write_text(json.dumps(m))
        proc = run(RESOLVE, root, "--all")
        expect("docs/NOT_WRITTEN_YET.md\t(missing)" in proc.stdout and proc.returncode == 0,
               "--all marks the missing file and still exits 0 as a listing")
        expect(run(RESOLVE, root, "--all", "--check").returncode == 1,
               "--all --check exits 1 when a mapped file is missing")
        manifest_path.write_text(original)

        print("check: doctor and design_debt count the stub as debt, not coverage")
        (root / ".design-suite" / "profile.json").write_text(json.dumps(
            {"docs": {"manifest": ".design-suite/docs.manifest.json"}}))
        doctor = run(BIN / "doctor.py", root)
        expect("flows" in doctor.stdout and "STUB" in doctor.stdout,
               "doctor names the stub role")
        debt = run(BIN / "design_debt.py", root, "--json")
        payload = json.loads(debt.stdout).get("docs", {})
        expect(payload.get("stubs") == ["flows"], "design_debt lists the stub")
        # Four roles mapped, three written: the alias fixture's `entry-point`
        # is a fourth written document, and the stub is still excluded.
        expect(payload.get("written") == 3 and payload.get("mapped") == 4,
               "design_debt excludes the stub from the written count")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("resolve.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
