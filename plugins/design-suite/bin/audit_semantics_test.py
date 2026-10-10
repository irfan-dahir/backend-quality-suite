#!/usr/bin/env python3
"""Tests for the issue-#128 semantics rules (dart.semantics_findings).

Every rule gets three cases, and the third is the one that matters:
  * a planted violation it MUST catch — proves true-positive capacity, so a rule
    that passes by never firing fails here (the failure that disabled
    audit_accessibility);
  * the issue's named known false positive it must NOT flag;
  * a clean control it must NOT flag.

Synthetic snippets, not a consumer's tree. Stdlib unittest.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_semantics_test.py"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_suite.adapters import dart  # noqa: E402
from design_suite.engine import exceptions as X  # noqa: E402


def kinds(source: str, kind: str) -> list[dict]:
    return [f for f in dart.semantics_findings(source) if f["kind"] == kind]


class Rule1TappableInLabellingSemantics(unittest.TestCase):
    K = "tappable_in_labelling_semantics"

    def test_planted_violation_is_caught_as_advisory(self):
        src = """
        Widget build(BuildContext c) => Semantics(
          label: 'Revenue series',
          selected: active,
          child: InkWell(
            onTap: toggle,
            child: Row(children: [Dot(), Text('Revenue')]),
          ),
        );
        """
        found = kinds(src, self.K)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["line"], 5)
        self.assertEqual(found[0]["severity"], "fyi")  # measured 40% wrong: never gates

    def test_known_false_positive_compound_control_via_merge_semantics(self):
        src = """
        Semantics(
          label: 'Row',
          child: MergeSemantics(
            child: GestureDetector(onTap: f, child: Text('x')),
          ),
        );
        """
        self.assertEqual(kinds(src, self.K), [])

    def test_clean_control_with_exclude_from_semantics(self):
        src = """
        Semantics(
          label: 'Close tour',
          onTap: close,
          child: GestureDetector(onTap: close, excludeFromSemantics: true,
                                 child: ColoredBox(color: c)),
        );
        """
        self.assertEqual(kinds(src, self.K), [])

    def test_descendants_own_label_does_not_make_outer_semantics_labelling(self):
        src = "Semantics(container: true, child: InkWell(onTap: f, child: Text('a')))"
        self.assertEqual(kinds(src, self.K), [])


class Rule2ErrorNotAnnounced(unittest.TestCase):
    K = "error_not_announced"

    def test_planted_violation_is_caught(self):
        src = """
        class DsDateField extends StatelessWidget {
          final String? errorText;
          Widget build(BuildContext c) => Column(children: [
            field,
            if (errorText != null) Text(errorText!, style: errStyle),
          ]);
        }
        """
        found = kinds(src, self.K)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["line"], 6)
        self.assertEqual(found[0]["severity"], "should_fix")

    def test_known_false_positive_delegated_to_input_decoration(self):
        src = """
        class DsTextField extends StatelessWidget {
          final String? errorText;
          Widget build(BuildContext c) =>
              TextField(decoration: InputDecoration(errorText: errorText));
        }
        """
        self.assertEqual(kinds(src, self.K), [])

    def test_clean_control_live_region(self):
        src = """
        class DsSelect extends StatelessWidget {
          final String? errorText;
          Widget build(BuildContext c) => Semantics(
            liveRegion: true,
            child: Text(errorText ?? ''),
          );
        }
        """
        self.assertEqual(kinds(src, self.K), [])

    def test_clean_control_send_announcement(self):
        src = """
        class _S extends State<DsPin> {
          final String? error;
          void didUpdate() { SemanticsService.sendAnnouncement(view, error!, dir); }
          Widget build(BuildContext c) => Text(error!);
        }
        """
        self.assertEqual(kinds(src, self.K), [])


class Rule3SelectionByColourOnly(unittest.TestCase):
    K = "selection_by_colour_only"

    def test_planted_violation_is_caught(self):
        src = """
        Widget build(BuildContext c) => InkWell(
          onTap: onTap,
          child: Container(
            color: selected ? colors.primary : colors.surface,
            child: Text(label),
          ),
        );
        """
        found = kinds(src, self.K)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["line"], 5)

    def test_known_false_positive_selection_published_on_ancestor(self):
        src = """
        Semantics(
          selected: isSelected,
          child: GestureDetector(
            onTap: onTap,
            child: DecoratedBox(decoration: BoxDecoration(
              color: isSelected ? a : b)),
          ),
        );
        """
        self.assertEqual(kinds(src, self.K), [])

    def test_clean_control_colour_not_from_selection(self):
        src = """
        InkWell(onTap: onTap, child: Container(color: colors.surface, child: Text(x)));
        """
        self.assertEqual(kinds(src, self.K), [])


class Rule4ExcludeSemanticsOverMultipleNodes(unittest.TestCase):
    K = "exclude_semantics_over_multiple_nodes"

    def test_planted_violation_is_caught(self):
        src = """
        Semantics(
          label: author,
          excludeSemantics: true,
          child: Row(children: [Text(author), Text(timestamp), Icon(Icons.check)]),
        );
        """
        found = kinds(src, self.K)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["line"], 2)

    def test_known_false_positive_single_text_matching_label(self):
        src = "Semantics(label: title, excludeSemantics: true, child: Text(title))"
        self.assertEqual(kinds(src, self.K), [])

    def test_clean_control_scoped_exclude_semantics_widget(self):
        src = """
        Row(children: [Text(author), ExcludeSemantics(child: Row(children: [
          Icon(Icons.a), Text(decor)]))]);
        """
        self.assertEqual(kinds(src, self.K), [])


class Escapes(unittest.TestCase):
    def test_comments_never_fire(self):
        src = "// Semantics(excludeSemantics: true, child: Row(children: [Text(a), Text(b)]))"
        self.assertEqual(dart.semantics_findings(src), [])

    def test_exceptions_json_category_suppresses_and_counts(self):
        finding = {"file": "lib/chip.dart", "line": 3, "kind": "selection_by_colour_only",
                   "severity": "should_fix", "snippet": "x"}
        raw = {"selection_by_colour_only": {"allowlistFiles": [
            {"path": "lib/chip.dart", "reason": "selection on ancestor"}]}}
        kept, hidden = X.partition([finding], {k: k for k in dart.SEMANTICS_KINDS},
                                   X.exemptions(raw), X.report_anyway(raw))
        self.assertEqual(kept, [])
        self.assertEqual(X.report(hidden)["count"], 1)

    def test_exception_is_scoped_to_its_own_rule(self):
        finding = {"file": "lib/chip.dart", "line": 3, "kind": "error_not_announced",
                   "severity": "should_fix", "snippet": "x"}
        raw = {"selection_by_colour_only": {"allowlistFiles": [{"path": "lib/chip.dart"}]}}
        kept, _ = X.partition([finding], {k: k for k in dart.SEMANTICS_KINDS},
                              X.exemptions(raw), X.report_anyway(raw))
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
