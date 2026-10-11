r"""PHP language adapter.

The suite's second shipped language, and the one the backend domain actually
runs on: PHP ^8.0 backends in the Lumen/Laravel mould (routes files, service
classes, middleware) and plain PHP libraries (src/ + tests/). The reference
consumer is `jikan-me/jikan-rest` (Lumen, 106 GET-only endpoints) and its
sibling library `jikan-me/jikan` (67 Request classes, 168 models).

Everything language-shaped lives here, per the seam contract in `base.py`:
how a file imports another, how a catch clause binds, where a user-facing
response literal appears, how a class declares its members, what a comment is.
The engine and the four seam-consuming audits (`audit_layer_boundaries`,
`audit_error_handling`, `audit_api_consistency`, `audit_contract_headers`) know
none of it.

## How PHP imports are shaped, and what that means for layer rules

PHP imports by namespace (`use App\Models\User;`) or by path
(`require __DIR__.'/x.php';`). A PSR-4 namespace IS conventionally its
directory — `App\Models\User` ⇔ `app/Models/User.php` — so a namespace root
carries the same hierarchical, prefix-comparable shape as Dart's
`package:foo/` targets. `IMPORT_RE` therefore emits the `use` target as-is,
and `audit_layer_boundaries` rules phrase `mustNotImport` with the namespace
root the project actually uses (`App\Http\`, `Domain\Shipping\`) or with a
repo-rooted path for `require`d files. Both compare by prefix; neither needs
the engine to learn what a namespace is.

## Known gaps, stated so a clean run is never mistaken for a full one

  * `ERROR_HANDLING.line_comment` is `//`. PHP also has `#` comments (not
    `#[` attributes, which are PHP 8 syntax and are left alone by
    `blank_comments`); a `#`-commented mention of an anti-pattern can
    therefore read as the anti-pattern in the error-handling window scan.
    `//` covers the overwhelming majority of real code.
  * `ERROR_HANDLING.stringify` matches the shapes that put the WHOLE
    exception — message plus stack trace — into a string: a `(string)` cast
    and a double-quoted string interpolation. Bare `"$e"` interpolation is
    only matched when the variable sits inside the quotes, because `$e` is
    also how ordinary code refers to the variable (`throw $e;`) and a
    variable-use pattern would flag every rethrow as mangling. An
    interpolated heredoc containing `{$e}` is not matched either; that path
    exists but is rare enough to leave to config review.
  * `API_CONSISTENCY.tappable` maps "interaction surface" to route
    declarations — the backend's only honest analogue of a tap target. The
    `authoredSemantics` check it feeds is a UI concept; a PHP project turns
    it off with a written reason (the audit requires an explicit decision on
    every check before it will run at all, so nothing here runs by default).
  * Contract extraction reads class-body statements and promoted constructor
    properties. A property assembled by a trait, a macro, or a runtime
    container is invisible here; reads through an untyped binding resolved
    from `Foo::class` raise `CapabilityError` rather than counting as "no
    reads".
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import (AdapterContext, ApiConsistencySyntax, Capability,
                   CapabilityError, CapabilityEvidence, Check, CheckSet,
                   ErrorHandlingSyntax)

NAME = "php"

# The canonical layout of a PHP backend or library, whichever the project has.
# Which files are SOURCES for a given audit stays profile-driven
# (`source.fileGlob`); these globs feed the structural sweep (layer dirs,
# uncovered-suffix accounting, the seam proof) and the error-handling suffix
# filter.
FILE_GLOBS = ("app/**/*.php", "routes/*.php", "src/**/*.php", "tests/**/*.php")

# PHP has no standard codegen suffix the way Dart has `.g.dart`; generated
# code lives in vendor/ (directory-scoped skips handle that). An empty tuple
# is honest here: `endswith(())` is False, so every file counts as hand-written.
GENERATED_SUFFIXES: tuple[str, ...] = ()

# How one PHP file declares a dependency on another.
#
#   use App\Models\User;                  -> group 1: App\Models\User
#   use App\Http\Controllers\Foo as Bar;  -> group 1: App\Http\Controllers\Foo
#   use function App\helpers;              -> group 1: App\helpers
#   require __DIR__.'/views/x.php';       -> group 2: ./views/x.php
#   include 'bootstrap.php';              -> group 2: bootstrap.php
#
# `import_targets` takes the first non-None group, so the two forms share one
# regex without a second group ever shadowing the first. A fully-qualified
# inline reference (`new \App\X()`) is deliberately not matched: the `use`
# statement is the convention, and chasing every inline FQN is how a structural
# audit starts reading expressions instead of declarations.
IMPORT_RE = re.compile(
    r"^[ \t]*use\s+(?:(?:function|const)\s+)?([\w\\]+)\s*(?:as\s+\w+)?\s*;"
    r"|^[ \t]*(?:require|require_once|include|include_once)\s*\(?\s*"
    r"['\"]([^'\"]+?)['\"]",
    re.M,
)


# --------------------------------------------------------------------------- #
# Sweep checks (the `Check` / `scan_tree` seam)
# --------------------------------------------------------------------------- #
#
# Two defects a text sweep genuinely catches on a PHP backend, each grounded
# in failure modes rather than style:

# Laravel/Lumen's global debug helpers: dd(), ddd(), dump(), plus the raw PHP
# var_dump()/print_r(). In a route handler a dd() dumps its argument AND halts
# the request — in production that leaks payload, config and stack into the
# response. The lookbehind scopes the match to the global functions: a method
# call (`$log->dump(`, `Foo::dump(`) is a project's own API, not the debug
# helper, and flagging those is how a check becomes noise people disable.
DEBUG_STATEMENT_RE = re.compile(r"(?<![\w>:])(?:ddd|dd|dump|var_dump|print_r)\s*\(")

# A credential committed as a string literal. Three assignment shapes occur
# in real config and all three are matched: `$password = '…'` (statement),
# `['api_key' => '…']` (array pair, keyword inside its own quotes), and
# `$cfg['secret'] = '…'` / `$cfg['Secret'] = '…'` (offset key, closing quote
# and bracket between keyword and operator; config keys appear in several
# casings, hence the case-insensitive keyword group). The comparison forms
# are rejected — `==`, `===`, `!=`, `!==` all fail the operator lookbehinds
# — so an equality test on a variable is never read as an assignment. The
# negative control this must NOT flag — verified in verify_seam's php leg
# the same way — is the correct shape: `$password = env('DB_PASSWORD');`,
# where the right-hand side is a reference, not a literal.
PLAINTEXT_SECRET_RE = re.compile(
    r"(?<![\w])(?i:password|passwd|secret|api[_-]?key|access[_-]?token"
    r"|client[_-]?secret)['\"]?\]?\s*"
    r"(?<![=!])(?:=>|=(?!=))\s*['\"][^'\"\n]{6,}['\"]"
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
# original file, so any transform that shifted offsets would make every
# finding point at the wrong line (the measured failure that fixed this in the
# Dart adapter).

# Heredoc/nowdoc bodies run to a closing identifier; a `//` inside one is
# text, not a comment. PHP 7.3+ allows the closing identifier to be indented.
_HEREDOC_RE = re.compile(
    r"<<<[ \t]*(['\"]?)([A-Za-z_]\w*)\1\r?\n.*?\r?\n[ \t]*\2\b", re.S)


def blank_comments(source: str) -> str:
    """`source` with every comment replaced by spaces, same length, lines intact.

    PHP's comment forms: `//`, `#` (but NOT `#[` — a PHP 8 attribute), and
    non-nesting `/* … */`. Strings are scanned first so a `'https://…'`
    literal does not lose the rest of its line to a false `//`. Single-quoted
    strings recognise only `\\` and `\'` as escapes; double-quoted ones share
    the backslash rule, which is enough to keep a trailing quote from ending a
    string early. Heredoc and nowdoc bodies are skipped whole.
    """
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch in "'\"":
            quote = ch
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if source.startswith("<<<", i):
            heredoc = _HEREDOC_RE.match(source, i)
            if heredoc:
                i = heredoc.end()
                continue
        if source.startswith("//", i) or (
                ch == "#" and not source.startswith("#[", i)):
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            stop = n if end == -1 else end + 2
            # PHP block comments do not nest — the first `*/` ends the block,
            # which is the whole difference from the Dart form of this scan.
            for j in range(i, stop):
                if out[j] != "\n":
                    out[j] = " "
            i = stop
            continue
        i += 1
    return "".join(out)


def block_comments(source: str) -> list[tuple[int, str]]:
    """Every `/* … */` block, as (1-based start line, text). Non-nesting."""
    return [(source.count("\n", 0, m.start()) + 1, m.group(1))
            for m in re.finditer(r"/\*(.*?)\*/", source, re.DOTALL)]


def _blank_strings_and_attributes(source: str) -> str:
    """`blank_comments(source)` with string literals and `#[…]` attribute
    blocks blanked to spaces too, same length throughout.

    Only the class-body member walk needs this, and there it is load-bearing
    rather than cosmetic:

      * an unbalanced `(` or `[` inside a literal (`private $m = "foo(";`)
        would skew the depth counter and silently swallow every declaration
        after it — members lost, not miscounted;
      * a `,` inside a constructor-parameter default would split the
        parameter list in the wrong place and lose promoted properties;
      * an attribute (`#[Route('/x')]`) preceding a declaration would prefix
        the statement and defeat the `^…`-anchored member regexes, hiding
        decorated methods — the common shape in attribute-routed projects.

    Blank, never delete: offsets must survive so reported line numbers still
    point into the original file.
    """
    out = list(blank_comments(source))
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch in "'\"":
            quote = ch
            start = i
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            for j in range(start, min(i, n)):
                if out[j] != "\n":
                    out[j] = " "
            continue
        if source.startswith("#[", i):
            # Attribute args may nest parens and contain strings (`#[Assert\Regex('/a[b]')]`);
            # count brackets with the same string-skipping rule.
            start = i
            depth, j = 0, i + 1
            while j < n:
                cj = source[j]
                if cj in "'\"":
                    quote = cj
                    j += 1
                    while j < n:
                        if source[j] == "\\":
                            j += 2
                            continue
                        if source[j] == quote:
                            j += 1
                            break
                        j += 1
                    continue
                if cj == "[":
                    depth += 1
                elif cj == "]":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            for k in range(start, min(j, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# Structural extraction, for audit_contract_headers
# --------------------------------------------------------------------------- #
#
# "What does this class declare", "what does this code read off a receiver",
# "where are the banner comments" — asked by the contract-header engine without
# knowing the language. A PHP "screen" is a controller, its "adapter" the
# service class it delegates to, and the CONTRACT banner is the same block
# comment convention the audit already reads from config.

CONTRACT_CAPABLE = True  # the engine checks this before trusting the below


def _class_body_span(source: str, class_name: str) -> tuple[int, int] | None:
    match = re.search(
        rf"\b(?:class|interface|trait|enum)\s+{re.escape(class_name)}\b"
        rf"[^{{;]*{{", source)
    if not match:
        return None
    depth, start = 0, match.end() - 1
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return start + 1, i
    return None


# A class-body property: `private string $name;`, `public ?Foo $bar = null;`,
# legacy `protected $x;`, `public static array $cache = [];`. The visibility
# keyword is required — a bare `$var = …;` at class-body depth is a stray
# statement, not a declaration. `&` joins the type class for intersection
# types (`Foo&Bar $x`).
_PROPERTY_RE = re.compile(
    r"^\s*(?:public|protected|private|var)\s+(?:readonly\s+)?(?:static\s+)?"
    r"(?:[\w\\|?&]+\s+)?\$(\w+)")

# A promoted constructor property: `function __construct(private readonly
# Foo $svc, protected int $n = 3)`. PHP's most common way to declare a
# service's dependencies, and missing it would report a real field as
# undeclared — a false stale-entry on a correct contract header, the failure
# that gets an audit switched off.
_PROMOTED_RE = re.compile(
    r"(?:public|protected|private)\s+(?:readonly\s+)?"
    r"(?:[\w\\|?&]+\s+)?\$(\w+)")

# A method declaration. PHP modifiers are order-insensitive (`final public
# function`, `abstract public function`, `public final function`), so the
# prefix is a repeated-modifier group rather than one fixed order; `&?`
# covers reference-returning `function &getThing()`. Privacy is read from
# the words before `function` (see _member_names) rather than a second
# fixed-order regex, which would mis-handle the same modifier permutations.
_METHOD_RE = re.compile(
    r"^\s*(?:(?:abstract|final|public|protected|private|static)\s+)*"
    r"function\s+&?(\w+)\s*\(")


def _member_names(stmt: str, methods: bool) -> list[str]:
    """The members one class-body statement declares (a constructor may
    promote several properties, hence a list)."""
    prop = _PROPERTY_RE.match(stmt)
    if prop:
        return [prop.group(1)]
    if re.match(
            r"^\s*(?:(?:abstract|final|public|protected|private|static)\s+)*"
            r"function\s+__construct\b", stmt):
        # Promoted properties live in the constructor's parameter list; they
        # are real fields (the object carries them), so they count.
        open_paren = stmt.find("(")
        names: list[str] = []
        if open_paren >= 0:
            depth, buf = 0, ""
            for ch in stmt[open_paren:]:
                if ch == "(":
                    depth += 1
                    continue
                if ch == ")":
                    depth -= 1
                    if depth == 0:
                        found = _PROMOTED_RE.match(buf.strip())
                        if found:
                            names.append(found.group(1))
                        break
                if depth == 1 and ch == ",":
                    found = _PROMOTED_RE.match(buf.strip())
                    if found:
                        names.append(found.group(1))
                    buf = ""
                    continue
                if depth >= 1:
                    buf += ch
        return names
    if methods:
        signature = stmt.split("{", 1)[0]
        found = _METHOD_RE.match(signature)
        # Only the public surface: a private/protected method is unreachable
        # for a caller, so a contract header documenting one would be
        # documenting a fiction; `__`-prefixed methods are framework magic,
        # not a contract anyone documents.
        head = signature.split("function", 1)[0]
        if (found and not found.group(1).startswith("__")
                and not re.search(r"\b(?:protected|private)\b", head)):
            return [found.group(1)]
    return []


def _members(source: str, class_name: str, methods: bool) -> dict[str, int] | None:
    # Strings and attribute blocks blanked, not just comments: a `(` inside a
    # literal would skew the depth counter and drop every declaration after
    # it (see _blank_strings_and_attributes).
    blanked = _blank_strings_and_attributes(source)
    span = _class_body_span(blanked, class_name)
    if span is None:
        return None
    start, end = span
    fields: dict[str, int] = {}
    depth, buf_start, buf = 0, start, []

    def record(stmt: str, offset: int):
        # The buffer picks up the newline and indentation that FOLLOW the
        # previous terminator; the declaration itself starts at the first
        # non-blank character, and reporting it one line high would send
        # every dead-member finding at the wrong line.
        lead = len(stmt) - len(stmt.lstrip())
        line = blanked.count("\n", 0, offset + lead) + 1
        for name in _member_names(stmt, methods=methods):
            fields.setdefault(name, line)

    for i in range(start, end):
        ch = blanked[i]
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if depth == 0 and ch == ";":
            record("".join(buf), buf_start)
            buf, buf_start = [], i + 1
        elif depth == 0 and ch == "}":
            # A brace-bodied member ends here (a method, or a property with an
            # array/arrow-function initializer). Still worth reading: the
            # signature before the `{` is what it declares.
            record("".join(buf), buf_start)
            buf, buf_start = [], i + 1
        else:
            if not buf:
                buf_start = i
            buf.append(ch)
    return fields


def class_fields(source: str, class_name: str) -> dict[str, int] | None:
    """`{property name: 1-based line}` for one class.

    None means the class is not in this source — distinct from `{}` meaning it
    declares nothing, which the caller must not conflate. Promoted constructor
    properties are included (they are fields the object carries); methods are
    not (see `class_members`).
    """
    return _members(source, class_name, methods=False)


def class_members(source: str, class_name: str) -> dict[str, int] | None:
    """Like `class_fields`, plus the class's public methods.

    A service class whose whole purpose is to be a surface offers query and
    action methods the same way a Dart adapter offers getters — a contract
    header documenting `totalFor(string $id)` is documenting a real member.
    Private and protected methods are excluded: a caller cannot reach them.
    """
    return _members(source, class_name, methods=True)


def member_reads(source: str, receiver: str) -> set[str]:
    """Names read off the receiver `receiver` — `$svc->totalFor` and
    `$this->svc->totalFor` both → {"totalFor"}.

    Two prefix forms, and both are required: `$receiver->` for the local
    variable, and `->receiver->` for a property read (`$this->svc->x`,
    `$ctrl->svc->x`). Dart's pattern is sigil-free — `receiver\.(\w+)` — so
    `this.adapter.x` matched with no special case; PHP variables always
    carry `$`, and requiring it immediately before the name would miss the
    property form entirely. Measured shape, jikan-rest and any Lumen
    controller: `$this->service->totalFor($id)`. A miss here reports every
    field of the service as dead with deletion as the advice — the exact
    failure this function exists to prevent.

    Comments are blanked first, and that is load-bearing: a CONTRACT banner
    listing `$svc->totalFor` would otherwise count as a read, every documented
    field would look wired, and the dead-member check would report zero
    forever — the exact measured failure this has in the Dart adapter.
    """
    return set(re.findall(rf"(?:\$|->){re.escape(receiver)}->(\w+)",
                          blank_comments(source)))


def receiver_aliases(source: str, receiver: str) -> set[str]:
    """Local names bound to the receiver, so reads through them still count.

    `$svc = $this->service;` then `$svc->totalFor(...)` is a read of the
    service. Matching only the conventional name reported every member of an
    aliased service as dead in the Dart adapter's origin project; PHP binds
    the same way (`$a = $this->service;`, `$a = $service;`), and the right-
    hand side of the second form carries its own `$`.
    """
    code = blank_comments(source)
    escaped = re.escape(receiver)
    patterns = (
        rf"\$(\w+)\s*=\s*\$this->{escaped}\s*;",
        rf"\$(\w+)\s*=\s*\${escaped}\s*;",
    )
    return {m.group(1) for pattern in patterns for m in re.finditer(pattern, code)} \
        - {receiver}


def typed_member_reads(source: str, types) -> dict[str, set[str]]:
    """`{type: members read off any identifier declared with that type}`.

    The receiver is resolved by its declared type, not by what it happens to
    be called — matching one conventional name is the bug that reported real
    members as dead with deletion as the advice in the Dart adapter's origin
    project. Typed parameters (`function f(Foo $x)`), properties
    (`private Foo $x;`), catch bindings (`catch (Foo $e)`) and locals
    (`$x = new Foo();`) are all followed; a namespace prefix
    (`function f(App\Foo $x)`) resolves to the same type as the imported
    short name.

    No word-list guard sits between the type and the name, unlike Dart's
    version: a PHP binding is `$`-prefixed, so `class X extends Y` or
    `instanceof Foo` can never be captured as a "variable" here — the sigil
    is the guard.

    Raises `CapabilityError` when a binding of one of `types` is resolved from
    `Foo::class` through an untyped variable (`$x = $container->get(Foo::class)`):
    reads through it are invisible here, and "I cannot tell" must never come
    back as "nothing reads it". The refusal is deliberately narrow — only an
    explicitly untyped `::class` binding raises — because an audit that
    refuses on ordinary code is an audit nobody runs.
    """
    code = blank_comments(source)
    found: dict[str, set[str]] = {}
    for type_name in types:
        escaped = re.escape(type_name)
        blind = re.search(rf"\$\w+\s*=[^;]*\b{escaped}::class\b", code)
        if blind:
            raise CapabilityError(
                "typed_member_reads", NAME,
                f"{type_name} is bound to an untyped receiver "
                f"({blind.group(0).strip()!r}); reads through it cannot be "
                f"resolved, so this file cannot be used to decide whether "
                f"{type_name}'s members are read")
        names = set()
        # `Foo $x`, `?Foo $x`, `readonly Foo $x`, `Foo|null $x`, `App\Foo $x`,
        # and the trailing segment of a union (`…|Foo $x`).
        for match in re.finditer(
                rf"(?<![\w\\])(?:[\w\\]+\\)?{escaped}\s+\$(\w+)", code):
            names.add(match.group(1))
        names |= {m.group(1) for m in re.finditer(
            rf"\$(\w+)\s*=\s*new\s+\\?{escaped}\b", code)}
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
# `catch (ApiException $e)` binds the variable; `$e instanceof ApiException`
# is the sanctioned type test; `(string) $e` or "…{$e}…" puts the WHOLE
# exception — message plus stack trace — into a string, which is the mangling
# this audit exists to catch. `$e->getMessage()` is the sanctioned narrowing
# and is deliberately invisible to the stringify pattern.
ERROR_HANDLING = ErrorHandlingSyntax(
    catch_var=re.compile(r"\bcatch\s*\(\s*[\w\\|]+\s+\$(\w+)\s*\)"),
    # No `\b` before the `$` — `$` is not a word character, so a word
    # boundary never holds in front of it and the pattern would match
    # nothing at all.
    type_guard=lambda var, typ: re.compile(
        rf"\${re.escape(var)}\s+instanceof\s+(?:\\?[\w\\]*\\)?"
        rf"{re.escape(typ)}\b"),
    stringify=lambda var: re.compile(
        rf"\(\s*string\s*\)\s*\${re.escape(var)}\b"
        rf"|\{{\s*\${re.escape(var)}\s*\}}"
        rf"|\"[^\"\n]*\${re.escape(var)}(?!\s*(?:->|::))[^\"\n]*\""),
    type_test=lambda cls: re.compile(
        rf"\binstanceof\s+(?:\\?[\w\\]*\\)?{re.escape(cls)}\b"),
    string_quotes=("'", '"'),
    line_comment="//",
)


# --------------------------------------------------------------------------- #
# audit_api_consistency syntax
# --------------------------------------------------------------------------- #
#
# The backend reading of the audit's four checks:
#
#   user_facing  — a response literal under a user-facing envelope key
#                  (`'message' => 'Not found'`). On a LIBRARY — the jikan
#                  model — this is the white-label defect itself: copy a
#                  consumer cannot re-voice without forking.
#   defaulted    — a parameter default (`string $msg = 'fallback'`): the
#                  overridable shape, so a default literal is not hard-baked.
#   compared     — a literal on either side of an equality: the load-bearing
#                  shape (`$state == 'Unknown'`), where the sentinel and the
#                  value are the same string.
#   tappable     — a route declaration, the backend's only honest analogue of
#                  an interaction surface. The `authoredSemantics` check it
#                  feeds is a UI concept; PHP projects turn that check off
#                  with a written reason rather than run it against a stack
#                  with no semantics API (the audit requires an explicit
#                  decision on every check before it runs at all).
API_CONSISTENCY = ApiConsistencySyntax(
    # PHP array keys are quoted strings (`['message' => 'Not found']`), so
    # the key's own quotes are optional-but-matched around the keyword; the
    # word-boundary guard moves to a lookbehind that holds either way.
    user_facing=re.compile(
        r"(?<![\w])['\"]?(?:message|error|detail|description)['\"]?"
        r"\s*=>\s*'([^'\\]{2,})'"),
    defaulted=re.compile(r"\$\w+\s*(?:\?\s*[\w\\]+\s+)?=\s*'([^'\\]{2,})'"),
    compared=re.compile(
        r"(?:===|!==|==|!=)\s*'([^'\\]{2,})'|'([^'\\]{2,})'\s*(?:===|!==|==|!=)"),
    tappable=re.compile(
        r"\bRoute::(?:get|post|put|patch|delete|any|fallback|match)\s*\("
        r"|\$router->(?:get|post|put|patch|delete|options|any|route)\s*\("),
)


# --------------------------------------------------------------------------- #
# Capability detection (base.LanguageCapabilityProtocol)
# --------------------------------------------------------------------------- #
#
# What a PHP routing declaration looks like is a language/framework fact and
# belongs here: the engine asks "does this project route?" and never learns
# what the answer was made of.

ROUTING_SIGNATURES = (
    # Laravel/Lumen facades over the router, in every real routes file.
    re.compile(
        r"\bRoute::(?:get|post|put|patch|delete|options|any|fallback|match"
        r"|middlewareGroup|group)\s*\("),
    # Lumen's closure style: $router->get('/x', function () {…}).
    re.compile(
        r"\$router->(?:get|post|put|patch|delete|options|any|route|group)\s*\("),
    # PHP 8 attributes (Symfony 6+, and route attributes generally).
    re.compile(r"@(?:Route|Get|Post|Put|Patch|Delete|Head|Options|Fallback)\b"),
)

CAPABILITY_SIGNATURES = {
    "routing": (
        ROUTING_SIGNATURES,
        "a PHP backend either declares its routes in a routes file (or an "
        "attributes-annotated controller) or has none; these are the "
        "constructions that mean the former",
    ),
}

CAPABILITIES = (
    Capability(
        name="routing",
        profile_field="source.routesFile",
        why="every route-aware check reads the file this field names. "
            "Undeclared, the check has nothing to read and reports clean — "
            "inert, not passing",
    ),
)


def capabilities(ctx: AdapterContext) -> list:
    """What this adapter can be asked about. See base.LanguageCapabilityProtocol."""
    return list(CAPABILITIES)


def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    """Whether this project does `name`, or a refusal.

    Three separate refusals, all of which would otherwise arrive as a flat
    "no": an unknown capability, a source root that is not there, and a
    source root holding no PHP at all. The last is the one that bites — point
    the adapter at a workspace stub and every capability reads as absent,
    which is a clean report about a tree nobody looked at.
    """
    signatures = CAPABILITY_SIGNATURES.get(name)
    if signatures is None:
        raise CapabilityError(name, NAME,
                              f"no signature set for this capability; known: "
                              f"{sorted(CAPABILITY_SIGNATURES)}")
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

    sources = [p for p in root.rglob("*.php")
               if "vendor" not in p.relative_to(root).parts]
    if not sources:
        raise CapabilityError(
            name, NAME,
            f"no hand-written .php under {root_rel!r} — absence of evidence in "
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
