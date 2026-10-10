"""A project's declared design tokens — names *and values* — as DTCG values.

The DTCG exporter and the drift check both need what the adapters' existing
enumeration does not give them: the value of every token, typed. This module
adds that without touching any adapter's check logic:

  * **dart** reuses `adapters.dart.token_declarations(ctx, "")` — the existing
    value enumerator band-1 repair already depends on, called with an empty
    prefix so it returns every `static const`.
  * **tsx / web** read CSS custom properties from the profile's token file —
    a Tailwind v4 `@theme` block or a `:root` block. A JavaScript
    `tailwind.config.*` is **refused**: `tailwind_theme` enumerates its names
    without executing it, but values would need the same parse, and a theme
    built by code would come back partial. Partial is the silent kind of wrong.
  * **swift / kotlin** have no token enumeration in their adapters at all; the
    profile's `tokens.source` file is read for `static let` / `val`
    declarations here. This is new and `unverified`.

Every declaration either converts to a DTCG `(type, value)` or is returned as
**unrepresentable with a reason**. Nothing is dropped. The caller (export or
drift) decides how to surface it; both surface it.

Converting is a judgement from the literal's own syntax, never from guessing a
token's purpose — with two exceptions stated where they happen: a unitless
number in a name segment `weight` becomes a fontWeight, and a string in a name
segment `font`/`family` becomes a fontFamily. Everything else unitless is a
DTCG `number`, because the code does not say what unit it means.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..adapters.base import AdapterContext, CapabilityError
from . import dtcg

EXT = "io.github.irfan-dahir.design-suite"   # reverse-domain $extensions key (spec 2025.10)


@dataclass
class Decl:
    name: str          # as written in code: `colorPrimary`, `color-primary`
    raw: str           # right-hand side text
    file: str          # repo-relative


@dataclass
class Converted:
    decl: Decl
    path: tuple
    type: str | None = None
    value: object = None
    alias: str | None = None        # code name of the aliased token
    note: str | None = None         # lossy-but-stated mapping (e.g. dp -> px)
    reason: str | None = None       # set iff unrepresentable


# ----------------------------------------------------------------- reading --

def _source_file(ctx: AdapterContext, lang: str) -> Path:
    source = (ctx.profile.get("tokens", {}) or {}).get("source", {}) or {}
    rel = source.get("path")
    if source.get("kind") == "package" or not rel:
        raise CapabilityError("token values", lang,
                              "tokens.source is not a single file path in the profile")
    p = Path(str(ctx.repo)) / rel
    if not p.is_file():
        raise CapabilityError("token values", lang, f"tokens.source.path {rel} does not exist")
    return p


def declarations(ctx: AdapterContext, lang: str) -> list[Decl]:
    """Every declared token as `Decl`. Raises CapabilityError — never returns
    an empty list for "could not read"."""
    repo = Path(str(ctx.repo))
    if lang == "dart":
        from ..adapters import dart
        got = dart.token_declarations(ctx, "")
        if got is None:
            raise CapabilityError("token values", "dart",
                                  "tokens.source did not resolve to a readable file")
        source = (ctx.profile.get("tokens", {}) or {}).get("source", {}) or {}
        where = source.get("path") or f"{source.get('package')}/{source.get('pathInPackage')}"
        return [Decl(n, v, where) for n, v in got.items()]
    if lang in ("tsx", "web"):
        p = _source_file(ctx, lang)
        if p.suffix != ".css":
            raise CapabilityError(
                "token values", lang,
                f"{p.name} is not CSS. Values are read from CSS custom properties "
                f"(a Tailwind v4 @theme block or :root) only; a JS tailwind config "
                f"is never executed, and a partial parse would be a silent omission")
        return css_declarations(p.read_text(), str(p.relative_to(repo)))
    if lang == "swift":
        p = _source_file(ctx, lang)
        return _native(p.read_text(), str(p.relative_to(repo)),
                       r"^\s*(?:public\s+|internal\s+)?static\s+let\s+(\w+)\s*(?::\s*[\w.<>?]+)?\s*=\s*(.+?)\s*$")
    if lang == "kotlin":
        p = _source_file(ctx, lang)
        return _native(p.read_text(), str(p.relative_to(repo)),
                       r"^\s*(?:(?:public|internal|const|private)\s+)*val\s+(\w+)\s*(?::\s*[\w.<>?]+)?\s*=\s*(.+?)\s*$")
    raise CapabilityError("token values", lang, "no token value reader for this adapter")


def _native(text, rel, pattern):
    out = []
    for m in re.finditer(pattern, text, re.M):
        raw = re.sub(r"\s*//.*$", "", m.group(2)).rstrip(";").strip()
        out.append(Decl(m.group(1), raw, rel))
    return out


_BLOCK_RE = re.compile(r"(@theme\b[^{]*|:root\b[^{]*)\{", re.I)
_PROP_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);")


def css_declarations(text: str, rel: str) -> list[Decl]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    out = []
    for m in _BLOCK_RE.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        for p in _PROP_RE.finditer(text[m.end():i - 1]):
            out.append(Decl(p.group(1), p.group(2).strip(), rel))
    return out


# -------------------------------------------------------------- converting --

def path_for(name: str) -> tuple:
    """`color-brand-500` -> (color, brand, 500); `colorPrimaryDark` -> (color, primary, dark)."""
    if "-" in name or "_" in name:
        parts = re.split(r"[-_]+", name)
    else:
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name) or [name]
    return tuple(p.lower() for p in parts if p)


def _n(t):
    return dtcg._num(t)


FLUTTER_CURVES = {  # Flutter's documented Cubic constants
    "ease": [0.25, 0.1, 0.25, 1.0], "easeIn": [0.42, 0.0, 1.0, 1.0],
    "easeOut": [0.0, 0.0, 0.58, 1.0], "easeInOut": [0.42, 0.0, 0.58, 1.0],
    "linear": [0.0, 0.0, 1.0, 1.0],
}
CSS_EASINGS = {  # CSS Easing Functions Level 1 keyword definitions
    "ease": [0.25, 0.1, 0.25, 1.0], "ease-in": [0.42, 0.0, 1.0, 1.0],
    "ease-out": [0.0, 0.0, 0.58, 1.0], "ease-in-out": [0.42, 0.0, 0.58, 1.0],
    "linear": [0.0, 0.0, 1.0, 1.0],
}
NUM = r"-?\d*\.?\d+"


def _rgb_color(r, g, b, a=None, scale=255.0):
    comps = [round(float(x) / scale, 6) for x in (r, g, b)]
    hexs = "#" + "".join(f"{round(c * 255):02x}" for c in comps)
    out = {"colorSpace": "srgb", "components": comps, "hex": hexs}
    if a is not None and float(a) != 1:
        out["alpha"] = round(float(a), 6)
    return out


def _argb_hex(h):
    h = h.lower()
    if len(h) == 6:
        h = "ff" + h
    if len(h) != 8:
        return None
    return dtcg._hex_to_color("#" + h[2:] + h[:2])


def _css_color(v):
    v = v.strip()
    if v.startswith("#"):
        return dtcg._hex_to_color(v)
    m = re.fullmatch(rf"rgba?\(\s*({NUM})[\s,]+({NUM})[\s,]+({NUM})\s*(?:[,/]\s*({NUM})(%?)\s*)?\)", v)
    if m:
        a = m.group(4)
        if a is not None and m.group(5):
            a = float(a) / 100
        return _rgb_color(m.group(1), m.group(2), m.group(3), a)
    return None


def _css_dim(v):
    m = re.fullmatch(rf"({NUM})(px|rem)", v.strip())
    if m:
        return {"value": _n(m.group(1)), "unit": m.group(2)}
    if re.fullmatch(r"-?0*\.?0+", v.strip()):
        return {"value": 0, "unit": "px"}
    return None


def _css_shadow(v):
    layers = []
    for part in re.split(r",(?![^()]*\))", v):
        part = part.strip()
        inset = False
        if part.startswith("inset "):
            inset, part = True, part[6:].strip()
        cm = re.search(r"(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))", part)
        if not cm:
            return None
        color = _css_color(cm.group(1))
        lens = (part[:cm.start()] + " " + part[cm.end():]).split()
        if color is None or len(lens) not in (2, 3, 4):
            return None
        dims = [_css_dim(x) for x in lens] + [{"value": 0, "unit": "px"}] * (4 - len(lens))
        if any(d is None for d in dims):
            return None
        layer = {"color": color, "offsetX": dims[0], "offsetY": dims[1],
                 "blur": dims[2], "spread": dims[3]}
        if inset:
            layer["inset"] = True
        layers.append(layer)
    return layers[0] if len(layers) == 1 else layers


def _convert_css(d: Decl, path):
    v = d.raw
    if m := re.fullmatch(r"var\(\s*--([A-Za-z0-9_-]+)\s*\)", v):
        return {"alias": m.group(1)}
    if (c := _css_color(v)) is not None:
        return {"type": "color", "value": c}
    if m := re.fullmatch(rf"({NUM})(ms|s)", v):
        return {"type": "duration", "value": {"value": _n(m.group(1)), "unit": m.group(2)}}
    if (dim := _css_dim(v)) is not None and not re.fullmatch(NUM, v):
        return {"type": "dimension", "value": dim}
    if m := re.fullmatch(rf"cubic-bezier\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)", v):
        return {"type": "cubicBezier", "value": [_n(x) for x in m.groups()]}
    if v in CSS_EASINGS:
        return {"type": "cubicBezier", "value": CSS_EASINGS[v]}
    if re.fullmatch(NUM, v):
        if "weight" in path and 1 <= float(v) <= 1000:
            return {"type": "fontWeight", "value": _n(v)}
        return {"type": "number", "value": _n(v)}
    if "font" in path or "family" in path:
        fams = [f.strip().strip("'\"") for f in re.split(r",(?![^()]*\))", v)]
        if all(re.fullmatch(r"[\w .-]+", f) for f in fams):
            return {"type": "fontFamily", "value": fams if len(fams) > 1 else fams[0]}
    if (s := _css_shadow(v)) is not None:
        return {"type": "shadow", "value": s}
    return {"reason": f"no DTCG {dtcg.SPEC_VERSION} type this exporter maps {v!r} to "
                      f"(e.g. oklch/hsl colours, calc(), em/% units, keyword values)"}


def _strip_accessor(raw, accessor):
    if accessor and raw.startswith(accessor + "."):
        return raw[len(accessor) + 1:]
    return raw


def _convert_dart(d: Decl, path, accessor, names):
    v = d.raw.strip()
    if (ref := _strip_accessor(v, accessor)) in names:
        return {"alias": ref}
    if m := re.fullmatch(r"(?:const\s+)?Color\(\s*0x([0-9a-fA-F]{6,8})\s*\)", v):
        if c := _argb_hex(m.group(1)):
            return {"type": "color", "value": c}
    if m := re.fullmatch(r"(?:const\s+)?Duration\(\s*(milliseconds|seconds)\s*:\s*(\d+)\s*\)", v):
        unit = "ms" if m.group(1) == "milliseconds" else "s"
        return {"type": "duration", "value": {"value": int(m.group(2)), "unit": unit}}
    if m := re.fullmatch(r"Curves\.(\w+)", v):
        if m.group(1) in FLUTTER_CURVES:
            return {"type": "cubicBezier", "value": FLUTTER_CURVES[m.group(1)]}
        return {"reason": f"Curves.{m.group(1)} is not one of the cubic curves this exporter knows"}
    if m := re.fullmatch(rf"(?:const\s+)?Cubic\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)", v):
        return {"type": "cubicBezier", "value": [_n(x) for x in m.groups()]}
    if m := re.fullmatch(r"FontWeight\.w(\d00)", v):
        return {"type": "fontWeight", "value": int(m.group(1))}
    if re.fullmatch(NUM, v):
        if "weight" in path and 1 <= float(v) <= 1000:
            return {"type": "fontWeight", "value": _n(v)}
        return {"type": "number", "value": _n(v)}
    if (m := re.fullmatch(r"""['"]([^'"$]+)['"]""", v)) and ("font" in path or "family" in path):
        return {"type": "fontFamily", "value": m.group(1)}
    return {"reason": f"no DTCG {dtcg.SPEC_VERSION} type this exporter maps {v!r} to "
                      f"(EdgeInsets, BorderRadius, TextStyle, BoxShadow and computed "
                      f"values are not mapped)"}


def _convert_native(d: Decl, path, lang, names):
    v = d.raw.strip()
    ref = v.split(".")[-1] if re.fullmatch(r"[\w.]+", v) else v
    if ref in names and not re.fullmatch(NUM, v):
        return {"alias": ref}
    if lang == "kotlin":
        if m := re.fullmatch(r"Color\(\s*0x([0-9a-fA-F]{8})\s*\)", v):
            if c := _argb_hex(m.group(1)):
                return {"type": "color", "value": c}
        if m := re.fullmatch(rf"({NUM})\.(dp|sp)", v):
            return {"type": "dimension", "value": {"value": _n(m.group(1)), "unit": "px"},
                    "note": f"{m.group(2)} exported as px (1{m.group(2)} = 1 logical px); "
                            f"source unit kept in $extensions"}
        if m := re.fullmatch(r"FontWeight\((\d+)\)", v):
            return {"type": "fontWeight", "value": int(m.group(1))}
        named = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Normal": 400,
                 "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800, "Black": 900}
        if (m := re.fullmatch(r"FontWeight\.(\w+)", v)) and m.group(1) in named:
            return {"type": "fontWeight", "value": named[m.group(1)]}
        v = re.sub(r"(?<=\d)[fFL]$", "", v)
    if lang == "swift":
        if m := re.fullmatch(rf"(?:Color|UIColor)\(\s*red:\s*({NUM})\s*,\s*green:\s*({NUM})\s*,"
                             rf"\s*blue:\s*({NUM})\s*(?:,\s*(?:opacity|alpha):\s*({NUM})\s*)?\)", v):
            r, g, b, a = m.groups()
            return {"type": "color", "value": _rgb_color(r, g, b, a, scale=1.0)}
    if re.fullmatch(NUM, v):
        if "weight" in path and 1 <= float(v) <= 1000:
            return {"type": "fontWeight", "value": _n(v)}
        return {"type": "number", "value": _n(v)}
    if (m := re.fullmatch(r'"([^"\\]+)"', v)) and ("font" in path or "family" in path):
        return {"type": "fontFamily", "value": m.group(1)}
    return {"reason": f"no DTCG {dtcg.SPEC_VERSION} type this exporter maps {v!r} to"}


def convert(decls: list[Decl], lang: str, accessor: str = "") -> list[Converted]:
    names = {d.name for d in decls}
    out = []
    for d in decls:
        path = path_for(d.name)
        if lang in ("tsx", "web"):
            got = _convert_css(d, path)
        elif lang == "dart":
            got = _convert_dart(d, path, accessor, names)
        else:
            got = _convert_native(d, path, lang, names)
        c = Converted(d, path, got.get("type"), got.get("value"), got.get("alias"),
                      got.get("note"), got.get("reason"))
        if c.alias is not None and c.alias not in names:
            c.alias, c.reason = None, f"references {d.raw!r}, which is not a declared token"
        out.append(c)
    # Alias types come from their target; a dangling or cyclic chain is unrepresentable.
    by = {c.decl.name: c for c in out}
    for c in out:
        seen, cur = [], c
        while cur.alias is not None and cur.reason is None:
            if cur.decl.name in seen:
                c.reason = "circular alias in code: " + " -> ".join(seen + [cur.decl.name])
                break
            seen.append(cur.decl.name)
            cur = by[cur.alias]
        if c.reason is None and cur.reason is not None:
            c.reason = f"aliases {cur.decl.name}, which is unrepresentable ({cur.reason})"
        elif c.reason is None:
            c.type = cur.type
            if c.alias is None:
                continue
            c.value = cur.value  # resolved; the exporter writes the alias instead
    return out


def read(ctx: AdapterContext, lang: str) -> list[Converted]:
    return convert(declarations(ctx, lang), lang, ctx.token_accessor)
