#!/usr/bin/env python3
"""audit_layer_boundaries: php namespace roots, path roots, refusals.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_layer_boundaries_test.py"

The php re-author of the fixture this script never shipped (the design-suite
cases were purged without a replacement): a layer rule on this stack bans
NAMESPACE roots for `use` targets as well as path roots for `require`d files,
both matched by prefix. The precision case matters as much as the planted
one: `App\Http\` must not match `use App\HttpExtra\X`, or every rule
over-bans its siblings' namespaces. The ratchet case guards the other half
of the contract: a new violation is shown, never silently baselined.
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
SCRIPT = "audit_layer_boundaries"

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
        [sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
        capture_output=True, text=True, cwd=str(repo), env=env)


def write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def tmp_repo() -> Path:
    repo = Path(tempfile.mkdtemp()) / "proj"
    repo.mkdir(parents=True)
    return repo


def scaffold(repo, rules):
    """A php project with app/Service, plus the given layerBoundaries rules."""
    write(repo, ".backend-suite/profile.json", json.dumps(PROFILE))
    write(repo, ".backend-suite/arch-rules.json",
          json.dumps({"layerBoundaries": rules}))
    write(repo, "composer.json",
          json.dumps({"autoload": {"psr-4": {"App\\": "app/"}}}))
    write(repo, "app/Service/A.php",
          "<?php\nnamespace App\Service;\nclass A {}\n")


def both_forms_rules():
    return {"rules": [{"label": "app/Service must stay the bottom layer",
                       "from": "app/Service",
                       "mustNotImport": ["src/", "App\\Http\\"],
                       "why": "fixture"}]}


class LayerBoundariesPhp(unittest.TestCase):
    def test_namespace_and_path_roots_both_fire(self):
        repo = tmp_repo()
        scaffold(repo, both_forms_rules())
        write(repo, "app/Service/B.php",
              "<?php\nnamespace App\\Service;\nuse App\\Http\\Thing;\n"
              "require 'src/x.php';\nclass B {}\n")
        run_ = run([], repo)
        self.assertEqual(run_.returncode, 1, run_.stderr)
        self.assertIn("NEW LAYER-BOUNDARY VIOLATIONS (2):", run_.stdout)
        self.assertIn("app/Service/B.php:3 imports App\\Http\\Thing",
                      run_.stdout)
        self.assertIn("app/Service/B.php:4 imports src/x.php", run_.stdout)

    def test_clean_control_says_what_it_swept(self):
        repo = tmp_repo()
        scaffold(repo, both_forms_rules())
        run_ = run([], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        self.assertIn("no new violations (0 baselined", run_.stdout)

    def test_namespace_prefix_precision_no_overmatch(self):
        """`App\Http\` must not catch `use App\HttpExtra\X` — the trailing
        separator is the whole precision of a namespace root."""
        repo = tmp_repo()
        scaffold(repo, both_forms_rules())
        write(repo, "app/Service/B.php",
              "<?php\nnamespace App\\Service;\nuse App\\HttpExtra\\X;\n"
              "class B {}\n")
        run_ = run([], repo)
        self.assertEqual(run_.returncode, 0, run_.stderr)
        self.assertIn("no new violations (0 baselined", run_.stdout)

    def test_todo_rule_refuses(self):
        repo = tmp_repo()
        scaffold(repo, {"rules": [{"from": "TODO: e.g. 'app/Service/**'",
                                   "mustNotImport": ["TODO_ROOT"]}]})
        run_ = run([], repo)
        self.assertEqual(run_.returncode, 2)
        self.assertIn("TODO placeholders", run_.stderr)
        self.assertIn("REFUSED (exit 2, INERT", run_.stderr)

    def test_empty_layer_refuses(self):
        """An empty sweep would report clean having compared nothing."""
        repo = tmp_repo()
        scaffold(repo, both_forms_rules())
        (repo / "app" / "Service" / "A.php").unlink()
        (repo / "app" / "Service" / "notes.txt").write_text("not php\n")
        run_ = run([], repo)
        self.assertEqual(run_.returncode, 2)
        self.assertIn("0 php source files under app/Service", run_.stderr)

    def test_missing_layer_dir_refuses(self):
        repo = tmp_repo()
        scaffold(repo, {"rules": [{"from": "app/Nope",
                                   "mustNotImport": ["App\\Http\\"]}]})
        run_ = run([], repo)
        self.assertEqual(run_.returncode, 2)
        self.assertIn("no such directory", run_.stderr)

    def test_ratchet_never_silently_absorbs(self):
        """A new violation is shown; the baseline write is refused until
        --accept-new says the absorption is deliberate."""
        repo = tmp_repo()
        scaffold(repo, both_forms_rules())
        first = run([], repo)
        self.assertEqual(first.returncode, 0, first.stderr)
        baseline = repo / ".backend-suite" / "baselines" / "layer-boundaries.json"
        write(repo, "app/Service/B.php",
              "<?php\nnamespace App\\Service;\nuse App\\Http\\Thing;\n"
              "class B {}\n")
        absorbed = run(["--update-baseline"], repo)
        self.assertEqual(absorbed.returncode, 2)
        self.assertIn("REFUSING TO UPDATE THE BASELINE", absorbed.stderr)
        self.assertFalse(baseline.exists(), "a refused write must write nothing")
        accepted = run(["--update-baseline", "--accept-new"], repo)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        keys = json.loads(baseline.read_text())
        self.assertEqual(keys, ["app/Service/B.php -> App\\Http\\Thing"])
        after = run([], repo)
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertIn("1 baselined", after.stdout)


if __name__ == "__main__":
    unittest.main()
