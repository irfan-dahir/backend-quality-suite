#!/usr/bin/env python3
"""Tests for mcp/onboarding_tools.py, driven over stdio JSON-RPC.

Each test spawns `mcp/audit_server.py` as a subprocess with CLAUDE_PROJECT_DIR
pointed at a synthetic project, and speaks initialize -> tools/list ->
tools/call to it, the way a client would. What these prove: project_status
classifications; a preview writes nothing; apply refuses without a preview_id,
with an unknown or mismatched one, and with a stale one; apply with the
matching preview writes exactly the previewed files; a chain checkpoint is not
cleared without confirmation. What they cannot prove: behaviour inside a real
MCP client (Claude Code, Codex, Cursor, ...).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SERVER = PLUGIN / "mcp" / "audit_server.py"
BIN = PLUGIN / "bin"


def patched_plugin_server(dest: Path) -> Path:
    """A copy of this plugin whose DISABLED registry has one planted entry.

    The registry is a hardcoded product fact and the server runs as a
    subprocess, so the mechanism -- "a disabled audit is LISTED, not hidden" --
    can only be exercised end-to-end against a copy whose registry is
    non-empty. The registry ships empty in this repo: its two entries left
    with their scripts when this repo re-domained.
    """
    import shutil
    # Mirror the real marketplace layout (plugins/<name>/bin/...) so that every
    # path derived from `BIN.parents[2]` -- audit_prose_flags.py's SUITE_REPO,
    # for one -- lands inside this temp dir instead of two levels too high (a
    # shallower copy once wrote its findings envelope into the system temp
    # root, which is an ancestor of every other test's fixtures and poisoned
    # their marker walk-up).
    dst = dest / "plugins" / "backend-suite"
    shutil.copytree(PLUGIN, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    core = dst / "backend_suite" / "engine" / "audit_discovery.py"
    text = core.read_text()
    marker = "DISABLED: dict[str, dict[str, str]] = {}"
    assert marker in text, "registry literal moved -- update this test"
    text = text.replace(marker,
                        "DISABLED: dict[str, dict[str, str]] = {\n"
                        '    "audit_doc_staleness": {"reason": "disabled - planted for "'
                        '"this test", "detail": "d", "pathBack": "p"},\n}', 1)
    core.write_text(text)
    return dst / "mcp" / "audit_server.py"


class Server:
    def __init__(self, root: Path, server: Path | None = None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
        env.pop("BACKEND_SUITE_NO_ONBOARDING", None)
        self.p = subprocess.Popen([sys.executable, str(server or SERVER)], cwd=root, env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.n = 0
        init = self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                       "clientInfo": {"name": "test", "version": "0"}})
        assert init["result"]["serverInfo"]["name"]
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")

    def rpc(self, method, params):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method,
                                       "params": params}) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def call(self, name, args=None):
        r = self.rpc("tools/call", {"name": name, "arguments": args or {}})["result"]
        return json.loads(r["content"][0]["text"]), r["isError"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=30)


def snapshot(root: Path) -> dict:
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        for fn in fns:
            p = Path(dp) / fn
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (hashlib.sha256(p.read_bytes()).hexdigest(),
                                                   st.st_mtime_ns)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "proj"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.servers = []

    def tearDown(self):
        for s in self.servers:
            s.close()
        self.tmp.cleanup()

    def server(self, server: Path | None = None):
        s = Server(self.root, server)
        self.servers.append(s)
        return s

    def configure(self):
        subprocess.run([sys.executable, str(BIN / "init.py"), "--dir", str(self.root),
                        "--name", "demo"], check=True, capture_output=True)


class ToolsList(Base):
    def test_lists_onboarding_and_disabled_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            patched = patched_plugin_server(Path(tmp))
            tools = {t["name"]: t for t
                     in self.server(server=patched).rpc("tools/list", {})["result"]["tools"]}
        for name in ("project_status", "survey", "resolve_role", "doctor", "repo_health",
                     "init_from_survey", "map_project", "chain_status", "chain_next",
                     "chain_checkpoint"):
            self.assertIn(name, tools)
        self.assertIn("OFFER", tools["project_status"]["description"])
        self.assertIn("never start", tools["project_status"]["description"])
        self.assertIn(".backend-suite/survey.json", tools["survey"]["description"])
        self.assertTrue(any(t["description"].startswith("DISABLED") for t in tools.values()),
                        "disabled audits must stay listed as disabled")


class ProjectStatus(Base):
    def state(self, server: Path | None = None):
        res, err = self.server(server=server).call("project_status")
        self.assertFalse(err, res)
        return res

    def test_new(self):
        (self.root / "README.md").write_text("hi")
        res = self.state()
        self.assertEqual(res["state"], "new")
        self.assertIn("Do not start it", res["offer"])
        self.assertIsNone(res["audits"])

    def test_existing(self):
        (self.root / "app.py").write_text("x = 1\n")
        self.assertEqual(self.state()["state"], "existing")

    def test_partial(self):
        (self.root / ".backend-suite").mkdir()
        self.assertEqual(self.state()["state"], "partial")

    def test_declined(self):
        (self.root / ".backend-suite-onboarding-declined").write_text("")
        self.assertEqual(self.state()["state"], "declined")

    def test_configured_lists_refusing_and_disabled(self):
        (self.root / "app.py").write_text("x = 1\n")
        self.configure()
        # Disabled half runs against the patched copy (see
        # patched_plugin_server); the refusing half needs no patch -- an
        # audit with no adapter refuses on its own.
        with tempfile.TemporaryDirectory() as tmp:
            patched = patched_plugin_server(Path(tmp))
            res = self.state(server=patched)
        self.assertEqual(res["state"], "configured")
        self.assertTrue(res["audits"]["disabled"])
        for row in res["audits"]["refusing"]:
            self.assertTrue(row["why"])

    def test_writes_nothing(self):
        (self.root / "app.py").write_text("x = 1\n")
        before = snapshot(self.root)
        self.state()
        self.assertEqual(before, snapshot(self.root))


class PreviewApply(Base):
    def setUp(self):
        super().setUp()
        (self.root / "app.py").write_text("x = 1\n")
        self.s = self.server()
        res, err = self.s.call("survey")
        self.assertFalse(err, res)
        self.assertTrue((self.root / ".backend-suite" / "survey.json").is_file())

    def test_preview_writes_nothing(self):
        before = snapshot(self.root)
        res, err = self.s.call("init_from_survey", {"name": "demo"})
        self.assertFalse(err, res)
        self.assertEqual(res["mode"], "preview")
        self.assertTrue(res["plannedWrites"])
        self.assertEqual(before, snapshot(self.root))

    def test_apply_without_preview_id_refuses(self):
        before = snapshot(self.root)
        res, err = self.s.call("init_from_survey", {"name": "demo", "confirm": True})
        self.assertTrue(err)
        self.assertIn("preview_id", res["reason"])
        self.assertEqual(before, snapshot(self.root))

    def test_apply_with_unknown_preview_refuses(self):
        res, err = self.s.call("init_from_survey", {"name": "demo", "confirm": True,
                                                    "preview_id": "0" * 64})
        self.assertTrue(err)
        self.assertIn("unknown preview_id", res["reason"])

    def test_apply_with_mismatched_preview_refuses(self):
        prev, _ = self.s.call("init_from_survey", {"name": "demo"})
        before = snapshot(self.root)
        res, err = self.s.call("init_from_survey", {"name": "other", "confirm": True,
                                                    "preview_id": prev["preview_id"]})
        self.assertTrue(err)
        self.assertIn("does not match", res["reason"])
        self.assertEqual(before, snapshot(self.root))

    def test_stale_preview_refuses(self):
        prev, _ = self.s.call("init_from_survey", {"name": "demo"})
        (self.root / "app.py").write_text("x = 2\n")
        before = snapshot(self.root)
        res, err = self.s.call("init_from_survey", {"name": "demo", "confirm": True,
                                                    "preview_id": prev["preview_id"]})
        self.assertTrue(err)
        self.assertIn("stale", res["reason"])
        self.assertEqual(before, snapshot(self.root))

    def test_apply_writes_exactly_previewed(self):
        prev, _ = self.s.call("init_from_survey", {"name": "demo"})
        before = snapshot(self.root)
        res, err = self.s.call("init_from_survey", {"name": "demo", "confirm": True,
                                                    "preview_id": prev["preview_id"]})
        self.assertFalse(err, res)
        after = snapshot(self.root)
        changed = {k for k in set(before) | set(after) if before.get(k, (None,))[0] != after.get(k, (None,))[0]}
        planned = {w["path"]: w for w in prev["plannedWrites"]}
        self.assertEqual(changed, set(planned))
        for rel, w in planned.items():
            self.assertEqual((self.root / rel).read_text(), w["content"])
        # A spent preview cannot be replayed.
        again, err = self.s.call("init_from_survey", {"name": "demo", "confirm": True,
                                                      "preview_id": prev["preview_id"]})
        self.assertTrue(err)


class Chain(Base):
    CHAIN = "onboard-new-client"

    def test_checkpoint_needs_confirmation(self):
        (self.root / "app.py").write_text("x = 1\n")
        self.configure()
        s = self.server()
        nxt, err = s.call("chain_next", {"chain": self.CHAIN})
        self.assertFalse(err, nxt)
        step = json.loads(nxt["stdout"])["id"]
        before = snapshot(self.root)
        prev, err = s.call("chain_checkpoint", {"chain": self.CHAIN, "step": step})
        self.assertFalse(err, prev)
        self.assertEqual(prev["mode"], "preview")
        self.assertEqual(before, snapshot(self.root))
        res, err = s.call("chain_checkpoint", {"chain": self.CHAIN, "step": step, "confirm": True})
        self.assertTrue(err)
        self.assertEqual(json.loads(s.call("chain_next", {"chain": self.CHAIN})[0]["stdout"])["id"], step)
        res, err = s.call("chain_checkpoint", {"chain": self.CHAIN, "step": step, "confirm": True,
                                               "preview_id": prev["preview_id"]})
        self.assertFalse(err, res)
        # First applied call records the run; the checkpoint still blocks.
        blocked = json.loads(s.call("chain_next", {"chain": self.CHAIN})[0]["stdout"])
        self.assertEqual((blocked["id"], blocked["blocked"]), (step, True))
        prev2, _ = s.call("chain_checkpoint", {"chain": self.CHAIN, "step": step})
        res, err = s.call("chain_checkpoint", {"chain": self.CHAIN, "step": step, "confirm": True,
                                               "preview_id": prev2["preview_id"]})
        self.assertFalse(err, res)
        self.assertNotEqual(json.loads(s.call("chain_next", {"chain": self.CHAIN})[0]["stdout"])["id"], step)

    def test_unknown_chain_is_error_result(self):
        self.configure()
        res, err = self.server().call("chain_status", {"chain": "no-such-chain"})
        self.assertTrue(err)
        self.assertIn("refused", res["reason"])


if __name__ == "__main__":
    unittest.main()
