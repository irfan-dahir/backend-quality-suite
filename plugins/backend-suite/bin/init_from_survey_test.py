#!/usr/bin/env python3
"""Tests for `init.py --from-survey` (RFC-0002 phase 4).

Built around a fixture the survey can partly read and deliberately cannot fully
read, because a run in which everything is inferred proves nothing: the
surviving TODO is the control. A seeder table that silently stopped firing and a
project the survey genuinely cannot describe produce the same profile unless the
two are asserted separately.

    python3 plugins/backend-suite/bin/init_from_survey_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

INIT = Path(__file__).resolve().parent / "init.py"
FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'}  {what}")
    if not condition:
        FAILURES.append(what)


def plant(root: Path) -> None:
    """A project whose stack the survey CAN read and whose tokens it cannot."""
    (root / "lib" / "features").mkdir(parents=True)
    (root / "pubspec.yaml").write_text("name: fixture\ndependencies:\n  flutter:\n    sdk: flutter\n")
    (root / "lib" / "main.dart").write_text("void main() {}\n")
    (root / "lib" / "features" / "home.dart").write_text("class Home {}\n")


def run_init(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(INIT), "--dir", str(root), *args],
                          capture_output=True, text=True)


def leaf(profile: dict, dotted: str):
    node = profile
    for key in dotted.split("."):
        node = node[key]
    return node


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "seeded"
        root.mkdir()
        plant(root)
        result = run_init(root, "--name", "Fixture", "--from-survey")
        expect(result.returncode == 0, f"--from-survey exits 0 (got {result.returncode})")

        profile = json.loads((root / ".backend-suite" / "profile.json").read_text())
        entries = profile["provenance"]["fields"]

        expect(bool(entries), "something was seeded — an empty seed would make every "
                              "assertion below vacuously true")
        expect(all(e["state"] == "inferred" for e in entries.values()),
               "EVERY seeded field is 'inferred' — never 'declared', never 'approved'")
        expect(leaf(profile, "source.root") == "lib" and "source.root" in entries,
               "a field the survey determined is seeded and carries its provenance")

        # The control. tokens.source.path is the field survey.py refuses to
        # settle on principle, so its TODO must survive untouched.
        expect(str(leaf(profile, "tokens.source.path")).startswith("TODO"),
               "CONTROL: a field the survey could not determine is still a TODO")
        expect("tokens.source.path" not in entries,
               "CONTROL: and carries no provenance entry claiming otherwise")
        expect(str(leaf(profile, "project.audience")).startswith("TODO"),
               "CONTROL: intent (audience) is never inferred from a codebase")

        # The chain's next step consumes this profile: map_project.py refuses to
        # write any inferred entry carrying a human's keys, and init.py once
        # stamped `value`/`verifiedAgainst` on every seeded field — so the very
        # next /map-project proposal on a seeded profile exited 2.
        expect(all(set(e) == {"state", "evidence"} for e in entries.values()),
               "seeded entries are exactly {state, evidence} — map_project.py's whitelist")
        mapped = subprocess.run(
            [sys.executable, str(INIT.parent / "map_project.py"), "--dir", str(root),
             "--field", "project.projectKind", "--value", "app", "--evidence",
             "pubspec.yaml declares a Flutter app with a main.dart entry point and "
             "feature directories, and no published package surface."],
            capture_output=True, text=True)
        expect(mapped.returncode == 0,
               f"map_project.py accepts a proposal on a freshly seeded profile "
               f"(got {mapped.returncode}: {mapped.stderr.strip()[:160]})")

        # Re-inferring over a profile that may hold ratified values would invert
        # the provenance model, so the second run must refuse rather than seed.
        again = run_init(root, "--from-survey")
        expect(again.returncode == 1 and "Refusing" in again.stderr,
               "a second --from-survey refuses rather than overwriting an existing profile")

        plain_root = Path(tmp) / "plain"
        plain_root.mkdir()
        plant(plain_root)
        expect(run_init(plain_root, "--name", "Fixture").returncode == 0, "plain init still exits 0")
        plain = json.loads((plain_root / ".backend-suite" / "profile.json").read_text())
        expect(str(leaf(plain, "source.root")).startswith("TODO")
               and not (plain_root / ".backend-suite" / "survey.json").exists(),
               "plain init is unchanged: no seeding, no survey written")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("init.py --from-survey: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
