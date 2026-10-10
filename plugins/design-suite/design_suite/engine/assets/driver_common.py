"""Shared helpers for the asset-pipeline render/animate drivers — the small
core that was duplicated (sRGB->linear conversion, `ctx` construction) across
gen_render.py, animate_render.py, recolor_render.py, shape_spec.py, and every
script that builds the `ctx` object passed to a generator's `build(ctx)`.

Pure python3, no bpy import — safe to import from a plain python3 script
(shapes_svg_render.py) or from inside Blender (every other driver).

Consolidated after the same photometric-conversion function existed in four
places and the same `ctx` construction in five — the kind of duplication
that lets a fix in one copy silently miss the others.
"""

from __future__ import annotations

import random
import types


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(hex_str: str, alpha: float = 1.0) -> tuple:
    h = hex_str.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


def apply_render_determinism(scene, *, quiet: bool = False) -> dict:
    """Pin the render settings that are wrong-by-default for brand assets.

    Takes an already-created `scene` and duck-types on it, so this module stays bpy-free
    per the contract above. Returns what it set, so a caller can log it.

    Two defects, both measured rather than assumed.

    1. COLOUR. `hex_to_linear_rgba` converts sRGB->linear on the INPUT side, but the
       output side was unmanaged, so every asset was tone-mapped through Blender's default
       view transform -- AgX, a filmic curve that deliberately desaturates. Measured
       round-trip, emission shader fed the exact linear value we compute, read back from
       the written PNG (max per-channel error, /255):

           hex        Standard   AgX (the default)   Khronos PBR Neutral
           #0B5FFF      1          48                  23
           #E4002B      1          45                   7
           #00A878      1          48                   1
           #F5A623      1          44                  12

       Brand orange #F5A623 was rendering as muddy tan #C99549, a ~17% shift. Invisible
       at 24dp; obvious on a slide beside a title bar in the same token colour.

       Standard is NOT the safe fix it looks like: it is exact at or below 1.0 and then
       clips with a hue skew -- the same blue driven up in exposure goes
       #0A5EFE -> #1EB3FF -> #41FFFF, i.e. cyan. The studio rig runs a 900-energy key on
       glossy materials and lives above 1.0 constantly. Khronos PBR Neutral is
       near-identity at base colour and rolls off without the skew. Needs Blender >= 4.2.

    2. DETERMINISM. Pixels were bit-identical across repeated runs in every configuration
       tested, including Cycles with OpenImageDenoise on -- while the PNG bytes differed
       every time. The cause is stamp metadata: tEXt chunks carrying Date and RenderTime.

           stamps=True   4c683d24 | 2a570195 | 3f569617   *** BYTES DIFFER ***
           stamps=False  c6734059 | c6734059 | c6734059   BYTE-IDENTICAL

       Without this a golden corpus fails 100% of the time for reasons unrelated to
       rendering, which is how a corpus gets blanket-updated and stops certifying anything.
    """
    applied = {}

    try:
        scene.view_settings.view_transform = "Khronos PBR Neutral"
        applied["view_transform"] = "Khronos PBR Neutral"
    except (TypeError, AttributeError):  # pragma: no cover - Blender < 4.2
        try:
            scene.view_settings.view_transform = "Standard"
            applied["view_transform"] = "Standard"
            if not quiet:
                print("WARN: Khronos PBR Neutral needs Blender 4.2+; falling back to Standard")
        except (TypeError, AttributeError):
            applied["view_transform"] = None

    r = getattr(scene, "render", None)
    if r is not None:
        try:
            r.use_stamp = False
        except (AttributeError, TypeError):  # pragma: no cover
            pass
        # Blender exposes ~20 individual use_stamp_* toggles and the set differs between
        # versions, so enumerate rather than name them and risk missing one silently.
        for attr in (a for a in dir(r) if a.startswith("use_stamp_")):
            try:
                setattr(r, attr, False)
            except (AttributeError, TypeError):  # pragma: no cover - read-only on some builds
                pass
        applied["stamps"] = False

    # Sampling seed. The default is 0, but leaving it implicit means an opened .blend can
    # carry its own and the render stops being reproducible for a reason nothing reports.
    cycles = getattr(scene, "cycles", None)
    if cycles is not None:
        try:
            cycles.seed = 0
            cycles.use_animated_seed = False
            applied["cycles_seed"] = 0
        except (AttributeError, TypeError):  # pragma: no cover
            pass

    return applied


def build_ctx(palette: dict, params: dict, *, bpy=None, linear: bool = True):
    """Build the `ctx` object passed to a generator's `build(ctx)`.

    linear=True — the gen_render.py/animate_render.py contract: `ctx.color`/
    `ctx.hex` return LINEAR RGBA TUPLES, ready to plug straight into a
    Principled BSDF Base Color. Most generator scripts (`gen.py`) use this.

    linear=False — the "shapes" generator kind's contract (see
    {{doc:assets}} §10): `ctx.color`/`ctx.hex` return the RAW HEX STRING,
    unconverted. A `shapes.py` `build(ctx)` returns plain shape-spec dicts
    (`color: "#RRGGBB"`); conversion to linear happens later, per-material,
    in whichever renderer consumes the spec (the flat SVG renderer embeds
    the hex literally; the skeuomorphic 3D renderer converts itself via
    `hex_to_linear_rgba`) — pre-converting here would be wrong for the flat
    path, so this variant is a deliberate passthrough, not an oversight.

    `bpy` becomes `ctx.bpy` only when passed. A "shapes" `build(ctx)` never
    touches bpy by design — that's exactly what lets one `shapes.py` drive
    both the flat and skeuomorphic renderers — so shapes-kind callers omit it.
    """
    seed = int(params.get("seed", 0))
    kwargs = dict(
        params=params,
        seed=seed,
        rng=random.Random(seed),
        palette=palette,
    )
    if linear:
        kwargs["color"] = lambda key: hex_to_linear_rgba(
            palette[key]["hex"], palette[key].get("alpha", 1.0)
        )
        kwargs["hex"] = hex_to_linear_rgba
    else:
        kwargs["color"] = lambda key: palette[key]["hex"]
        kwargs["hex"] = lambda h: h
    if bpy is not None:
        kwargs["bpy"] = bpy
    return types.SimpleNamespace(**kwargs)
