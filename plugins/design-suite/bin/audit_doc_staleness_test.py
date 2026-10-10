#!/usr/bin/env python3
"""Tests for audit_doc_staleness.py. Stdlib-only (unittest), matching this
project's Python-tooling convention (docs/INSTRUCTIONS.md §13) — no pytest.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_doc_staleness_test.py"
"""
from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_doc_staleness as ads  # noqa: E402

TODAY = datetime.date(2026, 9, 14)


class FindStatedDateTest(unittest.TestCase):
    def test_footer_with_real_date(self):
        text = "# Doc\n\nSome body.\n\n_Last updated: 2026-08-01_\n"
        stated = ads.find_stated_date(text)
        self.assertIsNotNone(stated)
        self.assertEqual(stated.source, "footer")
        self.assertEqual(stated.date, datetime.date(2026, 8, 1))

    def test_footer_with_trailing_space_before_closing_underscore(self):
        # RFC.md.template / POSTMORTEM.md.template / RELEASE.md.template all
        # use "_Last updated: <!-- DERIVED --> _" (space before the final _).
        text = "_Last updated: 2026-08-01 _\n"
        stated = ads.find_stated_date(text)
        self.assertIsNotNone(stated)
        self.assertEqual(stated.date, datetime.date(2026, 8, 1))

    def test_footer_placeholder_is_unparseable_not_fresh(self):
        text = "_Last updated: <!-- DERIVED --> _\n"
        stated = ads.find_stated_date(text)
        self.assertIsNotNone(stated)
        self.assertEqual(stated.source, "footer")
        self.assertIsNone(stated.date)

    def test_footer_install_date_placeholder_is_unparseable(self):
        text = "_Last updated: <!-- DERIVED: install date -->_\n"
        stated = ads.find_stated_date(text)
        self.assertIsNotNone(stated)
        self.assertIsNone(stated.date)

    def test_header_date_field(self):
        text = "# RFC\n\nDate: 2026-07-01\nStatus: open\n\nBody.\n"
        stated = ads.find_stated_date(text)
        self.assertIsNotNone(stated)
        self.assertEqual(stated.source, "header `Date:` field")
        self.assertEqual(stated.date, datetime.date(2026, 7, 1))

    def test_header_dated_phrase(self):
        text = "# Proposal, dated 2026-06-01\n\nBody.\n"
        stated = ads.find_stated_date(text)
        self.assertIsNotNone(stated)
        self.assertEqual(stated.date, datetime.date(2026, 6, 1))

    def test_no_signal_at_all(self):
        text = "# Doc\n\nJust prose, no date convention anywhere.\n"
        self.assertIsNone(ads.find_stated_date(text))

    def test_snippet_mentioning_the_convention_is_not_a_footer(self):
        # commands/audit-assets.md and commands/review-docs.md reference the
        # "_Last updated:" convention inside shell snippets — those lines do
        # not start the line with the label, so they must not match.
        text = (
            '```bash\n'
            "grep -c \"^_Last updated:\" some_file.md\n"
            "footer=$(grep -oE '_Last updated: [0-9]{4}-[0-9]{2}-[0-9]{2}' \"$rel\")\n"
            '```\n'
        )
        self.assertIsNone(ads.find_stated_date(text))

    def test_footer_preferred_over_header_when_both_present(self):
        text = "Date: 2026-01-01\n\nBody.\n\n_Last updated: 2026-08-01_\n"
        stated = ads.find_stated_date(text)
        self.assertEqual(stated.source, "footer")
        self.assertEqual(stated.date, datetime.date(2026, 8, 1))


class CheckDocTest(unittest.TestCase):
    def test_fresh_doc_produces_no_finding(self):
        text = "_Last updated: 2026-09-01_\n"  # 13 days before TODAY
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertIsNone(finding)
        self.assertEqual(status, "fresh")

    def test_stale_doc_flags_should_fix_and_names_it_honestly(self):
        text = "_Last updated: 2026-01-01_\n"  # well past 90 days
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertEqual(status, "stale")
        self.assertEqual(finding.check, "stale_by_stated_date")
        self.assertEqual(finding.severity, "should_fix")
        # The governing-principle requirement: never say "verified".
        self.assertNotIn("verified", finding.detail.lower())
        self.assertIn("NOT", finding.detail)

    def test_placeholder_doc_is_no_finding_but_unparseable_status(self):
        text = "_Last updated: <!-- DERIVED -->_\n"
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertEqual(status, "unparseable")
        self.assertEqual(finding.check, "unparseable_date")
        self.assertEqual(finding.severity, "info")

    def test_doc_with_no_signal_produces_no_finding(self):
        text = "# Doc\n\nNo date convention here.\n"
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertIsNone(finding)
        self.assertEqual(status, "no_signal")

    def test_future_dated_doc_is_flagged_not_treated_as_fresh(self):
        text = "_Last updated: 2026-12-25_\n"  # after TODAY
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertEqual(status, "unparseable")
        self.assertEqual(finding.check, "future_dated")

    def test_exactly_at_threshold_is_not_yet_stale(self):
        dated = TODAY - datetime.timedelta(days=90)
        text = f"_Last updated: {dated.isoformat()}_\n"
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertIsNone(finding)
        self.assertEqual(status, "fresh")

    def test_one_day_past_threshold_is_stale(self):
        dated = TODAY - datetime.timedelta(days=91)
        text = f"_Last updated: {dated.isoformat()}_\n"
        finding, status = ads.check_doc("doc.md", text, TODAY, stale_days=90)
        self.assertEqual(status, "stale")


class RunAuditTallyTest(unittest.TestCase):
    def test_tally_accounts_for_every_file(self):
        files = {
            "fresh.md": "_Last updated: 2026-09-01_\n",
            "stale.md": "_Last updated: 2020-01-01_\n",
            "placeholder.md": "_Last updated: <!-- DERIVED -->_\n",
            "silent.md": "# No convention here.\n",
        }
        findings, tally = ads.run_audit(files, TODAY, stale_days=90)
        self.assertEqual(tally, {"stale": 1, "fresh": 1, "unparseable": 1, "no_signal": 1})
        self.assertEqual(len(findings), 2)  # stale + unparseable; fresh/no_signal are silent


if __name__ == "__main__":
    unittest.main()
