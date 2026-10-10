#!/usr/bin/env python3
"""Tests for audit_reinvented_components.py, and specifically for where it gets
the design system's PACKAGE NAME from.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reinvented_components_test.py"

Stdlib `unittest`, synthetic fixtures in a temp directory — same convention as
`audit_contract_headers_test.py`, and for the same reason: a test pinned to a
real project's `lib/` goes green when that tree changes rather than when this
code works.

## The defect these cases exist for

The audit used to compile one consumer's package name into a regex literal:

    DS_IMPORT = re.compile(r"^import\\s+['\\"]package:<one consumer>/", re.M)

On that one project it was right. On every other project it matched nothing, so
every file read as "never imports the design system" and the reaching-past check
compared bespoke widgets against a design system it had already decided was
absent. Nothing errored and nothing was reported.

So the cases here are PAIRED, because a 0-finding run proves nothing on its own:

  * a planted duplicate under a project's own declared package must be FOUND
    (`Finds`), which is what makes the 0s below meaningful;
  * a file importing the OLD hardcoded name, in a project that declares a
    different one, must still be flagged (`NotTheOldLiteral`) — that import is
    not this project's design system and must not buy an exemption;
  * a file importing the project's OWN declared package must be exempt
    (`Finds.test_a_file_that_imports_the_declared_package_is_not_reaching_past`),
    which is the control proving the exemption is keyed on config, not on
    nothing;
  * a project that declares no package at all must REFUSE with exit 2
    (`Refuses`), never report a clean run.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "audit_reinvented_components.py"

# The literal this audit used to carry. Named once, here, so these tests fail
# loudly if it ever creeps back rather than quietly agreeing with it.
OLD_HARDCODED = "ds_flutter"
DECLARED = "acme_ds"

COMPONENT = """\
class SectionLabel extends StatelessWidget {
  const SectionLabel({super.key, this.title, this.subtitle});
}
"""


def widget(name: str, imports: str = "") -> str:
    return (f"{imports}"
            f"class {name} extends StatelessWidget {{\n"
            f"  const {name}({{super.key, this.title, this.subtitle}});\n"
            f"}}\n")


def build(tmp: Path, package: str | None, files: dict[str, str]) -> Path:
    """A synthetic project whose design system ships as `package`.

    `package=None` declares no design-system package anywhere, which is the
    refusal case.
    """
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    ds = root / "packages" / "design_system"
    (ds / "lib" / "src" / "components").mkdir(parents=True)
    (ds / "lib" / "src" / "components" / "section_label.dart").write_text(COMPONENT)

    profile: dict = {
        "profileVersion": 1,
        "project": {"name": "fixture"},
        "adapters": {"lang": "dart"},
        "source": {"root": "lib", "fileGlob": "**/*.dart"},
        "docs": {},
        "audits": {"archRulesFile": ".design-suite/arch-rules.json"},
        "tokens": {"accessor": "Tokens", "source": {"kind": "file",
                                                    "path": "lib/tokens.dart"}},
    }
    if package:
        profile["tokens"]["source"] = {
            "kind": "package",
            "package": package,
            "pathInPackage": "lib/src/tokens.dart",
            "resolveVia": ".dart_tool/package_config.json",
        }
        (root / ".dart_tool").mkdir()
        (root / ".dart_tool" / "package_config.json").write_text(json.dumps({
            "packages": [{"name": package, "rootUri": f"file://{ds}"}]}))

    (root / ".design-suite" / "profile.json").write_text(json.dumps(profile))
    (root / ".design-suite" / "arch-rules.json").write_text(json.dumps({
        "reinventedComponents": {
            "exportPrefix": "Ds",
            "allowedCollisions": [],
            "reachingPast": {"allowed": [], "threshold": 0.6,
                             "plumbingParams": ["key"], "noiseParamSets": []},
        }}))

    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


def audit(root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(RUNNER)], cwd=root, env=env,
                          capture_output=True, text=True)


class Finds(unittest.TestCase):
    """The audit still finds what it found before, on a project that declares
    its own package. Without this, every 0 below is worthless."""

    def test_planted_name_collision_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), DECLARED,
                         {"lib/planted.dart": widget("_SectionLabel")})
            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 1, blob)
            self.assertIn("_SectionLabel", blob)
            self.assertIn(f"{DECLARED} exports SectionLabel", blob)

    def test_planted_reaching_past_widget_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), DECLARED,
                         {"lib/bespoke.dart": widget("FancyLabel")})
            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 1, blob)
            self.assertIn("FancyLabel", blob)
            self.assertIn("resembles SectionLabel", blob)

    def test_a_file_that_imports_the_declared_package_is_not_reaching_past(self):
        """The control for the case above: same widget, one import different.

        This is what proves the exemption is keyed on the project's declared
        package rather than on a constant — and it is the assertion that would
        have failed for every consumer under the old hardcoded literal.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), DECLARED, {"lib/bespoke.dart": widget(
                "FancyLabel", f"import 'package:{DECLARED}/{DECLARED}.dart';\n")})
            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 0, blob)
            self.assertNotIn("FancyLabel", blob)


class NotTheOldLiteral(unittest.TestCase):
    """Nothing is attributable to the name that used to be hardcoded."""

    def test_the_old_package_name_buys_no_exemption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), DECLARED, {"lib/bespoke.dart": widget(
                "FancyLabel",
                f"import 'package:{OLD_HARDCODED}/{OLD_HARDCODED}.dart';\n")})
            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 1, blob)
            self.assertIn("FancyLabel", blob)

    def test_the_old_package_name_appears_nowhere_in_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), DECLARED,
                         {"lib/planted.dart": widget("_SectionLabel")})
            out = audit(root)
            self.assertNotIn(OLD_HARDCODED, out.stdout + out.stderr)

    def test_an_unrelated_dependency_by_that_name_is_not_the_design_system(self):
        """The sharpest form of the defect, and the reason it stayed invisible.

        A project whose design system is `acme_ds` but which ALSO depends on a
        package that happens to be called by the old hardcoded name. The old
        code resolved that package, found its (unrelated) components, matched
        nothing, and printed a clean run over a planted duplicate — exit 0, no
        findings, no error. Measured: that is what it does on this fixture.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), DECLARED,
                         {"lib/planted.dart": widget("_SectionLabel")})
            other = root / "packages" / "unrelated"
            (other / "lib" / "src" / "components").mkdir(parents=True)
            (other / "lib" / "src" / "components" / "gauge.dart").write_text(
                "class RadialGauge extends StatelessWidget {\n"
                "  const RadialGauge({super.key, this.value, this.max});\n}\n")
            config = root / ".dart_tool" / "package_config.json"
            data = json.loads(config.read_text())
            data["packages"].append(
                {"name": OLD_HARDCODED, "rootUri": f"file://{other}"})
            config.write_text(json.dumps(data))

            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 1, blob)
            self.assertIn(f"{DECLARED} exports SectionLabel", blob)
            self.assertNotIn("RadialGauge", blob)

    def test_a_project_declaring_the_old_name_still_works(self):
        """Portability cuts both ways: the one project that really does ship
        under that name must keep working, now by declaring it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), OLD_HARDCODED,
                         {"lib/planted.dart": widget("_SectionLabel")})
            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 1, blob)
            self.assertIn(f"{OLD_HARDCODED} exports SectionLabel", blob)


class Refuses(unittest.TestCase):
    def test_no_declared_package_is_exit_2_not_a_clean_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), None,
                         {"lib/planted.dart": widget("_SectionLabel")})
            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 2, blob)
            self.assertIn("REFUSING TO RUN", blob)
            self.assertNotIn("nothing reinvented", blob)

    def test_arch_rules_package_overrides_the_profile(self):
        """A project whose design system is not the package that owns its
        tokens declares it beside `exportPrefix`."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build(Path(tmp), None,
                         {"lib/planted.dart": widget("_SectionLabel")})
            ds = root / "packages" / "design_system"
            (root / ".dart_tool").mkdir()
            (root / ".dart_tool" / "package_config.json").write_text(json.dumps({
                "packages": [{"name": DECLARED, "rootUri": f"file://{ds}"}]}))
            rules_path = root / ".design-suite" / "arch-rules.json"
            rules = json.loads(rules_path.read_text())
            rules["reinventedComponents"]["package"] = DECLARED
            rules_path.write_text(json.dumps(rules))

            out = audit(root)
            blob = out.stdout + out.stderr
            self.assertEqual(out.returncode, 1, blob)
            self.assertIn(f"{DECLARED} exports SectionLabel", blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
