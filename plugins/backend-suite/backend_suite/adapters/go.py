r"""Go language adapter.

The suite's fifth shipped language, covering the Go web ecosystem: Gin, Echo,
Chi, Fiber, and the standard library's `net/http`. It brings the suite's
structural audits to the language the backend world's fast-moving middle class
actually writes services in — concurrency is the point of the language, but a
Gin project still ships the same shapes this suite audits: routes, response
maps, `err != nil` chains, and service structs.

Everything language-shaped lives here, per the seam contract in `base.py`: how a
file imports another, how a failed `Result` binds its error, where a user-facing
response literal appears, how a `struct` declares its fields, what a comment is.
The engine and the four seam-consuming audits (`audit_layer_boundaries`,
`audit_error_handling`, `audit_api_consistency`, `audit_contract_headers`) know
none of it.

## Why Go's imports make `audit_layer_boundaries` refuse

A Go `import` names a *package path* (`"github.com/gin-gonic/gin"`,
`"myapp/internal/data"`), not a file path. Even a same-module import is
`module-prefixed` (`import "github.com/me/app/internal/data"` rather than
`import "internal/data"`), and the module prefix is decided by the `module`
directive in `go.mod` — which may name a directory different from the one the
package actually lives in (`replace` directives exist precisely because the two
can diverge). `audit_layer_boundaries` matches a directory-rooted rule
(`mustNotImport: internal/**`) against file paths; a package path is what it
calls external, so every import would resolve to "external", the sweep would
decode relayout advice from a backward premise, and the parser (the audit's
second half) would point at files that are not actually imported.

So this adapter sets `IMPORT_TARGETS = "module"` — the same refusal Rust makes —
and `audit_layer_boundaries` refuses (exit 2) rather than print a confident
zero. The refusal is the feature: a boundary audit that cannot name files
should say so, not offer a passenger.

## The value-model error handling

Go has no exceptions, so `audit_error_handling`'s "caught exception" is the
`err` value bound by assignment and tested as `!= nil`. The sanctioned
narrowing is `errors.As(err, &target)` / `errors.Is(err, sentinel)` — tests the
error's *type or identity* and then takes its message — while the mangling is
`fmt.Sprintf("%+v", err)` / `fmt.Errorf("… %+v", err)`, which flattens a
struct-wrapped error (message plus fields) into a user-facing string. The
pattern for the audit lives in `ERROR_HANDLING` below.

## What this adapter counts as the surface

Go's exported-name rule does the work Rust's `pub` keyword does there: only
capitalised identifiers are reachable from outside the package, so
`class_fields`/`class_members` count capitalised struct fields and receiver
methods, and a CONTRACT banner documenting a private helper documents a fiction
the same way a Rust banner documenting a private `fn` does.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import (  # noqa: E501
    AdapterContext,
    ApiConsistencySyntax,
    Capability,
    CapabilityError,
    CapabilityEvidence,
    Check,
    CheckSet,
    ErrorHandlingSyntax,
)

NAME = "go"

# Go has no single canonical source root the way Rust has `src/` and PHP has
# `app/`/`src/`: a module's packages live anywhere — `cmd/`, `internal/`,
# `pkg/`, or the module root itself — and `*_test.go` files sit beside the
# code they test. The glob that names a Go source file is simply `**/*.go`;
# vendored and generated trees are pruned by the engine's directory skips
# (`vendor/`, `build/`, …). Which files are SOURCES for a given audit stays
# profile-driven (`source.fileGlob`).
FILE_GLOBS = ("**/*.go",)

# Go codegen lands in `target/`-style directory skips OR behind per-file
# suffixes this adapter can name: protoc-gen-go emits `*.pb.go`, sqlc emits
# `*.sql.go`, and mockgen emits `*_mock.go`. Named so the structural sweep's
# uncovered-suffix accounting and any generated-file handling can exclude them
# the way the node adapter names `.d.ts`/`.min.js`/`.bundle.js`.
GENERATED_SUFFIXES: tuple[str, ...] = (".pb.go", ".sql.go", "_mock.go")

# How one Go file declares a dependency on another.
#
#   import "fmt"                          -> fmt
#   import "github.com/gin-gonic/gin"     -> github.com/gin-gonic/gin
#   import gin "github.com/gin-gonic/gin" -> github.com/gin-gonic/gin (alias)
#   import _ "github.com/lib/pq"          -> github.com/lib/pg (blank)
#   import (
#       "myapp/internal/data"             -> myapp/internal/data
#       ...
#   )
#
# Group 1 is the quoted package path for the single form; the group form is
# captured whole as `body` (its per-line paths are all the same shape). A path
# is exactly what `audit_layer_boundaries` would mis-read as a file path — see
# the module docstring.
IMPORT_RE = re.compile(
    r"""^[ \t]*import\s+(?:(?:[A-Za-z_][A-Za-z0-9_]*|\b_\b|\b\.\b)\s+)?"([^"]+)"""  # single
    r"""|^[ \t]*import\s*\(\s*(?P<body>[^)]*)\)""",  # group form
    re.M,
)

# Go `import` targets name package paths, not file paths — see the module
# docstring. audit_layer_boundaries reads this and refuses rather than
# mis-matching a directory rule against a package path.
IMPORT_TARGETS = "module"


# --------------------------------------------------------------------------- #
# Sweep checks (the `Check` / `scan_tree` seam)
# --------------------------------------------------------------------------- #
#
# Two defects a text sweep genuinely catches on a Go backend, each grounded in
# a failure mode rather than style:

# A debug statement left in a handler: `fmt.Println`/`fmt.Printf` write to
# stdout, which in a server is the aggregator, not a response — and a leftover
# `fmt.Printf` in a hot path is the canonical "this was a println service"
# giveaway. The builtin `println(` (lowercase, no package) is the same defect
# one level down. The negative controls are load-bearing: `slog.Info`,
# `log.Printf`, `zap.L().Info` are the project's own structured logger and
# must not be flagged (the `(?<![\w.])` lookbehind stops `anything.fmt.Printf`
# and `x.log.Println` from matching a free call).
DEBUG_STATEMENT_RE = re.compile(
    r"(?<![\w.])fmt\.(?:Print|Printf|Println)\s*\("
    r"|(?<![\w.])println\s*\("
)

# A credential committed as a string literal. Matches a bare assignment
# (`password := "…"`, `Password := "…"`) and the struct/config-literal form a
# Go config actually uses (`Password: "…"`). The lookbehind allows the `DB_`
# prefix (`_` is not alphanumeric) while a lowercase suffix (`mypassword`) is
# still rejected. The negative control this must NOT flag is the correct shape
# `pw := os.Getenv("DB_PASSWORD")`, where the right-hand side is a call, not
# a literal — the `:=` is immediately followed by `os`, not a quote.
PLAINTEXT_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9])(?i:password|passwd|secret|api[_-]?key|access[_-]?token"
    r"|client[_-]?secret)\w*\s*(?::?=\s*\"[^\"\n]{6,}\"|:\s*\"[^\"\n]{6,}\")"
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
#
# Go's comment grammar is the accessible half of the language: `//` line
# comments and a NON-nesting `/* … */` block comment (Go is one of the few
# systems languages whose block comments do not nest — the walker below treats
# the first `*/` as the close, unlike Rust's). The subtle half is the literal
# set: an interpreted string `"…"` with backslash escapes, a RAW backtick string
# `` `…` `` which ends only at the next backtick and carries newlines, and a
# single-quoted rune literal `'x'` / `'\n'` / `'\''`.


def _raw_string_end(source: str, start: int) -> int:
    """Index just past a backtick raw string starting at `start`, or len(source).

    A backtick string has no escapes: it ends at the next backtick, period.
    Newlines inside it are data and must survive blanking, which the caller
    guarantees by only replacing the characters it walks past.
    """
    found = source.find("`", start + 1)
    return len(source) if found == -1 else found + 1


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


def _char_literal_end(source: str, start: int) -> int:
    """Index just past a rune literal `'…'`, or None if it has no close.

    Rune literals carry the same backslash-escape rule as `"…"` strings
    (a doubled `'` inside `'\''`, hex `'\x41'`, unicode `'\u0041'`), so the
    same walk applies with `'` as the terminator.
    """
    i, n = start + 1, len(source)
    while i < n:
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == "'":
            return i + 1
        i += 1
    return None


def _blank_block(out: list, source: str, start: int) -> int:
    """Blank a `/* … */` block from `start`; Go block comments do NOT nest.

    The delimiters are blanked too: leaving `/*` and `*/` in place would put a
    spurious `/` next to live code, and the marker of a comment is not source.
    """
    i, n = start, len(source)
    while i < n:
        if source.startswith("*/", i):
            out[i] = out[i + 1] = " "
            return i + 2
        if out[i] != "\n":
            out[i] = " "
        i += 1
    return i


def blank_comments(source: str) -> str:
    """`source` with every comment replaced by spaces, same length, lines intact.

    Go's comment forms: `//` and NON-nesting `/* … */`. Strings are skipped
    before comments are looked for, so a `"https://…"` literal does not lose
    the rest of its line to a false `//`, a backtick raw string carrying
    `/*`-style text stays whole, and a rune literal `'\''` is stepped over
    rather than opened as a string.
    """
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch == '"':
            i = _normal_string_end(source, i)
            continue
        if ch == "`":
            i = _raw_string_end(source, i)
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
            i = _blank_block(out, source, i)
            continue
        i += 1
    return "".join(out)


def block_comments(source: str) -> list[tuple[int, str]]:
    """Every banner block, as (1-based start line, text).

    Two forms, because Go documents a contract in either: a `/* … */` block,
    and a run of `//` lines — the idiomatic godoc banner above a struct or
    handler is a `//` run, and a banner like `// CONTRACT: …` reads the same
    way.
    """
    blocks = [(source.count("\n", 0, m.start()) + 1, m.group(1))
              for m in re.finditer(r"/\*(.*?)\*/", source, re.DOTALL)]
    for m in re.finditer(r"(?m)((?:[ \t]*//.*\n)+)", source):
        blocks.append((source.count("\n", 0, m.start(1)) + 1, m.group(1)))
    return blocks


# --------------------------------------------------------------------------- #
# Contract-header structural extraction
# --------------------------------------------------------------------------- #
#
# "What does this struct declare", "what does this code read off a receiver",
# "where are the banner comments" — asked by the contract-header engine without
# knowing the language. A Go "screen" is a handler, its "adapter" the service
# struct it delegates to, and the CONTRACT banner is the banner convention the
# audit already reads from config.

CONTRACT_CAPABLE = True  # the engine checks this before trusting the below

# A `type` declaration up to its opening brace: does NOT recurse, so a method
# receiver or a struct embedded in another type never lands in a class span
# twice.
_DECL_HEAD_RE = re.compile(r"\btype\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b")

# A struct field or interface element: a capitalised identifier at line start
# (`Name string`, `Service *UserService`, `Max int `json:"max"``) or an
# embedded exported type standing alone on its line (`Service`). The
# capitalisation is the surface: an unexported field is unreachable outside
# the package, so a contract documenting one documents a fiction. A
# multi-line field type (a nested anonymous struct) is not parsed — only the
# name and its line matter here, exactly as with Rust's fields.
_FIELD_RE = re.compile(r"(?m)^[ \t]*([A-Z]\w*)(?=\s|\s*$)")

# An exported receiver method header: `func (r *OrderAdapter) TotalFor(…`.
# The receiver is whatever sits between `func (` and `)`, so generics
# (`*Store[T]`) and pointer/value receivers (with or without the name) all
# read the same way — the caller filters by text-matching the class name.
_METHOD_RE = re.compile(r"(?m)^[ \t]*func\s*\(([^)]*)\)\s+([A-Z]\w*)\s*\(")

# An exported interface method: `TotalFor(…) error` inside a `type X interface
# { … }` body. Interface methods are the surface of an interface the same way
# `pub fn` is the surface of a Rust trait.
_IFACE_METHOD_RE = re.compile(r"(?m)^[ \t]*([A-Z]\w*)\s*\(")


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
    """(start, end) just inside the braces of a `type X struct/interface` body."""
    for m in _DECL_HEAD_RE.finditer(source):
        if m.group(1) != class_name:
            continue
        brace = source.find("{", m.end())
        if brace == -1:
            return None  # alias (`type X = Y`) or `type X int`: no body
        end = _match_brace(source, brace)
        if end is not None:
            return brace + 1, end
    return None


def class_fields(source: str, class_name: str) -> dict[str, int] | None:
    """`{field name: 1-based line}` for one struct/interface.

    None means the type is not in this source — distinct from `{}` meaning it
    declares nothing (a `type X int` alias), which the caller must not
    conflate. Methods are not included (see `class_members`).
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


def _method_spans(source: str, class_name: str) -> list[tuple[str, int, int]]:
    """`(method, name_offset, body_start)` for every exported receiver method
    of `class_name`, plus the interface methods declared in its body."""
    needle = re.compile(rf"\b\*?\s*{re.escape(class_name)}\b")
    out: list[tuple[str, int, int]] = []
    for m in _METHOD_RE.finditer(source):
        if needle.search(m.group(1)):
            out.append((m.group(2), m.start(2), m.start(2)))
    span = _decl_body_span(source, class_name)
    if span is not None and re.search(
            rf"\btype\s+{re.escape(class_name)}\s+interface\b", source):
        body, base = source[span[0]:span[1]], span[0]
        for im in _IFACE_METHOD_RE.finditer(body):
            out.append((im.group(1), base + im.start(1), base + im.start(1)))
    return out


def class_members(source: str, class_name: str) -> dict[str, int] | None:
    """Like `class_fields`, plus the type's exported methods.

    A service struct's whole purpose is to be a surface, so its exported
    receiver methods (`func (r *OrderAdapter) TotalFor(…)`) belong to the same
    contract a header documents; an interface's declared methods do too.
    Unexported methods are excluded: a caller cannot reach them.
    """
    blanked = blank_comments(source)
    fields = class_fields(source, class_name)
    if fields is None:
        return None
    members = dict(fields)
    for name, offset, body_start in _method_spans(blanked, class_name):
        members.setdefault(name, _line_of(blanked, offset))
    return members


def member_reads(source: str, receiver: str) -> set[str]:
    """Names read off the receiver `receiver` — `svc.TotalFor` and `r.Service`
    both → {"TotalFor", "Service"}.

    Go has no sigil, so `receiver\\.(\\w+)` matches both the local binding and
    a field read, exactly as with Rust's `svc.total`. Comments are blanked
    first, and that is load-bearing: a CONTRACT banner listing `svc.TotalFor`
    would otherwise count as a read, every documented field would look wired,
    and the dead-member check would report zero forever.
    """
    return set(re.findall(rf"(?:\b|\.){re.escape(receiver)}\.(\w+)",
                          blank_comments(source)))


def receiver_aliases(source: str, receiver: str) -> set[str]:
    """Local names bound to the receiver, so reads through them still count.

    `svc := r.Service` (a struct field read into a local) and `svc := service`
    (a package-level service bound directly) both then read `svc.TotalFor(...)`
    — a read of the service. Matching only the conventional name reported
    every member of an aliased service as dead in the Dart adapter's origin
    project; Go binds the same way.
    """
    code = blank_comments(source)
    escaped = re.escape(receiver)
    patterns = (
        rf"(\w+)\s*:=\s*&?\s*\w+\.{escaped}\b",   # svc := r.Service
        rf"(\w+)\s*:=\s*&?\s*{escaped}\b",         # svc := service
        rf"\bvar\s+(\w+)\s*=\s*&?\s*\w+\.{escaped}\b",
        rf"\bvar\s+(\w+)\s*=\s*&?\s*{escaped}\b",
    )
    return {m.group(1) for pattern in patterns for m in re.finditer(pattern, code)} \
        - {receiver}


def _key_matches(key: str, type_name: str) -> bool:
    """Whether a container lookup key names the type: `"order-service"`,
    `"OrderService"`, `"order_service"` and `"OrderServiceKey"` all resolve to
    `OrderService` once non-alphanumerics are dropped and case is folded.
    """
    return (re.sub(r"[^A-Za-z0-9]", "", key).lower()
            == re.sub(r"[^A-Za-z0-9]", "", type_name).lower())


def typed_member_reads(source: str, types) -> dict[str, set[str]]:
    """`{type: members read off any identifier declared with that type}`.

    The receiver is resolved by its declared type, not by what it happens to
    be called — matching one conventional name is the bug that reports real
    members as dead with deletion as the advice. Typed parameters
    (`func f(repo *Repo)`), struct fields (`repo SeaRepo`), locals
    (`repo := &SeaRepo{}`), and type assertions (`repo := c.Get("k").(SeaRepo)`
    — after the assertion the binding's static type IS `SeaRepo`) are all
    followed.

    Raises `CapabilityError` when a binding of one of `types` is drawn from a
    shared-state accessor through an untyped variable whose lookup key names
    the type (`svc := c.MustGet("order-service")`): reads through that
    interface{} are invisible here, and "I cannot tell" must never come back
    as "nothing reads it". Like PHP's `Foo::class` refusal and Rust's
    `state.get::<Foo>()` refusal, this is deliberately narrow — only a lookup
    key that actually names the type raises, so an audit that refuses on
    ordinary code stays an audit people run.
    """
    code = blank_comments(source)
    found: dict[str, set[str]] = {}
    # A binding from a container through an UNTYPED variable: `x := c.Get(KEY)`
    # where KEY is a string literal. If the key names one of `types`, reads
    # through x are invisible to the name-bindings below.
    blind_re = re.compile(
        r"(?:^|[;\n{])\s*(?P<var>\w+)\s*(?:,\s*\w*\s*)?:?=\s*[^;\n]*?"
        r"\.(?:MustGet|Get|GetContext|Locals|Value|Data|Resolve|Inject)"
        r"\s*\(\s*[\"`'](?P<key>[^\"`']*)[\"`']")
    for type_name in types:
        escaped = re.escape(type_name)
        m = blind_re.search(code)
        if m and _key_matches(m.group("key"), type_name):
            raise CapabilityError(
                "typed_member_reads", NAME,
                f"{type_name} is bound to an untyped receiver "
                f"({m.group(0).strip()!r}); reads through it cannot be "
                f"resolved, so this file cannot be used to decide whether "
                f"{type_name}'s members are read")
        names = set()
        # A binding with a declared type: `repo *SeaRepo`, `repo SeaRepo`,
        # `func (s *Dep) f(repo *SeaRepo)` — parameters, struct fields and
        # `var repo SeaRepo` alike. A pointer/array/map wrapper around the
        # type (`*SeaRepo`, `[]*SeaRepo`, `map[string]*SeaRepo`) is matched by
        # `\s+` + wrapper tokens + the type.
        for match in re.finditer(
                rf"(?:^|[\s(,*])(\w+)\s+(?:\*\s*)?(?:\[\]\s*\*\s*)?"
                rf"(?:map\s*\[[^]]*\]\s*\*\s*)?(?:[\w./]+\.)*{escaped}\b",
                code, re.M):
            names.add(match.group(1))
        # A composite literal: `repo := &SeaRepo{ … }`, `repo := SeaRepo{ … }`.
        names |= {m.group(1) for m in re.finditer(
            rf"(\w+)\s*:=\s*&?\s*{escaped}\s*\{{", code)}
        # A type assertion: `repo, ok := c.MustGet("k").(SeaRepo)` — after the
        # assertion the binding's static type is `SeaRepo`, so the field/method
        # reads through it ARE attributable.
        names |= {m.group(1) for m in re.finditer(
            rf"(?:^|[\s(,])\s*(\w+)\s*(?:,\s*\w+\s*)?\s*:?=\s*[^;\n]*?"
            rf"\.\s*\(\s*&?\s*\*?\s*{escaped}\s*\)", code, re.M)}
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
# Go has no `try`/`catch`: a failure is the `err` VALUE bound by assignment
# (`err := f()`), tested (`if err != nil`), and then either narrowed or
# flattened. `catch_var` captures the value variable at either the test site
# or the assignment site. The mangling the audit looks for is the WHOLE error
# reaching a user-facing string — `%+v` on a struct-wrapped error prints
# message plus fields (`%v`/`%s` print only `Error()`, the message, so they
# are the sanctioned shape, and `%w` is the sanctioned *wrap*). The sanctioned
# narrowing tests the error against the app's own type with `errors.As(err,
# &target)` / `errors.Is(err, sentinel)` and then takes its message.
#
# Go has a rune literal `'a'`; string_quotes lists the three quote characters
# that open a STRING. Runes are single characters and harmless either way.
ERROR_HANDLING = ErrorHandlingSyntax(
    # The value model has two sites that bind the error: the TEST
    # (`if err != nil`, group 2) and the ASSIGNMENT (`err := f()`, group 1).
    # The `_, err` multi-assign form is handled by a non-capturing `_ ,`
    # prefix so the error name is what lands in the group. The test site
    # may be the second arm of an init-test (`if _, err := f(); err != nil`)
    # — `;` is passable — but a `{` or newline bounds the search so the body
    # of one `if` cannot borrow an `err != nil` from a later one.
    catch_var=re.compile(
        r"(?m)(?:^|[;\n{])\s*(?:_\s*,\s*)?(\w+)\s*:?=\s*[^;\n]*?\([^;\n()]*\)"
        r"|\bif\s+[^{}\n]*?(?:_\s*,\s*)?(\w+)\s*!=\s*nil\b"),
    # The sanctioned narrowing: test the error's TYPE or IDENTITY against the
    # app's own error — `errors.As(err, &target)` where target is declared
    # `*AppError`, or `errors.Is(err, sentinel)`. The two lookaheads let the
    # variable and the type appear in EITHER order inside the audit's window
    # (the type sits on the `var target *AppError` line, the call on the
    # next), which a linear pattern cannot do.
    type_guard=lambda var, typ: re.compile(
        rf"(?=[\s\S]*\berrors\.(?:As|Is)\s*\(\s*{re.escape(var)}\b)"
        rf"(?=[\s\S]*\b{re.escape(typ)}\b)"),
    # Put the WHOLE error into a string: `%+v` / `%#v`
    # (`fmt.Sprintf("oops: %+v", err)`, `fmt.Errorf("… %+v", err)`), which
    # prints a struct-wrapped error's fields, not just its message. `%v`/`%s`
    # — the message — and `%w` — the sanctioned wrap — are deliberately
    # invisible to this pattern.
    stringify=lambda var: re.compile(
        rf"%[+#]v\b[^)\n]*?,\s*{re.escape(var)}\b"),
    # A failure state being pattern-matched: a type-switch `case *AppError:`,
    # or `errors.As`/`errors.Is` naming the error, marks a state the code
    # actually tests for.
    type_test=lambda cls: re.compile(
        rf"\bcase\s*(?:\*)?(?:[\w./]+\.)?{re.escape(cls)}\b"
        rf"|\berrors\.(?:As|Is)\s*\([^)]*\b{re.escape(cls)}\b"),
    string_quotes=('"', "'", "`"),
    line_comment="//",
)


# --------------------------------------------------------------------------- #
# audit_api_consistency syntax
# --------------------------------------------------------------------------- #
#
# The Go reading of the audit's four checks:
#
#   user_facing  — a response literal under a user-facing envelope key
#                  (`gin.H{"message": "Not found"}`). On a LIBRARY this is
#                  the white-label defect: copy a consumer cannot re-voice.
#   defaulted    — an overridable fallback (`if v == "" { v = "fallback" }`),
#                  so a default literal is not hard-baked.
#   compared     — a literal on either side of an equality: the load-bearing
#                  shape (`if status == "active"`), where the sentinel and
#                  the value are the same string.
#   tappable     — a route declaration, the backend's only honest analogue of
#                  an interaction surface. The `authoredSemantics` check it
#                  feeds is a UI concept; a Go project turns it off with a
#                  written reason rather than run it against a stack with no
#                  semantics API.
API_CONSISTENCY = ApiConsistencySyntax(
    # Go response maps keep the key as a string on the left of the colon
    # (`gin.H{"message": "Not found"}`); a struct-tag declaration
    # (`json:"message"`) puts the literal on the RIGHT of the colon and so
    # never matches the `key: "value"` shape.
    user_facing=re.compile(
        r'"?(?:message|error|detail|description)"?\s*:\s*"([^"\\]{2,})"'),
    # The idiomatic overridable default: a zero-value check feeding a
    # fallback literal. `os.Getenv` has no default argument in Go, so this is
    # the shape the pattern is worth against.
    defaulted=re.compile(
        r'==\s*""\s*\{\s*[^}]{0,80}?=\s*"([^"\\]{2,})"'),
    # Exactly two groups: the audit unpacks `for a, b in COMPARED.findall(line)`.
    compared=re.compile(
        r'(?:==|!=)\s*"([^"\\]{2,})"|"([^"\\]{2,})"\s*(?:==|!=)'),
    # A route declaration. Restricted to the conventional router receiver
    # names (`r`, `e`, `app`, `mux`, `router`, `api`, `srv`, `g`) so an HTTP
    # client's `.Get("X-Header")` is not read as a route. Covers Gin/Echo/Chi/
    # Fiber/net-http verb methods, `Handle`/`HandleFunc`, and `Group` mounts.
    tappable=re.compile(
        r'\b(?:r|e|app|mux|router|api|srv|g)\s*\.\s*'
        r'(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Any|Match|Group|Handle|HandleFunc)'
        r'\s*\(\s*"'),
)


# --------------------------------------------------------------------------- #
# Capability detection (base.LanguageCapabilityProtocol)
# --------------------------------------------------------------------------- #
#
# What a Go routing declaration looks like is a language/framework fact and
# belongs here: the engine asks "does this project route?" and never learns
# what the answer was made of.

# Base routing signatures (stdlib `net/http` and the shared router shapes).
# The verb-method form (`r.GET("/orders", …)`) is deliberately framework-
# agnostic, the way Rust's base set recognises `Router::new().route(…)` across
# axum/poem: however it is spelled, a Go service declares routes, and the
# route coverage audit needs the routesFile to run on all of them. The
# receiver-names constraint keeps an HTTP client's `.Get("X-Header")` from
# registering as a route.
ROUTING_SIGNATURES = (
    re.compile(r"\bhttp\s*\.\s*(?:Handle|HandleFunc|ListenAndServe|NewServeMux|FileServer)"),
    re.compile(r"\bmux\s*\.\s*(?:Get|Post|Put|Patch|Delete|Handle|HandleFunc)\s*\("),
    re.compile(r"\b(?:r|e|app|mux|router|api|srv|g)\s*\.\s*"
               r"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Any|Match|Handle|HandleFunc|Group)"
               r"\s*\(\s*\""),
    re.compile(r"\.\s*Group\s*\(\s*\""),
)

MODEL_CAPABILITY_SIGNATURES = (
    re.compile(r"\bgorm\s*\.\s*(?:Open|Model|Migrator|AutoMigrate)"),
    re.compile(r"\bdb\s*\.\s*AutoMigrate\s*\("),
    re.compile(r"\bsqlx\s*\.\s*(?:Open|Get|GetContext|Queryx|QueryRowx|Select)\b"),
    re.compile(r"\bent\s*\.\s*NewClient\s*\("),
    re.compile(r"\bbun\s*\.\s*(?:NewDB|New)\s*\("),
    re.compile(r"\bsql\s*\.\s*(?:Open|OpenDB)\s*\("),
)

VALIDATION_CAPABILITY_SIGNATURES = (
    re.compile(r'`(?:binding|validate|form|query)\s*:\s*"[^"]+"`'),
    re.compile(r"\bvalidator\s*\.\s*(?:New|Validate)\s*\("),
    re.compile(r"\b(?:validate|v)\s*\.\s*Struct\s*\("),
)

MIDDLEWARE_CAPABILITY_SIGNATURES = (
    re.compile(r"\.\s*Use\s*\("),
    re.compile(r"func\s*\([^)]*\)\s*http\.Handler"),
    re.compile(r"\bhttp\s*\.\s*HandlerFunc\b"),
    re.compile(r"\b(?:gin|echo|fiber)\s*\.\s*(?:Logger|Recovery|BasicAuth|CORS)\s*\("),
)

API_RESOURCES_CAPABILITY_SIGNATURES = (
    re.compile(r'`json:\s*"[^"]+"`'),
    re.compile(r"\b(?:gin|echo|fiber)\s*\.\s*(?:H|Map)\s*\{"),
    re.compile(r"\.\s*JSON\s*\("),
    re.compile(r"json\s*\.\s*NewEncoder\s*\("),
    re.compile(r"json\s*\.\s*Marshal\s*\("),
)

POLICIES_CAPABILITY_SIGNATURES = (
    re.compile(r"\bjwt\s*\.\s*(?:NewWithClaims|Parse|RegisteredClaims|MapClaims)"),
    re.compile(r"golang-jwt/jwt"),
    re.compile(r"\bcasbin\s*\.\s*NewEnforcer\s*\("),
    re.compile(r"\b(?:JWTAuth|RequireAuth|RequirePermission|HasRole|Authorize)\b"),
    re.compile(r"\bmiddleware\s*\.\s*(?:JWT|BasicAuth|KeyAuth)\s*\("),
    re.compile(r"\bClaims\b"),
)

# Framework-specific routing signatures (extends base)
GIN_ROUTING_SIGNATURES = (
    re.compile(r"\bgin\s*\.\s*(?:Default|New)\s*\("),
    re.compile(r"\bgin\s*\.\s*Engine\b"),
    re.compile(r"\bRouterGroup\b"),
)

ECHO_ROUTING_SIGNATURES = (
    re.compile(r"\becho\s*\.\s*New\s*\("),
    re.compile(r"\becho\s*\.\s*(?:Context|Echo)\b"),
)

CHI_ROUTING_SIGNATURES = (
    re.compile(r"\bchi\s*\.\s*(?:NewRouter|NewMux)\s*\("),
    re.compile(r"\bchi\s*\.\s*Router\b"),
)

FIBER_ROUTING_SIGNATURES = (
    re.compile(r"\bfiber\s*\.\s*New\s*\("),
    re.compile(r"\bfiber\s*\.\s*(?:App|Ctx|Map)\b"),
)

# Base capability signatures (framework-agnostic)
CAPABILITY_SIGNATURES = {
    "routing": (
        ROUTING_SIGNATURES,
        "a Go backend declares routes via net/http Handle/HandleFunc, ServeMux, "
        "or verb methods (r.GET(…)) on a router; these are the constructions "
        "that mean the former",
    ),
    "models": (
        MODEL_CAPABILITY_SIGNATURES,
        "a Go backend declares models through a data layer: GORM "
        "(gorm.Open/AutoMigrate), sqlx, ent, bun, or database/sql. These "
        "patterns cover the surface.",
    ),
    "validation": (
        VALIDATION_CAPABILITY_SIGNATURES,
        "a Go backend validates input via struct tags (binding:/validate:) on "
        "request DTOs or the go-playground/validator package. These patterns "
        "cover the surface.",
    ),
    "middleware": (
        MIDDLEWARE_CAPABILITY_SIGNATURES,
        "a Go backend composes middleware with r.Use(…) / app.Use(…) chains or "
        "http.Handler-wrapping functions. These patterns cover the surface.",
    ),
    "api_resources": (
        API_RESOURCES_CAPABILITY_SIGNATURES,
        "a Go backend defines API resources: request/response DTOs with json "
        "tags and response writers (c.JSON(…), json.NewEncoder). These "
        "patterns cover the surface.",
    ),
    "policies": (
        POLICIES_CAPABILITY_SIGNATURES,
        "a Go backend implements authorization: JWT claims parsing, casbin "
        "enforcers, or auth middleware. These patterns cover the surface.",
    ),
}

GIN_CAPABILITY_SIGNATURES = {
    "gin_routing": (GIN_ROUTING_SIGNATURES,
                    "a Gin project builds a gin.Default()/gin.New() engine with "
                    "verb routes and RouterGroup mounts."),
}
ECHO_CAPABILITY_SIGNATURES = {
    "echo_routing": (ECHO_ROUTING_SIGNATURES,
                     "an Echo project builds an echo.New() instance with verb "
                     "routes and echo.Context handlers."),
}
CHI_CAPABILITY_SIGNATURES = {
    "chi_routing": (CHI_ROUTING_SIGNATURES,
                    "a Chi project builds a chi.NewRouter()/chi.NewMux() tree "
                    "with mount and verb routes."),
}
FIBER_CAPABILITY_SIGNATURES = {
    "fiber_routing": (FIBER_ROUTING_SIGNATURES,
                      "a Fiber project builds a fiber.New() app with verb "
                      "routes and fiber.Ctx handlers."),
}

# All capability signatures merged
ALL_CAPABILITY_SIGNATURES = {
    **CAPABILITY_SIGNATURES,
    **GIN_CAPABILITY_SIGNATURES,
    **ECHO_CAPABILITY_SIGNATURES,
    **CHI_CAPABILITY_SIGNATURES,
    **FIBER_CAPABILITY_SIGNATURES,
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
        why="data-layer model declarations (GORM, sqlx, ent, bun, "
            "database/sql). A project using these patterns should declare "
            "source.root so the audit can find them.",
    ),
    Capability(
        name="validation",
        profile_field="source.root",
        why="input validation (struct tags, go-playground/validator). A "
            "project using these patterns should declare source.root so the "
            "audit can find them.",
    ),
    Capability(
        name="middleware",
        profile_field="source.root",
        why="middleware chains (Use(…), http.Handler wrappers). A project "
            "using these patterns should declare source.root so the audit "
            "can find them.",
    ),
    Capability(
        name="api_resources",
        profile_field="source.root",
        why="request/response DTOs and response writers (json tags, c.JSON, "
            "json.NewEncoder). A project using these patterns should declare "
            "source.root so the audit can find them.",
    ),
    Capability(
        name="policies",
        profile_field="source.root",
        why="authorization (jwt claims, casbin, auth middleware). A project "
            "using these patterns should declare source.root so the audit "
            "can find them.",
    ),
    Capability(
        name="gin_routing",
        profile_field="source.routesFile",
        why="a Gin project declares routes on a gin.Engine. Undeclared, no "
            "route check has a file to read and reports clean — inert, not "
            "passing",
    ),
    Capability(
        name="echo_routing",
        profile_field="source.routesFile",
        why="an Echo project declares routes on an echo.Echo instance. "
            "Undeclared, no route check has a file to read and reports clean "
            "— inert, not passing",
    ),
    Capability(
        name="chi_routing",
        profile_field="source.routesFile",
        why="a Chi project declares routes on a chi.Router. Undeclared, no "
            "route check has a file to read and reports clean — inert, not "
            "passing",
    ),
    Capability(
        name="fiber_routing",
        profile_field="source.routesFile",
        why="a Fiber project declares routes on a fiber.App. Undeclared, no "
            "route check has a file to read and reports clean — inert, not "
            "passing",
    ),
)

# Framework-gated routing capabilities and the Go module path that owns them.
FRAMEWORK_ONLY_CAPABILITIES = {
    "gin_routing": "github.com/gin-gonic/gin",
    "echo_routing": "github.com/labstack/echo",
    "chi_routing": "github.com/go-chi/chi",
    "fiber_routing": "github.com/gofiber/fiber",
}

# Go's major frameworks publish under major-version subpaths once past v1
# (`github.com/labstack/echo/v4`, `github.com/go-chi/chi/v5`, …), so module
# matching tries the plain path and every /vN subpath.
_MODULE_VARIANTS = tuple(
    f"{base}/v{n}" for base in () for n in range(2, 9)
)


def _module_variants(module: str) -> tuple[str, ...]:
    return (module,) + tuple(f"{module}/v{n}" for n in range(2, 9))


def _expand_file_glob(repo: Path, pattern: str) -> list:
    """The concrete files a `source.routesFile` value names.

    The value may be a single file (`cmd/server/main.go`) or a glob
    (`cmd/*/main.go`); both are resolved repo-relative, and a pattern that
    names nothing yields an empty list (the caller's own empty-sweep refusal
    then stands — no evidence is not evidence of absence).
    """
    path = Path(pattern)
    if path.is_absolute():
        return [path] if path.is_file() else []
    return sorted(repo.glob(pattern))


def _manifest_text(root: Path) -> str:
    path = root / "go.mod"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _declares_module(manifest: str, module: str) -> bool:
    """Whether `go.mod` names the module as a dependency (require/replace).

    The module's OWN identity — the `module` directive line — is excluded: a
    project whose module path happens to contain a framework name is not using
    that framework. An unrelated neighbour (`github.com/gin-gonic/gin-contrib`)
    must not match either, so the path is anchored at a whitespace/end boundary
    the way `require … vX.Y.Z` lines are laid out.
    """
    for variant in _module_variants(module):
        needle = re.compile(
            rf"(?m)^[ \t]*(?:[A-Za-z0-9_.-]+\s+)?{re.escape(variant)}(?:\s|$)")
        for line in manifest.splitlines():
            s = line.strip()
            if s.startswith("module ") or s.startswith("//") or not s:
                continue
            if needle.search(line):
                return True
    return False


def _source_tree(ctx: AdapterContext, root: Path) -> Path:
    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    return base if base.is_dir() else root


def _uses_module(base: Path, module: str) -> bool:
    """Whether any hand-written `.go` under `base` imports the module."""
    for path in base.rglob("*.go"):
        rel = path.relative_to(base)
        if "vendor" in rel.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for variant in _module_variants(module):
            if f'"{variant}' in text:
                return True
    return False


def _looks_go(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a Go project, not just "a directory".

    Conservative and cheap: any of a root `go.mod` or a `.go` file under the
    configured source tree is enough. A false "yes" costs extra capability
    findings; a false "no" leaves a real Go project's capabilities unexamined.
    """
    root = Path(str(ctx.repo))
    if (root / "go.mod").is_file():
        return True
    base = _source_tree(ctx, root)
    return any(base.rglob("*.go"))


def _looks_framework(ctx: AdapterContext, module: str) -> bool:
    """Whether this tree reads as a `module` application."""
    root = Path(str(ctx.repo))
    if _declares_module(_manifest_text(root), module):
        return True
    base = _source_tree(ctx, root)
    return _uses_module(base, module)


def capabilities(ctx: AdapterContext) -> list:
    """What this adapter can be asked about. See base.LanguageCapabilityProtocol.

    Framework-specific routing capabilities are offered only to projects that
    read as that framework (see `_looks_framework`). On any other Go tree they
    are simply not asked — a project is neither measured nor excused for
    capabilities it never claimed.

    `ctx` is None when a caller is merely probing which capabilities exist
    (`detect_capability` is not reached); treat that as "assume any framework"
    rather than crashing on `ctx.repo`.
    """
    caps = list(CAPABILITIES)
    if ctx is None:
        return caps
    for cap_name, module in FRAMEWORK_ONLY_CAPABILITIES.items():
        if not _looks_framework(ctx, module):
            caps = [c for c in caps if c.name != cap_name]
    return caps


def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    """Whether this project does `name`, or a refusal.

    Three separate refusals, all of which would otherwise arrive as a flat "no":
    an unknown capability, a source root that is not there, and a source root
    holding no Go at all. The last is the one that bites — point the adapter at
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
    for path in root.rglob("*.go"):
        rel = path.relative_to(root)
        if "vendor" in rel.parts:
            continue
        sources.append(path)

    # Routing evidence conventionally lives at a predictable entry — cmd/,
    # main.go — and this capability's own profile_field is `source.routesFile`.
    # Scan the declared routes file(s) as well, so a real layout is measured
    # rather than reported as "unused" by a scan that never saw its
    # declarations.
    routes_rel = (ctx.profile.get("source", {}) or {}).get("routesFile")
    if routes_rel:
        for candidate in _expand_file_glob(repo, routes_rel):
            if candidate not in sources:
                sources.append(candidate)

    if not sources:
        raise CapabilityError(
            name, NAME,
            f"no hand-written .go under {root_rel!r} — absence of evidence in "
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