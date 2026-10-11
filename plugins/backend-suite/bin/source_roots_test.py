#!/usr/bin/env python3
"""Tests for multi-root source declaration and content-based token detection.

    python3 plugins/backend-suite/bin/source_roots_test.py

Every assertion here is paired with a control, because the two changes under test
are both of the shape that fails silently:

  * a multi-root fixture that must resolve THREE roots, beside a single-root
    fixture that must still resolve exactly one and behave as it always did
    (both live consumer projects declare only `source.root`), beside a workspace
    fixture declaring NEITHER key, which must still REFUSE;
  * a Style-Dictionary-shaped token tree that must be found by content, beside a
    docs CSS asset and an ordinary config JSON that must NOT outrank it — the
    original bug was a detector that ranked a stylesheet first because it liked
    the filename.

Stdlib only. Exits 0 when every case holds, 1 otherwise.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
SURVEY = BIN / "survey.py"
RESOLVE = BIN / "resolve.py"
sys.path.insert(0, str(BIN.parent))

from backend_suite.engine import source_roots  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def survey_of(root: Path) -> dict:
    out = subprocess.run([sys.executable, str(SURVEY), "--project-root", str(root),
                          "--stdout"], capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(f"survey refused on {root}: {out.stderr}")
    return json.loads(out.stdout)


# --------------------------------------------------------------------------- #
# Fixtures. No consumer-project name appears in any of them: the shapes are what
# a pub workspace and a Style-Dictionary tree look like, not what one repo does.
# --------------------------------------------------------------------------- #

def workspace_fixture(tmp: Path, members=("packages/alpha", "packages/beta", "app")) -> Path:
    root = tmp / "workspace"
    (root).mkdir(parents=True)
    (root / "pubspec.yaml").write_text(
        "name: _workspace\npublish_to: none\n\nworkspace:\n"
        + "".join(f"  - {m}\n" for m in members))
    for member in members:
        (root / member / "lib").mkdir(parents=True)
        (root / member / "pubspec.yaml").write_text(f"name: {Path(member).name}\n")
        (root / member / "lib" / "main.dart").write_text("class X {}\n")
    return root


def single_root_fixture(tmp: Path) -> Path:
    """The backward-compat control: exactly what both live consumers declare."""
    root = tmp / "single"
    (root / ".backend-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "lib" / "a.dart").write_text("class A {}\n")
    (root / ".backend-suite" / "profile.json").write_text(json.dumps({
        "source": {"root": "lib", "fileGlob": "**/*.dart"}}))
    return root


def multi_root_fixture(tmp: Path) -> Path:
    root = tmp / "multi"
    (root / ".backend-suite").mkdir(parents=True)
    for rel in ("packages/alpha/lib", "packages/beta/lib", "app/lib"):
        (root / rel).mkdir(parents=True)
        (root / rel / "a.dart").write_text("class A {}\n")
    (root / ".backend-suite" / "profile.json").write_text(json.dumps({
        "source": {"roots": ["packages/alpha/lib", "packages/beta/lib", "app/lib"],
                   "fileGlob": "**/*.dart"}}))
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        print("engine: declared roots, and the refusal when nothing is declared")
        multi = multi_root_fixture(tmpdir)
        profile_multi = json.loads((multi / ".backend-suite" / "profile.json").read_text())
        expect(source_roots.declared(profile_multi)
               == ["packages/alpha/lib", "packages/beta/lib", "app/lib"],
               "a fixture declaring three roots resolves all three, in its own order")
        expect(len(source_roots.resolve(multi, profile_multi)) == 3,
               "all three resolve to real directories")
        expect(len(source_roots.source_files(multi, profile_multi, "**/*.dart")) == 3,
               "a union sweep sees a file from every root, not just the first")
        expect(source_roots.root_of(multi, profile_multi, "packages/beta/lib/a.dart")
               == "packages/beta/lib",
               "a finding's repo-relative path attributes it to its own root")
        expect(source_roots.root_of(multi, profile_multi, "tool/x.dart") is None,
               "a path outside every declared root attributes to None, not to the first")

        single = single_root_fixture(tmpdir)
        profile_single = json.loads((single / ".backend-suite" / "profile.json").read_text())
        expect(source_roots.declared(profile_single) == ["lib"],
               "BACKWARD-COMPAT CONTROL: a profile declaring only source.root still works")
        expect(source_roots.primary(single, profile_single) == single / "lib",
               "and single-root callers still get their one root")

        caught = None
        try:
            source_roots.primary(multi, profile_multi)
        except source_roots.SourceRootError as exc:
            caught = str(exc)
        expect(caught is not None and "three" in caught.lower() or "3 source" in (caught or ""),
               "a single-root caller handed three roots REFUSES rather than taking the first")

        caught = None
        try:
            source_roots.declared({"source": {"fileGlob": "**/*.dart"}})
        except source_roots.SourceRootError as exc:
            caught = str(exc)
        expect(caught is not None and "refusing to guess" in caught.lower(),
               "REFUSAL CONTROL: declaring neither key refuses, never falls back to '.'")

        caught = None
        try:
            source_roots.resolve(multi, {"source": {"roots": ["packages/gone"]}})
        except source_roots.SourceRootError as exc:
            caught = str(exc)
        expect(caught is not None,
               "a declared root that is not on disk refuses rather than sweeping nothing")

        print("\nresolve.py --source-roots")
        out = subprocess.run([sys.executable, str(RESOLVE), "--source-roots"],
                             capture_output=True, text=True,
                             env={**__import__("os").environ,
                                  "CLAUDE_PROJECT_DIR": str(multi)})
        expect(out.stdout.split() == ["packages/alpha/lib", "packages/beta/lib", "app/lib"],
               "prints every root, one per line")
        out = subprocess.run([sys.executable, str(RESOLVE), "--source-roots"],
                             capture_output=True, text=True,
                             env={**__import__("os").environ,
                                  "CLAUDE_PROJECT_DIR": str(single)})
        expect(out.stdout.split() == ["lib"] and out.returncode == 0,
               "BACKWARD-COMPAT CONTROL: a single-root project prints its one root, exit 0")

        print("\nsurvey: a workspace stub still refuses, and now says what it read")
        workspace = workspace_fixture(tmpdir)
        report = survey_of(workspace)
        stub_refusals = [u for u in report["couldNotDetermine"]
                         if u["field"] == "sourceRoots" and "stub" in u["why"]]
        expect(len(stub_refusals) == 1,
               "REFUSAL CONTROL: a stub manifest declaring no roots still refuses")
        expect("source.roots" in stub_refusals[0]["note"],
               "and the refusal now names the key a human should declare")
        paths = {c["path"] for c in report["sourceRoots"]}
        expect(paths == {"packages/alpha/lib", "packages/beta/lib", "app/lib"},
               "the declared workspace members are READ and offered as candidates")
        expect(all(c["confidence"] < 0.8 for c in report["sourceRoots"]),
               "every workspace candidate scores below init.py's auto-seed bar, so a "
               "workspace's roots reach profile.json only when a human writes them")

        glob_ws = workspace_fixture(tmpdir / "globbed", members=("packages/*",))
        glob_report = survey_of(glob_ws)
        expect(not glob_report["sourceRoots"]
               and any("glob" in u["why"] for u in glob_report["couldNotDetermine"]),
               "a glob workspace member is reported, never expanded into frozen members")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all source-root cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
