"""Read, validate and write W3C Design Tokens Community Group (DTCG) files.

Spec: Design Tokens Format Module **2025.10** — a *Final Community Group
Report* (28 October 2025), https://www.designtokens.org/tr/2025.10/format/ .
It is the first stable version of the format, but a Community Group report is
not a W3C Recommendation. Editors' drafts after it exist and are not followed
here; a value only a later draft allows is refused rather than guessed at.

What this module covers, and what it refuses:

  * tokens (`$value`), groups (no `$value`), `$type` inheritance from the
    closest ancestor group, `$description`, `$deprecated`, `$extensions`
    (preserved untouched), the `$root` token of a group
  * curly-brace aliases `{group.token}`, resolved transitively, with missing
    targets, group targets and cycles reported as errors (the spec requires
    cycles to be reported)
  * value shapes for: color, dimension, duration, fontFamily, fontWeight,
    cubicBezier, number, shadow. Composite types beyond shadow (typography,
    border, transition, strokeStyle, gradient) are **accepted as opaque** — kept,
    compared structurally, never interpreted — and listed as such.
  * **refused** (`DtcgError`, exit 2 in the CLIs): JSON Pointer `$ref`
    references and `$extends` group inheritance. Both are in 2025.10; neither is
    implemented, and silently ignoring one would make every token it touches
    compare wrong.

Draft-era files (Tokens Studio's legacy export, pre-2025.10 Style Dictionary,
`"#ff0000"` colours, `"16px"` dimensions, unprefixed `value`/`type`) are
refused by default and normalised only under `legacy=True`, which the CLIs
expose as `--accept-draft-forms`. Normalising silently would let a
non-conforming file pass as a conforming one.

Stdlib only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SPEC_VERSION = "2025.10"
SPEC_URL = "https://www.designtokens.org/tr/2025.10/format/"
SPEC_STATUS = "Final Community Group Report (stable; not a W3C Recommendation)"

TYPES_CHECKED = ("color", "dimension", "duration", "fontFamily", "fontWeight",
                 "cubicBezier", "number", "shadow")
TYPES_OPAQUE = ("typography", "border", "transition", "strokeStyle", "gradient")
KNOWN_TYPES = TYPES_CHECKED + TYPES_OPAQUE

FONT_WEIGHT_ALIASES = {
    "thin": 100, "hairline": 100, "extra-light": 200, "ultra-light": 200,
    "light": 300, "normal": 400, "regular": 400, "book": 400, "medium": 500,
    "semi-bold": 600, "demi-bold": 600, "bold": 700, "extra-bold": 800,
    "ultra-bold": 800, "black": 900, "heavy": 900, "extra-black": 950,
    "ultra-black": 950,
}
GROUP_KEYS = {"$type", "$description", "$deprecated", "$extensions"}
TOKEN_KEYS = {"$value", "$type", "$description", "$deprecated", "$extensions"}
ALIAS_RE = re.compile(r"^\{([^{}]+)\}$")


class DtcgError(ValueError):
    """The input is not a DTCG file this module can read faithfully.

    Always a refusal (exit 2), never a finding: a file that cannot be read is
    not a file with zero drift.
    """


@dataclass
class Token:
    path: tuple
    type: str
    value: object                      # as written (may be an alias string)
    description: str | None = None
    deprecated: object = None
    extensions: dict | None = None
    resolved: object = None            # alias-free value, filled by resolve()
    alias_of: tuple | None = None      # direct alias target, if $value is one
    notes: list = field(default_factory=list)

    @property
    def dotted(self) -> str:
        return ".".join(self.path)


# --------------------------------------------------------------- validation --

def _err(path, msg):
    raise DtcgError(f"{'.'.join(path) or '<root>'}: {msg}")


def _check_name(path, name):
    if name.startswith("$") or any(c in name for c in "{}."):
        _err(path, f"name {name!r} is reserved or contains '{{', '}}' or '.' "
                   f"(spec {SPEC_VERSION} §group/token names)")


def _hex_to_color(hexstr: str):
    h = hexstr.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-fA-F]+", h):
        return None
    comps = [round(int(h[i:i + 2], 16) / 255, 6) for i in (0, 2, 4)]
    out = {"colorSpace": "srgb", "components": comps, "hex": "#" + h[:6].lower()}
    if len(h) == 8:
        a = round(int(h[6:8], 16) / 255, 6)
        if a != 1:
            out["alpha"] = a
    return out


_DIM_STR = re.compile(r"^(-?\d*\.?\d+)(px|rem|ms|s)$")


def _legacy_value(type_, value):
    """Normalise a draft-era scalar into its 2025.10 object form, or None."""
    if not isinstance(value, str):
        return None
    if type_ == "color":
        return _hex_to_color(value) if value.startswith("#") else None
    m = _DIM_STR.match(value.strip())
    if m and type_ == "dimension" and m.group(2) in ("px", "rem"):
        return {"value": _num(m.group(1)), "unit": m.group(2)}
    if m and type_ == "duration" and m.group(2) in ("ms", "s"):
        return {"value": _num(m.group(1)), "unit": m.group(2)}
    return None


def _num(text):
    f = float(text)
    return int(f) if f.is_integer() else f


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_value(type_: str, value, path=(), legacy=False):
    """The value, validated (and under `legacy`, normalised). Raises DtcgError."""
    if isinstance(value, str) and ALIAS_RE.match(value):
        return value
    if legacy:
        norm = _legacy_value(type_, value)
        if norm is not None:
            return norm
    if type_ == "color":
        if not isinstance(value, dict) or "colorSpace" not in value or \
                not isinstance(value.get("components"), list):
            _err(path, f"color $value must be an object with colorSpace and components "
                       f"(spec {SPEC_VERSION}); got {value!r}"
                       + ("" if legacy else " — a draft-era hex string is accepted only "
                          "with --accept-draft-forms"))
        for c in value["components"]:
            if not (_is_num(c) or c == "none"):
                _err(path, f"color component {c!r} is not a number or 'none'")
        if "alpha" in value and not (_is_num(value["alpha"]) and 0 <= value["alpha"] <= 1):
            _err(path, "color alpha must be a number in [0, 1]")
        return value
    if type_ in ("dimension", "duration"):
        units = ("px", "rem") if type_ == "dimension" else ("ms", "s")
        if not (isinstance(value, dict) and _is_num(value.get("value"))
                and value.get("unit") in units):
            _err(path, f"{type_} $value must be {{value: number, unit: {'|'.join(units)}}}; "
                       f"got {value!r}")
        return value
    if type_ == "number":
        if not _is_num(value):
            _err(path, f"number $value must be a JSON number; got {value!r}")
        return value
    if type_ == "fontFamily":
        if isinstance(value, str) or (isinstance(value, list) and value
                                      and all(isinstance(v, str) for v in value)):
            return value
        _err(path, f"fontFamily $value must be a string or array of strings; got {value!r}")
    if type_ == "fontWeight":
        if _is_num(value) and 1 <= value <= 1000:
            return value
        if isinstance(value, str) and value in FONT_WEIGHT_ALIASES:
            return value
        _err(path, f"fontWeight $value must be 1-1000 or a spec alias; got {value!r}")
    if type_ == "cubicBezier":
        if (isinstance(value, list) and len(value) == 4 and all(_is_num(v) for v in value)
                and 0 <= value[0] <= 1 and 0 <= value[2] <= 1):
            return value
        _err(path, f"cubicBezier $value must be [x1,y1,x2,y2] with x in [0,1]; got {value!r}")
    if type_ == "shadow":
        layers = value if isinstance(value, list) else [value]
        out = []
        for i, layer in enumerate(layers):
            if isinstance(layer, str) and ALIAS_RE.match(layer):
                out.append(layer)
                continue
            if not isinstance(layer, dict):
                _err(path, f"shadow layer {i} must be an object")
            for k in ("color", "offsetX", "offsetY", "blur", "spread"):
                if k not in layer:
                    _err(path, f"shadow layer {i} is missing {k!r}")
            fixed = dict(layer)
            fixed["color"] = check_value("color", layer["color"], path + (f"[{i}].color",), legacy)
            for k in ("offsetX", "offsetY", "blur", "spread"):
                fixed[k] = check_value("dimension", layer[k], path + (f"[{i}].{k}",), legacy)
            if "inset" in layer and not isinstance(layer["inset"], bool):
                _err(path, f"shadow layer {i} inset must be a boolean")
            out.append(fixed)
        return out if isinstance(value, list) else out[0]
    if type_ in TYPES_OPAQUE:
        return value
    _err(path, f"unknown $type {type_!r}; this reader knows {', '.join(KNOWN_TYPES)}")


def _legacy_keys(node: dict) -> dict:
    """Under --accept-draft-forms, `value`/`type`/`description` → `$`-forms."""
    if "$value" in node or "value" not in node:
        return node
    out = {}
    for k, v in node.items():
        out[("$" + k) if k in ("value", "type", "description") else k] = v
    return out


def parse(doc, legacy: bool = False) -> dict:
    """`{path tuple: Token}` for every token in `doc`, aliases resolved.

    Raises DtcgError on anything not representable faithfully.
    """
    if not isinstance(doc, dict):
        raise DtcgError("<root>: a DTCG file must be a JSON object")
    tokens: dict = {}
    groups: set = {()}

    def walk(node, path, inherited):
        if legacy:
            node = _legacy_keys(node)
        if "$ref" in node:
            _err(path, "JSON Pointer `$ref` references are in the spec but not "
                       "implemented here; refusing rather than ignoring them")
        if "$extends" in node:
            _err(path, "`$extends` group inheritance is in the spec but not "
                       "implemented here; refusing rather than ignoring it")
        if "$value" in node:
            extra = [k for k in node if k not in TOKEN_KEYS]
            if extra:
                bad = [k for k in extra if not k.startswith("$")]
                _err(path, f"token has child keys {bad or extra} — an object with "
                           f"$value cannot also be a group")
            type_ = node.get("$type", inherited)
            tokens[path] = Token(path=path, type=type_, value=node["$value"],
                                 description=node.get("$description"),
                                 deprecated=node.get("$deprecated"),
                                 extensions=node.get("$extensions"))
            return
        groups.add(path)
        type_ = node.get("$type", inherited)
        for k, v in node.items():
            if k.startswith("$"):
                if k == "$root":
                    if not isinstance(v, dict):
                        _err(path, "$root must be a token object")
                    walk(v, path + ("$root",), type_)
                elif k not in GROUP_KEYS:
                    _err(path, f"unknown group property {k!r}")
                continue
            _check_name(path, k)
            if not isinstance(v, dict):
                _err(path + (k,), f"must be a token or group object; got {type(v).__name__}"
                     + (" (draft-era unprefixed keys need --accept-draft-forms)"
                        if k in ("value", "type") else ""))
            walk(v, path + (k,), type_)

    walk(doc, (), None)
    _resolve(tokens, groups, legacy)
    return tokens


def _target(ref: str, tokens, groups, here):
    path = tuple(ref.split("."))
    if path in tokens:
        return path
    if path in groups:
        hint = (f" — its root token is {{{ref}.$root}}" if path + ("$root",) in tokens
                else "")
        _err(here, f"alias {{{ref}}} points at a group, not a token{hint}")
    _err(here, f"alias {{{ref}}} points at nothing")


def _resolve(tokens, groups, legacy):
    for t in tokens.values():
        if isinstance(t.value, str) and (m := ALIAS_RE.match(t.value)):
            t.alias_of = _target(m.group(1), tokens, groups, t.path)

    def final(t, seen):
        if t.path in seen:
            _err(t.path, "circular alias: " + " -> ".join(".".join(p) for p in seen + [t.path]))
        if t.alias_of is None:
            return t
        return final(tokens[t.alias_of], seen + [t.path])

    for t in tokens.values():
        end = final(t, [])
        if t.type is None:
            t.type = end.type  # spec: type may be resolved from the referenced token
        if t.type is None:
            _err(t.path, "no $type on the token, its groups, or its alias target")
        if end.type is not None and end.type != t.type and t.alias_of is not None:
            _err(t.path, f"declared {t.type} but aliases a {end.type}")
    for t in tokens.values():
        if t.alias_of is None:
            t.value = check_value(t.type, t.value, t.path, legacy)
    for t in tokens.values():
        t.resolved = _deep(final(t, []).value, tokens, groups, t.path, t.type, legacy, [])


def _deep(value, tokens, groups, here, type_, legacy, seen):
    """Resolve aliases nested inside composite values (shadow layers, etc.)."""
    if isinstance(value, str) and (m := ALIAS_RE.match(value)):
        p = _target(m.group(1), tokens, groups, here)
        if p in seen:
            _err(here, "circular alias inside a composite value")
        return _deep(tokens[p].value, tokens, groups, here, tokens[p].type, legacy, seen + [p])
    if isinstance(value, list):
        return [_deep(v, tokens, groups, here, type_, legacy, seen) for v in value]
    if isinstance(value, dict):
        return {k: _deep(v, tokens, groups, here, type_, legacy, seen) for k, v in value.items()}
    return value


def load(path: Path, legacy: bool = False) -> dict:
    try:
        doc = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise DtcgError(f"{path}: no such file")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise DtcgError(f"{path}: not valid JSON ({exc})")
    return parse(doc, legacy)


# ---------------------------------------------------------- normalisation ---

def canonical(type_: str, value):
    """A comparable form of a resolved value. Equal canonicals mean equal tokens."""
    if type_ == "color" and isinstance(value, dict):
        comps = value.get("components", [])
        space = value.get("colorSpace")
        if space == "srgb" and value.get("hex") and \
                all(_is_num(c) for c in comps):
            # hex is the 8-bit truth when present; components may carry rounding
            key = value["hex"].lower()
        else:
            key = (space, tuple(round(c, 4) if _is_num(c) else c for c in comps))
        return ("color", key, round(value.get("alpha", 1), 3))
    if type_ in ("dimension", "duration") and isinstance(value, dict):
        v, u = value["value"], value["unit"]
        if u == "s":
            v, u = v * 1000, "ms"
        return (type_, round(float(v), 4), u)
    if type_ == "fontWeight":
        return ("fontWeight", FONT_WEIGHT_ALIASES.get(value, value))
    if type_ == "fontFamily":
        return ("fontFamily", tuple([value] if isinstance(value, str) else value))
    if type_ == "cubicBezier":
        return ("cubicBezier", tuple(round(float(v), 4) for v in value))
    if type_ == "number":
        return ("number", round(float(value), 6))
    if type_ == "shadow":
        layers = value if isinstance(value, list) else [value]
        return ("shadow", tuple(
            (canonical("color", l["color"]),) + tuple(
                canonical("dimension", l[k]) for k in ("offsetX", "offsetY", "blur", "spread"))
            + (bool(l.get("inset", False)),) for l in layers))
    return (type_, json.dumps(value, sort_keys=True))


def name_key(parts) -> str:
    """The stack-neutral comparison key for a token path or a code name.

    Lower-case, alphanumerics only, `$root` dropped: `color.primary`,
    `--color-primary` and `colorPrimary` all key to `colorprimary`. Two names
    that collide on this key are reported as ambiguous, never merged.
    """
    return "".join(re.sub(r"[^0-9a-zA-Z]", "", p).lower()
                   for p in parts if p != "$root")


# ----------------------------------------------------------------- writing ---

def build(entries) -> dict:
    """A DTCG document from `[(path tuple, $type, $value, $description|None, ext|None)]`.

    A path that is both a token and a prefix of another token becomes that
    group's `$root` token, which is how 2025.10 spells "a group with a value".
    """
    paths = {tuple(e[0]) for e in entries}
    prefixes = {p[:i] for p in paths for i in range(1, len(p))}
    doc: dict = {}
    for path, type_, value, desc, ext in entries:
        path = tuple(path)
        node = doc
        for part in path[:-1]:
            node = node.setdefault(part, {})
        tok = {"$type": type_, "$value": value}
        if desc:
            tok["$description"] = desc
        if ext:
            tok["$extensions"] = ext
        if path in prefixes:
            node.setdefault(path[-1], {})["$root"] = tok
        else:
            node[path[-1]] = tok
    return doc


def alias_ref(path: tuple, all_paths: set) -> str:
    """`{a.b}` for a token path. A path that `build` turns into a group's root
    token is referenced as `{a.b.$root}` — 2025.10 makes `{a.b}` an invalid
    reference to the group itself."""
    path = tuple(path)
    is_prefix = any(len(p) > len(path) and p[:len(path)] == path for p in all_paths)
    return "{" + ".".join(path + (("$root",) if is_prefix else ())) + "}"
