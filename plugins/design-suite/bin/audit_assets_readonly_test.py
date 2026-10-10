#!/usr/bin/env python3
"""/audit-assets must leave the consumer's tree byte-identical — and still catch a stale palette.

Regression for the bug where Step 1 ran `export_palette.py --help` against a
script that read no arguments: the "probe" overwrote `<pipelines.assets>/palette.json`
on every audit, with `2>/dev/null || true` hiding it.

The read-only test executes the skill's own scripted Step 0 and Step 1 blocks,
extracted from commands/audit-assets.md, so a future edit that reintroduces a
writing step fails here. It is paired with tests proving check G's input still
distinguishes stale from current — a fix that stops writing by checking nothing
would pass the first test and fail these.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / "commands" / "audit-assets.md"
EXPORT = PLUGIN / "design_suite" / "engine" / "assets" / "export_palette.py"

FRESH = json.dumps({"primary": "#112233", "surface": "#ffffff"}, indent=2) + "\n"
STALE = json.dumps({"primary": "#999999", "surface": "#ffffff"}, indent=2) + "\n"


def make_project(base: Path, palette: str | None) -> Path:
    root = base / "proj"
    checkout = base / "ds"
    (checkout / "packages" / "ds_flutter").mkdir(parents=True)
    (checkout / "dist" / "palette").mkdir(parents=True)
    (checkout / "dist" / "palette" / "acme.light.json").write_text(FRESH)
    (root / ".dart_tool").mkdir(parents=True)
    (root / ".dart_tool" / "package_config.json").write_text(json.dumps({
        "packages": [{"name": "ds_flutter",
                      "rootUri": "file://" + str(checkout / "packages" / "ds_flutter")}]}))
    (root / ".design-suite").mkdir()
    (root / ".design-suite" / "profile.json").write_text(json.dumps({
        "project": {"name": "fixture"},
        "pipelines": {"assets": "asset_pipeline"},
        "tokens": {"source": {"kind": "package", "package": "ds_flutter",
                              "resolveVia": ".dart_tool/package_config.json"}},
        "assets": {"root": "assets/images", "palette": {"brand": "acme", "mode": "light"}},
    }))
    (root / "asset_pipeline" / "sources").mkdir(parents=True)
    (root / "asset_pipeline" / "manifest.json").write_text('{"assets": []}\n')
    (root / "assets" / "images").mkdir(parents=True)
    (root / "assets" / "images" / ".gitkeep").write_text("")
    if palette is not None:
        (root / "asset_pipeline" / "palette.json").write_text(palette)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
                    "-qm", "fixture"], cwd=root, check=True)
    return root


def snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if ".git" in p.relative_to(root).parts:
            continue
        out[str(p.relative_to(root))] = (
            "dir" if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def scripted_steps() -> str:
    """Step 0's command plus every fenced bash block in Step 1, verbatim."""
    text = SKILL.read_text()
    step0 = text.split("## Step 0", 1)[1].split("## Step 1", 1)[0]
    step1 = text.split("## Step 1", 1)[1].split("## Step 2", 1)[0]
    cmds = re.findall(r"`(python3 [^`]*pipeline\.py\" check)`", step0)
    blocks = re.findall(r"```bash\n(.*?)```", step1, re.S)
    assert cmds and blocks, "could not extract /audit-assets scripted steps"
    return "\n".join(cmds + blocks)


def run(args, root):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    return subprocess.run(args, cwd=root, env=env, capture_output=True, text=True)


class AuditAssetsReadOnly(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="audit-assets-ro-")
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scripted_steps_leave_tree_byte_identical(self):
        root = make_project(self.base, STALE)  # stale: the old bug would overwrite it
        before = snapshot(root)
        proc = run(["bash", "-c", scripted_steps()], root)
        self.assertIn("export_palette --check exit: 1", proc.stdout,
                      "Step 1 must actually run the palette comparison:\n"
                      + proc.stdout + proc.stderr)
        self.assertEqual(snapshot(root), before,
                         "/audit-assets Steps 0-1 modified the project tree")
        self.assertEqual((root / "asset_pipeline" / "palette.json").read_text(), STALE)

    def test_check_detects_stale_palette(self):
        root = make_project(self.base, STALE)
        proc = run([sys.executable, str(EXPORT), "--check"], root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("STALE", proc.stdout)

    def test_check_detects_missing_palette(self):
        root = make_project(self.base, None)
        proc = run([sys.executable, str(EXPORT), "--check"], root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((root / "asset_pipeline" / "palette.json").exists())

    def test_check_passes_current_palette(self):
        root = make_project(self.base, FRESH)
        proc = run([sys.executable, str(EXPORT), "--check"], root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_check_refuses_with_2_when_it_cannot_compare(self):
        root = make_project(self.base, FRESH)
        (root / ".dart_tool" / "package_config.json").unlink()
        proc = run([sys.executable, str(EXPORT), "--check"], root)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("REFUSING", proc.stderr)

    def test_out_writes_only_the_named_path(self):
        root = make_project(self.base, STALE)
        before = snapshot(root)
        dest = self.base / "fresh.json"
        proc = run([sys.executable, str(EXPORT), "--out", str(dest)], root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(dest.read_text(), FRESH)
        self.assertEqual(snapshot(root), before)

    def test_default_mode_still_refreshes(self):
        root = make_project(self.base, STALE)
        proc = run([sys.executable, str(EXPORT)], root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((root / "asset_pipeline" / "palette.json").read_text(), FRESH)


if __name__ == "__main__":
    unittest.main()
