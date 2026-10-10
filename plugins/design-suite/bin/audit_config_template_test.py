#!/usr/bin/env python3
"""The scaffolded design-audit config must use the key spellings the code reads.

The template shipped `minTextSizeSp` / `minTouchTargetDp` while
`AdapterContext.minimums()` consumers read `min_text_sp` / `min_touch_target_dp`
(the snake_case every other key in that file uses). A scaffolded project's
accessibility checks therefore omitted both thresholds as "not set" even after
the human filled the values in. This test pins the template to the keys the
adapter source actually looks up, so the two cannot drift apart again.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
TEMPLATE = PLUGIN / "templates" / "dot-design-suite" / "design-audit-config.json.template"
ADAPTERS = PLUGIN / "design_suite" / "adapters"


def keys_read_from_minimums() -> set[str]:
    found: set[str] = set()
    for src in ADAPTERS.glob("*.py"):
        found |= set(re.findall(r'(?:minimums\.get\(|numeric_minimum\(\s*minimums,)\s*"([^"]+)"',
                                src.read_text()))
    return found


class TemplateKeysTest(unittest.TestCase):

    def test_template_minimums_are_the_keys_the_code_reads(self):
        template = json.loads(TEMPLATE.read_text())
        declared = set(template["accessibility_minimums"])
        read = keys_read_from_minimums()
        self.assertTrue(read, "found no minimums.get(...) in adapters — the "
                              "pattern this test relies on moved; fix the test, "
                              "do not let it pass vacuously")
        self.assertEqual(declared, read)

    def test_template_has_no_camel_case_keys(self):
        template = json.loads(TEMPLATE.read_text())
        for key in template["accessibility_minimums"]:
            self.assertRegex(key, r"^[a-z0-9_]+$")


class MinimumValuesTest(unittest.TestCase):
    """An unedited scaffold, and a pre-rename one, must not crash or go quiet."""

    def _checkset(self, minimums):
        import contextlib, io, sys
        sys.path.insert(0, str(PLUGIN))
        from design_suite.adapters import dart
        from design_suite.adapters.base import AdapterContext
        ctx = AdapterContext(repo=Path("."), profile={}, exceptions={},
                             audit_config={"accessibility_minimums": minimums})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cs = dart.a11y_checks(ctx)
        return cs, err.getvalue()

    def test_unedited_template_is_a_named_omission_not_a_crash(self):
        template = json.loads(TEMPLATE.read_text())
        cs, _ = self._checkset(template["accessibility_minimums"])
        kinds = {c.kind for c in cs.checks}
        self.assertNotIn("font_size", kinds)
        self.assertNotIn("small_tap_target", kinds)
        joined = " ".join(cs.omitted)
        self.assertIn("min_text_sp", joined)
        self.assertIn("not a number", joined)
        self.assertIn("min_touch_target_dp", joined)

    def test_old_camel_case_keys_still_work_with_a_warning(self):
        cs, err = self._checkset({"minTextSizeSp": 14, "minTouchTargetDp": 48})
        self.assertEqual(cs.omitted, [])
        kinds = {c.kind for c in cs.checks}
        self.assertIn("font_size", kinds)
        self.assertIn("small_tap_target", kinds)
        self.assertIn("deprecated", err)
        self.assertIn("minTextSizeSp", err)

    def test_new_key_wins_over_old(self):
        import sys
        sys.path.insert(0, str(PLUGIN))
        from design_suite.adapters.base import AdapterContext
        ctx = AdapterContext(repo=Path("."), profile={}, exceptions={},
                             audit_config={"accessibility_minimums":
                                           {"minTextSizeSp": 10, "min_text_sp": 14}})
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ctx.minimums(), {"min_text_sp": 14})


if __name__ == "__main__":
    unittest.main(verbosity=2)
