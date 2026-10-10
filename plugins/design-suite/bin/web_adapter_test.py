#!/usr/bin/env python3
"""Planted-violation tests for drop-in stack coverage. Stdlib-only (unittest).

Every case plants a violation and asserts it is found, or plants a stack the
suite cannot audit and asserts the audit REFUSES (exit 2) — never that it prints
zero. A zero-finding fixture proves nothing on its own (CLAUDE.md, "Before
claiming a refactor was behaviour-preserving").

Covers:
  * the `web` adapter's true-positive capacity on .vue / .svelte / .css / .scss,
    and that it does not report a token DEFINITION or a token READ;
  * `audit_tokens.py` refusing a partial sweep (a Vue tree on `tsx`);
  * the adapter loader refusing an unfilled/unknown `adapters.lang` with exit 2;
  * the two widget-shape audits refusing a stack they cannot parse, instead of
    sweeping a hardcoded `lib/**/*.dart` and printing clean;
  * `reduced_motion_checks` refusing the scaffolded TODO placeholder.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/web_adapter_test.py"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))

from design_suite.adapters import dart, tsx, web  # noqa: E402
from design_suite.adapters.base import AdapterContext  # noqa: E402
from design_suite.engine.scan import scan_source  # noqa: E402

CTX = AdapterContext(repo=Path("."), profile={}, exceptions={})


def kinds(rel: str, source: str) -> list[str]:
    return sorted(f["kind"] for f in scan_source(rel, source, web.checks(CTX)))


class Stylesheets(unittest.TestCase):
    def test_planted_css_values_are_found(self):
        found = kinds("a.css", ".box { color: #ff0000; padding: 13px; "
                               "border-radius: 7px; transition: opacity 300ms ease; }\n")
        self.assertEqual(found, ["css_border_radius", "css_color", "css_duration", "css_spacing"])

    def test_last_declaration_without_semicolon(self):
        self.assertIn("css_spacing", kinds("a.css", ".box { margin: 13px }\n"))

    def test_scss_values_are_found(self):
        found = kinds("a.scss", ".card { background: #00ff00; margin-top: 1.5rem; "
                                "animation: spin 2s linear; }\n")
        self.assertEqual(found, ["css_color", "css_duration", "css_spacing"])

    def test_token_definitions_are_not_violations(self):
        src = (":root { --brand: #3366ff; --gap: 8px; }\n$gap: 8px;\n$ink: #111;\n"
               "@space: 4px;\n")
        self.assertEqual(kinds("t.scss", src), [])

    def test_token_reads_are_not_violations(self):
        src = ".box { color: var(--brand); padding: var(--gap); margin: $gap; margin: 0; }\n"
        self.assertEqual(kinds("a.scss", src), [])

    def test_comment_is_not_a_violation(self):
        self.assertEqual(kinds("a.css", "/* padding: 13px; color: #fff */\n"), [])

    def test_multiline_comment_continuation_is_not_a_violation(self):
        src = "/* keeps the nav's surface\n   in its row (#5399) */\n.a { color: #fff; }\n"
        self.assertEqual([f["line"] for f in scan_source("a.css", src, web.checks(CTX))], [3])

    def test_line_height_is_not_height(self):
        found = scan_source("a.css", ".a { line-height: 21px; }\n", web.checks(CTX))
        self.assertEqual([f["snippet"].split(":")[0] for f in found], ["line-height"])


class SingleFileComponents(unittest.TestCase):
    VUE = """<template>
  <div :style="{ color: '#ff0000', padding: '13px' }">hi</div>
</template>
<script setup>
const x = 1
</script>
<style scoped>
.box { color: #00ff00; margin: 13px; transition: opacity 300ms ease; }
</style>
"""

    def test_vue_style_block_and_binding_are_both_read(self):
        found = scan_source("App.vue", self.VUE, web.checks(CTX))
        by_line = sorted((f["line"], f["kind"]) for f in found)
        self.assertEqual(by_line, [(2, "color"), (2, "spacing"),
                                   (8, "css_color"), (8, "css_duration"), (8, "css_spacing")])

    def test_each_literal_is_reported_once(self):
        found = scan_source("App.vue", self.VUE, web.checks(CTX))
        keys = [(f["line"], f["snippet"]) for f in found]
        self.assertEqual(len(keys), len(set(keys)))

    def test_svelte_style_attribute(self):
        src = '<div style="color: #ff0000; padding: 13px">hi</div>\n'
        self.assertEqual(kinds("App.svelte", src), ["css_color", "css_spacing"])


class ScriptFilesUnchanged(unittest.TestCase):
    def test_tsx_checks_still_apply(self):
        src = "export const A = () => <div className=\"h-[17px]\" style={{ padding: 13 }} />;\n"
        self.assertEqual(kinds("A.tsx", src), ["spacing", "tw_spacing"])

    def test_css_checks_do_not_run_on_script(self):
        # A JS file is read by the tsx checks only; the stylesheet family must
        # not double-report the same literal.
        self.assertEqual(kinds("a.js", "const s = { color: '#ff0000' };\n"), ["color"])


class MeasuredFalsePositiveClasses(unittest.TestCase):
    """Each class removed after the 2026-10-08 real-project measurement.

    Every negative case is paired with a positive one in the same file, so a
    filter that over-reaches fails here rather than going quiet on a project.
    """

    def test_hairlines_are_not_spacing_but_real_steps_are(self):
        src = (".a { height: 1px; bottom: -1px; margin: 0 1px; }\n"
               ".b { margin: 13px; letter-spacing: 0.4px; }\n")
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual(sorted(f["line"] for f in found), [2, 2])

    def test_circle_radius_is_not_a_radius_token(self):
        src = ".a { border-radius: 50%; } .b { border-radius: 9999px; }\n.c { border-radius: 7px; }\n"
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual([(f["line"], f["kind"]) for f in found], [(2, "css_border_radius")])

    def test_var_fallback_is_a_token_read(self):
        src = ".a { width: var(--icon-size, 1rem); }\n.b { width: calc(var(--x) + 2rem); }\n"
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2])  # calc offset stays reported

    def test_1em_identity(self):
        src = ".i { width: 1em; height: 1em; font-size: 1em; }\n.j { margin-bottom: 1em; }\n"
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2])

    def test_multiline_custom_property_definition(self):
        src = (":root {\n  --shadow: 0 1px 2px rgba(0, 0, 0, 0.1),\n"
               "    0 4px 8px rgba(0, 0, 0, 0.2);\n}\n.a { color: #123456; }\n")
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [5])

    def test_svg_artwork_colour_is_not_ui_colour(self):
        src = ('export const I = () => <svg><path fill="#fff" /><stop stopColor="#636" />'
               '</svg>;\nel.setAttribute("fill", "#000");\n'
               'export const s = { color: "#ff0000" };\n')
        found = scan_source("I.tsx", src, web.checks(CTX))
        self.assertEqual([(f["line"], f["kind"]) for f in found], [(3, "color")])

    def test_js_custom_property_definition(self):
        src = ("const a = <svg style={{'--dark': '#000', '--light': '#fff'}} />;\n"
               "const b = <div style={{ color: '#ff0000' }} />;\n")
        found = scan_source("A.tsx", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2])

    def test_image_metadata_is_not_layout(self):
        src = ("export const og = { images: [{ url: u, width: 1200, height: 630 }] };\n"
               "const s = { padding: 13 };\n")
        found = scan_source("page.tsx", src, web.checks(CTX))
        self.assertEqual([(f["line"], f["kind"]) for f in found], [(2, "spacing")])

    def test_tailwind_keyword_percentage_and_hairline(self):
        src = 'const a = "rounded-[inherit] max-w-[85%] h-[1px] top-[1px] w-[240px] rounded-[7px]";\n'
        found = scan_source("a.tsx", src, web.checks(CTX))
        self.assertEqual(sorted(f["snippet"] for f in found), ["rounded-[7px]", "w-[240px]"])

    def test_test_and_story_files_are_not_product(self):
        test = ("import { render } from '@testing-library/react';\n"
                "it('x', () => { expect(f({ backgroundColor: '#fff', width: 200 })).toBe(1); });\n")
        story = "import type { Meta } from '@storybook/react';\nconst s = { padding: 13 };\n"
        self.assertEqual(kinds("a.test.tsx", test), [])
        self.assertEqual(kinds("a.stories.tsx", story), [])
        self.assertEqual(kinds("a.tsx", "const s = { padding: 13 };\n"), ["spacing"])

    # --- held-out measurement classes (issue #104, 2026-10-08) -------------
    # Each negative is paired with an adjacent real violation that must still
    # be reported, so an over-reaching filter fails here.

    def test_story_file_by_name_without_meta_import(self):
        story = "import { Button } from './Button';\nconst s = { padding: 13 };\n"
        self.assertEqual(kinds("Button.story.tsx", story), [])
        self.assertEqual(kinds("Button.stories.jsx", story), [])
        self.assertEqual(kinds("Button.tsx", story), ["spacing"])  # same text, product name
        self.assertEqual(kinds("storybook.tsx", story), ["spacing"])  # not the convention

    def test_story_file_by_csf_default_export(self):
        story = "export default { title: 'Button' };\nexport const A = () => <div style={{ padding: 13 }} />;\n"
        self.assertEqual(kinds("Demo.tsx", story), [])
        product = "export default { name: 'Button' };\nconst s = { padding: 13 };\n"
        self.assertEqual(kinds("Demo.tsx", product), ["spacing"])

    def test_dimension_records_are_data_not_layout(self):
        src = ("const ladder = [{ videoCodec: 'av01', width: 1280, height: 720, bitrate: 2 }];\n"
               "const opts = [{ label: '4:3', width: 24, height: 18 }, r = { x: 0, y: 0, width: 9, height: 9 }];\n"
               "size = $state<Dims>({ width: 1000, height: 1000 });\n"
               "const a = <div style={{ width: 240, height: 120 }} />;\n"
               "const b = { width: 240, padding: 13 };\n"
               "const cardStyle = { width: 240 };\n"
               "static defaultProps = { width: 239, height: 110 };\n"
               "const cols = [{ data: null, width: '40px' }];\n"
               "withDefaults(defineProps<P>(), { withOkButton: false, width: 400 });\n")
        found = scan_source("v.ts", src, web.checks(CTX))
        self.assertEqual(sorted({f["line"] for f in found}), [4, 5, 6, 7, 8, 9])

    def test_html_numeric_entity_is_not_a_colour(self):
        src = "const a = <span>&#8595;&#8203;&#x200B;</span>;\nconst b = { color: '#8595' };\n"
        found = scan_source("a.tsx", src, web.checks(CTX))
        self.assertEqual([(f["line"], f["kind"]) for f in found], [(2, "color")])
        sfc = "<template><b>&#8595;</b></template>\n<style>\n.a { color: #abc; }\n</style>\n"
        self.assertEqual([f["line"] for f in scan_source("A.svelte", sfc, web.checks(CTX))], [3])

    def test_palette_array_is_a_definition(self):
        src = ("export const red = ['#fff5f5', '#ffe3e3', '#ffc9c9', '#ffa8a8'];\n"
               "const two = ['#111111', foo];\nconst s = { color: '#ff0000' };\n")
        found = scan_source("colors.ts", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2, 3])

    def test_mask_alpha_stops_are_not_colours(self):
        src = (".a { mask-image: linear-gradient(90deg, rgba(0, 0, 0, 1) 0%, rgba(0, 0, 0, 0.3) 50%); }\n"
               ".b { background-image: linear-gradient(rgba(0, 0, 0, 0.3), #fff); }\n")
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual(sorted({f["line"] for f in found}), [2])

    def test_closed_var_does_not_hide_a_later_colour(self):
        src = ".a { background: repeating-linear-gradient(90deg,\n  var(--x) 36px,\n  #000 36px); }\n"
        self.assertEqual(kinds("a.css", src), ["css_color"])

    def test_custom_property_definition_in_embedded_style_and_tailwind(self):
        src = ("const s = <style>{`.m { --mail-border: #44403c; color: #123456; }`}</style>;\n"
               "const c = 'min-h-screen [--cal-brand:#111827] text-[#222222]';\n")
        found = scan_source("M.tsx", src, web.checks(CTX))
        self.assertEqual(sorted(f["snippet"] for f in found), ["#123456", "text-[#222222]"])

    def test_var_colour_fallback_is_a_token_read(self):
        src = ('const a = { background: "linear-gradient(var(--cal-bg, #ffffff), var(--x))" };\n'
               'const b = { background: "linear-gradient(var(--cal-bg), #ffffff)" };\n')
        found = scan_source("p.tsx", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2])

    def test_zero_duration_is_a_reset(self):
        src = (".a { transition-duration: 0ms; }\n.b { transition-duration: 150ms; }\n"
               ".c { transition: opacity 0ms, transform 200ms; }\n")
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2, 3])

    # --- round-4 classes (issue #104, fresh held-out 2026-10-09) -----------

    def test_theme_palette_definition_is_a_token_definition(self):
        src = ("export const t = createTheme({\n"
               "  palette: { primary: { main: '#00a4dc' }, action: { hover: '#12122f' } },\n"
               "  components: { MuiButton: { styleOverrides: { root: { color: '#ff0000' } } } },\n"
               "});\nconst s = { color: '#00ff00' };\n")
        found = scan_source("theme.ts", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [3, 5])

    def test_image_request_and_graph_node_sizes_are_data(self):
        src = ("icon = api.getScaledImageUrl(item.Id, {\n  width: 80,\n  tag: t,\n  type: 'Primary'\n});\n"
               "nodes.push({ id: n, width: 220, height: 100, position: { x: 0, y: 0 }, data: o });\n"
               "g.setNode(n, { width: 220, height: 100 });\n"
               "openDialog(id, { width: 80, tag: t });\n"
               "boxes.push({ width: 220 });\n")
        found = scan_source("n.js", src, web.checks(CTX))
        self.assertEqual(sorted({f["line"] for f in found}), [8, 9])

    def test_custom_property_definition_in_styled_template(self):
        src = ("const A = styled.div`\n  --ai-chat-content-max-width: 768px;\n"
               "  max-width: 768px;\n  scroll-margin-top: 8px;\n`;\n")
        want = [(3, "css_spacing"), (4, "css_spacing")]
        found = scan_source("A.tsx", src, web.checks(CTX))
        self.assertEqual([(f["line"], f["kind"]) for f in found], want)
        found = scan_source("A.tsx", src, tsx.checks(CTX))  # tsx shares the pattern
        self.assertEqual([(f["line"], f["kind"]) for f in found], want)

    def test_unit_multiplier_is_not_a_duration(self):
        src = ("const A = styled.div`\n  transition: all calc(${t.fast} * 1s) ease;\n"
               "  transition: all calc(${t.fast} * 1s) ease, opacity 300ms;\n"
               "  animation-duration: 1s;\n`;\n")
        found = scan_source("A.tsx", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [3, 4])

    def test_canvas_paint_is_artwork(self):
        src = ("ctx.fillStyle = '#ffffff';\nctx.strokeStyle = i === 0 ? '#9ca3af' : 'rgba(17, 24, 39, 0.08)';\n"
               "grad.addColorStop(0, '#123456');\nel.style.color = '#ff0000';\n"
               "if (ctx.fillStyle == '#eeeeee') {}\n")
        found = scan_source("draw.ts", src, web.checks(CTX))
        self.assertEqual(sorted({f["line"] for f in found}), [4, 5])

    def test_form_control_value_is_a_setting_default(self):
        src = ("input.value = settings.textColor || '#ffffff';\n"
               "el.style.color = settings.textColor || '#ffffff';\n")
        found = scan_source("s.js", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2])

    def test_minified_bundle_is_not_product(self):
        mini = ".a{padding:13px;color:#ff0000}" * 400
        self.assertEqual(kinds("vendor.css", mini), [])

    def test_region_cache_does_not_leak_between_files(self):
        # Regression: SFC <style> spans were cached by id(source), and CPython
        # reuses a freed string's id for the next same-sized string — so a file
        # inherited the previous file's spans and lost its findings (measured:
        # 81 of 731 findings silently dropped on one real Vue project). Two
        # same-length files with their <style> blocks in different places.
        style = "<style>\n.a { margin: 13px; }\n</style>\n"
        filler = "<template><p>" + "x" * 200 + "</p></template>\n"
        early, late = style + filler, filler + style
        checks = web.checks(CTX)
        for i in range(50):
            src = "".join([early, late][i % 2])  # a fresh string object each time
            found = scan_source(f"C{i}.vue", src, checks)
            del src
            self.assertEqual([f["kind"] for f in found], ["css_spacing"], i)


def project(root: Path, files: dict, profile: dict) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    (root / ".design-suite").mkdir(exist_ok=True)
    (root / ".design-suite" / "profile.json").write_text(json.dumps(profile))
    return root


def run(script: str, root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(PLUGIN / "bin" / script)], cwd=root,
                          env=env, capture_output=True, text=True, timeout=60)


VUE_TREE = {"src/main.js": "import App from './App.vue'\n",
            "src/App.vue": SingleFileComponents.VUE}


def profile(lang, root="src"):
    return {"profileVersion": 1, "project": {"name": "fixture"},
            "adapters": {"lang": lang}, "source": {"root": root},
            "pipelines": {"tokens": ".design-suite/out"}}



class Round5FileLevel(unittest.TestCase):
    """Round-4 classes, fixed at file level; every skip is visible on stderr."""
    BANNER = ("/*!\n * Bootstrap v4.3.1 (https://getbootstrap.com/)\n"
              " * Copyright 2011-2019 The Bootstrap Authors\n"
              " * Licensed under MIT\n */\n")
    OWN = "/**\n * Copyright 2024 Example Labs. Licensed under AGPL-3.0.\n */\n"
    BAD = ".box { color: #ff0000; padding: 13px; }\n"

    def test_vendored_banner_is_skipped(self):
        self.assertEqual(web.non_product_file("ui/Tabler.css", self.BANNER + self.BAD),
                         "vendored (licence+version banner)")

    def test_own_licence_header_without_version_is_scanned(self):
        self.assertIsNone(web.non_product_file("ui/app.css", self.OWN + self.BAD))

    def test_banner_without_licence_is_scanned(self):
        self.assertIsNone(web.non_product_file("a.css", "/*! build 1.2.3 */\n" + self.BAD))

    def test_mock_and_fixture_paths(self):
        for rel in ("a/b.mock.ts", "a/__mocks__/x.ts", "a/fixtures/x.ts",
                    "a/__fixtures__/x.tsx", "a/x.stories.tsx"):
            self.assertIsNotNone(web.non_product_file(rel, ""), rel)
        for rel in ("a/mockup.tsx", "a/fixture.ts", "a/Mock.vue"):
            self.assertIsNone(web.non_product_file(rel, ""), rel)

    def _tree(self, files, exceptions=None):
        import contextlib
        import io
        from design_suite.engine import scan
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, src in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(src)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                found = scan.scan_tree(root, root, web.checks(CTX), globs=web.FILE_GLOBS,
                                       file_filter=web.non_product_file,
                                       include_files=scan.scan_skip_file_includes(exceptions))
            return sorted({f["file"] for f in found}), err.getvalue()

    def test_skip_is_visible_and_adjacent_real_file_still_reports(self):
        files, err = self._tree({"Tabler.css": self.BANNER + self.BAD, "app.css": self.BAD,
                                 "api.mock.ts": "const s = { color: '#ff0000' };\n",
                                 "real.ts": "const s = { color: '#ff0000' };\n"})
        self.assertEqual(files, ["app.css", "real.ts"])
        self.assertIn("SKIPPED 1 vendored", err)
        self.assertIn("Tabler.css", err)
        self.assertIn("SKIPPED 1 mock/fixture", err)
        self.assertIn("api.mock.ts", err)

    def test_include_override_rescans(self):
        files, _ = self._tree({"Tabler.css": self.BANNER + self.BAD},
                              {"scanSkipFiles": {"include": ["Tabler.css"]}})
        self.assertEqual(files, ["Tabler.css"])


class Round5MatchLevel(unittest.TestCase):
    def test_name_to_colour_map_is_data(self):
        src = ("const LANG = {\n  lua: '#000080',\n  'c++': '#f34b7d',\n  'jupyter notebook': '#da5b0b',\n"
               "  'objective-c': '#438eff',\n  \"ren'py\": '#ff7f7f',\n};\n")
        self.assertEqual(kinds("a.ts", src), [])

    def test_style_object_of_colours_still_reports(self):
        src = "const s = { color: '#ff0000', background: '#00ff00', borderColor: '#0000ff' };\n"
        self.assertEqual(kinds("a.ts", src), ["color", "color", "color"])

    def test_small_map_still_reports(self):
        self.assertEqual(kinds("a.ts", "const m = { ok: '#00ff00', bad: '#ff0000' };\n"),
                         ["color", "color"])

    def test_offscreen_hide_hack(self):
        src = ".hide { position: absolute; left: -999999px; }\n.real { left: 13px; }\n"
        found = scan_source("a.css", src, web.checks(CTX))
        self.assertEqual([f["line"] for f in found], [2])

    def test_offscreen_hide_hack_inline_style(self):
        src = ('<template><textarea style="position: fixed; left: -999999px"></textarea>\n'
               '<div style="left: 13px"></div></template>\n')
        self.assertEqual([f["line"] for f in scan_source("A.vue", src, web.checks(CTX))], [2])

    def test_banner_after_header_comment(self):
        src = '@charset "UTF-8";\n/**\nDashboard UI\n */\n\n' + Round5FileLevel.BANNER
        self.assertIsNotNone(web.non_product_file("Tabler.css", src))

    def test_large_negative_without_absolute_still_reports(self):
        self.assertEqual(kinds("a.css", ".x { margin-left: -13px; left: -99999px; }\n"),
                         ["css_spacing", "css_spacing"])

    def test_colour_lookup_is_not_paint(self):
        src = "const i = colors.indexOf('#E24D42');\nconst s = { color: '#ff0000' };\n"
        self.assertEqual([f["line"] for f in scan_source("a.ts", src, web.checks(CTX))], [2])


class AuditTokensEndToEnd(unittest.TestCase):
    def test_vue_tree_on_web_finds_the_planted_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(Path(tmp), VUE_TREE, profile("web"))
            proc = run("audit_tokens.py", root)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            out = json.loads((root / ".design-suite/tokens-findings.json").read_text())
            self.assertEqual(len(out), 5)

    def test_vue_tree_on_tsx_refuses_instead_of_reporting_clean(self):
        # The measured failure: tsx swept main.js, found nothing, exited 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = project(Path(tmp), VUE_TREE, profile("tsx"))
            proc = run("audit_tokens.py", root)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("NOT SCANNED", proc.stderr)
            self.assertIn(".vue", proc.stderr)

    def test_acknowledged_unscanned_suffix_is_a_recorded_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(Path(tmp), VUE_TREE, profile("tsx"))
            (root / ".design-suite/exceptions.json").write_text(
                json.dumps({"acknowledgedUnscanned": [".vue"]}))
            self.assertEqual(run("audit_tokens.py", root).returncode, 0)


class LoaderRefusals(unittest.TestCase):
    def test_unfilled_lang_placeholder_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(Path(tmp), {"Sources/App/V.swift": "let x = 1\n"},
                           profile("TODO: which language adapter audits this project's source",
                                   root="Sources"))
            proc = run("audit_tokens.py", root)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("INERT", proc.stderr)

    def test_unknown_lang_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = project(Path(tmp), {"src/a.cob": "x\n"}, profile("cobol"))
            proc = run("audit_tokens.py", root)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("unknown language adapter", proc.stderr)


class WidgetShapeAuditsRefuse(unittest.TestCase):
    ARCH = {"promotionCandidates": {"plumbingParams": ["key"], "noiseParamSets": [],
                                    "baseline": ".design-suite/b.json"},
            "reinventedComponents": {"exportPrefix": "Ds", "allowedCollisions": []}}

    def _root(self, tmp, files, lang, src_root):
        p = profile(lang, src_root)
        p["audits"] = {"archRulesFile": ".design-suite/arch-rules.json"}
        root = project(Path(tmp), files, p)
        (root / ".design-suite/arch-rules.json").write_text(json.dumps(self.ARCH))
        return root

    def test_non_dart_stack_is_refused_not_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, {"src/A.tsx": "export const A = 1;\n"}, "web", "src")
            proc = run("audit_promotion_candidates.py", root)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("WIDGET_SHAPE_GLOB", proc.stderr)

    def test_dart_tree_outside_lib_is_actually_scanned(self):
        # Used to sweep a literal `lib/`; a project rooted at `app/` read nothing.
        widget = ("class _{n} extends StatelessWidget {{\n"
                  "  const _{n}({{required this.title, required this.onTap}});\n"
                  "  final String title;\n  final VoidCallback onTap;\n}}\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp, {"app/a.dart": widget.format(n="CardA"),
                                    "app/b.dart": widget.format(n="CardB")}, "dart", "app")
            proc = run("audit_promotion_candidates.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)


class ReducedMotionPlaceholder(unittest.TestCase):
    def test_scaffolded_todo_is_a_refusal(self):
        ctx = AdapterContext(repo=Path("."), profile={}, exceptions={}, audit_config={
            "token_categories": {"motion": {"animated_widgets": [
                "TODO: every widget/class name audit_reduced_motion.py should treat"]}}})
        checks = dart.reduced_motion_checks(ctx)
        self.assertEqual(len(checks), 0)
        self.assertTrue(checks.omitted)
        self.assertIn("TODO placeholder", checks.omitted[0])


if __name__ == "__main__":
    unittest.main()
