#!/usr/bin/env python3
"""Tests for hooks/session_start_onboarding.py.

What these prove: classification of each state, that the hook writes nothing on
any path (tree snapshot before/after, including mtimes), that a configured or
declined project gets no prompt, and that a crash inside the hook still exits 0
with empty stdout. What they cannot prove: how Claude Code itself loads this
hook's output at a real session start — that is only observable inside Claude Code.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN = Path(__file__).resolve().parent.parent
HOOK = PLUGIN / "hooks" / "session_start_onboarding.py"

spec = importlib.util.spec_from_file_location("ssonb", HOOK)
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def snapshot(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for n in dirnames + filenames:
            p = Path(dirpath) / n
            st = p.lstat()
            out[str(p.relative_to(root))] = (st.st_mtime_ns, st.st_size)
    return out


def run_hook(root: Path | None, extra_env: dict | None = None, stdin: str | None = None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", H.DECLINE_ENV)}
    if root is not None:
        env["CLAUDE_PROJECT_DIR"] = str(root)
    env.update(extra_env or {})
    if stdin is None:
        stdin = json.dumps({"hook_event_name": "SessionStart", "source": "startup",
                            "cwd": str(root) if root else ""})
    return subprocess.run([sys.executable, str(HOOK)], input=stdin, env=env,
                          capture_output=True, text=True, timeout=30)


class Fixtures(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "proj"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, kind: str) -> Path:
        r = self.root
        if kind == "new":
            (r / "README.md").write_text("# hi\n")
            (r / ".git").mkdir()
            (r / ".git" / "x.py").write_text("")  # inside a skipped dir: not source
            (r / "node_modules").mkdir()
            (r / "node_modules" / "a.js").write_text("")
        elif kind in ("existing", "configured", "partial", "declined"):
            (r / "lib").mkdir()
            (r / "lib" / "main.dart").write_text("void main() {}\n")
            if kind == "configured":
                (r / ".backend-suite").mkdir()
                (r / ".backend-suite" / "profile.json").write_text("{}")
            if kind == "partial":
                (r / ".backend-suite").mkdir()
            if kind == "declined":
                (r / H.DECLINE_FILE).write_text("")
        return r


class Classification(Fixtures):
    def test_states(self):
        for kind in ("new", "existing", "configured", "partial", "declined"):
            with self.subTest(kind=kind):
                self.tearDown(); self.setUp()
                state, _ = H.classify(self.make(kind), env={})
                self.assertEqual(state, kind)

    def test_empty_dir_is_new(self):
        self.assertEqual(H.classify(self.root, env={})[0], "new")

    def test_env_decline(self):
        self.make("existing")
        self.assertEqual(H.classify(self.root, env={H.DECLINE_ENV: "1"})[0], "declined")

    def test_unclassifiable_paths(self):
        self.assertEqual(H.classify(None, env={})[0], "unclassifiable")
        self.assertEqual(H.classify(self.root / "nope", env={})[0], "unclassifiable")
        self.assertEqual(H.classify(Path.home(), env={})[0], "unclassifiable")
        self.assertEqual(H.classify(Path("/"), env={})[0], "unclassifiable")

    def test_budget_exhausted_is_unclassifiable_not_new(self):
        for i in range(30):
            (self.root / f"f{i}.txt").write_text("")
        with mock.patch.object(H, "MAX_ENTRIES", 5):
            state, reason = H.classify(self.root, env={})
        self.assertEqual(state, "unclassifiable")
        self.assertIn("budget", reason)


class WritesNothing(Fixtures):
    def test_every_path_leaves_tree_identical(self):
        for kind in ("new", "existing", "configured", "partial", "declined", "empty"):
            with self.subTest(kind=kind):
                self.tearDown(); self.setUp()
                root = self.make(kind) if kind != "empty" else self.root
                parent = root.parent
                before = snapshot(parent)
                r = run_hook(root)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(snapshot(parent), before)
                self.assertFalse((root / ".backend-suite" / "survey.json").exists())


class Output(Fixtures):
    def context(self, r) -> str:
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_configured_and_declined_are_silent(self):
        for kind in ("configured", "declined"):
            with self.subTest(kind=kind):
                self.tearDown(); self.setUp()
                r = run_hook(self.make(kind))
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_new_offers_onboard_new_client(self):
        r = run_hook(self.make("new"))
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("/onboard-new-client", out["additionalContext"])
        self.assertNotIn("understand-existing-project", out["additionalContext"])

    def test_existing_offers_chain_and_never_claims_writes(self):
        ctx = self.context(run_hook(self.make("existing")))
        self.assertIn("/run-chain understand-existing-project", ctx)
        self.assertIn("Nothing has been written", ctx)
        self.assertIn("without a yes", ctx)

    def test_unclassifiable_says_so(self):
        ctx = self.context(run_hook(self.root / "missing"))
        self.assertIn("could not tell", ctx)
        self.assertNotIn("/onboard-new-client", ctx)

    def test_cwd_from_payload_when_env_absent(self):
        self.make("existing")
        r = run_hook(None, stdin=json.dumps({"cwd": str(self.root)}))
        self.assertIn("understand-existing-project", self.context(r))


class NeverBreaksSession(Fixtures):
    def test_garbage_stdin(self):
        r = run_hook(self.make("configured"), stdin="{not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_internal_crash_exits_zero_with_empty_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(H, "classify", side_effect=RuntimeError("boom")), \
             mock.patch.object(sys, "stdin", io.StringIO("{}")), \
             mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            rc = H.main()
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("boom", err.getvalue())


class Registration(unittest.TestCase):
    def test_registered_as_session_start(self):
        cfg = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
        cmds = [h["command"] for m in cfg["hooks"].get("SessionStart", [])
                for h in m["hooks"]]
        self.assertTrue(any("session_start_onboarding.py" in c for c in cmds))

    def test_chain_names_only_real_skills(self):
        chain = json.loads((PLUGIN / "templates" / "chains" /
                            "understand-existing-project.json").read_text())
        skills = {p.stem for p in (PLUGIN / "commands").glob("*.md")}
        for step in chain["steps"]:
            self.assertIn(step["skill"], skills)
            if step.get("checkpoint", True) is False:
                self.assertIn(step["skill"], {"repo-health"})


if __name__ == "__main__":
    unittest.main()
