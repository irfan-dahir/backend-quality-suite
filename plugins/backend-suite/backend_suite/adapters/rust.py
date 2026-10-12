r"""Rust language adapter.

The suite's fourth shipped language, covering the Rust web ecosystem: Axum,
Actix Web, Rocket, Poem, and Warp. It brings the suite's structural audits to
the fastest-growing systems-language backend stack.

Everything language-shaped lives here, per the seam contract in `base.py`: how a
file imports another, how a failed `Result` binds its error, where a user-facing
response literal appears, how a `struct` declares its fields, what a comment is.
The engine and the four seam-consuming audits (`audit_layer_boundaries`,
`audit_error_handling`, `audit_api_consistency`, `audit_contract_headers`) know
none of it.

## Why Rust's imports make `audit_layer_boundaries` refuse

A Rust `use` names a *module path* (`crate::config::db`, `super::models::User`,
`axum::Router`), not a file path — the same shape as Swift's `import DataLayer`
and Kotlin's `import com.x.data.Repo`. `audit_layer_boundaries` matches a
directory-rooted rule (`mustNotImport: src/data/**`) against file paths; a module
is not a directory, so every import would resolve to "external", the sweep would
find nothing, and the audit would print clean over a tree it never checked. The
adapter therefore declares `IMPORT_TARGETS = "module"` and that audit refuses
(exit 2) rather than reporting a confident zero. This is a documented
degradation, not an omission.

## Known gaps, stated so a clean run is never mistaken for a full one

  * `IMPORT_TARGETS = "module"` — see above; no layer-boundary rule is enforced
    on Rust, by design.
  * `ERROR_HANDLING` maps Rust's `Result`/`match`/`?` model onto the audit's
    catch / type-test / stringify vocabulary. `catch_var` matches an `Err(e) =>`
    arm and a `.map_err(|e| …)` closure; `stringify` matches the *Debug* form
    (`format!("{e:?}")`, which prints the whole error plus its internals) and the
    positional Display form, and deliberately does NOT match `e.to_string()`
    alone — the sanctioned narrowing is to test the error against the app's own
    type and take its message.
  * Contract extraction reads `struct`/`enum`/`trait` bodies and `impl` blocks.
    A field assembled by a macro (`sqlx::FromRow`, a hand-written `Builder`) is
    invisible here; reads through an untyped binding raise `CapabilityError`
    rather than counting as "no reads".
  * `dependency_injection` is intentionally absent: Rust has no DI-container
    idiom, so declaring the capability would be inventing a boolean. Shared
    state (`State<AppState>`, `web::Data<T>`) is followed by
    `typed_member_reads`.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import (AdapterContext, ApiConsistencySyntax, Capability,
                   CapabilityError, CapabilityEvidence, Check, CheckSet,
                   ErrorHandlingSyntax)

NAME = "rust"

# The canonical Cargo layout: sources under src/, integration tests under
# tests/, benchmarks and examples beside them, and workspace members under
# crates/*/src/. Which files are SOURCES for a given audit stays profile-driven
# (`source.fileGlob`); these globs feed the structural sweep (uncovered-suffix
# accounting, the seam proof) and the error-handling suffix filter.
FILE_GLOBS = ("src/**/*.rs",
              "app/**/*.rs",
              "lib/**/*.rs",
              "tests/**/*.rs",
              "benches/**/*.rs",
              "examples/**/*.rs",
              "crates/**/src/**/*.rs")

# Rust codegen lands in `target/` (directory-scoped skips handle that) or behind
# `include!`; there is no per-file generated suffix to exclude the way Dart has
# `.g.dart`.
GENERATED_SUFFIXES: tuple[str, ...] = ()

# How one Rust file declares a dependency on another.
#
#   use crate::config::Database;      -> crate::config::Database
#   use super::models::User;          -> super::models::User
#   use axum::{Router, routing};      -> axum
#   use std::collections::HashMap;    -> std::collections::HashMap
#   extern crate serde;               -> serde
#
# Group 1 is the module path with any brace list dropped (`use axum::{…}` -> the
# `axum` root). A leading `::` (`use ::foo::bar`) is part of the path and kept.
IMPORT_RE = re.compile(
    r"""^[ \t]*(?:pub(?:\([^)]*\))?\s+)?use\s+"""
    r"""((?:::)?(?:crate|self|super|[A-Za-z_][A-Za-z0-9_]*)"""
    r"""(?:::[A-Za-z_][A-Za-z0-9_]*)*)"""
    r"""|^[ \t]*extern\s+crate\s+([A-Za-z_][A-Za-z0-9_]*)""",
    re.M,
)

# Rust `use` targets name modules, not file paths — see the module docstring.
# audit_layer_boundaries reads this and refuses rather than mis-matching a
# directory rule against a module path.
IMPORT_TARGETS = "module"


# --------------------------------------------------------------------------- #
# Sweep checks (the `Check` / `scan_tree` seam)
# --------------------------------------------------------------------------- #
#
# Two defects a text sweep genuinely catches on a Rust backend, each grounded in
# a failure mode rather than style:

# A debug statement left in a handler: `println!`/`eprintln!` bypass a structured
# logger (and in a server, stdout is an aggregator, not a response), `dbg!`
# dumps file/line/payload to stderr on a debug build, and `todo!()`/
# `unimplemented!()` are unfinished markers that panic when reached. The
# lookbehind scopes the match to the free macro: a method call
# (`log::info!(`, `tracing::debug!(`) is the project's own logger, and flagging
# those is how a check becomes noise people disable.
DEBUG_STATEMENT_RE = re.compile(
    r"(?<![\w.])(?:dbg!|println!|print!|eprintln!|eprint!)\s*\("
    r"|(?<![\w.])(?:todo|unimplemented)!\s*\("
)

# A credential committed as a string literal. Matches a bare assignment
# (`let password = "…"`) and the typed/`const` form a Rust config actually uses
# (`const DB_PASSWORD: &str = "…"`, `password: "…"`). The lookbehind allows the
# `DB_` prefix (`_` is not alphanumeric) while a lowercase suffix
# (`mypassword`) is still rejected. The negative control this must NOT flag is
# the correct shape `std::env::var("DB_PASSWORD")`, where the right-hand side is
# a call, not a literal.
PLAINTEXT_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9])(?i:password|passwd|secret|api[_-]?key|access[_-]?token"
    r"|client[_-]?secret)\w*\s*(?::\s*[^=;\n]+)?=\s*\"[^\"\n]{6,}\""
)


def checks(ctx: AdapterContext) -> CheckSet:
    return CheckSet([
        Check("debug_statement", DEBUG_STATEMENT_RE, category="debug",
              snippet_limit=80),
        Check("plaintext_secret", PLAINTEXT_SECRET_RE, category="secrets",
              snippet_limit=80),
    ])


# --------------------------------------------------------------------------- #
# Comment handling
# --------------------------------------------------------------------------- #
#
# Blanked in place, never deleted: the audits report line numbers into the
# original file, so any transform that shifted offsets would make every finding
# point at the wrong line.

# A raw string: `r"…"`, `r#"…"#`, `br##"…"##`. The `#` count must balance.
_RAW_STRING_RE = re.compile(r"(?:br|rb|r)(?P<hashes>#*)\"")


def _raw_string_end(source: str, start: int, hashes: str) -> int:
    """Index just past a raw string starting at `start`, or len(source)."""
    close = '"' + hashes
    found = source.find(close, start + 1)
    return len(source) if found == -1 else found + len(close)


def _normal_string_end(source: str, start: int) -> int:
    """Index just past a `"…"` string, honouring `\\` escapes."""
    i, n = start + 1, len(source)
    while i < n:
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == '"':
            return i + 1
        i += 1
    return n


def _char_literal_end(source: str, start: int) -> int | None:
    """Index just past a `'c'` char literal, or None when `start` is a lifetime.

    Rust reuses `'` for both char literals and lifetime annotations
    (`&'a mut T`). A literal closes on the same line after one character or one
    escape; a lifetime is `'` + identifier with no closing quote, and treating
    it as a literal would swallow the rest of the line.
    """
    n = len(source)
    j = start + 1
    if j >= n or source[j] == "\n":
        return None
    if source[j] == "\\":
        k = j + 1
        if k < n and source[k] == "u" and k + 1 < n and source[k + 1] == "{":
            close = source.find("}", k)
            if close == -1:
                return None
            k = close + 1
        else:
            k += 1
        return k + 1 if k < n and source[k] == "'" else None
    if j + 1 < n and source[j + 1] == "'":
        return j + 2
    return None


def _blank_nested_block(out: list, source: str, start: int) -> int:
    """Blank a `/* … */` block from `start`; Rust block comments NEST.

    The delimiters are blanked too: leaving `/*` and `*/` in place would put a
    spurious `/` next to live code, and the marker of a comment is not source.
    """
    i, n, depth = start, len(source), 0
    while i < n:
        if source.startswith("/*", i):
            depth += 1
            out[i] = out[i + 1] = " "
            i += 2
            continue
        if source.startswith("*/", i):
            depth -= 1
            out[i] = out[i + 1] = " "
            i += 2
            if depth == 0:
                return i
            continue
        if out[i] != "\n":
            out[i] = " "
        i += 1
    return i


def blank_comments(source: str) -> str:
    """`source` with every comment replaced by spaces, same length, lines intact.

    Rust's comment forms: `//` (including `///` doc comments) and nested
    `/* … */`. Strings are skipped before comments are looked for, so a
    `"https://…"` literal does not lose the rest of its line to a false `//`.
    Raw strings (`r"…"`, `r#"…"#`) and char literals are skipped whole, and a
    lifetime (`'a`) is stepped over rather than opened as a char literal.
    """
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        raw = _RAW_STRING_RE.match(source, i)
        if raw:
            i = _raw_string_end(source, i, raw.group("hashes"))
            continue
        ch = source[i]
        if ch == '"':
            i = _normal_string_end(source, i)
            continue
        if ch == "'":
            end = _char_literal_end(source, i)
            i = end if end is not None else i + 1
            continue
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if source.startswith("/*", i):
            i = _blank_nested_block(out, source, i)
            continue
        i += 1
    return "".join(out)


def block_comments(source: str) -> list[tuple[int, str]]:
    """Every banner block, as (1-based start line, text).

    Two forms, because Rust documents a contract in either: a `/* … */` block,
    and a run of `///` (outer) or `//!` (inner) doc-comment lines, which is the
    idiomatic rustdoc banner above a struct or handler.
    """
    blocks = [(source.count("\n", 0, m.start()) + 1, m.group(1))
              for m in re.finditer(r"/\*(.*?)\*/", source, re.DOTALL)]
    for m in re.finditer(r"(?m)((?:[ \t]*//[/!].*\n)+)", source):
        blocks.append((source.count("\n", 0, m.start(1)) + 1, m.group(1)))
    return blocks


# --------------------------------------------------------------------------- #
# Contract-header structural extraction
# --------------------------------------------------------------------------- #
#
# "What does this struct declare", "what does this code read off a receiver",
# "where are the banner comments" — asked by the contract-header engine without
# knowing the language. A Rust "screen" is a handler, its "adapter" the service
# struct it delegates to, and the CONTRACT banner is the banner convention the
# audit already reads from config.

CONTRACT_CAPABLE = True  # the engine checks this before trusting the below

# A `struct`/`enum`/`trait` header up to its opening brace.
_DECL_HEAD_RE = re.compile(r"\b(?:struct|enum|trait|union)\s+([A-Za-z_]\w*)\b")

# A struct field: `pub name: Type,`, `name: Type,`, `pub(crate) name: Type`.
# The `:` is required; a bare identifier at line start is a statement, not a
# field. Type text (generics, references, tuples) is not parsed — only the
# name and its line matter here.
_FIELD_RE = re.compile(
    r"(?m)^[ \t]*(?:pub(?:\([^)]*\))?\s+)?([A-Za-z_]\w*)\s*:")
# A public method in an `impl`: `pub fn name(`, `pub async fn name(`,
# `pub(crate) const fn name(`. Only the public surface — a private method is
# unreachable for a caller, so a contract documenting one documents a fiction.
_METHOD_RE = re.compile(
    r"(?m)^[ \t]*pub(?:\([^)]*\))?\s+"
    r"(?:async\s+|const\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+)*fn\s+([A-Za-z_]\w*)")
# A trait method declaration or a private `fn` — matched only inside a trait.
_TRAIT_FN_RE = re.compile(
    r"(?m)^[ \t]*(?:async\s+|const\s+|unsafe\s+)*fn\s+([A-Za-z_]\w*)")
_IMPL_HEADER_RE = re.compile(r"\bimpl\b[^{;]*\{")


def _line_of(blanked: str, offset: int) -> int:
    return blanked.count("\n", 0, offset) + 1


def _match_brace(source: str, open_index: int) -> int | None:
    """Index of the `}` matching the `{` at `open_index`, or None."""
    depth = 0
    for i in range(open_index, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _decl_body_span(source: str, class_name: str) -> tuple[int, int] | None:
    """(start, end) just inside the braces of a `struct`/`enum`/`trait` body."""
    for m in _DECL_HEAD_RE.finditer(source):
        if m.group(1) != class_name:
            continue
        brace = source.find("{", m.end())
        if brace == -1:
            return None  # unit struct (`struct X;`) or tuple struct: no body
        end = _match_brace(source, brace)
        if end is not None:
            return brace + 1, end
    return None


def _impl_body_spans(source: str, class_name: str) -> list[tuple[int, int]]:
    """Bodies of every `impl [Trait for] ClassName { … }` block."""
    needle = re.compile(rf"\b{re.escape(class_name)}\b")
    spans: list[tuple[int, int]] = []
    for m in _IMPL_HEADER_RE.finditer(source):
        if not needle.search(m.group(0)):
            continue
        brace = m.end() - 1
        end = _match_brace(source, brace)
        if end is not None:
            spans.append((brace + 1, end))
    return spans


def class_fields(source: str, class_name: str) -> dict[str, int] | None:
    """`{field name: 1-based line}` for one struct/enum/trait.

    None means the type is not in this source — distinct from `{}` meaning it
    declares nothing (a unit struct), which the caller must not conflate.
    Methods are not included (see `class_members`).
    """
    blanked = blank_comments(source)
    if not any(m.group(1) == class_name for m in _DECL_HEAD_RE.finditer(blanked)):
        return None
    span = _decl_body_span(blanked, class_name)
    if span is None:
        return {}
    start, end = span
    body = blanked[start:end]
    base = _line_of(blanked, start)
    fields: dict[str, int] = {}
    for m in _FIELD_RE.finditer(body):
        fields.setdefault(m.group(1), base + body.count("\n", 0, m.start(1)))
    return fields


def class_members(source: str, class_name: str) -> dict[str, int] | None:
    """Like `class_fields`, plus the type's public methods.

    A service struct's whole purpose is to be a surface, so its `pub fn`
    methods (declared in an `impl` block, which in Rust lives outside the
    struct body) belong to the same contract a header documents.
    """
    blanked = blank_comments(source)
    fields = class_fields(source, class_name)
    if fields is None:
        return None
    members = dict(fields)
    span = _decl_body_span(blanked, class_name)
    is_trait = span is not None and re.search(
        rf"\btrait\s+{re.escape(class_name)}\b", blanked)
    if is_trait:
        body, base = blanked[span[0]:span[1]], _line_of(blanked, span[0])
        for m in _TRAIT_FN_RE.finditer(body):
            members.setdefault(m.group(1), base + body.count("\n", 0, m.start(1)))
    for start, end in _impl_body_spans(blanked, class_name):
        body, base = blanked[start:end], _line_of(blanked, start)
        for m in _METHOD_RE.finditer(body):
            members.setdefault(m.group(1), base + body.count("\n", 0, m.start(1)))
    return members


def member_reads(source: str, receiver: str) -> set[str]:
    """Names read off the receiver `receiver` — `svc.total` and `self.svc.total`
    both → {"total"}.

    Rust has no sigil, so `receiver\\.(\\w+)` matches both the local binding and
    a property read. Comments are blanked first, and that is load-bearing: a
    CONTRACT banner listing `svc.total` would otherwise count as a read and the
    dead-member check would report zero forever.
    """
    return set(re.findall(rf"(?:\b|\.){re.escape(receiver)}\.(\w+)",
                          blank_comments(source)))


def receiver_aliases(source: str, receiver: str) -> set[str]:
    """Local names bound to the receiver, so reads through them still count.

    `let svc = &self.service;` then `svc.total()` is a read of the service.
    Matching only the conventional name reported every member of an aliased
    service as dead.
    """
    code = blank_comments(source)
    escaped = re.escape(receiver)
    patterns = (
        rf"\blet\s+(\w+)\s*(?::[^=;]+)?=\s*&?\s*self\.{escaped}\b",
        rf"\blet\s+(\w+)\s*(?::[^=;]+)?=\s*&?\s*{escaped}\b",
    )
    return {m.group(1) for pattern in patterns for m in re.finditer(pattern, code)} \
        - {receiver}


def typed_member_reads(source: str, types) -> dict[str, set[str]]:
    """`{type: members read off any identifier declared with that type}`.

    The receiver is resolved by its declared type, not by what it happens to be
    called — matching one conventional name is the bug that reports real members
    as dead with deletion as the advice. Typed parameters (`fn f(x: Foo)`),
    struct fields (`foo: Foo`), and locals (`let foo: Arc<Foo> = …`) are all
    followed.

    Raises `CapabilityError` when a binding of one of `types` is drawn from a
    shared-state accessor through an untyped variable (`let x = state.get::<Foo>()`):
    reads through it are invisible here, and "I cannot tell" must never come back
    as "nothing reads it".
    """
    code = blank_comments(source)
    found: dict[str, set[str]] = {}
    for type_name in types:
        escaped = re.escape(type_name)
        blind = re.search(
            rf"\blet\s+\w+\s*=\s*[^;]*"
            rf"(?:\.get|app_data|\.data|injector|container)\s*"
            rf"(?:::<\s*|\()\s*(?:[\w:]+::)*{escaped}\b", code)
        if blind:
            raise CapabilityError(
                "typed_member_reads", NAME,
                f"{type_name} is bound to an untyped receiver "
                f"({blind.group(0).strip()!r}); reads through it cannot be "
                f"resolved, so this file cannot be used to decide whether "
                f"{type_name}'s members are read")
        names = set()
        # A binding with a declared type: `x: Foo`, `x: &Foo`, `x: Arc<Foo>`,
        # `mut x: Foo` — parameters, struct fields, and `let x: Foo = …` alike.
        # The type expression may wrap the name (`Option<Foo>`, `Vec<Foo>`), so
        # it is matched as "everything up to the next separator that contains
        # the type".
        for match in re.finditer(
                rf"(?:^|[\s(,])(?:mut\s+)?(\w+)\s*:[^=,;)\n]*\b{escaped}\b",
                code, re.M):
            names.add(match.group(1))
        members: set[str] = set()
        for name in names:
            members |= member_reads(code, name)
        if members:
            found[type_name] = members
    return found


# --------------------------------------------------------------------------- #
# audit_error_handling syntax
# --------------------------------------------------------------------------- #
#
# Rust has no `try`/`catch`: a failure is an `Err(e)` variant bound by a `match`
# arm, an `if let`, or a closure handed to `.map_err`. The mangling the audit
# looks for is the *whole* error reaching a user-facing string — the Debug form
# `format!("{e:?}")` prints message plus internals, where the sanctioned
# narrowing tests the error against the app's own type and takes its message.
# `e.to_string()` alone is not matched: that is the message, and flagging it
# would report every correct handler as mangling.
ERROR_HANDLING = ErrorHandlingSyntax(
    # `Err(e) => …` (match arm), `if let Err(e) = …`, or `.map_err(|e| …)` /
    # `.map_err(|e: AppError| …)`. Group 1 is the variable from `Err(…)`,
    # group 2 the closure parameter.
    catch_var=re.compile(
        r"\bErr\s*\(\s*(\w+)\s*\)"
        r"|\.map_err\s*\(\s*\|\s*(\w+)(?:\s*:[^|]*)?\s*\|"),
    # The sanctioned narrowing: test the error against the app's own error type
    # before reaching for its message — `matches!(e, AppError::…)`,
    # `e.downcast_ref::<AppError>()`, or `if let AppError::… = e`.
    type_guard=lambda var, typ: re.compile(
        rf"matches!\s*\(\s*{re.escape(var)}\s*,[^)]*(?:[\w:]+::)*{re.escape(typ)}\b"
        rf"|{re.escape(var)}\s*\.\s*downcast_ref::<\s*{re.escape(typ)}\s*>"
        rf"|\bif\s+let\s+(?:[\w:]+::)*{re.escape(typ)}\b[^\n]*=\s*{re.escape(var)}"),
    # Put the WHOLE error into a string: the captured Debug form
    # (`format!("{e:?}")`) and the positional forms (`format!("{:?}", e)`,
    # `format!("{}", e)`).
    stringify=lambda var: re.compile(
        r"\{\s*" + re.escape(var) + r"\s*:\s*\?\s*\}"             # {e:?}
        r"|\{\s*" + re.escape(var) + r"\s*\}"                      # {e}
        r"|\{:[^}]*\}\s*\x22\s*,\s*" + re.escape(var) + r"\b"),    # {:?}, e
    # A failure state being pattern-matched: a bare variant/path reference,
    # `AppError::NotFound` including a struct-pattern application.
    type_test=lambda cls: re.compile(
        rf"\b(?:[\w:]+::)*{re.escape(cls)}\b\s*(?:::|\()"),
    string_quotes=('"',),
    line_comment="//",
)


# --------------------------------------------------------------------------- #
# audit_api_consistency syntax
# --------------------------------------------------------------------------- #
#
# The Rust reading of the audit's four checks:
#
#   user_facing  — a response literal under a user-facing envelope key
#                  (`json!({ "message": "Not found" })`). On a LIBRARY this is
#                  the white-label defect: copy a consumer cannot re-voice.
#   defaulted    — an overridable fallback (`unwrap_or("Unknown")`), so a
#                  default literal is not hard-baked.
#   compared     — a literal on either side of an equality: the load-bearing
#                  shape, where the sentinel and the value are the same string.
#   tappable     — a route declaration, the backend's only honest analogue of an
#                  interaction surface. The `authoredSemantics` check it feeds is
#                  a UI concept; a Rust project turns it off with a written
#                  reason rather than run it against a stack with no semantics API.
API_CONSISTENCY = ApiConsistencySyntax(
    user_facing=re.compile(
        r'"?(?:message|error|detail|description)"?\s*:\s*"([^"\\]{2,})"'),
    defaulted=re.compile(
        r'unwrap_or(?:_else)?\s*\(\s*(?:\|[^|]*\|\s*)?\.?"([^"\\]{2,})"'),
    # Exactly two groups: the audit unpacks `for a, b in COMPARED.findall(line)`.
    compared=re.compile(
        r'==\s*"([^"\\]{2,})"|!=\s*"([^"\\]{2,})"'),
    tappable=re.compile(
        r'\.route\s*\(\s*"'
        r'|\b(?:get|post|put|patch|delete|head|options)\s*\(\s*"'
        r'|#\[(?:get|post|put|patch|delete|head|options)\s*\(\s*"'
        r'|\bweb::resource\s*\(\s*"'
        r'|\bRoute::new\s*\(\s*\)'),
)


# --------------------------------------------------------------------------- #
# Capability detection (base.LanguageCapabilityProtocol)
# --------------------------------------------------------------------------- #
#
# What a Rust routing declaration looks like is a language/framework fact and
# belongs here: the engine asks "does this project route?" and never learns what
# the answer was made of.

# Base routing signatures (framework-agnostic)
ROUTING_SIGNATURES = (
    # Axum/Poem: Router::new().route("/path", get(handler))
    re.compile(r"\bRouter\s*::\s*new\s*\(\s*\)"),
    re.compile(r"\.\s*route\s*\(\s*\"[^\"]*\""),
    # Rocket: #[get("/path")], #[post("/path", data = "<d>")]
    re.compile(r"#\[(?:get|post|put|patch|delete|head|options)\s*\("),
    # Rocket: routes![…] mount list
    re.compile(r"\broutes!\s*\["),
    # Actix Web: web::resource("/path"), App::new().service(…)
    re.compile(r"\bweb\s*::\s*resource\s*\(\s*\""),
    re.compile(r"\bApp\s*::\s*new\s*\(\s*\)"),
    re.compile(r"\bHttpServer\s*::\s*new\s*\(\s*\)"),
    # Warp: warp::path("…"), warp::get(), warp::serve(…)
    re.compile(r"\bwarp\s*::\s*(?:path|get|post|put|delete|serve)\b"),
    # Poem: Route::new(), #[oai(path = "…")]
    re.compile(r"#\[oai\s*\(\s*path\s*="),
)

MODEL_CAPABILITY_SIGNATURES = (
    re.compile(r"#\[derive\([^)]*\b(?:Queryable|FromRow|Serialize|Deserialize)\b"),
    re.compile(r"\bdiesel\s*::"),
    re.compile(r"\bsea_orm\s*::"),
    re.compile(r"\brusqlite\s*::"),
    re.compile(r"\bsqlx\s*::\s*(?:query|query_as|query_scalar)!"),
    re.compile(r"#\[(?:table_name|sea_orm)\b"),
)

VALIDATION_CAPABILITY_SIGNATURES = (
    re.compile(r"#\[validate\("),
    re.compile(r"\bvalidator\s*::"),
    re.compile(r"garde\s*::"),
    re.compile(r"#\[garde\("),
)

MIDDLEWARE_CAPABILITY_SIGNATURES = (
    re.compile(r"\bmiddleware\s*::\s*from_fn\b"),
    re.compile(r"\bServiceBuilder\s*::\s*new\s*\(\s*\)"),
    re.compile(r"\btower\s*::"),
    re.compile(r"\b(?:wrap|service)\s*\(\s*\w*Middleware"),
    re.compile(r"\bimpl\s*<\s*[^>]*>\s*(?:tower::)?(?:Layer|Service)\b"),
)

API_RESOURCES_CAPABILITY_SIGNATURES = (
    re.compile(r"#\[derive\([^)]*\bSerialize\b[^)]*\)\]"),
    re.compile(r"#\[derive\([^)]*\bDeserialize\b[^)]*\)\]"),
    re.compile(r"\bimpl\s+(?:axum::response::)?IntoResponse\b"),
    re.compile(r"\bimpl\s+(?:actix_web::)?Responder\b"),
    re.compile(r"\b(?:Json|web::Json|web::Query|web::Form)\s*<"),
)

POLICIES_CAPABILITY_SIGNATURES = (
    re.compile(r"\bFromRequest\b"),
    re.compile(r"\bFromRequestParts\b"),
    re.compile(r"\bClaims\b"),
    re.compile(r"\bJwtAuth\b"),
    re.compile(r"\bRequireAuthorization\b"),
    re.compile(r"\bAuthoriz(?:e|ation)\b"),
    re.compile(r"#\[(?:protected|auth)\b"),
)

# Framework-specific routing signatures (extends base)
AXUM_ROUTING_SIGNATURES = (
    re.compile(r"\baxum\s*::"),
    re.compile(r"\bRouter\s*::\s*new\s*\(\s*\)"),
    re.compile(r"\.\s*route\s*\(\s*\"[^\"]*\"\s*,"),
    re.compile(r"\bmiddleware\s*::\s*from_fn\b"),
    re.compile(r"\.\s*with_state\s*\("),
)

ACTIX_ROUTING_SIGNATURES = (
    re.compile(r"\bactix_web\s*::"),
    re.compile(r"#\[(?:get|post|put|patch|delete)\s*\("),
    re.compile(r"\bweb\s*::\s*(?:resource|scope)\s*\("),
    re.compile(r"\bApp\s*::\s*new\s*\(\s*\)"),
    re.compile(r"\bHttpServer\s*::\s*new\s*\(\s*\)"),
)

ROCKET_ROUTING_SIGNATURES = (
    re.compile(r"\brocket\s*::"),
    re.compile(r"#\[(?:get|post|put|patch|delete|head|options)\s*\("),
    re.compile(r"\broutes!\s*\["),
    re.compile(r"#\[launch\]"),
    re.compile(r"#\[rocket::main\]"),
)

POEM_ROUTING_SIGNATURES = (
    re.compile(r"\bpoem\s*::"),
    re.compile(r"\bRoute\s*::\s*new\s*\(\s*\)"),
    re.compile(r"#\[oai\s*\("),
    re.compile(r"\.\s*at\s*\(\s*\""),
)

WARP_ROUTING_SIGNATURES = (
    re.compile(r"\bwarp\s*::"),
    re.compile(r"\bwarp\s*::\s*path\s*\("),
    re.compile(r"\bwarp\s*::\s*(?:get|post|put|delete|serve)\s*\("),
)

# Base capability signatures (framework-agnostic)
CAPABILITY_SIGNATURES = {
    "routing": (
        ROUTING_SIGNATURES,
        "a Rust backend declares its routes via Router::new().route(…) or "
        "#[get(\"/path\")] (Axum/Rocket/Poem), web::resource(…) (Actix), or "
        "warp::path(…) (Warp); these are the constructions that mean the former",
    ),
    "models": (
        MODEL_CAPABILITY_SIGNATURES,
        "a Rust backend declares models through an ORM: Diesel "
        "(#[derive(Queryable)]/#[table_name]), SeaORM (#[derive(DeriveEntityModel)]), "
        "SQLx (sqlx::query!), or rusqlite. These patterns cover the surface.",
    ),
    "validation": (
        VALIDATION_CAPABILITY_SIGNATURES,
        "a Rust backend validates input via the validator crate (#[validate(…)]), "
        "garde (#[garde(…)]), or an equivalent derive. These patterns cover the surface.",
    ),
    "middleware": (
        MIDDLEWARE_CAPABILITY_SIGNATURES,
        "a Rust backend uses Tower layers (ServiceBuilder, Layer/Service impls) or "
        "framework middleware (Axum middleware::from_fn, Actix wrap(…)). These "
        "patterns cover the surface.",
    ),
    "api_resources": (
        API_RESOURCES_CAPABILITY_SIGNATURES,
        "a Rust backend defines API resources: request/response structs deriving "
        "Serialize/Deserialize and handlers implementing IntoResponse/Responder. "
        "These patterns cover the surface.",
    ),
    "policies": (
        POLICIES_CAPABILITY_SIGNATURES,
        "a Rust backend implements authorization: FromRequest/FromRequestParts "
        "extractor guards, JWT/Claims extractors, or auth middleware. These "
        "patterns cover the surface.",
    ),
}

AXUM_CAPABILITY_SIGNATURES = {
    "axum_routing": (AXUM_ROUTING_SIGNATURES,
                     "an Axum project builds a Router::new().route(…) tree with "
                     "extractors and middleware::from_fn layers."),
}
ACTIX_CAPABILITY_SIGNATURES = {
    "actix_routing": (ACTIX_ROUTING_SIGNATURES,
                      "an Actix Web project declares routes via #[get(…)] attributes "
                      "and web::resource/web::scope, served by HttpServer."),
}
ROCKET_CAPABILITY_SIGNATURES = {
    "rocket_routing": (ROCKET_ROUTING_SIGNATURES,
                       "a Rocket project declares routes via #[get(…)]/#[post(…)] "
                       "attributes, mounts them with routes![…], and boots with "
                       "#[launch]."),
}
POEM_CAPABILITY_SIGNATURES = {
    "poem_routing": (POEM_ROUTING_SIGNATURES,
                     "a Poem project builds a Route::new() tree with .at(…) and "
                     "OpenAPI #[oai(…)] attributes."),
}
WARP_CAPABILITY_SIGNATURES = {
    "warp_routing": (WARP_ROUTING_SIGNATURES,
                     "a Warp project composes filters with warp::path(…)/warp::get() "
                     "and serves them with warp::serve(…)."),
}

# All capability signatures merged
ALL_CAPABILITY_SIGNATURES = {
    **CAPABILITY_SIGNATURES,
    **AXUM_CAPABILITY_SIGNATURES,
    **ACTIX_CAPABILITY_SIGNATURES,
    **ROCKET_CAPABILITY_SIGNATURES,
    **POEM_CAPABILITY_SIGNATURES,
    **WARP_CAPABILITY_SIGNATURES,
}

CAPABILITIES = (
    Capability(
        name="routing",
        profile_field="source.routesFile",
        why="every route-aware check reads the file this field names. "
            "Undeclared, the check has nothing to read and reports clean — "
            "inert, not passing",
    ),
    Capability(
        name="models",
        profile_field="source.root",
        why="ORM model declarations (Diesel, SeaORM, SQLx, rusqlite). A project "
            "using these patterns should declare source.root so the audit can "
            "find them.",
    ),
    Capability(
        name="validation",
        profile_field="source.root",
        why="input validation (validator, garde). A project using these patterns "
            "should declare source.root so the audit can find them.",
    ),
    Capability(
        name="middleware",
        profile_field="source.root",
        why="middleware layers (Tower, Axum middleware::from_fn, Actix wrap). A "
            "project using these patterns should declare source.root so the "
            "audit can find them.",
    ),
    Capability(
        name="api_resources",
        profile_field="source.root",
        why="request/response structs and handlers (Serialize/Deserialize, "
            "IntoResponse/Responder). A project using these patterns should "
            "declare source.root so the audit can find them.",
    ),
    Capability(
        name="policies",
        profile_field="source.root",
        why="authorization extractors and guards (FromRequest, Claims, JWT). A "
            "project using these patterns should declare source.root so the "
            "audit can find them.",
    ),
    Capability(
        name="axum_routing",
        profile_field="source.routesFile",
        why="an Axum project declares routes on a Router. Undeclared, no route "
            "check has a file to read and reports clean — inert, not passing",
    ),
    Capability(
        name="actix_routing",
        profile_field="source.routesFile",
        why="an Actix Web project declares routes via #[get(…)] attributes and "
            "web::resource. Undeclared, no route check has a file to read and "
            "reports clean — inert, not passing",
    ),
    Capability(
        name="rocket_routing",
        profile_field="source.routesFile",
        why="a Rocket project declares routes via #[get(…)] attributes, mounted "
            "with routes![…]. Undeclared, no route check has a file to read and "
            "reports clean — inert, not passing",
    ),
    Capability(
        name="poem_routing",
        profile_field="source.routesFile",
        why="a Poem project builds a Route::new() tree. Undeclared, no route "
            "check has a file to read and reports clean — inert, not passing",
    ),
    Capability(
        name="warp_routing",
        profile_field="source.routesFile",
        why="a Warp project composes routes with warp::path(…). Undeclared, no "
            "route check has a file to read and reports clean — inert, not "
            "passing",
    ),
)

# Framework-specific capabilities - only offered when the project reads as that
# framework (matched by Cargo dependency or a `use <crate>::` in source).
FRAMEWORK_ONLY_CAPABILITIES = {
    "axum_routing": "axum",
    "actix_routing": "actix-web",
    "rocket_routing": "rocket",
    "poem_routing": "poem",
    "warp_routing": "warp",
}


def _expand_file_glob(repo: Path, pattern: str) -> list:
    """The concrete files a `source.routesFile` value names.

    The value may be a single file (`src/routes.rs`) or a glob
    (`src/routes/*.rs`); both are resolved repo-relative, and a pattern that
    names nothing yields an empty list (the caller's own empty-sweep refusal
    then stands — no evidence is not evidence of absence).
    """
    path = Path(pattern)
    if path.is_absolute():
        return [path] if path.is_file() else []
    return sorted(repo.glob(pattern))


def _crate_alias(crate: str) -> str:
    """A crate name as an interchangable `-`/`_` regex (`actix-web`/`actix_web`)."""
    escaped = re.escape(crate).replace("_", "[_-]")
    return escaped.replace(r"\-", "[_-]")


def _manifest_text(root: Path) -> str:
    path = root / "Cargo.toml"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _declares_crate(manifest: str, crate: str) -> bool:
    """Whether `Cargo.toml` names the crate as a dependency (or package rename)."""
    alias = _crate_alias(crate)
    return bool(re.search(rf"(?m)^[ \t]*{alias}\s*=", manifest)
                or re.search(rf'package\s*=\s*"{alias}"', manifest))


def _source_tree(ctx: AdapterContext, root: Path) -> Path:
    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    return base if base.is_dir() else root


def _uses_crate(base: Path, crate: str) -> bool:
    """Whether any hand-written `.rs` under `base` names the crate in a `use`."""
    needle = re.compile(rf"\b(?:use|extern\s+crate)\s+{_crate_alias(crate)}\b")
    for path in base.rglob("*.rs"):
        rel = path.relative_to(base)
        if "target" in rel.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if needle.search(text):
            return True
    return False


def _looks_rust(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a Rust project, not just "a directory".

    Conservative and cheap: any of a root `Cargo.toml` or a `.rs` file under the
    configured source tree is enough. A false "yes" costs extra capability
    findings; a false "no" leaves a real Rust project's capabilities unexamined.
    """
    root = Path(str(ctx.repo))
    if (root / "Cargo.toml").is_file():
        return True
    base = _source_tree(ctx, root)
    return any(base.rglob("*.rs"))


def _looks_framework(ctx: AdapterContext, crate: str) -> bool:
    """Whether this tree reads as a `crate` application."""
    root = Path(str(ctx.repo))
    if _declares_crate(_manifest_text(root), crate):
        return True
    base = _source_tree(ctx, root)
    return _uses_crate(base, crate)


def capabilities(ctx: AdapterContext) -> list:
    """What this adapter can be asked about. See base.LanguageCapabilityProtocol.

    Framework-specific routing capabilities are offered only to projects that
    read as that framework (see `_looks_framework`). On any other Rust tree they
    are simply not asked — a project is neither measured nor excused for
    capabilities it never claimed.

    `ctx` is None when a caller is merely probing which capabilities exist
    (`detect_capability` is not reached); treat that as "assume any framework"
    rather than crashing on `ctx.repo`.
    """
    caps = list(CAPABILITIES)
    if ctx is None:
        return caps
    for cap_name, crate in FRAMEWORK_ONLY_CAPABILITIES.items():
        if not _looks_framework(ctx, crate):
            caps = [c for c in caps if c.name != cap_name]
    return caps


def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    """Whether this project does `name`, or a refusal.

    Three separate refusals, all of which would otherwise arrive as a flat "no":
    an unknown capability, a source root that is not there, and a source root
    holding no Rust at all. The last is the one that bites — point the adapter at
    a workspace stub and every capability reads as absent, which is a clean
    report about a tree nobody looked at.
    """
    signatures = ALL_CAPABILITY_SIGNATURES.get(name)
    if signatures is None:
        raise CapabilityError(name, NAME,
                              f"no signature set for this capability; known: "
                              f"{sorted(ALL_CAPABILITY_SIGNATURES)}")
    patterns, why = signatures

    repo = Path(str(ctx.repo))
    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    if not root_rel:
        raise CapabilityError(name, NAME, "profile sets no source.root, so there "
                                          "is no tree to read for evidence")
    root = repo / root_rel
    if not root.is_dir():
        raise CapabilityError(name, NAME,
                              f"source.root {root_rel!r} is not a directory here")

    sources: list[Path] = []
    for path in root.rglob("*.rs"):
        rel = path.relative_to(root)
        if "target" in rel.parts:
            continue
        sources.append(path)

    # Routing evidence conventionally lives OUTSIDE source.root — a binary crate
    # puts Router::new() in src/main.rs while the library lives under src/, and
    # this capability's own profile_field is `source.routesFile`. Scan the
    # declared routes file(s) as well, so a real layout is measured rather than
    # reported as "unused" by a scan that never saw its declarations.
    routes_rel = (ctx.profile.get("source", {}) or {}).get("routesFile")
    if routes_rel:
        for candidate in _expand_file_glob(repo, routes_rel):
            if candidate not in sources:
                sources.append(candidate)

    if not sources:
        raise CapabilityError(
            name, NAME,
            f"no hand-written .rs under {root_rel!r} — absence of evidence in "
            f"an empty tree is not evidence of absence")

    hits, unreadable = [], []
    for path in sorted(sources):
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f"{path.relative_to(repo).as_posix()}: {exc}")
            continue
        if any(pattern.search(text) for pattern in patterns):
            hits.append(path.relative_to(repo).as_posix())

    if not hits and unreadable:
        # A negative answer built partly on files nobody could read is a guess.
        raise CapabilityError(
            name, NAME,
            f"found no evidence, but {len(unreadable)} file(s) could not be "
            f"read: {unreadable[:5]}")
    return CapabilityEvidence(
        present=bool(hits),
        files=tuple(hits[:20]),
        why=why if hits else f"none of the {len(sources)} source file(s) match: {why}",
    )
