#!/usr/bin/env python3
"""Tests for the `design-suite` CLI (design_suite/cli.py) and its packaging.

Stdlib unittest. Covers:
  * every subcommand row reaches a script that exists, and `--help` exits 0 with
    text for every one of them — outside any project, where many scripts' own
    --help refuses;
  * the CLI returns the same exit code as calling the script directly, on
    synthetic projects planted to produce 0, 1 and 2;
  * the locator order (package > DESIGN_SUITE_HOME > CLAUDE_PLUGIN_ROOT) and its
    refusals: nothing resolves -> exit 2 naming every step; a set-but-invalid
    env var -> refusal, not a fall-through;
  * `pip install` of the repo into a fresh, offline temp venv yields a working
    `design-suite` that runs an audit with the right exit code.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN))

from design_suite import cli  # noqa: E402


def project(root: Path, files: dict, lang: str) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    (root / ".design-suite").mkdir(exist_ok=True)
    (root / ".design-suite" / "profile.json").write_text(json.dumps(
        {"profileVersion": 1, "project": {"name": "fixture"}, "adapters": {"lang": lang},
         "source": {"root": "src"}, "pipelines": {"tokens": ".design-suite/out"}}))
    return root


# lang, files, expected exit code of audit_tokens.py
CASES = {
    "findings": ("web", {"src/a.css": ".box { color: #ff0000; padding: 13px; }\n"}, 1),
    "clean": ("web", {"src/a.css": ".box { color: var(--ink); padding: var(--gap); }\n"}, 0),
    "refused": ("cobol", {"src/a.cob": "x\n"}, 2),
}


def env_for(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DESIGN_SUITE_HOME", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR")}
    return dict(env, CLAUDE_PROJECT_DIR=str(root))


def run(cmd: list, root: Path, extra_env: "dict | None" = None) -> subprocess.CompletedProcess:
    env = dict(env_for(root), **(extra_env or {}))
    return subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=180)


CLI = [sys.executable, "-m", "design_suite"]
PYPATH = {"PYTHONPATH": str(PLUGIN)}


class Dispatch(unittest.TestCase):
    def test_every_row_reaches_an_existing_script(self):
        rows = cli.table(PLUGIN)
        self.assertGreater(len([r for r in rows if r.startswith("audit ")]), 10)
        missing = [n for n, (s, _) in rows.items() if not (PLUGIN / "bin" / s).is_file()]
        self.assertEqual(missing, [])

    def test_every_audit_script_is_reachable(self):
        scripts = {p.name for p in (PLUGIN / "bin").glob("audit_*.py")
                   if not p.stem.endswith("_test")}
        self.assertEqual(scripts, set(cli.audits(PLUGIN).values()))

    def test_help_works_for_every_subcommand_outside_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in cli.table(PLUGIN):
                proc = run(CLI + name.split() + ["--help"], Path(tmp), PYPATH)
                self.assertEqual(proc.returncode, 0, f"{name}: {proc.stderr}")
                self.assertIn(f"design-suite {name}", proc.stdout)
                self.assertGreater(len(proc.stdout.splitlines()), 2, name)

    def test_list_enumerates_every_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = run(CLI + ["list"], Path(tmp), PYPATH).stdout
        for name in cli.table(PLUGIN):
            self.assertIn(name, out)

    def test_unknown_subcommand_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(CLI + ["no-such"], Path(tmp), PYPATH).returncode, 2)
            self.assertEqual(run(CLI + ["audit", "no-such"], Path(tmp), PYPATH).returncode, 2)


class ExitCodesPassThrough(unittest.TestCase):
    def test_cli_matches_direct_script(self):
        seen = set()
        for label, (lang, files, expected) in CASES.items():
            with tempfile.TemporaryDirectory() as tmp:
                root = project(Path(tmp), files, lang)
                direct = run([sys.executable, str(PLUGIN / "bin/audit_tokens.py")], root)
                via = run(CLI + ["audit", "tokens"], root, PYPATH)
                self.assertEqual(direct.returncode, expected, f"{label}: {direct.stderr}")
                self.assertEqual(via.returncode, direct.returncode, f"{label}: {via.stderr}")
                seen.add(via.returncode)
        self.assertEqual(seen, {0, 1, 2})  # a pass-through that only saw 0 proves nothing

    def test_script_arguments_pass_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(Path(tmp), CASES["findings"][1], "web")
            direct = run([sys.executable, str(PLUGIN / "bin/resolve.py"), "--profile",
                          "adapters.lang"], root)
            via = run(CLI + ["resolve", "--profile", "adapters.lang"], root, PYPATH)
            self.assertEqual((via.returncode, via.stdout), (direct.returncode, direct.stdout))
            self.assertIn("web", via.stdout)


class Locator(unittest.TestCase):
    def _bare_package(self, tmp: str) -> Path:
        pkg = Path(tmp) / "bare" / "design_suite"
        pkg.mkdir(parents=True)
        return pkg

    def test_package_wins_over_env(self):
        root, how = cli.locate({"DESIGN_SUITE_HOME": "/nope", "CLAUDE_PLUGIN_ROOT": "/nope"},
                               PLUGIN / "design_suite")
        self.assertEqual((root, how), (PLUGIN, "package"))

    def test_design_suite_home_before_claude_plugin_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._bare_package(tmp)
            root, how = cli.locate({"DESIGN_SUITE_HOME": str(PLUGIN),
                                    "CLAUDE_PLUGIN_ROOT": "/nope"}, pkg)
            self.assertEqual((root, how), (PLUGIN.resolve(), "DESIGN_SUITE_HOME"))
            root, how = cli.locate({"CLAUDE_PLUGIN_ROOT": str(PLUGIN)}, pkg)
            self.assertEqual(how, "CLAUDE_PLUGIN_ROOT")

    def test_set_but_invalid_env_refuses_rather_than_falling_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._bare_package(tmp)
            with self.assertRaises(cli.Refusal) as e:
                cli.locate({"DESIGN_SUITE_HOME": tmp, "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}, pkg)
            self.assertIn("DESIGN_SUITE_HOME", str(e.exception))

    def test_nothing_resolves_exits_2_naming_every_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = self._bare_package(tmp)
            shutil.copy(PLUGIN / "design_suite" / "cli.py", pkg / "cli.py")
            (pkg / "__init__.py").write_text("")
            proc = run([sys.executable, "-m", "design_suite.cli", "where"], Path(tmp),
                       {"PYTHONPATH": str(pkg.parent)})
            self.assertEqual(proc.returncode, 2, proc.stdout)
            for step in ("package:", "DESIGN_SUITE_HOME: not set", "CLAUDE_PLUGIN_ROOT: not set"):
                self.assertIn(step, proc.stderr)

    def test_where_reports_how(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(CLI + ["where"], Path(tmp), PYPATH)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("resolved via package", proc.stdout)


class InstallsIntoAVenv(unittest.TestCase):
    def test_offline_pip_install_runs_an_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / "venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                           capture_output=True, timeout=180)
            py = venv / ("Scripts" if os.name == "nt" else "bin") / "python"
            pip = subprocess.run([str(py), "-m", "pip", "install", "--no-index", "--quiet",
                                  str(REPO)], capture_output=True, text=True, timeout=300)
            self.assertEqual(pip.returncode, 0, pip.stdout + pip.stderr)
            exe = py.parent / "design-suite"
            self.assertTrue(exe.is_file(), "console entry point not installed")
            for label in ("findings", "refused"):
                lang, files, expected = CASES[label]
                root = project(Path(tmp) / label, files, lang)
                proc = run([str(exe), "audit", "tokens"], root)
                self.assertEqual(proc.returncode, expected, f"{label}: {proc.stderr}")
            where = run([str(exe), "where"], Path(tmp))
            self.assertIn("design_suite_plugin", where.stdout)
            self.assertIn("resolved via package", where.stdout)


if __name__ == "__main__":
    unittest.main()
