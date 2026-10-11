#!/usr/bin/env python3
"""Where the adapter-backed audits save their raw report.

Re-authored from the purged design-suite version. That version pinned six
audits (adapter-pattern, layer-boundaries, tokens, focus-order, semantics,
accessibility) all defaulting to a top-level `scripts/` or
`<pipelines.tokens>/` directory — one project's layout baked into the
plugin, created outside the reach of the scaffolded .gitignore. Of those
six, one survived the re-domain:

  * audit_layer_boundaries.py — defaults to
    `.backend-suite/layer-boundaries-findings.json`, the directory the
    scaffolded .gitignore already covers, and this test pins exactly what
    the original did: the default lands there, `--out` still wins, the
    report carries a planted violation (a 0-finding report proves
    nothing), and no `scripts/` directory is ever created.
  * audit_mock_api.py — same mechanics, already pinned in
    `mock_api_drift_test.py` (default `.backend-suite/mock-api-findings.json`,
    `--out` wins, gitignore coverage), so it is not re-tested here.
  * tokens/focus-order/semantics/accessibility/adapter-pattern —
    design-domain audits that were not carried; there is nothing left to
    pin a path for.

The original also swept for the literal `scripts/` in each audit's source.
That sweep is deliberately not ported: the re-domained scripts carry
measured-history notes naming the old location (e.g. "Ported from
`scripts/audit_error_handling.py`"), which stay as history — the
behavioral assertion below (no directory is created on a real run) is the
stronger guard anyway.

Stdlib unittest, synthetic php project in a temp dir — never a real
consumer tree.

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
TEMPLATE = PLUGIN / "templates" / "dot-backend-suite" / "gitignore.template"

PROFILE = {
    "profileVersion": 1,
    "adapters": {"lang": "php"},
    "source": {"root": "app", "fileGlob": "**/*.php"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}
RULES = {
    "layerBoundaries": {
        "rules": [{"label": "app/Http must not reach app/Service",
                   "from": "app/Http",
                   "mustNotImport": ["App\\Service\\"]}],
        "baseline": ".backend-suite/baselines/layer-boundaries.json",
    },
}

LAYER_REPORT = ".backend-suite/layer-boundaries-findings.json"


def _project(root: Path) -> None:
    (root / ".backend-suite").mkdir(parents=True)
    (root / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (root / ".backend-suite" / "arch-rules.json").write_text(json.dumps(RULES))
    (root / ".backend-suite" / "baselines").mkdir()
    (root / ".backend-suite" / "exceptions.json").write_text("{}")
    (root / "composer.json").write_text(
        json.dumps({"autoload": {"psr-4": {"App\\": "app/"}}}))
    (root / "app" / "Service").mkdir(parents=True)
    (root / "app" / "Service" / "Dep.php").write_text(
        "<?php\nnamespace App\\Service;\nclass Dep {}\n")
    (root / "app" / "Http").mkdir(parents=True)
    # A real violation, so the written report is non-trivial.
    (root / "app" / "Http" / "Thing.php").write_text(
        "<?php\nnamespace App\\Http;\nuse App\\Service\\Dep;\nclass Thing {}\n")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run(
        [sys.executable, str(HERE / "audit_layer_boundaries.py"), *args],
        cwd=root, env=env, capture_output=True, text=True)


class LayerBoundariesReportPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _project(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_lands_inside_dot_backend_suite(self):
        proc = _run(self.root)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        report = self.root / LAYER_REPORT
        self.assertTrue(report.is_file(),
                        f"audit did not write {LAYER_REPORT}: {proc.stderr}")
        json.loads(report.read_text())

    def test_out_flag_still_takes_precedence(self):
        proc = _run(self.root, "--out", "elsewhere/report.json")
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        self.assertTrue((self.root / "elsewhere" / "report.json").is_file())
        self.assertFalse((self.root / LAYER_REPORT).exists(),
                         "--out was given but the default was written too")

    def test_report_carries_the_planted_violation(self):
        """A 0-finding report proves nothing — confirm the file is the real one."""
        proc = _run(self.root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        findings = json.loads((self.root / LAYER_REPORT).read_text())
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["file"].endswith("Thing.php"))

    def test_a_plain_run_creates_nothing_outside_the_marker(self):
        # The directory this suite's .gitignore scaffolds is .backend-suite/ —
        # and the raw report must not land inside findings/, where the debt
        # reader picks up envelope files: a raw list and an envelope are
        # different formats and different audiences.
        _run(self.root)
        self.assertFalse((self.root / "scripts").exists(),
                         "a run created a scripts/ directory again")
        self.assertFalse((self.root / ".backend-suite" / "findings").exists(),
                         "the raw report must not land where envelopes are read")

    def test_scaffolded_gitignore_covers_the_report(self):
        lines = {l.strip() for l in TEMPLATE.read_text().splitlines()
                 if l.strip() and not l.lstrip().startswith("#")}
        self.assertIn("layer-boundaries-findings.json", lines)


if __name__ == "__main__":
    unittest.main()
