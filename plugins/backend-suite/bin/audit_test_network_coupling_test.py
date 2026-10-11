#!/usr/bin/env python3
"""audit_test_network_coupling: the live test, the recorded control, the fallback.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_test_network_coupling_test.py"

The recorded-client control is the point: a host string inside a mocked
test is not coupling, and an audit that flagged it would train its own
findings away from the real ones.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
SCRIPT = "audit_test_network_coupling"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "testNetworkCoupling": {
        "testsGlob": "test/**/*.php",
        "liveHostPattern": r"myanimelist\.net",
        "mockClientPattern": r"MockHttpClient|RecordedClient|extends TestCase",
        "fallbackPattern": r"HttpClient::create\(",
    },
}

LIVE = """<?php

class LiveTest extends \\PHPUnit\\Framework\\TestCase
{
    public function testFetch()
    {
        $client = new \\Goutte\\Client();
        $client->request('GET', 'https://myanimelist.net/topanime.php');
    }
}
"""

RECORDED = """<?php

class RecordedTest extends TestCase
{
    public function testParse()
    {
        $client = new \\Client($this->httpClient);
        $client->request('GET', 'https://myanimelist.net/topanime.php');
    }
}
"""

FALLBACK = """<?php

class CacheCallback
{
    public function __construct(string $cachePath)
    {
        $this->client = HttpClient::create();
    }
}
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, files: dict[str, str],
          rules: dict | None = None) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "test").mkdir()
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(
        json.dumps(rules or RULES))
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return repo


class TestNetworkCoupling(unittest.TestCase):
    def test_live_test_reported_and_recorded_control_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, files={
                "test/LiveTest.php": LIVE,
                "test/RecordedTest.php": RECORDED,
            })
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "test-network-coupling.json").read_text())
            self.assertEqual(data["audit"], "test-network-coupling")
            self.assertEqual({f["category"] for f in data["findings"]},
                             {"live_network_test"})
            self.assertEqual(data["findings"][0]["file"], "test/LiveTest.php")
            # The recorded file is counted, not silent — documented-clean.
            self.assertRegex(result.stdout, r"test files\s+2")
            self.assertRegex(result.stdout, r"reference a host\s+2")
            self.assertIn("(1 through recorded clients)", result.stdout)

    def test_a_real_client_fallback_is_reported_even_with_mock_markers(self):
        """The miss-path construction is the measured coupling shape: it
        goes live when a recording is absent, and the run looks offline."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, files={
                "test/Callback.php": FALLBACK,
                "test/RecordedTest.php": RECORDED,
            })
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "test-network-coupling.json").read_text())
            fallback = [f for f in data["findings"]
                        if f["category"] == "network_fallback"]
            self.assertEqual(fallback[0]["file"], "test/Callback.php")
            self.assertIsInstance(fallback[0]["line"], int)

    def test_an_exempted_fallback_is_named_with_its_reason(self):
        rules = json.loads(json.dumps(RULES))
        rules["testNetworkCoupling"]["exempt"] = {
            "test/Callback.php":
                "record-on-first-use by design; CI pre-clones recordings"}
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, files={"test/Callback.php": FALLBACK},
                         rules=rules)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "test-network-coupling.json").read_text())
            self.assertEqual(data["findings"], [])
            self.assertIn("test/Callback.php", data["suppressed"])

    def test_only_recorded_references_are_clean_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, files={
                "test/A.php": RECORDED,
                "test/B.php": RECORDED,
            })
            result = run([], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("(2 through recorded clients)", result.stdout)

    def test_tests_glob_matching_nothing_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, files={})
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("testsGlob", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
