#!/usr/bin/env python3
"""Tests for audit_contract_headers.py and the three units it stands on.

Stdlib `unittest`, no pytest, matching this repo's Python-tooling convention.

Re-authored from the purged design-suite version: dart fixtures are replaced
by php — a Lumen-shaped fixture where the "screens" are controllers carrying
a `CONTRACT` header over a `private …Contract $contract;` receiver, and the
adapter unit cases moved from `adapters.dart` to `adapters.php`. The
`Sections` cases exercise `engine/contracts`, which is language-agnostic, so
they carry over verbatim.

Every hazard case is a wrong answer the dart version measured on real files;
the php counterparts were measured against `adapters/php.py` before being
asserted here.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contract_headers_test.py"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN))

from backend_suite.adapters import php            # noqa: E402
from backend_suite.adapters.base import CapabilityError  # noqa: E402
from backend_suite.engine import contracts        # noqa: E402

RUNNER = HERE / "audit_contract_headers.py"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "adapters": {"lang": "php"},
    "source": {
        "root": "app",
        "fileGlob": "**/*.php",
    },
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

CONTRACT_RULES = {
    "scope": "app/Http/Controllers/*.php",
    "adapterGlob": "app/Services/*.php",
    "headerMarker": "CONTRACT",
    "sectionLabels": {"input": ["INPUT", "INPUTS"], "output": ["OUTPUT", "OUTPUTS"]},
    "namePrefix": "$contract.",
    "receiverPattern": r"private\s+(\w+)\s+\$contract\s*;",
    "receiverName": "contract",
    # The suffix stays INSIDE the capture: `class\s+(\w+)Controller` would
    # capture "Loose" for `class LooseController`, and the loose-parameter
    # branch resolves its contract by looking that name up in class_fields —
    # a name no class declares. (dart's pattern captured `(\w+Screen)` the
    # same way.)
    "screenClassPattern": r"class\s+(\w+Controller)\b",
    "outputPrefixes": ["on"],
    "screenTreeDepth": 2,
}

SERVICE = """<?php

class {cls}Contract
{{
    public string $title;
{extra}
    public function onTap()
    {{
        return true;
    }}
}}
"""

CLEAN_CONTROLLER_BODY = """    public function render()
    {
        return $this->contract->title . $this->contract->onTap();
    }
"""


def header(inputs: str, outputs: str | None = "") -> str:
    out = f"\nOUTPUT:   {outputs}" if outputs is not None else ""
    return (
        "/*\n"
        "===============================================================================\n"
        "ORDERS CONTRACT\n"
        "===============================================================================\n"
        "\n"
        "PURPOSE:  Serve the orders endpoint.\n"
        "\n"
        f"INPUT:    {inputs}{out}\n"
        "===============================================================================\n"
        "*/\n"
    )


# --------------------------------------------------------------------------- #
# Unit layer: class structure hazards, php edition
# --------------------------------------------------------------------------- #


class ClassStructureHazards(unittest.TestCase):
    """The wrong answers the dart version measured, re-measured on php.

    Each php counterpart was run against adapters/php.py before being
    written: a hazard row that has never fired is not a regression guard.
    """

    def test_multiline_promoted_constructor_properties_are_found(self):
        # A line-anchored parse lost properties whose declaration wraps —
        # the dart twin reported a documented field as absent.
        src = """<?php
class ThingContract {
    public function __construct(
        private string $id,
        private string $name,
    ) {}
}
"""
        self.assertEqual(set(php.class_fields(src, "ThingContract") or {}),
                         {"id", "name"})

    def test_sibling_class_contributes_nothing(self):
        # Reading from the first `class` to EOF counted the row model's
        # fields as the adapter's.
        src = """<?php
class Ticket { public $id; public $subject; }
class ThingContract { public $isLoading; }
"""
        self.assertEqual(set(php.class_fields(src, "ThingContract") or {}),
                         {"isLoading"})
        self.assertEqual(set(php.class_fields(src, "Ticket") or {}),
                         {"id", "subject"})

    def test_attributes_and_comma_defaults_do_not_split_members(self):
        # `#[Get('/x (y)')]` must not prefix the next declaration, and a
        # comma inside a default string must not split the parameter list.
        src = """<?php
class ThingContract {
    #[Get('/x (y)')]
    public function totalFor(string $id) { return 1; }

    public $title;

    public function __construct(
        private string $a = "x, y",
        public string $note = 'z',
    ) {}
}
"""
        self.assertEqual(set(php.class_fields(src, "ThingContract") or {}),
                         {"a", "note", "title"})
        self.assertEqual(
            set(php.class_members(src, "ThingContract") or {}),
            {"a", "note", "title", "totalFor"})

    def test_method_locals_are_not_fields_and_private_methods_are_not_members(self):
        src = """<?php
class ThingContract {
    public $count;
    public function refresh() { $local = 1; $this->count = $local; }
    private function hidden() { return 1; }
}
"""
        self.assertEqual(set(php.class_fields(src, "ThingContract") or {}),
                         {"count"})
        self.assertEqual(
            set(php.class_members(src, "ThingContract") or {}),
            {"count", "refresh"})

    def test_absent_class_is_none_not_empty(self):
        # `{}` means "declares nothing"; `None` means "not here". Conflating
        # them reports a real adapter as declaring no members.
        self.assertIsNone(php.class_fields("<?php\nclass Other {}\n",
                                          "ThingContract"))


class CommentBlanking(unittest.TestCase):
    def test_line_numbers_and_length_are_preserved(self):
        src = "a\n// gone\n# also gone\nb\n"
        blanked = php.blank_comments(src)
        self.assertEqual(len(blanked), len(src))
        self.assertEqual(blanked.count("\n"), src.count("\n"))
        self.assertNotIn("gone", blanked)

    def test_url_inside_a_string_is_not_a_comment(self):
        src = "final $u = 'https://example.test/x';\nfinal $v = 1;\n"
        self.assertIn("example.test", php.blank_comments(src))
        self.assertIn("final $v = 1", php.blank_comments(src))

    def test_an_attribute_is_not_a_comment(self):
        # `#[` opens an attribute, not a `#` comment: blanking it would hide
        # the declaration that follows from every structural scan.
        src = "#[Route('/x')]\npublic $title;\n"
        self.assertIn("Route", php.blank_comments(src))
        self.assertIn("public $title", php.blank_comments(src))

    def test_php_block_comments_do_not_nest_so_late_text_is_code(self):
        # C-style comments close at the first `*/`; what follows is code and
        # must survive the blanking (blanking it would silently drop reads).
        src = "/* outer /* inner */ still */\nfinal $v = 1;\n"
        self.assertIn("still", php.blank_comments(src))
        self.assertIn("final $v = 1", php.blank_comments(src))

    def test_block_comments_expose_each_block_with_its_line(self):
        blocks = php.block_comments(
            "<?php\n/*\nCONTRACT\n*/\n$x = 1;\n/* b */\n$y = 2;\n")
        self.assertEqual(len(blocks), 2)
        self.assertIn("CONTRACT", blocks[0][1])
        self.assertIn("b", blocks[1][1])
        self.assertIsInstance(blocks[0][0], int)


class TypedReceivers(unittest.TestCase):
    """Resolving the receiver by its declared type, not by what it is called."""

    def test_a_typed_parameter_is_a_receiver(self):
        src = "<?php\nfunction f(ThingContract $a) { return $a->title; }\n"
        self.assertEqual(php.typed_member_reads(src, {"ThingContract"}),
                         {"ThingContract": {"title"}})

    def test_a_constructor_local_and_a_property_are_receivers(self):
        src = ("<?php\n$a = new ThingContract();\nreturn $a->onTap();\n")
        self.assertEqual(php.typed_member_reads(src, {"ThingContract"}),
                         {"ThingContract": {"onTap"}})
        prop = ("<?php\nclass X { private ThingContract $svc;"
                " function m() { return $this->svc->total; } }\n")
        self.assertEqual(php.typed_member_reads(prop, {"ThingContract"}),
                         {"ThingContract": {"total"}})

    def test_a_namespace_prefix_resolves_to_the_same_type(self):
        src = "<?php\nfunction f(App\\ThingContract $a) { return $a->title; }\n"
        self.assertEqual(php.typed_member_reads(src, {"ThingContract"}),
                         {"ThingContract": {"title"}})

    def test_a_comment_is_not_a_read(self):
        src = "<?php\n// ThingContract $a reads $a->title\n$x = 1;\n"
        self.assertEqual(php.typed_member_reads(src, {"ThingContract"}), {})

    def test_the_class_declaration_itself_is_not_a_receiver(self):
        src = "<?php\nclass ThingContract { public $title; }\n"
        self.assertEqual(php.typed_member_reads(src, {"ThingContract"}), {})

    def test_an_untyped_class_binding_raises_rather_than_answering(self):
        # `$a = $c->get(ThingContract::class)` binds a receiver whose reads
        # are invisible; "I cannot tell" must not come back as "dead".
        src = ("<?php\n$a = $c->get(ThingContract::class);\n"
               "return $a->title;\n")
        with self.assertRaises(CapabilityError):
            php.typed_member_reads(src, {"ThingContract"})


class MemberReadsAndAliases(unittest.TestCase):
    def test_both_receiver_forms_are_reads_and_the_header_is_not(self):
        src = header("$contract.isLoading") + (
            "<?php\n"
            "$x = $this->contract->title;\n"
            "$y = $contract->onSave;\n"
            "// $contract->fromComment\n"
        )
        self.assertEqual(php.member_reads(src, "contract"),
                         {"title", "onSave"})

    def test_alias_bindings_both_spellings(self):
        src = ("<?php\nfunction m() { $a = $this->contract; $b = $contract; }\n"
               "class X { private $contract; function n() {"
               " $contract = $this->contract; } }\n")
        self.assertEqual(php.receiver_aliases(src, "contract"), {"a", "b"})

    def test_the_receiver_is_not_its_own_alias(self):
        src = "<?php\nclass X { function m() { $contract = $contract; } }\n"
        self.assertEqual(php.receiver_aliases(src, "contract"), set())


# --------------------------------------------------------------------------- #
# engine/contracts — language-agnostic, carried over verbatim
# --------------------------------------------------------------------------- #


class Sections(unittest.TestCase):
    def test_inline_with_wrapped_continuation(self):
        text = (
            "\nOUTPUT:   $contract.onSelect(id), $contract.onFilter(status),\n"
            "          $contract.onApprove(id, scheduleFor:)\n"
            "\n"
        )
        self.assertEqual(
            set(contracts.section(text, ["OUTPUT"], "$contract.", 1)),
            {"onSelect", "onFilter", "onApprove"},
        )

    def test_bulleted_dialect(self):
        text = "\nINPUT:\n- $contract.isLoading\n- $contract.staff\n\n"
        self.assertEqual(
            set(contracts.section(text, ["INPUT"], "$contract.", 1)),
            {"isLoading", "staff"},
        )

    def test_a_sub_path_documents_the_field_it_starts_from(self):
        text = "\nINPUT:\n- $contract.initial.hasAllergies\n"
        self.assertEqual(
            set(contracts.section(text, ["INPUT"], "$contract.", 1)),
            {"initial"})

    def test_a_label_may_carry_a_parenthetical(self):
        text = ("\nINPUT (via Contract, built by the wrapper):\n- content\n"
                "\nOUTPUT (via Contract callbacks):\n- onRetry()\n")
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)),
                         {"content"})
        self.assertEqual(set(contracts.section(text, ["OUTPUT"], "", 1)),
                         {"onRetry"})

    def test_a_decorated_label_still_anchors_a_finding(self):
        text = "\nPURPOSE: x\nOUTPUT (via callbacks):\n- onRetry()\n"
        self.assertEqual(contracts.label_line(text, ["OUTPUT"], 1, 1), 3)

    def test_a_slash_separates_entries_too(self):
        text = "\nINPUT:\n- isLoading / errorMessage -> skeleton / error state\n"
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)),
                         {"isLoading", "errorMessage"})

    def test_dot_field_shorthand_on_a_wrapped_line(self):
        # Measured in #104: `.field` entries were dropped as prose and nine
        # of the most thoroughly documented header's members read as
        # undocumented.
        text = ("\nINPUT:    $contract.journey, .riskFactors, .alerts,\n"
                "          .isLoading\n")
        self.assertEqual(
            set(contracts.section(text, ["INPUT"], "$contract.", 1)),
            {"journey", "riskFactors", "alerts", "isLoading"})

    def test_a_prose_entry_is_not_a_field(self):
        text = ("\nOUTPUT:   $contract.onTap(), "
                "router.push() to article/video detail routes\n")
        self.assertEqual(
            set(contracts.section(text, ["OUTPUT"], "$contract.", 1)),
            {"onTap"})

    def test_an_annotated_call_is_still_a_field(self):
        text = "\nOUTPUT:   $contract.onRefresh() — awaited by pull-to-refresh\n"
        self.assertEqual(
            set(contracts.section(text, ["OUTPUT"], "$contract.", 1)),
            {"onRefresh"})

    def test_absent_section_is_empty_not_an_error(self):
        self.assertEqual(contracts.section("\nINPUT:  a\n", ["OUTPUT"], "", 1), {})

    def test_another_label_terminates(self):
        text = "\nINPUT:    a\nRULES:    do not fetch\n"
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)), {"a"})

    def test_section_terminates_on_a_rule_line(self):
        text = (
            "\nPURPOSE:  x\n"
            "\nINPUT:    member\n"
            "===============================================================================\n"
        )
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)), {"member"})

    def test_lines_are_absolute_to_the_file(self):
        text = "\nINPUT:\n- $contract.staff\n"
        # header starts at file line 6; INPUT is text line 1, the bullet line 2.
        self.assertEqual(
            contracts.section(text, ["INPUT"], "$contract.", 6)["staff"], 8)


# --------------------------------------------------------------------------- #
# End-to-end: the runner over a throwaway php project
# --------------------------------------------------------------------------- #


class Project:
    """A throwaway project on disk, so the runner can be exercised for real."""

    def __init__(self, tmp: Path, rules=None, profile=None):
        self.root = tmp
        (tmp / ".backend-suite").mkdir(parents=True, exist_ok=True)
        (tmp / ".backend-suite/profile.json").write_text(
            json.dumps(profile or PROFILE))
        (tmp / ".backend-suite/arch-rules.json").write_text(
            json.dumps({"contractHeaders": rules or CONTRACT_RULES}))

    def add(self, rel: str, body: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def feature(self, name="orders", *, header_text, service_body,
                controller_body="", cls="Orders"):
        """One feature: a contract class and a controller handed it.

        The `private …Contract $contract;` property is not decoration —
        without it the runner cannot tell which contract the header
        describes and refuses.
        """
        self.add(f"app/Services/{name}_contract.php", service_body)
        self.add(
            f"app/Http/Controllers/{cls}Controller.php",
            header_text
            + f"class {cls}Controller\n{{\n"
            + f"    private {cls}Contract $contract;\n\n"
            + f"{controller_body}}}\n",
        )

    def run(self, *extra):
        out = self.root / "findings.json"
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--out", "findings.json", *extra],
            cwd=self.root, capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
        )
        findings = json.loads(out.read_text()) if out.is_file() else []
        return proc, findings


CLEAN_SERVICE = SERVICE.format(cls="Orders", extra="")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def clean_feature(self, p: Project, *, inputs="$contract.title",
                      outputs="$contract.onTap()", extra_fields="",
                      controller_body=CLEAN_CONTROLLER_BODY, cls="Orders"):
        p.feature(
            header_text=header(inputs, outputs),
            service_body=SERVICE.format(cls=cls, extra=extra_fields),
            controller_body=controller_body,
            cls=cls,
        )

    def test_clean_project_reports_nothing_and_exits_zero(self):
        p = Project(self.tmp)
        self.clean_feature(p)
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings, [])

    def test_undocumented_field(self):
        p = Project(self.tmp)
        self.clean_feature(
            p,
            extra_fields="    public string $subtitle;\n",
            controller_body="    public function render()\n    {\n"
                            "        return $this->contract->title"
                            " . $this->contract->subtitle"
                            " . $this->contract->onTap();\n    }\n",
        )
        proc, findings = p.run()
        self.assertEqual([(f["kind"], f["name"]) for f in findings],
                         [("undocumented_field", "subtitle")])
        self.assertEqual(proc.returncode, 1)

    def test_stale_header_entry(self):
        p = Project(self.tmp)
        self.clean_feature(p, inputs="$contract.title, $contract.selectedId")
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 1)
        self.assertIn(("stale_header_entry", "selectedId"),
                      [(f["kind"], f["name"]) for f in findings])

    def test_dead_adapter_field_reported_against_the_service_file(self):
        p = Project(self.tmp)
        self.clean_feature(p, extra_fields="    public bool $isLoading;\n")
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 1)
        dead = [f for f in findings if f["kind"] == "dead_adapter_field"]
        self.assertEqual([f["name"] for f in dead], ["isLoading"])
        self.assertTrue(dead[0]["file"].endswith("orders_contract.php"))

    def test_a_read_through_a_receiver_not_named_contract_is_not_dead(self):
        # Measured in the dart origin: a helper taking `CarePlanAdapter a`
        # read `a.patientName` and the field was advised for deletion.
        p = Project(self.tmp)
        self.clean_feature(
            p, extra_fields="    public string $patientName;\n")
        p.add("app/Support/payload.php",
              "<?php\n"
              "function payload(OrdersContract $a)\n"
              "{\n"
              "    return $a->patientName;\n"
              "}\n")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_receiver_the_adapter_cannot_type_refuses(self):
        p = Project(self.tmp)
        self.clean_feature(
            p, extra_fields="    public string $patientName;\n")
        p.add("app/Support/payload.php",
              "<?php\n"
              "$a = $c->get(OrdersContract::class);\n"
              "return $a->patientName;\n")
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("untyped receiver", proc.stdout + proc.stderr)
        self.assertEqual(findings, [])

    def test_a_use_outside_the_screens_own_tree_is_neither_dead_nor_undocumented(self):
        # One contract, two controllers: composition forwarding a second
        # callback. A use outside this screen's tree may not make the field
        # dead (it is read), and may not make this header stale for not
        # listing what this screen never touches.
        p = Project(self.tmp)
        self.clean_feature(
            p, extra_fields="    public function onPublish() { return 1; }\n")
        p.add("app/Support/composition.php",
              "<?php\n"
              "class Wire\n"
              "{\n"
              "    private OrdersContract $contract;\n"
              "    public function publish()\n"
              "    {\n"
              "        return $this->contract->onPublish();\n"
              "    }\n"
              "}\n")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_use_inside_the_screens_own_tree_counts_as_that_screens_use(self):
        # tree depth 2 from app/Http/Controllers/x.php is app/Http, so a
        # resource class beside the controller is its own subtree.
        p = Project(self.tmp)
        self.clean_feature(
            p, extra_fields="    public function onSave() { return 1; }\n")
        p.add("app/Http/Resources/orders_resource.php",
              "<?php\n"
              "class OrdersResource\n"
              "{\n"
              "    private OrdersContract $contract;\n"
              "    public function json()\n"
              "    {\n"
              "        return $this->contract->onSave();\n"
              "    }\n"
              "}\n")
        proc, findings = p.run()
        # In this screen's own tree (app/Http at depth 2), so its read counts
        # as this screen's read: not dead anywhere, but undocumented here —
        # the complement of the outside-the-tree test above, which stays clean.
        self.assertEqual([(f["kind"], f["name"]) for f in findings],
                         [("undocumented_field", "onSave")])
        self.assertEqual(proc.returncode, 1)

    def test_missing_header_is_reported_not_skipped(self):
        p = Project(self.tmp)
        self.clean_feature(p)  # a headered control, so the corpus is not all empty
        p.feature("thing", cls="Thing",
                  header_text="",  # no header at all
                  service_body=SERVICE.format(cls="Thing", extra=""),
                  controller_body="    public function render()"
                                  " { return $this->contract->title; }\n")
        proc, findings = p.run()
        self.assertIn("missing_contract_header", [f["kind"] for f in findings])
        self.assertEqual(proc.returncode, 1)

    def test_loose_parameter_controller_is_checked_not_skipped(self):
        # No receiver property: the controller's own promoted constructor
        # parameters *are* its contract. `plan` is listed; `onBack` is not.
        p = Project(self.tmp)
        self.clean_feature(p)
        p.add("app/Http/Controllers/LooseController.php",
              header("plan", None) + """
class LooseController
{
    public function __construct(
        private ?Plan $plan,
        private callable $onBack,
    ) {}
}
""")
        proc, findings = p.run()
        self.assertEqual([(f["kind"], f["name"]) for f in findings],
                         [("undocumented_field", "onBack")])
        self.assertEqual(proc.returncode, 1)

    def test_baseline_suppresses_and_then_reports_itself_stale(self):
        p = Project(self.tmp, rules={**CONTRACT_RULES,
                                     "baseline": ".backend-suite/baseline.json"})
        self.clean_feature(p, extra_fields="    public bool $isLoading;\n")
        proc, _ = p.run("--baseline-write")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        written = json.loads(
            (self.tmp / ".backend-suite/baseline.json").read_text())
        self.assertIn("_readme", written)
        self.assertEqual(len(written["accepted"]), 1)

        # Suppressed, but reported as having no recorded reason.
        proc, findings = p.run()
        self.assertEqual(findings, [])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unjustified", proc.stdout)

        # With a reason, it goes quiet.
        key = next(iter(written["accepted"]))
        (self.tmp / ".backend-suite/baseline.json").write_text(json.dumps(
            {"accepted": {key: "wired next sprint, tracked in #123"}}))
        proc, _ = p.run()
        self.assertNotIn("unjustified", proc.stdout)
        self.assertEqual(proc.returncode, 0)

        # Fix the finding; the baseline entry is now an exemption nobody needs.
        self.clean_feature(p)
        proc, _ = p.run()
        self.assertIn("stale baseline", proc.stdout)


class Portability(unittest.TestCase):
    """What a second consumer needed that the first did not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_contract_class_declared_inside_the_controller_file_resolves(self):
        # A dedicated-file glob alone cannot find classes declared beside
        # their use; adapterGlob takes several globs for exactly this.
        p = Project(self.tmp, rules={
            **CONTRACT_RULES,
            "adapterGlob": ["app/Services/*.php", "app/Http/Controllers/*.php"],
        })
        p.add("app/Http/Controllers/InlineController.php",
              header("$contract.title", None) + """
class InlineController
{
    private InlineContract $contract;

    public function render()
    {
        return $this->contract->title;
    }
}

class InlineContract
{
    public string $title;
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_documented_query_method_is_not_stale(self):
        # `totalFor` is a public method on the contract and its header says
        # so; counting only properties would call it a stale entry.
        p = Project(self.tmp)
        p.feature(
            header_text=header("$contract.title, $contract.totalFor(id)",
                               "$contract.onTap()"),
            service_body="""<?php

class OrdersContract
{
    public string $title;

    public function totalFor(string $id) { return 1; }

    public function onTap()
    {
        return true;
    }
}
""",
            controller_body="    public function render()\n    {\n"
                            "        return $this->contract->title"
                            " . $this->contract->totalFor('a')"
                            " . $this->contract->onTap();\n    }\n",
        )
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_loose_controllers_own_methods_are_not_its_contract(self):
        # The loose-parameter branch uses class_fields, not class_members:
        # `render` is the controller's own method, not an input it was handed.
        p = Project(self.tmp)
        # adapterGlob still has to match something, even for an all-loose
        # corpus — otherwise the run refuses before reaching any screen.
        p.add("app/Services/unused_contract.php",
              """<?php
class UnusedContract
{
}
""")
        p.add("app/Http/Controllers/LooseController.php",
              header("plan", None) + """
class LooseController
{
    public function __construct(
        private ?Plan $plan,
    ) {}

    public function render() { return 'x'; }
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_controller_taking_the_contract_and_a_direct_parameter(self):
        # The header documents both surfaces. The direct parameter is a
        # widget field for the undocumented check and is excluded from the
        # dead-member check, which may only look at the contract.
        p = Project(self.tmp)
        p.add("app/Services/orders_contract.php",
              """<?php

class OrdersContract
{
    public string $title;
}
""")
        p.add("app/Http/Controllers/OrdersController.php",
              header("$contract.title, readOnly — hides the FAB", None) + """
class OrdersController
{
    private OrdersContract $contract;
    private bool $readOnly;

    public function render()
    {
        return $this->contract->title;
    }
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_excluded_files_are_named_in_the_output_not_silently_dropped(self):
        p = Project(self.tmp, rules={
            **CONTRACT_RULES,
            "excludeGlobs": ["app/Http/Controllers/*_wrapper.php"],
        })
        p.add("app/Services/orders_contract.php", CLEAN_SERVICE)
        p.add("app/Http/Controllers/OrdersController.php",
              header("$contract.title", "$contract.onTap()") + """
class OrdersController
{
    private OrdersContract $contract;

    public function render()
    {
        return $this->contract->title . $this->contract->onTap();
    }
}
""")
        # In the screens glob, documented as not a screen.
        p.add("app/Http/Controllers/orders_wrapper.php",
              "<?php\nclass OrdersWrapper {}\n")
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings, [])
        self.assertIn("excluded", proc.stdout)
        self.assertIn("orders_wrapper.php", proc.stdout)

    def test_excluding_everything_refuses(self):
        p = Project(self.tmp, rules={**CONTRACT_RULES,
                                     "excludeGlobs": ["app/**/*.php"]})
        p.add("app/Services/orders_contract.php", CLEAN_SERVICE)
        p.add("app/Http/Controllers/OrdersController.php",
              header("$contract.title", None) + """
class OrdersController
{
    private OrdersContract $contract;
}
""")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("vacuously", proc.stdout + proc.stderr)


class Refusals(unittest.TestCase):
    """The governing principle: never report zero because it could not look."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_language_without_the_capability_is_inert_not_clean(self):
        p = Project(self.tmp, profile={**PROFILE, "adapters": {"lang": "tsx"}})
        p.feature(header_text=header("$contract.title", None),
                  service_body=CLEAN_SERVICE)
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("INERT", proc.stdout + proc.stderr)

    def test_a_scope_matching_nothing_refuses(self):
        p = Project(self.tmp)
        p.add("app/x.php", "<?php\n$v = 1;\n")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("matched nothing", proc.stdout + proc.stderr)

    def test_an_unresolvable_contract_class_refuses(self):
        p = Project(self.tmp)
        p.add("app/Services/orders_contract.php", CLEAN_SERVICE)
        p.add("app/Http/Controllers/OrdersController.php",
              header("$contract.title", None) + """
class OrdersController
{
    private MissingThing $contract;
}
""")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("Refusing to skip", proc.stdout + proc.stderr)

    def test_missing_receiver_config_refuses(self):
        rules = {k: v for k, v in CONTRACT_RULES.items()
                 if k != "receiverPattern"}
        p = Project(self.tmp, rules=rules)
        p.add("app/Services/orders_contract.php", CLEAN_SERVICE)
        p.add("app/Http/Controllers/OrdersController.php",
              header("$contract.title", None) + """
class OrdersController
{
    private OrdersContract $contract;
}
""")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("receiverPattern", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
