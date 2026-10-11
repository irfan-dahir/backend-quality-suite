r"""Node.js/TypeScript language adapter.

The suite's third shipped language, covering the JavaScript/TypeScript backend
ecosystem: Express, Fastify, NestJS, Hono, Koa, and AdonisJS. This adapter
brings the suite's audit capabilities to the largest backend ecosystem by
package count.

Everything language-shaped lives here, per the seam contract in `base.py`:
how a file imports another, how a catch clause binds, where a user-facing
response literal appears, how a class declares its members, what a comment is.
The engine and the four seam-consuming audits (`audit_layer_boundaries`,
`audit_error_handling`, `audit_api_consistency`, `audit_contract_headers`) know
none of it.

## How Node.js imports are shaped, and what that means for layer rules

Node.js imports by ES6 module syntax (`import x from 'y'`) or CommonJS
(`require('y')`). Both resolve by PATH, not by namespace like PHP — so a
layer-boundaries rule phrases `mustNotImport` with a path prefix (`../config/`,
`@app/database/`) or a package name (`express-validator`). Both compare by
substring or prefix; neither needs the engine to learn what a module specifier
is.

A path starting with `.` is a local file; anything else is a package. Both are
emitted by `IMPORT_RE` — a project's own rules decide which matters.

## Known gaps, stated so a clean run is never mistaken for a full one

  * `ERROR_HANDLING.line_comment` is `//`. JavaScript/TypeScript has no
    `#` comment form, so this is complete for line comments.
  * `ERROR_HANDLING.stringify` matches the shapes that put the WHOLE
    exception — message plus stack trace — into a string: a template literal
    (`` `${e}` ``), a `String(e)` call, and an implicit string concatenation
    (`'' + e`). Bare `e.message` is deliberately NOT matched: that is the
    sanctioned narrowing, and flagging it would report every correct handler
    as mangling.
  * `API_CONSISTENCY.tappable` maps "interaction surface" to route
    declarations — the backend's only honest analogue of a tap target. The
    `authoredSemantics` check it feeds is a UI concept; a Node.js project
    turns it off with a written reason (the audit requires an explicit
    decision on every check before it will run at all, so nothing here runs
    by default).
  * Contract extraction reads class-body properties and methods. A property
    assembled by a decorator, a mixin, or a runtime container is invisible
    here; reads through an untyped binding raise `CapabilityError` rather
    than counting as "no reads".
  * Template literal interpolation (`` `${expr}` ``) is not resolved. A
    secret assembled from parts (`${prefix}-${suffix}`) is not matched; only
    a complete literal is.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import (AdapterContext, ApiConsistencySyntax, Capability,
                   CapabilityError, CapabilityEvidence, Check, CheckSet,
                   ErrorHandlingSyntax)

NAME = "node"

# The canonical layout of a Node.js backend or library, whichever the project
# has. Which files are SOURCES for a given audit stays profile-driven
# (`source.fileGlob`); these globs feed the structural sweep (layer dirs,
# uncovered-suffix accounting, the seam proof) and the error-handling suffix
# filter.
FILE_GLOBS = ("src/**/*.ts", "src/**/*.js", "src/**/*.tsx", "src/**/*.jsx",
              "app/**/*.ts", "app/**/*.js", "lib/**/*.ts", "lib/**/*.js",
              "routes/**/*.ts", "routes/**/*.js",
              "controllers/**/*.ts", "controllers/**/*.js",
              "services/**/*.ts", "services/**/*.js",
              "test/**/*.ts", "test/**/*.js",
              "tests/**/*.ts", "tests/**/*.js")

# JavaScript/TypeScript has no codegen suffix the way Dart has `.g.dart`;
# generated code lives in `node_modules/` (directory-scoped skips handle that).
# `.d.ts` (declaration files) and `.min.js` (minified bundles) are excluded
# by suffix here rather than by directory, because they can appear anywhere.
GENERATED_SUFFIXES: tuple[str, ...] = (".d.ts", ".min.js", ".bundle.js")

# How one Node.js file declares a dependency on another.
#
#   import x from './foo';              -> group 1: ./foo
#   import { y } from '../bar';         -> group 1: ../bar
#   const z = require('./baz');         -> group 1: ./baz
#   import 'polyfill';                  -> group 1: polyfill (side-effect)
#   import express from 'express';      -> group 1: express
#
# A path starting with `.` is a local file; anything else is a package. Both
# are emitted — a project's own layer rules decide which matters. Dynamic
# `import(expr)` and `require(expr)` with a non-literal argument are NOT
# matched: the argument is computed at runtime, and chasing it is how a
# structural audit starts reading expressions instead of declarations.
IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w$]+\s+|[\w$]+\s*,\s*)?(?:\{[^}]*\}|\*\s+as\s+[\w$]+\s+)?\s*from\s*)?['"]([^'"]+)['"]"""
    r'''|require\s*\(\s*['"]([^'"]+)['"]\s*\)''',
    re.M,
)


# --------------------------------------------------------------------------- #
# Sweep checks (the `Check` / `scan_tree` seam)
# --------------------------------------------------------------------------- #
#
# Two defects a text sweep genuinely catches on a Node.js backend, each grounded
# in failure modes rather than style:

# A debug statement left in a route handler: console.log() dumps to stdout
# (which in production goes to a log aggregator, not a response — but still
# leaks payload, config, and stack to whoever reads the logs), debugger; halts
# the Node.js process in an attached debugger, and process.stdout.write()
# bypasses any structured logger. The lookbehind scopes the match to the
# global functions: a method call (`$log.debug(`, `Logger.info(`) is a
# project's own API, not the debug helper, and flagging those is how a check
# becomes noise people disable.
DEBUG_STATEMENT_RE = re.compile(
    r"(?<![\w.])(?:console\.(?:log|debug|trace|dir|table|time|timeEnd))"
    r"|(?<![\w.])debugger\b"
    r"|(?<![\w.])process\.stdout\.write\s*\(")

# A credential committed as a string literal. Three assignment shapes occur
# in real config and all three are matched: `const password = '…'` (variable),
# `password: '…'` (object property), and `config.password = '…'` (property
# assignment). The comparison forms are rejected — `===`, `!==`, `==`, `!=`
# all fail the operator lookbehinds — so an equality test on a variable is
# never read as an assignment. The negative control this must NOT flag: the
# correct shape `const password = process.env.DB_PASSWORD`, where the
# right-hand side is a reference, not a literal.
PLAINTEXT_SECRET_RE = re.compile(
    r"(?<![\w])(?i:password|passwd|secret|api[_-]?key|access[_-]?token"
    r"|client[_-]?secret)['\"]?\s*[:=]\s*['\"][^'\"\n]{6,}['\"]"
    r"|(?<![\w])(?i:password|passwd|secret|api[_-]?key|access[_-]?token"
    r"|client[_-]?secret)['\"]?\s*\]\s*=\s*['\"][^'\"\n]{6,}['\"]")


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
# finding point at the wrong line (the measured failure that fixed this in
# the Dart adapter).

# Template literals run to a backtick; a `//` inside one is text, not a
# comment. JavaScript/TypeScript template literals support nesting (a
# `${}` can contain another backtick), but the common case is a flat literal
# and the simple scanner is sufficient for comment blanking.
_TEMPLATE_RE = re.compile(r"`[^`]*`", re.DOTALL)


def blank_comments(source: str) -> str:
    """`source` with every comment replaced by spaces, same length, lines intact.

    JavaScript/TypeScript's comment forms: `//` and non-nesting `/* … */`.
    Strings are scanned first so a `'https://…'` literal does not lose the
    rest of its line to a false `//`. Single-quoted, double-quoted, and
    template-literal strings are all skipped whole. Template literals
    interpolate expressions (`` `${foo}` ``), but for comment blanking
    purposes the whole backtick-delimited span is treated as a string — an
    unbalanced `//` inside an interpolation is rare enough to leave to
    config review.
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
        if ch == "`":
            # Template literal: scan to the closing backtick, ignoring any
            # escapes. Nested template literals in interpolations are rare
            # enough to leave to config review.
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == "`":
                    i += 1
                    break
                i += 1
            continue
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            stop = n if end == -1 else end + 2
            # JavaScript block comments DO nest (unlike PHP), but the first
            # `*/` at depth 0 ends the block. A simple scan for `*/` is
            # sufficient: nested `/* … /* … */ … */` is rare in real code.
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


# --------------------------------------------------------------------------- #
# Contract-header structural extraction
# --------------------------------------------------------------------------- #
#
# "What does this class declare", "what does this code read off a receiver",
# "where are the banner comments" — asked by the contract-header engine without
# knowing the language. A Node.js "screen" is a route handler, its "adapter"
# the service class it delegates to, and the CONTRACT banner is the same block
# comment convention the audit already reads from config.

CONTRACT_CAPABLE = True  # the engine checks this before trusting the below


def _class_body_span(source: str, class_name: str) -> tuple[int, int] | None:
    match = re.search(
        rf"\b(?:class|interface)\s+{re.escape(class_name)}\b"
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


# A class-body property: `private name: string;`, `public readonly id = 0;`,
# `#secret = 'x';` (JS private), `static cache = new Map();`. The modifier
# keyword (private/public/protected/readonly/static/#) is required — a bare
# `var x = …;` at class-body depth is a stray statement, not a declaration.
# TypeScript's `declare` and `abstract` modifiers are also accepted.
_PROPERTY_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|readonly|static|declare|abstract|#)\s+)*"
    r"(?:[\w$<>\[\]|?,.]+\s+)?([#$]?[\w$]+)\s*(?::|=|;)")

# A TypeScript constructor parameter property: `constructor(private readonly
# svc: UserService, protected n: number = 3)`. TypeScript's most common way
# to declare a service's dependencies, and missing it would report a real
# field as undeclared — a false stale-entry on a correct contract header, the
# failure that gets an audit switched off. The visibility keyword is required:
# a bare `constructor(svc)` is a plain parameter, not a field.
_TS_PROMOTED_RE = re.compile(
    r"(?:public|private|protected)\s+(?:readonly\s+)?"
    r"(?:[\w$<>\[\]|?,.]+\s+)?([#$]?[\w$]+)\s*:")


# A method declaration. TypeScript modifiers are order-insensitive (`public
# async getThing()`, `async public getThing()`), so the prefix is a
# repeated-modifier group rather than one fixed order; `async` and `*`
# (generator) are also accepted. Privacy is read from the words before the
# method name (see _member_names) rather than a second fixed-order regex,
# which would mis-handle the same modifier permutations.
_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|readonly|abstract|async|\*)\s+)*"
    r"([#$]?[\w$]+)\s*\(")


def _member_names(stmt: str, methods: bool) -> list[str]:
    """The members one class-body statement declares (a constructor may
    promote several properties, hence a list)."""
    prop = _PROPERTY_RE.match(stmt)
    if prop:
        return [prop.group(1)]
    # TypeScript constructor parameter properties: `constructor(private
    # readonly svc: UserService, protected n: number = 3)`. The visibility
    # keyword (private/public/protected) — optionally with `readonly` — is
    # what makes a parameter a real field the object carries, so it counts.
    # A bare `constructor(svc)` with no modifier is a plain parameter, not a
    # field, and is excluded.
    if re.match(
            r"^\s*(?:(?:public|private|protected|static|readonly|abstract|async|\*)\s+)*"
            r"constructor\s*\(", stmt):
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
                        found = _TS_PROMOTED_RE.match(buf.strip())
                        if found:
                            names.append(found.group(1))
                        break
                if depth == 1 and ch == ",":
                    found = _TS_PROMOTED_RE.match(buf.strip())
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
        # not a contract anyone documents; `#`-prefixed methods are JS
        # private and also excluded.
        head = signature.split("(", 1)[0]
        if (found and not found.group(1).startswith("__")
                and not found.group(1).startswith("#")
                and not re.search(r"\b(?:private|protected)\b", head)):
            return [found.group(1)]
    return []


def _members(source: str, class_name: str, methods: bool) -> dict[str, int] | None:
    # Strings and template literals blanked, not just comments: a `(` inside
    # a literal would skew the depth counter and drop every declaration after
    # it (see blank_comments).
    blanked = blank_comments(source)
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
            # A brace-bodied member ends here (a method, or a property with
            # an object/array/arrow-function initializer). Still worth
            # reading: the signature before the `{` is what it declares.
            record("".join(buf), buf_start)
            buf, buf_start = [], i + 1
        else:
            if not buf:
                buf_start = i
            buf.append(ch)
    return fields


def class_fields(source: str, class_name: str) -> dict[str, int] | None:
    """`{property name: 1-based line}` for one class.

    None means the class is not in this source — distinct from `{}` meaning
    it declares nothing, which the caller must not conflate. Methods are not
    included (see `class_members`).
    """
    return _members(source, class_name, methods=False)


def class_members(source: str, class_name: str) -> dict[str, int] | None:
    """Like `class_fields`, plus the class's public methods.

    A service class whose whole purpose is to be a surface offers query and
    action methods the same way a Dart adapter offers getters — a contract
    header documenting `totalFor(id: string)` is documenting a real member.
    Private and protected methods are excluded: a caller cannot reach them.
    """
    return _members(source, class_name, methods=True)


def member_reads(source: str, receiver: str) -> set[str]:
    """Names read off the receiver `receiver` — `svc.totalFor` and
    `this.svc.totalFor` both → {"totalFor"}.

    Two prefix forms, and both are required: `receiver.` for the local
    variable, and `.receiver.` for a property read (`this.svc.x`,
    `ctrl.svc.x`). JavaScript/TypeScript has no sigil, so `receiver\.(\w+)`
    matches both forms with no special case. Measured shape, Express/NestJS
    controller: `this.service.totalFor(id)`. A miss here reports every field
    of the service as dead with deletion as the advice — the exact failure
    this function exists to prevent.

    Comments are blanked first, and that is load-bearing: a CONTRACT banner
    listing `svc.totalFor` would otherwise count as a read, every documented
    field would look wired, and the dead-member check would report zero
    forever — the exact measured failure this has in the Dart adapter.
    """
    return set(re.findall(rf"(?:\b|\.){re.escape(receiver)}\.(\w+)",
                          blank_comments(source)))


def receiver_aliases(source: str, receiver: str) -> set[str]:
    """Local names bound to the receiver, so reads through them still count.

    `const svc = this.service;` then `svc.totalFor(...)` is a read of the
    service. Matching only the conventional name reported every member of an
    aliased service as dead in the Dart adapter's origin project; Node.js
    binds the same way (`const a = this.service;`, `let a = service;`).
    """
    code = blank_comments(source)
    escaped = re.escape(receiver)
    patterns = (
        rf"(?:const|let|var)\s+(\w+)\s*=\s*this\.{escaped}\s*[;,]",
        rf"(?:const|let|var)\s+(\w+)\s*=\s*{escaped}\s*[;,]",
    )
    return {m.group(1) for pattern in patterns for m in re.finditer(pattern, code)} \
        - {receiver}


def typed_member_reads(source: str, types) -> dict[str, set[str]]:
    """`{type: members read off any identifier declared with that type}`.

    The receiver is resolved by its declared type, not by what it happens to
    be called — matching one conventional name is the bug that reported real
    members as dead with deletion as the advice in the Dart adapter's origin
    project. Typed parameters (`f(x: Foo)`), properties (`private foo: Foo;`),
    and locals (`const foo: Foo = new Foo()`) are all followed.

    Raises `CapabilityError` when a binding of one of `types` is resolved
    from a container or factory through an untyped variable
    (`const x = container.get(Foo)`): reads through it are invisible here,
    and "I cannot tell" must never come back as "nothing reads it".
    """
    code = blank_comments(source)
    found: dict[str, set[str]] = {}
    for type_name in types:
        escaped = re.escape(type_name)
        # A container/factory binding: `const x = container.get(Foo)`,
        # `const x = resolve(Foo)`, `const x = injector.get(Foo)`.
        blind = re.search(
            rf"(?:const|let|var)\s+(\w+)\s*=[^;]*\b(?:container|injector|resolver|provider)"
            rf"\s*(?:\.get|\.resolve|\.make)\s*\(\s*{escaped}\s*\)", code)
        if blind:
            raise CapabilityError(
                "typed_member_reads", NAME,
                f"{type_name} is bound to an untyped receiver "
                f"({blind.group(0).strip()!r}); reads through it cannot be "
                f"resolved, so this file cannot be used to decide whether "
                f"{type_name}'s members are read")
        names = set()
        # TypeScript typed bindings: `x: Foo`, `x!: Foo`, `private x: Foo`.
        for match in re.finditer(
                rf"(?:const|let|var|private|public|protected|readonly)?\s*"
                rf"(\w+)\s*[!:]\s*{escaped}\b", code):
            names.add(match.group(1))
        # Constructor parameter properties: `constructor(private foo: Foo)`.
        for match in re.finditer(
                rf"(?:private|public|protected|readonly)?\s*(\w+)\s*:\s*{escaped}\b",
                code):
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
# `catch (e) { … }` binds the variable; `e instanceof Error` is the sanctioned
# type test; `String(e)` or `` `${e}` `` or `'' + e` puts the WHOLE exception
# — message plus stack trace — into a string, which is the mangling this
# audit exists to catch. `e.message` is the sanctioned narrowing and is
# deliberately invisible to the stringify pattern.
ERROR_HANDLING = ErrorHandlingSyntax(
    # `catch (e)`, `catch (e: any)`, `catch (err: unknown)`. Group 1 is the
    # variable; the optional `: type` (TypeScript's annotation) is skipped so
    # the variable is captured whether or not the catch is typed.
    catch_var=re.compile(r"\bcatch\s*\(\s*(\w+)\s*(?::[^)]*)?\)"),
    type_guard=lambda var, typ: re.compile(
        rf"\b{re.escape(var)}\s+instanceof\s+(?:[\w$.]+\.)?{re.escape(typ)}\b"),
    stringify=lambda var: re.compile(
        r"String\s*\(\s*" + re.escape(var) + r"\s*\)"
        # A template literal interpolating the variable puts the whole
        # exception into the string. The closing `}` must follow the variable
        # immediately, so `${e.message}` (the sanctioned narrowing) is not
        # matched — only `${e}` itself.
        r"|\$\{" + re.escape(var) + r"\}"
        r"|['\"]\s*\+\s*" + re.escape(var) + r"\b"
        r"|" + re.escape(var) + r"\s*\+\s*['\"]"),
    type_test=lambda cls: re.compile(
        rf"\b{re.escape(cls)}\s+instanceof\s+[\w$.]+"
        rf"|instanceof\s+(?:[\w$.]+\.)?{re.escape(cls)}\b"),
    string_quotes=("'", '"', "`"),
    line_comment="//",
)


# --------------------------------------------------------------------------- #
# audit_api_consistency syntax
# --------------------------------------------------------------------------- #
#
# The Node.js reading of the audit's four checks:
#
#   user_facing  — a response literal under a user-facing envelope key
#                  (`{ message: 'Not found' }` in a res.json() call). On a
#                  LIBRARY this is the white-label defect itself: copy a
#                  consumer cannot re-voice without forking.
#   defaulted    — a parameter default (`msg: string = 'fallback'`): the
#                  overridable shape, so a default literal is not hard-baked.
#   compared     — a literal on either side of an equality: the load-bearing
#                  shape (`state === 'Unknown'`), where the sentinel and the
#                  value are the same string.
#   tappable     — a route declaration, the backend's only honest analogue
#                  of an interaction surface. The `authoredSemantics` check
#                  it feeds is a UI concept; Node.js projects turn that check
#                  off with a written reason rather than run it against a
#                  stack with no semantics API.
API_CONSISTENCY = ApiConsistencySyntax(
    # Node.js object keys are unquoted strings (`{ message: 'Not found' }`),
    # so the key's own quotes are optional-but-matched around the keyword.
    user_facing=re.compile(
        r"(?<![\w])['\"]?(?:message|error|detail|description)['\"]?\s*[:=]\s*"
        r"['\"]([^'\"\\]{2,})['\"]"),
    defaulted=re.compile(
        r"(?:const|let|var)?\s*[\w$]+\s*(?::\s*[\w$<>[\]|?,.\s]+)?=\s*"
        r"['\"]([^'\"\\]{2,})['\"]"),
    compared=re.compile(
        r"===?\s*['\"]([^'\"\\]{2,})['\"]|!==?\s*['\"]([^'\"\\]{2,})['\"]"
        r"|['\"]([^'\"\\]{2,})['\"]\s*===?|['\"]([^'\"\\]{2,})['\"]\s*!==?"),
    tappable=re.compile(
        r"\b(?:app|router|server)\s*\.\s*"
        r"(?:get|post|put|patch|delete|all|use|route|options|head)\s*\("
        r"|\b(?:Get|Post|Put|Patch|Delete|All|Options|Head|Controller)\s*\("
        r"|\b@(?:Get|Post|Put|Patch|Delete|All|Options|Head)\s*\("),
)


# --------------------------------------------------------------------------- #
# Capability detection (base.LanguageCapabilityProtocol)
# --------------------------------------------------------------------------- #
#
# What a Node.js routing declaration looks like is a language/framework fact
# and belongs here: the engine asks "does this project route?" and never
# learns what the answer was made of.

# Base routing signatures (Express/Fastify/Hono route declarations)
ROUTING_SIGNATURES = (
    # Express/Fastify/Koa: app.get('/path', handler), router.post(…)
    re.compile(r"\b(?:app|router|server)\s*\.\s*"
               r"(?:get|post|put|patch|delete|all|options|head|use|route)\s*\("),
    # NestJS decorators: @Get('/path'), @Post(), @Controller()
    re.compile(r"@(?:Get|Post|Put|Patch|Delete|All|Options|Head|Controller)\s*\("),
    # Hono: app.get('/path', c => …), router.get(…)
    re.compile(r"\b(?:app|router)\s*\.\s*"
               r"(?:get|post|put|patch|delete|all|on|route)\s*\(\s*['\"`]"),
    # Fastify: fastify.get('/path', …), fastify.route({…})
    re.compile(r"\bfastify\s*\.\s*(?:get|post|put|patch|delete|route|register)\s*\("),
    # AdonisJS: Route.get('/path', 'Controller.method')
    re.compile(r"\bRoute\s*\.\s*"
               r"(?:get|post|put|patch|delete|resource|apiResource|group|middleware)\s*\("),
)


# Express capability signatures
_EXPRESS_ROUTING = r"\b(?:app|router)\s*\.\s*(?:get|post|put|patch|delete|all|use|route)\s*\("
_EXPRESS_MIDDLEWARE = r"\bapp\s*\.\s*use\s*\("
_EXPRESS_ERROR_HANDLER = r"\bapp\s*\.\s*use\s*\(\s*(?:\s*\w+\s*,\s*)?(?:function\s*)?\(\s*(?:err|error)\s*[:,]"
_EXPRESS_BODY_PARSER = r"\bapp\s*\.\s*use\s*\(\s*(?:express|bodyParser|body-parser)\s*\.\s*(?:json|urlencoded|raw|text)\s*\("
_EXPRESS_COOKIE = r"\bapp\s*\.\s*use\s*\(\s*(?:cookieParser|cookie-parser)\s*\("
_EXPRESS_SESSION = r"\bapp\s*\.\s*use\s*\(\s*(?:session|express-session)\s*\("
_EXPRESS_HELMET = r"\bapp\s*\.\s*use\s*\(\s*helmet\s*\("
_EXPRESS_CORS = r"\bapp\s*\.\s*use\s*\(\s*(?:cors|corsMiddleware)\s*\("
_EXPRESS_ROUTER = r"\b(?:const|let|var)\s+\w+\s*=\s*express\s*\.\s*Router\s*\(\s*\)"

EXPRESS_ROUTING_SIGNATURES = (
    re.compile(_EXPRESS_ROUTING),
    re.compile(_EXPRESS_MIDDLEWARE),
    re.compile(_EXPRESS_ERROR_HANDLER),
    re.compile(_EXPRESS_BODY_PARSER),
    re.compile(_EXPRESS_COOKIE),
    re.compile(_EXPRESS_SESSION),
    re.compile(_EXPRESS_HELMET),
    re.compile(_EXPRESS_CORS),
    re.compile(_EXPRESS_ROUTER),
)

# Fastify capability signatures — require `fastify` identifier specifically
_FASTIFY_ROUTING = r"\bfastify\s*\.\s*(?:get|post|put|patch|delete|route|register)\s*\("
_FASTIFY_PLUGIN = r"\bfastify\s*\.\s*register\s*\("
_FASTIFY_HOOK = r"\bfastify\s*\.\s*addHook\s*\("
_FASTIFY_DECORATOR = r"\bfastify\s*\.\s*decorate(?:Request|Reply)?\s*\("
_FASTIFY_SCHEMA = r"\bschema\s*:\s*\{"
_FASTIFY_VALIDATION = r"\b(?:body|querystring|params|headers)\s*:\s*\{[^}]*type\s*:"
_FASTIFY_SERIALIZER = r"\bserializer\s*:"

FASTIFY_ROUTING_SIGNATURES = (
    re.compile(_FASTIFY_ROUTING),
    re.compile(_FASTIFY_PLUGIN),
    re.compile(_FASTIFY_HOOK),
    re.compile(_FASTIFY_DECORATOR),
    re.compile(_FASTIFY_SCHEMA),
    re.compile(_FASTIFY_VALIDATION),
    re.compile(_FASTIFY_SERIALIZER),
)

# NestJS capability signatures
_NESTJS_CONTROLLER = r"@Controller\s*\("
_NESTJS_GET = r"@Get\s*\("
_NESTJS_POST = r"@Post\s*\("
_NESTJS_PUT = r"@Put\s*\("
_NESTJS_PATCH = r"@Patch\s*\("
_NESTJS_DELETE = r"@Delete\s*\("
_NESTJS_MODULE = r"@Module\s*\("
_NESTJS_INJECTABLE = r"@Injectable\s*\("
_NESTJS_INJECT = r"@Inject\s*\("
_NESTJS_USE_GUARDS = r"@UseGuards\s*\("
_NESTJS_USE_PIPES = r"@UsePipes\s*\("
_NESTJS_USE_INTERCEPTORS = r"@UseInterceptors\s*\("
_NESTJS_USE_FILTERS = r"@UseFilters\s*\("
_NESTJS_BODY = r"@Body\s*\("
_NESTJS_PARAM = r"@Param\s*\("
_NESTJS_QUERY = r"@Query\s*\("
_NESTJS_HEADERS = r"@Headers\s*\("
_NESTJS_RES = r"@Res\s*\("
_NESTJS_NEXT = r"@Next\s*\("

NESTJS_CAPABILITY_SIGNATURES = (
    re.compile(_NESTJS_CONTROLLER),
    re.compile(_NESTJS_GET),
    re.compile(_NESTJS_POST),
    re.compile(_NESTJS_PUT),
    re.compile(_NESTJS_PATCH),
    re.compile(_NESTJS_DELETE),
    re.compile(_NESTJS_MODULE),
    re.compile(_NESTJS_INJECTABLE),
    re.compile(_NESTJS_INJECT),
    re.compile(_NESTJS_USE_GUARDS),
    re.compile(_NESTJS_USE_PIPES),
    re.compile(_NESTJS_USE_INTERCEPTORS),
    re.compile(_NESTJS_USE_FILTERS),
    re.compile(_NESTJS_BODY),
    re.compile(_NESTJS_PARAM),
    re.compile(_NESTJS_QUERY),
    re.compile(_NESTJS_HEADERS),
    re.compile(_NESTJS_RES),
    re.compile(_NESTJS_NEXT),
)

# Hono capability signatures — require `Hono` import/instantiation OR Hono-specific
# response methods (`c.json()`, `c.text()`, `c.html()`, `c.redirect()`) which
# distinguish it from Express's `res.json()`. Also the `c: Context` type hint.
_HONO_APP = r"\bnew\s+Hono\s*\("
_HONO_GET = r"\bapp\s*\.\s*get\s*\(\s*['\"`][^'\"]*['\"`]\s*,\s*(?:async\s*)?\(?\s*c\s*\)?\s*=>"
_HONO_POST = r"\bapp\s*\.\s*post\s*\(\s*['\"`][^'\"]*['\"`]\s*,\s*(?:async\s*)?\(?\s*c\s*\)?\s*=>"
_HONO_PUT = r"\bapp\s*\.\s*put\s*\(\s*['\"`][^'\"]*['\"`]\s*,\s*(?:async\s*)?\(?\s*c\s*\)?\s*=>"
_HONO_PATCH = r"\bapp\s*\.\s*patch\s*\(\s*['\"`][^'\"]*['\"`]\s*,\s*(?:async\s*)?\(?\s*c\s*\)?\s*=>"
_HONO_DELETE = r"\bapp\s*\.\s*delete\s*\(\s*['\"`][^'\"]*['\"`]\s*,\s*(?:async\s*)?\(?\s*c\s*\)?\s*=>"
_HONO_JSON = r"\bc\s*\.\s*json\s*\("
_HONO_TEXT = r"\bc\s*\.\s*text\s*\("
_HONO_HTML = r"\bc\s*\.\s*html\s*\("
_HONO_REDIRECT = r"\bc\s*\.\s*redirect\s*\("
_HONO_ON = r"\bapp\s*\.\s*on\s*\("
_HONO_USE = r"\bapp\s*\.\s*use\s*\(\s*(?:async\s*)?\(?\s*c\s*,?\s*next\s*\)?\s*=>"
_HONO_ROUTE = r"\bapp\s*\.\s*route\s*\("
_HONO_MIDDLEWARE = r"\bc\s*\.\s*next\s*\("
_HONO_CONTEXT = r"\bc\s*:\s*Context\b"

HONO_CAPABILITY_SIGNATURES = (
    re.compile(_HONO_APP),
    re.compile(_HONO_GET),
    re.compile(_HONO_POST),
    re.compile(_HONO_PUT),
    re.compile(_HONO_PATCH),
    re.compile(_HONO_DELETE),
    re.compile(_HONO_JSON),
    re.compile(_HONO_TEXT),
    re.compile(_HONO_HTML),
    re.compile(_HONO_REDIRECT),
    re.compile(_HONO_ON),
    # Hono's app.use takes middleware with (c, next) signature; Express uses (req, res, next).
    # We check for the `(c, next)` or `(c) => { ...; next(); }` pattern.
    re.compile(_HONO_USE),
    re.compile(_HONO_ROUTE),
    re.compile(_HONO_MIDDLEWARE),
    re.compile(_HONO_CONTEXT),
)

# Koa capability signatures — require `ctx` as the first parameter (Koa convention)
_KOA_ROUTING = r"\brouter\s*\.\s*(?:get|post|put|patch|delete|all|use)\s*\("
_KOA_MIDDLEWARE = r"\bapp\s*\.\s*use\s*\(\s*(?:async\s*)?(?:function\s*)?\(\s*(?:ctx|c)\s*[,:]"

KOA_CAPABILITY_SIGNATURES = (
    re.compile(_KOA_ROUTING),
    re.compile(_KOA_MIDDLEWARE),
)

# AdonisJS capability signatures
_ADONIS_ROUTE = r"\bRoute\s*\.\s*(?:get|post|put|patch|delete|resource|apiResource|group|middleware|domain)\s*\("
_ADONIS_CONTROLLER = r"\bexport\s+default\s+class\s+\w+Controller\b"
_ADONIS_MODEL = r"\bexport\s+default\s+class\s+\w+\s+extends\s+BaseModel\b"
_ADONIS_VALIDATOR = r"\bexport\s+default\s+class\s+\w+\s+extends\s+(?:BaseValidator|CustomMessages)\b"

ADONIS_CAPABILITY_SIGNATURES = (
    re.compile(_ADONIS_ROUTE),
    re.compile(_ADONIS_CONTROLLER),
    re.compile(_ADONIS_MODEL),
    re.compile(_ADONIS_VALIDATOR),
)

# Models capability signatures (ORM/ODM)
_PRISMA_SCHEMA = r"\bmodel\s+\w+\s*\{"
_PRISMA_CLIENT = r"\b@prisma/client\b"
_TYPEORM_ENTITY = r"@Entity\s*\("
_TYPEORM_COLUMN = r"@Column\s*\("
_TYPEORM_PRIMARY = r"@PrimaryGeneratedColumn\s*\("
_TYPEORM_RELATION = r"@OneToMany|@ManyToOne|@OneToOne|@ManyToMany"
_SEQUELIZE_MODEL = r"\b(?:Model|Sequelize)\s*\.\s*(?:define|init|sync)\s*\("
_MONGOOSE_SCHEMA = r"\bnew\s+Schema\s*\("
_MONGOOSE_MODEL = r"\bmodel\s*\(\s*['\"]"
_MIKRO_ENTITY = r"@Entity\s*\("
_MIKRO_PROPERTY = r"@Property\s*\("
_MIKRO_RELATION = r"@OneToMany|@ManyToOne|@OneToOne|@ManyToMany"

MODEL_CAPABILITY_SIGNATURES = (
    re.compile(_PRISMA_SCHEMA),
    re.compile(_PRISMA_CLIENT),
    re.compile(_TYPEORM_ENTITY),
    re.compile(_TYPEORM_COLUMN),
    re.compile(_TYPEORM_PRIMARY),
    re.compile(_TYPEORM_RELATION),
    re.compile(_SEQUELIZE_MODEL),
    re.compile(_MONGOOSE_SCHEMA),
    re.compile(_MONGOOSE_MODEL),
    re.compile(_MIKRO_ENTITY),
    re.compile(_MIKRO_PROPERTY),
    re.compile(_MIKRO_RELATION),
)

# Validation capability signatures
_ZOD_SCHEMA = r"\bz\s*\.\s*(?:object|string|number|boolean|array|enum|union|intersection|record|tuple|lazy)\s*\("
_ZOD_PARSE = r"\.parse\s*\("
_ZOD_SAFE_PARSE = r"\.safeParse\s*\("
_CLASS_VALIDATOR = r"@(?:IsString|IsNumber|IsBoolean|IsEmail|IsUrl|IsDate|IsArray|IsObject|IsOptional|IsNotEmpty|MinLength|MaxLength|Min|Max|Matches|IsIn|IsEnum|ValidateNested|ValidateIf|IsDefined|IsUndefined|IsNullable|IsPositive|IsNegative|IsInt|IsFloat|IsHexColor|IsUUID|IsISO8601|IsAlpha|IsAlphanumeric|IsAscii|IsBase64|IsBooleanString|IsDateString|IsDecimal|IsDivisibleBy|IsFQDN|IsFullWidth|IsHalfWidth|IsHash|IsIdentityCard|IsISSN|IsISIN|IsISO31661Alpha2|IsISO31661Alpha3|IsJSDate|IsJWT|IsLowercase|IsMACAddress|IsMimeType|IsMobilePhone|IsMongoId|IsMultibyte|IsNumericString|IsPort|IsSurrogatePair|IsUppercase|IsURLOptions|IsVariableWidth|Length|IsNotEmpty)\s*\("
_JOI_SCHEMA = r"\bjoi\s*\.\s*(?:object|string|number|boolean|array|alternatives|date|func|object|symbol|binary|when|ref|custom|extend|defaults|fork|keys|optional|require|forbidden|valid|invalid|allow|disallow|only|not|concat|raw|rawMethod|label|description|note|meta|example|unit|warn|error|presence|external|internal|when|conditional|match|try|errors)\s*\("
_YUP_SCHEMA = r"\byup\s*\.\s*(?:object|string|number|boolean|array|mixed|date|lazy|boolean|object)\s*\("

VALIDATION_CAPABILITY_SIGNATURES = (
    re.compile(_ZOD_SCHEMA),
    re.compile(_ZOD_PARSE),
    re.compile(_ZOD_SAFE_PARSE),
    re.compile(_CLASS_VALIDATOR),
    re.compile(_JOI_SCHEMA),
    re.compile(_YUP_SCHEMA),
)

# Middleware capability signatures
_EXPRESS_MIDDLEWARE_SIGS = r"\bapp\s*\.\s*use\s*\("
_FASTIFY_MIDDLEWARE_SIGS = r"\bfastify\s*\.\s*addHook\s*\("
_NESTJS_MIDDLEWARE_SIGS = r"@UseGuards|@UsePipes|@UseInterceptors|@UseFilters|@Catch"
_HONO_MIDDLEWARE_SIGS = r"\bapp\s*\.\s*use\s*\(|\bapp\s*\.\s*on\s*\("

MIDDLEWARE_CAPABILITY_SIGNATURES = (
    re.compile(_EXPRESS_MIDDLEWARE_SIGS),
    re.compile(_FASTIFY_MIDDLEWARE_SIGS),
    re.compile(_NESTJS_MIDDLEWARE_SIGS),
    re.compile(_HONO_MIDDLEWARE_SIGS),
)

# Dependency injection capability signatures
_NESTJS_DI_SIGS = r"@Injectable|@Module|@Inject|@Optional|@Scope"
_INVERSIFY_SIGS = r"@injectable|@inject|@multiInject|@optional|Container"
_TSYRINGE_SIGS = r"@Injectable|@Inject|inject\s*\(|Container\s*\.\s*get"
_REFLECT_METADATA_SIGS = r"Reflect\s*\.\s*defineMetadata|reflect-metadata"

DEPENDENCY_INJECTION_CAPABILITY_SIGNATURES = (
    re.compile(_NESTJS_DI_SIGS),
    re.compile(_INVERSIFY_SIGS),
    re.compile(_TSYRINGE_SIGS),
    re.compile(_REFLECT_METADATA_SIGS),
)

# API resources capability signatures
_DTO_PATTERN = r"\bclass\s+\w+(?:Dto|DTO|Request|Response|Payload|Input|Output)\b"
_CONTROLLER_PATTERN = r"@Controller|@Get|@Post|@Put|@Patch|@Delete"
_SERVICE_PATTERN = r"@Injectable|@Service\b"
_REPOSITORY_PATTERN = r"@Repository|@EntityRepository"
_OPENAPI_PATTERN = r"@ApiProperty|@ApiResponse|@ApiOperation|@ApiTags|@ApiBearerAuth"

API_RESOURCES_CAPABILITY_SIGNATURES = (
    re.compile(_DTO_PATTERN),
    re.compile(_CONTROLLER_PATTERN),
    re.compile(_SERVICE_PATTERN),
    re.compile(_REPOSITORY_PATTERN),
    re.compile(_OPENAPI_PATTERN),
)

# Policies/authorization capability signatures
_CASL_PATTERN = r"\b(?:Ability|AbilityBuilder|AbilityClass|createMongoAbility|createAliasAbility)\s*\("
_CASL_RULES = r"\bcan\s*\(|\bcannot\s*\("
_GUARD_PATTERN = r"@UseGuards|@CanActivate|implements\s+CanActivate"
_POLICY_PATTERN = r"\b(?:Policy|PolicyHandler|PolicyMapper)\b"
_RBAC_PATTERN = r"\b(?:Role|Permission|AccessControl)\b"

POLICIES_CAPABILITY_SIGNATURES = (
    re.compile(_CASL_PATTERN),
    re.compile(_CASL_RULES),
    re.compile(_GUARD_PATTERN),
    re.compile(_POLICY_PATTERN),
    re.compile(_RBAC_PATTERN),
)


# Base capability signatures (framework-agnostic)
CAPABILITY_SIGNATURES = {
    "routing": (
        ROUTING_SIGNATURES,
        "a Node.js backend either declares its routes via app.get/post/… "
        "(Express/Fastify/Koa/Hono), @Get/@Post decorators (NestJS), or "
        "Route.get (AdonisJS); these are the constructions that mean the former",
    ),
    "models": (
        MODEL_CAPABILITY_SIGNATURES,
        "a Node.js backend uses an ORM/ODM: Prisma (model blocks in schema.prisma), "
        "TypeORM (@Entity decorators), Sequelize (Model.define), Mongoose (new Schema), "
        "or MikroORM (@Entity/@Property). These patterns cover the full surface.",
    ),
    "validation": (
        VALIDATION_CAPABILITY_SIGNATURES,
        "a Node.js backend validates input via Zod (z.object/string/…), "
        "class-validator (@IsString/@IsEmail/… decorators), Joi (joi.object/string/…), "
        "or Yup (yup.object/string/…). These patterns cover the full surface.",
    ),
    "middleware": (
        MIDDLEWARE_CAPABILITY_SIGNATURES,
        "a Node.js backend uses middleware: Express (app.use), Fastify (addHook), "
        "NestJS (@UseGuards/@UsePipes/@UseInterceptors), or Hono (app.use/app.on). "
        "These patterns cover the full surface.",
    ),
    "dependency_injection": (
        DEPENDENCY_INJECTION_CAPABILITY_SIGNATURES,
        "a Node.js backend uses DI: NestJS (@Injectable/@Module/@Inject), "
        "InversifyJS (@injectable/@inject/Container), TSyringe (Container.get), "
        "or reflect-metadata. These patterns cover the full surface.",
    ),
    "api_resources": (
        API_RESOURCES_CAPABILITY_SIGNATURES,
        "a Node.js backend defines API resources: DTOs (class FooDto/FooRequest/FooResponse), "
        "controllers (@Controller/@Get/@Post), services (@Injectable), "
        "repositories (@Repository), or OpenAPI decorators (@ApiProperty/@ApiResponse). "
        "These patterns cover the full surface.",
    ),
    "policies": (
        POLICIES_CAPABILITY_SIGNATURES,
        "a Node.js backend implements authorization: CASL (Ability/can/cannot), "
        "guards (@UseGuards/implements CanActivate), policies (Policy/PolicyHandler), "
        "or RBAC (Role/Permission/AccessControl). These patterns cover the full surface.",
    ),
}

# Framework-specific capability signatures (extends base)
EXPRESS_CAPABILITY_SIGNATURES = {
    "express_routing": (
        EXPRESS_ROUTING_SIGNATURES,
        "an Express project declares routes via app.get/post/…, router.get/post/…, "
        "and configures middleware via app.use(). These patterns cover the full "
        "Express routing and middleware surface.",
    ),
}

FASTIFY_CAPABILITY_SIGNATURES = {
    "fastify_routing": (
        FASTIFY_ROUTING_SIGNATURES,
        "a Fastify project declares routes via fastify.get/post/…, registers plugins "
        "via fastify.register(), adds hooks via fastify.addHook(), and uses schema-"
        "based validation. These patterns cover the full Fastify surface.",
    ),
}

NESTJS_CAPABILITY_SIGNATURES_FULL = {
    "nestjs_routing": (
        NESTJS_CAPABILITY_SIGNATURES,
        "a NestJS project declares routes via @Controller/@Get/@Post/… decorators, "
        "organizes code in @Module blocks, injects dependencies via @Inject, and "
        "applies cross-cutting concerns via @UseGuards/@UsePipes/@UseInterceptors. "
        "These patterns cover the full NestJS surface.",
    ),
}

HONO_CAPABILITY_SIGNATURES_FULL = {
    "hono_routing": (
        HONO_CAPABILITY_SIGNATURES,
        "a Hono project declares routes via app.get/post/…, groups routes via "
        "app.route(), adds middleware via app.use()/app.on(), and handles requests "
        "via the Context object. These patterns cover the full Hono surface.",
    ),
}

KOA_CAPABILITY_SIGNATURES_FULL = {
    "koa_routing": (
        KOA_CAPABILITY_SIGNATURES,
        "a Koa project declares routes via app.get/post/… and adds middleware "
        "via app.use(). These patterns cover the full Koa surface.",
    ),
}

ADONIS_CAPABILITY_SIGNATURES_FULL = {
    "adonis_routing": (
        ADONIS_CAPABILITY_SIGNATURES,
        "an AdonisJS project declares routes via Route.get/post/…, defines controllers "
        "as classes extending a base, defines models extending BaseModel, and validates "
        "input via validators. These patterns cover the full AdonisJS surface.",
    ),
}

# All capability signatures merged
ALL_CAPABILITY_SIGNATURES = {
    **CAPABILITY_SIGNATURES,
    **EXPRESS_CAPABILITY_SIGNATURES,
    **FASTIFY_CAPABILITY_SIGNATURES,
    **NESTJS_CAPABILITY_SIGNATURES_FULL,
    **HONO_CAPABILITY_SIGNATURES_FULL,
    **KOA_CAPABILITY_SIGNATURES_FULL,
    **ADONIS_CAPABILITY_SIGNATURES_FULL,
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
        why="ORM/ODM model declarations (Prisma, TypeORM, Sequelize, Mongoose, "
            "MikroORM). A project using these patterns should declare source.root "
            "so the audit can find them.",
    ),
    Capability(
        name="validation",
        profile_field="source.root",
        why="input validation (Zod, class-validator, Joi, Yup). A project using "
            "these patterns should declare source.root so the audit can find them.",
    ),
    Capability(
        name="middleware",
        profile_field="source.root",
        why="middleware layers (Express, Fastify, NestJS, Hono). A project using "
            "these patterns should declare source.root so the audit can find them.",
    ),
    Capability(
        name="dependency_injection",
        profile_field="source.root",
        why="DI containers (NestJS, InversifyJS, TSyringe). A project using these "
            "patterns should declare source.root so the audit can find them.",
    ),
    Capability(
        name="api_resources",
        profile_field="source.root",
        why="API resource definitions (DTOs, controllers, services, repositories). "
            "A project using these patterns should declare source.root so the audit "
            "can find them.",
    ),
    Capability(
        name="policies",
        profile_field="source.root",
        why="authorization policies (CASL, guards, RBAC). A project using these "
            "patterns should declare source.root so the audit can find them.",
    ),
)

# Framework-specific capabilities - only offered when project reads as that framework
FRAMEWORK_ONLY_CAPABILITIES = {
    "express_routing": "express",
    "fastify_routing": "fastify",
    "nestjs_routing": "nestjs",
    "hono_routing": "hono",
    "koa_routing": "koa",
    "adonis_routing": "adonisjs",
}


def _expand_file_glob(repo: Path, pattern: str) -> list:
    """The concrete files a `source.routesFile` value names.

    The value may be a single file (`src/routes.ts`) or a glob
    (`src/routes/*.ts`); both are resolved repo-relative, and a pattern that
    names nothing yields an empty list (the caller's own empty-sweep refusal
    then stands — no evidence is not evidence of absence).
    """
    path = Path(pattern)
    if path.is_absolute():
        return [path] if path.is_file() else []
    return sorted(repo.glob(pattern))


def _looks_node(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a Node.js project, not just "a directory".

    The probe is deliberately cheap and deliberately conservative: a false
    "yes" costs extra capability findings (the old noise), while a false "no"
    makes a real Node.js project's capabilities go unexamined — so the default
    must be to answer "yes" whenever there is *any* Node.js signal. Three
    signals, any of which suffices:

      * a `package.json` file exists at the repo root;
      * a `node_modules/` directory exists (a strong indicator of npm/yarn/pnpm);
      * any hand-written `.ts`/`.js` file under the source root imports from
        a package (not a relative path).
    """
    root = Path(str(ctx.repo))

    if (root / "package.json").is_file():
        return True

    if (root / "node_modules").is_dir():
        return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for suffix in ("*.ts", "*.js", "*.tsx", "*.jsx"):
        for path in base.rglob(suffix):
            if "node_modules" in path.relative_to(base).parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            # A non-relative import (`import x from 'express'`) is a package,
            # which means this is a Node.js project.
            if re.search(r"import\s+[\w${}\s,*]+\s+from\s+['\"][^./]", text):
                return True
            if re.search(r"require\s*\(\s*['\"][^./]", text):
                return True
    return False


def _looks_express(ctx: AdapterContext) -> bool:
    """Whether this tree reads as an Express application."""
    root = Path(str(ctx.repo))

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            manifest = json.loads(pkg.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        for section in ("dependencies", "devDependencies"):
            for package in (manifest.get(section) or {}):
                if package == "express":
                    return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for path in base.rglob("*.ts"):
        if "node_modules" in path.relative_to(base).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bimport\s+[\w${}\s,*]+\s+from\s+['\"]express['\"]", text):
            return True
        if re.search(r"\brequire\s*\(\s*['\"]express['\"]", text):
            return True
    return False


def _looks_fastify(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a Fastify application."""
    root = Path(str(ctx.repo))

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            manifest = json.loads(pkg.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        for section in ("dependencies", "devDependencies"):
            for package in (manifest.get(section) or {}):
                if package == "fastify":
                    return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for path in base.rglob("*.ts"):
        if "node_modules" in path.relative_to(base).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bimport\s+[\w${}\s,*]+\s+from\s+['\"]fastify['\"]", text):
            return True
        if re.search(r"\brequire\s*\(\s*['\"]fastify['\"]", text):
            return True
    return False


def _looks_nestjs(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a NestJS application."""
    root = Path(str(ctx.repo))

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            manifest = json.loads(pkg.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        for section in ("dependencies", "devDependencies"):
            for package in (manifest.get(section) or {}):
                if package.startswith("@nestjs/"):
                    return True

    if (root / "nest-cli.json").is_file():
        return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for path in base.rglob("*.ts"):
        if "node_modules" in path.relative_to(base).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bimport\s+[\w${}\s,*]+\s+from\s+['\"]@nestjs/", text):
            return True
        if re.search(r"@(?:Controller|Injectable|Module)\s*\(", text):
            return True
    return False


def _looks_hono(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a Hono application."""
    root = Path(str(ctx.repo))

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            manifest = json.loads(pkg.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        for section in ("dependencies", "devDependencies"):
            for package in (manifest.get(section) or {}):
                if package == "hono":
                    return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for path in base.rglob("*.ts"):
        if "node_modules" in path.relative_to(base).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bimport\s+[\w${}\s,*]+\s+from\s+['\"]hono['\"]", text):
            return True
        if re.search(r"\bnew\s+Hono\s*\(", text):
            return True
    return False


def _looks_koa(ctx: AdapterContext) -> bool:
    """Whether this tree reads as a Koa application."""
    root = Path(str(ctx.repo))

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            manifest = json.loads(pkg.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        for section in ("dependencies", "devDependencies"):
            for package in (manifest.get(section) or {}):
                if package == "koa" or package.startswith("@koa/"):
                    return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for path in base.rglob("*.ts"):
        if "node_modules" in path.relative_to(base).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bimport\s+[\w${}\s,*]+\s+from\s+['\"]koa", text):
            return True
        if re.search(r"\brequire\s*\(\s*['\"]koa", text):
            return True
    return False


def _looks_adonisjs(ctx: AdapterContext) -> bool:
    """Whether this tree reads as an AdonisJS application."""
    root = Path(str(ctx.repo))

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            manifest = json.loads(pkg.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        for section in ("dependencies", "devDependencies"):
            for package in (manifest.get(section) or {}):
                if package.startswith("@adonisjs/"):
                    return True

    if (root / "adonisrc.ts").is_file() or (root / "adonisrc.js").is_file():
        return True

    root_rel = (ctx.profile.get("source", {}) or {}).get("root")
    base = root / root_rel if root_rel else root
    if not base.is_dir():
        return False
    for path in base.rglob("*.ts"):
        if "node_modules" in path.relative_to(base).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"\bimport\s+[\w${}\s,*]+\s+from\s+['\"]@adonisjs/", text):
            return True
        if re.search(r"\bRoute\s*\.\s*(?:get|post|resource)\s*\(", text):
            return True
    return False


def capabilities(ctx: AdapterContext) -> list:
    """What this adapter can be asked about. See base.LanguageCapabilityProtocol.

    Framework-specific capabilities are offered only to projects that read as
    that framework (see `_looks_express`, `_looks_fastify`, etc.). On any
    other Node.js tree they are simply not asked — a project is neither
    measured nor excused for capabilities it never claimed to have.
    """
    caps = list(CAPABILITIES)
    if not _looks_express(ctx):
        caps = [c for c in caps if c.name != "express_routing"]
    if not _looks_fastify(ctx):
        caps = [c for c in caps if c.name != "fastify_routing"]
    if not _looks_nestjs(ctx):
        caps = [c for c in caps if c.name != "nestjs_routing"]
    if not _looks_hono(ctx):
        caps = [c for c in caps if c.name != "hono_routing"]
    if not _looks_koa(ctx):
        caps = [c for c in caps if c.name != "koa_routing"]
    if not _looks_adonisjs(ctx):
        caps = [c for c in caps if c.name != "adonis_routing"]
    return caps


def detect_capability(ctx: AdapterContext, name: str) -> CapabilityEvidence:
    """Whether this project does `name`, or a refusal.

    Three separate refusals, all of which would otherwise arrive as a flat
    "no": an unknown capability, a source root that is not there, and a
    source root holding no Node.js at all. The last is the one that bites —
    point the adapter at a workspace stub and every capability reads as
    absent, which is a clean report about a tree nobody looked at.
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

    # Collect sources: all .ts/.js files under source.root, excluding
    # node_modules (dependency code, not hand-written).
    sources: list[Path] = []
    for suffix in ("*.ts", "*.js", "*.tsx", "*.jsx"):
        for path in root.rglob(suffix):
            rel = path.relative_to(root)
            if "node_modules" in rel.parts or "dist" in rel.parts or "build" in rel.parts:
                continue
            sources.append(path)

    # Routing evidence conventionally lives OUTSIDE source.root — Express
    # puts app.get(…) in src/index.ts or src/app.ts at the repo root, while
    # this capability's own profile_field is `source.routesFile`. Scan the
    # declared routes file(s) as well as the source tree (which still holds
    # attribute- and closure-routed controllers), so a real Node.js layout is
    # measured, not reported as "unused" by a scan that never saw its route
    # declarations.
    routes_rel = (ctx.profile.get("source", {}) or {}).get("routesFile")
    if routes_rel:
        for candidate in _expand_file_glob(repo, routes_rel):
            if candidate not in sources:
                sources.append(candidate)

    if not sources:
        raise CapabilityError(
            name, NAME,
            f"no hand-written .ts/.js under {root_rel!r} — absence of evidence in "
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
