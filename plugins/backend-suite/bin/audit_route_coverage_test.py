#!/usr/bin/env python3
"""audit_route_coverage: dead method, dead controller, closures, refusals.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_route_coverage_test.py"

The clean case matters as much as the planted ones: this audit measured
clean on its first validation target, and the honest run has to say what it
swept rather than just "0".
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
SCRIPT = "audit_route_coverage"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "routeCoverage": {
        "routesGlob": "routes/*.php",
        "actionPattern": r"'uses'\s*=>\s*'([A-Za-z]+)@([A-Za-z]+)'",
        "controllerDirs": ["app/Http/Controllers"],
    },
}

ROUTES = """<?php

$router->get('/', function () {
    return response()->json(['ok' => true]);
});

$router->get('/search', [
    'uses' => 'SearchController@anime'
]);

$router->get('/gone', [
    'uses' => 'SearchController@removed'
]);

$router->get('/ghost', [
    'uses' => 'GhostController@main'
]);
"""

SEARCH = """<?php

class SearchController
{
    public function anime()
    {
    }
}
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, routes: str = ROUTES, search: str = SEARCH) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "routes").mkdir()
    (repo / "app" / "Http" / "Controllers").mkdir(parents=True)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(json.dumps(RULES))
    (repo / "routes" / "web.v4.php").write_text(routes)
    (repo / "app" / "Http" / "Controllers" / "SearchController.php"
     ).write_text(search)
    return repo


class RouteCoverage(unittest.TestCase):
    def test_dead_method_and_dead_controller_reach_the_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "route-coverage.json").read_text())
            self.assertEqual(data["audit"], "route-coverage")
            self.assertEqual({f["category"] for f in data["findings"]},
                             {"dead_route"})
            summaries = {f["summary"].split(" ")[0]: f for f in data["findings"]}
            self.assertIn("SearchController@removed", summaries)
            self.assertIn("declares no function removed()", 
                          summaries["SearchController@removed"]["summary"])
            self.assertIn("GhostController@main", summaries)
            self.assertIn("no GhostController.php exists",
                          summaries["GhostController@main"]["summary"])
            # A dead route is request-time fatal: critical, with its line.
            self.assertEqual(summaries["SearchController@removed"]["severity"],
                             "critical")
            self.assertIsInstance(
                summaries["SearchController@removed"]["line"], int)

    def test_every_action_resolving_is_clean_and_counts_its_closure(self):
        routes = ROUTES.replace(
            "\n$router->get('/gone', [\n    'uses' => 'SearchController@removed'\n]);\n",
            "").replace(
            "\n$router->get('/ghost', [\n    'uses' => 'GhostController@main'\n]);\n",
            "")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, routes=routes)
            result = run([], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            # The closure route is named, not silently ignored.
            self.assertIn("closure handlers    1", result.stdout)
            self.assertRegex(result.stdout, r"route actions\s+1")

    def test_a_routes_file_with_only_closures_refuses_rather_than_clean(self):
        closure_only = """<?php

$router->get('/', function () {
    return response()->json(['ok' => true]);
});
"""
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, routes=closure_only)
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
