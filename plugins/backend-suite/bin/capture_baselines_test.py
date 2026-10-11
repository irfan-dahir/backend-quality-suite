#!/usr/bin/env python3
"""Tests for `capture-baselines.sh`'s handling of refusing audits.

The oracle exited 1 on this very repo because two audits refused (no contrast
pair list, no archRulesFile) and every non-zero exit was an ERROR. A refusal is
the exit-code contract's "I could not look" — a recordable state, not a broken
capture. These tests run the real script against a stub plugin whose
`repo_health.py --list` names four stub audits: clean (0), findings (1),
refusing (2), and crashing (traceback).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "capture-baselines.sh"

AUDITS = {
    "audit_clean": 'print("0 findings")\nraise SystemExit(0)',
    "audit_findings": 'print("1 finding(s)")\nraise SystemExit(1)',
    "audit_refuses": 'print("REFUSED: no archRulesFile")\nraise SystemExit(2)',
    "audit_crash": 'raise RuntimeError("boom")',
}


class CaptureBaselinesTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bin_dir = self.tmp / "plugin" / "bin"
        bin_dir.mkdir(parents=True)
        shutil.copy(SCRIPT, bin_dir / SCRIPT.name)
        self.bin = bin_dir
        self.project = self.tmp / "project"
        (self.project / ".backend-suite").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def stub(self, names):
        rows = "".join(f"{n}\\tlive\\tno\\t-\\tbin/{n}.py\\t{n}\\n" for n in names)
        (self.bin / "repo_health.py").write_text(
            f"import sys\nsys.stdout.write({rows!r}.replace('\\\\t','\\t').replace('\\\\n','\\n'))\n")
        for n in names:
            (self.bin / f"{n}.py").write_text(AUDITS[n] + "\n")

    def run_capture(self, *args):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.project)}
        p = subprocess.run(["bash", str(self.bin / SCRIPT.name), *args],
                           cwd=self.project, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def baseline(self, name):
        return (self.project / ".backend-suite" / "baselines" / f"{name}.txt").read_text()

    def test_refusing_audit_is_recorded_not_an_error(self):
        self.stub(["audit_clean", "audit_findings", "audit_refuses"])
        rc, out = self.run_capture("--update")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("ERROR", out)
        rc, out = self.run_capture()
        self.assertEqual(rc, 0, out)
        self.assertIn("REFUSED  audit_refuses", out)
        self.assertIn("verified nothing", out)

    def test_refused_and_zero_finding_baselines_differ(self):
        self.stub(["audit_clean", "audit_refuses"])
        self.run_capture("--update")
        clean, refused = self.baseline("audit_clean"), self.baseline("audit_refuses")
        self.assertIn("exit: 0", clean)
        self.assertNotIn("REFUSED", clean)
        self.assertIn("exit: 2", refused)
        self.assertIn("state: REFUSED", refused)
        self.assertIn("no archRulesFile", refused)

    def test_audit_flipping_from_clean_to_refused_is_drift(self):
        self.stub(["audit_clean"])
        self.run_capture("--update")
        (self.bin / "audit_clean.py").write_text(AUDITS["audit_refuses"] + "\n")
        rc, out = self.run_capture()
        self.assertEqual(rc, 1, out)
        self.assertIn("DRIFT", out)

    def test_crash_is_still_a_real_error(self):
        self.stub(["audit_clean", "audit_crash"])
        rc, out = self.run_capture("--update")
        self.assertEqual(rc, 1, out)
        self.assertIn("ERROR    audit_crash", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
