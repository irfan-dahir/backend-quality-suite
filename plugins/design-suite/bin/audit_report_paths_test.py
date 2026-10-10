#!/usr/bin/env python3
"""Where /audit-adapter-pattern and /audit-layer-boundaries save their raw report.

Both used to default to a top-level `scripts/` directory — one project's layout
baked into the universal plugin, which created that directory on any project
that lacked it, outside the reach of the .gitignore bin/init.py scaffolds. The
default now lives inside the project's `.design-suite/` directory, where that
scaffolded .gitignore covers it. These tests pin three things: the default lands
there, `--out` still wins, and no `scripts/` literal creeps back into either
script.

Stdlib unittest, synthetic project in a temp dir — never a real consumer tree.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_report_paths_test.py"
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
TEMPLATE = PLUGIN / "templates" / "dot-design-suite" / "gitignore.template"

PROFILE = {
    "profileVersion": 1,
    "adapters": {"lang": "dart"},
    "source": {"root": "lib", "fileGlob": "**/*.dart"},
    "audits": {"archRulesFile": ".design-suite/arch-rules.json"},
}
RULES = {
    "layerBoundaries": {
        "rules": [{"from": "lib/shared", "mustNotImport": ["lib/features"]}],
        "baseline": ".design-suite/baselines/layer_boundaries.txt",
    },
    "adapterPattern": {
        "screensDir": "lib/features",
        "bannedImports": [{"label": "bloc", "pattern": "package:flutter_bloc/"}],
    },
}

AUDITS = {
    # script -> report file name inside .design-suite/
    "audit_adapter_pattern.py": "adapter-pattern-findings.json",
    "audit_layer_boundaries.py": "layer-boundaries-findings.json",
}


def _project(root: Path) -> None:
    (root / ".design-suite" / "baselines").mkdir(parents=True)
    (root / ".design-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (root / ".design-suite" / "arch-rules.json").write_text(json.dumps(RULES))
    (root / ".design-suite" / "baselines" / "layer_boundaries.txt").write_text("")
    (root / "pubspec.yaml").write_text("name: synthetic_app\n")
    page = root / "lib" / "features" / "home" / "presentation" / "pages"
    page.mkdir(parents=True)
    # A real violation for the adapter audit, so a written report is non-trivial.
    (page / "home_page.dart").write_text("import 'package:flutter_bloc/flutter_bloc.dart';\n")
    shared = root / "lib" / "shared"
    shared.mkdir(parents=True)
    (shared / "button.dart").write_text("import 'package:flutter/material.dart';\n")


def _run(root: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(HERE / script), *args],
                          cwd=root, env=env, capture_output=True, text=True)


class ReportPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _project(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_lands_inside_dot_design_suite(self):
        for script, name in AUDITS.items():
            with self.subTest(script=script):
                proc = _run(self.root, script)
                self.assertIn(proc.returncode, (0, 1), proc.stderr)
                report = self.root / ".design-suite" / name
                self.assertTrue(report.is_file(), f"{script} did not write {report}")
                json.loads(report.read_text())
                self.assertFalse((self.root / "scripts").exists(),
                                 f"{script} created a scripts/ directory")

    def test_out_flag_still_takes_precedence(self):
        for script, name in AUDITS.items():
            with self.subTest(script=script):
                proc = _run(self.root, script, "--out", "elsewhere/report.json")
                self.assertIn(proc.returncode, (0, 1), proc.stderr)
                self.assertTrue((self.root / "elsewhere" / "report.json").is_file())
                self.assertFalse((self.root / ".design-suite" / name).exists(),
                                 "--out was given but the default was written too")

    def test_adapter_report_carries_the_planted_violation(self):
        """A 0-finding report proves nothing — confirm the file is the real one."""
        _run(self.root, "audit_adapter_pattern.py")
        findings = json.loads(
            (self.root / ".design-suite" / AUDITS["audit_adapter_pattern.py"]).read_text())
        self.assertEqual(len(findings), 1)

    def test_no_scripts_literal_in_either_audit(self):
        for script in AUDITS:
            with self.subTest(script=script):
                self.assertNotIn("scripts/", (HERE / script).read_text())

    def test_scaffolded_gitignore_covers_both_reports(self):
        lines = {l.strip() for l in TEMPLATE.read_text().splitlines()
                 if l.strip() and not l.lstrip().startswith("#")}
        for name in AUDITS.values():
            self.assertIn(name, lines)


class TokensReportPath(unittest.TestCase):
    """/audit-tokens used to default to `<pipelines.tokens>/findings.json` at the
    project root — outside `.design-suite/`, unreachable by its .gitignore, and
    quoting source lines. Pinned: the default lands in `.design-suite/`, a
    declared `pipelines.tokens` does not pull it back out, and the report is the
    real one (a planted literal is in it)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".design-suite").mkdir()
        (self.root / ".design-suite" / "profile.json").write_text(json.dumps(
            {**PROFILE, "pipelines": {"tokens": "token_pipeline"}}))
        (self.root / "lib").mkdir()
        (self.root / "lib" / "a.dart").write_text("final c = Color(0xFF112233);\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_is_inside_dot_design_suite_even_with_pipelines_tokens(self):
        proc = _run(self.root, "audit_tokens.py")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        report = self.root / ".design-suite" / "tokens-findings.json"
        self.assertTrue(report.is_file(), proc.stdout + proc.stderr)
        self.assertEqual(len(json.loads(report.read_text())), 1)
        self.assertFalse((self.root / "token_pipeline").exists(),
                         "wrote outside .design-suite/ again")
        self.assertFalse((self.root / ".design-suite" / "findings").exists(),
                         "the raw list must not land where /design-debt reads envelopes")

    def test_out_still_wins(self):
        proc = _run(self.root, "audit_tokens.py", "--out", "elsewhere/t.json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertTrue((self.root / "elsewhere" / "t.json").is_file())
        self.assertFalse((self.root / ".design-suite" / "tokens-findings.json").exists())

    def test_scaffolded_gitignore_covers_it(self):
        lines = {l.strip() for l in TEMPLATE.read_text().splitlines()
                 if l.strip() and not l.lstrip().startswith("#")}
        self.assertIn("tokens-findings.json", lines)


class PipelineReportPaths(unittest.TestCase):
    """/audit-focus-order, /audit-semantics and /audit-accessibility used to
    default to `<pipelines.tokens>/*_findings.json` at the project root — outside
    `.design-suite/`, unreachable by its .gitignore, and quoting source. Pinned
    per audit: a planted finding lands in the new path, nothing is written at
    the old one, and `--out` still wins."""

    # script -> (extra args, new name in .design-suite/, old name under pipelines.tokens, planted source)
    CASES = {
        "audit_focus_order.py": ((), "focus-order-findings.json", "focus_order_findings.json",
                                 "Widget b() => TextField(autofocus: true);\n"),
        "audit_semantics.py": ((), "semantics-findings.json", "semantics_findings.json",
                               "Widget b() => Semantics(excludeSemantics: true, "
                               "child: Row(children: [Text('a'), Text('b')]));\n"),
        "audit_accessibility.py": (("--run-disabled",), "accessibility-findings.json",
                                   "a11y_findings.json",
                                   "Widget b() => IconButton(onPressed: f, icon: Icon(Icons.add));\n"),
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".design-suite").mkdir()
        (self.root / ".design-suite" / "profile.json").write_text(json.dumps(
            {**PROFILE, "pipelines": {"tokens": "token_pipeline"},
             "audits": {**PROFILE["audits"], "configFile": ".design-suite/audit-config.json"}}))
        # The accessibility audit refuses (exit 2) without its minimums.
        (self.root / ".design-suite" / "audit-config.json").write_text(json.dumps(
            {"accessibility_minimums": {"min_text_sp": 12, "min_touch_target_dp": 48}}))
        (self.root / "pubspec.yaml").write_text("name: synthetic_app\n")
        (self.root / "lib").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _plant(self, src):
        (self.root / "lib" / "a.dart").write_text(src)

    def test_planted_finding_lands_in_new_path_and_nothing_at_old(self):
        for script, (extra, new, old, src) in self.CASES.items():
            with self.subTest(script=script):
                self._plant(src)
                proc = _run(self.root, script, *extra)
                self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
                report = self.root / ".design-suite" / new
                self.assertTrue(report.is_file(), proc.stdout + proc.stderr)
                self.assertGreaterEqual(len(json.loads(report.read_text())), 1,
                                        f"{script}: planted finding missing — a 0-finding "
                                        "report proves nothing")
                self.assertFalse((self.root / "token_pipeline" / old).exists())
                self.assertFalse((self.root / "token_pipeline").exists(),
                                 "wrote outside .design-suite/ again")
                self.assertFalse((self.root / ".design-suite" / "findings").exists())

    def test_out_still_wins(self):
        for script, (extra, new, _old, src) in self.CASES.items():
            with self.subTest(script=script):
                self._plant(src)
                proc = _run(self.root, script, *extra, "--out", f"elsewhere/{new}")
                self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
                self.assertTrue((self.root / "elsewhere" / new).is_file())
                self.assertFalse((self.root / ".design-suite" / new).exists())

    def test_scaffolded_gitignore_covers_them(self):
        lines = {l.strip() for l in TEMPLATE.read_text().splitlines()
                 if l.strip() and not l.lstrip().startswith("#")}
        for _e, new, _o, _s in self.CASES.values():
            self.assertIn(new, lines)


if __name__ == "__main__":
    unittest.main()
