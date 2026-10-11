#!/usr/bin/env python3
"""The structural refusal contract, measured over every section-reading audit.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/structural_refusals_test.py"

Re-authored from the purged design-suite version of this file. What died with
the purge: the adapter-pattern / pattern-adoption / unused-tokens /
unwired-roles rows (no audit ships for them) and the six-stack matrix — this
suite ships exactly one adapter, php. What survived, and what this file now
guards, is the cross-audit contract itself:

  * missing arch-rules section        -> exit 2, naming the section, ×6 audits
  * audits.archRulesFile undeclared   -> exit 2, naming the key, ×6 audits
  * malformed arch-rules file         -> exit 2, never a traceback (a bare
    JSON *string* parses, answers `section in rules` as a substring test, and
    used to TypeError out at exit 1 — measured, then fixed in engine/arch)
  * the SHIPPED scaffold template     -> exit 2 on every audit: a freshly
    init.py'd project must never read clean because its rules are still TODO
  * no / unknown adapters.lang        -> exit 2 for the four audits whose
    syntax comes from the adapter; the two route-table audits are text scans
    and keep working, which is asserted rather than assumed
  * missing profile input             -> exit 2 (engine/project.need_refused),
    not exit 1: SystemExit(message) exits 1, this suite's findings code, and a
    harness reads a miscoded refusal as results
  * planted violations still found    -> exit 1 rows, so every refusal above
    can only pass because the refusal fired, not because the audit is inert

Every expected exit was measured against the fixed audits before being written
here; nothing in this file is aspirational.
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

# audit -> (expected arch-rules section, message fragment for its
# missing-section refusal)
AUDITS = {
    "audit_error_handling": "errorHandling",
    "audit_api_consistency": "apiConsistency",
    "audit_contract_headers": "contractHeaders",
    "audit_layer_boundaries": "layerBoundaries",
    "audit_route_coverage": "routeCoverage",
    "audit_cache_ttl_coverage": "cacheTtlCoverage",
}

# The four audits that cannot run without a language adapter (their catch
# shapes, class members, or import syntax come from it). The other two read
# route tables as text on purpose.
ADAPTER_BOUND = ("audit_error_handling", "audit_api_consistency",
                 "audit_contract_headers", "audit_layer_boundaries")
LANG_INDEPENDENT = ("audit_route_coverage", "audit_cache_ttl_coverage")

VOCAB = {
    "exception_type": "AppError",
    "guard_call": "guardApiCall",
    "client_call_pattern": r"\bHttp::(?:get|post)\s*\(",
    "error_state_widget": "ErrorState",
    "error_message_field": "errorMessage",
    "state_class_pattern": r"^class (\w+Failed)\b",
    "state_file_suffix": "_state.php",
    "pages_marker": "/pages/",
}

LAYER_RULES = {"rules": [{"label": "app/Http must not reach app/Service",
                          "from": "app/Http",
                          "mustNotImport": ["App\\Service\\"]}]}
ROUTE_RULES = {"routesGlob": "routes/*.php",
               "actionPattern": r"'uses'\s*=>\s*'([A-Za-z]+)@([A-Za-z]+)'",
               "controllerDirs": ["app/Http/Controllers"]}
CACHE_RULES = {"routesGlob": "routes/*.php",
               "actionPattern": r"'uses'\s*=>\s*'([A-Za-z]+@[A-Za-z]+)'",
               "ttlConfigGlob": "config/app.php",
               "ttlKeyPattern": r"'([A-Za-z]+@[A-Za-z]+)'\s*=>"}

# Minimal VALID section per audit: enough to get past config validation so a
# refusal row can only be the row under test (e.g. the lang check is reached,
# not shadowed by an earlier TODO refusal).
VALID_SECTION = {
    "errorHandling": dict(VOCAB),
    "apiConsistency": {"scope": ["app/**/*.php"],
                       "checks": {"loadBearingCopy": True, "hardBakedCopy": True,
                                  "authoredSemantics": {"enabled": False,
                                                        "why": "probe: server tree"},
                                  "vocabulary": {"enabled": False,
                                                 "why": "probe: none named yet"}},
                       "vocabularyRules": []},
    "contractHeaders": {"headerMarker": "// CONTRACT:", "scope": "app/**/*.php",
                        "adapterGlob": "app/**/*.php"},
    "layerBoundaries": LAYER_RULES,
    "routeCoverage": ROUTE_RULES,
    "cacheTtlCoverage": CACHE_RULES,
}

BASE_FILES = {
    "composer.json": json.dumps({"autoload": {"psr-4": {"App\\": "app/"}}}),
    "routes/api.php": "<?php\n$router->get('/orders', "
                      "['uses' => 'OrdersController@index']);\n",
    "app/Http/Controllers/OrdersController.php":
        "<?php\nnamespace App\\Http\\Controllers;\n"
        "class OrdersController { public function index() {} }\n",
    "app/Service/Dep.php": "<?php\nnamespace App\\Service;\nclass Dep {}\n",
    # The planted layer violation: app/Http reaching into app/Service.
    "app/Http/Thing.php": "<?php\nnamespace App\\Http;\nuse App\\Service\\Dep;\n"
                          "class Thing {}\n",
    "config/app.php": "<?php\nreturn ['OrdersController@index' => 60];\n",
    "exceptions.json": "{}",
}


def build(arch=None, *, lang="php", file_glob=True, exceptions_file=True,
          audits=None, files=None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="structural-"))
    for rel, text in {**BASE_FILES, **(files or {})}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    profile = {"profileVersion": 1, "project": {"name": "probe"},
               "source": {"root": "app"},
               "audits": {"archRulesFile": ".backend-suite/arch-rules.json"}}
    if audits is not None:
        profile["audits"] = audits
    if file_glob:
        profile["source"]["fileGlob"] = "**/*.php"
    if lang:
        profile["adapters"] = {"lang": lang}
    if exceptions_file:
        profile["audits"]["exceptionsFile"] = "exceptions.json"
    (root / ".backend-suite").mkdir()
    (root / ".backend-suite/profile.json").write_text(json.dumps(profile))
    if arch is not None:
        (root / ".backend-suite/arch-rules.json").write_text(arch)
    return root


def valid(sections: dict, **kw) -> Path:
    return build(json.dumps(sections), **kw)


def run(audit: str, root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(BIN / f"{audit}.py")],
                          cwd=root, env=env, capture_output=True, text=True,
                          timeout=120)


class MissingSectionRefuses(unittest.TestCase):
    def test_exit_2_and_names_the_section_on_all_six_audits(self):
        for audit, section in AUDITS.items():
            with self.subTest(audit=audit):
                r = run(audit, build(json.dumps({"unrelated": {}})))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("REFUSED", r.stderr)
                self.assertIn(f"has no '{section}' section", r.stderr)
                self.assertNotIn("Traceback", r.stderr)


class UndeclaredArchFileRefuses(unittest.TestCase):
    def test_exit_2_naming_the_key_on_all_six_audits(self):
        for audit in AUDITS:
            with self.subTest(audit=audit):
                r = run(audit, build(json.dumps({"unrelated": {}}),
                                     audits={}))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("does not set audits.archRulesFile", r.stderr)
                self.assertNotIn("Traceback", r.stderr)


class MalformedArchFileRefuses(unittest.TestCase):
    """Valid JSON of the wrong shape must refuse, never crash.

    The bare-string case is the measured defect: `json.loads('"…"')` returns a
    str, `"layerBoundaries" in "layerBoundaries"` is a substring test that
    passes, and `rules[section]` then raised TypeError at exit 1 — a traceback
    a harness reads as findings. engine/arch.load now type-checks the parse.
    """

    CASES = {"bare-string": '"layerBoundaries"',
             "array": "[1, 2]",
             "invalid-json": "{oops"}

    def test_exit_2_without_traceback_on_all_six_audits(self):
        for label, text in self.CASES.items():
            for audit in AUDITS:
                with self.subTest(case=label, audit=audit):
                    r = run(audit, build(text))
                    self.assertEqual(r.returncode, 2,
                                     f"{label}: {r.stdout + r.stderr}")
                    self.assertIn("REFUSED", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertNotIn("TypeError", r.stderr)


class ScaffoldedTemplateNeverReadsClean(unittest.TestCase):
    """The shipped arch-rules scaffold is all TODO — every audit must refuse.

    A freshly init.py'd project exiting 0 here would be the governing failure
    with a fresh coat of paint: the check matched nothing and called it a pass.
    """

    EXPECTED = {
        # the vocabulary refusal added when this test was written: a TODO
        # string is not a name, it matches nothing, and the run reported a
        # confident zero over real files before this row existed.
        "audit_error_handling": "TODO placeholders",
        "audit_api_consistency": "matched no files",
        "audit_contract_headers": "REFUSING TO RUN",
        "audit_layer_boundaries": "TODO placeholders",
        "audit_route_coverage": "has no 'routeCoverage' section",
        "audit_cache_ttl_coverage": "has no 'cacheTtlCoverage' section",
    }

    def test_exit_2_on_every_audit(self):
        scaffold = (PLUGIN / "templates/dot-backend-suite/"
                           "arch-rules.json.template").read_text()
        for audit, fragment in self.EXPECTED.items():
            with self.subTest(audit=audit):
                r = run(audit, build(scaffold))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("REFUS", r.stderr)
                self.assertIn(fragment, r.stderr)
                self.assertNotIn("Traceback", r.stderr)


class LanguageAdapterRefusals(unittest.TestCase):
    """Adapter-bound audits refuse on absent/unknown adapters.lang; the
    route-table audits are text scans and keep working without one."""

    def test_adapter_bound_audits_refuse(self):
        for lang in (None, "cobol"):
            for audit in ADAPTER_BOUND:
                with self.subTest(audit=audit, lang=lang):
                    section = AUDITS[audit]
                    r = run(audit, valid({section: VALID_SECTION[section]},
                                         lang=lang))
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    # The refusal wording differs by path (the audit's own
                    # Refused vs adapters.load's), but every one of them is
                    # marked INERT: could-not-check, not clean.
                    self.assertIn("INERT", r.stderr)
                    if lang is None:
                        self.assertIn("adapters.lang", r.stderr)
                    else:
                        self.assertIn("unknown language adapter 'cobol'",
                                      r.stderr)
                    self.assertNotIn("Traceback", r.stderr)

    def test_lang_independent_audits_still_find_their_violation(self):
        # Ghost action: a route whose controller does not exist, and a route
        # with no TTL in config/app.php. Found with or without adapters.lang
        # — asserted rather than assumed, because "these two don't need a
        # adapter" is a claim about code that could change.
        files = {"routes/api.php": "<?php\n$router->get('/x', "
                                   "['uses' => 'GhostController@index']);\n"}
        for audit, fragment in (("audit_route_coverage", "GhostController@index"),
                                ("audit_cache_ttl_coverage", "GhostController@index")):
            for lang in (None, "php"):
                with self.subTest(audit=audit, lang=lang):
                    section = AUDITS[audit]
                    r = run(audit, valid({section: VALID_SECTION[section]},
                                         lang=lang, files=files))
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn(fragment, r.stdout + r.stderr)
                    self.assertNotIn("Traceback", r.stderr)


class MissingProfileInputRefuses(unittest.TestCase):
    """`SystemExit(message)` exits 1 — this suite's findings code. A missing
    input is "could not check", so the audits now raise through
    project.need_refused (exit 2) with the same named message."""

    def test_error_handling_without_fileglob_exits_2(self):
        r = run("audit_error_handling", valid({"errorHandling": dict(VOCAB)},
                                              file_glob=False))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("source.fileGlob", r.stderr)
        self.assertIn("REFUSED", r.stderr)

    def test_api_consistency_without_exceptions_file_exits_2(self):
        r = run("audit_api_consistency",
                valid({"apiConsistency": VALID_SECTION["apiConsistency"]},
                      exceptions_file=False))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("audits.exceptionsFile", r.stderr)
        self.assertIn("REFUSED", r.stderr)


class PlantedViolationsStillFound(unittest.TestCase):
    """The supported rows: each audit that runs must still find its violation.

    Without these, every refusal above could pass because the audit is inert
    rather than because it refused. The two audits without a row here carry
    their finding-depth in their own tests (contract_headers) or in the
    envelope test over the ApiConsistency class (findings_envelope).
    """

    def test_layer_boundaries_finds_the_planted_import(self):
        r = run("audit_layer_boundaries",
                valid({"layerBoundaries": LAYER_RULES}))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("NEW LAYER-BOUNDARY VIOLATIONS", r.stdout)

    def test_error_handling_finds_the_unguarded_client_call(self):
        files = {"app/Api.php": "<?php\nnamespace App;\nclass Api {\n"
                                "    public function f() {\n"
                                "        return Http::get('/orders');\n"
                                "    }\n}\n"}
        r = run("audit_error_handling", valid({"errorHandling": dict(VOCAB)},
                                              files=files))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("1 critical", r.stdout)
        self.assertIn("guardApiCall", r.stdout + r.stderr)

    def test_route_coverage_finds_the_dead_route(self):
        files = {"routes/api.php": "<?php\n$router->get('/x', "
                                   "['uses' => 'GhostController@index']);\n"}
        r = run("audit_route_coverage",
                valid({"routeCoverage": ROUTE_RULES}, files=files))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GhostController@index", r.stdout + r.stderr)

    def test_cache_ttl_coverage_finds_the_missing_ttl(self):
        files = {"routes/api.php": "<?php\n$router->get('/x', "
                                   "['uses' => 'GhostController@index']);\n",
                 "config/app.php": "<?php\nreturn [];\n"}
        r = run("audit_cache_ttl_coverage",
                valid({"cacheTtlCoverage": CACHE_RULES}, files=files))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GhostController@index", r.stdout + r.stderr)

    def test_api_consistency_runs_and_counts_its_sweep(self):
        # A real run, not a finding: 2 of 4 checks on, the other two off with
        # their `why` printed. The point is the sweep happened — without this
        # row the refusal rows above could pass against an audit that never
        # reads its config at all.
        r = run("audit_api_consistency",
                valid({"apiConsistency": VALID_SECTION["apiConsistency"]}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("checks clean over", r.stdout)
        self.assertRegex(r.stdout, r"\d+ file\(s\)")
        self.assertIn("probe: server tree", r.stdout)


if __name__ == "__main__":
    unittest.main()
