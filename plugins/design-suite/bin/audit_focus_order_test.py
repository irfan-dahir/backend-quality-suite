#!/usr/bin/env python3
"""Tests for the Dart adapter's focus-order checks (dart.stack_order_findings and
dart.focus_order_checks). Stdlib unittest, matching this project's Python-tooling
convention — no pytest. Fixtures are synthetic snippets, not a real project's
lib/ tree, so these stay stable independent of any consumer app's own findings.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_focus_order_test.py"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_suite.adapters import dart  # noqa: E402


class StackOrderMismatch(unittest.TestCase):
    def test_later_declared_but_visually_earlier_sibling_is_flagged(self):
        source = """
        Stack(
          children: [
            Positioned(top: 100, left: 0, child: TextButton(onPressed: (){}, child: Text('a'))),
            Positioned(top: 0, left: 0, child: ElevatedButton(onPressed: (){}, child: Text('b'))),
          ],
        )
        """
        findings = dart.stack_order_findings(source)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "stack_order_mismatch")

    def test_declaration_order_matching_visual_order_is_clean(self):
        source = """
        Stack(
          children: [
            Positioned(top: 0, left: 0, child: ElevatedButton(onPressed: (){}, child: Text('a'))),
            Positioned(top: 100, left: 0, child: TextButton(onPressed: (){}, child: Text('b'))),
          ],
        )
        """
        self.assertEqual(dart.stack_order_findings(source), [])

    def test_non_focusable_positioned_children_are_ignored(self):
        """A decorative image out of visual order is not a focus-order defect —
        only Positioned blocks containing a configured focusable widget count."""
        source = """
        Stack(
          children: [
            Positioned(top: 100, left: 0, child: Image.asset('a.png')),
            Positioned(top: 0, left: 0, child: Image.asset('b.png')),
          ],
        )
        """
        self.assertEqual(dart.stack_order_findings(source), [])

    def test_positioned_without_top_is_skipped_not_guessed_at(self):
        """Many Positioned widgets only constrain bottom/right. Nothing to
        compare against declaration order, so no finding — not a false one."""
        source = """
        Stack(
          children: [
            Positioned(bottom: 0, left: 0, child: TextButton(onPressed: (){}, child: Text('a'))),
            Positioned(top: 0, left: 0, child: ElevatedButton(onPressed: (){}, child: Text('b'))),
          ],
        )
        """
        self.assertEqual(dart.stack_order_findings(source), [])

    def test_respects_configured_focusable_widget_list(self):
        source = """
        Stack(
          children: [
            Positioned(top: 100, left: 0, child: MyCustomTappable(child: Text('a'))),
            Positioned(top: 0, left: 0, child: ElevatedButton(onPressed: (){}, child: Text('b'))),
          ],
        )
        """
        self.assertEqual(dart.stack_order_findings(source), [])
        self.assertEqual(
            len(dart.stack_order_findings(
                source, focusable_widgets=("MyCustomTappable", "ElevatedButton"))),
            1,
        )


class TraversalOverrideChecks(unittest.TestCase):
    def _fires(self, kind: str, source: str) -> int:
        from design_suite.engine.scan import scan_source
        class Ctx:
            profile = {}
            exceptions = {}
            audit_config = {}
        checkset = dart.focus_order_checks(Ctx())
        findings = scan_source("f.dart", source, checkset)
        return len([f for f in findings if f["kind"] == kind])

    def test_autofocus_true_is_flagged(self):
        self.assertEqual(
            self._fires("autofocus_override", "TextButton(autofocus: true, onPressed: (){})"),
            1,
        )

    def test_autofocus_false_is_not_flagged(self):
        self.assertEqual(
            self._fires("autofocus_override", "TextButton(autofocus: false, onPressed: (){})"),
            0,
        )

    def test_explicit_focus_traversal_order_is_flagged(self):
        self.assertEqual(
            self._fires(
                "explicit_traversal_order",
                "FocusTraversalOrder(order: NumericFocusOrder(1), child: Text('x'))",
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
