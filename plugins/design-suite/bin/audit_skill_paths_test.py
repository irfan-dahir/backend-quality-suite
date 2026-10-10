#!/usr/bin/env python3
"""Tests for the no-project-literals rules — PROJECT_PATH and its widenings.

CLAUDE.md's table of "never write / write instead" is enforced by a handful of
regexes and nothing else. Everything else about portability is prose, and prose
does not fail a build. If one of these patterns stops matching a shape, a skill
carrying a hardcoded consumer literal ships and behaves the way that defect
always behaves here: it does
not error, it silently audits the wrong place on any project shaped differently,
which is indistinguishable from a clean result.

**These cases are written against the contract, not against current behaviour.**
The rule is about what a skill *tells Claude to look at*, and a path inside
backticks is still that — a skill that says "scan `lib/widgets/`" has hardcoded a
consumer's layout just as thoroughly as one that says it unquoted, and markdown
prose is where a path is most likely to be in backticks. Cases below that fail
today are marked KNOWN-HOLE; they are deliberately not weakened to match, because
a test that ratifies the gap would make closing it look like a regression.

The excluded shapes are asserted just as carefully. A regex that fired on a
plugin-root invocation, or on an angle-bracketed placeholder, would flag the two
forms the rule actually prescribes, and a gate that reports correct code as a
violation gets muted — which costs more than the gate was worth.

    python3 plugins/design-suite/bin/audit_skill_paths_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only, no I/O — a regex is a
pure function of a string.
"""
from __future__ import annotations

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import audit_skill_paths as asp  # noqa: E402

FAILURES: list[str] = []
KNOWN_HOLES: list[str] = []


def expect(condition: bool, what: str, known_hole: bool = False) -> None:
    if condition:
        print("  ok   " + what)
        return
    if known_hole:
        # Still a failure. Recorded separately only so the report can say which
        # failures are the documented gap rather than a new break.
        KNOWN_HOLES.append(what)
    print("  FAIL " + what)
    FAILURES.append(what)


def caught(text: str) -> bool:
    return asp.PROJECT_PATH.search(text) is not None


def main() -> int:
    print("check: a project-shaped path in a skill is caught")
    expect(caught("Read every widget under lib/widgets/ and report."),
           "a bare source-tree path is caught")
    expect(caught("Check the dependency block in pubspec.yaml."),
           "a project manifest filename is caught")
    expect(caught("Every icon lives in assets/images and is registered."),
           "an asset directory literal is caught")
    expect(caught("Run the generator in token_pipeline/ before auditing."),
           "a pipeline directory literal is caught")
    expect(caught("Fixtures are registered in mock_api/contracts.json."),
           "a mock-api directory literal is caught")

    print("check: the same paths in backticks are still hardcoded paths")
    # Markdown prose is where a skill is MOST likely to quote a path, so this is
    # the shape the rule most needs to cover, not an edge case.
    expect(caught("Scan `lib/widgets/` for unlabelled icon buttons."),
           "a source-tree path inside backticks is caught", known_hole=True)
    expect(caught("Add the asset to `pubspec.yaml` under flutter/assets."),
           "a manifest filename inside backticks is caught", known_hole=True)
    expect(caught("Renders come out in `assets/images`."),
           "an asset directory inside backticks is caught", known_hole=True)

    print("check: the prescribed forms are NOT caught")
    # The negative controls. Without these, a regex matching everything would
    # pass every assertion above.
    expect(not caught("Run ${CLAUDE_PLUGIN_ROOT}/bin/resolve.py --profile x"),
           "a plugin-root invocation is not flagged")
    expect(not caught("Scan <source.root>/widgets, read from the profile."),
           "an angle-bracketed placeholder is not flagged")
    expect(not caught("The project's own library/ directory is unrelated."),
           "a word merely starting with 'lib' is not flagged")
    expect(not caught("See docs/DESIGN.md — doc roles are out of scope here."),
           "a doc path is left to the {{doc:}} mechanism, not flagged here")

    # ------------------------------------------------------------------
    # Rule 5: project IDENTIFIERS, not just project paths.
    # ------------------------------------------------------------------
    # /promote-component carried a consumer's package, its GitHub repository and
    # seven of its class names through the Phase 1 widening without firing a
    # single rule — none of those literals is path-shaped, so PROJECT_PATH's
    # alternation never saw them and PROJECT_NAMES did not match either.
    #
    # The controls here are the more important half. `ThemeData` and `MediaQuery`
    # are FRAMEWORK types: correct, portable, and legitimately named by a skill
    # about a project whose adapter is that framework. A rule that flags them is
    # a rule somebody switches off, and a switched-off gate is worse than the
    # blind spot it replaced. They are asserted as controls rather than trusted.
    def ident(text: str, name: str = "some-skill.md") -> set[str]:
        return {hit for hit, _ in asp.project_identifiers(text, name)}

    print("check: project identifiers are caught")
    expect("DsStatCell" in ident("Compare against `DsStatCell(icon, value)`."),
           "a prefixed design-system export symbol is caught")
    expect("ds_flutter" in ident("The tokens live in `ds_flutter`."),
           "a project package name is caught")
    expect("acme-org/acme-design-system"
           in ident("Governed by `acme-org/acme-design-system`, whose gates apply."),
           "a backticked repository slug is caught")
    expect("acme-org/acme-design-system"
           in ident("See https://github.com/acme-org/acme-design-system for gates."),
           "a repository slug inside a GitHub URL is caught")

    print("check: CONTROL — framework types and portable prose do NOT fire")
    expect(ident("Delete the `ThemeData` parameter and read from context.") == set(),
           "CONTROL: `ThemeData` is a framework type, not a project literal")
    expect(ident("`MediaQuery...size` where constraints are meant.") == set(),
           "CONTROL: `MediaQuery` is a framework type, not a project literal")
    expect(ident("A fixed `Row` that overflows at 2.0x text scale.") == set(),
           "CONTROL: a bare framework widget name does not fire")
    expect(ident("Use `LayoutBuilder`, `Semantics` and `TextScaler`.") == set(),
           "CONTROL: several framework types in one line still do not fire")
    expect(ident("Run `python3 ${CLAUDE_PLUGIN_ROOT}/bin/resolve.py design`.") == set(),
           "CONTROL: a plugin-internal invocation does not fire")
    expect(ident("Read `docs/api-reference.html` and `docs/CONCEPTS.md`.") == set(),
           "CONTROL: a slash-bearing FILE path is not mistaken for a repo slug")
    expect(ident("Resolve with `bin/resolve.py`, see `design_suite/engine`.") == set(),
           "CONTROL: plugin-internal relative paths are not repo slugs")
    expect(ident("Treat read/write and input/output as ordinary prose.") == set(),
           "CONTROL: an ordinary slashed word pair is not a repo slug")
    expect(ident("The `{{doc:components}}` role and `{{dir:derived}}`.") == set(),
           "CONTROL: role notation does not fire")
    expect(ident("`Ds` alone, and `ds` alone, are two letters.") == set(),
           "CONTROL: the bare prefix without a symbol after it does not fire")

    print("check: rules 5b/5c reach into the plugin's own CODE, regex included")
    # This is the widening that closed the defect. The gate could always SEE
    # the string — `code_literals()` yields every non-docstring constant, and a
    # regex is an ordinary string argument to `re.compile` — but the only rule
    # applied to code literals was PROJECT_PATH, and a bare package name is not
    # path-shaped. The rule was missing, not the visibility, so the case that
    # matters is the regex literal itself.
    def in_code(text: str) -> set[str]:
        return {hit for hit, _why in asp.identifiers_in_code(text, "x.py")}

    expect(in_code(r"^import\s+['\"]package:ds_flutter/") == {"ds_flutter"},
           "a package name inside a REGEX literal is caught — the exact form "
           "that sat clean in two audits")
    expect(in_code("ds_flutter") == {"ds_flutter"},
           "and so is the same name as a plain comparison literal")
    expect(in_code("DsStatCell") == {"DsStatCell"},
           "a prefixed export symbol in code is caught too")
    expect(in_code("ThemeData") == set(),
           "CONTROL: a framework type cannot match a rule anchored on the "
           "configured export prefix")
    expect(in_code(".dart_tool/package_config.json") == set(),
           "CONTROL: a toolchain path is not a project identifier")
    expect(in_code("design_suite/engine") == set(),
           "CONTROL: a plugin-internal path is not a package name")
    expect(in_code("ds") == set() and in_code("ds_") == set(),
           "CONTROL: the bare prefix is two letters of English, not a package")

    print("check: CONTROL — an identifier exemption is scoped, not blanket")
    _saved = list(asp.IDENT_EXEMPT)
    asp.IDENT_EXEMPT[:] = [("pointer-skill.md", "example-org/example-repo",
                            "synthetic entry for this test")]
    try:
        expect(asp.ident_exempt("pointer-skill.md",
                                "example-org/example-repo") is not None,
               "an exempted identifier is exempt, with a printed reason")
        expect(asp.ident_exempt("pointer-skill.md", "DsStatCell") is None,
               "CONTROL: the exemption covers that one slug only — it does "
               "not amnesty every identifier in that file")
        expect(asp.ident_exempt("promote-component.md",
                                "example-org/example-repo") is None,
               "CONTROL: the exemption is keyed to the file that earned it")
    finally:
        asp.IDENT_EXEMPT[:] = _saved

    # ------------------------------------------------------------------
    # Rule 6 — a hardcoded external URL. The defect that motivated it is a
    # consumer's mock server compiled into generated OpenAPI; the CONTROLS are
    # the more important half, for the same reason as rule 5's. This repo's own
    # forge, namespace URIs, an install pointer and loopback all appear in the
    # plugin legitimately, and a gate that fires on them gets switched off.
    def urls(text: str, name: str = "some_engine.py") -> set[str]:
        return {hit for hit, _ in asp.external_urls(text, name)}

    print("check: a hardcoded external host is caught")
    expect("api.acme-client.com" in urls('BASE = "https://api.acme-client.com/v2"'),
           "a consumer's API host is caught")
    expect("00000000-0000-4000-8000-000000000000.mock.pstmn.io"
           in urls('"dev": "https://00000000-0000-4000-8000-000000000000'
                   '.mock.pstmn.io"'),
           "the mock-server host that motivated this rule is caught — a UUID "
           "host contains no project NAME, so rule 4 could never reach it")
    expect(urls("Fetch http://cdn.example-vendor.net/bundle.js") != set(),
           "an http:// host is caught as well as https://")

    print("check: CONTROL — legitimate hosts do NOT fire")
    expect(urls('"https://github.com/irfan-dahir/ai-design-suite"') == set(),
           "CONTROL: this repository's own forge does not fire (the OWNER "
           "segment is rule 5a's question, not rule 6's)")
    expect(urls('curl -fsSL https://raw.githubusercontent.com/Homebrew/install'
                '/HEAD/install.sh') == set(),
           "CONTROL: Homebrew's bootstrap URL does not fire")
    expect(urls('xmlns="http://www.w3.org/2000/svg"') == set(),
           "CONTROL: an XML namespace URI is an identifier, never fetched")
    expect(urls('"$schema": "https://json-schema.org/draft/2020-12/schema"')
           == set(),
           "CONTROL: a JSON Schema meta-schema URI does not fire")
    expect(urls("point them to https://brew.sh rather than scripting it") == set(),
           "CONTROL: an install-docs pointer does not fire")
    expect(urls("navigate to `http://127.0.0.1:8934/<id>.webp`") == set(),
           "CONTROL: loopback cannot be a consumer's endpoint")
    expect(urls("serve on http://localhost:8080/preview") == set(),
           "CONTROL: localhost cannot be a consumer's endpoint")
    expect(urls("Read docs/CONCEPTS.md and the profile at .design-suite/") == set(),
           "CONTROL: a path with no scheme is not a URL")
    expect(urls("See the ADOPTING.md section on http proxies.") == set(),
           "CONTROL: the bare word 'http' in prose does not fire")
    expect(asp.host_allowed("gist.github.com"),
           "CONTROL: a subdomain of an allowed host is allowed")
    expect(not asp.host_allowed("github.com.attacker.example"),
           "CONTROL: a host merely CONTAINING an allowed one is not allowed")

    # ------------------------------------------------------------------
    # Rule 4 widened to code literals. The control is the whole reason this was
    # safe to widen: the three surviving occurrences of the name in the
    # universal plugin's Python are all prose that exists to FORBID the
    # coupling, and prose never reaches code_literals()' AST walk.
    print("check: rule 4 over code literals")
    expect(asp.names_in_code('"AcmeCorp API Reference"', "generate_openapi.py",
                             {"acmecorp"}) == ["acmecorp"],
           "a consumer product name in a code literal is caught")
    expect(asp.names_in_code('"acmecorp_mobile"', "x.py", {"acmecorp"})
           == ["acmecorp"],
           "the name is matched case-insensitively and inside a longer token")
    expect(asp.names_in_code('"read the name from project.name"', "x.py",
                             {"acmecorp"}) == [],
           "CONTROL: a literal that does not name the project does not fire")
    expect(asp.names_in_code('"API Reference"', "x.py", set()) == [],
           "CONTROL: an empty derived name set flags nothing — it cannot flag "
           "everything just because it knows nothing")

    # ------------------------------------------------------------------
    # The hashed client-name denylist. Planted, then controls.
    print("check: hashed client-name denylist")
    import client_denylist as cd
    planted = {cd.digest("acmecorp"), cd.digest("blue harbor")}
    expect([n for n, _ in cd.hits_in("x\npackages/ds_tokens_acmecorp/\n", planted)] == [2],
           "a planted name inside a snake_case token is caught, with its line")
    expect(cd.hits_in("EXT-AcmeCorp-Mobile", planted) != [],
           "matched case-insensitively across a kebab-case repo name")
    expect(cd.hits_in("the Blue  Harbor portal", planted) != [],
           "a two-word name is caught as a token run")
    expect(cd.hits_in("acmecorporation and acme corp", planted) == [],
           "CONTROL: a longer word merely containing the name does not fire")
    expect(all("acmecorp" not in d for _, d in cd.hits_in("acmecorp", planted)),
           "the report names a digest prefix, never the name")
    expect(cd.load(Path("/nonexistent/denylist")) == set(),
           "a missing digest file loads as empty, which check() reports INERT")
    expect(len(cd.load()) >= 1,
           "the committed digest file is present and non-empty")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        if KNOWN_HOLES:
            print(f"{len(KNOWN_HOLES)} of them are the documented backtick hole in "
                  f"PROJECT_PATH's lookbehind, which excludes '`'. The contract says "
                  f"these must be caught; the regex does not catch them yet. Do not "
                  f"weaken these cases — fix the lookbehind.")
        return 1
    print("audit_skill_paths: all cases hold (rules 3, 5 and 6).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
