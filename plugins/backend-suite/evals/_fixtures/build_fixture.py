#!/usr/bin/env python3
"""Build one eval fixture — a throwaway consumer project in a known state.

    python3 plugins/backend-suite/evals/_fixtures/build_fixture.py service --dir /tmp/x
    python3 .../build_fixture.py --list

This is the `context.scaffold_script` end of an eval case: a case names a
fixture, the harness runs this to materialise it, and the case then asserts what
a skill does when pointed at it.

## Why a script and not committed files

A fixture is only useful if it is what `init.py` *actually* produces. A
committed tree of `.backend-suite/` files is a photograph of what init.py
produced on the day someone ran it, and it goes stale silently — the fixture
keeps passing, the tool it stands in for has moved, and every case built on it
is now measuring a project shape no real adopter has. That is this repo's
governing failure (a check whose silence reads as a pass) relocated into the
test harness.

So every `.backend-suite/` file here comes from running the real tools:

    bin/init.py          scaffolds the config
    bin/decline_doc.py   records the decline, with its reason
    bin/scaffold_doc.py  writes the stub, with its `status: stub` frontmatter

and this script only does the two things those tools deliberately do not:
declare a `projectKind` (init.py leaves archetype declaration to a human) and
write a `provenance.fields` entry at `approved` (init.py will only ever write
`inferred`, by design — see its SEEDED_STATE comment).

The **source** files are written literally, because there is no tool that
generates a consumer project's source and inventing one would be a bigger lie
than a five-file stub. They are deliberately tiny and generic: enough shape for
a skill to read an archetype off, no more.

## What each fixture is for

See FIXTURES in this file — each entry carries the state it exists to produce.
`fixture_selftest.py` asserts every one of those states actually holds, so a
fixture that stops producing its state fails before any model ever sees it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
BIN = PLUGIN_ROOT / "bin"

# The role the `service` fixture authors for real, declines, and stubs. Named
# once here and imported by the self-test so the two cannot drift into asserting
# a state the builder stopped producing.
AUTHORED_ROLE = "api"
STUB_ROLE = "rfc"
DECLINED_ROLE = "public-roadmap"
DECLINE_REASON = ("this project has no public roadmap of its own; committing to "
                  "one unprompted would be a promise nobody asked for and a "
                  "second list to drift from the backlog")

# The field the `pre-ratified` fixture marks as a human decision. `source.root`
# is chosen because it is also one of init.py's --from-survey seed targets, so
# the fixture exercises the exact collision that matters: a skill re-inferring a
# field a human has already ratified.
RATIFIED_FIELD = "source.root"

# The fixture tree's own layout, named once here and imported by the self-test.
#
# Same reason AUTHORED_ROLE / STUB_ROLE / DECLINED_ROLE are named here: the
# builder and the thing asserting the builder's output must not drift into
# describing different trees. It also keeps these literals out of `bin/`, where
# audit_skill_paths.py correctly reports a hardcoded project path as a defect —
# in bin/ a path like `app/Http/…` is an assumption about a CONSUMER's
# layout, which is the thing the universal plugin may never make. Here it is
# not an assumption at all: it is this builder's own output, three functions up.
#
# Package manifests and the directory the library fixture publishes its API
# from — both stacks' package manifest is composer.json, which is part of why
# the archetype vocabulary could be measured on one language pair.
APP_MANIFEST = "composer.json"
DS_MANIFEST = "composer.json"
DS_COMPONENT_GLOB = "src/*.php"


def _run(args: list[str], cwd: Path | None = None) -> None:
    """Run one of the real tools, or die naming it.

    CLAUDE_PROJECT_DIR is cleared for the child: these tools prefer it over the
    --dir they were handed, so a builder invoked from inside a configured
    project would otherwise scaffold into that project instead of the fixture.
    """
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"fixture build step failed ({proc.returncode}): "
                         f"{' '.join(args)}\n{proc.stdout}\n{proc.stderr}")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _edit_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Source shapes. Literal by necessity (see module docstring), generic on
# purpose: no client name, no real product, nothing a reader could mistake for
# a consumer project's actual code.
# --------------------------------------------------------------------------- #

def _app_sources(root: Path) -> None:
    _write(root, "README.md", "# Example Service\n\nA small HTTP API: routes, controllers and a domain.\n")
    _write(root, APP_MANIFEST,
           "{\n"
           '  "name": "example/service",\n'
           '  "description": "A small HTTP API: routes, controllers and a domain.",\n'
           '  "require": {\n'
           '    "php": "^8.1"\n'
           "  },\n"
           '  "autoload": {\n'
           '    "psr-4": {\n'
           '      "App\\\\": "app/"\n'
           "    }\n"
           "  }\n"
           "}\n")
    # The routing table: every entry spells Controller@method, which is the
    # shape audit_route_coverage measures against the controllers below, and
    # routes/ beside app/ is what reads as `service` rather than `library`.
    _write(root, "routes/api.php",
           "<?php\n"
           "\n"
           "$router->get('/orders', ['uses' => 'OrdersController@index']);\n"
           "$router->get('/orders/{id}', ['uses' => 'OrdersController@show']);\n"
           "$router->get('/home', ['uses' => 'HomeController@index']);\n")
    _write(root, "app/Http/Controllers/HomeController.php",
           "<?php\n"
           "\n"
           "namespace App\\Http\\Controllers;\n"
           "\n"
           "class HomeController\n"
           "{\n"
           "    public function index()\n"
           "    {\n"
           "        return ['service' => 'example'];\n"
           "    }\n"
           "}\n")
    _write(root, "app/Http/Controllers/OrdersController.php",
           "<?php\n"
           "\n"
           "namespace App\\Http\\Controllers;\n"
           "\n"
           "use App\\Domain\\Order;\n"
           "\n"
           "class OrdersController\n"
           "{\n"
           "    public function index()\n"
           "    {\n"
           "        return [];\n"
           "    }\n"
           "\n"
           "    public function show()\n"
           "    {\n"
           "        return new Order('1');\n"
           "    }\n"
           "}\n")
    # The domain the controller reads: routes plus a request/response contract
    # plus something they act on is what `service` means in roles.json ("a
    # deployed data or API service — routes, request/response contracts").
    # The `use App\Domain\Order` edge also gives composer.json's psr-4 mapping
    # something real to describe.
    _write(root, "app/Domain/Order.php",
           "<?php\n"
           "\n"
           "namespace App\\Domain;\n"
           "\n"
           "class Order\n"
           "{\n"
           "    public function __construct(public string $id)\n"
           "    {\n"
           "    }\n"
           "}\n")


def _design_system_sources(root: Path) -> None:
    # A package consumed by other repositories: a public parsing surface,
    # pointedly NO routes and no controllers. An archetype detector that
    # guesses `service` from the presence of source code alone should be wrong
    # here.
    #
    # PHP, and the same language as `_app_sources`, because the two fixtures
    # are siblings — a package and the API service beside it — which is the
    # pair templates/docs/roles.json says its two archetypes were measured on:
    # "a PHP parser package and its REST API sibling".
    _write(root, "README.md",
           "# Example Query Support\n\nA query-parsing package consumed by other "
           "repositories. It has no routes, no controllers and no users of its own.\n")
    _write(root, DS_MANIFEST,
           "{\n"
           '  "name": "example/query-support",\n'
           '  "description": "A query-parsing package consumed by other repositories.",\n'
           '  "require": {\n'
           '    "php": "^8.1"\n'
           "  },\n"
           '  "autoload": {\n'
           '    "psr-4": {\n'
           '      "Example\\\\QuerySupport\\\\": "src/"\n'
           "    }\n"
           "  }\n"
           "}\n")
    _write(root, "src/QueryParser.php",
           "<?php\n"
           "\n"
           "namespace Example\\QuerySupport;\n"
           "\n"
           "class QueryParser\n"
           "{\n"
           "    public function parse(string $query): Segment\n"
           "    {\n"
           "        return new Segment($query);\n"
           "    }\n"
           "}\n")
    _write(root, "src/Segment.php",
           "<?php\n"
           "\n"
           "namespace Example\\QuerySupport;\n"
           "\n"
           "class Segment\n"
           "{\n"
           "    public function __construct(public string $raw)\n"
           "    {\n"
           "    }\n"
           "}\n")
    _write(root, "tests/QueryParserTest.php",
           "<?php\n"
           "\n"
           "use Example\\QuerySupport\\QueryParser;\n"
           "\n"
           "class QueryParserTest\n"
           "{\n"
           "    public function testParsesToASegment()\n"
           "    {\n"
           "        $segment = (new QueryParser())->parse('a=b');\n"
           "        assert($segment->raw === 'a=b');\n"
           "    }\n"
           "}\n")


AUTHORED_DOC = """# API

This document is deliberately *written*, not scaffolded — it carries no
`status: stub` frontmatter, so it resolves with exit 0 and counts as real
coverage. It exists so a case can tell an authored document apart from the
stub and the decline that sit beside it in this same fixture.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/orders` | List orders |
| GET | `/orders/{id}` | One order |

## Errors

Every failure answers `{status, type, message}`; no route invents a shape.
"""


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _strip_prose_keys(root: Path) -> None:
    """Drop `_readme` / `_comment` / `_example` keys from the scaffolded profile.

    Not cosmetic, and the one place this builder knowingly departs from raw
    `init.py` output. The template's `provenance._readme` explains the
    provenance vocabulary *in prose* — it contains the literal words
    `inferred`, `declared` and `approved` three and two times over — and its
    `_example` shows a full ratified entry. A grader written as `not_contains:
    approved` over the profile therefore fails on a fixture where nothing has
    been ratified at all, and a `count:1` grader on `pre-ratified` counts four.

    Stripping them keeps the fixture's profile *semantically* identical to what
    init.py writes (these keys are documentation for a human, read by nothing)
    while making the file say what it means.

    Worth stating plainly, because it is a real limitation and not a detail: a
    REAL adopter's profile does contain those words, so `not_contains:
    approved` over a whole profile is not a sound check in the field. The sound
    target is `provenance.fields`. The fixtures honour the whole-file form
    because the cases are written against it, and the self-test locks the
    property in so it cannot regress silently.
    """
    path = root / ".backend-suite/profile.json"

    def prune(node):
        if isinstance(node, dict):
            return {k: prune(v) for k, v in node.items()
                    if not (isinstance(k, str) and k.startswith("_"))}
        if isinstance(node, list):
            return [prune(v) for v in node]
        return node

    path.write_text(json.dumps(prune(json.loads(path.read_text())), indent=2) + "\n",
                    encoding="utf-8")


def _init(root: Path, name: str) -> None:
    _run([sys.executable, str(BIN / "init.py"), "--dir", str(root), "--name", name])
    _strip_prose_keys(root)


def _declare_kind(root: Path, kind: str) -> None:
    """Declare a projectKind. init.py deliberately does not — archetype is a
    human's call, not a scaffolder's — so the fixture makes it explicitly."""
    _edit_json(root / ".backend-suite/profile.json",
               lambda d: d["project"].__setitem__("projectKind", kind))


def build_zero_state(root: Path) -> None:
    """Source files and nothing else — no `.backend-suite/` at all.

    The onboarding path nothing has ever exercised. Every `bin/*.py` exits 2
    here via `project_root()`, and that is the correct behaviour, not a bug:
    the point of the fixture is that a case can assert the refusal rather than
    a skill inventing a project shape.
    """
    _app_sources(root)


def build_service(root: Path) -> None:
    """A scaffolded `service` with one authored doc, one real decline, one stub.

    Exercises exit 4 (declined) and exit 5 (stub) side by side with exit 0
    (authored), which is the only arrangement that proves a skill is reading
    the exit code rather than the file's existence.
    """
    _app_sources(root)
    _init(root, "Example Service")
    _declare_kind(root, "service")

    # Authored: a real document, no stub frontmatter.
    manifest = json.loads((root / ".backend-suite/docs.manifest.json").read_text())
    _write(root, manifest["roles"][AUTHORED_ROLE], AUTHORED_DOC)

    # Stub: written by the real scaffolder, so the `status: stub` frontmatter is
    # whatever scaffold_doc.py actually emits today, not a copy of it.
    _run([sys.executable, str(BIN / "scaffold_doc.py"), STUB_ROLE, "--dir", str(root)])

    # Declined: recorded by the real tool, with a reason. A decline with no
    # reason is the silence the state exists to prevent, so the fixture carries
    # a real sentence — and the self-test asserts it is still there.
    _run([sys.executable, str(BIN / "decline_doc.py"), DECLINED_ROLE,
          "--dir", str(root), "--reason", DECLINE_REASON,
          "--by", "fixture builder", "--on", "2026-01-01"])


def build_library(root: Path) -> None:
    """A package-shaped repo with NO `.backend-suite/`.

    Undeclared on purpose: the interesting question is whether a skill reads
    the shape or assumes `service`.
    """
    _design_system_sources(root)


def build_library_declared(root: Path) -> None:
    """The same repo with `projectKind: library` actually declared."""
    _design_system_sources(root)
    _init(root, "Example Library Package")
    _declare_kind(root, "library")


def build_undeclared_kind(root: Path) -> None:
    """The `service` fixture with `projectKind` removed.

    Both real consumer projects are in exactly this state today, which makes it
    the most important fixture here: it is not an edge case, it is the default.
    `archetypes.kind_of()` must raise `ArchetypeNotDeclared` — never guess.
    """
    build_service(root)
    _edit_json(root / ".backend-suite/profile.json",
               lambda d: d["project"].pop("projectKind", None))


def build_pre_ratified(root: Path) -> None:
    """The `service` fixture plus one field a human has ratified.

    `state: approved` with `by` / `on` / `verifiedAgainst` is the strongest
    claim the provenance model can carry. Nothing may downgrade it to
    `inferred` or overwrite its value — init.py is already built so it cannot
    (SEEDED_STATE), and a case's job is to prove a *skill* cannot either.
    """
    build_service(root)

    def mutate(profile: dict) -> None:
        fields = profile.setdefault("provenance", {}).setdefault("fields", {})
        fields.pop("_example", None)
        fields[RATIFIED_FIELD] = {
            "state": "approved",
            "by": "a human who reviewed it",
            "on": "2026-01-01",
            "value": "app",
            "evidence": "composer.json maps App\\ to app/ and the controllers live there",
            "verifiedAgainst": {"commit": "0" * 40},
        }
        # The ratified value must agree with the profile itself, or doctor would
        # report it contradicted and the fixture would be testing the wrong state.
        profile["source"]["root"] = "app"

    _edit_json(root / ".backend-suite/profile.json", mutate)


FIXTURES = {
    "zero-state": build_zero_state,
    "service": build_service,
    "library": build_library,
    "library-declared": build_library_declared,
    "undeclared-kind": build_undeclared_kind,
    "pre-ratified": build_pre_ratified,
}


def build(name: str, root: Path, force: bool = False) -> Path:
    if name not in FIXTURES:
        raise SystemExit(f"unknown fixture {name!r}. Known: {', '.join(sorted(FIXTURES))}")
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        if not force:
            raise SystemExit(f"{root} is not empty — pass --force to rebuild it. "
                             f"Refusing to build a fixture on top of unknown files, "
                             f"because the result would be neither state.")
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    FIXTURES[name](root)
    return root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture", nargs="?", help="which fixture to build")
    ap.add_argument("--dir", help="where to build it (created if absent)")
    ap.add_argument("--force", action="store_true", help="rebuild over a non-empty directory")
    ap.add_argument("--list", action="store_true", help="list fixtures and what each is for")
    args = ap.parse_args()

    if args.list:
        for name, fn in FIXTURES.items():
            first = (fn.__doc__ or "").strip().splitlines()[0]
            print(f"{name:26} {first}")
        return 0

    if not args.fixture or not args.dir:
        ap.print_usage(sys.stderr)
        print("\nboth a fixture name and --dir are required (or --list)", file=sys.stderr)
        return 2

    print(build(args.fixture, Path(args.dir), args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
