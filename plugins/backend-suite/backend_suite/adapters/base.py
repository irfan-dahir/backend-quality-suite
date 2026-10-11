"""The language-adapter contract.

A scanner in `backend_suite/engine/` knows *how to sweep a codebase and report
findings*. It must not know what language that codebase is written in. Everything
language-shaped — what a hardcoded colour looks like, how code references a
design token, which files are source — lives in an adapter here.

This split is the point of the whole extraction: `audit_tokens.py` used to hold
`Color(0x...)`, `EdgeInsets.all(`, `AppTokens.` and `Curves.` as module-level
regexes, so it could only ever audit a Flutter project. The regexes have not
changed; they moved.

## Writing an adapter

Expose two things:

    NAME = "php"

    def checks(ctx: AdapterContext) -> list[Check]: ...

and optionally:

    def token_names(ctx: AdapterContext) -> set[str] | None
        The design-token names this project actually defines, so the audit can
        verify its own config lists them all. Return None when the language has
        no way to enumerate them — None means "cannot tell", which the caller
        must treat differently from an empty set meaning "there are none".

`FILE_GLOBS` defaults to the profile's `source.fileGlob` and only needs
overriding when a language has several relevant extensions.

## Why checks are declarative

Each `Check` is a regex plus an optional predicate. Keeping them data rather than
methods means the engine can report *which* check fired, count them, and let a
project disable one by category — none of which works if each adapter hand-rolls
its own scan loop. It also keeps an adapter honest: if a rule cannot be expressed
as "find this, then decide", it probably belongs in the engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional


class CapabilityError(RuntimeError):
    """An adapter was asked for something it cannot answer for this stack.

    The distinction this type exists to preserve: "no, there are none" and "I
    have no way to tell" are different answers, and collapsing them into a falsy
    return is how a report ends up saying "clean" about a check that never ran.

    Raise it — never return False or an empty collection — when the concept
    genuinely does not apply. `is_registered()` on a bundler-driven web project
    is the canonical case: there is no registry to consult, so False would
    manufacture a permanent false finding and True would hide every real one.
    """

    def __init__(self, capability: str, adapter: str, why: str):
        super().__init__(
            f"{adapter} cannot answer {capability!r}: {why}\n"
            f"This is a refusal, not a finding of zero. Fix the profile, pick a "
            f"different adapter, or implement the capability."
        )
        self.capability = capability
        self.adapter = adapter
        self.why = why


@dataclass(frozen=True)
class Capability:
    """A thing a project may *do* that some profile field is supposed to point at.

    The pairing is the point. A capability on its own is a fact about the code;
    a profile field on its own is a fact about the config. Only the pair makes
    the reflexion model's **absence** verdict expressible — the code routes,
    and nothing in the config says where, so every check keyed on that field
    runs against nothing and reports clean.

    `profile_field` is a dotted path into `profile.json` and belongs to the
    adapter, not the engine: which field answers "where are the routes declared"
    is a fact about how this stack is described, and an engine that named the
    field would be naming a literal it has no business knowing.
    """
    name: str
    profile_field: str
    why: str


@dataclass(frozen=True)
class CapabilityEvidence:
    """What the adapter actually found. Never used to mean "I could not tell".

    There is deliberately no "unknown" member: the only way to say that is to
    raise `CapabilityError`. A tri-state here would be one more value callers
    could forget to branch on, and forgetting it reads as absent — the exact
    silence this type exists to prevent.
    """
    present: bool
    files: tuple
    why: str


class LanguageCapabilityProtocol:
    """The optional half of a language adapter: capability detection.

      capabilities(ctx) -> list[Capability]
          What this adapter is able to look for at all. An adapter that
          implements none omits the function; the engine then reports the
          project as unexamined for capabilities rather than reporting nothing.

      detect_capability(ctx, name) -> CapabilityEvidence
          Whether the project does it, with the files that say so. MUST raise
          `CapabilityError` when the adapter cannot reach an answer — no source
          to read, an unreadable tree, a capability whose signature this stack
          does not express. Returning `CapabilityEvidence(present=False, ...)`
          for "I don't know" rebuilds the silence one layer down: absent and
          undetermined would then reach the engine as the same value, and the
          engine cannot recover a distinction the adapter threw away.
    """


@dataclass(frozen=True)
class AdapterContext:
    """What an adapter is allowed to know about the project.

    Deliberately narrow. An adapter that reaches for anything beyond this is
    reintroducing the coupling this interface exists to remove.
    """
    repo: "object"                      # pathlib.Path to the repo root
    profile: dict                       # .backend-suite/profile.json
    exceptions: dict                    # .backend-suite/exceptions.json
    token_accessor: str = ""            # e.g. "AppTokens" — how code names a token
    audit_config: dict = field(default_factory=dict)  # the design-audit rules file

    def minimums(self) -> dict:
        """Accessibility thresholds from the audit config.

        These live in config for a reason worth stating: the accessibility
        scanner used to hardcode `< 14` and `< 48` while the config *also*
        declared min_text_sp 14 and min_touch_target_dp 48. They agreed, but
        nothing made them agree — a project raising its minimum in config would
        have got a scanner that silently kept enforcing the old one.
        """
        raw = dict(self.audit_config.get("accessibility_minimums", {}) or {})
        # Templates scaffolded before the rename wrote camelCase keys that
        # nothing read — a configured minimum silently became "not set". Accept
        # them, loudly, so those projects keep working until they migrate.
        for old, new in DEPRECATED_MINIMUM_KEYS.items():
            if old in raw:
                import sys
                print(f"warning: accessibility_minimums.{old} is deprecated — rename it "
                      f"to {new} in the audit config", file=sys.stderr)
                if new not in raw:
                    raw[new] = raw[old]
                del raw[old]
        return raw


DEPRECATED_MINIMUM_KEYS = {
    "minTextSizeSp": "min_text_sp",
    "minTouchTargetDp": "min_touch_target_dp",
}


def numeric_minimum(minimums: dict, key: str) -> tuple[Optional[float], Optional[str]]:
    """(value, None), (None, None) when unset, or (None, reason) when unusable.

    An unedited scaffold leaves "TODO or delete, e.g. 14" here. That must be a
    named refusal, never a float() crash and never a guessed number.
    """
    value = minimums.get(key)
    if value is None:
        return None, None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, (f"accessibility_minimums.{key} is {value!r}, not a number — "
                      "replace the scaffold placeholder with a number, or delete the key")
    return float(value), None


@dataclass
class CheckSet:
    """Checks an adapter could build, plus the ones it could not.

    `omitted` exists so a missing threshold cannot quietly reduce coverage. A
    scanner that drops a check because config was incomplete, and still prints
    "0 findings", is the exact failure this suite keeps guarding against.
    """
    checks: list
    omitted: list = field(default_factory=list)

    def __iter__(self):
        return iter(self.checks)

    def __len__(self):
        return len(self.checks)


@dataclass(frozen=True)
class Check:
    """One violation pattern.

    kind      stable identifier that appears in findings and in the baseline, so
              renaming one is a visible change rather than a silent reshuffle
    pattern   compiled regex swept over the whole file, not line by line, so a
              check can look at surrounding context (a Duration preceded by
              `.delayed(` is a mock delay, not an animation)
    accept    optional (match, source) -> bool. True means "this is a real
              violation". Absent means every match counts. Defaults to accepting
              so a malformed adapter over-reports rather than silently passing —
              a noisy audit gets fixed, a silent one does not.
    category  optional exceptions bucket. A check tagged "color" honours
              exceptions.json's color.allowlistFiles; an untagged check ignores
              allowlists entirely.
    """
    kind: str
    pattern: re.Pattern
    accept: Optional[Callable[[re.Match, str], bool]] = None
    category: Optional[str] = None
    tags: tuple = field(default_factory=tuple)
    # What the finding shows a human. Defaults to the matched text, which is right
    # for a literal ("Color(0xFF123456)") and useless for an *absence* — matching
    # "IconButton(" tells a reader nothing about the missing tooltip. Set a string
    # for those, or a callable for something computed.
    snippet: Optional[object] = None
    # Cap on the matched text, for patterns that can span a lot of source.
    snippet_limit: Optional[int] = None
    # File suffixes this check applies to; empty means every file the adapter
    # globs. Exists for adapters spanning several syntaxes (a `.css` file and a
    # `.tsx` file both hold `padding: 13px`, and only one of them is a JS object),
    # so the engine can skip by path without learning what any suffix means.
    suffixes: tuple = field(default_factory=tuple)

    def applies_to(self, rel: str) -> bool:
        return not self.suffixes or rel.endswith(tuple(self.suffixes))

    def fires(self, match: re.Match, source: str) -> bool:
        return True if self.accept is None else bool(self.accept(match, source))

    def describe(self, match: re.Match, source: str) -> str:
        if self.snippet is None:
            text = match.group(0)
        elif callable(self.snippet):
            text = self.snippet(match, source)
        else:
            text = str(self.snippet)
        return text[:self.snippet_limit] if self.snippet_limit else text


# ---------------------------------------------------------------------------
# The asset and scaffold seams
# ---------------------------------------------------------------------------
#
# Per decision D5 the suite designs adapter interfaces up front and implements
# them when a real project needs one. The language seam ships one adapter —
# `adapters/php.py` — and `verify_seam.py` proves the engine sweeps a second,
# in-process language through the same interface with no engine changes. The
# asset and scaffold seams below stay as written contracts; their design-era
# implementations (flutter_pubspec, bundler, flutter scaffold) left with the
# design domain rather than being re-pointed at a backend stack that does not
# need them.
#
#   language  adapters/php.py
#   asset     protocol below — no backend-stack implementation yet
#   scaffold  protocol below — no backend-stack implementation yet
#
# The protocols below stay as the written contract — they are what an
# implementation is checked against, and they record *why* each method exists,
# which the implementations should not have to restate.
#
# Both were documented from the coupling that actually exists in the unmigrated
# code rather than from imagination, and the implementations bore that out: the
# directory-registration case called out under `is_registered` is exactly what a
# literal-path implementation gets wrong, and the originating project registers
# `assets/images/` as a directory covering all 33 of its assets.
#
# `bundler.py` is the reference for the refusal path: a stack with no asset
# registry raises CapabilityError rather than inventing a boolean.


@dataclass(frozen=True)
class ErrorHandlingSyntax:
    """How one language spells the pieces audit_error_handling looks for.

    Optional adapter capability, exposed as a module-level `ERROR_HANDLING`.
    The audit used to carry Dart's spelling as constants and ran it over every
    stack, so a TS project with its vocabulary filled in matched nothing and
    exited 0. An adapter without this attribute makes the audit refuse (exit 2)
    rather than guess.

      catch_var    regex whose first non-None group is the caught variable
      type_guard   (var, exception_type) -> regex for the sanctioned type test
      stringify    var -> regex for the whole exception reaching a string
      type_test    class_name -> regex for a state being pattern-matched
      string_quotes  characters that open a string literal (paren matching)
      line_comment   prefix of a whole-line comment
    """
    catch_var: "re.Pattern"
    type_guard: Callable[[str, str], "re.Pattern"]
    stringify: Callable[[str], "re.Pattern"]
    type_test: Callable[[str], "re.Pattern"]
    string_quotes: tuple = ("'", '"')
    line_comment: str = "//"


@dataclass(frozen=True)
class ApiConsistencySyntax:
    """How one language spells the literals audit_api_consistency looks for.

    Optional adapter capability, exposed as `API_CONSISTENCY`. Absent means the
    audit refuses: its patterns were Flutter widget calls, and over another
    stack the semantics check could match nothing and report "clean".
    """
    user_facing: "re.Pattern"   # group(1) is the on-screen literal
    defaulted: "re.Pattern"     # group(1) is an overridable default literal
    compared: "re.Pattern"      # group(1) or group(2) is a compared literal
    tappable: "re.Pattern"      # a raw tap target needing authored semantics


class AssetAdapterProtocol:
    """How bundled imagery enters a project.

    Implementations: `adapters/assets/flutter_pubspec.py` (a real registry) and
    `adapters/assets/bundler.py` (no registry — refuses).

    The generation and rendering core is already project-agnostic — the Blender
    pipeline was designed that way from the start. The coupling is entirely at the
    *registration* boundary: where a rendered file lands, how it is declared to the
    build system, and what a "registered" asset means.

    Required methods, with the concrete Flutter behaviour each would replace:

      asset_root(ctx) -> str
          Where bundled assets live (`assets/` today, hardcoded in the pipeline).

      is_registered(ctx, path) -> bool
          Whether the build system declares this asset. In Flutter that means an
          entry under `flutter: assets:` in pubspec.yaml; in a web project it may
          mean nothing at all, since bundlers discover imports. An adapter that
          cannot tell must raise rather than return False — reporting an asset as
          unregistered when the concept does not apply produces a permanent false
          finding, and reporting it as registered hides a real one.

      register(ctx, path) -> None
          Declare it. Must be idempotent: the asset skills are re-run routinely.

      manifest_path(ctx) -> str
          The pipeline's own record of what exists and how it was produced. Comes
          from the profile's `pipelines.assets`, not a literal.

    Also needed, and the part most likely to be got wrong: the *local* manifest
    (`manifest.local.json`) is gitignored working state. An adapter must not treat
    its absence as "no assets registered".
    """


class ScaffoldAdapterProtocol:
    """How a new screen is generated.

    Implementation: `adapters/scaffold/flutter.py`.

    `/scaffold-screen` already documents a portable three-state core — loading,
    error, content — separately from its Flutter instantiation, so the split is
    half-made in prose. This is the interface that would finish it.

      screen_path(ctx, name) -> str
          Where a screen file belongs, from the profile's `source.screensGlob`.

      render(ctx, name, states) -> str
          The file body. `states` is the portable part; everything else — widget
          names, the contract-header convention, how navigation callbacks arrive —
          is the adapter's.

      companion_files(ctx, name) -> list
          Files a screen cannot exist without in this stack. In the originating
          project that is an adapter class carrying the screen's I/O contract, and
          the architecture audit fails without it. Other stacks may need none.

      register(ctx, name) -> list
          Edits needed to route to it, returned as a description rather than
          applied. Routing is where a scaffolder does the most damage if it guesses.

    Caveat carried forward: `/scaffold-screen` has never been run to produce a real
    screen — its only verification on record is a throwaway compiled-then-deleted
    file. Building this seam should not be treated as validating the skill.
    """
