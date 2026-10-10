#!/usr/bin/env python3
"""Tests for directory-valued doc roles, one fixture per state.

    python3 plugins/design-suite/bin/directory_roles_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.

## What this is guarding

A directory role has FOUR states and they must produce four different exit codes
— see `design_suite/engine/doc_roles.py` for the argument. Three of them are
refusals, and the dangerous one is `empty`: a directory that exists and holds
nothing is the state a caller would glob, get `[]` from, and grade clean. That is
this repository's governing failure with a directory in front of it.

Every state is therefore asserted BESIDE the others, from one manifest, in one
run. A test that only ever built the populated case would pass just as happily
against a resolver that returned 0 for everything — and a test that only built
the empty case would pass against one that returned 2 for everything. The four
codes are only meaningful as a set of four *distinct* answers, so the test
asserts distinctness explicitly rather than trusting four separate equalities.
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
FAILURES: list[str] = []

STUB = ("---\nstatus: stub\n---\n\nTODO\n")


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(RESOLVE), *args],
                          capture_output=True, text=True, env=env, cwd=str(root))


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def fixture(tmp: Path) -> Path:
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)

    # POPULATED: an index plus two pages, one of them still a stub. A directory
    # with *some* stubs is coverage — the stub rule is about ALL of them, and a
    # fixture with only clean pages would not tell those two apart.
    pages = root / "docs" / "pages"
    pages.mkdir(parents=True)
    (pages / "index.md").write_text("# Index\n")
    (pages / "one.md").write_text("# One\n\nWritten.\n")
    (pages / "two.md").write_text(STUB)
    # Nested, to prove members are found recursively: a design system that groups
    # its pages into subdirectories has not stopped documenting them.
    (pages / "group").mkdir()
    (pages / "group" / "three.md").write_text("# Three\n\nWritten.\n")

    # STUBS ONLY: registered, scaffolded, unwritten.
    stubs = root / "docs" / "stubs"
    stubs.mkdir()
    (stubs / "a.md").write_text(STUB)
    (stubs / "b.md").write_text(STUB)

    # EMPTY: exists, and holds no document. The state that must never be 0.
    (root / "docs" / "empty").mkdir()

    # EMPTY, with a non-document in it. A stray image is not coverage, and a
    # member count that included it would report this directory as populated —
    # the same bug wearing a different file extension.
    noise = root / "docs" / "noise"
    noise.mkdir()
    (noise / "diagram.svg").write_text("<svg/>")
    (noise / "data.json").write_text("{}")

    # ABSENT: docs/gone is deliberately never created.

    (root / "docs" / "DESIGN.md").write_text("# Design\n\nWritten.\n")

    (root / ".design-suite" / "docs.manifest.json").write_text(json.dumps({
        "roles": {
            "components": {"directory": "docs/pages"},
            "patterns": {"directory": "docs/stubs"},
            "gallery": {"directory": "docs/empty"},
            "theming": {"directory": "docs/noise"},
            "figma": {"directory": "docs/gone"},
            # A plain string role in the same manifest: the directory branch must
            # not change how an ordinary file role behaves, and a test with no
            # file role could not notice if it did.
            "design": "docs/DESIGN.md",
        },
    }))
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        codes = {}

        print("check: the four directory states produce four distinct exit codes")

        for role, want, label in (
            ("components", 0, "populated -> 0 (real coverage)"),
            ("patterns", 5, "stubs only -> 5 (registered, unwritten)"),
            ("gallery", 2, "empty -> 2 (I could not look)"),
            ("theming", 2, "non-document members only -> 2 (a stray file is not coverage)"),
            ("figma", 1, "absent -> 1 (mapped, does not exist)"),
        ):
            result = run(root, role)
            codes[role] = result.returncode
            expect(result.returncode == want, f"{label}; got {result.returncode}")

        expect(len({codes["components"], codes["patterns"],
                    codes["gallery"], codes["figma"]}) == 4,
               "the four states are four DIFFERENT codes, not four assertions "
               "that happen to hold")

        print("check: the path is printed in every state, refusals included")
        for role, where in (("components", "docs/pages"), ("patterns", "docs/stubs"),
                            ("gallery", "docs/empty"), ("figma", "docs/gone")):
            result = run(root, role)
            expect(result.stdout.splitlines()[0].strip() == where,
                   f"{role}: prints {where} on stdout even when refusing")

        print("check: every refusal says WHY on stderr, by name")
        for role, word in (("patterns", "stub"), ("gallery", "could not look"),
                           ("figma", "does not exist")):
            result = run(root, role)
            expect(word in result.stderr,
                   f"{role}: stderr names the state ({word!r})")
        expect(run(root, "components").stderr.strip() == "",
               "components: the healthy state says nothing on stderr")

        print("check: --members lists documents, and lists the right ones")
        result = run(root, "components", "--members")
        listed = result.stdout.splitlines()[1:]
        expect(any(p.endswith("group/three.md") for p in listed),
               "--members finds nested pages (recursive)")
        expect(not any(p.endswith("two.md") for p in listed),
               "--members on a populated role lists AUTHORED pages, not the stub")
        result = run(root, "patterns", "--members")
        expect(len(result.stdout.splitlines()[1:]) == 2,
               "--members on a stubs-only role lists the stubs (they are the work)")

        print("check: --reverse answers for a path INSIDE a directory role")
        result = run(root, "--reverse", "docs/pages/group/three.md")
        expect(result.returncode == 0 and result.stdout.strip() == "components",
               "a member document resolves to the directory role")
        result = run(root, "--reverse", "docs/pages")
        expect(result.returncode == 0 and result.stdout.strip() == "components",
               "the directory itself resolves to the role")
        # CONTROL. A path that merely shares a prefix must NOT be claimed: a
        # startswith() with no separator would hand `docs/pagesX.md` the role,
        # which is how a reverse lookup starts answering confidently and wrongly.
        result = run(root, "--reverse", "docs/pagesX.md")
        expect(result.returncode == 2,
               "CONTROL: a path that only shares a prefix is not claimed")
        result = run(root, "--reverse", "docs/elsewhere/thing.md")
        expect(result.returncode == 2,
               "CONTROL: an unrelated path still exits 2")

        print("check: plain file roles are unaffected")
        result = run(root, "design")
        expect(result.returncode == 0 and result.stdout.strip() == "docs/DESIGN.md",
               "CONTROL: a string-valued role still resolves to its file, exit 0")
        expect(run(root, "nonexistent-role").returncode == 2,
               "CONTROL: an unknown role still exits 2")

        print("check: --all marks directory roles, in every state")
        out = run(root, "--all").stdout
        expect("(directory: populated)" in out and "(directory: empty)" in out
               and "(directory: stubs-only)" in out and "(directory: absent)" in out,
               "--all names each directory role's state rather than listing it "
               "like a file")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("directory roles: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
