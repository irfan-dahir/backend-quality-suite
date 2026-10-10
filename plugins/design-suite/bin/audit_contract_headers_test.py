#!/usr/bin/env python3
"""Tests for audit_contract_headers.py and the two units it stands on.

Stdlib `unittest`, no pytest, matching this repo's Python-tooling convention.

Fixtures are synthetic — built in a temp directory, never read from a real
project's `lib/`. That is deliberate for the same reason
`audit_error_handling_test.py` gives: the originating project is about to have its
14 real findings fixed, and tests pinned to that tree would go green because the
tree changed rather than because the code works.

Every case under "hazards" is a wrong answer this engine actually produced on a
real file during development. Two of them were false positives on *correct*
headers, which is the failure that gets an audit switched off rather than fixed,
so they are the cases most worth keeping.

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

from design_suite.adapters import dart          # noqa: E402
from design_suite.adapters.base import CapabilityError   # noqa: E402
from design_suite.engine import contracts       # noqa: E402

RUNNER = HERE / "audit_contract_headers.py"

PROFILE = {
    "profileVersion": 1,
    "adapters": {"lang": "dart"},
    "source": {
        "root": "lib",
        "fileGlob": "**/*.dart",
        "screensGlob": "lib/features/*/presentation/pages/*.dart",
    },
    "audits": {"archRulesFile": ".design-suite/arch-rules.json"},
}

CONTRACT_RULES = {
    "scope": "lib/features/*/presentation/pages/*.dart",
    "adapterGlob": "lib/features/*/*_adapter.dart",
    "headerMarker": "CONTRACT",
    "sectionLabels": {"input": ["INPUT", "INPUTS"], "output": ["OUTPUT", "OUTPUTS"]},
    "namePrefix": "adapter.",
    "receiverPattern": r"final\s+(\w*Adapter)\s+adapter\s*;",
    "receiverName": "adapter",
    "screenClassPattern": r"class\s+(\w+Screen)\b",
    "outputPrefixes": ["on"],
    "screenTreeDepth": 2,
}


def header(inputs: str, outputs: str | None = "") -> str:
    out = f"\nOUTPUT:   {outputs}" if outputs is not None else ""
    return (
        "/*\n"
        "==============================================================================\n"
        "THING SCREEN CONTRACT\n"
        "==============================================================================\n"
        "\n"
        "PURPOSE:  A thing.\n"
        "\n"
        f"INPUT:    {inputs}{out}\n"
        "==============================================================================\n"
        "*/\n"
    )


class Hazards(unittest.TestCase):
    """The four wrong answers that shaped the parser, plus the fifth in reads."""

    def test_multiline_declaration_is_found(self):
        # A line-anchored regex missed this and reported the field absent — a
        # false positive on a header that listed it correctly.
        src = """
class ThingAdapter {
  const ThingAdapter({required this.onSave});

  final void Function({
    String? id,
    required String name,
  })
  onSave;
}
"""
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")), {"onSave"})

    def test_sibling_model_class_contributes_nothing(self):
        # Reading from the first `class` to EOF counted the row model's fields as
        # the adapter's: 16 where the adapter had 9.
        src = """
class Ticket {
  final String id;
  final String subject;
}

class ThingAdapter {
  final bool isLoading;
}
"""
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")), {"isLoading"})
        self.assertEqual(set(dart.class_fields(src, "Ticket")), {"id", "subject"})

    def test_getters_are_part_of_the_read_surface(self):
        # `bool get canConfirm` is something a screen reads and a header
        # documents. Counting only `final` reported six correctly documented
        # members as stale entries on a second project.
        src = """
class ThingAdapter {
  final int count;

  bool get canConfirm =>
      count > 0;

  List<String>? get labels {
    return null;
  }
}
"""
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")),
                         {"count", "canConfirm", "labels"})

    def test_a_method_body_mentioning_get_is_not_a_getter(self):
        src = """
class ThingAdapter {
  void refresh() {
    final v = store.get('k');
    use(v);
  }
}
"""
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")), set())

    def test_methods_are_not_members(self):
        src = """
class ThingAdapter {
  final int count;
  String describe(int n) => 'x';
  void reset() { count = 0; }
}
"""
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")), {"count"})

    def test_constructor_and_methods_contribute_nothing(self):
        src = """
class ThingAdapter {
  const ThingAdapter({required this.items, this.note});

  final List<String> items;
  final String? note;

  bool get isEmpty => items.isEmpty;

  String describe() {
    final local = note;
    return local ?? '';
  }
}
"""
        # `isEmpty` is a getter, so it *is* a member — see
        # test_getters_are_part_of_the_read_surface. What must contribute nothing
        # is the constructor's `required this.x` and the method's local `final`.
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")),
                         {"items", "note", "isEmpty"})

    def test_section_terminates_on_a_rule_line(self):
        # `INPUT:    member` followed immediately by `=====` with no blank line
        # absorbed the rule as a continuation, yielding a token matching nothing,
        # so a listed field was reported missing.
        text = (
            "\nPURPOSE:  x\n"
            "\nINPUT:    member\n"
            "==============================================================================\n"
        )
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)), {"member"})

    def test_comments_do_not_count_as_reads(self):
        # The header itself lists `adapter.isLoading`, so an unstripped scan made
        # every documented field look wired: 0 dead fields on a tree with 14.
        src = header("adapter.isLoading") + "\nWidget build() => Text('x');\n"
        self.assertEqual(dart.member_reads(src, "adapter"), set())

    def test_reads_through_a_local_alias_still_count(self):
        # `get _a => widget.adapter` then `_a.activePlans` is a read. Counting
        # only `adapter.` reported all 15 fields of one adapter as dead.
        src = """
class ThingScreenState extends State<ThingScreen> {
  ThingAdapter get _a => widget.adapter;
  Widget build() => Text(_a.title);
}
"""
        self.assertEqual(dart.receiver_aliases(src, "adapter"), {"_a"})
        names = {"adapter"} | dart.receiver_aliases(src, "adapter")
        self.assertEqual({n for name in names for n in dart.member_reads(src, name)},
                         {"title"})

    def test_the_other_two_alias_bindings(self):
        for line in ("    final a = widget.adapter;",
                     "    var shorter = adapter;"):
            src = f"class X {{\n  void m() {{\n{line}\n  }}\n}}\n"
            self.assertTrue(dart.receiver_aliases(src, "adapter"),
                            f"no alias found in {line!r}")

    def test_the_receiver_is_not_its_own_alias(self):
        src = "class X { void m() { final adapter = widget.adapter; } }\n"
        self.assertEqual(dart.receiver_aliases(src, "adapter"), set())

    def test_reads_are_found_in_real_code(self):
        src = header("adapter.isLoading") + "\nWidget b() => Text(adapter.title);\n"
        self.assertEqual(dart.member_reads(src, "adapter"), {"title"})


class CommentBlanking(unittest.TestCase):
    def test_line_numbers_and_length_are_preserved(self):
        src = "a\n// gone\nb\n"
        blanked = dart.blank_comments(src)
        self.assertEqual(len(blanked), len(src))
        self.assertEqual(blanked.count("\n"), src.count("\n"))
        self.assertNotIn("gone", blanked)

    def test_url_inside_a_string_is_not_a_comment(self):
        src = "final u = 'https://example.test/x';\nfinal v = 1;\n"
        self.assertIn("example.test", dart.blank_comments(src))
        self.assertIn("final v = 1", dart.blank_comments(src))

    def test_nested_block_comments(self):
        src = "/* outer /* inner */ still */\nfinal v = 1;\n"
        self.assertIn("final v = 1", dart.blank_comments(src))
        self.assertNotIn("still", dart.blank_comments(src))

    def test_field_after_a_doc_comment_mentioning_a_quote(self):
        src = """
class ThingAdapter {
  /// It's the one that matters. See http://x.test
  final String name;
}
"""
        self.assertEqual(set(dart.class_fields(src, "ThingAdapter")), {"name"})


class TypedReceivers(unittest.TestCase):
    """Resolving the receiver by its declared type, not by what it is called."""

    def test_a_parameter_of_the_contract_type_is_a_receiver(self):
        src = "Payload f(ThingAdapter a) => Payload(a.patientName, a.title);\n"
        self.assertEqual(dart.typed_member_reads(src, {"ThingAdapter"}),
                         {"ThingAdapter": {"patientName", "title"}})

    def test_a_cast_and_a_constructor_binding_are_receivers(self):
        src = ("void f(Object x) { final a = x as ThingAdapter; a.title; }\n"
               "void g() { final b = ThingAdapter(); b.onTap(); }\n")
        self.assertEqual(dart.typed_member_reads(src, {"ThingAdapter"}),
                         {"ThingAdapter": {"title", "onTap"}})

    def test_a_comment_is_not_a_read(self):
        src = "// ThingAdapter a reads a.title\nfinal int x = 1;\n"
        self.assertEqual(dart.typed_member_reads(src, {"ThingAdapter"}), {})

    def test_the_class_declaration_itself_is_not_a_receiver(self):
        src = "class ThingAdapter extends Base { final String title; }\n"
        self.assertEqual(dart.typed_member_reads(src, {"ThingAdapter"}), {})

    def test_an_untyped_binding_raises_rather_than_answering(self):
        src = "void f() { dynamic a = locate<ThingAdapter>(); a.title; }\n"
        with self.assertRaises(CapabilityError):
            dart.typed_member_reads(src, {"ThingAdapter"})


class Sections(unittest.TestCase):
    def test_inline_with_wrapped_continuation(self):
        text = (
            "\nOUTPUT:   adapter.onSelect(id), adapter.onFilter(status),\n"
            "          adapter.onApprove(id, scheduleFor:)\n"
            "\n"
        )
        self.assertEqual(
            set(contracts.section(text, ["OUTPUT"], "adapter.", 1)),
            {"onSelect", "onFilter", "onApprove"},
        )

    def test_bulleted_dialect(self):
        text = "\nINPUT:\n- adapter.isLoading\n- adapter.staff\n\n"
        self.assertEqual(
            set(contracts.section(text, ["INPUT"], "adapter.", 1)),
            {"isLoading", "staff"},
        )

    def test_a_sub_path_documents_the_field_it_starts_from(self):
        # `- initial.hasAllergies` documents `initial`, in more detail than a
        # bare name. Dropping it as prose reported the root field undocumented
        # on nine screens whose headers describe it thoroughly.
        text = "\nINPUT:\n- initial.hasAllergies\n- initial.medications\n"
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)), {"initial"})

    def test_sub_path_under_the_configured_prefix(self):
        text = "\nINPUT:    adapter.plan.title\n"
        self.assertEqual(set(contracts.section(text, ["INPUT"], "adapter.", 1)), {"plan"})

    def test_a_label_may_carry_a_parenthetical(self):
        # `OUTPUT (via LibraryAdapter callbacks):` is still an OUTPUT section.
        # Requiring a bare `OUTPUT:` made the most thoroughly documented header
        # in one project read as having no sections at all — 18 members reported
        # undocumented on a header that names every one of them.
        text = ("\nINPUT (via LibraryAdapter, built by the wrapper):\n- content\n"
                "\nOUTPUT (via LibraryAdapter callbacks):\n- onRetry()\n")
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)), {"content"})
        self.assertEqual(set(contracts.section(text, ["OUTPUT"], "", 1)), {"onRetry"})

    def test_a_decorated_label_still_anchors_a_finding(self):
        text = "\nPURPOSE: x\nOUTPUT (via callbacks):\n- onRetry()\n"
        self.assertEqual(contracts.label_line(text, ["OUTPUT"], 1, 1), 3)

    def test_a_slash_separates_entries_too(self):
        text = "\nINPUT:\n- isLoading / errorMessage -> skeleton / error state\n"
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)),
                         {"isLoading", "errorMessage"})

    def test_dot_field_shorthand_on_a_wrapped_line(self):
        # Measured in #104: a header written this way had nine of its members
        # reported undocumented, because a `.field` entry has nothing before the
        # dot to keep and was dropped as prose. A false positive on the most
        # thoroughly documented header in the project.
        text = ("\nINPUT:    adapter.journey, .riskFactors, .alerts,\n"
                "          .adherenceSeries,\n"
                "          .isLoading\n")
        self.assertEqual(
            set(contracts.section(text, ["INPUT"], "adapter.", 1)),
            {"journey", "riskFactors", "alerts", "adherenceSeries", "isLoading"})

    def test_a_prose_entry_is_not_a_field(self):
        # `context.push() to article/video detail routes` describes a
        # navigation. Read as a member it invented an adapter field `context`.
        text = ("\nOUTPUT:   adapter.onTap(), "
                "context.push() to article/video detail routes\n")
        self.assertEqual(set(contracts.section(text, ["OUTPUT"], "adapter.", 1)),
                         {"onTap"})

    def test_an_annotated_call_is_still_a_field(self):
        text = "\nOUTPUT:   adapter.onRefresh() — awaited by pull-to-refresh\n"
        self.assertEqual(set(contracts.section(text, ["OUTPUT"], "adapter.", 1)),
                         {"onRefresh"})

    def test_absent_section_is_empty_not_an_error(self):
        self.assertEqual(contracts.section("\nINPUT:  a\n", ["OUTPUT"], "", 1), {})

    def test_another_label_terminates(self):
        text = "\nINPUT:    a\nRULES:    do not fetch\n"
        self.assertEqual(set(contracts.section(text, ["INPUT"], "", 1)), {"a"})

    def test_lines_are_absolute_to_the_file(self):
        text = "\nINPUT:\n- adapter.staff\n"
        # header starts at file line 6; INPUT is text line 1, the bullet line 2.
        self.assertEqual(contracts.section(text, ["INPUT"], "adapter.", 6)["staff"], 8)


class Project:
    """A throwaway project on disk, so the runner can be exercised for real."""

    def __init__(self, tmp: Path, rules=None, profile=None):
        self.root = tmp
        (tmp / ".design-suite").mkdir(parents=True, exist_ok=True)
        (tmp / ".design-suite/profile.json").write_text(
            json.dumps(profile or PROFILE))
        (tmp / ".design-suite/arch-rules.json").write_text(
            json.dumps({"contractHeaders": rules or CONTRACT_RULES}))

    def add(self, rel: str, body: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def feature(self, name="thing", *, header_text, adapter_body, screen_body="",
                cls="Thing"):
        """One feature: an adapter file and a screen that is handed it.

        The screen wrapper is not decoration — without `final XAdapter adapter;`
        the runner cannot tell which contract the header describes and refuses,
        which is what the first draft of these fixtures did.
        """
        self.add(f"lib/features/{name}/{name}_adapter.dart", adapter_body)
        self.add(
            f"lib/features/{name}/presentation/pages/{name}_screen.dart",
            header_text
            + f"class {cls}Screen extends StatelessWidget {{\n"
            + f"  const {cls}Screen({{super.key, required this.adapter}});\n"
            + f"  final {cls}Adapter adapter;\n"
            + f"  {screen_body}\n}}\n",
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


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_clean_project_reports_nothing_and_exits_zero(self):
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  const ThingAdapter({required this.title, required this.onTap});
  final String title;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings, [])

    def test_undocumented_field(self):
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final String subtitle;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text('${adapter.title}${adapter.subtitle}',"
                        " onTap: adapter.onTap);\n",
        )
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 1)
        kinds = [(f["kind"], f["name"]) for f in findings]
        self.assertIn(("undocumented_field", "subtitle"), kinds)

    def test_stale_header_entry(self):
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title, adapter.selectedId", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 1)
        self.assertIn(("stale_header_entry", "selectedId"),
                      [(f["kind"], f["name"]) for f in findings])

    def test_dead_adapter_field_reported_against_the_adapter_file(self):
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final bool isLoading;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 1)
        dead = [f for f in findings if f["kind"] == "dead_adapter_field"]
        self.assertEqual([f["name"] for f in dead], ["isLoading"])
        self.assertTrue(dead[0]["file"].endswith("thing_adapter.dart"))

    def test_a_read_through_a_receiver_not_named_adapter_is_not_dead(self):
        # Measured in #104: `CarePlanPdfPayload.fromAdapter(CarePlanAdapter a)`
        # reads `a.patientName`; the audit followed only a receiver literally
        # named `adapter` and advised deleting the field.
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final String patientName;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        p.add("lib/features/thing/pdf/thing_payload.dart", """
class ThingPayload {
  static ThingPayload fromAdapter(ThingAdapter a) => ThingPayload(a.patientName);
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_receiver_the_adapter_cannot_type_refuses(self):
        # Neither a finding nor silence: reads through an untyped receiver are
        # invisible, so "I cannot tell" must not be reported as "read nowhere".
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final String patientName;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        p.add("lib/features/thing/pdf/thing_payload.dart", """
String render() {
  dynamic a = locate<ThingAdapter>();
  return a.patientName;
}
""")
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("untyped receiver", proc.stdout + proc.stderr)
        self.assertEqual(findings, [])

    def test_a_field_used_by_a_sibling_screen_is_neither_dead_nor_undocumented(self):
        # One adapter, two screens, composition forwarding the second's callback.
        # Comparing the whole class against one header would flag a correct one.
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final void Function() onTap;
  final void Function(String id) onPublish;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        p.add("lib/app/composition/thing_composition.dart",
              "Widget wire() => PublishScreen(onPublish: adapter.onPublish);\n")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_widget_in_the_screens_own_tree_counts_as_that_screens_use(self):
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final void Function() onTap;
  final void Function() onSave;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        # A sheet beside the page, not in it — the real project's only caller of
        # onSave lives here.
        p.add("lib/features/thing/presentation/widgets/thing_sheet.dart",
              "Widget s() => Button(onPressed: adapter.onSave);\n")
        proc, findings = p.run()
        self.assertEqual([(f["kind"], f["name"]) for f in findings],
                         [("undocumented_field", "onSave")])
        self.assertEqual(proc.returncode, 1)

    def test_missing_header_is_reported_not_skipped(self):
        p = Project(self.tmp)
        p.feature(
            header_text="",  # no header at all
            adapter_body="class ThingAdapter { final String title; }\n",
            screen_body="Widget b() => Text(adapter.title);\n",
        )
        # A second, headered screen so the corpus is not entirely headerless.
        p.feature("other", cls="Other",
                  header_text=header("adapter.a", None),
                  adapter_body="class OtherAdapter { final String a; }\n",
                  screen_body="Widget b() => Text(adapter.a);")
        proc, findings = p.run()
        self.assertIn("missing_contract_header", [f["kind"] for f in findings])
        self.assertEqual(proc.returncode, 1)

    def test_loose_parameter_screen_is_checked_not_skipped(self):
        p = Project(self.tmp)
        p.add("lib/features/thing/thing_adapter.dart",
              "class ThingAdapter { final String unused; }\n")
        p.add("lib/features/thing/presentation/pages/thing_screen.dart",
              header("plan", None) + """
class ThingScreen extends StatelessWidget {
  const ThingScreen({super.key, required this.plan, required this.onBack});
  final Plan? plan;
  final void Function() onBack;
}
""")
        proc, findings = p.run()
        # `plan` is listed; `onBack` is not; `key` is ignored, not reported.
        self.assertEqual([(f["kind"], f["name"]) for f in findings],
                         [("undocumented_field", "onBack")])
        self.assertEqual(proc.returncode, 1)

    def test_baseline_suppresses_and_then_reports_itself_stale(self):
        p = Project(self.tmp, rules={**CONTRACT_RULES,
                                     "baseline": ".design-suite/baseline.json"})
        p.feature(
            header_text=header("adapter.title", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  final String title;
  final bool isLoading;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text(adapter.title, onTap: adapter.onTap);\n",
        )
        proc, _ = p.run("--baseline-write")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        written = json.loads((self.tmp / ".design-suite/baseline.json").read_text())
        self.assertIn("_readme", written)
        self.assertEqual(len(written["accepted"]), 1)

        # Suppressed, but reported as having no recorded reason.
        proc, findings = p.run()
        self.assertEqual(findings, [])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unjustified", proc.stdout)

        # With a reason, it goes quiet.
        key = next(iter(written["accepted"]))
        (self.tmp / ".design-suite/baseline.json").write_text(json.dumps(
            {"accepted": {key: "wired next sprint, tracked in #123"}}))
        proc, _ = p.run()
        self.assertNotIn("unjustified", proc.stdout)
        self.assertEqual(proc.returncode, 0)

        # Fix the finding; the baseline entry is now an exemption nobody needs.
        p.add("lib/features/thing/thing_adapter.dart", """
class ThingAdapter {
  final String title;
  final void Function() onTap;
}
""")
        proc, _ = p.run()
        self.assertIn("stale baseline", proc.stdout)


class Portability(unittest.TestCase):
    """What a second consumer needed that the first did not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_adapter_declared_inside_the_screen_file_resolves(self):
        # 10 of one project's adapters are declared in the screen that uses
        # them, so a dedicated-file glob alone cannot find them.
        p = Project(self.tmp, rules={
            **CONTRACT_RULES,
            "adapterGlob": ["lib/features/*/*_adapter.dart",
                            "lib/features/*/presentation/pages/*.dart"],
        })
        p.add("lib/features/thing/presentation/pages/thing_screen.dart",
              header("adapter.title", "adapter.onTap()") + """
class ThingScreen extends StatelessWidget {
  final ThingAdapter adapter;
  Widget b() => Text(adapter.title, onTap: adapter.onTap);
}

class ThingAdapter {
  final String title;
  final void Function() onTap;
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_single_glob_string_still_works(self):
        p = Project(self.tmp)  # adapterGlob is a plain string here
        p.feature(header_text=header("adapter.title", None),
                  adapter_body="class ThingAdapter { final String title; }\n",
                  screen_body="Widget b() => Text(adapter.title);")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)

    def test_excluded_files_are_named_in_the_output_not_silently_dropped(self):
        p = Project(self.tmp, rules={
            **CONTRACT_RULES,
            "excludeGlobs": ["lib/features/*/presentation/pages/*_page_wrapper.dart"],
        })
        p.feature(header_text=header("adapter.title", None),
                  adapter_body="class ThingAdapter { final String title; }\n",
                  screen_body="Widget b() => Text(adapter.title);")
        # A route wrapper: in the screens glob, documented as not a screen.
        p.add("lib/features/thing/presentation/pages/thing_page_wrapper.dart",
              "class ThingPageWrapper extends StatelessWidget {}\n")
        proc, findings = p.run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings, [])
        self.assertIn("excluded", proc.stdout)
        self.assertIn("thing_page_wrapper.dart", proc.stdout)

    def test_a_documented_query_method_on_an_adapter_is_not_stale(self):
        # `int totalMinutesToday(String id)` is part of an adapter's surface and
        # its header says so. Counting only fields called it a stale entry.
        p = Project(self.tmp)
        p.feature(
            header_text=header("adapter.totalMinutesToday(id)", "adapter.onTap()"),
            adapter_body="""
class ThingAdapter {
  int totalMinutesToday(String id) => 1;
  final void Function() onTap;
}
""",
            screen_body="Widget b() => Text('${adapter.totalMinutesToday(\"a\")}',"
                        " onTap: adapter.onTap);",
        )
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_widgets_framework_overrides_are_not_its_contract(self):
        # The loose-param branch must not gain `build`: it is an override, not a
        # documented input, and reporting it would flag every screen.
        p = Project(self.tmp)
        p.add("lib/features/thing/thing_adapter.dart",
              "class Unused { final int a; }\n")
        p.add("lib/features/thing/presentation/pages/thing_screen.dart",
              header("plan", None) + """
class ThingScreen extends StatelessWidget {
  const ThingScreen({super.key, required this.plan});
  final Plan? plan;
  Widget build(BuildContext context) { return X(); }
  State createState() { return Y(); }
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_a_screen_taking_an_adapter_and_a_direct_param(self):
        # The header documents both surfaces. Comparing it against the adapter
        # alone called live widget parameters stale; counting them in the
        # dead-member check called them dead, since they are read as bare
        # identifiers and never off the receiver. Both must hold at once.
        p = Project(self.tmp)
        p.add("lib/features/thing/thing_adapter.dart", """
class ThingAdapter {
  final String title;
}
""")
        p.add("lib/features/thing/presentation/pages/thing_screen.dart",
              header("adapter.title, readOnly — hides the FAB", None) + """
class ThingScreen extends StatelessWidget {
  const ThingScreen({super.key, required this.adapter, required this.readOnly});
  final ThingAdapter adapter;
  final bool readOnly;
  Widget b() => Text(adapter.title, hidden: readOnly);
}
""")
        proc, findings = p.run()
        self.assertEqual(findings, [], proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_excluding_everything_refuses(self):
        p = Project(self.tmp, rules={**CONTRACT_RULES,
                                     "excludeGlobs": ["lib/features/*/**/*.dart"]})
        p.feature(header_text=header("adapter.title", None),
                  adapter_body="class ThingAdapter { final String title; }\n",
                  screen_body="Widget b() => Text(adapter.title);")
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
        p.feature(
            header_text=header("adapter.title", None),
            adapter_body="class ThingAdapter { final String title; }\n",
        )
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("INERT", proc.stdout + proc.stderr)

    def test_a_scope_matching_nothing_refuses(self):
        p = Project(self.tmp)
        p.add("lib/x.dart", "final v = 1;\n")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("matched nothing", proc.stdout + proc.stderr)

    def test_an_unresolvable_adapter_class_refuses(self):
        p = Project(self.tmp)
        p.add("lib/features/thing/thing_adapter.dart", "class Unrelated { final int a; }\n")
        p.add("lib/features/thing/presentation/pages/thing_screen.dart",
              header("adapter.title", None) + """
class ThingScreen extends StatelessWidget {
  final ThingAdapter adapter;
}
""")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("Refusing to skip", proc.stdout + proc.stderr)

    def test_missing_receiver_config_refuses(self):
        rules = {k: v for k, v in CONTRACT_RULES.items() if k != "receiverPattern"}
        p = Project(self.tmp, rules=rules)
        p.feature(header_text=header("adapter.title", None),
                  adapter_body="class ThingAdapter { final String title; }\n")
        proc, _ = p.run()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("receiverPattern", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
