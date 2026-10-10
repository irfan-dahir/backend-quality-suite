#!/usr/bin/env python3
"""Tests for how a project's accepted exceptions are applied to findings.

Stdlib-only (unittest), per docs/INSTRUCTIONS.md §13.

The case that matters here is not "an exception suppresses a finding" — it is the
control beside it. `allowlistRegions` was read by nothing for the life of this
audit, and the failure was invisible because the findings it should have hidden
looked exactly like the findings it should not have (#108, measured in #104). So
every suppression test below carries a planted literal outside the exception,
and asserts it survived.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_suite.engine import exceptions as A  # noqa: E402

CATEGORIES = {"color": "color", "edge_insets": "spacing"}


def finding(path: str, kind: str = "color") -> dict:
    return {"file": path, "line": 1, "kind": kind, "snippet": "Color(0xFF000000)"}


def partition(findings, exceptions):
    return A.partition(findings, CATEGORIES, A.exemptions(exceptions),
                       A.report_anyway(exceptions))


REGIONS = {"color": {"allowlistRegions": [
    {"path": "lib/a/tabs.dart", "scope": "gradients", "reason": "spectrum",
     "appliedBy": "reader"},
    {"path": "lib/chat/**", "scope": "scrim", "reason": "dark wash"},
]}}


class AllowlistRegions(unittest.TestCase):
    def test_exact_path_is_suppressed_and_its_control_is_not(self):
        kept, suppressed = partition(
            [finding("lib/a/tabs.dart"), finding("lib/a/other.dart")], REGIONS)
        self.assertEqual([f["file"] for f in suppressed], ["lib/a/tabs.dart"])
        self.assertEqual([f["file"] for f in kept], ["lib/a/other.dart"])

    def test_glob_path_is_suppressed_and_its_control_is_not(self):
        kept, suppressed = partition(
            [finding("lib/chat/deep/bubble.dart"), finding("lib/chatty.dart")],
            REGIONS)
        self.assertEqual([f["file"] for f in suppressed],
                         ["lib/chat/deep/bubble.dart"])
        self.assertEqual([f["file"] for f in kept], ["lib/chatty.dart"])

    def test_exemption_is_scoped_to_its_own_category(self):
        """A file allowed to hold raw colours is still held to the spacing rules."""
        kept, suppressed = partition(
            [finding("lib/a/tabs.dart", "edge_insets")], REGIONS)
        self.assertEqual(len(kept), 1)
        self.assertEqual(suppressed, [])


class AllowlistFiles(unittest.TestCase):
    """The pre-existing key, unchanged in effect."""

    def test_still_suppresses(self):
        kept, suppressed = partition(
            [finding("lib/brand.dart"), finding("lib/other.dart")],
            {"color": {"allowlistFiles": [{"path": "lib/brand.dart",
                                           "reason": "brand"}]}})
        self.assertEqual([f["file"] for f in suppressed], ["lib/brand.dart"])
        self.assertEqual([f["file"] for f in kept], ["lib/other.dart"])


class ReportAnyway(unittest.TestCase):
    def test_outranks_a_glob_that_would_otherwise_cover_it(self):
        exceptions = {"color": {
            "allowlistRegions": [{"path": "lib/chat/**", "reason": "scrim"}],
            "reportAnyway": [{"path": "lib/chat/debt.dart", "reason": "open item"}],
        }}
        kept, suppressed = partition(
            [finding("lib/chat/debt.dart"), finding("lib/chat/bubble.dart")],
            exceptions)
        self.assertEqual([f["file"] for f in kept], ["lib/chat/debt.dart"])
        self.assertEqual([f["file"] for f in suppressed], ["lib/chat/bubble.dart"])


class SuppressionIsCountable(unittest.TestCase):
    """The governing principle, applied to the audit's own silence: a finding a
    documented exception hid must not read the same as a finding that never was."""

    def test_report_names_the_entry_and_counts_what_it_hid(self):
        _, suppressed = partition(
            [finding("lib/a/tabs.dart"), finding("lib/chat/x.dart")], REGIONS)
        report = A.report(suppressed)
        self.assertEqual(report["count"], 2)
        rows = {r["path"]: r for r in report["byException"]}
        self.assertEqual(rows["lib/a/tabs.dart"]["count"], 1)
        self.assertEqual(rows["lib/a/tabs.dart"]["scope"], "gradients")
        self.assertEqual(rows["lib/a/tabs.dart"]["exceptionKey"], "allowlistRegions")
        self.assertEqual(rows["lib/chat/**"]["count"], 1)

    def test_nothing_suppressed_reports_zero_rather_than_nothing(self):
        report = A.report([])
        self.assertEqual(report, {"count": 0, "byException": []})


class MalformedEntriesAreIgnoredNotFatal(unittest.TestCase):
    def test_entry_without_a_path_suppresses_nothing(self):
        kept, suppressed = partition(
            [finding("lib/a.dart")],
            {"color": {"allowlistRegions": [{"reason": "no path"}, "not a dict"]}})
        self.assertEqual(len(kept), 1)
        self.assertEqual(suppressed, [])

    def test_non_dict_category_is_skipped(self):
        kept, _ = partition([finding("lib/a.dart")], {"exceptionsVersion": 1})
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
