#!/usr/bin/env python3
"""Tests for DTCG export/import (bin/export_tokens_dtcg.py, bin/import_tokens_dtcg.py).

Every token set here is synthetic. Spec examples are the published 2025.10
examples (https://www.designtokens.org/tr/2025.10/format/), transcribed with
their explanatory comments removed so they are valid JSON.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/dtcg_tokens_test.py"
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
sys.path.insert(0, str(BIN.parents[0]))

from design_suite.engine import dtcg  # noqa: E402

DART = """
class AppTokens {
  static const Color colorPrimary = Color(0xFF0066CC);
  static const Color colorPrimaryDark = Color(0x80003366);
  static const colorAccent = AppTokens.colorPrimary;
  static const space8 = 8.0;
  static const durationFast = Duration(milliseconds: 150);
  static const curveStandard = Curves.easeInOut;
  static const curveCustom = Cubic(0.2, 0.0, 0.0, 1.0);
  static const fontWeightBold = FontWeight.w700;
  static const fontFamilyBody = 'Inter';
  static const insetCard = EdgeInsets.all(16);
}
"""
CSS = """
@theme {
  --color-brand: #0066cc;
  --color-brand-strong: rgb(51 136 221 / 50%);
  --color-link: var(--color-brand);
  --spacing-gutter: 1.5rem;
  --radius-card: 12px;
  --duration-fast: 150ms;
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
  --font-weight-bold: 700;
  --font-sans: "Inter", system-ui, sans-serif;
  --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.5), inset 0 0 4px 1px #00000080;
  --color-fancy: oklch(0.7 0.1 200);
}
"""
SWIFT = """
enum Tokens {
    static let colorPrimary = Color(red: 0, green: 0.4, blue: 0.8)
    static let colorLink = Tokens.colorPrimary
    static let spaceMedium: CGFloat = 16
    static let fontFamilyBody = "Inter"
    static let shadowCard = Shadow(radius: 4)
}
"""
KOTLIN = """
object Tokens {
    val colorPrimary = Color(0xFF0066CC)
    val colorLink = colorPrimary
    val spaceMedium = 16.dp
    val fontWeightBold = FontWeight.Bold
    val opacityDisabled = 0.38f
}
"""
STACKS = {
    "dart": ("tokens.dart", DART, {"insetCard"}),
    "web": ("theme.css", CSS, {"color-fancy"}),
    "tsx": ("theme.css", CSS, {"color-fancy"}),
    "swift": ("Tokens.swift", SWIFT, {"shadowCard"}),
    "kotlin": ("Tokens.kt", KOTLIN, set()),
}


def build(root: Path, lang: str, path: str, text: str, dtcg_path=None):
    (root / ".design-suite").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / path).write_text(text)
    tokens = {"source": {"kind": "file", "path": path}, "accessor": "AppTokens"}
    if dtcg_path:
        tokens["dtcg"] = {"path": dtcg_path}
    (root / ".design-suite" / "profile.json").write_text(json.dumps({
        "adapters": {"lang": lang}, "source": {"root": "src"}, "tokens": tokens}))
    (root / ".design-suite" / "exceptions.json").write_text("{}")


def run(root: Path, script: str, *extra):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(BIN / script), *extra],
                          capture_output=True, text=True, env=env)


class SpecExamples(unittest.TestCase):
    def test_root_tokens_example(self):
        doc = {"color": {"accent": {
            "$root": {"$type": "color", "$value": {"colorSpace": "srgb",
                      "components": [0.867, 0, 0], "hex": "#dd0000"}},
            "light": {"$type": "color", "$value": {"colorSpace": "srgb",
                      "components": [1, 0.267, 0.267], "hex": "#ff4444"}}}}}
        t = dtcg.parse(doc)
        self.assertIn(("color", "accent", "$root"), t)
        ok = dict(doc, alias={"$value": "{color.accent.$root}"})
        self.assertEqual(dtcg.parse(ok)[("alias",)].type, "color")
        with self.assertRaisesRegex(dtcg.DtcgError, "group"):
            dtcg.parse(dict(doc, alias={"$value": "{color.accent}"}))

    def test_shadow_example(self):
        doc = {"drop-shadow": {"$type": "shadow", "$value": {
            "color": {"colorSpace": "srgb", "components": [0, 0, 0], "alpha": 0.5, "hex": "#000000"},
            "offsetX": {"value": 0.5, "unit": "rem"}, "offsetY": {"value": 0.5, "unit": "rem"},
            "blur": {"value": 1.5, "unit": "rem"}, "spread": {"value": 0, "unit": "rem"}}}}
        self.assertEqual(dtcg.parse(doc)[("drop-shadow",)].type, "shadow")

    def test_type_inheritance_and_alias_typing(self):
        doc = {"space": {"$type": "dimension", "sm": {"$value": {"value": 4, "unit": "px"}},
                         "gap": {"$value": "{space.sm}"}}}
        t = dtcg.parse(doc)
        self.assertEqual(t[("space", "gap")].resolved, {"value": 4, "unit": "px"})

    def test_every_checked_type_accepts_a_valid_value(self):
        vals = {"color": {"colorSpace": "srgb", "components": [1, 0, 0]},
                "dimension": {"value": 2, "unit": "rem"}, "duration": {"value": 0.2, "unit": "s"},
                "fontFamily": ["Inter", "sans-serif"], "fontWeight": "semi-bold",
                "cubicBezier": [0.4, 0, 0.2, 1], "number": 1.5}
        doc = {k: {"$type": k, "$value": v} for k, v in vals.items()}
        self.assertEqual(len(dtcg.parse(doc)), len(vals))


class Refusals(unittest.TestCase):
    CASES = {
        "cycle": {"a": {"$type": "number", "$value": "{b}"}, "b": {"$type": "number", "$value": "{a}"}},
        "dangling": {"a": {"$type": "number", "$value": "{nope}"}},
        "no type": {"a": {"$value": 1}},
        "bad unit": {"a": {"$type": "dimension", "$value": {"value": 1, "unit": "em"}}},
        "hex string": {"a": {"$type": "color", "$value": "#ff0000"}},
        "token+children": {"a": {"$type": "number", "$value": 1, "b": {"$value": 2}}},
        "dot in name": {"a.b": {"$type": "number", "$value": 1}},
        "unknown type": {"a": {"$type": "colour", "$value": 1}},
        "json pointer": {"a": {"$type": "number", "$ref": "#/b/$value"}},
        "extends": {"g": {"$extends": "{h}"}},
        "weight range": {"a": {"$type": "fontWeight", "$value": 1200}},
        "bezier x": {"a": {"$type": "cubicBezier", "$value": [1.5, 0, 0, 1]}},
        "not object": [1, 2],
    }

    def test_each_malformed_document_is_refused(self):
        for label, doc in self.CASES.items():
            with self.subTest(label), self.assertRaises(dtcg.DtcgError):
                dtcg.parse(doc)

    def test_draft_forms_accepted_only_when_asked(self):
        doc = {"c": {"type": "color", "value": "#ff0000"},
               "d": {"$type": "dimension", "$value": "16px"}}
        with self.assertRaises(dtcg.DtcgError):
            dtcg.parse(doc)
        t = dtcg.parse(doc, legacy=True)
        self.assertEqual(t[("c",)].resolved["hex"], "#ff0000")
        self.assertEqual(t[("d",)].resolved, {"value": 16, "unit": "px"})

    def test_cli_refuses_malformed_file_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "dart", "tokens.dart", DART)
            (root / "bad.tokens.json").write_text("{not json")
            r = run(root, "import_tokens_dtcg.py", "--file", "bad.tokens.json")
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("not valid JSON", r.stderr)
            (root / "bad.tokens.json").write_text(json.dumps(self.CASES["cycle"]))
            r = run(root, "import_tokens_dtcg.py", "--file", "bad.tokens.json")
            self.assertEqual(r.returncode, 2)
            self.assertIn("circular", r.stderr)

    def test_cli_refuses_without_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "dart", "tokens.dart", DART)
            r = run(root, "import_tokens_dtcg.py")
            self.assertEqual(r.returncode, 2)
            self.assertIn("tokens.dtcg.path", r.stderr)

    def test_export_refuses_a_js_tailwind_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "tsx", "tailwind.config.js", "module.exports = {theme: {}}")
            r = run(root, "export_tokens_dtcg.py")
            self.assertEqual(r.returncode, 2)
            self.assertIn("never executed", r.stderr)


class RoundTrip(unittest.TestCase):
    def test_export_is_valid_and_reimports_with_zero_drift_per_stack(self):
        for lang, (path, text, unrepresentable) in STACKS.items():
            with self.subTest(lang), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                build(root, lang, path, text, dtcg_path="out.tokens.json")
                preview = run(root, "export_tokens_dtcg.py")
                self.assertFalse((root / "out.tokens.json").exists(), "preview wrote a file")
                exp = run(root, "export_tokens_dtcg.py", "--out", "out.tokens.json")
                self.assertEqual(exp.returncode, 1 if unrepresentable else 0, exp.stderr)
                self.assertEqual(preview.stdout, (root / "out.tokens.json").read_text())
                doc = json.loads((root / "out.tokens.json").read_text())
                dtcg.parse(doc)
                listed = set(doc["$extensions"]["io.github.irfan-dahir.design-suite"]["unrepresentable"])
                self.assertEqual(listed, unrepresentable)
                for name in unrepresentable:
                    self.assertIn(name, exp.stderr)
                imp = run(root, "import_tokens_dtcg.py", "--json")
                rep = json.loads(imp.stdout)
                for k in ("missing_in_code", "missing_in_file", "value_mismatch", "ambiguous"):
                    self.assertEqual(rep[k], [], f"{lang} {k}")
                self.assertEqual({u["name"] for u in rep["uncomparable"]}, unrepresentable)
                self.assertEqual(imp.returncode, 1 if unrepresentable else 0)

    def test_aliases_and_types_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "web", "theme.css", CSS)
            doc = json.loads(run(root, "export_tokens_dtcg.py").stdout)
            self.assertEqual(doc["color"]["link"]["$value"], "{color.brand.$root}")
            self.assertEqual(doc["color"]["brand"]["strong"]["$value"]["alpha"], 0.5)
            types = {t.type for t in dtcg.parse(doc).values()}
            self.assertTrue({"color", "dimension", "duration", "cubicBezier", "fontWeight",
                             "fontFamily", "shadow"} <= types, types)
            shadow = doc["shadow"]["card"]["$value"]
            self.assertTrue(shadow[1]["inset"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "dart", "tokens.dart", DART)
            doc = json.loads(run(root, "export_tokens_dtcg.py").stdout)
            self.assertEqual(doc["color"]["accent"]["$value"], "{color.primary.$root}")
            self.assertEqual(doc["curve"]["standard"]["$value"], [0.42, 0.0, 0.58, 1.0])
            self.assertEqual(doc["duration"]["fast"]["$value"], {"value": 150, "unit": "ms"})


class Drift(unittest.TestCase):
    def test_planted_mismatches_are_each_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "web", "theme.css", CSS, dtcg_path="figma.tokens.json")
            run(root, "export_tokens_dtcg.py", "--out", "figma.tokens.json")
            doc = json.loads((root / "figma.tokens.json").read_text())
            doc["color"]["brand"]["$root"]["$value"] = {"colorSpace": "srgb",
                                                       "components": [1, 0, 0], "hex": "#ff0000"}
            doc["duration"]["fast"]["$value"] = {"value": 0.2, "unit": "s"}
            del doc["radius"]
            doc["space"] = {"huge": {"$type": "dimension", "$value": {"value": 64, "unit": "px"}}}
            (root / "figma.tokens.json").write_text(json.dumps(doc))
            r = run(root, "import_tokens_dtcg.py", "--json")
            self.assertEqual(r.returncode, 1, r.stderr)
            rep = json.loads(r.stdout)
            mism = {m["name"] for m in rep["value_mismatch"]}
            # color-link aliases color-brand on both sides, so it drifts too.
            self.assertEqual(mism, {"color-brand", "color-link", "duration-fast"})
            self.assertEqual([m["name"] for m in rep["missing_in_file"]], ["radius-card"])
            self.assertEqual([m["token"] for m in rep["missing_in_code"]], ["space.huge"])
            self.assertFalse((root / ".design-suite" / "dtcg-drift.json").exists())

    def test_equal_values_in_different_units_are_not_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "web", "theme.css", "@theme { --duration-fast: 150ms; }")
            (root / "f.tokens.json").write_text(json.dumps(
                {"duration": {"fast": {"$type": "duration", "$value": {"value": 0.15, "unit": "s"}}}}))
            r = run(root, "import_tokens_dtcg.py", "--file", "f.tokens.json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_write_report_only_with_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "kotlin", "Tokens.kt", KOTLIN, dtcg_path="t.tokens.json")
            run(root, "export_tokens_dtcg.py", "--out", "t.tokens.json")
            r = run(root, "import_tokens_dtcg.py", "--write-report")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((root / ".design-suite" / "dtcg-drift.json").is_file())


if __name__ == "__main__":
    unittest.main()
