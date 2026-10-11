#!/usr/bin/env python3
"""Prove every eval fixture actually produces the state its cases will branch on.

    python3 plugins/backend-suite/bin/eval_fixture_selftest.py
    python3 plugins/backend-suite/bin/eval_fixture_selftest.py -k service

Exit 0 when every fixture holds, 1 otherwise. Stdlib only.

## Why this is a gate and not a convenience

An eval case for a *declined* role asserts a skill handles exit 4. If the
fixture stops producing exit 4 — someone edits the decline out, `decline_doc.py`
changes shape, the manifest key is renamed — the case does not fail. It passes,
because the skill behaves perfectly well on a role that is simply mapped. The
suite goes green while measuring nothing.

That is this repo's governing principle pointed at its own test harness: **a
fixture that does not produce its state is INERT, and INERT must never be
baselined clean.** So every state a case is allowed to branch on is asserted
here first, for free, before any model is ever paid to look at it.

## Negative controls are half of it

Each positive is paired with a control, in the style of `resolve_test.py` and
`project_root_test.py`. A resolver that returned 5 for every role would satisfy
"the stub role exits 5" and tell us nothing — so the authored role is asserted
NOT to exit 5 in the same fixture, and the declined role is asserted to be the
only one printing its reason. A check that cannot distinguish its states is the
same silence in a different costume.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
PLUGIN_ROOT = BIN.parent
FIXTURE_BUILDER = PLUGIN_ROOT / "evals" / "_fixtures" / "build_fixture.py"

sys.path.insert(0, str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT / "evals" / "_fixtures"))

from backend_suite.engine import archetypes  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("_build_fixture", FIXTURE_BUILDER)
build_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_fixture)

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def resolve(fixture: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the real resolver against a fixture.

    CLAUDE_PROJECT_DIR is how `project_root()` is told which repo it is looking
    at, and it is set explicitly rather than relying on cwd: a fixture built
    under a temp dir would otherwise be found by the cwd walk only by accident,
    and an accident that works is an accident that stops working.
    """
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(fixture)
    return subprocess.run([sys.executable, str(BIN / "resolve.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(fixture))


def resolve_rootless(fixture: Path, *args: str) -> subprocess.CompletedProcess:
    """The same, with CLAUDE_PROJECT_DIR deliberately absent.

    This is the only way to exercise `project_root()`'s refusal: with the
    variable set it never walks, so a `zero-state` assertion made through it
    would prove nothing about the path a real adopter takes.
    """
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([sys.executable, str(BIN / "resolve.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(fixture))


def profile_of(fixture: Path) -> dict:
    return json.loads((fixture / ".backend-suite/profile.json").read_text())


# --------------------------------------------------------------------------- #
# One checker per fixture. Each asserts exactly the states a case may branch on
# — nothing more, so that a case relying on an unasserted detail is a gap this
# file can be extended to close rather than a detail it silently blessed.
# --------------------------------------------------------------------------- #

def check_zero_state(fixture: Path) -> None:
    expect(not (fixture / ".backend-suite").exists(),
           "zero-state: has no .backend-suite/ at all")
    expect(any(fixture.rglob("*.dart")),
           "zero-state: has real source files (an empty dir is a different fixture)")

    proc = resolve_rootless(fixture, build_fixture.AUTHORED_ROLE)
    expect(proc.returncode == 2,
           f"zero-state: resolve.py exits 2 via project_root() (got {proc.returncode})")
    expect(".backend-suite" in proc.stderr,
           "zero-state: the refusal names the marker it could not find")
    expect("Refusing to guess" in proc.stderr,
           "zero-state: the refusal says it is refusing, not reporting nothing")


def check_service(fixture: Path) -> None:
    authored = build_fixture.AUTHORED_ROLE
    stub = build_fixture.STUB_ROLE
    declined = build_fixture.DECLINED_ROLE

    proc = resolve(fixture, authored)
    expect(proc.returncode == 0,
           f"service: authored role {authored!r} resolves clean, exit 0 (got {proc.returncode})")

    proc = resolve(fixture, stub)
    expect(proc.returncode == 5,
           f"service: stub role {stub!r} exits 5 (got {proc.returncode})")
    expect(bool(proc.stdout.strip()),
           "service: the stub still PRINTS its path — a caller filling it needs the path")

    proc = resolve(fixture, declined)
    expect(proc.returncode == 4,
           f"service: declined role {declined!r} exits 4 (got {proc.returncode})")
    # The reason is the entire point of the declined state. A decline with no
    # recorded reason resolves to the literal string below, and a fixture in
    # that shape would let a case pass while asserting nothing about reasons.
    expect("NO REASON RECORDED" not in proc.stdout,
           "service: the decline carries a real reason, not the no-reason sentinel")
    expect(build_fixture.DECLINE_REASON.split(";")[0].strip() in proc.stdout,
           "service: the decline prints the reason the builder recorded")

    # Negative controls: the three states must be distinguishable from each
    # other, not merely each individually observed.
    expect(resolve(fixture, authored).returncode != 5,
           "service: the authored role is NOT reported as a stub (control)")
    expect(resolve(fixture, authored).returncode != 4,
           "service: the authored role is NOT reported as declined (control)")
    expect(resolve(fixture, stub).returncode != 4,
           "service: the stub is NOT reported as declined (control)")

    expect(archetypes.kind_of(profile_of(fixture)) == "service",
           "service: declares projectKind service")



def check_library(fixture: Path) -> None:
    expect(not (fixture / ".backend-suite").exists(),
           "library: undeclared variant has no .backend-suite/")
    # Package-shaped is asserted on SHAPE, not on language. This used to read
    # `package.json exists AND no lib/**/*.dart`, which made "is a package" and
    # "is TypeScript" the same assertion — so the fixture could not become the
    # Dart promotion target `_fixtures/app` needs without this failing for a
    # reason that had nothing to do with the property it names. What actually
    # matters is that it publishes components and has no screens or routes.
    expect((fixture / build_fixture.DS_MANIFEST).is_file(),
           "library: carries a package manifest")
    expect(any(fixture.glob(build_fixture.DS_COMPONENT_GLOB)),
           "library: exports components — what a package library is for")
    screens = sorted(p.name for p in fixture.rglob("*")
                     if p.is_file() and ("screen" in p.name or "route" in p.name))
    expect(not screens,
           f"library: has no screens or routes to mistake it for an app "
           f"(found {screens})")
    # Control: the same probe DOES find screens in the `app` fixture, so the
    # emptiness above is a fact about this fixture and not a broken measurement.
    with tempfile.TemporaryDirectory() as tmp:
        svc = build_fixture.build("service", Path(tmp) / "service", force=True)
        expect(any("screen" in p.name for p in svc.rglob("*") if p.is_file()),
               "library: the same screen probe finds screens in `service` (control)")
    proc = resolve_rootless(fixture, "api")
    expect(proc.returncode == 2,
           f"library: every bin/*.py refuses here too (got {proc.returncode})")


def check_library_declared(fixture: Path) -> None:
    kind = archetypes.kind_of(profile_of(fixture))
    expect(kind == "library", f"library-declared: kind_of is library (got {kind})")
    roles = set(archetypes.roles_for(kind))
    # The roles that carry a package's consumer contract. If these ever stop
    # being library-flavoured, the fixture is no longer exercising an archetype.
    for role in ("changelog", "deprecations"):
        expect(role in roles, f"library-declared: role {role!r} applies")
    # deployment is na for a library — a package is consumed, not deployed.
    expect("deployment" not in roles,
           "library-declared: 'deployment' (a service's role) does NOT apply (control)")

    # MEASURED, not asserted from prose: which roles one kind owns exclusively
    # (non-na here, na for every other kind). Computed so the fixture cannot
    # outlive the claim.
    service_exclusive = [role for role in archetypes.roles()
                         if archetypes.applicability(role, "service") != "na"
                         and all(archetypes.applicability(role, other) == "na"
                                 for other in archetypes.kinds() if other != "service")]
    expect("deployment" in service_exclusive,
           f"library-declared: deployment is service-exclusive (measured: {service_exclusive})")
    library_exclusive = [role for role in archetypes.roles()
                         if archetypes.applicability(role, "library") != "na"
                         and all(archetypes.applicability(role, other) == "na"
                                 for other in archetypes.kinds() if other != "library")]
    expect(library_exclusive == [],
           f"library-declared: no role is library-exclusive — the package kinds share "
           f"their core with services (measured: {library_exclusive})")


def check_undeclared_kind(fixture: Path) -> None:
    profile = profile_of(fixture)
    expect("projectKind" not in profile.get("project", {}),
           "undeclared-kind: profile really has no projectKind key")
    try:
        got = archetypes.kind_of(profile)
        expect(False, f"undeclared-kind: kind_of must raise, but returned {got!r}")
    except archetypes.ArchetypeNotDeclared:
        expect(True, "undeclared-kind: kind_of raises ArchetypeNotDeclared")
    except archetypes.ArchetypeError as exc:
        # An UnknownArchetype here would mean the key is present but wrong — a
        # different fixture entirely, and one a case would branch on differently.
        expect(False, f"undeclared-kind: raised the wrong refusal ({type(exc).__name__})")

    proc = resolve(fixture, "--project-kind")
    expect(proc.returncode == 2,
           f"undeclared-kind: resolve.py --project-kind exits 2 (got {proc.returncode})")
    expect("do not assume one" in proc.stderr,
           "undeclared-kind: the refusal tells the caller not to guess")
    # Control: the rest of the manifest still works, so a case that hits the
    # archetype refusal is hitting THAT and not a broken fixture.
    expect(resolve(fixture, build_fixture.AUTHORED_ROLE).returncode == 0,
           "undeclared-kind: ordinary role resolution still works (control)")


def check_pre_ratified(fixture: Path) -> None:
    field = build_fixture.RATIFIED_FIELD
    entry = profile_of(fixture).get("provenance", {}).get("fields", {}).get(field)
    expect(isinstance(entry, dict), f"pre-ratified: {field} has a provenance entry")
    if not isinstance(entry, dict):
        return
    expect(entry.get("state") == "approved",
           f"pre-ratified: {field} reads as approved (got {entry.get('state')!r})")
    for key in ("by", "on", "value", "evidence"):
        expect(bool(entry.get(key)), f"pre-ratified: {field} carries {key!r}")
    expect(bool((entry.get("verifiedAgainst") or {}).get("commit")),
           f"pre-ratified: {field} carries verifiedAgainst.commit")
    # The ratified value must agree with the profile, or the fixture is testing
    # a CONTRADICTED field rather than a ratified one — a different state, and
    # one a case would rightly expect different behaviour on.
    expect(profile_of(fixture).get("source", {}).get("root") == entry.get("value"),
           f"pre-ratified: {field}'s ratified value matches the profile (not contradicted)")
    # Control: not everything is approved, so a skill that respects the whole
    # file rather than this one field is not accidentally passing.
    others = {k: v for k, v in profile_of(fixture)["provenance"]["fields"].items() if k != field}
    expect(all(v.get("state") != "approved" for v in others.values() if isinstance(v, dict)),
           "pre-ratified: it is the ONLY approved field (control)")


def check_scaffold_shims() -> None:
    """The properties the CASES depend on, which no single fixture check sees.

    Three of them, each found the expensive way by someone else's run rather
    than reasoned about here:

      * `context.scaffold_script` is rejected if it escapes the case directory,
        so every fixture must ship a `scaffold.sh` a case's in-directory shim
        can exec. A fixture with no shim is a fixture no case can reach;
      * a `case.yaml` or `prompt.md` ANYWHERE under `_fixtures/` makes case
        discovery — which walks the whole eval dir — try to run a fixture as a
        case;
      * the shim must be runnable by `bash`, not merely present.
    """
    fixtures_dir = FIXTURE_BUILDER.parent
    for name in sorted(build_fixture.FIXTURES):
        shim = fixtures_dir / name / "scaffold.sh"
        expect(shim.is_file(), f"shims: {name}/scaffold.sh exists")
        if shim.is_file():
            expect(f" {name} " in shim.read_text() or f"py\" {name} " in shim.read_text(),
                   f"shims: {name}/scaffold.sh builds the fixture of its own name")

    strays = [p for marker in ("case.yaml", "case.yml", "prompt.md")
              for p in fixtures_dir.rglob(marker)]
    expect(not strays,
           f"shims: no case file anywhere under _fixtures/ — discovery walks the "
           f"whole eval dir and would run a fixture as a case (found: {strays})")


def check_no_provenance_prose(fixture: Path) -> None:
    """Profiles must not mention `approved`/`declared` outside a real entry.

    The cases' strongest graders are `not_contains` over the whole profile, and
    the template's `provenance._readme` explains the vocabulary in prose —
    three `approved`, two `declared` — so a fixture where NOTHING is ratified
    would false-fail them. The builder strips those non-semantic keys; this
    asserts it still does.
    """
    path = fixture / ".backend-suite/profile.json"
    if not path.is_file():
        return
    text = path.read_text()
    field = build_fixture.RATIFIED_FIELD
    entry = json.loads(text).get("provenance", {}).get("fields", {}).get(field, {})
    ratified = isinstance(entry, dict) and entry.get("state") == "approved"
    want = 1 if ratified else 0
    expect(text.count("approved") == want,
           f"{fixture.name}: profile contains `approved` exactly {want} time(s) "
           f"(got {text.count('approved')})")
    expect(text.count("declared") == 0,
           f"{fixture.name}: profile never contains `declared` "
           f"(got {text.count('declared')})")
    if ratified:
        expect("verifiedAgainst" in text,
               f"{fixture.name}: profile carries a verifiedAgainst")


CHECKS = {
    "zero-state": check_zero_state,
    "service": check_service,
    "library": check_library,
    "library-declared": check_library_declared,
    "undeclared-kind": check_undeclared_kind,
    "pre-ratified": check_pre_ratified,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", metavar="SUBSTR", help="only fixtures whose name contains SUBSTR")
    ap.add_argument("--keep", metavar="DIR",
                    help="build into DIR and leave it behind, for debugging")
    args = ap.parse_args()

    names = [n for n in CHECKS if not args.k or args.k.lower() in n.lower()]

    # Every fixture must have a checker and every checker a fixture. A fixture
    # added to the builder with nothing asserting its state is the exact silence
    # this file exists to prevent, so it is a failure rather than a note.
    unchecked = sorted(set(build_fixture.FIXTURES) - set(CHECKS))
    if unchecked:
        print(f"FAIL fixtures with no self-test: {unchecked}. A fixture nothing "
              f"asserts is INERT — add a checker or delete the fixture.", file=sys.stderr)
        return 1
    if not names:
        print(f"no fixture matched {args.k!r}. Nothing ran, which is not the same "
              f"as everything passing.", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(args.keep) if args.keep else Path(tmp)
        for name in names:
            print(f"\n{name}")
            try:
                root = build_fixture.build(name, base / name, force=True)
            except SystemExit as exc:
                expect(False, f"{name}: fixture failed to build — {exc}")
                continue
            CHECKS[name](root)
            # Applied to EVERY fixture, not just the ones whose own checker
            # cares: the `not_contains` graders are written against whichever
            # fixture a case happens to use.
            check_no_provenance_prose(root)

    print("\nscaffold shims")
    check_scaffold_shims()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} assertion(s) failed:", file=sys.stderr)
        for line in FAILURES:
            print(f"  - {line}", file=sys.stderr)
        print("\nA fixture that does not produce its state is INERT. Fix the fixture "
              "before running any case built on it.", file=sys.stderr)
        return 1
    print(f"{len(names)} fixture(s) produce every state their cases branch on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
