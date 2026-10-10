"""Swift / SwiftUI (and UIKit) adapter — hardcoded colours, spacing, radii, durations.

**Maturity: unverified.** Proven against synthetic planted-violation fixtures
(`bin/native_adapters_test.py`) and sanity-run on public OSS SwiftUI sample apps,
never against a consumer project. Its findings are leads, not a measured
false-positive rate.

## What is checked

  color          `Color(red:green:blue:)`, `Color(.sRGB, red: …)`, `Color(white: 0.2)`,
                 `UIColor(red: …)` / `UIColor(white: …)`, `.init(red: …)`,
                 `#colorLiteral(…)`, `Color(hex: …)` / `UIColor(hex: …)`, and a
                 hex string literal `"#RRGGBB"` anywhere in code.
  spacing        `.padding(16)`, `.padding(.horizontal, 12)`, `spacing: 8`
                 (stacks, grids), `EdgeInsets(top: 8, …)` / `UIEdgeInsets(…)`
                 with any raw non-zero number.
  border_radius  `.cornerRadius(12)`, `RoundedRectangle(cornerRadius: 12)`,
                 `layer.cornerRadius = 12`.
  duration       `.easeInOut(duration: 0.3)` and friends, `.spring(response: 0.4…)`,
                 `.delay(0.2)`, `UIView.animate(withDuration: 0.3 …)`.

Zero is never a finding (`.padding(0)` is idiomatic). An argument that is a
name (`.padding(Spacing.md)`) never matches — every pattern requires a numeric
literal where the token would go.

**Token definitions are not violations.** Definition sites are recognised from
the enclosing declaration, never from the file name:

  - a `static let` / `static var` (stored or computed, single- or multi-line),
    or a top-level `let`/`var`;
  - anything inside `extension Color` / `UIColor` / `NSColor` / `CGColor` /
    `ShapeStyle` / `Font` (the palette-extension idiom);
  - a stored `let`/`var` member, or a computed property whose type is a colour,
    of a type that does not conform to `View` (`struct Palette { let primary =
    Color(…) }`, `enum Brand { var color: Color { switch self { … } } }`).

A local `let c = Color(red: …)` inside a view body, and a member of a `View`
type, are still reported. Token files written some other way belong in
exceptions.json `color.allowlistFiles`.

## Capabilities

  checks()                 yes
  reduced_motion_checks()  yes — config-driven like dart; the signal is
                           `accessibilityReduceMotion` / `UIAccessibility
                           .isReduceMotionEnabled` / the didChange notification,
                           or a name the file binds one of those to.
  IMPORT_RE                yes — `import Module`, `@testable import`, `import
                           struct Module.Type`. Targets are MODULE names, not
                           paths, so `audit_adapter_pattern` (regex over targets)
                           works and `audit_layer_boundaries` (path-rooted
                           layers) refuses — see IMPORT_TARGETS.
  token_names              not implemented: Swift tokens are static members of
                           arbitrary types and cannot be enumerated without a
                           parser. audit_tokens reads the absence as "cannot tell".
  WIDGET_SHAPE_GLOB        not set — the constructor-shape parser is Dart-shaped,
                           so promotion-candidates / reinvented-components refuse.
  focus order, semantics,  not implemented — those audits refuse (exit 2).
  copy, token repair,
  contracts, colour roles
"""
from __future__ import annotations

import re

from . import _native
from .base import AdapterContext, Check, CheckSet

NAME = "swift"
FILE_GLOBS = ("**/*.swift",)
# SwiftGen / Sourcery / R.swift output: generated, never hand-edited.
GENERATED_SUFFIXES = (".generated.swift", "+Generated.swift", "R.generated.swift")

# `import SwiftUI`, `@testable import Core`, `import struct Foo.Bar`. Group 1 is
# the module path (dotted for a submodule/decl import).
IMPORT_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*import\s+(?:(?:typealias|struct|class|enum|protocol|let|var|func)\s+)?"
    r"([A-Za-z_][\w.]*)", re.M)
# What an import target names. "path" stacks (dart, tsx) can have a layer
# rule rooted at a directory; "module" stacks cannot, and a path-rooted audit
# that matched nothing would print clean — so it must refuse instead.
IMPORT_TARGETS = "module"

_NUM = r"-?\d+(?:\.\d+)?"

COLOR_RE = re.compile(
    r"(?<![\w.])(?:Color|UIColor|NSColor|CGColor|\.init)\(\s*(?:\.\w+\s*,\s*)?"
    r"(?:red|white|hue|displayP3Red|srgbRed)\s*:\s*" + _NUM
    + r"|#colorLiteral\([^)]*\)"
    r"|(?<![\w.])(?:Color|UIColor|NSColor)\(\s*hex\s*:\s*[^)]*\)"
    r"|\"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\"")
SPACING_RE = re.compile(
    r"\.padding\(\s*(?:\[[^\]]*\]\s*,\s*|\.\w+\s*,\s*)?(" + _NUM + r")\s*\)"
    r"|(?<![\w.])spacing\s*:\s*(" + _NUM + r")\b"
    r"|(?<![\w.])(?:UI|NS)?EdgeInsets\(([^)]*)\)")
RADIUS_RE = re.compile(
    r"\.cornerRadius\(\s*(" + _NUM + r")"
    r"|cornerRadius\s*:\s*(" + _NUM + r")"
    r"|\.cornerRadius\s*=\s*(" + _NUM + r")")
DURATION_RE = re.compile(
    r"\.(?:easeInOut|easeIn|easeOut|linear|interpolatingSpring|smooth|snappy|bouncy)"
    r"\(\s*duration\s*:\s*(" + _NUM + r")"
    r"|\.(?:spring|interactiveSpring)\(\s*(?:response|duration)\s*:\s*(" + _NUM + r")"
    r"|\.delay\(\s*(" + _NUM + r")\s*\)"
    r"|\bwithDuration\s*:\s*(" + _NUM + r")")

_ARG_NUM_RE = re.compile(r"(?::\s*|^\s*|,\s*)(" + _NUM + r")\b")
# A token definition: `static let x = <literal>` anywhere, or `let x = <literal>`
# at column 0. The literal must be the whole right-hand side's start.
_DEFINITION_RE = re.compile(
    r"(?:^\s*(?:(?:public|internal|private|fileprivate|@\w+)\s+)*static\s+(?:let|var)"
    r"|^(?:(?:public|internal|private|fileprivate)\s+)*(?:let|var))"
    r"\s+\w+\s*(?::\s*[\w.]+\s*)?=\s*(?:Color|UIColor|NSColor)?\(?\s*$")


_MODS = r"(?:(?:public|internal|private|fileprivate|open|final|nonisolated|lazy|@\w+(?:\([^)]*\))?)\s+)*"
_STATIC_DECL_RE = re.compile(r"^\s*" + _MODS + r"(?:static|class)\s+" + _MODS + r"(?:let|var)\b")
_MEMBER_DECL_RE = re.compile(r"^\s*" + _MODS + r"(?:let|var)\b")
_TYPE_HEADER_RE = re.compile(r"\b(struct|class|enum|actor|extension)\s+([\w.]+)([^{]*)$")
_PALETTE_EXT_RE = re.compile(r"\bextension\s+(?:SwiftUI\.|UIKit\.)?(?:Color|UIColor|NSColor|CGColor|ShapeStyle|Font|UIFont)\b")
_COLOR_PROP_RE = re.compile(
    r"^\s*" + _MODS + r"(?:static\s+)?var\s+\w+\s*:\s*(?:some\s+)?(?:SwiftUI\.)?"
    r"(?:Color|UIColor|NSColor|CGColor|ShapeStyle)\b")


def _scopes(source: str, offset: int):
    """Headers of the brace scopes enclosing `offset`, outermost first."""
    stack, last = [], 0
    for i in range(offset):
        c = source[i]
        if c == "{":
            header = source[last:i]
            stack.append(header.strip().splitlines()[-1].strip() if header.strip() else "")
            last = i + 1
        elif c == "}":
            if stack:
                stack.pop()
            last = i + 1
        elif c in ";\n" and source[last:i].strip() == "":
            last = i + 1
    return stack


def _statement_head(source: str, offset: int) -> str:
    """The first line of the (possibly multi-line) statement containing offset."""
    start = source.rfind("\n", 0, offset) + 1
    while start > 0:
        prev_start = source.rfind("\n", 0, start - 1) + 1
        prev = source[prev_start:start - 1].rstrip()
        cur = source[start:offset].lstrip()
        if prev.endswith(("(", ",", "=", "[")) or cur.startswith((".", ")", "]")):
            start = prev_start
            continue
        break
    return source[start:offset]


def _is_definition(source: str, offset: int) -> bool:
    head = _statement_head(source, offset)
    if _DEFINITION_RE.match(_native.line_prefix(source, offset)) or _STATIC_DECL_RE.match(head):
        return True
    scopes = _scopes(source, offset)
    if not scopes and _MEMBER_DECL_RE.match(head):
        return True  # top-level let/var
    if any(_PALETTE_EXT_RE.search(h) for h in scopes):
        return True
    if any(_STATIC_DECL_RE.match(h) for h in scopes):
        return True  # inside a static computed property
    # The innermost enclosing type decides member semantics.
    type_idx = None
    for i in range(len(scopes) - 1, -1, -1):
        if _TYPE_HEADER_RE.search(scopes[i]):
            type_idx = i
            break
    if type_idx is None:
        return False
    conforms = _TYPE_HEADER_RE.search(scopes[type_idx]).group(3)
    if re.search(r"\bView\b|\bViewModifier\b|\bShape\b|\bApp\b|\bScene\b|(?:UI|NS)\w*(?:View|ViewController|Cell|Button|Label)\b", conforms):
        return False
    inner = scopes[type_idx + 1:]
    if not inner:
        return bool(_MEMBER_DECL_RE.match(head))  # stored member of a non-View type
    return bool(_COLOR_PROP_RE.match(inner[0]))  # colour-typed computed property


def _real(m, source) -> bool:
    if _native.in_comment(source, m.start()):
        return False
    return not _is_definition(source, m.start())


def _numeric(m, source) -> bool:
    """A finding only if some captured argument is a non-zero numeric literal."""
    if not _real(m, source):
        return False
    groups = [g for g in m.groups() if g is not None]
    if not groups:
        return True
    for g in groups:
        nums = [g] if re.fullmatch(_NUM, g.strip()) else _ARG_NUM_RE.findall(g)
        if any(not _native.is_zero(n) for n in nums):
            return True
    return False


def checks(ctx: AdapterContext) -> CheckSet:
    return CheckSet([
        Check("color", COLOR_RE, accept=_real, category="color"),
        Check("spacing", SPACING_RE, accept=_numeric),
        Check("border_radius", RADIUS_RE, accept=_numeric),
        Check("duration", DURATION_RE, accept=_numeric, tags=("motion",)),
    ])


REDUCED_MOTION_SIGNAL_RE = re.compile(
    r"\baccessibilityReduceMotion\b|\bisReduceMotionEnabled\b"
    r"|\breduceMotionStatusDidChangeNotification\b")
# `@Environment(\.accessibilityReduceMotion) private var reduceMotion`
# `let reduce = UIAccessibility.isReduceMotionEnabled`
REDUCED_MOTION_BINDING_RE = re.compile(
    r"@Environment\(\s*\\\.accessibilityReduceMotion\s*\)\s*(?:(?:private|fileprivate|internal)\s+)?var\s+(\w+)"
    r"|(?:let|var)\s+(\w+)\s*(?::\s*Bool\s*)?=\s*UIAccessibility\.isReduceMotionEnabled")


class _Binding:
    """findall over an alternation returns tuples; flatten to names."""
    def findall(self, source):
        return [a or b for a, b in REDUCED_MOTION_BINDING_RE.findall(source)]


def reduced_motion_checks(ctx: AdapterContext) -> CheckSet:
    return _native.reduced_motion_checks(ctx, REDUCED_MOTION_SIGNAL_RE, _Binding())
