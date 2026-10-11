#!/usr/bin/env python3
"""audit_versioning: the three version statements, each direction.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_versioning_test.py"

Filename, prefix, namespace — two planted mismatches (one per comparison)
against the coherent control, plus the refusal for a bootstrap that mounts
nothing this audit can version-check.
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
SCRIPT = "audit_versioning"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "versioning": {
        "bootstrapGlob": "bootstrap/app.php",
        "routeFilePattern": r"web\.v(\d+)\.php",
        "prefixPattern": r"'prefix'\s*=>\s*'v(\d+)'",
        "namespacePattern": r"'namespace'\s*=>\s*'([^']+)'",
        "namespaceVersionPattern": r"V(\d+)",
    },
}

COHERENT = """<?php

$app->router->group(
    [
        'prefix' => 'v4',
        'namespace' => 'App\\Http\\Controllers\\V4DB',
    ],
    function ($router) {
        require __DIR__.'/../routes/web.v4.php';
    }
);

$app->router->group(
    [
        'prefix' => '/',
    ],
    function ($router) {
        $router->get('/', function () {
            return response()->json(['ok' => true]);
        });
    }
);
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, bootstrap: str = COHERENT) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "bootstrap").mkdir()
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(json.dumps(RULES))
    (repo / "bootstrap" / "app.php").write_text(bootstrap)
    return repo


class Versioning(unittest.TestCase):
    def test_coherent_mount_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "versioning.json").read_text())
            self.assertEqual(data["findings"], [])
            self.assertGreaterEqual(data["scanned"], 1)

    def test_prefix_behind_the_filename_is_a_critical_mismatch(self):
        planted = COHERENT.replace("web.v4.php", "web.v5.php")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, bootstrap=planted)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "versioning.json").read_text())
            # A v5 file on a v4 prefix under a V4 namespace disagrees with
            # both — every stale statement is its own finding.
            kinds = {f["category"] for f in data["findings"]}
            self.assertEqual(kinds, {"prefix_version_mismatch",
                                     "namespace_version_mismatch"})
            prefix = [f for f in data["findings"]
                      if f["category"] == "prefix_version_mismatch"][0]
            self.assertIn("web.v5.php", prefix["summary"])
            self.assertIn("prefix is v4", prefix["summary"])
            # Callers reach v5 code on the v4 URL: request-time critical.
            self.assertEqual(prefix["severity"], "critical")
            self.assertIsInstance(prefix["line"], int)

    def test_namespace_on_another_version_is_reported(self):
        planted = COHERENT.replace("V4DB", "V3DB")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, bootstrap=planted)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "versioning.json").read_text())
            kinds = {f["category"] for f in data["findings"]}
            self.assertEqual(kinds, {"namespace_version_mismatch"})
            self.assertIn("V3DB", data["findings"][0]["summary"])

    def test_a_bootstrap_mounting_no_versioned_file_refuses(self):
        inline_only = COHERENT.replace(
            "require __DIR__.'/../routes/web.v4.php';",
            "$router->get('/', function () { return null; });")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, bootstrap=inline_only)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("REFUSED", result.stderr)

    def test_bootstrap_glob_matching_nothing_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            (repo / "bootstrap" / "app.php").unlink()
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("bootstrapGlob", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
