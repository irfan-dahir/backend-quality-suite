#!/usr/bin/env python3
"""Tests for bin/harness.py on synthetic projects (stdlib unittest)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
SCRIPT = BIN / "harness.py"


def run(project, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--project", str(project), *args],
                          capture_output=True, text=True)


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)
        (self.p / "AGENTS.md").write_text("# Ours\n\nuser line above\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_writes_nothing(self):
        before = snapshot(self.p)
        r = run(self.p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would write", r.stdout)
        self.assertEqual(snapshot(self.p), before)

    def test_apply_writes_exactly_previewed(self):
        planned = {l.split()[-1] for l in run(self.p).stdout.splitlines()
                   if l.startswith("would write")}
        self.assertTrue(planned)
        before = snapshot(self.p)
        r = run(self.p, "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = snapshot(self.p)
        changed = {k for k in after if before.get(k) != after[k]}
        self.assertEqual(changed, planned)
        self.assertIn(".agents/skills/survey/SKILL.md", planned)

    def test_user_content_preserved_and_idempotent(self):
        run(self.p, "--apply")
        a = self.p / "AGENTS.md"
        a.write_text(a.read_text() + "\nuser line below\n")
        self.assertEqual(run(self.p, "--check").returncode, 0)
        once = snapshot(self.p)
        r = run(self.p, "--apply")
        self.assertNotIn("wrote", r.stdout)
        self.assertEqual(snapshot(self.p), once)
        text = a.read_text()
        self.assertTrue(text.startswith("# Ours\n\nuser line above\n"))
        self.assertTrue(text.endswith("user line below\n"))
        self.assertEqual(text.count("BEGIN backend-suite"), 1)

    def test_json_other_keys_preserved(self):
        (self.p / ".cursor").mkdir()
        (self.p / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
        (self.p / ".gemini").mkdir()
        (self.p / ".gemini/settings.json").write_text(json.dumps({"context": {"fileName": "GEMINI.md"}, "theme": "t"}))
        run(self.p, "--apply")
        c = json.loads((self.p / ".cursor/mcp.json").read_text())
        self.assertEqual(set(c["mcpServers"]), {"other", "backend-suite"})
        g = json.loads((self.p / ".gemini/settings.json").read_text())
        self.assertEqual(g["context"]["fileName"], ["AGENTS.md", "GEMINI.md"])
        self.assertEqual(g["theme"], "t")

    def test_check_stale_and_cannot_determine(self):
        self.assertEqual(run(self.p, "--check").returncode, 1)
        run(self.p, "--apply")
        self.assertEqual(run(self.p, "--check").returncode, 0)
        s = self.p / ".agents/skills/survey/SKILL.md"
        s.write_text(s.read_text() + "drift\n")
        self.assertEqual(run(self.p, "--check").returncode, 1)
        (self.p / ".vscode/mcp.json").write_text('{ // comment\n "servers": {} }')
        r = run(self.p, "--check")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("CANNOT DETERMINE  .vscode/mcp.json", r.stdout)
        self.assertEqual((self.p / ".vscode/mcp.json").read_text(), '{ // comment\n "servers": {} }')

    def test_handwritten_skill_not_overwritten(self):
        d = self.p / ".agents/skills/survey"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("mine")
        r = run(self.p, "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual((d / "SKILL.md").read_text(), "mine")

    def test_shadowing_warnings(self):
        (self.p / "CLAUDE.md").write_text("# rules\n")
        (self.p / ".cursorrules").write_text("x")
        out = run(self.p).stdout
        self.assertIn("Claude Code: SHADOWED", out)
        self.assertIn("Zed: SHADOWED", out)
        self.assertIn("add a line `@AGENTS.md` to CLAUDE.md", out)
        (self.p / "CLAUDE.md").write_text("# rules\n@AGENTS.md\n")
        self.assertNotIn("Claude Code: SHADOWED", run(self.p).stdout)
        self.assertEqual((self.p / "CLAUDE.md").read_text(), "# rules\n@AGENTS.md\n")

    def test_plugin_root_fully_rewritten_and_explicit_tier(self):
        run(self.p, "--apply")
        skills = list(self.p.glob(".*/skills/*/SKILL.md"))
        self.assertGreater(len(skills), 40)
        for s in skills:
            t = s.read_text()
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", t, s)
        add = (self.p / ".agents/skills/upgrade-apply/SKILL.md").read_text()
        self.assertNotIn("disable-model-invocation", add)
        self.assertIn("only when explicitly asked", add)
        aud = (self.p / ".agents/skills/survey/SKILL.md").read_text()
        self.assertNotIn("only when the user directly asks", aud)

    def test_claude_files_only_with_flag(self):
        out = run(self.p).stdout
        self.assertNotIn(".mcp.json", [l.split()[-1] for l in out.splitlines() if l.startswith("would")])
        self.assertIn("--include-claude", out)
        run(self.p, "--apply")
        self.assertFalse((self.p / ".mcp.json").exists())
        self.assertFalse((self.p / ".claude/skills").exists())
        run(self.p, "--apply", "--include-claude")
        self.assertTrue((self.p / ".mcp.json").is_file())
        self.assertTrue((self.p / ".claude/skills/survey/SKILL.md").is_file())

    def test_mcp_configs_use_cli_not_paths(self):
        run(self.p, "--apply")
        c = json.loads((self.p / ".cursor/mcp.json").read_text())["mcpServers"]["backend-suite"]
        self.assertEqual((c["command"], c["args"]), ("backend-suite", ["mcp"]))
        for f in (".cursor/mcp.json", ".vscode/mcp.json", ".codex/config.toml",
                  ".gemini/settings.json", "opencode.json"):
            self.assertNotIn("audit_server.py", (self.p / f).read_text(), f)

    def test_never_writes_outside_project(self):
        run(self.p, "--apply")
        for f in snapshot(self.p):
            self.assertFalse(f.startswith(".."))
        self.assertFalse((self.p / ".config").exists())


if __name__ == "__main__":
    unittest.main()
