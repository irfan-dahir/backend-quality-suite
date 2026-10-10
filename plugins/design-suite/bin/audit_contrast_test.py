#!/usr/bin/env python3
"""Tests for WCAG contrast scoring and its refusals.

Written under this directory's standing rule: **every refusal is tested next to
the positive case it must not swallow.** A contrast audit that refuses on
everything is not safe, it is broken — and a contrast audit that refuses on
nothing is the pointer-shaped hole this file exists to close.

The ratio arithmetic is checked against values fixed by WCAG 2.1 rather than
against whatever this implementation happens to produce: black on white is
exactly 21:1, a colour against itself is exactly 1:1, and #767676 on white is the
canonical 4.54:1 that the W3C's own quick-reference uses as the boundary case for
AA body text. A test that only asserted "the number did not change" would keep
passing through a sign error.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))

from _bootstrap import PLUGIN_ROOT  # noqa: E402

from design_suite.engine import contrast as C  # noqa: E402

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# A palette in the shape `token_declarations()` returns: name -> value TEXT,
# unparsed, in three syntaxes on purpose. The Dart `Color(0xFF...)` form is what
# this repo's own adapter emits; the others are what a web consumer would.
PALETTE = {
    "colorSurface": "Color(0xFFFFFFFF)",
    "colorTextPrimary": "Color(0xFF000000)",
    "colorTextMuted": "#767676",
    "colorAccent": "rgb(5, 103, 141)",
    "colorFaint": "#DDDDDD",
}

GOOD_PAIR = {
    "name": "body text on surface",
    "foreground": "colorTextPrimary",
    "background": "colorSurface",
    "minRatio": 4.5,
}


def _write_pairs(root: Path, payload) -> Path:
    path = root / C.PAIRS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str)
                    else json.dumps(payload, indent=2))
    return path


class Arithmetic(unittest.TestCase):
    """The half of this audit that is fixed by the spec, not by the project."""

    def test_black_on_white_is_the_maximum_21(self):
        self.assertAlmostEqual(C.ratio(BLACK, WHITE), 21.0, places=6)

    def test_a_colour_against_itself_is_the_minimum_1(self):
        self.assertAlmostEqual(C.ratio(WHITE, WHITE), 1.0, places=6)
        self.assertAlmostEqual(C.ratio((5, 103, 141), (5, 103, 141)), 1.0, places=6)

    def test_ratio_is_order_independent_as_wcag_defines_it(self):
        self.assertAlmostEqual(C.ratio(BLACK, WHITE), C.ratio(WHITE, BLACK), places=9)

    def test_the_canonical_aa_boundary_colour(self):
        # #767676 on white is the W3C's own worked example of the lightest grey
        # that still clears 4.5:1. If this drifts, the gamma expansion is wrong.
        self.assertAlmostEqual(C.ratio((0x76, 0x76, 0x76), WHITE), 4.54, places=2)

    def test_luminance_endpoints(self):
        self.assertAlmostEqual(C.relative_luminance(BLACK), 0.0, places=9)
        self.assertAlmostEqual(C.relative_luminance(WHITE), 1.0, places=9)


class ColourParsing(unittest.TestCase):
    def test_every_supported_syntax_reaches_the_same_triple(self):
        for text in ("#05678D", "#05678DFF", "0xFF05678D", "Color(0xFF05678D)",
                     "rgb(5, 103, 141)", "rgba(5, 103, 141, 1.0)"):
            with self.subTest(text=text):
                self.assertEqual(C.parse_color(text), (5, 103, 141))

    def test_three_and_four_digit_shorthand_expands(self):
        self.assertEqual(C.parse_color("#abc"), (0xAA, 0xBB, 0xCC))
        self.assertEqual(C.parse_color("#abcf"), (0xAA, 0xBB, 0xCC))

    # --- refusals, each beside the positive case above ---

    def test_refuses_an_unparseable_value_rather_than_defaulting_to_black(self):
        # The failure this guards: an unreadable colour silently becoming (0,0,0)
        # scores a near-maximum ratio against a light surface and PASSES.
        with self.assertRaises(C.ContrastError):
            C.parse_color("Curves.easeInOut")
        with self.assertRaises(C.ContrastError):
            C.parse_color("")

    def test_refuses_a_translucent_colour_but_not_a_fully_opaque_one(self):
        with self.assertRaises(C.ContrastError):
            C.parse_color("Color(0x80000000)")
        with self.assertRaises(C.ContrastError):
            C.parse_color("rgba(0, 0, 0, 0.5)")
        with self.assertRaises(C.ContrastError):
            C.parse_color("#00000080")
        # ...and the opaque forms of the same colour still answer.
        self.assertEqual(C.parse_color("Color(0xFF000000)"), BLACK)
        self.assertEqual(C.parse_color("rgba(0, 0, 0, 1)"), BLACK)

    def test_refuses_an_out_of_range_channel(self):
        with self.assertRaises(C.ContrastError):
            C.parse_color("rgb(300, 0, 0)")
        self.assertEqual(C.parse_color("rgb(255, 0, 0)"), (255, 0, 0))


class Scoring(unittest.TestCase):
    def test_a_passing_pair_and_a_failing_pair_are_both_recorded(self):
        pairs = [
            GOOD_PAIR,
            {"name": "faint on surface", "foreground": "colorFaint",
             "background": "colorSurface", "minRatio": 4.5},
        ]
        results = C.score(pairs, PALETTE)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["passed"])
        self.assertEqual(results[0]["ratio"], 21.0)
        self.assertFalse(results[1]["passed"])

    def test_passes_are_kept_so_a_run_that_scored_nothing_is_distinguishable(self):
        # The REPORTS_CHECKS polarity depends on this: an all-passing run must
        # emit records, or it is byte-identical to an audit that never ran.
        results = C.score([GOOD_PAIR], PALETTE)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["passed"])

    def test_the_threshold_is_the_pairs_own_not_a_global_constant(self):
        muted = {"name": "muted", "foreground": "colorTextMuted",
                 "background": "colorSurface"}
        # 4.54:1 — clears the default 4.5 body-text bar, fails a AAA 7:1 bar.
        self.assertTrue(C.score([dict(muted)], PALETTE)[0]["passed"])
        strict = dict(muted, minRatio=C.AAA_NORMAL_TEXT)
        self.assertFalse(C.score([strict], PALETTE)[0]["passed"])

    def test_default_threshold_is_aa_body_text(self):
        scored = C.score([{"name": "n", "foreground": "colorTextPrimary",
                           "background": "colorSurface"}], PALETTE)
        self.assertEqual(scored[0]["min_ratio"], C.AA_NORMAL_TEXT)

    # --- refusals ---

    def test_refuses_a_pair_naming_an_undeclared_token_rather_than_skipping_it(self):
        # THE load-bearing one. A renamed token that silently drops out of the run
        # leaves the pass rate looking unchanged while the check stopped happening.
        missing = {"name": "renamed", "foreground": "colorOnBrandRenamed",
                   "background": "colorSurface"}
        with self.assertRaises(C.ContrastError) as caught:
            C.score([GOOD_PAIR, missing], PALETTE)
        self.assertIn("colorOnBrandRenamed", str(caught.exception))
        # ...and the sibling pair that IS resolvable still scores on its own.
        self.assertTrue(C.score([GOOD_PAIR], PALETTE)[0]["passed"])

    def test_refuses_when_a_declared_token_value_is_not_a_colour(self):
        broken = dict(PALETTE, colorSurface="AppTokens.surfaceElevated")
        with self.assertRaises(C.ContrastError):
            C.score([GOOD_PAIR], broken)
        self.assertTrue(C.score([GOOD_PAIR], PALETTE)[0]["passed"])

    def test_an_empty_palette_refuses_rather_than_scoring_zero_failures(self):
        with self.assertRaises(C.ContrastError):
            C.score([GOOD_PAIR], {})


class PairListLoading(unittest.TestCase):
    def test_loads_a_valid_pair_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_pairs(root, {"schemaVersion": 1, "pairs": [GOOD_PAIR]})
            self.assertEqual(len(C.load_pairs(root)), 1)

    def test_refuses_a_missing_pair_list_rather_than_using_a_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(C.ContrastError) as caught:
                C.load_pairs(Path(tmp))
            self.assertIn(C.PAIRS_FILE, str(caught.exception))

    def test_refuses_an_unreadable_pair_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_pairs(root, "{ not json")
            with self.assertRaises(C.ContrastError):
                C.load_pairs(root)
            # ...and a readable one at the same path still loads.
            _write_pairs(root, {"pairs": [GOOD_PAIR]})
            self.assertEqual(len(C.load_pairs(root)), 1)

    def test_refuses_an_empty_pair_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_pairs(root, {"pairs": []})
            with self.assertRaises(C.ContrastError):
                C.load_pairs(root)

    def test_refuses_a_pair_missing_a_required_field(self):
        for field in ("name", "foreground", "background"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                incomplete = {k: v for k, v in GOOD_PAIR.items() if k != field}
                _write_pairs(root, {"pairs": [incomplete]})
                with self.assertRaises(C.ContrastError):
                    C.load_pairs(root)

    def test_refuses_two_pairs_with_the_same_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_pairs(root, {"pairs": [GOOD_PAIR, dict(GOOD_PAIR,
                                                          background="colorFaint")]})
            with self.assertRaises(C.ContrastError):
                C.load_pairs(root)

    def test_refuses_a_min_ratio_outside_the_wcag_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_pairs(root, {"pairs": [dict(GOOD_PAIR, minRatio=45)]})
            with self.assertRaises(C.ContrastError):
                C.load_pairs(root)
            _write_pairs(root, {"pairs": [dict(GOOD_PAIR, minRatio=4.5)]})
            self.assertEqual(len(C.load_pairs(root)), 1)


class ShipsWithTheCommand(unittest.TestCase):
    def test_the_command_doc_is_no_longer_a_pointer(self):
        """The whole point of this file: the command claims an implementation now,
        so the catalogue's maturity must not still say it points elsewhere."""
        doc = (PLUGIN_ROOT / "commands" / "audit-contrast.md").read_text()
        # The frontmatter line, not any mention: the body legitimately explains
        # what it used to be, and a substring check would fail on the history.
        maturity = [line for line in doc.splitlines()
                    if line.startswith("maturity:")]
        self.assertEqual(maturity, ["maturity: unverified"])
        self.assertIn("audit_contrast.py", doc)
        self.assertTrue((PLUGIN_ROOT / "bin" / "audit_contrast.py").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
