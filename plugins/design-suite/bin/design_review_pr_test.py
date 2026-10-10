#!/usr/bin/env python3
"""Tests for design_review_pr.py against throwaway git repositories.

What must hold: findings on changed lines come first; findings in untouched
files are counted, never silently dropped; every audit that could not check is
listed; a review in which nothing checked exits 2, not 0; and nothing is ever
posted unless `--post` is passed (proved with a fake `gh` on PATH).

    python3 plugins/design-suite/bin/design_review_pr_test.py
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

import design_review_pr as R  # noqa: E402

GIT = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t",
       "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(tmp: Path) -> Path:
    repo = tmp / "proj"
    (repo / ".design-suite").mkdir(parents=True)
    (repo / ".design-suite/profile.json").write_text("{}\n")
    (repo / "lib").mkdir()
    (repo / "lib/a.dart").write_text("one\ntwo\nthree\nfour\n")
    (repo / "lib/untouched.dart").write_text("x\n")
    (repo / "lib/gone.dart").write_text("bye\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    git(repo, "checkout", "-qb", "feature")
    (repo / "lib/a.dart").write_text("one\nTWO\nthree\nfour\nfive\n")
    (repo / "lib/new.dart").write_text("n1\nn2\n")
    (repo / "lib/gone.dart").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change")
    return repo


def envelopes(directory: Path) -> Path:
    directory.mkdir()
    (directory / "tokens.json").write_text(json.dumps({
        "schemaVersion": 1, "audit": "tokens", "reports": "violations", "scanned": 3,
        "findings": [
            {"audit": "tokens", "category": "color", "severity": "fyi",
             "summary": "ON-LINE", "file": "lib/a.dart", "line": 2},
            {"audit": "tokens", "category": "color", "severity": "should-fix",
             "summary": "SAME-FILE", "file": "lib/a.dart", "line": 4},
            {"audit": "tokens", "category": "color", "severity": "critical",
             "summary": "UNTOUCHED", "file": "lib/untouched.dart", "line": 1},
            {"audit": "tokens", "category": "color", "severity": "critical",
             "summary": "NEW-FILE", "file": "./lib/new.dart", "line": 1}]}))
    (directory / "empty.json").write_text(json.dumps({
        "schemaVersion": 1, "audit": "empty", "reports": "violations", "findings": []}))
    return directory


def cli(*args: str, env: dict | None = None):
    return subprocess.run([sys.executable, str(BIN / "design_review_pr.py"), *args],
                          capture_output=True, text=True, env=env)


class Diff(unittest.TestCase):
    def test_changed_lines_include_new_modified_and_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / "lib/untouched.dart").write_text("x\nuncommitted\n")
            changed = R.changed_lines(repo, "main")
            self.assertEqual(changed["lib/a.dart"], {2, 5})
            self.assertEqual(changed["lib/new.dart"], {1, 2})
            self.assertEqual(changed["lib/untouched.dart"], {2})
            self.assertNotIn("lib/gone.dart", changed)

    def test_project_in_a_subdirectory_of_the_git_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app/src").mkdir(parents=True)
            (root / "app/src/x.ts").write_text("a\n")
            (root / "other.txt").write_text("a\n")
            git(root, "init", "-q", "-b", "main")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "i")
            (root / "app/src/x.ts").write_text("a\nb\n")
            (root / "other.txt").write_text("a\nb\n")
            self.assertEqual(R.changed_lines(root / "app", "main"), {"src/x.ts": {2}})

    def test_bad_base_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            proc = cli("no-such-ref", "--repo", str(repo), "--envelopes", str(repo))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("cannot diff", proc.stderr)


class Review(unittest.TestCase):
    def test_order_counts_and_could_not_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            env_dir = envelopes(Path(tmp) / "env")
            proc = cli("main", "--repo", str(repo), "--envelopes", str(env_dir))
            self.assertEqual(proc.returncode, 1, proc.stderr)
            out = proc.stdout
            on_line = out.index("### Findings on changed lines")
            in_file = out.index("### Elsewhere in changed files")
            couldnt = out.index("### Could not check")
            self.assertLess(on_line, out.index("ON-LINE"))
            self.assertLess(out.index("NEW-FILE"), in_file)
            self.assertLess(out.index("NEW-FILE"), out.index("ON-LINE"),
                            "critical sorts before fyi within a section")
            self.assertTrue(in_file < out.index("SAME-FILE") < couldnt)
            self.assertNotIn("UNTOUCHED", out)
            self.assertIn("1 finding(s) in files this change does not touch", out)
            self.assertIn("**empty** — ran, but no findings and nothing recorded as scanned", out)

    def test_real_audit_end_to_end_findings_in_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / "docs").mkdir()
            (repo / "docs/old.md").write_text("# Old\n\n_Last updated: 2001-01-01_\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "doc")
            proc = cli("main", "--repo", str(repo), "-k", "doc_staleness")
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            self.assertIn("docs/old.md", proc.stdout)
            self.assertFalse((repo / ".design-suite/findings").exists(),
                             "diff-scoped run must not overwrite /design-debt's envelopes")

    def test_only_refusals_is_exit_2_and_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            proc = cli("main", "--repo", str(repo), "-k", "adapter_pattern")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("**audit_adapter_pattern** — refused", proc.stdout)
            self.assertIn("not a clean review", proc.stderr)

    def test_disabled_audit_is_listed_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            proc = cli("main", "--repo", str(repo), "-k", "audit_copy")
            self.assertIn("**audit_copy** — disabled", proc.stdout)


class NeverPostsUnlessAsked(unittest.TestCase):
    def test_gh_only_invoked_with_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = make_repo(tmp)
            env_dir = envelopes(tmp / "env")
            fake = tmp / "fakebin"
            fake.mkdir()
            marker = tmp / "posted.txt"
            gh = fake / "gh"
            gh.write_text(f"#!/bin/sh\necho \"$@\" > {marker}\ncat >> {marker}\n")
            gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
            env = {**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}

            cli("main", "--repo", str(repo), "--envelopes", str(env_dir), env=env)
            self.assertFalse(marker.exists(), "posted without --post")

            proc = cli("main", "--repo", str(repo), "--envelopes", str(env_dir),
                       "--post", "42", env=env)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            posted = marker.read_text()
            self.assertTrue(posted.startswith("pr comment 42 --body-file -"))
            self.assertIn("## Design review vs `main`", posted)


if __name__ == "__main__":
    unittest.main()
