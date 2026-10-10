#!/usr/bin/env python3
"""Focus-order, semantics and error-handling capabilities on the `tsx` and `web`
adapters (design_suite/adapters/_jsx.py), plus the refusals that stay.

Planted violations must be found, clean controls must run with files scanned
and report nothing, and a tree the rules cannot read must refuse (exit 2) —
never pass. Stdlib unittest, no pytest.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/web_audit_capabilities_test.py"
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

from design_suite.adapters import _jsx  # noqa: E402


def kinds(found):
    return [f["kind"] for f in found]


class TagScanner(unittest.TestCase):
    def test_arrow_in_attribute_does_not_end_the_tag(self):
        t = _jsx.tags('<div onClick={() => a > b} role="x">')
        self.assertEqual(t[0].attrs["role"], "x")

    def test_generics_and_comparisons_are_not_tags(self):
        self.assertEqual(_jsx.tags("const a = useState<boolean>(x); if (a <b) {}"), [])

    def test_html_in_a_string_is_not_markup(self):
        self.assertEqual(_jsx.tags("const h = '<p onclick=\"x\">y</p>';"), [])

    def test_comments_are_blanked(self):
        code = _jsx.blank_comments("// <div onClick={x}>\n/* <span onClick={y}> */ ok")
        self.assertEqual(_jsx.tags(code), [])
        self.assertEqual(code.count("\n"), 1)


class FocusFindings(unittest.TestCase):
    def test_planted_autofocus_and_positive_tabindex(self):
        src = "export const A = () => <input autoFocus tabIndex={2} />;\n"
        self.assertEqual(sorted(kinds(_jsx.focus_findings("A.tsx", src))),
                         ["autofocus_override", "positive_tabindex"])

    def test_vue_and_svelte_spellings(self):
        self.assertEqual(kinds(_jsx.focus_findings(
            "C.vue", '<template><li :tabindex="3">x</li></template>')), ["positive_tabindex"])
        self.assertEqual(kinds(_jsx.focus_findings(
            "C.svelte", "<input autofocus bind:value={v}>")), ["autofocus_override"])

    def test_clean_controls(self):
        for src in ("<input autoFocus={false} tabIndex={0} />",
                    "<input tabIndex={-1} />",
                    "<Input autoFocus={autoFocus} />",            # forwarded prop
                    "type P = { autoFocus?: boolean }",           # not a tag
                    "<input tabIndex={order} />"):                # expression: not judged
            self.assertEqual(_jsx.focus_findings("A.tsx", src), [], src)

    def test_plain_ts_and_tests_are_not_read(self):
        self.assertEqual(_jsx.focus_findings("a.ts", "<input autoFocus />"), [])
        self.assertEqual(_jsx.focus_findings("a.test.tsx", "<input autoFocus />"), [])


class SemanticsFindings(unittest.TestCase):
    def test_planted_static_click_handlers(self):
        for rel, src in (("A.tsx", "<div onClick={go}>x</div>"),
                         ("C.vue", '<template><span @click="go">x</span></template>'),
                         ("C.svelte", "<li on:click={go}>x</li>")):
            self.assertEqual(kinds(_jsx.semantics_findings_for(rel, src)),
                             ["static_element_click_handler"], rel)

    def test_clean_controls(self):
        for src in ('<div role="button" tabIndex={0} onClick={go}>x</div>',
                    "<button onClick={go}>x</button>",
                    "<Card onClick={go} />",                          # component: unseen
                    "<div {...rest} onClick={go} />",                 # spread may carry role
                    '<div aria-hidden="true" onClick={go} />',
                    "<div onClick={(e) => e.stopPropagation()}>x</div>",
                    "<div onClick={onClose} className='backdrop' />",
                    "<div onClick={focus}><input /></div>"):          # click-to-focus
            self.assertEqual(_jsx.semantics_findings_for("A.tsx", src), [], src)
        self.assertEqual(_jsx.semantics_findings_for(
            "C.vue", '<template><div @click.stop>x</div></template>'), [])


def project(root: Path, files: dict, lang: str, extra: dict | None = None) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    prof = {"profileVersion": 1, "project": {"name": "fixture"},
            "adapters": {"lang": lang}, "source": {"root": "src"},
            "pipelines": {"tokens": ".design-suite/out"}}
    prof.update(extra or {})
    (root / ".design-suite").mkdir(exist_ok=True)
    (root / ".design-suite" / "profile.json").write_text(json.dumps(prof))
    return root


def run(script: str, root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(PLUGIN / "bin" / script)], cwd=root,
                          env=env, capture_output=True, text=True, timeout=120)


PLANTED = {"src/A.tsx": "export const A = () => <><div onClick={go}>x</div><input autoFocus /></>;\n",
           "src/B.vue": '<template><span @click="go" :tabindex="2">x</span></template>\n'}
CLEAN = {"src/A.tsx": "export const A = () => <button onClick={go}>x</button>;\n",
         "src/B.vue": '<template><button @click="go">x</button></template>\n'}
NO_MARKUP = {"src/a.ts": "export const x = 1;\n", "src/s.css": ".a { color: red; }\n"}


class EndToEnd(unittest.TestCase):
    def check(self, script, files, lang, rc, needle=None):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(script, project(Path(tmp), files, lang))
            self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            if needle:
                self.assertIn(needle, r.stdout + r.stderr)
            return r

    def test_semantics(self):
        for lang in ("tsx", "web"):
            files = PLANTED if lang == "web" else {"src/A.tsx": PLANTED["src/A.tsx"]}
            clean = CLEAN if lang == "web" else {"src/A.tsx": CLEAN["src/A.tsx"]}
            with self.subTest(lang=lang):
                self.check("audit_semantics.py", files, lang, 1, "should_fix")
                self.check("audit_semantics.py", clean, lang, 0, "0 semantics findings")
                self.check("audit_semantics.py", NO_MARKUP, lang, 2, "refusal")

    def test_focus_order(self):
        # Focus-order findings are FYI by contract: exit 0 with findings counted.
        self.check("audit_focus_order.py", PLANTED, "web", 0, "Found 2 focus-order findings")
        self.check("audit_focus_order.py", CLEAN, "web", 0, "Found 0 focus-order findings")
        self.check("audit_focus_order.py", NO_MARKUP, "web", 2, "refusal")
        self.check("audit_focus_order.py", {"src/A.tsx": PLANTED["src/A.tsx"]}, "tsx", 0,
                   "Found 1 focus-order findings")

    def test_error_handling_on_web(self):
        rules = {"errorHandling": {
            "exception_type": "AppError", "guard_call": "guard",
            "client_call_pattern": r"\bfetch\(", "error_state_widget": "ErrorState",
            "error_message_field": "errorMessage",
            "state_class_pattern": r"^class\s+(\w+Failed)\b",
            "state_file_suffix": ".state.ts", "pages_marker": "/pages/"}}
        cases = (({"src/C.vue": "<script>try { a() } catch (e) { msg = `${e}` }</script>\n"}, 1),
                 ({"src/C.vue": "<script>try { a() } catch (e) { msg = 'failed' }</script>\n"}, 0),
                 ({"src/s.css": ".a { color: red; }\n"}, 2))
        for files, rc in cases:
            with tempfile.TemporaryDirectory() as tmp:
                root = project(Path(tmp), files, "web",
                               {"source": {"root": "src", "fileGlob": "**/*"},
                                "audits": {"archRulesFile": ".design-suite/arch.json"}})
                (root / ".design-suite" / "arch.json").write_text(json.dumps(rules))
                r = run("audit_error_handling.py", root)
                self.assertEqual(r.returncode, rc, f"{files}\n{r.stdout}{r.stderr}")
                self.assertNotIn("Traceback", r.stderr)

    def test_component_shape_audits_still_refuse_on_web_and_tsx(self):
        # Measured >20% wrong (see the note at the end of adapters/tsx.py).
        arch = {"promotionCandidates": {"plumbingParams": ["key"], "noiseParamSets": [],
                                        "baseline": ".design-suite/b.json"},
                "reinventedComponents": {}}
        for lang in ("tsx", "web"):
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                root = project(Path(tmp), PLANTED, lang,
                               {"audits": {"archRulesFile": ".design-suite/arch.json"}})
                (root / ".design-suite" / "arch.json").write_text(json.dumps(arch))
                r = run("audit_promotion_candidates.py", root)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("WIDGET_SHAPE_GLOB", r.stderr)


if __name__ == "__main__":
    unittest.main()
