#!/usr/bin/env python3
"""audit_endpoint_parity: the undocumented route, the phantom doc, refusals.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_endpoint_parity_test.py"

Both drift directions are planted (a clean envelope proves nothing), and the
dead-controller path asserts a refusal rather than a misfiled finding — that
defect belongs to route coverage.
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
SCRIPT = "audit_endpoint_parity"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "endpointParity": {
        "routesGlob": "routes/*.php",
        "actionPattern": r"'uses'\s*=>\s*'([A-Za-z]+)@([A-Za-z]+)'",
        "controllerDirs": ["app/Http/Controllers"],
        "docMarkers": ["@OA\\Get("],
    },
}

ROUTES = """<?php

$router->get('/search', [
    'uses' => 'SearchController@anime'
]);

$router->get('/insights', [
    'uses' => 'InsightsController@main'
]);
"""

SEARCH = """<?php

class SearchController
{
    /**
     * @OA\\Get(path="/search", operationId="searchAnime")
     */
    public function anime()
    {
    }

    /**
     * @OA\\Get(path="/search/legacy", operationId="searchLegacy")
     */
    public function legacy()
    {
    }
}
"""

INSIGHTS = """<?php

class InsightsController
{
    public function main()
    {
    }
}
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, search: str = SEARCH, insights: str = INSIGHTS,
          rules: dict | None = None, drop_insights_file: bool = False) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "routes").mkdir()
    (repo / "app" / "Http" / "Controllers").mkdir(parents=True)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(
        json.dumps(rules or RULES))
    (repo / "routes" / "web.v4.php").write_text(ROUTES)
    (repo / "app" / "Http" / "Controllers" / "SearchController.php").write_text(
        search)
    if not drop_insights_file:
        (repo / "app" / "Http" / "Controllers" / "InsightsController.php"
         ).write_text(insights)
    return repo


class EndpointParity(unittest.TestCase):
    def test_both_drift_directions_reach_the_envelope(self):
        """InsightsController@main is served but undocumented; the annotated
        SearchController.legacy has no route — the measured pair."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "endpoint-parity.json").read_text())
            self.assertEqual(data["audit"], "endpoint-parity")
            categories = {f["category"] for f in data["findings"]}
            self.assertEqual(categories,
                             {"undocumented_endpoint", "phantom_documentation"})
            undocumented = [f for f in data["findings"]
                            if f["category"] == "undocumented_endpoint"]
            self.assertEqual(len(undocumented), 1)
            self.assertIn("InsightsController@main",
                          undocumented[0]["summary"])
            self.assertEqual(undocumented[0]["file"], "routes/web.v4.php")
            self.assertIsInstance(undocumented[0]["line"], int)
            phantom = [f for f in data["findings"]
                       if f["category"] == "phantom_documentation"]
            self.assertIn("SearchController.legacy()", phantom[0]["summary"])
            self.assertEqual(phantom[0]["file"],
                             "app/Http/Controllers/SearchController.php")

    def test_documented_routes_and_no_phantoms_are_clean(self):
        clean_search = SEARCH.replace(
            "    /**\n     * @OA\\Get(path=\"/search/legacy\", "
            "operationId=\"searchLegacy\")\n     */\n", "")
        documented_insights = INSIGHTS.replace(
            "    public function main()",
            "    /**\n     * @OA\\Get(path=\"/insights\")\n     */\n"
            "    public function main()")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, search=clean_search, insights=documented_insights)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "endpoint-parity.json").read_text())
            self.assertEqual(data["findings"], [])
            self.assertEqual(data["scanned"], 3)  # 1 routes file + 2 controllers

    def test_a_file_header_mentioning_the_marker_documents_nothing(self):
        """The comment regex must not let a docblock run past its own end
        into the next one — or a header mentioning @OA would document the
        method below it."""
        header = ("<?php\n"
                  "/** API surface. Annotations use @OA\\Get. */\n"
                  "class InsightsController\n{\n"
                  "    public function main()\n    {\n    }\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, insights=header)
            result = run([], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("InsightsController@main", result.stderr)

    def test_an_action_whose_controller_file_is_missing_refuses(self):
        """That route is dead — route coverage's defect, not a doc gap."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, drop_insights_file=True)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("REFUSED", result.stderr)
            self.assertIn("InsightsController", result.stderr)

    def test_empty_doc_markers_refuse_rather_than_report_all_undocumented(self):
        rules = json.loads(json.dumps(RULES))
        rules["endpointParity"]["docMarkers"] = []
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, rules=rules)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("docMarkers", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
