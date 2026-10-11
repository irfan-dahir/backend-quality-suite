#!/usr/bin/env python3
"""scan: vendored-directory skips are real, counted, and overridable.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/scan_skip_test.py"

The surviving half of the purged issue #104 regression file
(`scan_skip_and_tsx_cache_test.py`). The tsx span-cache half died with the
tsx adapter — there is no template-span cache left to key by `id()` — but
the skip machinery it sat beside did not: `scan.source_files` is
adapter-independent and every sweep runs through it.

Three properties, each a silent-loss guard:

  * vendored dirs are skipped while an authored dir that merely shares a
    generic name (`src/build/`) is not — and every skip is counted on
    stderr, so "zero findings" is always traceable to what was not looked
    at. `dist` beside a `composer.json` is tool output; `dist` under
    `src/` with no manifest beside it is source;
  * the skip reaches the sweep, not just the file list: a planted
    violation under a skipped dir can never surface in findings;
  * exceptions.json `scanSkipDirs` re-enables a default (`include`) and
    adds project-specific names (`add`), and a project-added name is
    skipped anywhere, not only beside a manifest.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend_suite.adapters import php  # noqa: E402
from backend_suite.adapters.base import AdapterContext  # noqa: E402
from backend_suite.engine import scan  # noqa: E402

GLOBS = ("**/*.php",)

# Every file carries the same planted violation, so findings under a
# scanned dir and findings under a skipped dir are distinguishable only
# by the skip — there is no "the fixture forgot to plant one" escape.
VIOLATION = "<?php\nvar_dump($payload);\n"


class VendoredDirSkip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for d in ("src", "node_modules/pkg", "dist", "vendor/app"):
            (self.tmp / d).mkdir(parents=True)
        for rel in ("src/x.php", "node_modules/pkg/x.php", "dist/x.php",
                    "vendor/app/x.php"):
            (self.tmp / rel).write_text(VIOLATION)
        # The package manifest beside which `dist` and `vendor` are
        # unambiguously tool output (composer.json is in
        # scan.PACKAGE_MANIFESTS).
        (self.tmp / "composer.json").write_text("{}")
        # Authored source in a dir with a generic name: no manifest beside
        # it in src/, so it is scanned rather than skipped.
        (self.tmp / "src/build").mkdir()
        (self.tmp / "src/build/y.php").write_text(VIOLATION)

    def run_scan(self, skip_dirs=None):
        err, skipped = io.StringIO(), []
        with contextlib.redirect_stderr(err):
            files = scan.source_files(self.tmp, GLOBS, skip_dirs, skipped)
        return files, skipped, err.getvalue()

    def rels(self, files):
        return [str(f.relative_to(self.tmp)) for f in files]

    def test_src_found_vendored_not_and_skip_counted(self):
        files, skipped, err = self.run_scan()
        self.assertEqual(self.rels(files), ["src/build/y.php", "src/x.php"])
        self.assertEqual(sorted(p.name for p in skipped),
                         ["dist", "node_modules", "vendor"])
        # The count is printed, never swallowed: a skip that produced no
        # line of stderr would be indistinguishable from a clean sweep.
        self.assertIn("SKIPPED 3", err)

        # The skip reaches the sweep itself: only the two scanned files
        # can contribute, so the three planted violations beside
        # composer.json and under node_modules/vendor never surface.
        ctx = AdapterContext(repo=self.tmp, profile={}, exceptions={})
        with contextlib.redirect_stderr(io.StringIO()):
            findings = scan.scan_tree(self.tmp, self.tmp, php.checks(ctx),
                                      globs=GLOBS)
        self.assertTrue(findings)
        self.assertEqual({f["file"] for f in findings},
                         {"src/build/y.php", "src/x.php"})
        self.assertTrue(all(f["kind"] == "debug_statement" for f in findings),
                        [f["kind"] for f in findings])

    def test_exceptions_override(self):
        # `include` re-enables dist; `add` skips src wholesale. A
        # project-added name is skipped anywhere — no manifest needed.
        eff = scan.skip_dirs_from({"scanSkipDirs": {"include": ["dist"],
                                                    "add": ["src"]}})
        files, skipped, _ = self.run_scan(eff)
        self.assertEqual(self.rels(files), ["dist/x.php"])
        self.assertEqual(sorted(p.name for p in skipped),
                         ["node_modules", "src", "vendor"])


if __name__ == "__main__":
    unittest.main()
