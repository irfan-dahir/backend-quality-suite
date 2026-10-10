#!/usr/bin/env python3
"""Re-scoping of the two DISABLED audits (audit_accessibility, audit_copy).

Each fix removes a measured false-positive class; each test plants a true
positive beside it so a fix that silenced everything would fail here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN.parent))

from design_suite.engine.copy import check_microcopy, classify  # noqa: E402
from design_suite.adapters import dart  # noqa: E402
from design_suite.adapters.base import AdapterContext  # noqa: E402
from design_suite.engine.scan import scan_source  # noqa: E402

CTX = AdapterContext(repo=Path("."), profile={}, exceptions={},
                     audit_config={"accessibility_minimums": {"min_text_sp": 12,
                                                              "min_touch_target_dp": 48}})


def kinds(src):
    return sorted(f["kind"] for f in scan_source("a.dart", src, dart.a11y_checks(CTX)))


class IconButtonLabels(unittest.TestCase):
    def test_labelled_by_ancestor_or_icon_is_not_a_finding(self):
        src = ("Widget a() => Tooltip(message: 'Search', child: IconButton(onPressed: f, icon: Icon(Icons.search)));\n"
               "Widget b() => Semantics(label: 'Scan', child: IconButton(onPressed: f, icon: Icon(Icons.qr)));\n"
               "Widget c() => IconButton(onPressed: f, icon: Icon(Icons.eye, semanticLabel: 'Show'));\n"
               "Widget d() => IconButton(onPressed: f, icon: Tooltip(message: 'Add', child: Icon(Icons.add)));\n")
        self.assertEqual(kinds(src), [])

    def test_unlabelled_still_found(self):
        src = ("Widget a() => IconButton(onPressed: f, icon: Icon(Icons.close));\n"
               "Widget b() => Row(children: [IconButton(onPressed: f, icon: Icon(Icons.add))]);\n")
        self.assertEqual(kinds(src), ["icon_button_no_tooltip"] * 2)


class PrintExclusion(unittest.TestCase):
    def run_audit(self, exceptions):
        root = Path(tempfile.mkdtemp(prefix="a11y-"))
        (root / ".design-suite").mkdir()
        (root / ".design-suite/profile.json").write_text(json.dumps({
            "project": {"name": "x"}, "adapters": {"lang": "dart"},
            "source": {"root": "lib", "fileGlob": "**/*.dart"},
            "audits": {"configFile": ".design-suite/c.json", "exceptionsFile": ".design-suite/exceptions.json"}}))
        (root / ".design-suite/c.json").write_text(json.dumps(CTX.audit_config))
        (root / ".design-suite/exceptions.json").write_text(json.dumps(exceptions))
        (root / "pubspec.yaml").write_text("name: x\n")
        (root / "lib").mkdir()
        (root / "lib/print.dart").write_text("import 'package:printlib/widgets.dart' as pw;\n"
                                             "final s = pw.TextStyle(fontSize: 8);\n")
        (root / "lib/screen.dart").write_text("final s = TextStyle(fontSize: 9);\n")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
        r = subprocess.run([sys.executable, str(BIN / "audit_accessibility.py"), "--run-disabled"],
                           cwd=root, env=env, capture_output=True, text=True)
        out = root / ".design-suite/accessibility-findings.json"
        return r, (json.loads(out.read_text()) if out.is_file() else None)

    def test_declared_import_is_set_aside_and_counted_screen_kept(self):
        r, f = self.run_audit({"accessibility": {"excludeFilesImporting": [
            {"import": "package:printlib/", "reason": "print output"}]}})
        self.assertEqual([x["file"] for x in f], ["lib/screen.dart"], r.stderr)
        self.assertIn("set aside 1", r.stdout)

    def test_undeclared_reports_both(self):
        _, f = self.run_audit({})
        self.assertEqual(len(f), 2)

    def test_malformed_declaration_refuses(self):
        r, _ = self.run_audit({"accessibility": {"excludeFilesImporting": [{"import": "x"}]}})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class CopyClassifier(unittest.TestCase):
    def test_keyword_is_not_proof_of_chrome(self):
        body = "Your update is now live. Testers can start today."
        self.assertEqual(classify(body, "message", kind="message"), "content")
        self.assertEqual(classify("Could not load leaderboard.", None, kind="text"), "content")

    def test_declared_chrome_kind_is_microcopy(self):
        self.assertEqual(classify("Save Changes Now Please", "label", kind="label",
                                  chrome_kinds=("label",)), "microcopy")

    def test_fragments_are_not_copy(self):
        self.assertEqual(classify(".", None, kind="text"), "fragment")
        self.assertEqual(classify("// found in the LICENSE file.", None, kind="text"), "fragment")

    def test_true_positives_survive(self):
        self.assertEqual(classify("Save Changes", "label", kind="label"), "microcopy")
        self.assertEqual([i["rule"] for i in check_microcopy("Save Changes")], ["title_case"])
        self.assertEqual([i["rule"] for i in check_microcopy("GAME OVER")], ["all_caps"])

    def test_all_caps_needs_latin_cased_letters(self):
        self.assertEqual(check_microcopy("T+1天到账(免手续费，T为工作日)"), [])
        self.assertEqual(check_microcopy("23.5MB"), [])


if __name__ == "__main__":
    unittest.main()
