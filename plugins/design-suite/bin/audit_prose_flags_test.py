#!/usr/bin/env python3
"""The parses-nothing rule of audit_prose_flags.py, against synthetic plugins.

Synthetic on purpose: the real defect that motivated the rule
(`/audit-assets` passing `--help` to an argless `export_palette.py`) is being
fixed, and this rule's coverage must not depend on one bug staying unfixed.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Assembled so the path gate does not read a fixture invocation as a real one.
PY = 'python3 "${' + 'CLAUDE_PLUGIN_ROOT}/'
GATE = Path(__file__).resolve().parent / "audit_prose_flags.py"

ARGLESS = ("from pathlib import Path\n"
           "def main():\n    Path(__file__).with_name('SIDE_EFFECT').write_text('x')\n"
           "if __name__ == '__main__':\n    main()\n")
PARSES = ("import argparse\n"
          "ap = argparse.ArgumentParser(); ap.add_argument('--real', action='store_true')\n"
          "ap.parse_args()\n")


def plant(tmp: str, scripts: dict[str, str], invocation: str) -> Path:
    plugin = Path(tmp) / "plugins" / "fake"
    for rel, body in scripts.items():
        p = plugin / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    (plugin / "commands").mkdir(parents=True)
    (plugin / "commands" / "s.md").write_text(
        f"# Skill\n\n```bash\n{invocation}\n```\n")
    return plugin.parent


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATE), "--root", str(root)],
                          capture_output=True, text=True, timeout=300)


class PassesFlagToArglessScript(unittest.TestCase):
    def test_help_to_argless_non_bin_script_is_a_finding_and_never_runs_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plant(tmp, {"engine/export.py": ARGLESS},
                         PY + 'engine/export.py" --help 2>/dev/null || true')
            r = run(root)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("export.py parses no arguments", r.stderr)
            self.assertIn("runs its default behaviour", r.stderr)
            # Static detection: the gate must not itself trigger the side effect.
            self.assertFalse((root / "fake" / "engine" / "SIDE_EFFECT").exists())

    def test_any_flag_to_argless_bin_script_is_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plant(tmp, {"bin/thing.py": ARGLESS},
                         PY + 'bin/thing.py" --check')
            r = run(root)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("thing.py parses no arguments", r.stderr)
            self.assertFalse((root / "fake" / "bin" / "SIDE_EFFECT").exists())

    def test_script_that_parses_its_flag_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plant(tmp, {"bin/thing.py": PARSES},
                         PY + 'bin/thing.py" --real')
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("parses no arguments", r.stderr)

    def test_parsing_delegated_to_a_local_helper_counts_as_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plant(tmp, {"engine/helper.py": "import sys\ndef flags():\n    return sys.argv[1:]\n",
                               "engine/run.py": "from helper import flags\nflags()\n"},
                         PY + 'engine/run.py" --x')
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_unresolvable_import_is_cannot_determine_not_argless_not_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plant(tmp, {"engine/run.py": "import some_thirdparty_pkg_xyz\n"},
                         PY + 'engine/run.py" --x')
            r = run(root)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("cannot determine whether run.py parses arguments", r.stderr)
            self.assertNotIn("parses no arguments", r.stderr)


if __name__ == "__main__":
    unittest.main()
