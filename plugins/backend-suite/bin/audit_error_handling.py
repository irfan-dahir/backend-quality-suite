#!/usr/bin/env python3
"""Does every failure actually reach the user, or does it leak, bypass, or drop?

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_error_handling.py"

## Why this exists

Error handling is the part of an app nobody demos and everybody discovers in
production. The four checks below each catch a way a failure stops being visible:
a network call that never routes through the shared mapper, a caught exception
whose internal string reaches the screen, a failure state emitted and never
matched, a screen that reads an error and renders its own thing.

None of them is about whether the code compiles. All of them are about whether a
user finds out something went wrong.

## Ported from `scripts/audit_error_handling.py` in the mobile app

The *shape* travelled unchanged — the four checks, the two severity tiers, the
paren-matching that lets check 2 tell "inside the guard" from "beside it". The
**vocabulary did not**, and that was the whole port.

`AppException`, `guardApiCall`, `ApiClient.instance.dio`, `AppErrorState`,
`errorMessage`, `*_state.dart` — every one of those is one project's name for a
thing every project has. Left as literals they would make this engine report a
confident zero on any codebase that spelled its error machinery differently, and
zero findings is indistinguishable from a clean run.

So they live in the project's architecture rules, and a project that has not
named them gets a refusal rather than a pass. The checks take their vocabulary as
an argument, which is also what lets the tests construct one directly instead of
needing a whole project profile on disk.

## Two severity tiers

`critical` findings are unambiguous greps with no realistic false-positive risk.
`should_fix` findings need a human's judgement and are advisory — they are
reported and do not fail the build, so that the tier which *does* fail stays
worth reading.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TO_STRING_WINDOW = 4  # lines to scan after a catch/onError site

# The *syntax* (how a catch, a type test, a string interpolation is spelled)
# comes from the language adapter's optional ERROR_HANDLING capability
# (backend_suite.adapters.base.ErrorHandlingSyntax). It used to be Dart literals
# here, so on any other stack the audit matched nothing and exited 0. An adapter
# without the capability makes this audit refuse with exit 2.


@dataclass(frozen=True)
class Vocabulary:
    """What this project calls the pieces of its own error machinery.

    Every field is a name the origin script had hardcoded. A dataclass rather
    than a dict so a missing field is an error where it is built, not a `None`
    that silently turns a regex into one that matches nothing.
    """

    exception_type: str        # the shared exception the app maps failures onto
    guard_call: str            # the wrapper every network call must sit inside
    client_call_pattern: str   # what an unguarded client call looks like
    error_state_widget: str    # the shared "something went wrong" widget
    error_message_field: str   # the adapter field a screen reads an error from
    state_class_pattern: str   # how a failure state class is spelled
    state_file_suffix: str     # which files hold those state classes
    pages_marker: str          # path fragment identifying a screen

    @property
    def client_call(self) -> re.Pattern:
        return re.compile(self.client_call_pattern)

    @property
    def guard(self) -> re.Pattern:
        return re.compile(rf"\b{re.escape(self.guard_call)}\s*\(")

    @property
    def state_class(self) -> re.Pattern:
        return re.compile(self.state_class_pattern)


def find_to_string_mangling(rel_path: str, lines: list[str], vocab: Vocabulary,
                            syntax) -> list[dict]:
    """A caught exception stringified straight onto the screen."""
    findings = []
    comment = syntax.line_comment
    for i, line in enumerate(lines):
        if line.strip().startswith(comment):
            continue  # a comment mentioning the anti-pattern isn't the anti-pattern
        m = syntax.catch_var.search(line)
        if not m:
            continue
        var = next((g for g in m.groups() if g), None)
        if not var or var == "_":
            continue
        window_lines = lines[i: i + TO_STRING_WINDOW]
        guard_re = syntax.type_guard(var, vocab.exception_type)
        if guard_re.search("\n".join(window_lines)):
            continue  # the sanctioned `x is AppException ? x.message : x.toString()`
        # Only the *whole* exception reaching a string — not its `.message`.
        mangle_re = syntax.stringify(var)
        for offset, wline in enumerate(window_lines):
            if wline.strip().startswith(comment):
                continue
            if mangle_re.search(wline):
                lineno = i + offset + 1
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "check": "to_string_mangling",
                    "severity": "should_fix",
                    # The wording is deliberately adapter-neutral: it names the
                    # shapes every stack shares (cast / interpolation /
                    # stringification) rather than one language's spellings —
                    # the previous text told a PHP reader to write
                    # `x is AppError ? … : …`, which is Dart's guard.
                    "detail": (
                        f"{rel_path}:{lineno} puts the caught exception `{var}` into "
                        f"a string whole — cast, interpolation, or stringification "
                        f"— rather than narrowing it to its message. The whole "
                        f"exception is message plus stack: test `{var}` against "
                        f"{vocab.exception_type} and take its message explicitly. "
                        f"An implicit conversion is a silent trap the moment "
                        f"{vocab.exception_type}'s string form stops returning just "
                        f"the message."),
                })
                break
    return findings


def matching_paren(text: str, open_paren_idx: int,
                   quotes: tuple = ("'", '"')) -> int:
    """Index of the ')' matching the '(' at open_paren_idx.

    Skips string-literal contents so a stray paren inside a path or a message
    does not throw off the depth count.
    """
    depth = 0
    in_string: str | None = None
    i = open_paren_idx
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
        elif ch in quotes:
            in_string = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1  # unbalanced — treat as running to EOF


def find_client_bypass(rel_path: str, text: str, vocab: Vocabulary, syntax) -> list[dict]:
    """A network call sitting outside the guard rather than inside it."""
    guarded_spans = []
    for m in vocab.guard.finditer(text):
        open_idx = m.end() - 1
        guarded_spans.append((open_idx, matching_paren(text, open_idx, syntax.string_quotes)))

    findings = []
    for m in vocab.client_call.finditer(text):
        call_idx = m.start()
        if any(start <= call_idx <= end for start, end in guarded_spans):
            continue
        lineno = text.count("\n", 0, call_idx) + 1
        findings.append({
            "file": rel_path,
            "line": lineno,
            "check": "client_call_bypasses_guard",
            "severity": "critical",
            "detail": (
                f"{rel_path}:{lineno} makes a network call outside "
                f"`{vocab.guard_call}(...)`. Every call must route through it so "
                f"failures map onto the shared {vocab.exception_type} hierarchy "
                f"instead of being hand-rolled per call site."),
        })
    return findings


def find_dead_failure_states(files: dict[str, str], vocab: Vocabulary,
                             known_dead: dict, syntax) -> list[dict]:
    """A failure state emitted and pattern-matched by nothing."""
    findings = []
    for rel_path, text in files.items():
        if not rel_path.endswith(vocab.state_file_suffix):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = vocab.state_class.match(line.strip())
            if not m:
                continue
            class_name = m.group(1)
            if class_name in known_dead:
                continue
            is_pattern = syntax.type_test(class_name)
            consumed = any(
                is_pattern.search(other_text)
                for other_path, other_text in files.items()
                if other_path != rel_path
            )
            if not consumed:
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "check": "dead_failure_state",
                    "severity": "should_fix",
                    # `type-tests` rather than `is X`/`instanceof X`: the type
                    # test's spelling belongs to the adapter, and the previous
                    # wording named Dart's for every stack.
                    "detail": (
                        f"{class_name} ({rel_path}:{lineno}) is declared but no "
                        f"other file type-tests for it outside its own state file "
                        f"— nothing surfaces this failure to the user."),
                })
    return findings


def find_inline_error_widgets(files: dict[str, str], vocab: Vocabulary) -> list[dict]:
    """A screen that reads an error and renders its own thing instead."""
    # Member access takes `->` (PHP) as well as `.` (Dart-era spelling): with
    # `\.` alone this check could never fire on the shipped adapter — a silent
    # zero on every real PHP project, which is the failure mode the audit
    # exists to prevent.
    ref_re = re.compile(rf"(?:->|\.)\s*{re.escape(vocab.error_message_field)}\b")
    shared_re = re.compile(rf"\b{re.escape(vocab.error_state_widget)}\b")
    findings = []
    for rel_path, text in files.items():
        if vocab.pages_marker not in rel_path:
            continue
        if not ref_re.search(text) or shared_re.search(text):
            continue
        lineno = next((i for i, line in enumerate(text.splitlines(), start=1)
                       if ref_re.search(line)), 1)
        findings.append({
            "file": rel_path,
            "line": lineno,
            "check": "inline_error_without_shared_state",
            "severity": "should_fix",
            "detail": (
                f"{rel_path} reads {vocab.error_message_field} but never renders "
                f"{vocab.error_state_widget} — a bespoke inline error widget, "
                f"inconsistent with every other screen."),
        })
    return findings


def run_audit(files: dict[str, str], vocab: Vocabulary,
              known_dead: dict | None = None, *, syntax) -> list[dict]:
    """Every check over an already-read set of files.

    Kept separate from `main()` so the tests can drive the whole audit from an
    in-memory dict — no repository, no profile, no disk. That is what makes the
    fixtures stable while the real tree's findings get fixed out from under them.
    """
    known_dead = known_dead or {}
    findings: list[dict] = []
    for rel, text in files.items():
        findings += find_to_string_mangling(rel, text.splitlines(), vocab, syntax)
        findings += find_client_bypass(rel, text, vocab, syntax)
    findings += find_dead_failure_states(files, vocab, known_dead, syntax)
    findings += find_inline_error_widgets(files, vocab)
    return findings


def _vocabulary(rules: dict) -> Vocabulary:
    fields = Vocabulary.__dataclass_fields__
    missing = [f for f in fields if f not in rules]
    if missing:
        from backend_suite.engine.refusal import Refused  # noqa: E402
        raise Refused(
            "errorHandling is missing " + ", ".join(sorted(missing)) + ".\n"
            "These are this project's names for its own error machinery, and this "
            "audit cannot guess them — a wrong name matches nothing and reports a "
            "confident zero.")
    # Present-but-placeholder is the same incapacity wearing the other mask:
    # the scaffolded `TODO: …` value is not this project's name for anything,
    # it matches nothing, and the run reports a confident zero over real files
    # (measured: scaffold vocabulary + a real fileGlob exited 0 clean). Refuse
    # it the way audit_layer_boundaries refuses its own TODO rules.
    todos = [f for f in fields if str(rules[f]).lstrip().startswith("TODO")]
    if todos:
        from backend_suite.engine.refusal import Refused  # noqa: E402
        raise Refused(
            "errorHandling still holds init.py's TODO placeholders: "
            + ", ".join(sorted(todos)) + ".\n"
            "A TODO string is not this project's name for its error machinery — "
            "it matches nothing and reports a confident zero. Fill them in, or "
            "delete the section and the audit together.")
    return Vocabulary(**{f: rules[f] for f in fields})


def error_handling_syntax(adapter):
    """The adapter's ERROR_HANDLING capability, or a named refusal."""
    syntax = getattr(adapter, "ERROR_HANDLING", None)
    if syntax is None:
        from backend_suite.engine.refusal import Refused  # noqa: E402
        raise Refused(
            f"the {getattr(adapter, 'NAME', '?')!r} language adapter has no "
            f"ERROR_HANDLING capability — it cannot say how this stack spells a "
            f"catch, a type test, or a stringified exception. Running another "
            f"language's patterns would match nothing and report a confident zero. "
            f"Implement ERROR_HANDLING in that adapter (see adapters/php.py).",
            audit="audit_error_handling")
    return syntax


def main() -> int:
    from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

    repo = project_root()
    from backend_suite.engine.arch import load      # noqa: E402
    from backend_suite.project import need_refused, profile  # noqa: E402
    from backend_suite.engine.refusal import Refused  # noqa: E402

    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", help="override the scanned tree (default: source.root)")
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /quality-debt "
                             "(bare flag uses the default path)")
    args = parser.parse_args()

    from backend_suite.adapters import load as load_adapter, _suffixes  # noqa: E402

    rules = load(repo, "errorHandling")
    vocab = _vocabulary(rules)
    prof = profile(repo)
    lang = (prof.get("adapters", {}) or {}).get("lang")
    if not lang:
        raise Refused(".backend-suite/profile.json does not set adapters.lang — no "
                      "language adapter to say how this stack spells error handling.",
                      audit="audit_error_handling")
    adapter = load_adapter(lang)
    syntax = error_handling_syntax(adapter)
    # An adapter whose globs span file kinds this syntax cannot describe (web's
    # stylesheets) narrows them, so a CSS-only sweep refuses instead of passing.
    covered = (tuple(getattr(adapter, "ERROR_HANDLING_SUFFIXES", ()))
               or _suffixes(getattr(adapter, "FILE_GLOBS", ())))
    scan_root = repo / (args.dir or need_refused(prof, "source.root",
                                                  "is the tree this audit scans",
                                                  audit="audit_error_handling"))
    file_glob = need_refused(prof, "source.fileGlob",
                             "is how this audit finds sources",
                             audit="audit_error_handling")

    known_dead = {}
    exceptions_rel = (prof.get("audits", {}) or {}).get("exceptionsFile")
    if exceptions_rel and (repo / exceptions_rel).is_file():
        try:
            exceptions = json.loads((repo / exceptions_rel).read_text())
        except ValueError as exc:
            raise Refused(f"{exceptions_rel} is not valid JSON: {exc}")
        known_dead = (exceptions.get("errorHandling", {}) or {}).get(
            "intentionalDeadStates", {}) or {}

    # Only files the adapter's syntax describes: a `.swift` file matched by the
    # profile glob but read with Dart patterns would be "scanned" and say nothing.
    files = {p.relative_to(repo).as_posix(): p.read_text()
             for p in sorted(scan_root.glob(file_glob))
             if p.is_file() and (not covered or p.suffix in covered)}
    if not files:
        raise Refused(f"no files under {scan_root} matching {file_glob!r} that the "
                      f"{lang!r} adapter reads — refusing to report clean on an "
                      f"empty sweep", audit="audit_error_handling")

    findings = run_audit(files, vocab, known_dead, syntax=syntax)

    if args.out:
        (repo / args.out).parent.mkdir(parents=True, exist_ok=True)
        (repo / args.out).write_text(json.dumps(findings, indent=2) + "\n")

    # Deliberately NOT nested inside `if args.out` — the two flags are
    # independent, and requiring both would make --findings silently do nothing
    # on its own. It did, briefly, which is exactly the failure this suite is
    # built to refuse: a flag that appears to work and writes nothing.
    if args.findings:
        from backend_suite.engine import findings as F
        F.write(
            F.default_path(repo, "error_handling") if args.findings is True
            else repo / args.findings,
            "error_handling",
            F.from_records("error_handling", findings,
                           category_key="check", severity_key="severity"),
            scanned=len(files),
        )

    critical = [f for f in findings if f["severity"] == "critical"]
    advisory = [f for f in findings if f["severity"] != "critical"]

    for label, group in (("CRITICAL", critical), ("should fix", advisory)):
        if not group:
            continue
        stream = sys.stderr if group is critical else sys.stdout
        print(f"\n{label} — {len(group)} finding(s):\n", file=stream)
        for f in group:
            print(f"  {f['detail']}", file=stream)

    print(f"\naudit_error_handling: {len(files)} file(s), {len(critical)} critical, "
          f"{len(advisory)} advisory ({len(known_dead)} documented dead state(s))")
    # Exit code carries "were there findings", full stop — severity is a
    # property of the finding, not of the contract. `return 1 if critical
    # else 0` used to let an advisory-only run exit 0, which is exactly the
    # "found something and reported it clean" failure this suite exists to
    # refuse: repo_health.py and any other rc-only consumer would read an
    # advisory-only run as spotless. Severity still drives which stream a
    # finding prints to and whether a human should drop everything for it —
    # that's a presentation decision, made below, not an exit-code one.
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
