#!/usr/bin/env python3
"""Tests for band-1 token repair. Stdlib-only (unittest), like every other test
here — no pytest.

The fixture project is synthetic and built per-test, for the reason RFC-0003 §5
gives: a wrong band-1 rewrite is worse than any false positive, so correctness
has to be checked against a token set whose every value is known, not against a
real app whose tokens change underneath the assertions. The real app is measured
separately, read-only, and only for the band split.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens_test.py"
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN.parents[0]))

from design_suite.adapters.base import Check  # noqa: E402
from design_suite.engine import token_repair as R  # noqa: E402

TOKENS = """
class AppTokens {
  static const radiusSmall = 4.0;
  static const radiusMedium = 6.0;
  static const space4 = 4.0;
  static const space8 = 8.0;
  static const space16 = 16.0;
  static const colorPrimary = Color(0xFF05678D);
  static const durationFast = Duration(milliseconds: 150);
  static const curveStandard = Curves.easeInOut;
}
"""

# space4 and radiusSmall are both 4.0 — a deliberate ambiguity, but in different
# categories, so a spacing literal of 4 must still be band 1. The trap this
# guards is a repairer that searches every token rather than the right category
# and turns a padding into a corner radius.
TOKENS_AMBIGUOUS = TOKENS.replace(
    "static const space8 = 8.0;",
    "static const space8 = 8.0;\n  static const spaceGutter = 8.0;")

CATEGORIES = {"spacing": "space", "radius": "radius", "color": "color",
              "duration": "duration", "curve": "curve"}


def build(root: Path, dart_source: str, tokens: str = TOKENS,
          categories=CATEGORIES, accessor="AppTokens", token_path="tokens.dart",
          write_tokens=True):
    (root / ".design-suite").mkdir(parents=True, exist_ok=True)
    (root / "lib").mkdir(parents=True, exist_ok=True)
    if write_tokens:
        (root / token_path).write_text(tokens)
    profile = {
        "adapters": {"lang": "dart"},
        "source": {"root": "lib", "fileGlob": "**/*.dart"},
        "tokens": {"source": {"kind": "file", "path": token_path}},
        "audits": {"archRulesFile": ".design-suite/arch-rules.json"},
    }
    if accessor:
        profile["tokens"]["accessor"] = accessor
    (root / ".design-suite" / "profile.json").write_text(json.dumps(profile))
    (root / ".design-suite" / "arch-rules.json").write_text(
        json.dumps({"unusedTokens": {"categories": categories}}))
    (root / ".design-suite" / "exceptions.json").write_text("{}")
    (root / "lib" / "screen.dart").write_text(dart_source)


def run(root: Path, *extra):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run(
        [sys.executable, str(BIN / "repair_tokens.py"), *extra],
        capture_output=True, text=True, env=env)


class Bands(unittest.TestCase):
    def repair(self, source, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, source, **kwargs)
            result = run(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            # The working tree is never touched — the whole contract of §3c.
            self.assertEqual((root / "lib" / "screen.dart").read_text(), source)
            return result

    def test_band_1_exact_single_match_is_rewritten(self):
        out = self.repair("const p = EdgeInsets.all(16);")
        self.assertIn("-const p = EdgeInsets.all(16);", out.stdout)
        self.assertIn("+const p = EdgeInsets.all(AppTokens.space16);", out.stdout)
        self.assertIn("band 1  deterministic      1", out.stderr)

    def test_band_1_respects_category_not_just_value(self):
        """4 is both space4 and radiusSmall; a padding must become space4."""
        out = self.repair("const p = EdgeInsets.only(top: 4);")
        self.assertIn("+const p = EdgeInsets.only(top: AppTokens.space4);", out.stdout)

    def test_band_2_two_tokens_share_a_value(self):
        out = self.repair("const p = EdgeInsets.all(8);", tokens=TOKENS_AMBIGUOUS)
        self.assertIn("band 2  ambiguous          1", out.stderr)
        self.assertEqual(out.stdout, "")
        self.assertIn("space8, spaceGutter", out.stderr)

    def test_band_2_close_but_not_equal_is_never_rounded(self):
        """15 is not 16. A repairer that rounds changes what the screen looks
        like, silently, under a heading that says it was deterministic."""
        out = self.repair("const p = EdgeInsets.all(15);")
        self.assertEqual(out.stdout, "")
        self.assertIn("band 3  absent             1", out.stderr)

    def test_band_3_no_token_has_this_value(self):
        out = self.repair("const p = EdgeInsets.only(top: 5);")
        self.assertEqual(out.stdout, "")
        self.assertIn("band 3  absent             1", out.stderr)

    def test_mixed_expression_takes_the_worst_band(self):
        """One repairable argument beside one that is not: a partial rewrite of
        a single expression is a diff a reviewer cannot trust."""
        out = self.repair(
            "const p = EdgeInsets.symmetric(horizontal: 8, vertical: 3);")
        self.assertEqual(out.stdout, "")
        self.assertIn("band 3  absent             1", out.stderr)

    def test_zero_is_not_a_repair_site(self):
        out = self.repair(
            "const p = EdgeInsets.only(top: 0, bottom: 16);")
        self.assertIn("+const p = EdgeInsets.only(top: 0, bottom: AppTokens.space16);",
                      out.stdout)

    def test_colour_literal_is_repaired_case_and_alpha_insensitively(self):
        out = self.repair("const c = Color(0xff05678d);")
        self.assertIn("+const c = AppTokens.colorPrimary;", out.stdout)

    def test_duration_and_curve_literals_are_repaired(self):
        out = self.repair(
            "const d = Duration(milliseconds: 150);\nconst c = Curves.easeInOut;")
        self.assertIn("+const d = AppTokens.durationFast;", out.stdout)
        self.assertIn("+const c = AppTokens.curveStandard;", out.stdout)

    def test_several_sites_in_one_file_keep_their_offsets(self):
        out = self.repair(
            "const a = EdgeInsets.all(4);\nconst b = EdgeInsets.all(16);\n")
        self.assertIn("+const a = EdgeInsets.all(AppTokens.space4);", out.stdout)
        self.assertIn("+const b = EdgeInsets.all(AppTokens.space16);", out.stdout)

    def test_the_emitted_diff_applies_cleanly(self):
        """A diff that does not apply is a report with extra steps."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const a = EdgeInsets.all(4);\nconst b = BorderRadius.circular(6);\n")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            patch = run(root).stdout
            (root / "t.patch").write_text(patch)
            applied = subprocess.run(["git", "apply", "t.patch"], cwd=root,
                                     capture_output=True, text=True)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            after = (root / "lib" / "screen.dart").read_text()
            self.assertEqual(
                after,
                "const a = EdgeInsets.all(AppTokens.space4);\n"
                "const b = BorderRadius.circular(AppTokens.radiusMedium);\n")


class Refusals(unittest.TestCase):
    """RFC-0003 §2c. Every one of these would otherwise produce a *confident*
    wrong answer, because `dart.checks()` falls back to "AppTokens" whether or
    not the project has a token source at all."""

    def refuse(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const p = EdgeInsets.all(16);", **kwargs)
            result = run(root)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("REFUSING", result.stderr)
            return result

    def test_no_declared_token_source_refuses(self):
        out = self.refuse(token_path="missing/tokens.dart", write_tokens=False)
        self.assertIn("does not resolve", out.stderr)

    def test_no_declared_accessor_refuses(self):
        out = self.refuse(accessor=None)
        self.assertIn("tokens.accessor", out.stderr)

    def test_no_declared_categories_refuses(self):
        out = self.refuse(categories={})
        self.assertIn("categories", out.stderr)

    def test_empty_token_set_refuses_rather_than_reporting_band_3(self):
        """An unreadable token file must not report every literal as "no token
        exists" — that is the one band that tells a human to author one."""
        out = self.refuse(tokens="class AppTokens {}\n")
        self.assertIn("no tokens at all", out.stderr)


class CheckMode(unittest.TestCase):
    def test_check_exits_1_when_a_repair_is_available_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const p = EdgeInsets.all(16);")
            result = run(root, "--check")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")

    def test_check_exits_0_when_nothing_is_in_band_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const p = EdgeInsets.all(15);")
            self.assertEqual(run(root, "--check").returncode, 0)


class DiffTimeScoping(unittest.TestCase):
    """`--files` and `--bands-json`: what the pre-commit runner needs.

    Whole-repo band-1 repair fixed 0 of 33 findings on an already-migrated
    codebase (RFC-0003 §3a). These are the two capabilities that let the repair
    land where it pays instead — on the files a commit is touching — and let the
    caller tell an offered fix from an absent one.
    """

    def test_files_restricts_the_sweep_to_the_named_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const a = EdgeInsets.all(16);\n")
            (root / "lib" / "other.dart").write_text("const b = EdgeInsets.all(8);\n")
            out = run(root, "--files", "lib/other.dart")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("lib/other.dart", out.stdout)
            self.assertNotIn("screen.dart", out.stdout)

    def test_a_named_file_the_adapter_does_not_sweep_is_announced(self):
        """Silence here would read as "nothing to fix in that file"."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const a = EdgeInsets.all(16);\n")
            (root / "README.md").write_text("# not source\n")
            out = run(root, "--files", "README.md")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout, "")
            self.assertIn("README.md", out.stderr)
            self.assertIn("not looked at", out.stderr)

    def test_bands_json_names_a_band_for_every_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const a = EdgeInsets.all(16);\nconst b = EdgeInsets.all(7);\n")
            out = run(root, "--bands-json", "bands.json")
            self.assertEqual(out.returncode, 0, out.stderr)
            records = json.loads((root / "bands.json").read_text())["bands"]
            by_line = {r["line"]: r["band"] for r in records}
            self.assertEqual(by_line, {1: R.BAND_DETERMINISTIC, 2: R.BAND_ABSENT})
            # Keyed exactly as engine/scan.py keys an audit finding, or the caller
            # cannot match an offer to the finding it answers.
            self.assertEqual({"file", "line", "kind", "snippet", "candidates", "band"},
                             set(records[0]))


class Validation(unittest.TestCase):
    """Phase 2, V1: a candidate diff must be re-checked against the same check
    it claims to satisfy before it is ever offered — the Getafix pattern.
    `R.revalidates` is exercised directly with a synthetic check, because
    engineering a *real* dart finding whose deterministic substitution is
    technically wrong would mean deliberately breaking `dart.py`'s own
    partitioning logic, which is precisely what this feature guards against
    happening unnoticed. The synthetic case is the honest way to prove the
    mechanism: a repairer cannot tell "check I wrote a correct patch" apart
    from "check the patch actually clears the check" without this step.
    """

    def test_control_an_ordinary_correct_fix_still_validates(self):
        """The common case must not disappear: a patch that removes the raw
        literal a check keys off of clears the check and validates."""
        check = Check("bad", re.compile(r"\d+"))
        source = "BAD(5)"
        match = check.pattern.search(source)
        site = R.Site(match.start(), match.end(), "5", "x", ["ok"], "Q")
        self.assertTrue(R.revalidates(check, match, source, [site]))

    def test_a_substitution_that_does_not_clear_the_finding_is_caught(self):
        """An edge case where the deterministic substitution is technically
        wrong: the check's pattern matches the whole call regardless of what
        is inside it, so replacing the inner literal with a token reference
        does not make the check stop firing at the same offset. This is the
        one property this whole feature exists to catch — see issue #109,
        the corrupting `title_case` fix, for what an unvalidated diff cost
        elsewhere in this project."""
        check = Check("bad", re.compile(r"BAD\(.*?\)"))
        source = "BAD(5)"
        match = check.pattern.search(source)
        site = R.Site(4, 5, "5", "x", ["ok"], "Q")
        self.assertFalse(R.revalidates(check, match, source, [site]))

    def test_repair_tokens_reports_a_failed_validation_as_undeterminable(self):
        """End to end, in-process so `R.revalidates` can be forced to fail: a
        band-1 candidate that fails revalidation must not be silently dropped
        and must not be emitted as a working diff — it must surface as
        UNDETERMINABLE, `token_repair`'s own name for "cannot look", applied
        one layer up to "cannot trust this candidate"."""
        if str(BIN) not in sys.path:
            sys.path.insert(0, str(BIN))
        import importlib
        import io
        import contextlib

        original_revalidates = R.revalidates
        R.revalidates = lambda *a, **k: False
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                build(root, "const p = EdgeInsets.all(16);")
                bands_path = root / "bands.json"
                old_argv = sys.argv
                old_env = os.environ.get("CLAUDE_PROJECT_DIR")
                sys.argv = ["repair_tokens.py", "--bands-json", str(bands_path)]
                os.environ["CLAUDE_PROJECT_DIR"] = str(root)
                # REPO is computed at import time, so a fresh root needs a
                # fresh import — reload rather than import_module, which would
                # no-op on an already-cached module.
                if "repair_tokens" in sys.modules:
                    repair_tokens = importlib.reload(sys.modules["repair_tokens"])
                else:
                    repair_tokens = importlib.import_module("repair_tokens")
                stdout = io.StringIO()
                try:
                    with contextlib.redirect_stdout(stdout):
                        rc = repair_tokens.main()
                finally:
                    sys.argv = old_argv
                    if old_env is None:
                        os.environ.pop("CLAUDE_PROJECT_DIR", None)
                    else:
                        os.environ["CLAUDE_PROJECT_DIR"] = old_env
                self.assertEqual(rc, 0)
                # Never included as a working diff.
                self.assertEqual(stdout.getvalue(), "")
                records = json.loads(bands_path.read_text())["bands"]
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["band"], R.UNDETERMINABLE)
        finally:
            R.revalidates = original_revalidates


class Suggestions(unittest.TestCase):
    """Phase 2, S1: band-2 findings get a real, machine-readable channel."""

    def test_suggestions_json_carries_band_2_and_is_never_a_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const p = EdgeInsets.all(8);\n", tokens=TOKENS_AMBIGUOUS)
            out = run(root, "--suggestions-json", "sug.json",
                      "--bands-json", "bands.json")
            self.assertEqual(out.returncode, 0, out.stderr)
            # Never a diff: an ambiguous finding is proposed, not applied.
            self.assertEqual(out.stdout, "")

            suggestions = json.loads((root / "sug.json").read_text())["suggestions"]
            self.assertEqual(len(suggestions), 1)
            rec = suggestions[0]
            self.assertEqual(set(rec), {"file", "line", "kind", "snippet", "candidates"})
            self.assertEqual(rec["file"], "lib/screen.dart")
            self.assertEqual(rec["candidates"], ["space8", "spaceGutter"])

            # --bands-json and --suggestions-json must agree on band 2.
            bands = json.loads((root / "bands.json").read_text())["bands"]
            band2 = [b for b in bands if b["band"] == R.BAND_AMBIGUOUS]
            self.assertEqual(len(band2), 1)
            self.assertEqual(band2[0]["line"], rec["line"])
            self.assertEqual(band2[0]["candidates"], rec["candidates"])

    def test_suggestions_never_appear_in_the_out_envelope_as_band_1(self):
        """A mixed file: one band-1 finding (diffed) and one band-2 finding
        (suggested only) must not cross channels."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root,
                  "const a = EdgeInsets.all(16);\nconst b = EdgeInsets.all(8);\n",
                  tokens=TOKENS_AMBIGUOUS)
            out = run(root, "--suggestions-json", "sug.json")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("+const a = EdgeInsets.all(AppTokens.space16);", out.stdout)
            self.assertNotIn("+const b", out.stdout)
            self.assertNotIn("space8", out.stdout)

            suggestions = json.loads((root / "sug.json").read_text())["suggestions"]
            self.assertEqual([s["line"] for s in suggestions], [2])

    def test_no_sweepable_files_writes_an_empty_suggestions_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, "const a = EdgeInsets.all(16);\n")
            (root / "README.md").write_text("# not source\n")
            out = run(root, "--files", "README.md", "--suggestions-json", "sug.json")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads((root / "sug.json").read_text()),
                              {"suggestions": []})


class Equality(unittest.TestCase):
    def test_numeric_forms_of_the_same_value_are_equal(self):
        self.assertTrue(R.equal("16", "16.0"))

    def test_near_values_are_not_equal(self):
        self.assertFalse(R.equal("15.9", "16.0"))

    def test_six_and_eight_digit_hex_agree_on_opaque_colours(self):
        self.assertTrue(R.equal("Color(0x05678D)", "Color(0xFF05678D)"))

    def test_a_number_never_equals_an_expression(self):
        self.assertFalse(R.equal("150", "Duration(milliseconds: 150)"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
