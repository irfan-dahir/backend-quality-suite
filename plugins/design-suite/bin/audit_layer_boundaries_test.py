#!/usr/bin/env python3
"""audit_layer_boundaries: path aliases and multi-rule enforcement.

Before this fix:
  * `import { api } from '@/data/api'` (tsconfig `paths`, vite `resolve.alias`)
    was read as a third-party package — the violation was missed and the run
    printed clean;
  * only `layerBoundaries.rules[0]` was enforced; every later rule was
    configuration that did nothing.

Each test plants a real violation and asserts it is FOUND (exit 1), so a
resolver that silently stopped resolving would fail here, not pass.
"""
from __future__ import annotations

import json
import shutil
import unittest

from structural_refusals_test import make, run

RULE = {"rules": [{"fromGlob": "src/ui/**", "mustNotImport": "src/data/**"}],
        "baseline": ".design-suite/baselines/layer-boundaries.json"}
TSCONFIG = """{
  // comments and trailing commas are legal in tsconfig
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"], },
  },
}
"""


def project(button_import: str, extra: dict) -> "Path":
    root = make("tsx", arch={"layerBoundaries": RULE})
    (root / "src/ui/Button.tsx").write_text(f"import {{ api }} from '{button_import}';\n")
    for rel, text in extra.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


class Aliases(unittest.TestCase):
    def tearDown(self):
        for r in getattr(self, "_roots", []):
            shutil.rmtree(r, ignore_errors=True)

    def check(self, root, code, needle, stream="stdout"):
        self._roots = getattr(self, "_roots", []) + [root]
        r = run("audit_layer_boundaries.py", root)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertIn(needle, getattr(r, stream))
        return r

    def test_tsconfig_paths_alias_violation_is_found(self):
        self.check(project("@/data/api", {"tsconfig.json": TSCONFIG}), 1, "src/data/api")

    def test_tsconfig_references_are_followed(self):
        # Vite's template: paths live in tsconfig.app.json, referenced from tsconfig.json.
        self.check(project("@/data/api", {
            "tsconfig.json": '{"files": [], "references": [{"path": "./tsconfig.app.json"}]}',
            "tsconfig.app.json": '{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}'}),
            1, "src/data/api")

    def test_jsconfig_baseurl_bare_import_is_found(self):
        self.check(project("data/api", {
            "jsconfig.json": '{"compilerOptions": {"baseUrl": "src"}}'}), 1, "src/data/api")

    def test_vite_alias_violation_is_found(self):
        vite = ("import { fileURLToPath, URL } from 'node:url'\n"
                "import path from 'path'\n"
                "export default defineConfig({ resolve: { alias: {\n"
                "  '@': fileURLToPath(new URL('./src', import.meta.url)),\n"
                "  '~lib': path.resolve(__dirname, 'src/lib'),\n"
                "} } })\n")
        self.check(project("@/data/api", {"vite.config.ts": vite}), 1, "src/data/api")

    def test_vite_array_alias_violation_is_found(self):
        vite = ("export default { resolve: { alias: [\n"
                "  { find: '#data', replacement: '/src/data' },\n"
                "] } }\n")
        self.check(project("#data/api", {"vite.config.js": vite}), 1, "src/data/api")

    def test_unparseable_alias_config_refuses(self):
        self.check(project("@/data/api", {"tsconfig.json": "{ not json"}), 2, "REFUSED", "stderr")

    def test_non_literal_vite_alias_refuses(self):
        vite = "const a = mk()\nexport default { resolve: { alias: { '@': a } } }\n"
        self.check(project("@/data/api", {"vite.config.ts": vite}), 2, "not a literal path", "stderr")

    def test_alias_shaped_import_without_config_refuses(self):
        self.check(project("@/data/api", {}), 2, "shaped", "stderr")

    def test_clean_alias_import_stays_clean(self):
        self.check(project("@/ui/Other", {"tsconfig.json": TSCONFIG, "src/ui/Other.tsx": "x\n"}),
                   0, "no new violations")

    def test_scoped_package_is_not_mistaken_for_alias(self):
        self.check(project("@scope/pkg", {"tsconfig.json": TSCONFIG}), 0, "no new violations")


class MultiRule(unittest.TestCase):
    def test_second_rule_is_enforced(self):
        rules = {"rules": [
            {"fromGlob": "src/ui/**", "mustNotImport": "src/nothing/**"},
            {"label": "data must not import pages", "from": "src/data",
             "mustNotImport": "src/pages/**"}],
            "baseline": ".design-suite/baselines/layer-boundaries.json"}
        root = make("tsx", arch={"layerBoundaries": rules})
        (root / "src/data/leak.ts").write_text("import { H } from '../pages/Home';\n")
        try:
            r = run("audit_layer_boundaries.py", root)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("src/data/leak.ts", r.stdout)
            self.assertIn("src/pages/Home", r.stdout)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_placeholder_in_later_rule_refuses(self):
        rules = {**RULE, "rules": RULE["rules"] + [{"fromGlob": "TODO: x", "mustNotImport": "TODO: y"}]}
        root = make("tsx", arch={"layerBoundaries": rules})
        try:
            r = run("audit_layer_boundaries.py", root)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("rules[1]", r.stderr)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
