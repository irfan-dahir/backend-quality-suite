#!/usr/bin/env python3
"""propose_config: measured backend proposals, honest refusals, human fills.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config_test.py"

The bar under test is the one the module states: every proposal is an
observed invariant a scan can measure, and where the evidence is not there
the script refuses rather than guesses. The fixture is a small php project
whose layer relationship, routing table and TTL map are all real files, so
each assertion checks a value that could only come from reading the tree —
including the psr-4 namespace handle that makes the proposed layer rule
one audit_layer_boundaries.py can actually fire on.
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
SCRIPT = "propose_config"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "adapters": {"lang": "php"},
    "source": {"root": "app"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}


def run(args, repo):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run(
        [sys.executable, str(BIN / f"{SCRIPT}.py"), "--dir", str(repo), *args],
        capture_output=True, text=True, cwd=str(repo), env=env)


def write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def tmp_repo() -> Path:
    repo = Path(tempfile.mkdtemp()) / "proj"
    repo.mkdir(parents=True)
    return repo


def full_repo(repo: Path) -> Path:
    """A php project where all three measurements have something to find.

    app/Service is imported by exactly five app/Http files and imports none
    of them back (the layer invariant); routes/api.php spells two
    Class@method actions whose controllers live in one directory — plus a
    same-named controller under vendor/, which must be ignored; and
    config/app.php keeps an action-keyed TTL map.
    """
    write(repo, ".backend-suite/profile.json", json.dumps(PROFILE))
    write(repo, ".backend-suite/arch-rules.json", json.dumps({"_readme": "f"}))
    write(repo, "composer.json", json.dumps(
        {"autoload": {"psr-4": {"App\\": "app/"}}}))
    write(repo, "app/Service/A.php", "<?php\nnamespace App\\Service;\nclass A {}\n")
    write(repo, "app/Service/B.php", "<?php\nnamespace App\\Service;\nclass B {}\n")
    for i in range(5):
        write(repo, f"app/Http/H{i}.php",
              f"<?php\nnamespace App\\Http;\nuse App\\Service\\A;\nclass H{i} {{}}\n")
    write(repo, "app/Http/Controllers/ThingController.php",
          "<?php\nnamespace App\\Http\\Controllers;\n"
          "class ThingController {\n    public function getA() {}\n"
          "    public function getB() {}\n}\n")
    write(repo, "vendor/pkg/ThingController.php",
          "<?php\nclass ThingController {}\n")
    write(repo, "routes/api.php",
          "<?php\n"
          "$router->get('/a', ['uses' => 'ThingController@getA']);\n"
          "$router->get('/b', ['uses' => 'ThingController@getB']);\n")
    write(repo, "config/app.php",
          "<?php\nreturn ['ttl' => [\n    'ThingController@getA' => 60,\n]];\n")
    return repo


def by_section(proposals):
    return {p["section"]: p for p in proposals}


class ProposalsAreMeasured(unittest.TestCase):
    def test_all_three_sections_proposed_from_the_tree(self):
        repo = full_repo(tmp_repo())
        before = (repo / ".backend-suite" / "arch-rules.json").read_text()
        run_ = run(["--json"], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        data = json.loads(run_.stdout)
        props = by_section(data["proposals"])
        self.assertEqual(sorted(props), ["cacheTtlCoverage", "layerBoundaries",
                                         "routeCoverage"])

        layer = props["layerBoundaries"]["value"]["rules"][0]
        self.assertEqual(layer["fromGlob"], "app/Service/**")
        self.assertEqual(sorted(layer["mustNotImport"]),
                         ["App\\Http\\", "app/Http/**"])
        self.assertIn("no file under app/Service imports any of them",
                      props["layerBoundaries"]["evidence"])
        self.assertIn("Http = App\\Http\\",
                      props["layerBoundaries"]["evidence"])

        route = props["routeCoverage"]["value"]
        self.assertEqual(route["routesGlob"], "routes/*.php")
        self.assertEqual(route["controllerDirs"], ["app/Http/Controllers"])
        self.assertIn("uses", route["actionPattern"])

        ttl = props["cacheTtlCoverage"]["value"]
        self.assertEqual(ttl["routesGlob"], "routes/*.php")
        self.assertEqual(ttl["ttlConfigGlob"], "config/app.php")
        self.assertIn("config/app.php", props["cacheTtlCoverage"]["evidence"])
        self.assertIn("1 of them have a TTL entry",
                      props["cacheTtlCoverage"]["evidence"])

        for p in data["proposals"]:
            self.assertGreaterEqual(len(p["evidence"]), 40, p["section"])
        # A preview writes nothing.
        self.assertEqual((repo / ".backend-suite" / "arch-rules.json").read_text(),
                         before)

    def test_apply_all_writes_provenance(self):
        repo = full_repo(tmp_repo())
        run_ = run(["--apply", "all"], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        doc = json.loads((repo / ".backend-suite" / "arch-rules.json").read_text())
        for section in ("layerBoundaries", "routeCoverage", "cacheTtlCoverage"):
            prov = doc[section]["_provenance"]
            self.assertEqual(prov["state"], "inferred", section)
            self.assertGreaterEqual(len(prov["evidence"]), 40, section)
        self.assertEqual(doc["routeCoverage"]["controllerDirs"],
                         ["app/Http/Controllers"])

    def test_human_filled_section_never_overwritten(self):
        repo = full_repo(tmp_repo())
        hand = {"routesGlob": "routes/*.php",
                "actionPattern": "'uses'\\s*=>\\s*'X'",
                "controllerDirs": ["app/Http/Controllers"]}
        write(repo, ".backend-suite/arch-rules.json",
              json.dumps({"routeCoverage": hand}))
        run_ = run(["--apply", "all"], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        doc = json.loads((repo / ".backend-suite" / "arch-rules.json").read_text())
        self.assertEqual(doc["routeCoverage"], hand)
        self.assertIn("_provenance", doc["layerBoundaries"])
        self.assertIn("_provenance", doc["cacheTtlCoverage"])


class HonestRefusals(unittest.TestCase):
    def test_nothing_measurable_exits_two(self):
        """'Nothing inferred' must never read like 'all configured'."""
        repo = tmp_repo()
        write(repo, ".backend-suite/profile.json", json.dumps(PROFILE))
        write(repo, ".backend-suite/arch-rules.json", json.dumps({}))
        write(repo, "composer.json", json.dumps(
            {"autoload": {"psr-4": {"App\\": "app/"}}}))
        write(repo, "app/X.php", "<?php\nnamespace App;\nclass X {}\n")
        run_ = run(["--json"], repo)
        self.assertEqual(run_.returncode, 2)
        data = json.loads(run_.stdout)
        self.assertEqual(data["proposals"], [])
        self.assertIn("routes layout", data["notInferred"]["routeCoverage"])
        self.assertIn("the routes measurement failed first",
                      data["notInferred"]["cacheTtlCoverage"])
        self.assertIn("nothing could be proposed", run_.stderr)

    def test_unspelled_uses_refuses_the_route_section(self):
        """A routing table that does not spell Class@method gets no
        actionPattern — the guess would leave the audit resolving nothing."""
        repo = full_repo(tmp_repo())
        write(repo, "routes/api.php",
              "<?php\n"
              "$router->get('/a', ['uses' => 'ThingController@getA']);\n"
              "$router->get('/b', ['uses' => 'Thing::method']);\n")
        run_ = run(["--json"], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        data = json.loads(run_.stdout)
        props = by_section(data["proposals"])
        self.assertNotIn("routeCoverage", props)
        self.assertNotIn("cacheTtlCoverage", props)
        self.assertIn("Class@method", data["notInferred"]["routeCoverage"])
        self.assertIn("layerBoundaries", props)  # the rest still stands

    def test_unreadable_composer_json_refuses(self):
        repo = full_repo(tmp_repo())
        (repo / "composer.json").write_text("{ not json")
        run_ = run(["--json"], repo)
        self.assertEqual(run_.returncode, 2)
        self.assertIn("psr-4", run_.stderr)
        self.assertIn("composer.json is not valid JSON", run_.stderr)

    def test_apply_unknown_section_refused_and_writes_nothing(self):
        repo = full_repo(tmp_repo())
        before = (repo / ".backend-suite" / "arch-rules.json").read_text()
        run_ = run(["--apply", "bogusSection"], repo)
        self.assertEqual(run_.returncode, 2)
        self.assertIn("refusing: no proposal for", run_.stderr)
        self.assertEqual((repo / ".backend-suite" / "arch-rules.json").read_text(),
                         before)


class NeverProposed(unittest.TestCase):
    def test_listing_covers_conventions_decisions_and_dead_sections(self):
        repo = full_repo(tmp_repo())
        run_ = run(["--json"], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        not_proposed = json.loads(run_.stdout)["notProposed"]
        for section in ("errorHandling", "contractHeaders", "apiConsistency",
                        "errorShape", "endpointParity", "rateLimit",
                        "versioning", "toolchainGates", "testNetworkCoupling",
                        "adapterPattern", "unwiredRoles", "unusedTokens"):
            self.assertIn(section, not_proposed)
            self.assertTrue(not_proposed[section], section)
        self.assertIn("no audit ships", not_proposed["adapterPattern"])


if __name__ == "__main__":
    unittest.main()
