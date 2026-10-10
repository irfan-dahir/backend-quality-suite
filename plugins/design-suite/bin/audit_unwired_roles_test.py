#!/usr/bin/env python3
"""Tests for the one thing `audit_unwired_roles` got confidently wrong.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_unwired_roles_test.py"

Asked of a package, "does anything here read this role?" is the right question.
Asked of a consuming app it is close to backwards — the design system's theme
factory and components are what read the roles, and the app gets them by using
the components. Measured on a real consumer: eight of nineteen roles reported
unread, including `surface` and `background`, and every one was wired. A 100%
false-positive rate on the roles it named.

So the case that matters here is a role read ONLY by the package's theme
factory: it must not be reported. On its own that assertion is worthless — an
audit that reports nothing passes it — so every such case is paired with a
control role that really is read nowhere and MUST still be reported. A fix that
buys silence is this repo's governing principle failing, not a fix.

The refusal cases are the same argument from the other side: when the package is
configured and its source cannot be found, a narrower sweep would produce
exactly the false positives above with nothing on screen to say so, so the audit
must refuse (exit 2) rather than scan less.

Stdlib `unittest`, subprocess-driven like `audit_findings_envelope_test.py`:
this script resolves `project_root()` at import time, so a fixture can only be
pointed at through `CLAUDE_PROJECT_DIR` in a child process. The two unit tests
at the bottom import the module instead, against a module-scope fixture, because
the branches they cover are defence-in-depth the CLI cannot reach.
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

ROLES = ("primary", "surface", "danger")

ARCH_RULES = {"unwiredRoles": {"requiredRoles": list(ROLES)}}

# Read by the app itself.
APP_SOURCE = """class Home {
  void build(BuildContext context) {
    final colors = DsColors.of(context);
    colors.primary;
  }
}
"""

# Read by the design system's theme factory, on the app's behalf. This is the
# whole finding: `surface` is wired, and a brand changing it moves the app.
DS_THEME_SOURCE = """class DsTheme {
  static ThemeData of(BuildContext context) {
    final colors = DsColors.of(context);
    return ThemeData(scaffoldBackgroundColor: colors.surface);
  }
}
"""

ROLES_SOURCE = ("class DsColors {\n"
                + "".join(f"  final Color {r};\n" for r in ROLES)
                + "}\n")


def _profile(role_source: dict) -> dict:
    return {
        "profileVersion": 1,
        "project": {"name": "Fixture"},
        "adapters": {"lang": "dart"},
        "source": {"root": "lib", "fileGlob": "**/*.dart"},
        "tokens": {"roleSource": role_source, "roleAccessor": "DsColors"},
        "audits": {"exceptionsFile": ".design-suite/exceptions.json",
                   "archRulesFile": ".design-suite/arch-rules.json"},
    }


def _base(tmp: str, role_source: dict) -> Path:
    repo = Path(tmp)
    (repo / ".design-suite").mkdir(parents=True, exist_ok=True)
    (repo / ".design-suite" / "profile.json").write_text(
        json.dumps(_profile(role_source)))
    (repo / ".design-suite" / "arch-rules.json").write_text(json.dumps(ARCH_RULES))
    (repo / ".design-suite" / "exceptions.json").write_text(
        json.dumps({"unwiredRoles": {}}))
    (repo / "lib").mkdir(parents=True, exist_ok=True)
    (repo / "lib" / "home.dart").write_text(APP_SOURCE)
    return repo


def package_fixture(tmp: str, *, roles_at: str = "lib/theme/roles.dart",
                    with_theme: bool = True) -> Path:
    """A consumer whose roles come from a design-system package.

    `primary` is read by the app, `surface` only by the package's theme factory,
    and `danger` by nothing at all — one of each, so a run reports exactly the
    third and a fix that silences all three fails.
    """
    repo = _base(tmp, {
        "kind": "package",
        "package": "ds",
        "resolveVia": ".dart_tool/package_config.json",
        "pathInPackage": roles_at,
    })
    (repo / ".dart_tool").mkdir(parents=True, exist_ok=True)
    (repo / ".dart_tool" / "package_config.json").write_text(json.dumps(
        {"configVersion": 2,
         "packages": [{"name": "ds", "rootUri": "../packages/ds"}]}))
    target = repo / "packages" / "ds" / roles_at
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ROLES_SOURCE)
    if with_theme:
        (target.parent / "theme.dart").write_text(DS_THEME_SOURCE)
    return repo


def file_fixture(tmp: str) -> Path:
    """The package-less shape: roles are a plain file in this repo. There is no
    second place to look, and behaviour must be exactly what it was before."""
    repo = _base(tmp, {"kind": "file", "path": "lib/theme/roles.dart"})
    (repo / "lib" / "theme").mkdir(parents=True, exist_ok=True)
    (repo / "lib" / "theme" / "roles.dart").write_text(ROLES_SOURCE)
    (repo / "lib" / "surface_user.dart").write_text(
        "class S {\n  void b(BuildContext context) {\n"
        "    final colors = DsColors.of(context);\n    colors.surface;\n  }\n}\n")
    return repo


def run(repo: Path, args: list[str] | None = None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    return subprocess.run(
        [sys.executable, str(BIN / "audit_unwired_roles.py"), *(args or [])],
        capture_output=True, text=True, env=env)


def failing_roles(repo: Path, result) -> list[str]:
    out = json.loads((repo / "out.json").read_text())
    return out["failing"]


class RoleReadOnlyByThePackage(unittest.TestCase):
    """The measured false positive, and its control."""

    def test_a_role_only_the_theme_factory_reads_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = package_fixture(tmp)
            result = run(repo, ["--out", "out.json"])
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("surface", failing_roles(repo, result))
            self.assertNotIn("surface", result.stderr)

    def test_the_genuinely_dead_role_is_still_reported(self):
        """Paired with the case above on purpose: an audit that reported
        nothing would pass that one and fail this one."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = package_fixture(tmp)
            result = run(repo, ["--out", "out.json"])
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(failing_roles(repo, result), ["danger"])
            self.assertIn("danger", result.stderr)

    def test_without_the_upstream_scan_surface_would_have_been_reported(self):
        """The oracle for the two above. Same fixture minus the design system's
        theme factory: `surface` becomes genuinely unread and IS reported — so
        the pass above is the upstream scan working, not the audit going quiet."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = package_fixture(tmp, with_theme=False)
            result = run(repo, ["--out", "out.json"])
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(failing_roles(repo, result), ["danger", "surface"])

    def test_the_report_says_where_each_role_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = package_fixture(tmp)
            result = run(repo, ["--out", "out.json"])
            self.assertIn("read here      1", result.stdout)
            self.assertIn("read upstream  1", result.stdout)

    def test_the_envelope_names_the_reach_of_the_sweep(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = package_fixture(tmp)
            result = run(repo, ["--findings"])
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(
                (repo / ".design-suite" / "findings" / "unwired-roles.json").read_text())
            self.assertEqual([f["summary"].split()[0] for f in data["findings"]],
                             ["danger"])
            self.assertIn("ds package", data["findings"][0]["detail"])


class NoPackageConfigured(unittest.TestCase):
    """Roles as a plain file in this repo — the shape that predates this change
    and must be untouched by it."""

    def test_behaviour_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = file_fixture(tmp)
            result = run(repo, ["--out", "out.json"])
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(failing_roles(repo, result), ["danger"])

    def test_no_upstream_line_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = file_fixture(tmp)
            result = run(repo, ["--out", "out.json"])
            self.assertNotIn("read upstream", result.stdout)

    def test_the_envelope_detail_claims_only_this_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = file_fixture(tmp)
            run(repo, ["--findings"])
            data = json.loads(
                (repo / ".design-suite" / "findings" / "unwired-roles.json").read_text())
            self.assertIn("searched this project's own source",
                          data["findings"][0]["detail"])


class UnresolvablePackageRefuses(unittest.TestCase):
    """Exit 2, not a quieter exit 0/1. `2` means "I could not look"; scanning
    the app alone is looking less, and looking less is what produced the eight
    false positives in the first place."""

    def test_an_upstream_sweep_that_matches_nothing_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A generated roles file at the package root: the roles resolve, so
            # the audit knows the package exists, but every file the sweep would
            # read is the emitter's own output.
            repo = package_fixture(tmp, roles_at="roles.g.dart", with_theme=False)
            result = run(repo)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("REFUSING TO RUN", result.stderr)

    def test_a_refusal_writes_no_findings_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = package_fixture(tmp, roles_at="roles.g.dart", with_theme=False)
            run(repo, ["--findings"])
            self.assertFalse(
                (repo / ".design-suite" / "findings" / "unwired-roles.json").exists())


# ---------------------------------------------------------------------------
# `_package_lib` directly, for the branches the CLI cannot reach.
#
# The adapter resolves the roles through the same package map this helper reads,
# so by the time `main()` calls it a missing map or an unlisted package has
# already exited earlier. Those branches are defence-in-depth against an adapter
# that resolves roles some other way — real, and only testable here. The module
# resolves `project_root()` at import, hence the module-scope fixture.
# ---------------------------------------------------------------------------

_HOLD = tempfile.TemporaryDirectory()
_IMPORT_FIXTURE = package_fixture(_HOLD.name)
os.environ["CLAUDE_PROJECT_DIR"] = str(_IMPORT_FIXTURE)
sys.path.insert(0, str(BIN))

import audit_unwired_roles as AUR  # noqa: E402


class PackageLib(unittest.TestCase):
    def test_a_file_role_source_has_no_second_place_to_look(self):
        self.assertIsNone(
            AUR._package_lib(_IMPORT_FIXTURE, {"kind": "file", "path": "x.dart"}))

    def test_a_missing_resolution_map_refuses(self):
        with self.assertRaises(SystemExit) as caught:
            AUR._package_lib(_IMPORT_FIXTURE, {
                "kind": "package", "package": "ds",
                "resolveVia": ".dart_tool/nope.json",
                "pathInPackage": "lib/theme/roles.dart"})
        self.assertEqual(caught.exception.code, 2)

    def test_a_package_absent_from_the_map_refuses(self):
        with self.assertRaises(SystemExit) as caught:
            AUR._package_lib(_IMPORT_FIXTURE, {
                "kind": "package", "package": "not_installed",
                "resolveVia": ".dart_tool/package_config.json",
                "pathInPackage": "lib/theme/roles.dart"})
        self.assertEqual(caught.exception.code, 2)

    def test_a_package_with_no_name_refuses(self):
        with self.assertRaises(SystemExit) as caught:
            AUR._package_lib(_IMPORT_FIXTURE, {"kind": "package"})
        self.assertEqual(caught.exception.code, 2)

    def test_the_resolved_root_is_the_packages_own_source_directory(self):
        lib = AUR._package_lib(_IMPORT_FIXTURE, {
            "kind": "package", "package": "ds",
            "resolveVia": ".dart_tool/package_config.json",
            "pathInPackage": "lib/theme/roles.dart"})
        self.assertEqual(lib, (_IMPORT_FIXTURE / "packages" / "ds" / "lib").resolve())


if __name__ == "__main__":
    unittest.main(verbosity=1)
