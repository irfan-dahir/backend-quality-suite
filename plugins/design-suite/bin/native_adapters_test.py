#!/usr/bin/env python3
"""Planted-violation tests for the `swift` and `kotlin` adapters. Stdlib-only.

Every audit the adapters claim is exercised three ways, per language:
  * planted violations  -> exit 1, and the planted count is asserted;
  * a clean control     -> exit 0, paired with the same project emptied of
                           sources exiting 2 (a 0 over 0 files proves nothing);
  * an unsupported capability -> exit 2, named — never 0, never a traceback.

Plus survey detection: Package.swift / *.xcodeproj -> swift; a Gradle build
that enables Compose -> kotlin; a plain Gradle build -> no adapter.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/native_adapters_test.py"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
BIN = PLUGIN / "bin"
sys.path.insert(0, str(PLUGIN))

from design_suite.adapters import kotlin, swift  # noqa: E402
from design_suite.adapters.base import AdapterContext  # noqa: E402
from design_suite.engine.scan import scan_source  # noqa: E402

CTX = AdapterContext(repo=Path("."), profile={}, exceptions={})


def kinds(mod, rel, source):
    return sorted(f["kind"] for f in scan_source(rel, source, mod.checks(CTX)))


SWIFT_PLANTED = """import SwiftUI
import DataRepositories

struct HomeView: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("Hi")
                .padding(16)
                .padding(.horizontal, 20)
                .foregroundColor(Color(red: 0.2, green: 0.4, blue: 1.0))
                .background(Color(hex: "#FF0000"))
            RoundedRectangle(cornerRadius: 10)
        }
        .cornerRadius(8)
        .animation(.easeInOut(duration: 0.3), value: flag)
    }
}
"""
SWIFT_CLEAN = """import SwiftUI

extension Color {
    static let brand = Color(red: 0.2, green: 0.4, blue: 1.0)
}

struct HomeView: View {
    @Environment(\\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        // .padding(16) in a comment is documentation
        VStack(spacing: Spacing.md) {
            Text("Hi").padding(Spacing.lg).padding(0)
                .foregroundColor(.brand)
        }
        .cornerRadius(Radius.md)
        .animation(reduceMotion ? nil : Motion.standard, value: flag)
    }
}
"""
KOTLIN_PLANTED = """package com.x.screens

import androidx.compose.runtime.Composable
import androidx.compose.animation.core.animateFloatAsState
import com.x.data.repositories.Repo

@Composable
fun Home() {
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Hi", color = Color(0xFF6200EE), fontSize = 14.sp)
        Box(Modifier.clip(RoundedCornerShape(12.dp)))
        val alpha by animateFloatAsState(1f, animationSpec = tween(durationMillis = 300))
    }
}
"""
KOTLIN_CLEAN = """package com.x.screens

import androidx.compose.runtime.Composable

val Purple80 = Color(0xFFD0BCFF)

object Spacing {
    val md = 16.dp
}

@Composable
fun Home() {
    val reduceMotion = LocalReduceMotion.current
    // padding(16.dp) in a comment is documentation
    Column(Modifier.padding(Spacing.md).padding(0.dp)) {
        Text("Hi", color = MaterialTheme.colorScheme.primary)
        val alpha by animateFloatAsState(1f, animationSpec = if (reduceMotion) snap() else Motion.standard)
    }
}
"""


class SwiftChecks(unittest.TestCase):
    def test_planted(self):
        self.assertEqual(kinds(swift, "V.swift", SWIFT_PLANTED),
                         ["border_radius", "border_radius", "color", "color", "duration",
                          "spacing", "spacing", "spacing"])

    def test_clean(self):
        self.assertEqual(kinds(swift, "V.swift", SWIFT_CLEAN), [])

    def test_uikit(self):
        src = ("    v.backgroundColor = UIColor(red: 1, green: 0, blue: 0, alpha: 1)\n"
               "    v.layer.cornerRadius = 6\n    UIView.animate(withDuration: 0.25) { }\n"
               "    let i = UIEdgeInsets(top: 8, left: 0, bottom: 0, right: 0)\n")
        self.assertEqual(kinds(swift, "V.swift", "func f() {\n" + src + "}\n"),
                         ["border_radius", "color", "duration", "spacing"])

    def test_zero_insets_are_not_findings(self):
        self.assertEqual(kinds(swift, "V.swift", "func f() {\n    EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0)\n}\n"), [])

    def test_local_color_in_view_is_reported(self):
        self.assertEqual(kinds(swift, "V.swift", "func f() {\n    let c = Color(white: 0.5)\n}\n"),
                         ["color"])

    def test_palette_definition_sites_are_not_findings(self):
        # Item: theme/palette files reported as findings. Recognised by the
        # enclosing declaration, so the file name is deliberately neutral.
        src = (
            "import SwiftUI\n"
            "extension Color {\n"
            "    static var primary: Color { Color(red: 0.1, green: 0.2, blue: 0.3) }\n"
            "    init(brandHex: String) { self.init(hex: \"#FF0000\") }\n"
            "}\n"
            "extension UIColor {\n"
            "    static let accent =\n"
            "        UIColor(red: 0.9, green: 0.1, blue: 0.1, alpha: 1)\n"
            "}\n"
            "struct ColorSet {\n"
            "    let background = Color(white: 0.95)\n"
            "    static let shared = ColorSet()\n"
            "}\n"
            "enum Palette {\n"
            "    case a, b\n"
            "    var color: Color {\n"
            "        switch self {\n"
            "        case .a: return Color(red: 1, green: 0, blue: 0)\n"
            "        case .b: return Color(white: 0.2)\n"
            "        }\n"
            "    }\n"
            "}\n")
        self.assertEqual(kinds(swift, "Anything.swift", src), [])

    def test_palette_recognition_keeps_true_positives(self):
        src = (
            "struct HomeView: View {\n"
            "    let accent = Color(white: 0.4)\n"
            "    var tint: Color { Color(red: 1, green: 0, blue: 0) }\n"
            "    var body: some View {\n"
            "        Text(\"x\").foregroundColor(Color(red: 0.2, green: 0.4, blue: 1.0))\n"
            "    }\n"
            "}\n"
            "final class VC: UIViewController {\n"
            "    let tint = UIColor(white: 0.1, alpha: 1)\n"
            "    func viewDidLoad() { view.backgroundColor = UIColor(red: 1, green: 1, blue: 1, alpha: 1) }\n"
            "}\n"
            "struct Palette {\n"
            "    func make() -> Color { Color(white: 0.3) }\n"
            "}\n")
        self.assertEqual(kinds(swift, "ColorSet.swift", src), ["color"] * 6)

    def test_imports(self):
        targets = [m.group(1) for m in swift.IMPORT_RE.finditer(
            "import SwiftUI\n@testable import Core\nimport struct Data.Repo\n")]
        self.assertEqual(targets, ["SwiftUI", "Core", "Data.Repo"])


class KotlinChecks(unittest.TestCase):
    def test_planted(self):
        self.assertEqual(kinds(kotlin, "H.kt", KOTLIN_PLANTED),
                         ["border_radius", "color", "duration", "font_size", "spacing", "spacing"])

    def test_clean(self):
        self.assertEqual(kinds(kotlin, "H.kt", KOTLIN_CLEAN), [])

    def test_local_val_in_composable_is_reported(self):
        src = "@Composable\nfun A() {\n    val c = Color(0xFF00FF00)\n}\n"
        self.assertEqual(kinds(kotlin, "A.kt", src), ["color"])

    def test_sizes_are_not_spacing(self):
        src = ("@Composable\nfun A() {\n"
               "    Box(Modifier.size(200.dp).width(120.dp).height(48.dp))\n"
               "    Card(elevation = CardDefaults.cardElevation(4.dp), border = BorderStroke(1.dp, c)) {}\n"
               "    Icon(i, null, Modifier.requiredSize(24.dp))\n"
               "}\n")
        self.assertEqual(kinds(kotlin, "A.kt", src), [])

    def test_spacing_contexts_survive(self):
        src = ("@Composable\nfun A() {\n"
               "    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {}\n"
               "    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {}\n"
               "    Spacer(Modifier.height(4.dp))\n"
               "    Box(Modifier.offset(x = 2.dp).size(10.dp))\n"
               "    LazyColumn(contentPadding = PaddingValues(all = 20.dp)) {}\n"
               "    Foo(itemSpacing = 6.dp)\n"
               "}\n")
        self.assertEqual(kinds(kotlin, "A.kt", src), ["spacing"] * 7)

    def test_radius_dp_is_not_double_counted_as_spacing(self):
        src = "fun a() {\n  Box(Modifier.clip(RoundedCornerShape(topStart = 8.dp)))\n}\n"
        self.assertEqual(kinds(kotlin, "A.kt", src), ["border_radius"])

    def test_imports(self):
        targets = [m.group(1) for m in kotlin.IMPORT_RE.finditer(
            "import a.b.C\nimport a.b.*\nimport x.Y as Z\n")]
        self.assertEqual(targets, ["a.b.C", "a.b.*", "x.Y"])


LAYOUT = {
    "swift": ("Sources", "Sources/App/Screens/HomeView.swift", "Sources/App/UI/Button.swift"),
    "kotlin": ("app/src", "app/src/main/java/com/x/screens/Home.kt",
               "app/src/main/java/com/x/ui/Button.kt"),
}
SOURCES = {"swift": (SWIFT_PLANTED, SWIFT_CLEAN), "kotlin": (KOTLIN_PLANTED, KOTLIN_CLEAN)}
ANIMATED = [".animation", "withAnimation", "animateFloatAsState", "AnimatedVisibility"]
ARCH = {
    "adapterPattern": {"bannedImports": [{"label": "data layer",
                                          "pattern": r"[Dd]ata\.?[Rr]epositories"}],
                       "screensGlob": "**/[Ss]creens/**/*"},
    "layerBoundaries": {"rules": [{"label": "ui", "fromGlob": "Sources/App/UI/**",
                                   "mustNotImport": "Sources/Data/**"}]},
    "promotionCandidates": {"plumbingParams": ["key"], "noiseParamSets": [],
                            "baseline": ".design-suite/b.json"},
    "apiConsistency": {"scope": ["**/*.swift", "**/*.kt"], "checks": {}},
    "unusedTokens": {"categories": {"spacing": "Spacing"}},
}


def make(lang: str, planted: bool) -> Path:
    src_root, screen, ui = LAYOUT[lang]
    root = Path(tempfile.mkdtemp(prefix=f"native-{lang}-"))
    body = SOURCES[lang][0 if planted else 1]
    for rel, text in ((screen, body), (ui, "// empty\n")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    ds = root / ".design-suite"
    ds.mkdir()
    (ds / "profile.json").write_text(json.dumps({
        "profileVersion": 1, "project": {"name": "fixture"}, "adapters": {"lang": lang},
        "source": {"root": src_root}, "pipelines": {"tokens": ".design-suite/out"},
        "audits": {"archRulesFile": ".design-suite/arch-rules.json",
                   "configFile": ".design-suite/audit.json"}}))
    (ds / "audit.json").write_text(json.dumps(
        {"token_categories": {"motion": {"animated_widgets": ANIMATED}}}))
    (ds / "arch-rules.json").write_text(json.dumps(ARCH))
    return root


def run(script: str, root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(BIN / script)], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)


class EndToEnd(unittest.TestCase):
    def test_tokens(self):
        expect = {"swift": 8, "kotlin": 6}
        for lang in LAYOUT:
            with self.subTest(lang=lang, case="planted"):
                root = make(lang, True)
                r = run("audit_tokens.py", root)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                out = json.loads((root / ".design-suite/tokens-findings.json").read_text())
                self.assertEqual(len(out), expect[lang], out)
            with self.subTest(lang=lang, case="clean"):
                r = run("audit_tokens.py", make(lang, False))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_reduced_motion(self):
        for lang in LAYOUT:
            with self.subTest(lang=lang, case="planted"):
                r = run("audit_reduced_motion.py", make(lang, True))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            with self.subTest(lang=lang, case="clean"):
                r = run("audit_reduced_motion.py", make(lang, False))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_clean_exit_0_is_not_an_empty_sweep(self):
        # Exit 0 on the clean control means something only if an empty sweep
        # refuses: delete the sources and the same project must exit 2.
        for lang in LAYOUT:
            for script in ("audit_tokens.py", "audit_reduced_motion.py"):
                with self.subTest(lang=lang, script=script):
                    root = make(lang, False)
                    for rel in LAYOUT[lang][1:]:
                        (root / rel).unlink()
                    r = run(script, root)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_reduced_motion_counts_uses_not_imports(self):
        for lang in LAYOUT:
            with self.subTest(lang=lang):
                root = make(lang, True)
                run("audit_reduced_motion.py", root)
                found = json.loads((root / ".design-suite/reduced-motion-findings.json").read_text())
                found = found if isinstance(found, list) else found.get("findings", [])
                self.assertEqual(len(found), 1, found)

    def test_reduced_motion_unconfigured_refuses(self):
        for lang in LAYOUT:
            with self.subTest(lang=lang):
                root = make(lang, True)
                (root / ".design-suite/audit.json").write_text("{}")
                r = run("audit_reduced_motion.py", root)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_adapter_pattern(self):
        for lang in LAYOUT:
            with self.subTest(lang=lang, case="planted"):
                r = run("audit_adapter_pattern.py", make(lang, True))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(r.stdout, r"[Dd]ata\.?[Rr]epositories")
            with self.subTest(lang=lang, case="clean"):
                r = run("audit_adapter_pattern.py", make(lang, False))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unsupported_capabilities_refuse(self):
        scripts = ("audit_layer_boundaries.py", "audit_focus_order.py", "audit_semantics.py",
                   "audit_promotion_candidates.py", "audit_api_consistency.py",
                   "audit_unused_tokens.py")
        for lang in LAYOUT:
            root = make(lang, True)
            for script in scripts:
                with self.subTest(lang=lang, script=script):
                    r = run(script, root)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertNotIn("Traceback", r.stderr)


class Survey(unittest.TestCase):
    def survey(self, files: dict) -> dict:
        root = Path(tempfile.mkdtemp(prefix="native-survey-"))
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        r = subprocess.run([sys.executable, str(BIN / "survey.py"), "--project-root", str(root),
                            "--stdout"], capture_output=True, text=True, timeout=60)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        return json.loads(r.stdout)["stack"]

    def test_package_swift(self):
        s = self.survey({"Package.swift": "// swift-tools-version:5.9\n",
                         "Sources/App/V.swift": "import SwiftUI\n"})
        self.assertEqual(s["candidateAdapter"], "swift")

    def test_xcodeproj(self):
        s = self.survey({"App/V.swift": "import SwiftUI\n",
                         "Demo.xcodeproj/project.pbxproj": "// !$*UTF8*$!\n"})
        self.assertEqual(s["candidateAdapter"], "swift")

    def test_gradle_compose(self):
        s = self.survey({"build.gradle.kts": "plugins {}\n",
                         "app/build.gradle.kts": "android { buildFeatures { compose = true } }\n",
                         "app/src/main/java/A.kt": "fun a() {}\n"})
        self.assertEqual(s["candidateAdapter"], "kotlin")
        self.assertEqual(s["adapterRefinement"]["to"], "kotlin")

    def test_plain_gradle_gets_no_adapter(self):
        s = self.survey({"build.gradle.kts": "plugins { kotlin(\"jvm\") }\n",
                         "src/main/kotlin/A.kt": "fun a() {}\n"})
        self.assertIsNone(s["candidateAdapter"])

    def test_every_adapter_reachable(self):
        sys.path.insert(0, str(BIN))
        import survey  # noqa: E402
        self.assertEqual(survey.adapter_reachability(), [])


if __name__ == "__main__":
    unittest.main()
