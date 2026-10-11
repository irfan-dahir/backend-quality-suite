#!/usr/bin/env python3
"""Tests: portable hooks — per-harness adapters, config generation, git fallback.

    python3 plugins/backend-suite/bin/harness_hooks_test.py

Every case runs the real scripts as subprocesses on synthetic payloads in temp
projects. The non-Claude payload shapes used here are this suite's best reading
of UNVERIFIED stdin schemas (see hooks/harness_output.py); what is tested is the
OUTPUT contract each adapter promises, which the research doc does state.

  * each adapter's after-edit and session-start output shape
  * claude without --harness is unchanged (no adapter keys leak in)
  * unknown --harness is a hard error (exit 1), never a silent default
  * session-start writes nothing into the project tree, for every harness
  * file-sink harnesses write only under .backend-suite/hook-reports/ and say the
    model did not see it
  * `hooks --harness X`: preview writes nothing; codex --apply writes and is
    idempotent and merges; unverified harnesses refuse --apply with exit 2
  * `hooks --status` reports NOT WIRED before and WIRED after
  * pre-commit: install / refuse-to-overwrite / uninstall, and exit-2 refusals
    block by default and only warn under --refusals warn
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
HOOKS = PLUGIN / "hooks"
EDIT = HOOKS / "audit_on_edit.py"
START = HOOKS / "session_start_onboarding.py"
CLI = PLUGIN / "bin" / "harness_hooks.py"
INSTALL = PLUGIN / "bin" / "install_precommit_hook.py"
RUNNER = PLUGIN / "bin" / "run_precommit_audits.py"

ENTRY = {"name": "fake-audit", "glob": "lib/*.dart", "wholeRepo": True,
         "command": [sys.executable, "-c", "import sys; print('bad thing'); sys.exit(1)"]}


def snapshot(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for n in dirnames + filenames:
            p = Path(dirpath) / n
            st = p.lstat()
            out[str(p.relative_to(root))] = (st.st_mtime_ns, st.st_size)
    return out


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "BACKEND_SUITE_NO_ONBOARDING")}
    env.update(extra)
    return env


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.proj = self.tmp / "proj"
        (self.proj / "lib").mkdir(parents=True)
        (self.proj / "lib" / "a.dart").write_text("x\n")
        self.state = self.tmp / "state"

    def tearDown(self):
        self._tmp.cleanup()

    def configure(self):
        ds = self.proj / ".backend-suite"
        ds.mkdir(exist_ok=True)
        (ds / "hooks.map.json").write_text(json.dumps({"entries": [ENTRY]}))

    def edit(self, harness, payload, project_env=False):
        args = [sys.executable, str(EDIT)] + (["--harness", harness] if harness else [])
        env = clean_env(BACKEND_SUITE_HOOK_STATE_DIR=str(self.state))
        if project_env:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        return subprocess.run(args, input=json.dumps(payload), capture_output=True,
                              text=True, cwd=self.proj, env=env, timeout=60)

    def start(self, harness, payload=None):
        args = [sys.executable, str(START)] + (["--harness", harness] if harness else [])
        payload = payload if payload is not None else {"cwd": str(self.proj)}
        return subprocess.run(args, input=json.dumps(payload), capture_output=True,
                              text=True, cwd=self.proj, env=clean_env(), timeout=60)


class AfterEditAdapters(Base):
    def file(self):
        return str(self.proj / "lib" / "a.dart")

    def test_claude_default_unchanged(self):
        self.configure()
        r = self.edit(None, {"session_id": "s", "tool_name": "Edit",
                             "tool_input": {"file_path": self.file()}}, project_env=True)
        out = json.loads(r.stdout)
        self.assertEqual(set(out), {"systemMessage"})
        self.assertIn("bad thing", out["systemMessage"])

    def test_claude_explicit_matches_default(self):
        self.configure()
        p = {"session_id": "s", "tool_name": "Edit", "tool_input": {"file_path": self.file()}}
        a = self.edit(None, p, project_env=True).stdout
        b = self.edit("claude", p, project_env=True).stdout
        self.assertEqual(a, b)

    def test_codex_additional_context(self):
        self.configure()
        r = self.edit("codex", {"session_id": "s", "tool_name": "Edit",
                                "tool_input": {"file_path": self.file()}, "cwd": str(self.proj)})
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("bad thing", out["hookSpecificOutput"]["additionalContext"])

    def test_gemini_aftertool_json_only(self):
        self.configure()
        r = self.edit("gemini", {"session_id": "s", "tool_name": "write_file",
                                 "tool_input": {"file_path": self.file()}, "cwd": str(self.proj)})
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)  # stdout must be pure JSON
        out = json.loads(lines[0])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "AfterTool")
        self.assertIn("bad thing", out["hookSpecificOutput"]["additionalContext"])

    def test_vscode_additional_context(self):
        self.configure()
        r = self.edit("vscode", {"tool_name": "editFiles",
                                 "tool_input": {"filePath": self.file()}, "cwd": str(self.proj)})
        out = json.loads(r.stdout)
        self.assertIn("bad thing", out["hookSpecificOutput"]["additionalContext"])

    def test_cursor_snake_case(self):
        self.configure()
        r = self.edit("cursor", {"tool_name": "edit_file", "tool_input": {"path": self.file()},
                                 "workspace_roots": [str(self.proj)]})
        out = json.loads(r.stdout)
        self.assertEqual(set(out), {"additional_context"})
        self.assertIn("bad thing", out["additional_context"])

    def _file_sink(self, harness, payload):
        self.configure()
        r = self.edit(harness, payload)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIn("cannot feed the model", r.stderr)
        self.assertIn("bad thing", r.stderr)
        report = self.proj / ".backend-suite" / "hook-reports" / f"after-edit-{harness}.txt"
        self.assertTrue(report.is_file())
        self.assertIn("bad thing", report.read_text())

    def test_cursor_after_edit_file_sink(self):
        self._file_sink("cursor-after-edit", {"file_path": self.file(),
                                              "workspace_roots": [str(self.proj)]})

    def test_devin_file_sink(self):
        self._file_sink("devin", {"tool_info": {"file_path": self.file()}})

    def test_file_sink_without_backend_suite_writes_nothing(self):
        before = snapshot(self.proj)
        r = self.edit("devin", {"tool_info": {"file_path": self.file()}})
        self.assertEqual(snapshot(self.proj), before)
        self.assertIn("no .backend-suite/", r.stderr)

    def test_unknown_harness_is_hard_error(self):
        for script in (EDIT, START):
            r = subprocess.run([sys.executable, str(script), "--harness", "nope"],
                               input="{}", capture_output=True, text=True,
                               cwd=self.proj, env=clean_env(), timeout=30)
            self.assertEqual(r.returncode, 1, script.name)
            self.assertIn("unknown harness", r.stderr)
            self.assertEqual(r.stdout, "")


class SessionStartAdapters(Base):
    def test_shapes_and_no_writes(self):
        before = snapshot(self.proj)
        shapes = {}
        for h in ("claude", "codex", "vscode", "gemini", "cursor", "devin",
                  "cursor-after-edit", None):
            r = self.start(h)
            self.assertEqual(r.returncode, 0, h)
            shapes[h] = r
        self.assertEqual(snapshot(self.proj), before, "session-start wrote to the tree")
        for h in ("claude", "codex", "vscode", "gemini"):
            out = json.loads(shapes[h].stdout)
            self.assertIn("existing", out["hookSpecificOutput"]["additionalContext"].lower())
        self.assertEqual(shapes[None].stdout, shapes["claude"].stdout)
        cur = json.loads(shapes["cursor"].stdout)
        self.assertEqual(set(cur), {"additional_context"})
        for h in ("devin", "cursor-after-edit"):
            self.assertEqual(shapes[h].stdout, "")
            self.assertIn("NOT told", shapes[h].stderr)

    def test_cursor_workspace_roots(self):
        r = self.start("cursor", {"workspace_roots": [str(self.proj)]})
        self.assertIn("additional_context", json.loads(r.stdout))


class HooksCli(Base):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), "--dir", str(self.proj), *args],
                              capture_output=True, text=True, env=clean_env(), timeout=60)

    def test_preview_writes_nothing(self):
        before = snapshot(self.proj)
        for h in ("claude", "codex", "cursor", "vscode", "gemini", "devin"):
            r = self.cli("--harness", h)
            self.assertEqual(r.returncode, 0, h + r.stderr)
        self.assertEqual(snapshot(self.proj), before)

    def test_unverified_refuse_apply(self):
        before = snapshot(self.proj)
        for h in ("cursor", "vscode", "gemini", "devin"):
            r = self.cli("--harness", h, "--apply")
            self.assertEqual(r.returncode, 2, h)
            self.assertIn("UNVERIFIED", r.stdout)
        self.assertEqual(snapshot(self.proj), before)

    def test_codex_apply_merge_idempotent_and_status(self):
        st = json.loads(self.cli("--status", "--json").stdout)
        self.assertEqual(st["codex"]["afterEdit"], "NOT WIRED")
        self.assertEqual(st["git"]["preCommit"], "NOT WIRED")
        self.assertEqual(st["claude"]["afterEdit"], "UNKNOWN")
        target = self.proj / ".codex" / "hooks.json"
        target.parent.mkdir()
        foreign = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
                   "other": 1}
        target.write_text(json.dumps(foreign))
        r = self.cli("--harness", "codex", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(target.read_text())
        self.assertEqual(data["hooks"]["Stop"], foreign["hooks"]["Stop"])
        self.assertEqual(data["other"], 1)
        cmd = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        self.assertIn("audit_on_edit.py", cmd)
        self.assertIn("--harness codex", cmd)
        first = target.read_text()
        r = self.cli("--harness", "codex", "--apply")
        self.assertIn("already wired", r.stdout)
        self.assertEqual(target.read_text(), first)
        st = json.loads(self.cli("--status", "--json").stdout)
        self.assertEqual(st["codex"], {**st["codex"], "sessionStart": "WIRED",
                                       "afterEdit": "WIRED"})
        self.assertEqual(st["cursor"]["afterEdit"], "NOT WIRED")

    def test_malformed_existing_refused(self):
        target = self.proj / ".codex" / "hooks.json"
        target.parent.mkdir()
        target.write_text("{not json")
        r = self.cli("--harness", "codex", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(target.read_text(), "{not json")

    def test_unknown_harness(self):
        self.assertEqual(self.cli("--harness", "nope").returncode, 2)


class PreCommit(Base):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", str(self.proj)], check=True)
        self.hook = self.proj / ".git" / "hooks" / "pre-commit"

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), "--dir", str(self.proj), "--git",
                               *args], capture_output=True, text=True,
                              env=clean_env(), timeout=60)

    def test_install_uninstall_refuse(self):
        r = self.cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("backend-suite:precommit-hook", self.hook.read_text())
        self.assertNotIn("--refusals", self.hook.read_text())
        self.assertEqual(self.cli("--uninstall").returncode, 0)
        self.assertFalse(self.hook.exists())
        self.hook.parent.mkdir(parents=True, exist_ok=True)
        self.hook.write_text("#!/bin/sh\necho mine\n")
        r = self.cli()
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing to overwrite", r.stderr)
        self.assertEqual(self.hook.read_text(), "#!/bin/sh\necho mine\n")
        self.assertEqual(self.cli("--uninstall").returncode, 0)
        self.assertEqual(self.hook.read_text(), "#!/bin/sh\necho mine\n")

    def test_refusals_warn_baked_in(self):
        self.assertEqual(self.cli("--refusals", "warn").returncode, 0)
        self.assertIn("--refusals warn", self.hook.read_text())

    def _refusing_project(self):
        ds = self.proj / ".backend-suite"
        ds.mkdir()
        entry = {"name": "refuser", "preCommit": True, "wholeRepo": True,
                 "command": [sys.executable, "-c",
                             "import sys; sys.stderr.write('no config'); sys.exit(2)"]}
        (ds / "hooks.map.json").write_text(json.dumps({"entries": [entry]}))
        subprocess.run(["git", "add", "-A"], cwd=self.proj, check=True)

    def run_runner(self, *args):
        return subprocess.run([sys.executable, str(RUNNER), *args], cwd=self.proj,
                              capture_output=True, text=True,
                              env=clean_env(CLAUDE_PROJECT_DIR=str(self.proj)), timeout=60)

    def test_refusal_blocks_by_default(self):
        self._refusing_project()
        r = self.run_runner()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stderr)
        self.assertIn("checked NOTHING", r.stderr)

    def test_refusal_warn_allows_but_is_loud(self):
        self._refusing_project()
        r = self.run_runner("--refusals", "warn")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stderr)
        self.assertIn("NOT blocked", r.stderr)
        self.assertNotIn("all 1 pre-commit gate(s)", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
