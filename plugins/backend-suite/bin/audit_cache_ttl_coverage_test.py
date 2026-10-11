#!/usr/bin/env python3
"""audit_cache_ttl_coverage: both drift directions, the clean run, the refusals.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_cache_ttl_coverage_test.py"

The TTL map is a copy of the routing table, so the audit compares them in
both directions. Every case plants its defect (a 0-finding envelope proves
nothing) or asserts the clean run still names what it swept.
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
SCRIPT = "audit_cache_ttl_coverage"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "cacheTtlCoverage": {
        "routesGlob": "routes/*.php",
        "actionPattern": r"'uses'\s*=>\s*'([A-Za-z]+@[A-Za-z]+)'",
        "ttlConfigGlob": "config/jikan.php",
        "ttlKeyPattern": r"'([A-Za-z]+@[A-Za-z]+)'\s*=>",
    },
}

ROUTES = """<?php

$router->get('/anime', [
    'uses' => 'AnimeController@main'
]);

$router->get('/anime/full', [
    'uses' => 'AnimeController@full'
]);
"""

TTL_CONFIG = """<?php

return [
    'per_endpoint_cache_ttl' => [
        'AnimeController@main' => env('CACHE_DEFAULT_EXPIRE'),
    ],
];
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, routes: str = ROUTES, ttl: str = TTL_CONFIG,
          rules: dict | None = None, missing_routes: bool = False) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(
        json.dumps(rules or RULES))
    if not missing_routes:
        (repo / "routes").mkdir()
        (repo / "routes" / "web.v4.php").write_text(routes)
    (repo / "config").mkdir()
    (repo / "config" / "jikan.php").write_text(ttl)
    return repo


class CacheTtlCoverage(unittest.TestCase):
    def test_route_missing_from_the_ttl_map_reaches_the_envelope(self):
        """AnimeController@full is routed but unconfigured — the measured shape."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, ttl=TTL_CONFIG.replace(
                "'AnimeController@main'", "'MangaController@main'"))
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "cache-ttl-coverage.json").read_text())
            self.assertEqual(data["audit"], "cache-ttl-coverage")
            categories = {f["category"] for f in data["findings"]}
            self.assertEqual(categories,
                             {"route_missing_ttl", "stale_ttl_entry"})
            missing = [f for f in data["findings"]
                       if f["category"] == "route_missing_ttl"]
            self.assertEqual(len(missing), 2)
            self.assertEqual(
                {f["summary"].split(" ")[0] for f in missing},
                {"AnimeController@main", "AnimeController@full"})
            self.assertEqual(missing[0]["file"], "routes/web.v4.php")
            self.assertIsInstance(missing[0]["line"], int)
            stale = [f for f in data["findings"]
                     if f["category"] == "stale_ttl_entry"]
            self.assertIn("MangaController@main", stale[0]["summary"])
            self.assertGreaterEqual(data["scanned"], 1)

    def test_every_action_configured_is_clean_but_says_what_it_swept(self):
        with tempfile.TemporaryDirectory() as tmp:
            ttl = TTL_CONFIG.replace(
                "];",
                "    'AnimeController@full' => env('CACHE_DEFAULT_EXPIRE'),\n];")
            repo = build(tmp, ttl=ttl)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "cache-ttl-coverage.json").read_text())
            self.assertEqual(data["findings"], [])
            # Clean over a real sweep: both files were read, neither silently.
            self.assertEqual(data["scanned"], 2)

    def test_a_documented_exemption_covers_a_route_and_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = json.loads(json.dumps(RULES))
            rules["cacheTtlCoverage"]["exempt"] = {
                "AnimeController@full": "static responses; caching adds nothing"}
            repo = build(tmp, rules=rules)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "cache-ttl-coverage.json").read_text())
            self.assertEqual(data["findings"], [])
            # Documented, not green: the envelope names what was exempted.
            self.assertIn("AnimeController@full", data["suppressed"])

    def test_an_exemption_without_a_reason_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = json.loads(json.dumps(RULES))
            rules["cacheTtlCoverage"]["exempt"] = {"AnimeController@full": ""}
            repo = build(tmp, rules=rules)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("REFUSED", result.stderr)

    def test_routes_glob_matching_nothing_refuses_rather_than_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, missing_routes=True)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("routesGlob", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
