#!/usr/bin/env python3
"""Tests for the Dart adapter's reduced-motion wiring check. Stdlib-only
(unittest), matching this project's Python-tooling convention — no pytest.
Fixtures are synthetic snippets, not a live lib/ tree, so these stay stable as
real findings get fixed out from under them.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reduced_motion_dart_test.py"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_suite.adapters import dart  # noqa: E402
from design_suite.adapters.base import AdapterContext  # noqa: E402
from design_suite.engine.scan import scan_source  # noqa: E402


def _ctx(animated_widgets) -> AdapterContext:
    audit_config = {}
    if animated_widgets is not None:
        audit_config = {"token_categories": {"motion": {"animated_widgets": animated_widgets}}}
    return AdapterContext(repo=Path("."), profile={}, exceptions={}, audit_config=audit_config)


WIRED = """
class _WiredState extends State<_Wired> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    _controller = AnimationController(
      duration: reduceMotion ? Duration.zero : const Duration(milliseconds: 300),
      vsync: this,
    );
  }
}
"""

UNWIRED = """
class _UnwiredState extends State<_Unwired> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _controller.forward();
  }
}
"""


class ReducedMotionOmittedWithoutConfig(unittest.TestCase):
    def test_missing_key_is_omitted_not_clean(self):
        checks = dart.reduced_motion_checks(_ctx(None))
        self.assertEqual(len(checks), 0)
        self.assertTrue(checks.omitted, "missing config must refuse, not report zero findings")

    def test_empty_list_is_omitted_not_clean(self):
        checks = dart.reduced_motion_checks(_ctx([]))
        self.assertEqual(len(checks), 0)
        self.assertTrue(checks.omitted)


class ReducedMotionWiring(unittest.TestCase):
    def setUp(self):
        self.checks = dart.reduced_motion_checks(_ctx(["AnimationController"]))
        self.assertEqual(len(self.checks), 1, "config-driven check should build with a real list")

    def test_wired_animation_is_clean(self):
        findings = scan_source("wired.dart", WIRED, self.checks)
        self.assertEqual(findings, [])

    def test_unwired_animation_is_flagged(self):
        # Two matches fire — the field declaration and the instantiation, both
        # named `AnimationController` — and both are legitimately unwired.
        findings = scan_source("unwired.dart", UNWIRED, self.checks)
        self.assertTrue(findings)
        self.assertTrue(all(f["kind"] == "reduced_motion_unwired" for f in findings))

    def test_only_configured_names_are_treated_as_animated(self):
        # A widget name not in the config's animated_widgets list is invisible
        # to this check, even if it obviously animates something — the "which
        # components count as animated" list is config's call, not a guess.
        checks = dart.reduced_motion_checks(_ctx(["SlideTransition"]))
        findings = scan_source("unwired.dart", UNWIRED, checks)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
