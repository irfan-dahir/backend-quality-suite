#!/usr/bin/env python3
"""A component API has to be coherent, not just correct.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_api_consistency.py"

## Why this exists

The other structural audits ask whether a component is *correct*: does it
overflow, does it meet contrast, is it swept, is it a reinvention. None asks
whether the components look like they were designed by the same person.

That stops being cosmetic the moment a second person writes against them. An API
someone has to look up per-component is an API they get wrong, and — as the
checks below were written to catch — some of those wrong guesses compile.

Ported from the design system's `tooling/scripts/audit_api_consistency.py`,
where all four checks are grounded in defects that package actually had. What
each check means now is stated under it: load-bearing and hard-baked copy are
universal and run off the language adapter's syntax; authored semantics keeps
its UI provenance and is meant to be switched off with a why on a server-side
tree; vocabulary's rules moved into project config, because Flutter literals in
a PHP tree is exactly the "another language's patterns match nothing, and the
run prints clean" failure this suite keeps closing.

## 1. Load-bearing copy — universal

A user-facing string is *load-bearing* when the code compares it to decide what
something means. The origin case appended an "Unknown" segment and identified it
with `option == 'Unknown'`, so the word printed on screen was simultaneously the
label and the sentinel. A caller whose own options contained that word got it
rendered twice, and a genuine answer of "Unknown" came back as `null` —
indistinguishable from never having answered.

It compiles, it renders, and it is quietly wrong, which is the whole family of
defect this tooling exists to catch. The backend reading is the same shape one
layer down: a PHP response where `$payload['status'] === 'Unknown'` decides
branching, so the envelope's own copy is also its control flow.

## 2. Hard-baked copy — OPT-IN, and this is the one that changed in the port

Copy the caller cannot override at all. In a white-label *package* that is a
defect: a client in another language, or simply with their own voice, has no way
out short of forking. On a backend it is the same defect on the wire — a
response literal a consumer must parse in your words rather than re-voice in
theirs.

In an application it is not a defect at all — the literals **are** the copy.
Running this against a consuming app would report every string it ships, which is
noise indistinguishable from a broken audit.

So it is off unless `checks.hardBakedCopy` turns it on, and turning it *off*
costs a written reason, because "we decided" and "nobody noticed" have to stay
distinguishable. This is a net, not a proof: it only matches literals someone
thought to pattern-match. What actually proves the claim is a reference brand
that renders every string in guillemets.

## 3. Authored semantics — UI provenance: off, with a why, on a server-side tree

A component with a tap handler must author a `Semantics` node.

`InkWell` and `GestureDetector` publish a tap action with **no name**, so a
screen reader announces "button" and then reads whatever text happens to sit
inside — tooltips, trailing values, subtitles, in build order.

Flutter's own `meetsGuideline(labeledTapTargetGuideline)` passes on that, because
it only asks whether a name exists *somewhere*. It cannot see that the name is
wrong, or that the ROLE is wrong, and the role is the part a user acts on: a dose
taken or not is a checkbox, a chip in a multi-select is selected or not.
Announcing either as a button loses the only state that matters.

Which wrappers count as authoring is per-project (`semanticsWrappers`), because
`Semantics` is Flutter's and the wrapper beside it is the project's own.

The check compares the project's interaction surface (`tappable`) against those
wrappers — and on a server-side tree the interaction surface belongs to the
client app, not to this codebase. A PHP adapter spells `tappable` as route
declarations, so leaving this check on would report every route as an unnamed
tap: a finding nobody can act on here, which is how a real finding on the client
side gets ignored too. The honest configuration is
`checks.authoredSemantics: {"enabled": false, "why": "<where the surface
lives>"}` — silence that costs a sentence, which the config contract enforces.
What is not honest is leaving it on and learning to skip its line.

## 4. Vocabulary — the rules are the project's own

Whether the same idea has the same name everywhere. Each rule is a class-name
condition plus the member conditions that contradict it, authored in
`apiConsistency.vocabularyRules` — the same file as every other architecture
fact this suite enforces (`[{message, classPattern?, classNotPattern?, has,
hasNot?}]`; a class whose name matches, whose members all match `has`, and whose
members match none of `hasNot`, is a finding).

The origin's rules were Flutter framework conventions, and they are recorded
under each shape as the provenance of the mechanism:

  * a class named `*Button`/`*Cta`/`*Fab` taking `onTap`, where Flutter's
    buttons take `onPressed` — and the mirror case, `onPressed` on a class that
    is not button-like
  * a nullable `onTap`/`onPressed` callback beside an `enabled` flag — two
    things that can disagree about whether a control works, where the nullable
    callback alone is supposed to be the one answer

`checks.vocabulary: true` with zero rules refuses rather than sweeping: a check
with nothing to compare reports a confident clean, which is this suite's
governing failure with a config file wrapped around it.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from backend_suite.adapters import for_project  # noqa: E402
from backend_suite.engine.arch import load  # noqa: E402
from backend_suite.project import need_refused, profile  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402
from backend_suite.engine.refusal import Refused  # noqa: E402

# Every line `scan()` emits starts with the file it is about, optionally with a
# `:line`, then prose. Parsed back out here rather than threading a second,
# structured return value through `scan()`: the string form is what `--out` has
# always written and what `capture-baselines.sh` diffs byte-for-byte, so the
# envelope is derived from it rather than changing it (findings.py's ADDITIVE
# rule). A line that does not parse still becomes a finding — with no file
# rather than being dropped, because a dropped finding is the silence this
# suite exists to prevent.
_LOCATION_RE = re.compile(r"^(\S+?\.\w+)(?::(\d+))?[: ]\s*(.*)$", re.S)


def _locate(line: str) -> tuple[str | None, int | None, str]:
    match = _LOCATION_RE.match(line)
    if not match:
        return None, None, line
    path, line_no, rest = match.groups()
    return path, int(line_no) if line_no else None, rest.strip() or line

# Comment handling lives in the adapter, not here. Two audits counting symbol
# uses have to agree on whether a mention inside a doc comment is one, and a
# second private copy is how they stop agreeing.
#
# `blank_comments` rather than the deleting version this file used to carry:
# it is string-aware (a `'https://…'` literal is not a comment) and it blanks
# in place, so the line numbers this audit reports still point at the right
# line. The old private copy deleted lines and shifted every number after one.
_ADAPTER, _, _ = for_project(REPO)
_RULES = load(REPO, "apiConsistency")

# The literal-shape patterns are the language adapter's optional
# API_CONSISTENCY capability (adapters.base.ApiConsistencySyntax). They used to
# be Flutter literals here: over a TSX tree the semantics check (InkWell /
# GestureDetector) could never match, and the run printed "4/4 checks clean".
_SYNTAX = getattr(_ADAPTER, "API_CONSISTENCY", None)
if _SYNTAX is None:
    raise Refused(
        f"the {getattr(_ADAPTER, 'NAME', '?')!r} language adapter has no "
        f"API_CONSISTENCY capability — it cannot say how this stack spells "
        f"on-screen copy or a raw tap target, and running another language's "
        f"patterns would report a confident zero. Implement API_CONSISTENCY in "
        f"that adapter (see adapters/php.py).", audit="audit_api_consistency")

if not hasattr(_ADAPTER, "blank_comments"):
    # Was a raw AttributeError (exit 1, read as "findings") on any adapter
    # without the capability; the rules below are also Dart-shaped.
    raise Refused(
        f"the {getattr(_ADAPTER, 'NAME', '?')!r} adapter has no blank_comments, and "
        f"this audit's rules are written for its syntax — this audit cannot run on "
        f"this stack. A refusal, not a clean result.")

# A string literal reaching one of these is on screen for someone to read.
USER_FACING = _SYNTAX.user_facing
# An overridable constructor default — not hard-baked.
DEFAULTED = _SYNTAX.defaulted
# A literal on either side of an equality test — the load-bearing shape.
COMPARED = _SYNTAX.compared

TAPPABLE = _SYNTAX.tappable

_WRAPPERS = _RULES.get("semanticsWrappers") or ["Semantics"]
AUTHORED = re.compile("|".join(rf"\b{re.escape(w)}\(" for w in _WRAPPERS))

# The vocabulary rules are the project's own naming decisions, so they live in
# arch-rules.json beside every other fact this suite enforces — the inline
# Flutter literals this used to carry would have run over a PHP tree matching
# nothing and reporting a confident clean. Every rule present in the config is
# compiled HERE, at load, so a malformed rule is a startup refusal rather than a
# silent skip at scan time: a rule that cannot run is a check that reports
# nothing, and the two must not look alike. Zero rules is legal — the check can
# be off — but not while it is on (see main()).
VOCABULARY_RULES: list[dict] = []
for _index, _rule in enumerate(_RULES.get("vocabularyRules") or []):
    _where = f"apiConsistency.vocabularyRules[{_index}]"
    _message = _rule.get("message")
    _has = _rule.get("has")
    if not isinstance(_message, str) or not _message.strip():
        raise Refused(
            f"{_where} has no non-empty `message`. A finding without a stated "
            f"conflict is a count, not a finding.")
    if not isinstance(_has, list) or not _has:
        raise Refused(
            f"{_where} has no `has` patterns — a rule with nothing to match on a "
            f"class body can never fire, and a check that cannot fire reads as one "
            f"that passed.")
    try:
        VOCABULARY_RULES.append({
            "message": _message.strip(),
            "class": re.compile(_rule["classPattern"]) if _rule.get("classPattern") else None,
            "classNot": (re.compile(_rule["classNotPattern"])
                         if _rule.get("classNotPattern") else None),
            "has": [re.compile(p) for p in _has],
            "hasNot": [re.compile(p) for p in _rule.get("hasNot") or []],
        })
    except re.error as exc:
        raise Refused(f"{_where} carries an invalid regex: {exc}")


def _exceptions() -> dict:
    """Per-project exemptions, each carrying its reason.

    Lives in the project's exceptions file rather than in this script, because a
    literal here would be one project's fact welded into every project's engine —
    which is exactly what the port existed to undo.
    """
    rel = need_refused(profile(REPO), "audits.exceptionsFile",
                       "is where audit_api_consistency reads its documented exemptions from")
    path = REPO / rel
    if not path.is_file():
        raise Refused(f"exceptions file not found at {rel}")
    try:
        exceptions = json.loads(path.read_text())
    except ValueError as exc:
        raise Refused(f"{rel} is not valid JSON: {exc}")
    return exceptions.get("apiConsistency", {}) or {}


def _check_enabled(name: str) -> bool:
    """Whether a check runs — and refuse to let it be switched off silently.

    A boolean `false` would make a disabled check indistinguishable from one
    nobody configured, and a check that reports nothing reads exactly like a
    check that passes. Turning one off costs a sentence.
    """
    entry = (_RULES.get("checks") or {}).get(name)
    if entry is None:
        raise Refused(
            f"apiConsistency.checks.{name} is not set. Set it to true, or to "
            f'{{"enabled": false, "why": "..."}} — an unconfigured check is one '
            f"nobody decided about.")
    if entry is True:
        return True
    if isinstance(entry, dict) and entry.get("enabled") is False and entry.get("why"):
        return False
    raise Refused(
        f"apiConsistency.checks.{name} must be `true` or "
        f'{{"enabled": false, "why": "<reason>"}}. A bare `false` records that '
        f"the check is off but not that anyone chose it.")


def _files() -> list[Path]:
    globs = _RULES.get("scope")
    if not globs:
        raise Refused("apiConsistency.scope is empty — an audit with nothing to "
                         "scan passes vacuously")
    if isinstance(globs, str):
        globs = [globs]
    found: list[Path] = []
    for pattern in globs:
        found.extend(REPO.glob(pattern))
    if not found:
        raise Refused(
            f"apiConsistency.scope matched no files ({', '.join(globs)}). Refusing "
            f"to report clean on an empty sweep — fix the globs or drop the audit.")
    return sorted(set(found))


def scan(paths: list[Path], exempt: dict) -> dict:
    compared: list[str] = []
    hardbaked: list[str] = []
    vocabulary: list[str] = []
    semantics: list[str] = []

    strings_exempt = exempt.get("hardBakedStrings", {}) or {}
    semantics_exempt = exempt.get("semanticsExempt", {}) or {}

    for path in paths:
        rel = path.relative_to(REPO).as_posix()
        src = _ADAPTER.blank_comments(path.read_text())

        # Asserts exist to *reject* a colliding label; they name the string
        # deliberately — a test exercising the case, not production code
        # deciding what something means by a word on screen.
        body = re.sub(r"assert\(.*?\n\s*\);", "", src, flags=re.S)

        for line_no, line in enumerate(body.splitlines(), 1):
            for a, b in COMPARED.findall(line):
                literal = a or b
                # Enum-ish and symbol-ish literals aren't user-facing copy.
                if literal[0].isupper() or " " in literal:
                    compared.append(f"{rel}:{line_no} compares against '{literal}'")

        overridable = set(DEFAULTED.findall(src))
        for literal in USER_FACING.findall(src):
            if (literal in overridable or literal in strings_exempt
                    or not literal[0].isalpha()):
                continue
            hardbaked.append(f"{rel}: '{literal}'")

        # Every declared kind in scope, not one language's spelling of one:
        # `class`/`final class`/`abstract class`, `interface`, `trait`, `enum`
        # are all containers a naming rule can hold. The extraction is generic
        # on purpose — it takes the body text and lets the project's own rules
        # decide what matters, so nothing language-specific hides here. Bodies
        # are matched multi-line (the convention in every language this suite
        # has syntax for); a one-line body reads as part of whatever follows
        # it, so plant fixtures with braces on their own lines.
        for cls, fields in re.findall(
            r"^\s*[\w\s]*?\b(?:class|interface|trait|enum)\s+(\w+)"
            r"[^{]*\{(.*?)^\}", src, flags=re.S | re.M
        ):
            if cls.startswith("_"):
                continue
            for rule in VOCABULARY_RULES:
                if rule["class"] and not rule["class"].search(cls):
                    continue
                if rule["classNot"] and rule["classNot"].search(cls):
                    continue
                if not all(p.search(fields) for p in rule["has"]):
                    continue
                if any(p.search(fields) for p in rule["hasNot"]):
                    continue
                vocabulary.append(f"{rel}: {cls} — {rule['message']}")

        if any(fnmatch.fnmatch(rel, p) or path.stem == p for p in semantics_exempt):
            continue
        if TAPPABLE.search(src) and not AUTHORED.search(src):
            semantics.append(f"{rel} has a tap handler and authors no Semantics")

    return {
        "compared": sorted(compared),
        "hardbaked": sorted(hardbaked),
        "semantics": sorted(semantics),
        "vocabulary": sorted(vocabulary),
    }


_REMEDY = {
    "compared": (
        "The word on screen must not also be the sentinel. Compare a position, an "
        "index, or an enum instead — a translator, or a client rebranding the copy, "
        "cannot silently change those."),
    "hardbaked": (
        "Read it from the project's string source so a caller can re-voice it. If a "
        "word genuinely should not be — a proper noun, a network name — add it to "
        "apiConsistency.hardBakedStrings in the exceptions file WITH A REASON. An "
        "absence reads as an oversight."),
    "semantics": (
        "Wrap it in the project's interactive wrapper, or author a Semantics node "
        "with the right ROLE — `checked:` for something taken or not, `selected:` "
        "for a chip in a multi-select, `button:` for a control that acts. Flutter's "
        "labelled-tap-target guideline passes without this, because it only asks "
        "whether a name exists somewhere."),
    "vocabulary": (
        "The rule that flagged this lives in apiConsistency.vocabularyRules "
        "because it is a naming decision this project actually holds to — two "
        "names for one idea are in play. Adopt the name the rest of the codebase "
        "already uses on the other side; if the rule no longer describes a real "
        "conflict, delete it with the care you would delete any check — a rule "
        "nobody believes trains readers to ignore findings."),
}
_HEADLINE = {
    "compared": "load-bearing copy — a string literal decides what something means",
    "hardbaked": "hard-baked copy — a string the caller cannot override",
    "semantics": "unauthored semantics — a tap handler with no name or role",
    "vocabulary": "vocabulary — the same idea spelled two ways",
}
_CHECK_KEY = {
    "compared": "loadBearingCopy",
    "hardbaked": "hardBakedCopy",
    "semantics": "authoredSemantics",
    "vocabulary": "vocabulary",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(default .backend-suite/findings/api-consistency.json)")
    args = parser.parse_args()

    paths = _files()
    exempt = _exceptions()
    enabled = {kind: _check_enabled(key) for kind, key in _CHECK_KEY.items()}
    if enabled["vocabulary"] and not VOCABULARY_RULES:
        raise Refused(
            "apiConsistency.checks.vocabulary is on but "
            "apiConsistency.vocabularyRules is empty. A vocabulary check with no "
            "rules compares nothing and reports a confident clean — the exact "
            "failure this audit's port exists to close. Author the naming rules "
            "this project holds itself to, or switch the check off with a why.",
            audit="audit_api_consistency")
    found = scan(paths, exempt)
    active = {k: v for k, v in found.items() if enabled[k]}

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(active, indent=2) + "\n")

    if args.findings:
        # Category is the check kind, so a project with one noisy `hardbaked`
        # sweep and a clean `semantics` one gets two grades rather than one.
        records = []
        for kind in sorted(active):
            for line in active[kind]:
                path, line_no, summary = _locate(line)
                records.append(F.make("api-consistency", kind, summary,
                                       severity=F.SHOULD_FIX,
                                       file=path, line=line_no))
        # Disabled checks are named in `suppressed`, not silently absent: a
        # check switched off must not read as a check that found nothing.
        off = {kind: f"{key} off — {(_RULES['checks'][key]).get('why')}"
               for kind, key in _CHECK_KEY.items() if not enabled[kind]}
        F.write(
            F.default_path(REPO, "api-consistency") if args.findings is True
            else REPO / args.findings,
            "api-consistency", records,
            scanned=len(paths),
            suppressed=off or None,
        )

    failed = False
    for kind in ("compared", "hardbaked", "semantics", "vocabulary"):
        if not active.get(kind):
            continue
        failed = True
        print(f"{_HEADLINE[kind]}:\n", file=sys.stderr)
        for line in active[kind]:
            print(f"  {line}", file=sys.stderr)
        print(f"\n{_REMEDY[kind]}\n", file=sys.stderr)
    if failed:
        return 1

    off = [k for k, key in _CHECK_KEY.items() if not enabled[k]]
    ran = len(_CHECK_KEY) - len(off)
    note = ""
    if off:
        # Named, not counted. A disabled check that appears only as a smaller
        # number is one nobody rereads.
        reasons = "; ".join(
            f"{_CHECK_KEY[k]} off — {(_RULES['checks'][_CHECK_KEY[k]]).get('why')}"
            for k in off)
        note = f"\n  {reasons}"
    print(f"audit_api_consistency: {ran}/{len(_CHECK_KEY)} checks clean over "
          f"{len(paths)} file(s){note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
