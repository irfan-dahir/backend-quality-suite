#!/usr/bin/env python3
"""audit_error_handling: the four `find_*` checks over php fixtures, in memory.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_handling_test.py"

Re-authored from the purged design-suite version of this file — same four
checks, same `run_audit(files, vocab, syntax)` driver, dart fixtures replaced
by `adapters/php.ERROR_HANDLING` and a php-shaped vocabulary. Everything here
was measured against that capability before being asserted:

  * to_string_mangling — a caught `AppError` cast or interpolated within the
    4-line window is a finding at the stringified line; `$e->getMessage()`
    is not (that is the sanctioned narrowing); a window carrying the
    `instanceof` type test, comment lines, and `catch (… $_)` are skipped;
  * client_call_bypasses_guard — `Http::get(` outside `guardApiCall(...)` is
    critical at the call's line; inside the span it is not; and a paren
    inside a string literal does not unbalance the span match
    (`matching_paren` quote-skip);
  * dead_failure_state — a `class …Failed` declared in a `*_state.php` file
    with no `instanceof` for it in any OTHER file is a finding; consumed,
    known_dead, and wrong-suffix cases are not;
  * inline_error_without_shared_state — a `/pages/` file reading
    `->errorMessage` without `ErrorState` is a finding. The member match
    takes `->` as well as `.`: measured before this test existed, the
    dot-only pattern could never fire on the shipped adapter, i.e. the
    check read "clean" on every real PHP project;
  * run_audit aggregates all four; `_vocabulary` refuses on missing keys and
    on TODO placeholders (both exit 2, INERT); `error_handling_syntax`
    refuses an adapter without the capability and returns php's.

No subprocess here — the CLI-level refusal rows (missing section, missing
fileGlob, unknown lang, scaffold) live in `structural_refusals_test.py`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit_error_handling as aeh  # noqa: E402
from backend_suite.adapters import php  # noqa: E402

SYNTAX = php.ERROR_HANDLING

# The vocabulary under test: this project's own names for its error
# machinery, phrased the way a PHP service words them. A project with
# different names gets the same assertions for free by passing its own
# Vocabulary — the checks are name-driven, never name-hardcoded.
VOCAB_FIELDS = {
    "exception_type": "AppError",
    "guard_call": "guardApiCall",
    "client_call_pattern": r"\bHttp::(?:get|post)\s*\(",
    "error_state_widget": "ErrorState",
    "error_message_field": "errorMessage",
    "state_class_pattern": r"^class (\w+Failed)\b",
    "state_file_suffix": "_state.php",
    "pages_marker": "/pages/",
}
VOCAB = aeh.Vocabulary(**VOCAB_FIELDS)

CATCH_AND_FLAG = (
    "<?php\n"
    "try {\n"
    "    load();\n"
    "} catch (AppError $e) {\n"
    "    return \"failed: {$e}\";\n"
    "}\n"
)


class ToStringMangling(unittest.TestCase):
    def test_interpolated_catch_flags_at_the_stringified_line(self):
        findings = aeh.find_to_string_mangling(
            "app/Api.php", CATCH_AND_FLAG.splitlines(), VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["check"], "to_string_mangling")
        self.assertEqual(f["severity"], "should_fix")
        self.assertEqual(f["line"], 5)  # the `"failed: {$e}"` line
        # The advice is adapter-neutral: it must not name one language's
        # spellings (`.toString()`, the Dart `x is AppError ? …` guard).
        self.assertNotIn("toString()", f["detail"])
        self.assertNotIn("is AppError", f["detail"])
        self.assertIn("narrowing it to its message", f["detail"])

    def test_string_cast_flags_too(self):
        text = (
            "<?php\n"
            "try {\n"
            "    load();\n"
            "} catch (AppError $e) {\n"
            "    $msg = (string) $e;\n"
            "}\n"
        )
        findings = aeh.find_to_string_mangling(
            "app/Api.php", text.splitlines(), VOCAB, SYNTAX)
        self.assertEqual([f["line"] for f in findings], [5])

    def test_message_narrowing_is_the_sanctioned_shape_and_stays_quiet(self):
        text = (
            "<?php\n"
            "} catch (AppError $e) {\n"
            "    log($e->getMessage());\n"
            "}\n"
        )
        findings = aeh.find_to_string_mangling(
            "app/Api.php", text.splitlines(), VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_type_test_in_the_window_skips_the_whole_site(self):
        # The sanctioned `instanceof` narrowing: even a stringify three lines
        # below it is inside the guard's window and is not the anti-pattern.
        text = (
            "<?php\n"
            "} catch (AppError $e) {\n"
            "    if ($e instanceof AppError) {\n"
            "        return \"failed: {$e}\";\n"
            "    }\n"
            "}\n"
        )
        findings = aeh.find_to_string_mangling(
            "app/Api.php", text.splitlines(), VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_comment_lines_are_not_the_antipattern(self):
        text = (
            "<?php\n"
            "    // catch (AppError $e)\n"
            "    // return \"failed: {$e}\";\n"
        )
        findings = aeh.find_to_string_mangling(
            "app/Api.php", text.splitlines(), VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_unnamed_catch_var_is_skipped(self):
        text = (
            "<?php\n"
            "} catch (AppError $_) {\n"
            "    return \"failed: {$_}\";\n"
            "}\n"
        )
        findings = aeh.find_to_string_mangling(
            "app/Api.php", text.splitlines(), VOCAB, SYNTAX)
        self.assertEqual(findings, [])


class ClientCallBypass(unittest.TestCase):
    def test_unguarded_call_is_critical_at_its_line(self):
        text = "<?php\nreturn Http::get('/orders');\n"
        findings = aeh.find_client_bypass("app/Api.php", text, VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["check"], "client_call_bypasses_guard")
        self.assertEqual(f["severity"], "critical")
        self.assertEqual(f["line"], 2)
        self.assertIn("guardApiCall", f["detail"])

    def test_call_inside_the_guard_span_stays_quiet(self):
        text = "return guardApiCall(fn () => Http::get('/orders'));\n"
        findings = aeh.find_client_bypass("app/Api.php", text, VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_a_paren_inside_a_string_does_not_unbalance_the_span(self):
        # `matching_paren` skips quoted contents; without that the odd `(`
        # inside 'auth (' would swallow the close and report the guarded
        # call as a bypass.
        text = "return guardApiCall('auth (', fn () => Http::get('/x'));\n"
        findings = aeh.find_client_bypass("app/Api.php", text, VOCAB, SYNTAX)
        self.assertEqual(findings, [])


class DeadFailureStates(unittest.TestCase):
    FILES = {
        "pages/orders_state.php":
            "<?php\n"
            "class OrderLoadFailed {}\n"
            "class OrderSaveFailed {}\n",
        "pages/list.php":
            "<?php\n"
            "if ($e instanceof OrderLoadFailed) {}\n",
    }

    def test_unconsumed_state_class_flags_at_its_line(self):
        findings = aeh.find_dead_failure_states(self.FILES, VOCAB, {}, SYNTAX)
        self.assertEqual([(f["check"], f["line"]) for f in findings],
                         [("dead_failure_state", 3)])
        self.assertIn("OrderSaveFailed", findings[0]["detail"])
        self.assertNotIn("is OrderSave", findings[0]["detail"])

    def test_a_state_type_tested_in_another_file_is_consumed(self):
        findings = aeh.find_dead_failure_states(self.FILES, VOCAB, {}, SYNTAX)
        self.assertNotIn("OrderLoadFailed",
                         [f["detail"] for f in findings])

    def test_known_dead_suppresses(self):
        findings = aeh.find_dead_failure_states(
            self.FILES, VOCAB, {"OrderSaveFailed": True}, SYNTAX)
        self.assertEqual(findings, [])

    def test_only_state_files_are_scanned(self):
        files = {"models/Foo.php": "<?php\nclass FooFailed {}\n"}
        findings = aeh.find_dead_failure_states(files, VOCAB, {}, SYNTAX)
        self.assertEqual(findings, [])


class InlineErrorWithoutSharedState(unittest.TestCase):
    def test_php_member_access_flags_at_the_read_line(self):
        files = {"app/pages/OrdersPage.php":
                 "<?php\n"
                 "class OrdersPage {\n"
                 "    public function x($state) { return $state->errorMessage; }\n"
                 "}\n"}
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["check"], "inline_error_without_shared_state")
        self.assertEqual(f["severity"], "should_fix")
        self.assertEqual(f["line"], 3)

    def test_dot_member_access_still_flags(self):
        files = {"app/pages/OrdersPage.php":
                 "<?php\n$x = $state.errorMessage;\n"}
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(len(findings), 1)

    def test_rendering_the_shared_widget_is_quiet(self):
        files = {"app/pages/OrdersPage.php":
                 "<?php\n"
                 "return new ErrorState($state->errorMessage);\n"}
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(findings, [])

    def test_files_outside_the_pages_marker_are_quiet(self):
        files = {"app/Orders.php": "<?php\n$x = $state->errorMessage;\n"}
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(findings, [])


class RunAuditAggregates(unittest.TestCase):
    def test_every_check_fires_over_one_file_set(self):
        files = {
            "app/Api.php":
                "<?php\n"
                "} catch (AppError $e) {\n"
                "    return \"failed: {$e}\";\n"
                "}\n"
                "return Http::get('/orders');\n",
            "pages/orders_state.php": "<?php\nclass OrderSaveFailed {}\n",
            "app/pages/OrdersPage.php":
                "<?php\n$x = $state->errorMessage;\n",
        }
        findings = aeh.run_audit(files, VOCAB, None, syntax=SYNTAX)
        self.assertEqual(
            sorted({f["check"] for f in findings}),
            ["client_call_bypasses_guard", "dead_failure_state",
             "inline_error_without_shared_state", "to_string_mangling"])
        self.assertEqual(len(findings), 4)


class VocabularyRefusals(unittest.TestCase):
    def test_missing_keys_refuse_exit_2(self):
        with self.assertRaises(SystemExit) as ctx:
            aeh._vocabulary({"exception_type": "AppError"})
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("errorHandling is missing", str(ctx.exception))
        self.assertIn("guard_call", str(ctx.exception))

    def test_todo_placeholders_refuse_exit_2(self):
        rules = dict(VOCAB_FIELDS)
        rules["guard_call"] = "TODO: the wrapper every call sits inside"
        with self.assertRaises(SystemExit) as ctx:
            aeh._vocabulary(rules)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("TODO placeholders", str(ctx.exception))
        self.assertIn("guard_call", str(ctx.exception))

    def test_a_complete_vocabulary_builds(self):
        vocab = aeh._vocabulary(dict(VOCAB_FIELDS))
        self.assertEqual(vocab.exception_type, "AppError")
        self.assertEqual(vocab.state_file_suffix, "_state.php")


class SyntaxCapability(unittest.TestCase):
    def test_php_exposes_error_handling(self):
        self.assertIs(aeh.error_handling_syntax(php), php.ERROR_HANDLING)

    def test_an_adapter_without_the_capability_refuses(self):
        with self.assertRaises(SystemExit) as ctx:
            aeh.error_handling_syntax(object())
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("ERROR_HANDLING capability", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
