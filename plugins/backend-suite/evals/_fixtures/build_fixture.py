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

# Node.js fixtures
NODE_APP_MANIFEST = "package.json"
NODE_DS_MANIFEST = "package.json"


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


def _symfony_sources(root: Path) -> None:
    """A Symfony application with routes, controllers, services, forms, entities, voters, and Twig."""
    _write(root, "README.md", "# Example Symfony App\n\nA small Symfony HTTP API.\n")
    _write(root, "composer.json",
           "{\n"
           '  "name": "example/symfony-app",\n'
           '  "description": "A small Symfony HTTP API.",\n'
           '  "require": {\n'
           '    "php": "^8.1",\n'
           '    "symfony/framework-bundle": "^6.4",\n'
           '    "symfony/orm-pack": "^2.0",\n'
           '    "symfony/form": "^6.4",\n'
           '    "symfony/security-bundle": "^6.4",\n'
           '    "symfony/twig-bundle": "^6.4"\n'
           "  },\n"
           '  "autoload": {\n'
           '    "psr-4": {\n'
           '      "App\\\\": "src/"\n'
           "    }\n"
           "  }\n"
           "}\n")
    # Routing config
    _write(root, "config/routes.yaml",
           "index:\n"
           "    path: /\n"
           "    controller: App\\Controller\\DefaultController::index\n"
           "orders:\n"
           "    path: /orders\n"
           "    controller: App\\Controller\\OrderController::index\n")
    _write(root, "config/services.yaml",
           "services:\n"
           "    _defaults:\n"
           "        autowire: true\n"
           "        autoconfigure: true\n")
    _write(root, "config/security.yaml",
           "security:\n"
           "    firewalls:\n"
           "        main:\n"
           "            lazy: true\n"
           "    access_control: []\n")
    # Kernel
    _write(root, "src/Kernel.php",
           "<?php\n"
           "\n"
           "namespace App;\n"
           "\n"
           "use Symfony\\Component\\HttpKernel\\Kernel;\n"
           "\n"
           "class Kernel extends Kernel\n"
           "{\n"
           "}\n")
    # Controller with #[Route] attribute
    _write(root, "src/Controller/DefaultController.php",
           "<?php\n"
           "\n"
           "namespace App\\Controller;\n"
           "\n"
           "use Symfony\\Component\\Routing\\Annotation\\Route;\n"
           "\n"
           "class DefaultController\n"
           "{\n"
           "    #[Route('/', name: 'index')]\n"
           "    public function index()\n"
           "    {\n"
           "        return ['service' => 'symfony'];\n"
           "    }\n"
           "}\n")
    _write(root, "src/Controller/OrderController.php",
           "<?php\n"
           "\n"
           "namespace App\\Controller;\n"
           "\n"
           "use App\\Entity\\Order;\n"
           "use Symfony\\Component\\Routing\\Annotation\\Route;\n"
           "\n"
           "class OrderController\n"
           "{\n"
           "    #[Route('/orders', name: 'orders', methods: ['GET'])]\n"
           "    public function index()\n"
           "    {\n"
           "        return [];\n"
           "    }\n"
           "}\n")
    # Service with #[AsService]
    _write(root, "src/Service/OrderService.php",
           "<?php\n"
           "\n"
           "namespace App\\Service;\n"
           "\n"
           "use Symfony\\Component\\DependencyInjection\\Attribute\\AsService;\n"
           "\n"
           "#[AsService]\n"
           "class OrderService\n"
           "{\n"
           "    public function getOrders(): array\n"
           "    {\n"
           "        return [];\n"
           "    }\n"
           "}\n")
    # Form Type
    _write(root, "src/Form/OrderType.php",
           "<?php\n"
           "\n"
           "namespace App\\Form;\n"
           "\n"
           "use Symfony\\Component\\Form\\AbstractType;\n"
           "use Symfony\\Component\\Form\\FormBuilderInterface;\n"
           "use Symfony\\Component\\OptionsResolver\\OptionsResolver;\n"
           "\n"
           "class OrderType extends AbstractType\n"
           "{\n"
           "    public function buildForm(FormBuilderInterface \$builder, array \$options): void\n"
           "    {\n"
           "        \$builder->add('name');\n"
           "    }\n"
           "\n"
           "    public function configureOptions(OptionsResolver \$resolver): void\n"
           "    {\n"
           "        \$resolver->setDefaults(['data_class' => 'App\\Entity\\Order']);\n"
           "    }\n"
           "}\n")
    # Doctrine Entity
    _write(root, "src/Entity/Order.php",
           "<?php\n"
           "\n"
           "namespace App\\Entity;\n"
           "\n"
           "use Doctrine\\ORM\\Mapping as ORM;\n"
           "\n"
           "#[ORM\\Entity]\n"
           "#[ORM\\Table(name: 'orders')]\n"
           "class Order\n"
           "{\n"
           "    #[ORM\\Id]\n"
           "    #[ORM\\GeneratedValue]\n"
           "    #[ORM\\Column]\n"
           "    private ?int \$id = null;\n"
           "\n"
           "    #[ORM\\Column(length: 255)]\n"
           "    private string \$name;\n"
           "\n"
           "    public function getId(): ?int { return \$this->id; }\n"
           "    public function getName(): string { return \$this->name; }\n"
           "    public function setName(string \$name): self { \$this->name = \$name; return \$this; }\n"
           "}\n")
    # Doctrine Repository
    _write(root, "src/Repository/OrderRepository.php",
           "<?php\n"
           "\n"
           "namespace App\\Repository;\n"
           "\n"
           "use App\\Entity\\Order;\n"
           "use Doctrine\\Bundle\\DoctrineBundle\\Repository\\ServiceEntityRepository;\n"
           "use Doctrine\\Persistence\\ManagerRegistry;\n"
           "\n"
           "class OrderRepository extends ServiceEntityRepository\n"
           "{\n"
           "    public function __construct(ManagerRegistry \$registry)\n"
           "    {\n"
           "        parent::__construct(\$registry, Order::class);\n"
           "    }\n"
           "}\n")
    # Security Voter
    _write(root, "src/Security/OrderVoter.php",
           "<?php\n"
           "\n"
           "namespace App\\Security;\n"
           "\n"
           "use Symfony\\Component\\Security\\Core\\Authorization\\Voter\\Voter;\n"
           "use Symfony\\Component\\Security\\Core\\Authentication\\Token\\TokenInterface;\n"
           "\n"
           "class OrderVoter extends Voter\n"
           "{\n"
           "    protected function voteOnAttribute(string \$attribute, \$subject, TokenInterface \$token): bool\n"
           "    {\n"
           "        return true;\n"
           "    }\n"
           "}\n")
    # Twig Extension
    _write(root, "src/Twig/AppExtension.php",
           "<?php\n"
           "\n"
           "namespace App\\Twig;\n"
           "\n"
           "use Twig\\Extension\\AbstractExtension;\n"
           "use Twig\\TwigFunction;\n"
           "\n"
           "class AppExtension extends AbstractExtension\n"
           "{\n"
           "    public function getFunctions(): array\n"
           "    {\n"
           "        return [new TwigFunction('my_function', fn() => 'hello')];\n"
           "    }\n"
           "}\n")
    # Template
    _write(root, "templates/base.html.twig",
           "{% block body %}{% endblock %}\n")


# --------------------------------------------------------------------------- #
# Node.js source shapes
# --------------------------------------------------------------------------- #

def _express_sources(root: Path) -> None:
    """An Express application with routes, controllers, and a domain."""
    _write(root, "README.md", "# Example Express Service\n\nA small HTTP API: routes, controllers and a domain.\n")
    _write(root, NODE_APP_MANIFEST,
            '{\n'
            '  "name": "example/express-service",\n'
            '  "description": "A small HTTP API: routes, controllers and a domain.",\n'
            '  "dependencies": {\n'
            '    "express": "^4.18.0",\n'
            '    "zod": "^3.22.0"\n'
            "  },\n"
            '  "devDependencies": {\n'
            '    "@types/express": "^4.17.0",\n'
            '    "typescript": "^5.0.0"\n'
            "  }\n"
            '}\n')
    # Routing: Express app with routes
    _write(root, "src/app.ts",
            "import express from 'express';\n"
            "import { OrderController } from './controllers/OrderController';\n"
            "import { HealthController } from './controllers/HealthController';\n"
            "import { z } from 'zod';\n"
            "\n"
            "const app = express();\n"
            "app.use(express.json());\n"
            "\n"
            "app.get('/health', (req, res) => new HealthController().index(req, res));\n"
            "app.get('/orders', (req, res) => new OrderController().index(req, res));\n"
            "app.get('/orders/:id', (req, res) => new OrderController().show(req, res));\n"
            "\n"
            "export default app;\n")
    _write(root, "src/controllers/HealthController.ts",
            "import { Request, Response } from 'express';\n"
            "\n"
            "export class HealthController\n"
            "{\n"
            "    index(req: Request, res: Response): void\n"
            "    {\n"
            "        res.json({ service: 'express' });\n"
            "    }\n"
            "}\n")
    _write(root, "src/controllers/OrderController.ts",
            "import { Request, Response } from 'express';\n"
            "import { Order } from '../domain/Order';\n"
            "import { z } from 'zod';\n"
            "\n"
            "export class OrderController\n"
            "{\n"
            "    index(req: Request, res: Response): void\n"
            "    {\n"
            "        res.json([]);\n"
            "    }\n"
            "\n"
            "    show(req: Request, res: Response): void\n"
            "    {\n"
            "        res.json(new Order(req.params.id));\n"
            "    }\n"
            "}\n")
    _write(root, "src/domain/Order.ts",
            "export class Order\n"
            "{\n"
            "    constructor(public readonly id: string)\n"
            "    {\n"
            "    }\n"
            "}\n")


def _nestjs_sources(root: Path) -> None:
    """A NestJS application with controllers, services, modules, guards, and DTOs."""
    _write(root, "README.md", "# Example NestJS App\n\nA small NestJS HTTP API.\n")
    _write(root, NODE_APP_MANIFEST,
            '{\n'
            '  "name": "example/nestjs-app",\n'
            '  "description": "A small NestJS HTTP API.",\n'
            '  "dependencies": {\n'
            '    "@nestjs/common": "^10.0.0",\n'
            '    "@nestjs/core": "^10.0.0",\n'
            '    "@nestjs/platform-express": "^10.0.0",\n'
            '    "reflect-metadata": "^0.2.0",\n'
            '    "rxjs": "^7.8.0",\n'
            '    "zod": "^3.22.0",\n'
            '    "@nestjs/swagger": "^7.0.0",\n'
            '    "@nestjs/passport": "^10.0.0",\n'
            '    "passport": "^0.7.0",\n'
            '    "passport-jwt": "^4.0.0",\n'
            '    "class-validator": "^0.14.0",\n'
            '    "class-transformer": "^0.5.0"\n'
            "  },\n"
            '  "devDependencies": {\n'
            '    "@nestjs/cli": "^10.0.0",\n'
            '    "typescript": "^5.0.0"\n'
            "  }\n"
            '}\n')
    # nest-cli.json
    _write(root, "nest-cli.json",
            '{\n'
            '  "$schema": "https://json.schemastore.org/nest-cli",\n'
            '  "collection": "@nestjs/schematics",\n'
            '  "sourceRoot": "src",\n'
            '  "compilerOptions": {\n'
            '    "deleteOutDir": true\n'
            "  }\n"
            '}\n')
    # Main entry
    _write(root, "src/main.ts",
            "import { NestFactory } from '@nestjs/core';\n"
            "import { AppModule } from './app.module';\n"
            "\n"
            "async function bootstrap() {\n"
            "    const app = await NestFactory.create(AppModule);\n"
            "    await app.listen(3000);\n"
            "}\n"
            "bootstrap();\n")
    # App Module
    _write(root, "src/app.module.ts",
            "import { Module } from '@nestjs/common';\n"
            "import { OrdersModule } from './orders/orders.module';\n"
            "\n"
            "@Module({\n"
            "    imports: [OrdersModule],\n"
            "})\n"
            "export class AppModule {}\n")
    # Orders Module
    _write(root, "src/orders/orders.module.ts",
            "import { Module } from '@nestjs/common';\n"
            "import { OrdersController } from './orders.controller';\n"
            "import { OrdersService } from './orders.service';\n"
            "\n"
            "@Module({\n"
            "    controllers: [OrdersController],\n"
            "    providers: [OrdersService],\n"
            "})\n"
            "export class OrdersModule {}\n")
    # Controller
    _write(root, "src/orders/orders.controller.ts",
            "import { Controller, Get, Param, UseGuards, Inject } from '@nestjs/common';\n"
            "import { OrdersService } from './orders.service';\n"
            "import { Order } from './orders.entity';\n"
            "import { JwtAuthGuard } from '../auth/jwt-auth.guard';\n"
            "import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';\n"
            "\n"
            "@ApiTags('orders')\n"
            "@Controller('orders')\n"
            "export class OrdersController\n"
            "{\n"
            "    constructor(private readonly service: OrdersService) {}\n"
            "\n"
            "    @Get()\n"
            "    @UseGuards(JwtAuthGuard)\n"
            "    @ApiOperation({ summary: 'List all orders' })\n"
            "    @ApiResponse({ status: 200, description: 'List of orders', type: [Order] })\n"
            "    index(): Order[]\n"
            "    {\n"
            "        return this.service.findAll();\n"
            "    }\n"
            "\n"
            "    @Get(':id')\n"
            "    @UseGuards(JwtAuthGuard)\n"
            "    show(@Param('id') id: string): Order\n"
            "    {\n"
            "        return this.service.findOne(id);\n"
            "    }\n"
            "}\n")
    # Service
    _write(root, "src/orders/orders.service.ts",
            "import { Injectable, Inject } from '@nestjs/common';\n"
            "import { Order } from './orders.entity';\n"
            "\n"
            "@Injectable()\n"
            "export class OrdersService\n"
            "{\n"
            "    private readonly cache = new Map<string, Order>();\n"
            "\n"
            "    findAll(): Order[]\n"
            "    {\n"
            "        return [];\n"
            "    }\n"
            "\n"
            "    findOne(id: string): Order\n"
            "    {\n"
            "        return new Order(id);\n"
            "    }\n"
            "}\n")
    # Entity
    _write(root, "src/orders/orders.entity.ts",
            "import { ApiProperty } from '@nestjs/swagger';\n"
            "import { IsString, IsNotEmpty } from 'class-validator';\n"
            "import { z } from 'zod';\n"
            "\n"
            "export const orderSchema = z.object({\n"
            "    id: z.string(),\n"
            "});\n"
            "\n"
            "export class Order\n"
            "{\n"
            "    @ApiProperty()\n"
            "    @IsString()\n"
            "    @IsNotEmpty()\n"
            "    id: string;\n"
            "\n"
            "    constructor(id: string)\n"
            "    {\n"
            "        this.id = id;\n"
            "    }\n"
            "}\n")
    # Auth Guard
    _write(root, "src/auth/jwt-auth.guard.ts",
            "import { Injectable, CanActivate, ExecutionContext } from '@nestjs/common';\n"
            "import { Observable } from 'rxjs';\n"
            "\n"
            "@Injectable()\n"
            "export class JwtAuthGuard implements CanActivate\n"
            "{\n"
            "    canActivate(\n"
            "        context: ExecutionContext,\n"
            "    ): boolean | Promise<boolean> | Observable<boolean>\n"
            "    {\n"
            "        return true;\n"
            "    }\n"
            "}\n")


def _build_express(root: Path) -> None:
    """An Express application fixture with routing, models, validation, middleware."""
    _express_sources(root)


def _build_nestjs(root: Path) -> None:
    """A NestJS application fixture with routing, DI, validation, guards, OpenAPI."""
    _nestjs_sources(root)


def build_symfony(root: Path) -> None:
    """A Symfony application fixture with all capabilities."""
    _symfony_sources(root)


FIXTURES = {
    "zero-state": build_zero_state,
    "service": build_service,
    "library": build_library,
    "library-declared": build_library_declared,
    "undeclared-kind": build_undeclared_kind,
    "pre-ratified": build_pre_ratified,
    "symfony": build_symfony,
    "express": _build_express,
    "nestjs": _build_nestjs,
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
