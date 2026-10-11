#!/usr/bin/env python3
"""audit_rate_limit: unprotected routes, the two protection shapes, refusals.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_rate_limit_test.py"

The measured first-target state is "nothing protected", so the planted case
is the default state and each protection shape gets its own control: a
finding audit whose protected case silently still reported would teach
readers to skip its line.
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
SCRIPT = "audit_rate_limit"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "rateLimit": {
        "routesGlob": "routes/*.php",
        "actionPattern": r"'uses'\s*=>\s*'([A-Za-z]+)@([A-Za-z]+)'",
        "protectionPattern": r"throttle[:'\)]",
        "globalProtectionPattern": r"'throttle'",
        "globalProtectionFiles": ["bootstrap/app.php"],
        "windowLines": 4,
    },
}

ROUTES = """<?php

$router->get('/open', [
    'uses' => 'OpenController@main'
]);

$router->get('/limited', [
    'uses' => 'LimitedController@main'
])->middleware('throttle:60,1');
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, routes: str = ROUTES, bootstrap: str = "<?php\n",
          rules: dict | None = None) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "routes").mkdir()
    (repo / "bootstrap").mkdir()
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(
        json.dumps(rules or RULES))
    (repo / "routes" / "web.v4.php").write_text(routes)
    (repo / "bootstrap" / "app.php").write_text(bootstrap)
    return repo


class RateLimit(unittest.TestCase):
    def test_unprotected_route_reported_per_route_limiter_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "rate-limit.json").read_text())
            self.assertEqual(data["audit"], "rate-limit")
            self.assertEqual({f["category"] for f in data["findings"]},
                             {"unprotected_endpoint"})
            self.assertEqual(len(data["findings"]), 1)
            self.assertIn("OpenController@main", data["findings"][0]["summary"])
            self.assertIsInstance(data["findings"][0]["line"], int)
            self.assertIn("OpenController@main",
                          result.stderr)

    def test_a_global_throttle_covers_every_route(self):
        bootstrap = ("<?php\n"
                     "$app->middleware(['throttle']);\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, bootstrap=bootstrap)
            result = run([], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("global throttle     yes", result.stdout)

    def test_a_documented_exemption_covers_and_is_named(self):
        rules = json.loads(json.dumps(RULES))
        rules["rateLimit"]["exempt"] = {
            "OpenController@main": "static status payload; abuse costs nothing"}
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, rules=rules)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "rate-limit.json").read_text())
            self.assertEqual(data["findings"], [])
            self.assertIn("OpenController@main", data["suppressed"])

    def test_an_exemption_without_a_reason_refuses(self):
        rules = json.loads(json.dumps(RULES))
        rules["rateLimit"]["exempt"] = {"OpenController@main": ""}
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, rules=rules)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("REFUSED", result.stderr)

    def test_routes_glob_matching_nothing_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            (repo / "routes" / "web.v4.php").unlink()
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("routesGlob", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
