#!/usr/bin/env python3
"""audit_error_shape: the bypass, the dropped key, and the empty-config refusals.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_shape_test.py"

Both defect classes are planted against the other direction's clean control,
because an envelope audit that only ever sees healthy handlers cannot tell
its own wiring from a no-op.
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
SCRIPT = "audit_error_shape"

PROFILE = {
    "profileVersion": 1,
    "project": {"name": "Fixture"},
    "audits": {"archRulesFile": ".backend-suite/arch-rules.json"},
}

RULES = {
    "errorShape": {
        "handlerGlob": "app/Exceptions/Handler.php",
        "envelopeKeys": ["status", "type", "message", "error"],
        "sourceGlob": "app/**/*.php",
        "bypassPattern": r"response\(\)->json\(\[[^;]*,\s*[45]\d\d\s*\)",
    },
}

HANDLER = """<?php

class Handler
{
    private function payload(string $type, string $message)
    {
        return [
            'status' => 500,
            'type' => $type,
            'message' => $message,
            'error' => true,
        ];
    }
}
"""

CONTROLLER_OK = """<?php

class OkController
{
    public function main()
    {
        return response()->json(['ok' => true]);
    }
}
"""

CONTROLLER_BYPASS = """<?php

class BypassController
{
    public function main()
    {
        return response()->json(['error' => 'boom'], 500);
    }
}
"""


def run(args: list[str], repo: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    return subprocess.run([sys.executable, str(BIN / f"{SCRIPT}.py"), *args],
                          capture_output=True, text=True, env=env)


def build(tmp: str, *, handler: str = HANDLER,
          controller: str = CONTROLLER_OK,
          controller_file: str = "OkController.php",
          rules: dict | None = None) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "app" / "Exceptions").mkdir(parents=True)
    (repo / "app" / "Http").mkdir(parents=True)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps(PROFILE))
    (repo / ".backend-suite" / "arch-rules.json").write_text(
        json.dumps(rules or RULES))
    (repo / "app" / "Exceptions" / "Handler.php").write_text(handler)
    (repo / "app" / "Http" / controller_file).write_text(controller)
    return repo


class ErrorShape(unittest.TestCase):
    def test_direct_error_response_and_dropped_key_reach_the_envelope(self):
        stripped = HANDLER.replace("            'status' => 500,\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, handler=stripped,
                         controller=CONTROLLER_BYPASS,
                         controller_file="BypassController.php")
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "error-shape.json").read_text())
            self.assertEqual(data["audit"], "error-shape")
            categories = {f["category"] for f in data["findings"]}
            self.assertEqual(categories,
                             {"envelope_key_missing", "error_shape_bypass"})
            missing = [f for f in data["findings"]
                       if f["category"] == "envelope_key_missing"]
            self.assertIn("'status'", missing[0]["summary"])
            bypass = [f for f in data["findings"]
                      if f["category"] == "error_shape_bypass"]
            self.assertEqual(bypass[0]["file"],
                             "app/Http/BypassController.php")
            self.assertIsInstance(bypass[0]["line"], int)
            # A caller-visible contract drift is request-time critical.
            self.assertEqual(bypass[0]["severity"], "critical")

    def test_envelope_kept_and_no_bypass_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp)
            result = run(["--findings"], repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(
                (repo / ".backend-suite" / "findings" /
                 "error-shape.json").read_text())
            self.assertEqual(data["findings"], [])
            self.assertGreaterEqual(data["scanned"], 2)

    def test_empty_envelope_keys_refuse(self):
        rules = json.loads(json.dumps(RULES))
        rules["errorShape"]["envelopeKeys"] = []
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, rules=rules)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("envelopeKeys", result.stderr)

    def test_handler_glob_matching_nothing_refuses(self):
        rules = json.loads(json.dumps(RULES))
        rules["errorShape"]["handlerGlob"] = "app/Exceptions/Nope.php"
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, rules=rules)
            result = run([], repo)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("handlerGlob", result.stderr)

    def test_success_responses_are_not_mistaken_for_bypasses(self):
        """The pattern targets error statuses; a 200 json response is not a
        shape violation, and reporting it would train the finding away."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = build(tmp, controller=CONTROLLER_OK)
            result = run([], repo)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
