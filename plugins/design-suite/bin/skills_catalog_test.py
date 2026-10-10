#!/usr/bin/env python3
"""Tests for skills_catalog.py — the user-facing catalogue generator.

The point of these is not that the file renders. It is that the generator
*refuses* in every case where its output would be a confident-looking table
built on nothing: an empty audit list, an unreadable disabled registry, an agent
that quietly gained a writing tool, a command that fell out of every cheat-sheet
bucket. A generated catalogue that degrades to a plausible blank is worse than no
catalogue, because nothing downstream can tell the two apart.

Run directly, or via `python3 plugins/design-suite/bin/run_tests.py`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import skills_catalog as sc  # noqa: E402
import catalog  # noqa: E402


class OneLiner(unittest.TestCase):
    def test_drops_the_trigger_clause(self):
        out = sc.one_liner(
            "Mechanically audit source for hardcoded design values. "
            "Use when asked to check design-token compliance.")
        self.assertEqual(out, "Mechanically audit source for hardcoded design values.")

    def test_keeps_capability_text_verbatim_and_invents_nothing(self):
        src = "Move a component into the shared design system, or demote one back."
        self.assertEqual(sc.one_liner(src), src)

    def test_joins_short_sentences_until_the_limit(self):
        out = sc.one_liner("Pointer, not an implementation. It lives elsewhere. "
                           "Use when asked about contrast.")
        self.assertEqual(out, "Pointer, not an implementation. It lives elsewhere.")

    def test_never_returns_empty_for_a_pure_trigger_description(self):
        out = sc.one_liner("Use when asked to do the thing.")
        self.assertTrue(out)

    def test_escapes_pipes_so_a_description_cannot_break_the_table(self):
        self.assertEqual(sc.one_liner("a | b"), "a \\| b")

    def test_truncates_long_text_at_a_word_boundary(self):
        out = sc.one_liner("word " * 200)
        self.assertTrue(out.endswith("…"))
        self.assertLess(len(out), 200)


class Buckets(unittest.TestCase):
    def setUp(self):
        self.gi = sc.group_index()

    def test_name_rules_beat_the_group_map(self):
        self.assertEqual(sc.bucket_of("audit-tokens", self.gi), "Audit")
        self.assertEqual(sc.bucket_of("add-asset", self.gi), "Assets")
        self.assertEqual(sc.bucket_of("sync-mock-api", self.gi), "Mock API")

    def test_falls_back_to_catalog_groups(self):
        self.assertEqual(sc.bucket_of("sync-docs", self.gi), "Document")
        self.assertEqual(sc.bucket_of("run-chain", self.gi), "Workflow")

    def test_unknown_command_is_visible_not_dropped(self):
        self.assertEqual(sc.bucket_of("not-a-real-command", self.gi), "Other")

    def test_every_bucket_name_used_by_a_rule_exists(self):
        used = {b for _, b in sc.NAME_RULES} | set(sc.GROUP_BUCKET.values())
        self.assertTrue(used <= set(sc.BUCKETS), used - set(sc.BUCKETS))


class RealRender(unittest.TestCase):
    """Against the real tree — these are the facts the doc asserts."""

    @classmethod
    def setUpClass(cls):
        data, problems = catalog.collect()
        if problems:
            raise AssertionError(f"catalog.collect() reported problems: {problems}")
        cls.data = data
        cls.text, cls.problems = sc.render(data)

    def test_renders_without_problems(self):
        self.assertEqual(self.problems, [])

    def test_committed_file_is_not_stale(self):
        self.assertTrue(sc.OUT.is_file(), "docs/SKILLS.md has not been generated")
        self.assertEqual(sc.OUT.read_text(), self.text,
                         "docs/SKILLS.md is stale — regenerate it")

    def test_every_command_appears_exactly_once(self):
        for plugin, entry in self.data.items():
            for s in entry["skills"]:
                self.assertEqual(self.text.count(f"| `/{s['name']}` |"), 1,
                                 f"/{s['name']} is not in exactly one skills table")

    def test_audits_come_from_discovery_not_from_here(self):
        rows, problems = sc.audits()
        self.assertEqual(problems, [])
        self.assertTrue(rows)
        for r in rows:
            self.assertIn(f"`{r['name']}`", self.text)

    def test_every_disabled_audit_is_named_with_a_reason(self):
        registry, problems = sc.disabled_detail()
        self.assertEqual(problems, [])
        self.assertTrue(registry, "the disabled registry is empty — if that is real, this "
                                  "test should be updated deliberately, not silently")
        for stem, entry in registry.items():
            self.assertIn(entry["reason"].split("(")[0].strip(), self.text)

    def test_maturity_renders_as_a_plain_marker_never_the_raw_word(self):
        self.assertIn("⚠️ use with review", self.text)
        self.assertNotIn("| unverified |", self.text)
        self.assertNotIn("| disabled |", self.text)

    def test_hook_matchers_do_not_break_the_table(self):
        for line in self.text.splitlines():
            if line.startswith("| `mock_api_reminders.py`"):
                self.assertEqual(line.count("|") - line.count("\\|"), 5)
                break
        else:
            self.fail("no hook row rendered")


class Refusals(unittest.TestCase):
    """The failure modes. Each of these must produce a problem, not a blank table."""

    def test_empty_audit_discovery_is_a_problem(self):
        original = sc.audits
        sc.audits = lambda: ([], ["repo_health.py --list produced no audits"])
        try:
            _, problems = sc.render(catalog.collect()[0])
        finally:
            sc.audits = original
        self.assertTrue(any("no audits" in p for p in problems))

    def test_unreadable_disabled_registry_is_a_problem(self):
        original = catalog.disabled_registry
        catalog.disabled_registry = lambda: ({}, "cannot import audit_discovery")
        try:
            _, problems = sc.render(catalog.collect()[0])
        finally:
            catalog.disabled_registry = original
        self.assertTrue(any("cannot import" in p for p in problems))

    def test_an_agent_with_a_writing_tool_is_a_problem(self):
        original = sc.agent_tools
        sc.agent_tools = lambda: dict(original(), **{"design-critic": "Read, Edit"})
        try:
            _, problems = sc.render(catalog.collect()[0])
        finally:
            sc.agent_tools = original
        self.assertTrue(any("read-only" in p for p in problems), problems)

    def _render_with_hook_event(self, event):
        original = sc.hooks
        sc.hooks = lambda: ([{"plugin": "p", "event": event, "matcher": "*",
                              "script": "x.py", "message": "m"}], [])
        try:
            return sc.render(catalog.collect()[0])[1]
        finally:
            sc.hooks = original

    def test_an_undescribed_hook_event_is_a_problem(self):
        # The hooks sentence describes PostToolUse and SessionStart only; any
        # other event (PreToolUse can block) must not publish under that prose.
        problems = self._render_with_hook_event("PreToolUse")
        self.assertTrue(any("PreToolUse" in p for p in problems), problems)

    def test_a_session_start_hook_is_described(self):
        problems = self._render_with_hook_event("SessionStart")
        self.assertFalse(any("hooks are registered" in p for p in problems), problems)

    def test_check_mode_fails_on_a_stale_file(self):
        original = sc.OUT
        sc.OUT = BIN / "_skills_catalog_stale_fixture.md"
        sc.OUT.write_text("stale\n")
        try:
            self.assertEqual(sc.main(["--check"]), 1)
        finally:
            sc.OUT.unlink(missing_ok=True)
            sc.OUT = original

    def test_check_mode_fails_when_the_file_is_missing(self):
        original = sc.OUT
        sc.OUT = BIN / "_skills_catalog_absent_fixture.md"
        try:
            self.assertEqual(sc.main(["--check"]), 1)
        finally:
            sc.OUT = original

    def test_check_mode_passes_on_the_committed_file(self):
        self.assertEqual(sc.main(["--check"]), 0)


class HtmlGuide(unittest.TestCase):
    """The field guide's numbers and DATA array, against the real tree."""

    @classmethod
    def setUpClass(cls):
        cls.data = catalog.collect()[0]
        cls.template = sc.OUT_HTML.read_text()
        cls.html, cls.problems = sc.render_html(cls.data, cls.template)
        cls.skills = sc.skill_rows(cls.data)

    def test_renders_without_problems(self):
        self.assertEqual(self.problems, [])

    def test_committed_guide_is_not_stale(self):
        self.assertEqual(self.template, self.html,
                         "docs/design-suite-guide.html is stale — regenerate with "
                         "`skills_catalog.py --html`")

    def test_data_row_count_equals_the_collected_command_count(self):
        body = self.html.split("/*gen:data*/")[1].split("/*gen:/data*/")[0]
        rows = [ln for ln in body.splitlines() if ln.startswith('["/')]
        self.assertEqual(len(rows), len(self.skills))

    def test_every_command_is_a_data_row_exactly_once(self):
        for s in self.skills:
            self.assertEqual(self.html.count(f'["/{s["name"]}",'), 1,
                             f"/{s['name']} is not in the DATA array exactly once")

    def test_output_is_byte_stable_across_runs(self):
        again, problems = sc.render_html(self.data, self.html)
        self.assertEqual(problems, [])
        self.assertEqual(again, self.html, "re-rendering churns — --check would flap")

    def test_derived_counts_appear_in_the_page(self):
        auto = [s for s in self.skills if s["invocation"] == "auto"]
        self.assertIn(f"<!--gen:n-commands-->{len(self.skills)}<!--gen:/n-commands-->",
                      self.html)
        self.assertIn(f"<!--gen:n-auto-->{len(auto)}<!--gen:/n-auto-->", self.html)

    def test_a_maturity_with_no_html_mapping_is_a_hard_error(self):
        with self.assertRaises(sc.MaturityMappingError):
            sc.html_maturity("brand-new-maturity")

    def test_an_unmappable_maturity_stops_the_render_rather_than_dropping_a_row(self):
        import copy as _copy
        broken = _copy.deepcopy(self.data)
        plugin = next(iter(broken))
        broken[plugin]["skills"][0]["maturity"] = "brand-new-maturity"
        with self.assertRaises(sc.MaturityMappingError):
            sc.render_html(broken, self.template)

    def test_a_marked_region_the_generator_does_not_fill_is_a_problem(self):
        out, problems = sc.substitute("<!--gen:mystery-->x<!--gen:/mystery-->", {})
        self.assertTrue(any("does not fill" in p for p in problems), problems)

    def test_a_missing_region_is_a_problem_not_a_silent_omission(self):
        _, problems = sc.render_html(self.data, "<html>no markers here</html>")
        self.assertTrue(any("no <!--gen:n-commands--> region" in p for p in problems),
                        problems)

    def test_every_role_is_counted_from_roles_json(self):
        n, problems = sc.roles_count()
        self.assertEqual(problems, [])
        self.assertIn(f"<!--gen:n-roles-->{n}<!--gen:/n-roles-->", self.html)

    def test_check_mode_fails_on_a_stale_html_file(self):
        original = sc.OUT_HTML
        sc.OUT_HTML = BIN / "_skills_catalog_stale_fixture.html"
        sc.OUT_HTML.write_text(self.template.replace(
            "<!--gen:n-commands-->", "<!--gen:n-commands-->9", 1))
        try:
            self.assertEqual(sc.main(["--html", "--check"]), 1)
        finally:
            sc.OUT_HTML.unlink(missing_ok=True)
            sc.OUT_HTML = original

    def test_check_mode_fails_when_the_guide_is_missing(self):
        original = sc.OUT_HTML
        sc.OUT_HTML = BIN / "_skills_catalog_absent_fixture.html"
        try:
            self.assertEqual(sc.main(["--html", "--check"]), 1)
        finally:
            sc.OUT_HTML = original

    def test_check_mode_passes_on_the_committed_guide(self):
        self.assertEqual(sc.main(["--html", "--check"]), 0)

    def test_a_disabled_audit_the_page_never_names_is_a_problem(self):
        stripped = self.template.replace("/audit-accessibility", "/audit-redacted")
        _, problems = sc.render_html(self.data, stripped)
        self.assertTrue(any("never names it" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
