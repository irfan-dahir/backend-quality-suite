#!/usr/bin/env python3
"""Regression tests for issue #104's two silent-loss defects.

1. tsx.py cached template spans by id(source). CPython reuses an id once the
   string is freed, so a later file inherited an earlier file's spans and lost
   its findings. The test forces id reuse and asserts the later file's finding
   survives.
2. scan.source_files walked node_modules/, dist/ etc. Vendored dirs are now
   skipped by default, and every skip is reported, never silent.

Stdlib-only (unittest).
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_suite.adapters import tsx  # noqa: E402
from design_suite.adapters.base import AdapterContext  # noqa: E402
from design_suite.engine import scan  # noqa: E402

# Same length on purpose: equal-size allocations are what CPython recycles.
# In A the whole literal sits inside a styled template; in B it is a bare
# inline-style violation at the same offset.
A = 'const X = styled.div`\n  color: "#ff0000";\n`;'
B = 'const Y = {          \n  color: "#ff0000"  };'
assert len(A) == len(B)


class TsxSpanCacheIdReuse(unittest.TestCase):
    def test_later_file_with_reused_id_keeps_its_findings(self):
        ctx = AdapterContext(repo=Path("."), profile={}, exceptions={})
        checks = tsx.checks(ctx)
        expected = len(scan.scan_source("b.tsx", "".join(list(B)), tsx.checks(ctx)))
        self.assertGreater(expected, 0, "fixture B must produce a finding on a fresh cache")

        # Scan A, free it, then build B until it lands on A's old id.
        # On the old id-keyed cache this loop reliably lands B on A's freed id
        # (CPython recycles equal-size allocations). With the fix the cache
        # holds A alive, reuse cannot happen, and B is scanned fresh.
        for _ in range(2000):
            a = "".join(list(A))
            a_id = id(a)
            scan.scan_source("a.tsx", a, checks)
            del a
            b = "".join(list(B))
            if id(b) == a_id:
                break
        got = scan.scan_source("b.tsx", b, checks)
        self.assertEqual(len(got), expected,
                         "file B reused file A's id and lost its findings to a stale span cache")


class TsxHtmlEntityIsNotAColour(unittest.TestCase):
    """`&#8595;` in JSX text is a character reference, not hex (issue #104)."""

    def test_entity_skipped_adjacent_hex_still_found(self):
        ctx = AdapterContext(repo=Path("."), profile={}, exceptions={})
        src = "const a = <i>&#8595;</i>;\nconst b = { color: '#8595' };\n"
        found = scan.scan_source("a.tsx", src, tsx.checks(ctx))
        self.assertEqual([(f["line"], f["kind"]) for f in found], [(2, "color")])


class VendoredDirSkip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for d in ("src", "node_modules/pkg", "dist"):
            (self.tmp / d).mkdir(parents=True)
            (self.tmp / d / "x.tsx").write_text('const s = { color: "#ff0000" };\n')
        (self.tmp / "package.json").write_text("{}")
        # Authored source that happens to be named `build` (vitepress has one).
        (self.tmp / "src" / "build").mkdir()
        (self.tmp / "src" / "build" / "y.tsx").write_text('const s = { color: "#ff0000" };\n')

    def run_scan(self, skip_dirs=None):
        err, skipped = io.StringIO(), []
        with contextlib.redirect_stderr(err):
            files = scan.source_files(self.tmp, ("**/*.tsx",), skip_dirs, skipped)
        return files, skipped, err.getvalue()

    def test_src_found_vendored_not_and_skip_counted(self):
        files, skipped, err = self.run_scan()
        rels = [str(f.relative_to(self.tmp)) for f in files]
        self.assertEqual(rels, ["src/build/y.tsx", "src/x.tsx"])
        self.assertEqual(sorted(p.name for p in skipped), ["dist", "node_modules"])
        self.assertIn("SKIPPED 2", err)
        ctx = AdapterContext(repo=self.tmp, profile={}, exceptions={})
        with contextlib.redirect_stderr(io.StringIO()):
            findings = scan.scan_tree(self.tmp, self.tmp, tsx.checks(ctx), globs=("**/*.tsx",))
        self.assertTrue(findings)
        self.assertEqual({f["file"] for f in findings}, {"src/build/y.tsx", "src/x.tsx"})

    def test_exceptions_override(self):
        eff = scan.skip_dirs_from({"scanSkipDirs": {"include": ["dist"], "add": ["src"]}})
        files, skipped, _ = self.run_scan(eff)
        self.assertEqual([str(f.relative_to(self.tmp)) for f in files], ["dist/x.tsx"])  # src (incl. src/build) skipped via `add`
        self.assertEqual(sorted(p.name for p in skipped), ["node_modules", "src"])


if __name__ == "__main__":
    unittest.main()
