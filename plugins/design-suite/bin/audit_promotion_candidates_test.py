#!/usr/bin/env python3
"""Tests for audit_promotion_candidates' design-system package resolution.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates_test.py"

The bug these exist for: this audit called

    design_system_package(REPO, _RULES)   # _RULES = load(REPO, "promotionCandidates")

but `design_system_package` read `package` out of whatever dict it was handed,
and `package` lives in `reinventedComponents` — it is the section that also owns
`exportPrefix`, and the only section in arch-rules.json.template carrying either.
So on every project that declared its package the documented way, the lookup fell
through to `tokens.source.package` and the `near_ds` ("possibly already covered
by") suggestions were silently off. The stderr note even named the key that WAS
set, which is the one thing that kept it from being invisible.

The sibling `audit_reinvented_components_test.py` could not have caught it: its
fixture declares the package via `tokens.source.package`, exercising source 2.
Source 1 — the source the bug was in — had no test at all.

Why the parameter is gone rather than corrected at the call site: one right
section, and a signature accepting any dict, is a footgun. `test_resolver_takes_
only_a_repo` pins that, so a third caller cannot repeat the mistake.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "audit_promotion_candidates.py"

sys.path.insert(0, str(HERE))
import _bootstrap  # noqa: F401,E402 — sets up the design_suite import path
from design_suite.engine.component_shape import design_system_package  # noqa: E402

DECLARED = "example_design_system"

# Two widgets, separately written, with an IDENTICAL parameter set. The detector
# matches on parameter names, so a near-miss here silently finds nothing — which
# is how a first draft of the eval fixture scored zero and looked like a pass.
SHAPE = """\
class _{name} extends StatelessWidget {{
  const _{name}({{super.key, this.label, this.value, this.icon, this.onTap}});
}}
"""


def build(tmp: Path, *, declare_in: str | None) -> Path:
    """A project with one duplicated widget shape.

    `declare_in` is where the design-system package name is declared:
      "arch"    -> reinventedComponents.package  (source 1, the reported bug)
      "tokens"  -> tokens.source.package         (source 2, already covered)
      None      -> nowhere; suggestions must go off, loudly
    """
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    ds = root / "packages" / "design_system"
    (ds / "lib" / "src" / "components").mkdir(parents=True)
    (ds / "lib" / "src" / "components" / "ds_stat_cell.dart").write_text(
        "class DsStatCell extends StatelessWidget {\n"
        "  const DsStatCell({super.key, this.label, this.value, this.icon, this.onTap});\n"
        "}\n")

    profile: dict = {
        "profileVersion": 1,
        "project": {"name": "fixture"},
        "adapters": {"lang": "dart"},
        "source": {"root": "lib", "fileGlob": "**/*.dart"},
        "docs": {},
        "audits": {"archRulesFile": ".design-suite/arch-rules.json"},
        "tokens": {"accessor": "Tokens",
                   "source": {"kind": "file", "path": "lib/tokens.dart"}},
    }
    arch: dict = {
        "reinventedComponents": {
            "exportPrefix": "Ds",
            "allowedCollisions": [],
            "reachingPast": {"allowed": [], "threshold": 0.6,
                             "plumbingParams": ["key"], "noiseParamSets": []},
        },
        "promotionCandidates": {
            "plumbingParams": ["key"],
            "noiseParamSets": [],
            "baseline": ".design-suite/promotion-baseline.json",
        },
    }

    if declare_in == "arch":
        # The documented place. Deliberately NOT also set in tokens.source, so a
        # pass here can only come from source 1 actually being read.
        arch["reinventedComponents"]["package"] = DECLARED
    elif declare_in == "tokens":
        profile["tokens"]["source"] = {
            "kind": "package", "package": DECLARED,
            "pathInPackage": "lib/src/tokens.dart",
            "resolveVia": ".dart_tool/package_config.json",
        }

    if declare_in is not None:
        (root / ".dart_tool").mkdir(exist_ok=True)
        (root / ".dart_tool" / "package_config.json").write_text(json.dumps(
            {"packages": [{"name": DECLARED, "rootUri": f"file://{ds}"}]}))

    (root / ".design-suite" / "profile.json").write_text(json.dumps(profile))
    (root / ".design-suite" / "arch-rules.json").write_text(json.dumps(arch))
    (root / ".design-suite" / "promotion-baseline.json").write_text(
        json.dumps({"accepted": []}))

    (root / "lib" / "home_screen.dart").write_text(SHAPE.format(name="StatCell"))
    (root / "lib" / "settings_screen.dart").write_text(SHAPE.format(name="MetricTile"))
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(RUNNER)], cwd=root, env=env,
                          capture_output=True, text=True)


NO_PACKAGE_NOTE = "no design-system package declared"


class PackageResolution(unittest.TestCase):
    def test_arch_rules_package_is_read(self):
        """THE REGRESSION. Declared in reinventedComponents.package and nowhere
        else, the audit must not claim none is declared."""
        with tempfile.TemporaryDirectory() as tmp:
            out = run(build(Path(tmp), declare_in="arch"))
            self.assertNotIn(NO_PACKAGE_NOTE, out.stdout + out.stderr,
                             "reinventedComponents.package was set, yet the audit "
                             "reported no package declared — the suggestions are off")

    def test_tokens_source_package_still_works(self):
        """Control: fixing source 1 must not break source 2."""
        with tempfile.TemporaryDirectory() as tmp:
            out = run(build(Path(tmp), declare_in="tokens"))
            self.assertNotIn(NO_PACKAGE_NOTE, out.stdout + out.stderr)

    def test_undeclared_still_says_so_out_loud(self):
        """The paired refusal. A project that declares nowhere must still be
        TOLD the suggestions are off — losing them silently is the failure this
        suite forbids, and a fix that made this quiet would be worse than the bug."""
        with tempfile.TemporaryDirectory() as tmp:
            out = run(build(Path(tmp), declare_in=None))
            self.assertIn(NO_PACKAGE_NOTE, out.stdout + out.stderr)

    def test_duplicate_shapes_are_found_either_way(self):
        """Control for all three above: the primary finding does not depend on a
        design system existing, so every case must still report the duplicate.
        Without this, a run that found nothing would satisfy the assertions."""
        for where in ("arch", "tokens", None):
            with self.subTest(declared_in=where), tempfile.TemporaryDirectory() as tmp:
                out = run(build(Path(tmp), declare_in=where))
                self.assertIn("duplicated widget shapes", out.stdout,
                              f"no duplicate reported with package declared in {where!r} "
                              f"— the fixture stopped exercising the detector")

    def test_resolver_takes_only_a_repo(self):
        """The signature is the fix. A `rules` parameter accepting any dict is
        what let one caller pass the wrong section; there is exactly one section
        carrying `package`, so there is nothing for a caller to choose."""
        params = list(inspect.signature(design_system_package).parameters)
        self.assertEqual(params, ["repo"],
                         "design_system_package regained a section argument — a "
                         "third caller can now repeat audit_promotion_candidates' bug")


if __name__ == "__main__":
    unittest.main(verbosity=2)
