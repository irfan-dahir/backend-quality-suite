#!/usr/bin/env python3
"""Build one eval fixture — a throwaway consumer project in a known state.

    python3 plugins/design-suite/evals/_fixtures/build_fixture.py app --dir /tmp/x
    python3 .../build_fixture.py --list

This is the `context.scaffold_script` end of an eval case: a case names a
fixture, the harness runs this to materialise it, and the case then asserts what
a skill does when pointed at it.

## Why a script and not committed files

A fixture is only useful if it is what `init.py` *actually* produces. A
committed tree of `.design-suite/` files is a photograph of what init.py
produced on the day someone ran it, and it goes stale silently — the fixture
keeps passing, the tool it stands in for has moved, and every case built on it
is now measuring a project shape no real adopter has. That is this repo's
governing failure (a check whose silence reads as a pass) relocated into the
test harness.

So every `.design-suite/` file here comes from running the real tools:

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

# The role the `app` fixture authors for real, declines, and stubs. Named once
# here and imported by the self-test so the two cannot drift into asserting a
# state the builder stopped producing.
AUTHORED_ROLE = "design"
STUB_ROLE = "flows"
DECLINED_ROLE = "motion"
DECLINE_REASON = ("this fixture's project has no motion of its own; it inherits "
                  "the design system's, and re-documenting it would create a "
                  "second copy to drift")

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
# in bin/ a path like `lib/screens/…` is an assumption about a CONSUMER's
# layout, which is the thing the universal plugin may never make. Here it is
# not an assumption at all: it is this builder's own output, three functions up.
#
# Widget name -> the screen file it is declared in. The /promote-component
# cases invoke these by name.
PROMOTION_SUBJECTS = {
    "_StatCell": "lib/screens/home_screen.dart",
    "_MetricTile": "lib/screens/settings_screen.dart",
    "_OrderSummaryRow": "lib/screens/orders_screen.dart",
}

# The constructor parameter set `_StatCell` and `_MetricTile` share. The shape
# match in audit_promotion_candidates.py is over parameter NAMES, so this being
# identical across the two is what makes the duplication detectable at all.
SHARED_WIDGET_PARAMS = ("label", "value", "icon", "onTap")

# The product layer `_OrderSummaryRow` is coupled to, and the type names that
# must NOT appear anywhere near `_StatCell`.
DOMAIN_SOURCES = ("lib/models/order.dart", "lib/services/pricing_rules.dart")
DOMAIN_TYPES = ("Order", "Money", "PricingRules", "OrderStatus")

# Package manifests, the design system's component directory, and the package
# name the app resolves it under.
APP_MANIFEST = "pubspec.yaml"
DS_MANIFEST = "pubspec.yaml"
DS_COMPONENT_GLOB = "lib/src/components/*.dart"
DS_PACKAGE = "example_design_system"
DS_GATE_GLOBS = {
    "a unit test": "test/**/*_test.dart",
    "a gallery use case": "gallery/*.dart",
    "a docs entry": "doc/**/*.md",
}


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
    _write(root, "README.md", "# Example App\n\nA small product with screens and routes.\n")
    # The path dependency on ../design-system is what makes the two fixtures a
    # PAIR rather than two unrelated trees. `/promote-component`'s Step 4 is
    # "bump the design-system package refs in the project's manifest", and a
    # manifest with no such ref gives that step nothing to edit. When the app
    # fixture is built alone the path dangles, which is harmless: nothing in
    # this suite runs `pub get`.
    _write(root, "pubspec.yaml",
           "name: example_app\n"
           "environment:\n  sdk: '>=3.0.0 <4.0.0'\n"
           "dependencies:\n"
           "  flutter:\n    sdk: flutter\n"
           "  example_design_system:\n    path: ../design-system\n")
    _write(root, "lib/main.dart",
           "void main() => runApp(const ExampleApp());\n")
    # The three screens. Each carries, at the bottom of its own file, the
    # PRIVATE widget the /promote-component cases are pointed at.
    #
    # Private and screen-local rather than public under lib/widgets/, because
    # that is the shape the tooling and the command both actually model: the
    # detector in audit_promotion_candidates.py matches
    # `class _Name extends StatelessWidget`, and Step 4 of the command
    # ("delete the private widget, import the real one") describes exactly this
    # arrangement. A public widget in its own file is already half-promoted and
    # would make Step 4 vacuous.
    _write(root, "lib/screens/home_screen.dart",
           "// A screen with the three standard states, so a reader can tell this is an app.\n"
           "import '../theme/app_theme.dart';\n"
           "\n"
           "class HomeScreen {\n"
           "  Widget build() => Column(children: [\n"
           "        Loading(),\n"
           "        ErrorView(),\n"
           "        Content(),\n"
           "        const _StatCell(label: 'Orders', value: '128', icon: Icons.receipt),\n"
           "      ]);\n"
           "}\n"
           "\n"
           "// THE PROMOTION CANDIDATE. Generic by construction: a label, a value,\n"
           "// an icon and a tap. No project type appears in its signature or its\n"
           "// body, which is what makes it promotable — it would survive being\n"
           "// renamed to anything at all.\n"
           "class _StatCell extends StatelessWidget {\n"
           "  const _StatCell({\n"
           "    required this.label,\n"
           "    required this.value,\n"
           "    required this.icon,\n"
           "    this.onTap,\n"
           "  });\n"
           "\n"
           "  final String label;\n"
           "  final String value;\n"
           "  final IconData icon;\n"
           "  final VoidCallback? onTap;\n"
           "\n"
           "  @override\n"
           "  Widget build(BuildContext context) => InkWell(\n"
           "        onTap: onTap,\n"
           "        child: Padding(\n"
           "          padding: AppTheme.spacing.md,\n"
           "          child: Row(children: [\n"
           "            Icon(icon),\n"
           "            Column(children: [Text(value), Text(label)]),\n"
           "          ]),\n"
           "        ),\n"
           "      );\n"
           "}\n")
    _write(root, "lib/screens/settings_screen.dart",
           "import '../theme/app_theme.dart';\n"
           "\n"
           "class SettingsScreen {\n"
           "  Widget build() => Column(children: [\n"
           "        const Placeholder(),\n"
           "        const _MetricTile(label: 'Storage used', value: '4.2 GB',\n"
           "            icon: Icons.storage),\n"
           "      ]);\n"
           "}\n"
           "\n"
           "// THE SAME WIDGET, BUILT AGAIN UNDER A DIFFERENT NOUN. Identical\n"
           "// constructor parameter set to _StatCell, different class name and a\n"
           "// separately written body — which is what makes StatCell a real\n"
           "// promotion candidate rather than one screen's private helper.\n"
           "// audit_promotion_candidates.py matches on the parameter set, not on\n"
           "// the name, so Step 0 has a true duplication to report; without this\n"
           "// the command's own first step comes back empty and /promote-component\n"
           "// StatCell argues from nothing.\n"
           "class _MetricTile extends StatelessWidget {\n"
           "  const _MetricTile({\n"
           "    required this.label,\n"
           "    required this.value,\n"
           "    required this.icon,\n"
           "    this.onTap,\n"
           "  });\n"
           "\n"
           "  final String label;\n"
           "  final String value;\n"
           "  final IconData icon;\n"
           "  final VoidCallback? onTap;\n"
           "\n"
           "  @override\n"
           "  Widget build(BuildContext context) => GestureDetector(\n"
           "        onTap: onTap,\n"
           "        child: Container(\n"
           "          padding: AppTheme.spacing.md,\n"
           "          child: Column(children: [\n"
           "            Icon(icon),\n"
           "            Text(value),\n"
           "            Text(label),\n"
           "          ]),\n"
           "        ),\n"
           "      );\n"
           "}\n")
    _write(root, "lib/screens/orders_screen.dart",
           "import '../models/order.dart';\n"
           "import '../services/pricing_rules.dart';\n"
           "import '../theme/app_theme.dart';\n"
           "\n"
           "class OrdersScreen {\n"
           "  Widget build() => Column(\n"
           "        children: orders\n"
           "            .map((o) => _OrderSummaryRow(order: o, onReorder: reorder))\n"
           "            .toList(),\n"
           "      );\n"
           "}\n"
           "\n"
           "// STAYS IN THE APP, and fails the command's Step 1 bar structurally\n"
           "// rather than by its name. Its constructor takes a domain entity\n"
           "// (`Order`) and its body applies product rules to that entity, so\n"
           "// promoting it would drag Order, Money, OrderStatus and PricingRules\n"
           "// into the design system with it. A widget merely CALLED\n"
           "// OrderSummaryRow, taking two strings, would let the refusal case pass\n"
           "// on the noun in the filename and measure nothing.\n"
           "class _OrderSummaryRow extends StatelessWidget {\n"
           "  const _OrderSummaryRow({\n"
           "    required this.order,\n"
           "    required this.onReorder,\n"
           "  });\n"
           "\n"
           "  final Order order;\n"
           "  final void Function(Order order) onReorder;\n"
           "\n"
           "  @override\n"
           "  Widget build(BuildContext context) => Padding(\n"
           "        padding: AppTheme.spacing.md,\n"
           "        child: Row(children: [\n"
           "          Text('Order ${order.id}'),\n"
           "          Text('${order.itemCount} items'),\n"
           "          if (PricingRules.showsTaxBreakdown(order)) const Text('incl. tax'),\n"
           "          Text(PricingRules.formatTotal(order)),\n"
           "          if (PricingRules.isReorderable(order))\n"
           "            TextButton(\n"
           "              onPressed: () => onReorder(order),\n"
           "              child: const Text('Reorder'),\n"
           "            ),\n"
           "        ]),\n"
           "      );\n"
           "}\n")
    _write(root, "lib/theme/app_theme.dart",
           "// A hardcoded colour, so a token audit pointed here has something to find.\n"
           "const primary = Color(0xFF2266EE);\n")
    _app_domain_sources(root)


# --------------------------------------------------------------------------- #
# The two widgets the `/promote-component` cases name, and the domain layer one
# of them is coupled to.
#
# These exist because the four promote-component cases invoke
# `/promote-component StatCell` and `/promote-component OrderSummaryRow`
# against this fixture, and neither name appeared anywhere in it. Every one of
# those cases was therefore pointed at a component that did not exist — the
# command could only ever report "no such widget", and each case's negative
# graders (`no-write`, `nothing-lands-in-design-system`) would have scored a
# clean 1.0 off that refusal while measuring nothing about promotion judgement.
#
# They are shaped so the DISTINCTION the cases turn on is structural rather
# than nominal: StatCell would survive being renamed to anything, and
# OrderSummaryRow would not.
# --------------------------------------------------------------------------- #

def _app_domain_sources(root: Path) -> None:
    """The product-layer types `OrderSummaryRow` is built on.

    A widget is refusable because of what it is COUPLED to, not because of what
    it is called. Naming a widget `OrderSummaryRow` and giving it two strings
    would let the refusal case pass on the noun in the filename, which is a
    fixture that makes a case pass by accident. So the entity is real, it
    carries business state, and there is a rules module that decides things
    about it.
    """
    _write(root, "lib/models/money.dart",
           "/// A value object, not a primitive: the widget cannot render one\n"
           "/// without knowing this project's currency conventions.\n"
           "class Money {\n"
           "  const Money(this.minorUnits, this.currency);\n"
           "  final int minorUnits;\n"
           "  final String currency;\n"
           "}\n")
    _write(root, "lib/models/order.dart",
           "import 'money.dart';\n"
           "\n"
           "enum OrderStatus { pending, paid, shipped, delivered, cancelled, refunded }\n"
           "\n"
           "/// A domain entity. It has an identity, a lifecycle and money on it.\n"
           "class Order {\n"
           "  const Order({\n"
           "    required this.id,\n"
           "    required this.status,\n"
           "    required this.itemCount,\n"
           "    required this.subtotal,\n"
           "    required this.tax,\n"
           "    required this.total,\n"
           "    required this.placedAt,\n"
           "  });\n"
           "  final String id;\n"
           "  final OrderStatus status;\n"
           "  final int itemCount;\n"
           "  final Money subtotal;\n"
           "  final Money tax;\n"
           "  final Money total;\n"
           "  final DateTime placedAt;\n"
           "}\n")
    _write(root, "lib/services/pricing_rules.dart",
           "import '../models/order.dart';\n"
           "\n"
           "/// Product rules, not presentation. A design system that imported this\n"
           "/// would be importing the business.\n"
           "class PricingRules {\n"
           "  static bool isReorderable(Order order) =>\n"
           "      order.status == OrderStatus.delivered ||\n"
           "      order.status == OrderStatus.cancelled;\n"
           "\n"
           "  static bool showsTaxBreakdown(Order order) => order.tax.minorUnits > 0;\n"
           "\n"
           "  static String formatTotal(Order order) =>\n"
           "      '${order.total.currency} ${(order.total.minorUnits / 100).toStringAsFixed(2)}';\n"
           "}\n")


def _design_system_sources(root: Path) -> None:
    # A package consumed by other repositories: components + tokens + theming,
    # and pointedly NO screens or routes. An archetype detector that guesses
    # `app` from the presence of source code alone should be wrong here.
    #
    # DART, NOT TYPESCRIPT — and this is load-bearing rather than a preference.
    # This fixture is the promotion TARGET for `_fixtures/app`, which is a
    # Flutter app. Promoting a Dart widget into a TypeScript package is not a
    # thing `/promote-component` could do correctly, so the pair has to share a
    # language, and the graders settle which one: they assert
    # `design-system/**/*stat_cell*` and `design-system/**/*stat_cell*test*` —
    # snake_case, which is Dart's file convention and not TSX's. Making the app
    # TypeScript instead would strand those two graders AND rewrite the fixture
    # that eleven other cases depend on, including the planted-violation
    # control that grades on `app_theme.dart` by name. Both `dart` and `tsx`
    # adapters ship, so neither language is unsupported; this one is the one
    # the assertions are written in.
    _write(root, "README.md",
           "# Example Design System\n\nA component and token package consumed by other "
           "repositories. It has no screens, no routes and no users of its own.\n")
    _write(root, "pubspec.yaml",
           "name: example_design_system\n"
           "description: Components, tokens and theming consumed by other repositories.\n"
           "version: 0.4.0\n"
           "environment:\n  sdk: '>=3.0.0 <4.0.0'\n"
           "dependencies:\n  flutter:\n    sdk: flutter\n"
           "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n")
    # The barrel. Step 4 of /promote-component exports the promoted component
    # from here, so there has to be a here.
    _write(root, "lib/example_design_system.dart",
           "export 'src/components/ds_button.dart';\n"
           "export 'src/components/ds_card.dart';\n"
           "export 'src/tokens/tokens.dart';\n"
           "export 'src/theme/ds_theme.dart';\n")
    _write(root, "lib/src/components/ds_button.dart",
           "import '../tokens/tokens.dart';\n"
           "\n"
           "class DsButton extends StatelessWidget {\n"
           "  const DsButton({super.key, required this.label, this.onPressed});\n"
           "  final String label;\n"
           "  final VoidCallback? onPressed;\n"
           "\n"
           "  @override\n"
           "  Widget build(BuildContext context) => TextButton(\n"
           "        onPressed: onPressed,\n"
           "        child: Padding(padding: DsTokens.space.md, child: Text(label)),\n"
           "      );\n"
           "}\n")
    _write(root, "lib/src/components/ds_card.dart",
           "import '../tokens/tokens.dart';\n"
           "\n"
           "class DsCard extends StatelessWidget {\n"
           "  const DsCard({super.key, required this.child});\n"
           "  final Widget child;\n"
           "\n"
           "  @override\n"
           "  Widget build(BuildContext context) => Container(\n"
           "        padding: DsTokens.space.md,\n"
           "        decoration: BoxDecoration(borderRadius: DsTokens.radius.md),\n"
           "        child: child,\n"
           "      );\n"
           "}\n")
    _write(root, "lib/src/tokens/tokens.dart",
           "class DsTokens {\n"
           "  static const space = (sm: 4.0, md: 8.0, lg: 16.0);\n"
           "  static const radius = (sm: 2.0, md: 6.0);\n"
           "}\n")
    _write(root, "lib/src/theme/ds_theme.dart",
           "import '../tokens/tokens.dart';\n"
           "\n"
           "class DsTheme {\n"
           "  static const surface = DsTokens.space;\n"
           "}\n")
    # The three DS-side contribution gates /promote-component Step 3 names —
    # unit test, gallery use case, docs entry — each shown ONCE, on an existing
    # component. A command told "the DS repo requires a test, a gallery entry
    # and a doc" can only comply if the repo it is handed shows where those go;
    # `promote-component-proceeds-on-go-ahead` grades the test
    # (`design-system/**/*stat_cell*test*`) on exactly that pattern.
    _write(root, "test/components/ds_button_test.dart",
           "import 'package:flutter_test/flutter_test.dart';\n"
           "import 'package:example_design_system/example_design_system.dart';\n"
           "\n"
           "void main() {\n"
           "  testWidgets('DsButton renders its label', (tester) async {\n"
           "    await tester.pumpWidget(const DsButton(label: 'Save'));\n"
           "    expect(find.text('Save'), findsOneWidget);\n"
           "  });\n"
           "}\n")
    _write(root, "gallery/ds_button_gallery.dart",
           "// One use case per component. Every component in lib/src/components/\n"
           "// must appear here; this is the gallery gate Step 3 refers to.\n"
           "import 'package:example_design_system/example_design_system.dart';\n"
           "\n"
           "final dsButtonUseCases = [\n"
           "  DsButton(label: 'Default', onPressed: () {}),\n"
           "  const DsButton(label: 'Disabled'),\n"
           "];\n")
    # `doc/`, not `docs/`: Dart's own convention, and it keeps the component
    # docs out of the directory the doc-role scaffolder writes into, so a
    # bootstrap case run against this fixture is not reading these as project
    # documents.
    _write(root, "doc/components/ds_button.md",
           "# DsButton\n\nOne entry per exported component: what it is for, its "
           "parameters, and when to reach for something else.\n\n"
           "| Parameter | Type | Notes |\n| --- | --- | --- |\n"
           "| `label` | `String` | Required. |\n"
           "| `onPressed` | `VoidCallback?` | Null disables the button. |\n")


def _docs_site_sources(root: Path) -> None:
    # A repository whose product is a published documentation site: content and
    # a site generator config, no application source at all.
    _write(root, "README.md",
           "# Example Docs Site\n\nThe published documentation site. Its product is the "
           "site itself, not an application.\n")
    _write(root, "mkdocs.yml",
           "site_name: Example Docs\nnav:\n  - Home: index.md\n  - Guide: guide.md\n")
    _write(root, "docs/index.md", "# Home\n\nWelcome.\n")
    _write(root, "docs/guide.md", "# Guide\n\nHow to use the thing.\n")


AUTHORED_DESIGN_DOC = """# Design

This document is deliberately *written*, not scaffolded — it carries no
`status: stub` frontmatter, so it resolves with exit 0 and counts as real
coverage. It exists so a case can tell an authored document apart from the
stub and the decline that sit beside it in this same fixture.

## Layout

Two screens, a single column, spacing from the token scale.

## Colour

One primary, one surface, one error. Semantic roles only; no literal hex in
screen code.
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
    path = root / ".design-suite/profile.json"

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
    _edit_json(root / ".design-suite/profile.json",
               lambda d: d["project"].__setitem__("projectKind", kind))


def build_zero_state(root: Path) -> None:
    """Source files and nothing else — no `.design-suite/` at all.

    The onboarding path nothing has ever exercised. Every `bin/*.py` exits 2
    here via `project_root()`, and that is the correct behaviour, not a bug:
    the point of the fixture is that a case can assert the refusal rather than
    a skill inventing a project shape.
    """
    _app_sources(root)


def build_app(root: Path) -> None:
    """A scaffolded `app` with one authored doc, one real decline, one stub.

    Exercises exit 4 (declined) and exit 5 (stub) side by side with exit 0
    (authored), which is the only arrangement that proves a skill is reading
    the exit code rather than the file's existence.
    """
    _app_sources(root)
    _init(root, "Example App")
    _declare_kind(root, "app")

    # Authored: a real document, no stub frontmatter.
    manifest = json.loads((root / ".design-suite/docs.manifest.json").read_text())
    _write(root, manifest["roles"][AUTHORED_ROLE], AUTHORED_DESIGN_DOC)

    # Stub: written by the real scaffolder, so the `status: stub` frontmatter is
    # whatever scaffold_doc.py actually emits today, not a copy of it.
    _run([sys.executable, str(BIN / "scaffold_doc.py"), STUB_ROLE, "--dir", str(root)])

    # Declined: recorded by the real tool, with a reason. A decline with no
    # reason is the silence the state exists to prevent, so the fixture carries
    # a real sentence — and the self-test asserts it is still there.
    _run([sys.executable, str(BIN / "decline_doc.py"), DECLINED_ROLE,
          "--dir", str(root), "--reason", DECLINE_REASON,
          "--by", "fixture builder", "--on", "2026-01-01"])


def build_app_configured(root: Path) -> None:
    """The `app` fixture with its profile and arch-rules actually filled in.

    WHY THIS IS A VARIANT AND NOT A CHANGE TO `app`

    `init.py` writes every profile and arch-rules value as a `TODO:` string, and
    the plain `app` fixture keeps them that way — correctly, because four
    `map-project-*` cases exist to watch `/map-project` propose exactly those
    fields. Filling them in place would neuter those cases: the skill would
    arrive to find its own job already done.

    But the four `/promote-component` cases need the opposite. Their command's
    Step 0 is `audit_reinvented_components.py`, which REFUSES (exit 2) when
    `reinventedComponents.package` is a TODO — and Step 1's decision is recorded
    by `audit_promotion_candidates.py`, which cannot see a duplicate shape
    without a source root. Run against the unconfigured fixture, Step 0 returns
    a refusal, and the command is left arguing about a promotion from no
    evidence at all.

    So: same sources, same design-system counterpart, one extra step. Not a new
    fixture pair — `_app_sources` and `build_design_system` are shared verbatim,
    and every source assertion in the self-test applies to both.

    The values are the true ones for this fixture's own tree, not plausible
    filler: `lib` really is the source root, `example_design_system` really is
    what `../design-system/pubspec.yaml` names itself, and `Ds` really is the
    prefix its exported components carry.
    """
    build_app(root)

    def configure_profile(profile: dict) -> None:
        profile["project"]["framework"] = "Flutter, Material 3"
        profile["project"]["audience"] = "general consumer, adults 18+"
        profile["adapters"]["lang"] = "dart"
        profile["source"].update({
            "root": "lib",
            "fileGlob": "**/*.dart",
            "screensGlob": "screens/**/*.dart",
            "featureWidgetsGlob": "widgets/**/*.dart",
            "testRoot": "test",
        })
        # No `sharedComponentDir`: the shared components live in the OTHER
        # repository, which is the whole premise of these cases. Deleted rather
        # than pointed somewhere, because a wrong path here would make the
        # audits compare private widgets against an empty directory and print a
        # clean run.
        profile["source"].pop("sharedComponentDir", None)
        profile["tokens"]["source"] = {"kind": "file", "path": "lib/theme/app_theme.dart"}
        profile["tokens"]["accessor"] = "AppTheme"
        profile["tokens"].pop("themeAccessor", None)
        profile["tokens"].pop("ownedBy", None)

    _edit_json(root / ".design-suite/profile.json", configure_profile)

    def configure_rules(rules: dict) -> None:
        # Only the two sections the promote-component flow reaches. Every other
        # section stays TODO on purpose: an unfilled section makes its audit
        # refuse cleanly, which is the documented behaviour, and filling all of
        # them would make this fixture a more configured project than either
        # real adopter.
        rules["reinventedComponents"].update({
            "exportPrefix": "Ds",
            "package": "example_design_system",
        })
        rules["promotionCandidates"]["baseline"] = \
            ".design-suite/baselines/promotion-candidates.json"

    _edit_json(root / ".design-suite/arch-rules.json", configure_rules)

    # The package manager's own resolution map. `audit_reinvented_components.py`
    # reads the design system's exported types out of the RESOLVED package
    # (component_shape.package_resolver -> .dart_tool/package_config.json) and
    # refuses with exit 2 when it cannot resolve — so without this file Step 0
    # refuses even with `reinventedComponents.package` correctly declared, which
    # is the second half of the same blocker and not an obvious one.
    #
    # Written, not generated, for the reason the module docstring gives about
    # source: there is no `flutter pub get` to run here and no network to run it
    # over. It is a small, exactly-specified toolchain artifact rather than a
    # stand-in for a tool's judgement.
    #
    # `rootUri` is RELATIVE — resolved against the audit's working directory,
    # which is the app repo. That is correct when the two fixtures are built as
    # siblings, which is the only arrangement the promote-component cases use;
    # each case's scaffold.sh rewrites it to the run base's real absolute path
    # once both trees exist, because a run's working directory is the base
    # rather than ./app.
    _write(root, ".dart_tool/package_config.json", json.dumps({
        "configVersion": 2,
        "generated": "2026-01-01T00:00:00.000Z",
        "generator": "eval fixture builder",
        "packages": [
            {
                "name": "example_design_system",
                "rootUri": "../design-system",
                "packageUri": "lib/",
                "languageVersion": "3.0",
            },
        ],
    }, indent=2) + "\n")


def build_design_system(root: Path) -> None:
    """A design-system-shaped repo with NO `.design-suite/`.

    The archetype whose recipes were written from the role vocabulary and never
    from a real repo. Undeclared on purpose: the interesting question is whether
    a skill reads the shape or assumes `app`.
    """
    _design_system_sources(root)


def build_design_system_declared(root: Path) -> None:
    """The same repo with `projectKind: design-system` actually declared."""
    _design_system_sources(root)
    _init(root, "Example Design System")
    _declare_kind(root, "design-system")


def build_docs_site(root: Path) -> None:
    """Minimal docs-site shape, declared.

    `docs-site` owns no role exclusively — see fixture_selftest.py, which
    measures that from the vocabulary rather than asserting the claim here. A
    case's job is to check a skill *says so and stops* rather than falling
    through to `app`'s recipe.
    """
    _docs_site_sources(root)
    _init(root, "Example Docs Site")
    _declare_kind(root, "docs-site")


def build_undeclared_kind(root: Path) -> None:
    """The `app` fixture with `projectKind` removed.

    Both real consumer projects are in exactly this state today, which makes it
    the most important fixture here: it is not an edge case, it is the default.
    `archetypes.kind_of()` must raise `ArchetypeNotDeclared` — never guess.
    """
    build_app(root)
    _edit_json(root / ".design-suite/profile.json",
               lambda d: d["project"].pop("projectKind", None))


def build_pre_ratified(root: Path) -> None:
    """The `app` fixture plus one field a human has ratified.

    `state: approved` with `by` / `on` / `verifiedAgainst` is the strongest
    claim the provenance model can carry. Nothing may downgrade it to
    `inferred` or overwrite its value — init.py is already built so it cannot
    (SEEDED_STATE), and a case's job is to prove a *skill* cannot either.
    """
    build_app(root)

    def mutate(profile: dict) -> None:
        fields = profile.setdefault("provenance", {}).setdefault("fields", {})
        fields.pop("_example", None)
        fields[RATIFIED_FIELD] = {
            "state": "approved",
            "by": "a human who reviewed it",
            "on": "2026-01-01",
            "value": "lib",
            "evidence": "read the tree and confirmed every source file is under lib/",
            "verifiedAgainst": {"commit": "0" * 40},
        }
        # The ratified value must agree with the profile itself, or doctor would
        # report it contradicted and the fixture would be testing the wrong state.
        profile["source"]["root"] = "lib"

    _edit_json(root / ".design-suite/profile.json", mutate)


FIXTURES = {
    "zero-state": build_zero_state,
    "app": build_app,
    "app-configured": build_app_configured,
    "design-system": build_design_system,
    "design-system-declared": build_design_system_declared,
    "docs-site": build_docs_site,
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
