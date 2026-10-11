#!/usr/bin/env python3
"""audit_toolchain_gates: the three drift shapes and the coherent control.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_toolchain_gates_test.py"

The zero-tests-suite-directory case is planted as CRITICAL on purpose: a
suite over a missing directory exits green having run nothing, and that is
the confident-zero failure this whole suite is built around — showing up
here in the project's own toolchain.
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
SCRIPT = "audit_toolchain_gates"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "toolchainGates": {
        "manifestGlob": "composer.json",
        "runnerGlob": "phpunit.xml",
        "requiredScripts": ["test"],
        "testsuiteFlag": "--testsuite",
    },
}

COMPOSER_OK = {
    "scripts": {
        "test": "@php ./vendor/bin/phpunit --testsuite unit",
    },
}
COMPOSER_NO_TEST = {
    "scripts": {
        "post-install": "echo hi",
    },
}
COMPOSER_BROKEN_SUITE = {
    "scripts": {
        "test-unit": "@php ./vendor/bin/phpunit --testsuite renamed",
    },
}

PHPUNIT_OK = """<phpunit>
  <testsuites>
    <testsuite name="unit">
      <directory>tests</directory>
    </testsuite>
  </testsuites>
</phpunit>
"""

PHPUNIT_MISSING_DIR = """<phpunit>
  <testsuites>
    <testsuite name="unit">
      <directory>gone</directory>
    </testsuite>
  </testsuites>
</phpunit>
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, composer: dict,
          phpunit: str = PHPUNIT_OK) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(json.dumps(RULES))
    (repo / "composer.json").write_text(json.dumps(composer))
    (repo / "phpunit.xml").write_text(phpunit)
    return repo


class ToolchainGates(unittest.TestCase):
    def test_all_three_drift_shapes_reach_the_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, composer=COMPOSER_BROKEN_SUITE,
                         phpunit=PHPUNIT_MISSING_DIR)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "toolchain-gates.json").read_text())
            self.assertEqual(data["audit"], "toolchain-gates")
            kinds = {f["category"] for f in data["findings"]}
            self.assertEqual(kinds, {"missing_required_script",
                                     "script_testsuite_undefined",
                                     "testsuite_directory_missing"})
            zero = [f for f in data["findings"]
                    if f["category"] == "testsuite_directory_missing"][0]
            self.assertIn("runs zero tests and exits green", zero["summary"])
            self.assertEqual(zero["severity"], "critical")

    def test_wired_scripts_and_real_directories_are_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, composer=COMPOSER_OK)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "toolchain-gates.json").read_text())
            self.assertEqual(data["findings"], [])
            self.assertEqual(data["scanned"], 2)

    def test_a_required_script_is_only_missing_when_actually_absent(self):
        composer = {"scripts": {"test": "phpunit", "other": "x"}}
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, composer=composer)
            result = run([], repo)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_runner_glob_matching_nothing_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, composer=COMPOSER_OK)
            (repo / "phpunit.xml").unlink()
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("runnerGlob", result.stderr)

    def test_unparseable_runner_refuses_rather_than_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, composer=COMPOSER_OK, phpunit="<phpunit")
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("not parseable XML", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
