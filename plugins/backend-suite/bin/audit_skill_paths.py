#!/usr/bin/env python3
"""Fail if a skill tells Claude to run a script that isn't there.

This exists because it already happened, to every skill at once. Phase 1 moved
the scripts out of the app and into this plugin, and all 21 skills kept citing
their old in-app locations — `python3 .backend-suite/resolve.py`,
`token_pipeline/scripts/audit_tokens.py`, and so on. The scripts themselves were
fine. Every documented way to invoke them was dead, in a shipped, installable
plugin, and nothing caught it: manifests parsed, Python compiled, the seam check
passed, `claude plugin validate` was clean.

It is the exact failure mode the suite is built to forbid — a check that reports
nothing being indistinguishable from a check that passes — so it gets a gate.

Six rules:

  1. Every `${CLAUDE_PLUGIN_ROOT}/…` path a skill names must exist in that
     plugin. This is decidable, which is why it is the primary rule.

  2. No skill may name a path from the pre-extraction layout. These are
     project-relative and so cannot be verified by existence, but they are known
     to be wrong wherever they appear.

  3. No skill may hardcode a project-shaped path at all — `lib/…`, `pubspec.yaml`,
     `assets/images`, a pipeline directory. Added after /review-docs was found
     carrying 7 and /audit-assets 3, in skills that advertise portability. This one
     is the quietest of the three: a hardcoded path does not error, it silently
     audits the wrong place on any project shaped differently, which reads exactly
     like a clean result. Read them from the profile instead.

     Applies to the plugin's own Python too, not only to skills — the engine is
     shipped in the same universal plugin and is where the hardcoding actually
     accumulated, as `argparse` defaults. Narrowed to code literals, for the
     reasons in code_literals().

  4. No skill in the UNIVERSAL plugin may name a consumer project. Quieter still:
     nothing errors, the skill simply tells the model it is working on a different
     project than it is. Four skills addressed the model as though it were on one
     specific repo, in a plugin installed on two and advertised for any.

     Applies to the plugin's own Python too, for the same reason rule 3 does and
     with the same narrowing to code literals — see `names_in_code()`.

  5. No skill in the UNIVERSAL plugin may name a project IDENTIFIER that is not
     path-shaped — a repository slug, a design-system export symbol, a package.
     See the long block above `REPO_SLUG`.

  6. No file in the UNIVERSAL plugin may hardcode an absolute http(s) URL whose
     host is not on a short allow-list. A consumer's service endpoint is a
     project literal by definition, and a URL is not directory-shaped, so rule 3
     never had a chance at one. See the block above `EXTERNAL_URL`.

Still NOT checked: whether a path the *profile* declares exists. That depends on the
project, and `doctor.py` is the check for it.

    python3 plugins/backend-suite/bin/audit_skill_paths.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGINS = REPO / "plugins"

PLUGIN_PATH = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+)")

# Locations that existed only inside the original app, before extraction.
# Anchored so `mock_api/contracts.json` (a real project file) is not caught by
# the `mock_api/scripts/` rule.
LEGACY = [
    (re.compile(r"\.backend-suite/[A-Za-z0-9_-]+\.(?:py|sh)"),
     "scripts moved out of .backend-suite/ into the plugin's bin/"),
    (re.compile(r"\btoken_pipeline/scripts/"),
     "token_pipeline/scripts/ -> ${CLAUDE_PLUGIN_ROOT}/bin/"),
    (re.compile(r"\bcopy_pipeline/scripts/"),
     "copy_pipeline/scripts/ -> ${CLAUDE_PLUGIN_ROOT}/bin/"),
    (re.compile(r"\bmock_api/scripts/"),
     "mock_api/scripts/ -> ${CLAUDE_PLUGIN_ROOT}/backend_suite/engine/mockapi/"),
    (re.compile(r"(?:^|[^\w/])scripts/audit_[a-z_]+\.py"),
     "top-level scripts/ -> ${CLAUDE_PLUGIN_ROOT}/bin/"),
    (re.compile(r"\btooling/scripts/"),
     "tooling/scripts/ never existed in this plugin"),
    (re.compile(r"\.backend-suite/DOC-ROLES\.md"),
     "DOC-ROLES.md lives at ${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md"),
]

# Project-shaped literals that belong in the profile, not in a portable skill.
#
# Added after /review-docs was found carrying 7 hardcoded Flutter paths and
# /audit-assets 3 hardcoded `assets/images` — in skills that advertise portability.
# A hardcoded project path is a quieter defect than a dead one: it does not error,
# it just silently audits the wrong place (or nothing) on any project shaped
# differently, which is indistinguishable from a clean result.
#
# Doc paths are excluded — those go through {{doc:}} roles and DOC-ROLES.md covers
# them. Angle-bracketed placeholders like <source.root> are the correct form and are
# excluded by the lookbehind.
#
# THE BACKTICK IS NOT IN THE LOOKBEHIND, AND MUST NOT BE PUT BACK.
# ----------------------------------------------------------------
# It used to be — `(?<![\w/`.<])` — which meant a project path written in
# markdown code formatting was invisible to this rule. That is precisely the
# form a skill writes a path in when it is instructing the model to go read or
# create that file, so the exclusion did not narrow the rule to prose, it
# removed the rule's whole subject. Measured when it was found: 37 project-shaped
# paths across 14 skills and agents passing this gate, including eight
# consumer-specific widget classes in /scaffold-screen and eight `mock_api/*`
# paths in /wire-endpoint.
#
# The backtick was almost certainly added alongside `<` to exclude placeholders,
# on the reasoning that a code-formatted path is being *quoted* rather than
# *used*. That reasoning is backwards here: `<source.root>` is a placeholder
# because of what is inside the brackets, not because of the brackets, whereas
# a backtick says nothing at all about whether the path is an instruction. A
# genuinely illustrative path belongs in EXEMPT with a reason, where a reader
# can see it — not hidden from the regex, where nobody can.
PROJECT_PATH = re.compile(
    r"(?<![\w/.<])(lib/[a-z_]+[a-z_/]*|pubspec\.yaml|assets/images"
    r"|token_pipeline/|copy_pipeline/|mock_api/)")

# Consumer project names, which must not appear in the UNIVERSAL plugin.
#
# Added after four skills were found addressing the model as though it were working
# on one specific project — "You are a documentation auditor for the <client>
# mobile project" in a skill installed on two repos and advertised for any. That is a
# quieter defect than a hardcoded path: nothing errors, the skill simply tells the
# model the wrong thing about where it is, and on another project it announces
# itself as auditing someone else's.
#
# Scoped to backend-suite only. house-style is org-scope by definition and its
# client-readiness skill names projects deliberately, as worked examples of a
# filename convention.
#
# The mechanism is derive_names(): when this gate runs inside a consuming
# project, it reads that project's own `project.name` from the profile and checks
# for it. A new consumer is therefore covered the first time the gate runs there,
# with no edit here.
#
# There is deliberately NO static plaintext backstop any more. It used to hold a
# real client's name, which made this file the place the plugin most reliably
# named a client — the coupling it exists to forbid. The backstop for this repo
# is now client_denylist.py: a SALTED-HASH list checked over every tracked file
# in the repository (a strict superset of this rule's scope), run from main()
# below, so a client name reappearing anywhere still fails this gate.
PROJECT_NAMES: tuple[str, ...] = ()

# ---------------------------------------------------------------------------
# Rule 5: project IDENTIFIERS, not just project paths.
# ---------------------------------------------------------------------------
#
# WHAT THIS GATE MISSED, AND WHY IT MISSED IT.
# --------------------------------------------
# /promote-component sat clean through the Phase 1 widening while naming one
# consumer's package (`ds_flutter`), one consumer's GitHub repository, seven of
# its class names, and its framework's analyzer command. It was not exempted and
# it was not unscanned: `PROJECT_PATH`'s alternation is a list of *directory and
# filename shapes*, and none of those literals is path-shaped. The rule never had
# a chance at them. `PROJECT_NAMES` did not fire either — none of them contains
# the project's name.
#
# So the coupling simply had no rule. Same signature as every other defect this
# file catches: nothing errors, the skill tells the model to run a command and
# import symbols that exist in one repository, and on any other project it
# produces confident instructions about components that are not there.
#
# WHAT IS DECIDABLE, AND WHAT IS DELIBERATELY NOT GATED.
# -----------------------------------------------------
# The hard constraint on widening is false positives. `ThemeData` and
# `MediaQuery` appear in these same skills and are FRAMEWORK types — correct,
# portable, and exactly what a skill about a Flutter-adapter project should name.
# A rule that flags a capitalised identifier flags those too, and a gate that
# fires on framework types is a gate somebody switches off, which is strictly
# worse than the blind spot it replaced.
#
# So this rule is deliberately narrow, and narrow in a STRUCTURAL way rather than
# by keeping a denylist of framework types (a denylist is a hand-maintained list
# of an open set — the exact shape this repo keeps regretting):
#
#   5a. A **repository slug** — `<owner>/<repo>` naming a specific GitHub
#       repository. Decidable, because a universal plugin has no business naming
#       any repository but its own.
#
#   5b. A **configured export prefix** — a symbol matching `<Prefix><Capital>…`
#       where `<Prefix>` is the design system's own export prefix, which
#       `audit_reinvented_components.py` ALREADY reads from config rather than
#       hardcoding. `DsStatCell` matches; `ThemeData` and `MediaQuery` cannot,
#       because they do not begin with a configured prefix. That is the control,
#       and it is a property of the rule rather than a list of exceptions.
#
# NOT gated, on purpose, and this is the interesting half:
#
#   * **Domain entity names** (`MeasurementEntry`, `LabMarker`,
#     `LiveChatMessageEntity`). These are indistinguishable IN SHAPE from
#     `ThemeData`. Nothing in the text says which repository owns the symbol, and
#     no regex can decide it. Making them gateable would mean listing them, which
#     is a second copy of a consumer's domain model living in the universal
#     plugin — the disease, sold as the cure.
#
#   * **Framework tool commands** (`flutter analyze`). Adapter-specific rather
#     than project-specific, and the adapter vocabulary lives in the profile;
#     gating it here would require this file to know every adapter's toolchain.
#
#   Both are real coupling and both are FILE defects, fixed in the file by
#   routing them through a doc role or the profile. They are named here rather
#   than left implicit so that the next person to read this knows the gap is
#   measured, not missed — and so that "the gate passes" is never read as "this
#   skill is portable".
#
# WHERE RULE 5 APPLIES, AND THE SECOND THING IT MISSED.
# ------------------------------------------------------
# 5a (repo slug) applies to skill/agent markdown only, for the same reason
# PROJECT_NAMES does: the engine legitimately carries provider modules named
# after what they recognise, and that is a different question from a skill
# telling the model it is working on somebody else's repository.
#
# 5b/5c (export prefix and package) now ALSO apply to the plugin's own Python
# code literals — `identifiers_in_code()` below. They did not, and the cost was
# measured: `audit_reinvented_components.py` compiled one consumer's package
# name straight into a regex literal,
#
#     DS_IMPORT = re.compile(r"^import\s+['\"]package:<one consumer>/", re.M)
#
# and `audit_promotion_candidates.py` carried the same name twice more. Both sat
# clean through every gate in this file.
#
# It is worth being exact about WHY, because the obvious explanation is wrong.
# The gate could see the string. `code_literals()` walks the AST and yields every
# non-docstring `ast.Constant`, and a regex is an ordinary string argument to
# `re.compile` — it is yielded like any other. `EXPORT_PACKAGE` matches the text
# unchanged. Nothing about the regex hid it.
#
# What was missing was the RULE, not the visibility. The source-file loop applied
# exactly one pattern to code literals — `PROJECT_PATH`, a list of directory and
# filename shapes — and a bare package name is not path-shaped, so it matched
# nothing. Rule 5 was scoped to markdown by a comment that said the engine
# legitimately names things, which is true of an adapter module and of a
# provider's API host, and is not true of `bin/`. The blind spot was the file
# set, the same way it was when `sources()` was added.
#
# Widening is cheap here for a measurable reason rather than a hoped-for one:
# run over the whole plugin at the moment it was added, 5b and 5c produced
# exactly two hits, both of them this defect in the sibling audit, and zero
# false positives. `adapters/`, `*_test.py` and `verify_seams_*` stay excluded
# for the reasons in `code_literals()`, docstrings and comments never reach the
# AST, and the structural control on 5b still holds — `ThemeData` cannot match a
# rule anchored on a configured export prefix.

# `<owner>/<repo>`, only where the text is already asserting a repository:
# inside a GitHub URL, or as a backticked slug. Requiring one of those two
# frames is what keeps this off ordinary prose like "read/write" and off every
# relative path in the file.
REPO_SLUG = re.compile(
    r"(?:github\.com/|`)([A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*)`?")

# A dot in either segment makes `a/b` a FILE path, not a repository slug —
# measured: `docs/api-reference.html` in /wire-endpoint was this rule's first
# false positive, and enumerating file extensions to exclude would have been a
# hand-maintained list of an open set. A repository name may legally contain a
# dot; missing those is a named, deliberate cost of a rule that stays quiet.
SLUG_NOT_REPO = re.compile(r"\.")

# Owners a universal plugin may name: its own, and nobody else's.
#
# Static backstop, same construction and same justification as PROJECT_NAMES —
# this repository has no consumer profile of its own, so a gate that could only
# derive would check nothing in its own CI. The derived half reads
# `tokens.ownedBy` from whatever project the gate is run against.
ALLOWED_OWNERS = ("anthropics", "irfan-dahir")  # irfan-dahir: this suite's own org; added when skills began citing this repo's slug (Phase C)

# Design-system export prefixes. `audit_reinvented_components.py` reads this from
# the project's own audit config (`reinventedComponents.exportPrefix`) and
# defaults to the same value for the same stated reason: it is this ecosystem's
# convention, not an assumption about a particular repository.
EXPORT_PREFIX_DEFAULT = "Ds"
EXPORT_PREFIX = re.compile(r"\b(" + EXPORT_PREFIX_DEFAULT + r"[A-Z][A-Za-z0-9]{2,})\b")

# 5c. The PACKAGE spelling of the same prefix. A design system that exports
# `DsThing` ships as `ds_<something>`, so the package literal is derived from the
# prefix rather than being a second constant naming a specific package — one
# fact, one source. Requires the underscore: `ds` alone is two letters of English.
EXPORT_PACKAGE = re.compile(
    r"\b(" + EXPORT_PREFIX_DEFAULT.lower() + r"_[a-z][a-z0-9_]{2,})\b")

# An identifier is allowed when the sentence exists to forbid or retract it, same
# construction as NAME_EXEMPT and EXEMPT. Keyed by (basename, matched text).
IDENT_EXEMPT: list[tuple[str, str, str]] = []


# ---------------------------------------------------------------------------
# Rule 6: an absolute URL hardcoded in the universal plugin.
# ---------------------------------------------------------------------------
#
# WHAT THIS GATE MISSED, AND WHY IT MISSED IT.
# --------------------------------------------
# `generate_openapi.py` shipped one consumer's mock server as a server-table
# entry — `https://<uuid>.mock.pstmn.io` — and sat clean through every rule in
# this file. The cause is exactly the one the rule-5 block above already names
# for `ds_flutter`, in a different costume: `PROJECT_PATH` is an alternation of
# DIRECTORY AND FILENAME shapes, and a URL is not directory-shaped. The rule
# never had a chance at it. `PROJECT_NAMES` did not fire either — the host is a
# UUID, so it does not contain the project's name anywhere.
#
# A consumer's service endpoint is a project literal by definition: it is the one
# fact in the file that is true of exactly one engagement. Same signature as
# every other defect here — nothing errors, the generated OpenAPI just points
# every other consumer at somebody else's mock server, which reads as a clean
# generation.
#
# WHY AN ALLOW-LIST, WHEN THIS REPO KEEPS REGRETTING LISTS.
# --------------------------------------------------------
# The rule-5 block warns off "a hand-maintained list of an open set". That
# warning is about DENY-lists, and the direction is the whole point: a deny-list
# of framework types fails OPEN — the entry nobody added is a defect that ships.
# An allow-list of hosts fails CLOSED — the entry nobody added is a gate firing
# on a legitimate URL, which is noisy but visible, and is fixed by adding a line
# with a reason next to it. That is the same construction, and the same
# justification, as `ALLOWED_OWNERS` and `PROJECT_NAMES` already in this file.
#
# MEASURED BEFORE SHIPPING, over the whole plugin, at the moment it was added:
#
#   code literals (the file set `scans_project_paths()` already defines)
#     · raw.githubusercontent.com  — Homebrew's own bootstrap URL, in the asset
#       pipeline's "you need brew" message.                     allowed, correct
#     · www.w3.org                 — the SVG XML namespace. A namespace URI is an
#       identifier, never fetched.                              allowed, correct
#     · <uuid>.mock.pstmn.io       — THE DEFECT.                       flagged ✓
#   markdown (commands/ + agents/)
#     · 127.0.0.1                  — a loopback review server. Loopback is
#       structurally incapable of being a consumer's endpoint.  allowed, correct
#     · github.com, brew.sh        — this repo's own, and an install pointer.
#                                                               allowed, correct
#
#   1 finding, 1 true positive, 0 false positives. Test files carry four more
#   (`example.test`, `example.invalid`, `x.test`) and are excluded by the file
#   set, not by a URL exemption — a fixture has to be shaped like the thing it
#   stands in for, same reasoning as `code_literals()`.
#
# NOT gated, on purpose:
#
#   * **The owner segment of an allowed host's URL.** `github.com/<someone>/…`
#     is checked by rule 5a, which owns that question and already reads
#     `ALLOWED_OWNERS`. Re-deciding it here would be two rules holding one fact.
#     5a is markdown-only, so a consumer's GitHub URL in CODE is a named gap.
#   * **Schema `$id` URLs**, because `sources()` yields only `.py` and `.sh` —
#     `templates/*.schema.json` is not scanned at all, and their `$id`s are this
#     repo's own in any case.
#   * **`docs/backend-suite-guide.html`** and its `fonts.googleapis.com` /
#     `cdnjs` tags, for the same reason: it is not under `plugins/`, so no rule
#     in this file reaches it.
EXTERNAL_URL = re.compile(r"\bhttps?://([A-Za-z0-9][A-Za-z0-9.:-]*)")

# Hosts the UNIVERSAL plugin may name. Each entry matches the host exactly, or
# any subdomain of it. Keep the reason next to the entry: an allow-list whose
# entries nobody can justify is how a real endpoint gets waved through.
ALLOWED_HOSTS: list[tuple[str, str]] = [
    ("github.com", "this repository's own forge; the OWNER is rule 5a's job"),
    ("githubusercontent.com", "raw.githubusercontent.com — Homebrew's bootstrap"),
    ("w3.org", "XML/SVG namespace URIs: identifiers, never fetched"),
    ("json-schema.org", "JSON Schema meta-schema URIs: identifiers, never fetched"),
    ("docs.oasis-open.org", "the SARIF 2.1.0 schema's own $schema/id URI: an identifier, never fetched"),
    ("brew.sh", "Homebrew's install page, named in a dependency-missing message"),
    ("pre-commit.com", "the pre-commit framework's own docs"),
    ("designtokens.org", "the W3C DTCG format spec the DTCG export/import cite; a standard, never a consumer endpoint"),
    ("localhost", "loopback cannot be a consumer's endpoint"),
    ("127.0.0.1", "loopback cannot be a consumer's endpoint"),
]


def host_allowed(host: str) -> bool:
    host = host.split(":")[0].rstrip(".").lower()
    for entry, _ in ALLOWED_HOSTS:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def external_urls(text: str, basename: str) -> list[tuple[str, str]]:
    """(matched host, why it is a project literal) — rule 6 over one chunk."""
    hits: list[tuple[str, str]] = []
    seen = set()
    for m in EXTERNAL_URL.finditer(text):
        host = m.group(1).rstrip(".,;:)/").lower()
        if host_allowed(host) or host in seen:
            continue
        if ident_exempt(basename, host):
            continue
        seen.add(host)
        hits.append((host, "is a hardcoded external host. A consumer's service "
                           "endpoint is a project literal — read it from the "
                           "profile, or make it a required argument. If it is "
                           "genuinely universal, add it to ALLOWED_HOSTS with a "
                           "reason"))
    return hits


def names_in_code(literal: str, basename: str,
                  project_names: set[str]) -> list[str]:
    """Rule 4 over ONE code literal.

    This used to be markdown-only, and `main()` carried a comment saying why:
    "the engine has provider modules and fixture data named after what they came
    from, and that is a separate question from a skill addressing the model as
    though it were working on somebody else's repo."

    That is still true, and it is not a reason to skip code — it is a reason to
    skip PROSE, which `code_literals()` already does by construction. Measured
    when this was widened, the three surviving occurrences of the static backstop
    name in the universal plugin's Python were all in a docstring or a comment
    (`presets.py`'s "no <client> specifics", `dart.py`'s and
    `audit_layer_boundaries.py`'s records of a hardcoding that was removed) —
    sentences that exist to FORBID the coupling, the same shape as `NAME_EXEMPT`.
    None reaches the AST. The one code literal that matched was a real defect:
    a consumer's product name baked into a generated OpenAPI document's title,
    emitted into every consumer's API reference.
    """
    low = literal.lower()
    return [n for n in sorted(project_names) if n in low]


def derive_names() -> tuple[set[str], str]:
    """(names to check, where they came from).

    The plugin cannot know who installs it. It CAN know the project it is currently
    running against, which is enough: `project.name` in that project's profile.

    Only the FIRST token is used. `acme-mobile` and `acme-portal` both yield
    `acme` — the product, not the surface. Taking every token would add `mobile`
    and `portal`, which are ordinary English words that appear legitimately in a
    skill about mobile layouts or a staff portal, and a gate that fires on those
    gets switched off.
    """
    names = set(PROJECT_NAMES)
    source = "no consumer profile; client names covered by client_denylist.py"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _bootstrap import project_root  # noqa: E402
        profile = Path(project_root()) / ".backend-suite" / "profile.json"
        if profile.is_file():
            import json
            declared = (json.loads(profile.read_text())
                        .get("project", {}) or {}).get("name", "")
            stem = re.split(r"[-_]", declared.strip().lower())[0]
            if len(stem) >= 4:
                names.add(stem)
                source = f"{declared!r} from the project profile"
    except SystemExit:
        # project_root() exits when there is no consumer — which is the normal case
        # in this repo's own CI, not an error.
        pass
    return names, source
UNIVERSAL_PLUGIN = "backend-suite"

# A project name is allowed when the sentence exists to forbid the coupling.
NAME_EXEMPT: list[tuple[str, str]] = []

# A trailing `.` or `,` swept up from prose, e.g. "see bin/resolve.py."
TRAILING = ".,;:)"

# Exemptions. Every entry needs a reason, and passing runs print them, because an
# exemption nobody can see is how a real finding gets suppressed for years.
# Keyed by (file basename, substring of the matched text).
EXEMPT: list[tuple[str, str, str]] = [
    ("audit-contrast.md", "tooling/scripts/",
     "/audit-contrast is a ↗️ pointer skill: the command is correct, but it runs "
     "in the design-system repo, where that path is real. Rewriting it to "
     "${CLAUDE_PLUGIN_ROOT} would point at a script this plugin does not have."),
    ("generate-client-readiness.md", "scripts/audit_adapter_pattern.py",
     "Illustrative prose, not an invocation — it lists internal tool names as "
     "examples of what must be stripped out of a client-facing document."),

    # PROVENANCE. Each of these says where code came FROM, before extraction.
    # Rewriting them to the current location would make the sentence false: the
    # point is naming the origin, and "lifted verbatim from ${CLAUDE_PLUGIN_ROOT}/
    # bin/audit_tokens.py" would claim this code was lifted from itself. Kept as
    # named exemptions rather than a blanket "ignore anything near the word
    # ported", which would be a loophole wide enough to hide a real invocation in.
    ("dart.py", "token_pipeline/scripts/",
     "Provenance: records that these regexes were lifted verbatim from the "
     "pre-extraction audit_tokens.py. Naming the old location is the point."),
    ("audit_copy.py", "tooling/scripts/",
     "Provenance: the rules came from the design-system repo's own audit_copy.py, "
     "which is where that path is real."),
    ("copy.py", "tooling/scripts/",
     "Provenance: same origin as audit_copy.py's rules, folded into the engine."),
    ("audit_api_consistency.py", "tooling/scripts/",
     "Provenance: ported from the design-system repo, where that path is real."),
    ("audit_error_handling.py", "scripts/audit_error_handling.py",
     "Provenance: ported from the mobile app's own scripts/, pre-extraction."),
    ("mock_api_reminders.py", "mock_api/scripts/",
     "Provenance: the comment explains the bug where this hook pointed at the "
     "project's pre-port script location. Quoting the wrong path is the record."),
    ("doctor.py", "token_pipeline/scripts/",
     "Worked example of this tool's own output — a table of config files and the "
     "script pointers they were found naming, not a pointer doctor.py follows."),
    ("doctor.py", ".backend-suite/doctor.py",
     "Same worked-example table as above."),

    # PROJECT_PATH in code. Added with the Python scan (see code_literals) — these
    # are the ones that survived triage, not a blanket amnesty for the engine.
    ("doctor.py", "mock_api/",
     "doctor.py's own rule definition: the literal is one alternative inside a "
     "regex whose whole job is recognising pre-extraction script locations. "
     "Rewriting it to come from the profile would stop it matching the wrong "
     "paths it exists to find — the same reason this file skips itself."),
    ("survey.py", "pubspec.yaml",
     "Bootstrap detection, which cannot read the profile it is being run to "
     "write. survey.py's manifest table maps a root manifest filename to the "
     "language it implies, so that a project with no profile yet can be "
     "surveyed at all. The name is an input to the detection, not an assumption "
     "about where this project keeps things."),
    ("audit_promotion_candidates.py", "lib/src/components",
     "Not this project's layout: `lib/src/` is pub's own convention for "
     "package-internal Dart code, and the path is joined onto a DEPENDENCY root "
     "resolved from .dart_tool/package_config.json, not onto the consumer repo. "
     "It is still language knowledge sitting in bin/ rather than in "
     "backend_suite/adapters/ where CLAUDE.md's table puts it — that is a real "
     "and separate defect, tracked as the Dart-only-audits-in-bin cluster, and "
     "this exemption is scoped to the path literal so it expires when that moves."),
    ("audit_reinvented_components.py", "lib/src/components",
     "Same dependency-package path as audit_promotion_candidates.py, for the "
     "same reason and with the same expiry."),
    ("design-auditor.md", "lib/app/theme/app_theme",
     "The sentence exists to say the path is GONE — \"…and a components.dart "
     "barrel, neither of which still exists\". Replacing it with a profile "
     "placeholder would make the warning unreadable: the reader needs the old "
     "name to recognise the stale instruction being retracted."),
]
# The four KNOWN BROKEN entries that sat here — house-style's two skills unable to
# reach backend-suite's resolver — are gone because the cause is gone, not because
# the exemption was widened. house-style now ships bin/resolve_role.py. If you are
# tempted to add a KNOWN BROKEN entry back, note that these lasted exactly one
# commit, which is the intended lifetime.


def exempt(basename: str, matched: str) -> str | None:
    for f, needle, reason in EXEMPT:
        if f == basename and needle in matched:
            return reason
    return None


def ident_exempt(basename: str, matched: str) -> str | None:
    for f, needle, reason in IDENT_EXEMPT:
        if f == basename and needle == matched:
            return reason
    return None


def derive_owners() -> set[str]:
    """Repository owners this plugin may name.

    The static `ALLOWED_OWNERS` plus, when the gate is running inside a consuming
    project, nothing at all — a consumer's own `tokens.ownedBy` is precisely the
    repository the universal plugin must not name, so it is read to be FORBIDDEN,
    not allowed. There is no derived allowance here on purpose: widening the
    allow-list from the environment is how a gate stops gating.
    """
    return set(ALLOWED_OWNERS)


def project_identifiers(text: str, basename: str) -> list[tuple[str, str]]:
    """(matched identifier, why it is a project literal) for one markdown file.

    Rule 5 — see the block above REPO_SLUG for what is in scope, what is
    structurally excluded, and which real coupling is deliberately left ungated.
    """
    hits: list[tuple[str, str]] = []
    owners = derive_owners()

    for m in REPO_SLUG.finditer(text):
        slug = m.group(1)
        owner, _, repo = slug.partition("/")
        if owner.lower() in owners:
            continue
        if SLUG_NOT_REPO.search(repo) or "." in owner:
            continue
        if "-" not in owner and "-" not in repo:
            # Both segments plain single words: overwhelmingly a relative path
            # (`bin/resolve`, `commands/audit`). Requiring a hyphen somewhere is
            # what keeps this rule off ordinary prose, at the known cost of
            # missing a hyphen-free repository name. A named miss beats noise.
            continue
        hits.append((slug, "names a specific repository — a universal plugin has "
                           "no business naming one. Use a doc role, or read it "
                           "from the profile"))

    for pattern, why in (
        (EXPORT_PREFIX, "is a design-system export symbol from one project's "
                        "component namespace. Name the role or the capability, "
                        "not the class"),
        (EXPORT_PACKAGE, "is one project's package name. Read it from the "
                         "project's own config"),
    ):
        for m in pattern.finditer(text):
            hit = m.group(1)
            if ident_exempt(basename, hit):
                continue
            hits.append((hit, why))

    # De-duplicated: a class named eight times is one defect, and eight identical
    # lines is how a reader learns to skim past this gate's output.
    seen, unique = set(), []
    for hit, why in hits:
        if hit in seen:
            continue
        seen.add(hit)
        unique.append((hit, why))
    return unique


def identifiers_in_code(text: str, basename: str) -> list[tuple[str, str]]:
    """Rules 5b/5c over ONE code literal — see the block above `sources()`.

    Deliberately not 5a: a repository slug is a `<owner>/<repo>` shape, and in
    Python source that shape is overwhelmingly a relative path. The two rules
    that carry a structural control (a configured export prefix, and the package
    spelling derived from it) are the two that widen safely.
    """
    hits: list[tuple[str, str]] = []
    for pattern, why in (
        (EXPORT_PREFIX, "is a design-system export symbol from one project's "
                        "component namespace. Read the prefix from the project's "
                        "config (reinventedComponents.exportPrefix)"),
        (EXPORT_PACKAGE, "is one project's package name. Read it from the "
                         "project's own config or from the audit's "
                         "own rules section"),
    ):
        for m in pattern.finditer(text):
            hit = m.group(1)
            if ident_exempt(basename, hit):
                continue
            if any(hit == seen for seen, _ in hits):
                # One literal naming the package twice — `"package:X/X.dart"` —
                # is one defect. De-duplicated for the same reason
                # `project_identifiers` does it: repeated identical lines are
                # how a reader learns to skim past this gate's output.
                continue
            hits.append((hit, why))
    return hits


def sources(plugin_dir: Path):
    """The plugin's own executable source — the half this gate could not see.

    Every pre-extraction path this file knows how to recognise also occurs in
    docstrings, usage lines, shell comments, and user-facing message strings, and
    scanning only `commands/`+`agents/` markdown missed all of them. When that
    blind spot was measured it was hiding 25 stale references across 15 files,
    including copy-pasteable invocations and one written into the header of a
    generated Dart file, so it propagated. The LEGACY patterns matched them
    unchanged — the file set was the defect, not the patterns.
    """
    for sub in ("bin", "hooks", "backend_suite"):
        root = plugin_dir / sub
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in (".py", ".sh") or "__pycache__" in path.parts:
                continue
            # This file is skipped, and it has to be: LEGACY below *is* a list of
            # those paths as literal strings, and every EXEMPT reason quotes one.
            # A linter that reports its own rule definitions produces eleven
            # findings that can never be fixed, which is how a gate gets muted.
            if path.name == Path(__file__).name:
                continue
            yield path


def code_literals(path: Path):
    """(line, string) for every string literal in *executable* Python.

    WHY PYTHON IS IN SCOPE AT ALL.
    ------------------------------
    Rule 3 was written as a rule about skills, so it only ever ran over
    `commands/` and `agents/` markdown. But the engine is shipped in the same
    universal plugin and is read by nothing that would notice, and that is where
    the hardcoding actually accumulated — as `argparse` defaults. A `--out`
    default of one project's pipeline directory is the same defect as a skill
    naming `lib/`, with the same signature: nothing errors, the audit writes its
    findings into a directory the project has never heard of, the baseline diff
    compares it against nothing, and the run reads exactly like a clean one.
    Measured when this was added: seven live defaults across five engines, none
    of them visible to any gate.

    WHY ONLY LITERALS, AND ONLY SOME FILES.
    ---------------------------------------
    Scanning the raw text of every `.py` file reports 181 hits, of which the
    overwhelming majority are prose: docstrings explaining a Flutter convention,
    comments recording where code was ported from, and test fixtures. A gate at
    that signal-to-noise ratio gets switched off, which is worse than the blind
    spot it replaced. So:

      - docstrings are excluded — they are prose, and the *provenance* case
        (naming a pre-extraction path on purpose) is already handled by LEGACY
        plus its named EXEMPT entries;
      - comments never reach the AST at all, for the same reason;
      - `adapters/` is excluded, because CLAUDE.md's table names
        `backend_suite/adapters/` as the sanctioned home for exactly this kind of
        language- and framework-specific knowledge. A path literal there is the
        adapter doing its job; a path literal in `bin/` or `engine/` is the
        leak;
      - `*_test.py` and `verify_seams_*.py` are excluded, because a fixture has
        to be shaped like the project it stands in for. A test that builds
        `lib/features/thing/thing_adapter.dart` in a tmpdir is not telling
        anybody where a real project keeps its code.

    `.sh` files are not covered: there is no AST to separate a comment from a
    command, and the shell scripts here are wrappers whose paths LEGACY already
    covers. That is a known, named gap rather than a silent one.
    """
    import ast
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docs):
            yield node.lineno, node.value


def scans_project_paths(path: Path) -> bool:
    """Whether PROJECT_PATH applies to this source file — see code_literals."""
    if path.suffix != ".py":
        return False
    parts = path.parts
    if "adapters" in parts:
        return False
    return not (path.name.endswith("_test.py")
                or path.name.startswith("verify_seams"))


def main() -> int:
    problems: list[str] = []
    allowed: list[str] = []
    checked = 0
    project_names, names_source = derive_names()

    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        # Source files get the two checks that are about *this plugin's* own
        # layout, plus PROJECT_PATH over their code literals — see code_literals()
        # for why that is narrower than a text sweep and why it is in scope now.
        #
        # This block used to skip PROJECT_PATH entirely, on the grounds that "an
        # engine resolves real project paths as its job (`REPO / "mock_api" /
        # "contracts.json"`)". That reasoning holds for the *shape* of the work
        # and not for the *directory name*: an engine has to resolve a project
        # path, and it should resolve it out of the profile. The example the old
        # comment used to justify the skip was itself the bug — that exact line
        # is why the mock-API hook was a no-op on any project that kept its mock
        # API somewhere other than `mock_api/`.
        #
        # PROJECT_NAMES still does not apply to source: the engine has provider
        # modules and fixture data named after what they came from, and that is a
        # separate question from a skill addressing the model as though it were
        # working on somebody else's repo.
        for f in sources(plugin_dir):
            text = f.read_text()
            rel = f.relative_to(REPO)

            for m in PLUGIN_PATH.finditer(text):
                target = m.group(1).rstrip(TRAILING)
                checked += 1
                if not (plugin_dir / target).exists():
                    problems.append(
                        f"{rel}: ${{CLAUDE_PLUGIN_ROOT}}/{target} does not exist "
                        f"in {plugin_dir.name}/")

            for pat, why in LEGACY:
                for m in pat.finditer(text):
                    hit = m.group(0).strip()
                    reason = exempt(f.name, hit)
                    if reason:
                        allowed.append(f"{rel}: {hit} — {reason}")
                        continue
                    problems.append(
                        f"{rel}: {hit!r} is a pre-extraction path — {why}")

            if not scans_project_paths(f):
                continue
            for lineno, literal in code_literals(f):
                for m in PROJECT_PATH.finditer(literal):
                    hit = m.group(1)
                    reason = exempt(f.name, hit)
                    if reason:
                        allowed.append(f"{rel}:{lineno}: {hit} — {reason}")
                        continue
                    problems.append(
                        f"{rel}:{lineno}: hardcoded project path {hit!r} in code — "
                        f"read it from the profile instead (backend_suite.project."
                        f"profile / engine.pipelines), or make it a required argument")

                if plugin_dir.name != UNIVERSAL_PLUGIN:
                    continue
                for hit, why in identifiers_in_code(literal, f.name):
                    reason = ident_exempt(f.name, hit)
                    if reason:
                        allowed.append(f"{rel}:{lineno}: {hit} — {reason}")
                        continue
                    problems.append(f"{rel}:{lineno}: {hit!r} {why}")

                # Rule 6, and rule 4 widened to code — see external_urls() and
                # names_in_code() for what each was measured to flag.
                for hit, why in external_urls(literal, f.name):
                    problems.append(f"{rel}:{lineno}: {hit!r} {why}")

                for name in names_in_code(literal, f.name, project_names):
                    reason = next((r for fn, r in NAME_EXEMPT if fn == f.name), None)
                    if reason:
                        allowed.append(f"{rel}:{lineno}: {name!r} — {reason}")
                        continue
                    problems.append(
                        f"{rel}:{lineno}: code literal names the consumer project "
                        f"{name!r}. This plugin ships to more than one repo — read "
                        f"it from the profile (project.name), or take it as an "
                        f"argument")

        for sub in ("commands", "agents"):
            for f in sorted((plugin_dir / sub).glob("*.md")):
                text = f.read_text()
                rel = f.relative_to(REPO)

                for m in PLUGIN_PATH.finditer(text):
                    target = m.group(1).rstrip(TRAILING)
                    checked += 1
                    if not (plugin_dir / target).exists():
                        problems.append(
                            f"{rel}: ${{CLAUDE_PLUGIN_ROOT}}/{target} does not exist "
                            f"in {plugin_dir.name}/")

                for m in PROJECT_PATH.finditer(text):
                    hit = m.group(1)
                    reason = exempt(f.name, hit)
                    if reason:
                        allowed.append(f"{rel}: {hit} — {reason}")
                        continue
                    problems.append(
                        f"{rel}: hardcoded project path {hit!r} — read it from the "
                        f"profile instead (resolve.py --profile source.<key>), or use "
                        f"an <angle-bracketed> placeholder in prose")

                if plugin_dir.name == UNIVERSAL_PLUGIN:
                    for hit, why in external_urls(text, f.name):
                        problems.append(f"{rel}: {hit!r} {why}")

                    for hit, why in project_identifiers(text, f.name):
                        reason = ident_exempt(f.name, hit)
                        if reason:
                            allowed.append(f"{rel}: {hit} — {reason}")
                            continue
                        problems.append(f"{rel}: {hit!r} {why}")

                    low = text.lower()
                    for name in project_names:
                        if name not in low:
                            continue
                        reason = next((r for fn, r in NAME_EXEMPT if fn == f.name), None)
                        if reason:
                            allowed.append(f"{rel}: {name!r} — {reason}")
                            continue
                        problems.append(
                            f"{rel}: names the consumer project {name!r}. This plugin "
                            f"is installed on more than one repo — say \"this project\" "
                            f"or read the value from the profile")

                for pat, why in LEGACY:
                    for m in pat.finditer(text):
                        hit = m.group(0).strip()
                        reason = exempt(f.name, hit)
                        if reason:
                            allowed.append(f"{rel}: {hit} — {reason}")
                            continue
                        problems.append(
                            f"{rel}: {hit!r} is a pre-extraction path — {why}")

    if allowed:
        print(f"skill paths: {len(allowed)} exemption(s) in force:")
        for a in allowed:
            print(f"  · {a}")
        print()

    # Repo-wide client-name denylist (hashed). Runs last so its INERT refusal
    # cannot hide findings above; see client_denylist.py for why it is hashed.
    import client_denylist
    deny_problems, deny_status = client_denylist.check(REPO)
    problems.extend(deny_problems)

    if problems:
        print("skill paths: dead or legacy references\n", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s). A skill that names a path which does not "
              "exist fails at run time, in a plugin that otherwise validates clean.",
              file=sys.stderr)
        return 1

    print(f"skill paths: {checked} plugin-relative reference(s) all resolve. "
          f"No unexplained pre-extraction paths ({len(allowed)} exempted above).")
    print(f"  project names checked: {', '.join(sorted(project_names)) or '(none)'} "
          f"({names_source})")
    print(f"  {deny_status}")
    if deny_status.startswith("INERT"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
