#!/usr/bin/env python3
"""Tests for the Dart adapter's hardcoded-value checks. Stdlib-only (unittest),
matching this project's Python-tooling convention (docs/INSTRUCTIONS.md §13) —
no pytest. Fixtures are synthetic snippets, not the live lib/ tree, so these
stay stable as the real findings get fixed out from under them.

The zero and runtime-value cases below are regressions with a price tag: they
accounted for 61 of 147 findings on the mobile app (54 zero-only insets, 7
MediaQuery insets), i.e. 41% of a backlog that was being carried as real design
debt and re-triaged by hand.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens_dart_test.py"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_suite.adapters import dart  # noqa: E402

ACCESSOR = "AppTokens"


def flags(snippet: str) -> bool:
    """True if the edge_insets check would report `snippet` as a violation."""
    m = dart.EDGE_INSETS_RE.search(snippet)
    assert m is not None, f"fixture did not match EDGE_INSETS_RE: {snippet}"
    return dart._has_raw_number(m.group(2), ACCESSOR)


class EdgeInsetsRawNumbers(unittest.TestCase):
    def test_bare_number_is_a_violation(self):
        self.assertTrue(flags("EdgeInsets.all(16)"))

    def test_named_bare_number_is_a_violation(self):
        self.assertTrue(flags("EdgeInsets.symmetric(horizontal: 12)"))

    def test_raw_number_alongside_a_token_is_still_a_violation(self):
        self.assertTrue(
            flags("EdgeInsets.only(left: AppTokens.space16, top: 4)"))

    def test_fully_tokenised_is_clean(self):
        self.assertFalse(
            flags("EdgeInsets.symmetric(horizontal: AppTokens.space16)"))


class ZeroIsNotAViolation(unittest.TestCase):
    """There is no zero token to reach for — AppTokens.space0 does not and
    should not exist — so `0` is already the clearest way to write "no inset"."""

    def test_zero_alongside_tokens_is_clean(self):
        self.assertFalse(flags(
            "EdgeInsets.fromLTRB(AppTokens.space16, 0, AppTokens.space16, "
            "AppTokens.space12)"))

    def test_bare_zero_is_clean(self):
        self.assertFalse(flags("EdgeInsets.all(0)"))

    def test_named_zero_is_clean(self):
        self.assertFalse(flags("EdgeInsets.only(top: 0)"))

    def test_decimal_zero_is_clean(self):
        self.assertFalse(flags("EdgeInsets.all(0.0)"))

    def test_a_real_number_beside_a_zero_is_still_a_violation(self):
        self.assertTrue(flags("EdgeInsets.only(top: 0, bottom: 8)"))


class RuntimeValuesAreNotViolations(unittest.TestCase):
    """An argument with no numeric literal has nothing to tokenise. The keyboard
    inset is the common case and appeared 7 times on the mobile app."""

    def test_media_query_inset_is_clean(self):
        self.assertFalse(flags(
            "EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom)"))

    def test_plain_variable_is_clean(self):
        self.assertFalse(flags("EdgeInsets.only(bottom: bottom)"))


class Zeros(unittest.TestCase):
    def test_recognises_zero_spellings(self):
        for text in ("0", "0.0", "-0", " 0 ", "00", "0.00"):
            self.assertTrue(dart._is_zero(text), text)

    def test_rejects_non_zero(self):
        for text in ("1", "0.5", "-4", "10", "0.01"):
            self.assertFalse(dart._is_zero(text), text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
