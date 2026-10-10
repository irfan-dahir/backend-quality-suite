#!/usr/bin/env python3
"""Refusals are exit 2, findings are exit 1, and nothing exits 0 over an
unscanned tree — measured on one synthetic project per stack.

Before this fix, on every non-Dart stack:
  * audit_adapter_pattern swept `*/presentation/pages/**/*.dart`, scanned
    nothing, printed "no violations found" and exited 0 (silently wrong);
  * audit_layer_boundaries crashed `KeyError: 'from'` (exit 1, read as findings)
    on the arch-rules.json init.py scaffolds;
  * arch.load on a missing section, and the string `SystemExit("...")` refusals
    in five audits, exited 1;
  * audit_mock_api raised FileNotFoundError (exit 1) with no mock-API config.

Each stack fixture plants a real violation, so the "supported" rows prove the
check still finds it (exit 1) rather than that it merely stopped crashing.
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
PLUGIN = BIN.parent

ADAPTER_RULE = {"bannedImports": [{"label": "data layer", "pattern": r"data/repositories"}]}
LAYER_RULE = {"rules": [{"label": "ui must not import data", "fromGlob": "src/ui/**",
                         "mustNotImport": "src/data/**"}],
              "baseline": ".design-suite/baselines/layer-boundaries.json"}

# stack -> (adapters.lang or None, fileGlob, {path: content}); each plants a
# screen that imports the data layer and a ui file that imports src/data.
STACKS = {
    "dart": ("dart", "**/*.dart", {
        "pubspec.yaml": "name: demo_app\n",
        "lib/features/home/presentation/pages/home_page.dart":
            "import 'package:demo_app/features/home/data/repositories/repo.dart';\n",
        "src/ui/button.dart": "import '../data/api.dart';\n",
        "src/data/api.dart": "class Api {}\n",
    }),
    "tsx": ("tsx", "**/*.tsx", {
        "src/pages/Home.tsx": "import { repo } from '../data/repositories/repo';\n",
        "src/ui/Button.tsx": "import { api } from '../data/api';\n",
        "src/data/api.ts": "export const api = 1;\n",
    }),
    "vue": ("web", "**/*.vue", {
        "src/pages/Home.vue": "<script setup>\nimport repo from '../data/repositories/repo'\n</script>\n",
        "src/ui/Button.vue": "<script>\nimport api from '../data/api'\n</script>\n",
        "src/data/api.js": "export default 1\n",
    }),
    "css": ("web", "**/*.css", {
        "src/pages/home.css": "@import '../data/repositories/theme.css';\n",
        "src/ui/button.css": "@import '../data/palette.css';\n",
        "src/data/palette.css": ":root{}\n",
    }),
    "swift": ("swift", "**/*.swift", {
        "Sources/pages/Home.swift": "import DataRepositories\n",
        "src/ui/Button.swift": "import Data\n",
    }),
    "kotlin": ("kotlin", "**/*.kt", {
        "app/src/pages/Home.kt": "import com.x.data.repositories.Repo\n",
        "src/ui/Button.kt": "import com.x.data.Api\n",
    }),
    # A stack with no adapter at all: profile names none.
    "cobol": (None, "**/*.cob", {"src/pages/HOME.cob": "COPY DATAREPO.\n"}),
}


def make(stack: str, *, arch: dict | None, lang_override=..., extra_profile=None) -> Path:
    lang, glob, files = STACKS[stack]
    if lang_override is not ...:
        lang = lang_override
    root = Path(tempfile.mkdtemp(prefix=f"refusal-{stack}-"))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    profile = {"project": {"name": "demo"}, "source": {"root": ".", "fileGlob": glob},
               "audits": {"archRulesFile": ".design-suite/arch-rules.json"}}
    if lang:
        profile["adapters"] = {"lang": lang}
    profile.update(extra_profile or {})
    (root / ".design-suite").mkdir(exist_ok=True)
    (root / ".design-suite/profile.json").write_text(json.dumps(profile))
    if arch is not None:
        (root / ".design-suite/arch-rules.json").write_text(json.dumps(arch))
    return root


def run(script: str, root: Path, *args) -> subprocess.CompletedProcess:
    path = BIN / script if (BIN / script).is_file() else PLUGIN / script
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(path), *args], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)


SCAFFOLD = json.loads(
    (PLUGIN / "templates/dot-design-suite/arch-rules.json.template").read_text())


class AdapterPattern(unittest.TestCase):
    def test_planted_violation_found_on_every_supported_stack(self):
        for stack, scope in (("dart", None), ("tsx", "**/pages/**/*"),
                             ("vue", "**/pages/**/*"), ("css", "**/pages/**/*")):
            with self.subTest(stack=stack):
                rule = dict(ADAPTER_RULE)
                if scope:
                    rule["screensGlob"] = scope
                root = make(stack, arch={"adapterPattern": rule})
                if stack == "dart":
                    (root / ".design-suite/arch-rules.json").write_text(json.dumps(
                        {"adapterPattern": {**rule, "screensDir": "lib/features"}}))
                r = run("audit_adapter_pattern.py", root)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("data/repositories", r.stdout)

    def test_non_dart_stack_without_scope_refuses_instead_of_clean(self):
        for stack in ("tsx", "vue", "css"):
            with self.subTest(stack=stack):
                r = run("audit_adapter_pattern.py", make(stack, arch={"adapterPattern": ADAPTER_RULE}))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("screensGlob", r.stderr)
                self.assertNotIn("no violations", r.stdout)

    def test_zero_files_in_scope_refuses(self):
        rule = {**ADAPTER_RULE, "screensGlob": "**/nowhere/**/*"}
        r = run("audit_adapter_pattern.py", make("tsx", arch={"adapterPattern": rule}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("nothing in scope was scanned", r.stderr)

    def test_unadapted_stack_refuses(self):
        r = run("audit_adapter_pattern.py", make("cobol", arch={"adapterPattern": ADAPTER_RULE}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("adapters.lang", r.stderr)

    def test_module_import_stacks_find_planted_violation(self):
        # swift/kotlin imports are module/package names; the banned pattern is
        # a regex over the target, so it still matches.
        rule = {"bannedImports": [{"label": "data layer", "pattern": r"[Dd]ata\.?[Rr]epositories"}],
                "screensGlob": "**/pages/**/*"}
        for stack in ("swift", "kotlin"):
            with self.subTest(stack=stack):
                r = run("audit_adapter_pattern.py", make(stack, arch={"adapterPattern": rule}))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_scaffolded_placeholder_refuses(self):
        r = run("audit_adapter_pattern.py", make("tsx", arch=SCAFFOLD))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("TODO", r.stderr)

    def test_missing_section_refuses_with_2(self):
        r = run("audit_adapter_pattern.py", make("tsx", arch={"other": {}}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no 'adapterPattern' section", r.stderr)


class LayerBoundaries(unittest.TestCase):
    def test_planted_violation_found_on_every_supported_stack(self):
        for stack in ("dart", "tsx", "vue", "css"):
            with self.subTest(stack=stack):
                r = run("audit_layer_boundaries.py", make(stack, arch={"layerBoundaries": LAYER_RULE}))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("src/data/", r.stdout)

    def test_scaffolded_rules_refuse_not_keyerror(self):
        r = run("audit_layer_boundaries.py", make("tsx", arch=SCAFFOLD))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("KeyError", r.stderr)
        self.assertIn("TODO placeholders", r.stderr)

    def test_empty_layer_refuses(self):
        rule = {**LAYER_RULE, "rules": [{**LAYER_RULE["rules"][0], "fromGlob": "src/nope/**"}]}
        r = run("audit_layer_boundaries.py", make("tsx", arch={"layerBoundaries": rule}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_unadapted_and_module_import_stacks_refuse(self):
        # cobol: no adapter. swift/kotlin: imports name modules, not paths, so a
        # path-rooted layer rule cannot match — refusal, never a clean 0.
        for stack in ("cobol", "swift", "kotlin"):
            with self.subTest(stack=stack):
                r = run("audit_layer_boundaries.py", make(stack, arch={"layerBoundaries": LAYER_RULE}))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)


class MiscodedRefusals(unittest.TestCase):
    """Each previously exit-1 cannot-determine path now exits 2, named."""

    def test_arch_rules_missing_section(self):
        for script in ("audit_unused_tokens.py", "audit_unwired_roles.py",
                       "audit_error_handling.py", "audit_api_consistency.py"):
            with self.subTest(script=script):
                r = run(script, make("tsx", arch={"unrelated": {}}))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("REFUSED", r.stderr)

    def test_arch_rules_file_undeclared(self):
        root = make("tsx", arch=None, extra_profile={"audits": {}})
        r = run("audit_layer_boundaries.py", root)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("archRulesFile", r.stderr)

    def test_pattern_adoption_unconfigured(self):
        r = run("audit_pattern_adoption.py", make("tsx", arch=None))
        self.assertIn(r.returncode, (2,), r.stdout + r.stderr)

    def test_mock_api_without_config(self):
        r = run("design_suite/engine/mockapi/audit_mock_api.py", make("tsx", arch=None))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("FileNotFoundError", r.stderr)
        self.assertIn("mock-API config", r.stderr)


# --- audit_error_handling: syntax comes from the adapter ---------------------
# Before: the catch / type-test / interpolation regexes were Dart literals, so a
# TS project with its errorHandling vocabulary filled in matched nothing and
# exited 0 over a planted leak.
def _eh_vocab(suffix: str) -> dict:
    return {"errorHandling": {
        "exception_type": "AppError",
        "guard_call": "guardApiCall",
        "client_call_pattern": r"\bhttp\.(?:get|post)\s*\(",
        "error_state_widget": "ErrorState",
        "error_message_field": "errorMessage",
        "state_class_pattern": r"^(?:export\s+)?class\s+(\w+Failed)\b",
        "state_file_suffix": suffix,
        "pages_marker": "/pages/",
    }}


EH_STACKS = {
    # stack -> (lang, glob, suffix, clean files, planted {path: content})
    "dart": ("dart", "**/*.dart", "_state.dart", {
        "lib/x_bloc.dart": ("void f() async {\n  try { await guardApiCall(() => http.get('u')); }\n"
                            "  catch (e) { emit(msg(e is AppError ? e.message : e.toString())); }\n}\n"),
    }, {
        "lib/y_bloc.dart": "void g() {\n  try { x(); } catch (e) {\n    show('failed: $e');\n  }\n}\n",
    }),
    "tsx": ("tsx", "**/*.ts*", ".state.ts", {
        "src/api.ts": ("export async function f() {\n  try { return await guardApiCall(() => http.get('u')); }\n"
                       "  catch (e) { return e instanceof AppError ? e.message : String(e); }\n}\n"),
    }, {
        "src/load.ts": "export async function g() {\n  try { await x(); } catch (e) {\n    toast(`failed: ${e}`);\n  }\n}\n",
        "src/raw.ts": "export const h = () => http.get('/u');\n",
    }),
}


def _eh_project(stack: str, *, planted: bool) -> Path:
    lang, glob, suffix, clean, bad = EH_STACKS[stack]
    root = Path(tempfile.mkdtemp(prefix=f"eh-{stack}-"))
    for rel, text in {**clean, **(bad if planted else {})}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    (root / ".design-suite").mkdir()
    (root / ".design-suite/profile.json").write_text(json.dumps({
        "project": {"name": "demo"}, "adapters": {"lang": lang},
        "source": {"root": ".", "fileGlob": glob},
        "audits": {"archRulesFile": ".design-suite/arch-rules.json"}}))
    (root / ".design-suite/arch-rules.json").write_text(json.dumps(_eh_vocab(suffix)))
    return root


class ErrorHandlingIsStackAware(unittest.TestCase):
    def test_planted_violation_found_per_supported_stack(self):
        for stack in EH_STACKS:
            with self.subTest(stack=stack):
                r = run("audit_error_handling.py", _eh_project(stack, planted=True))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("to_string", (r.stdout + r.stderr).replace("toString", "to_string"))

    def test_tsx_unguarded_call_is_critical(self):
        r = run("audit_error_handling.py", _eh_project("tsx", planted=True))
        self.assertIn("src/raw.ts", r.stderr)

    def test_tsx_leak_dart_patterns_never_saw(self):
        # Measured: exited 0 ("0 advisory") before the adapter owned the syntax.
        root = _eh_project("tsx", planted=False)
        (root / "src/load.ts").write_text(
            "export const g = () => x().catch((err) => {\n  toast('failed: ' + err);\n});\n")
        r = run("audit_error_handling.py", root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("src/load.ts:2", r.stdout)

    def test_clean_project_exits_0_with_files_scanned(self):
        for stack in EH_STACKS:
            with self.subTest(stack=stack):
                r = run("audit_error_handling.py", _eh_project(stack, planted=False))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("1 file(s), 0 critical, 0 advisory", r.stdout)

    def test_adapter_without_capability_refuses(self):
        root = _eh_project("tsx", planted=True)
        # `web` gained ERROR_HANDLING (it reuses tsx's); swift still has none.
        (root / "src/Home.swift").write_text("do { try f() } catch { print(\"\\(error)\") }\n")
        prof = json.loads((root / ".design-suite/profile.json").read_text())
        prof["adapters"]["lang"] = "swift"
        prof["source"]["fileGlob"] = "**/*.swift"
        (root / ".design-suite/profile.json").write_text(json.dumps(prof))
        r = run("audit_error_handling.py", root)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("ERROR_HANDLING capability", r.stderr)

    def test_unadapted_stacks_refuse(self):
        for stack in ("swift", "kotlin"):
            with self.subTest(stack=stack):
                root = make(stack, arch=_eh_vocab(".state.x"))
                r = run("audit_error_handling.py", root)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_zero_files_the_adapter_reads_refuses(self):
        root = _eh_project("dart", planted=False)
        prof = json.loads((root / ".design-suite/profile.json").read_text())
        prof["source"]["fileGlob"] = "**/*.swift"
        (root / ".design-suite/profile.json").write_text(json.dumps(prof))
        (root / "A.swift").write_text("do { try x() } catch { print(\"\\(error)\") }\n")
        r = run("audit_error_handling.py", root)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("empty sweep", r.stderr)


class ApiConsistencyIsStackAware(unittest.TestCase):
    def test_adapter_without_capability_refuses(self):
        arch = {"apiConsistency": {"scope": ["src/**/*.tsx"], "checks": {
            k: True for k in ("loadBearingCopy", "hardBakedCopy",
                              "authoredSemantics", "vocabulary")}}}
        r = run("audit_api_consistency.py", make("tsx", arch=arch))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("API_CONSISTENCY capability", r.stderr)
        self.assertNotIn("checks clean", r.stdout)


if __name__ == "__main__":
    unittest.main()
