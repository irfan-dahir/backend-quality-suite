#!/usr/bin/env python3
"""Tests for audit_error_handling.py. Stdlib-only (unittest), matching this
project's Python-tooling convention (docs/INSTRUCTIONS.md §13) — no pytest.
Fixtures are synthetic in-memory/temp-dir snippets, not the live lib/ tree,
so these stay stable as Phase 2/2b of the error-handling plan fixes the real
findings out from under them.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_handling_test.py"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit_error_handling as aeh  # noqa: E402
from design_suite.adapters import dart as _dart  # noqa: E402

SYNTAX = _dart.ERROR_HANDLING

# The vocabulary under test. These are the mobile app's own names — the ones the
# origin script had hardcoded — used here as a fixture. A second project with
# different names gets the same 22 assertions for free by passing its own.
VOCAB = aeh.Vocabulary(
    exception_type="AppException",
    guard_call="guardApiCall",
    client_call_pattern=(
        r"\b(?:ApiClient\.instance\.dio|Dio\(\))\."
        r"(?:get|post|put|patch|delete)\s*\("),
    error_state_widget="AppErrorState",
    error_message_field="errorMessage",
    state_class_pattern=(
        r"^(?:final\s+|sealed\s+|base\s+|abstract\s+)*class\s+"
        r"(\w+(?:Failed|Failure|Error))\b"),
    state_file_suffix="_state.dart",
    pages_marker="/presentation/pages/",
)
KNOWN_DEAD = {"TourNotesHubLoadFailed": "documented as intentionally unwired"}



class ToStringManglingTest(unittest.TestCase):
    def test_flags_catch_block_toString(self):
        lines = [
            "  Future<void> _onLoad(Event e, Emitter emit) async {",
            "    try {",
            "      final x = await repo.fetch();",
            "    } catch (e) {",
            "      emit(FooLoadFailed(e.toString()));",
            "    }",
            "  }",
        ]
        findings = aeh.find_to_string_mangling("lib/x_bloc.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "to_string_mangling")
        self.assertEqual(findings[0]["severity"], "should_fix")
        self.assertEqual(findings[0]["line"], 5)

    def test_flags_on_error_callback(self):
        lines = [
            "    _stream.listen(",
            "      onData: (v) => emit(Loaded(v)),",
            "      onError: (e) => emit(FooLoadFailed(e.toString())),",
            "    );",
        ]
        findings = aeh.find_to_string_mangling("lib/x_bloc.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)

    def test_flags_string_interpolation(self):
        lines = [
            "    } catch (e) {",
            "      emit(FooLoadFailed('Error: $e'));",
            "    }",
        ]
        findings = aeh.find_to_string_mangling("lib/x_bloc.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)

    def test_does_not_flag_interpolated_message_property(self):
        lines = [
            "    } on DioException catch (e) {",
            "      throw NetworkException('Token refresh failed: ${e.message}');",
            "    }",
        ]
        findings = aeh.find_to_string_mangling("lib/api_client.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_does_not_flag_guarded_fallback(self):
        lines = [
            "    } catch (e) {",
            "      emit(FooLoadFailed(e is AppException ? e.message : e.toString()));",
            "    }",
        ]
        findings = aeh.find_to_string_mangling("lib/x_bloc.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_does_not_flag_guarded_fallback_split_across_lines(self):
        lines = [
            "    onError: (ex) => emit(",
            "      FooLoadFailed(",
            "        ex is AppException ? ex.message : ex.toString(),",
            "      ),",
            "    ),",
        ]
        findings = aeh.find_to_string_mangling("lib/x_bloc.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_does_not_flag_discarded_exception(self):
        lines = [
            "    } catch (_) {",
            "      // refresh failed -- let the error propagate",
            "    }",
        ]
        findings = aeh.find_to_string_mangling("lib/x_bloc.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_does_not_flag_comment_mentioning_the_pattern(self):
        lines = [
            "/// (a bloc's generic `catch (e) { emit(Failure(e.toString())) }` has no way",
            "/// to tell a parsing bug from a deliberately-thrown AppException).",
        ]
        findings = aeh.find_to_string_mangling("lib/x.dart", lines, VOCAB, SYNTAX)
        self.assertEqual(findings, [])


class DioBypassTest(unittest.TestCase):
    def test_flags_unwrapped_call(self):
        text = (
            "class FooRemoteDataSourceImpl {\n"
            "  Future<FooModel> fetchFoo() async {\n"
            "    final response = await ApiClient.instance.dio.get('/v1/foo');\n"
            "    return FooModel.fromJson(response.data);\n"
            "  }\n"
            "}\n"
        )
        findings = aeh.find_client_bypass("lib/x_datasource.dart", text, VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "client_call_bypasses_guard")
        self.assertEqual(findings[0]["severity"], "critical")

    def test_does_not_flag_call_wrapped_in_guard_api_call(self):
        text = (
            "class FooRemoteDataSourceImpl {\n"
            "  Future<FooModel> fetchFoo() => guardApiCall(() async {\n"
            "    final response = await ApiClient.instance.dio.get('/v1/foo');\n"
            "    return FooModel.fromJson(response.data);\n"
            "  });\n"
            "}\n"
        )
        findings = aeh.find_client_bypass("lib/x_datasource.dart", text, VOCAB, SYNTAX)
        self.assertEqual(findings, [])

    def test_flags_raw_dio_construction(self):
        text = (
            "Future<void> refresh() async {\n"
            "  final response = await Dio().post('/v1/auth/refresh', data: body);\n"
            "}\n"
        )
        findings = aeh.find_client_bypass("lib/api_client.dart", text, VOCAB, SYNTAX)
        self.assertEqual(len(findings), 1)

    def test_paren_matching_ignores_parens_inside_string_literals(self):
        text = (
            "Future<void> fetchFoo() => guardApiCall(() async {\n"
            "  final response = await ApiClient.instance.dio.get('/v1/foo(bar)');\n"
            "});\n"
        )
        findings = aeh.find_client_bypass("lib/x_datasource.dart", text, VOCAB, SYNTAX)
        self.assertEqual(findings, [])


class DeadFailureStateTest(unittest.TestCase):
    def test_flags_unconsumed_state(self):
        files = {
            "lib/features/foo/presentation/bloc/foo_state.dart": (
                "final class FooLoadFailed extends FooState {\n"
                "  const FooLoadFailed(this.message);\n"
                "  final String message;\n"
                "}\n"
            ),
            "lib/features/foo/presentation/bloc/foo_bloc.dart": (
                "class FooBloc extends Bloc<FooEvent, FooState> {\n"
                "  void _onLoad(e, emit) { emit(FooLoadFailed('x')); }\n"
                "}\n"
            ),
        }
        findings = aeh.find_dead_failure_states(files, VOCAB, KNOWN_DEAD, SYNTAX)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "dead_failure_state")
        self.assertEqual(findings[0]["severity"], "should_fix")

    def test_does_not_flag_consumed_state(self):
        files = {
            "lib/features/foo/presentation/bloc/foo_state.dart": (
                "final class FooLoadFailed extends FooState {\n"
                "  const FooLoadFailed(this.message);\n"
                "}\n"
            ),
            "lib/app/router/routes/foo_routes.dart": (
                "errorMessage: s is FooLoadFailed ? s.message : null,\n"
            ),
        }
        findings = aeh.find_dead_failure_states(files, VOCAB, KNOWN_DEAD, SYNTAX)
        self.assertEqual(findings, [])

    def test_does_not_flag_known_intentional_exception(self):
        files = {
            "lib/features/tour_notes/presentation/bloc/tour_notes_hub_state.dart": (
                "final class TourNotesHubLoadFailed extends TourNotesHubState {\n"
                "  const TourNotesHubLoadFailed(this.message);\n"
                "}\n"
            ),
        }
        findings = aeh.find_dead_failure_states(files, VOCAB, KNOWN_DEAD, SYNTAX)
        self.assertEqual(findings, [])

    def test_handles_class_declaration_split_across_lines(self):
        files = {
            "lib/features/foo/presentation/bloc/foo_state.dart": (
                "final class FooLoadFailed\n"
                "    extends FooState {\n"
                "  const FooLoadFailed(this.message);\n"
                "}\n"
            ),
        }
        findings = aeh.find_dead_failure_states(files, VOCAB, KNOWN_DEAD, SYNTAX)
        self.assertEqual(len(findings), 1)


class InlineErrorWidgetTest(unittest.TestCase):
    def test_flags_screen_without_app_error_state(self):
        files = {
            "lib/features/foo/presentation/pages/foo_screen.dart": (
                "if (adapter.errorMessage != null) {\n"
                "  return _ErrorBanner(message: adapter.errorMessage!);\n"
                "}\n"
            ),
        }
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "inline_error_without_shared_state")
        self.assertEqual(findings[0]["severity"], "should_fix")

    def test_does_not_flag_screen_using_app_error_state(self):
        files = {
            "lib/features/foo/presentation/pages/foo_screen.dart": (
                "if (adapter.errorMessage != null) {\n"
                "  return AppErrorState(message: adapter.errorMessage!);\n"
                "}\n"
            ),
        }
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(findings, [])

    def test_does_not_flag_named_argument_construction(self):
        files = {
            "lib/features/foo/presentation/pages/foo_page_wrapper.dart": (
                "return FooScreen(adapter: FooAdapter(errorMessage: error));\n"
            ),
        }
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(findings, [])

    def test_ignores_files_outside_presentation_pages(self):
        files = {
            "lib/features/foo/presentation/bloc/foo_bloc.dart": (
                "if (adapter.errorMessage != null) { return _ErrorBanner(); }\n"
            ),
        }
        findings = aeh.find_inline_error_widgets(files, VOCAB)
        self.assertEqual(findings, [])


class RunAuditTest(unittest.TestCase):
    def test_severity_tiers_present_and_exit_worthy(self):
        files = {
            "lib/features/foo/data/datasources/foo_remote_datasource.dart": (
                "Future<FooModel> fetchFoo() async {\n"
                "  final response = await ApiClient.instance.dio.get('/v1/foo');\n"
                "  return FooModel.fromJson(response.data);\n"
                "}\n"
            ),
        }
        findings = aeh.run_audit(files, VOCAB, KNOWN_DEAD, syntax=SYNTAX)
        severities = {f["severity"] for f in findings}
        self.assertIn("critical", severities)
        for f in findings:
            self.assertIn(f["severity"], ("critical", "should_fix"))

    def test_clean_tree_produces_no_findings(self):
        files = {
            "lib/features/foo/presentation/bloc/foo_bloc.dart": (
                "  } catch (e) {\n"
                "    emit(FooLoadFailed(e is AppException ? e.message : e.toString()));\n"
                "  }\n"
            ),
        }
        findings = aeh.run_audit(files, VOCAB, KNOWN_DEAD, syntax=SYNTAX)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
