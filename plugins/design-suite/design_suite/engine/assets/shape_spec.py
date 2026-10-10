"""Shared shape-spec helpers for the "shapes" generator kind.

One small, data-driven description of an icon's geometry that can be
rendered EITHER as a flat 2D SVG (shapes_svg_render.py, plain python3) OR as
a layered, beveled, glossy 3D "skeuomorphic" scene (shapes_blender_render.py,
inside Blender) — from the exact same source. Pure python3, no bpy import —
safe to import from either renderer.

A generated/<id>/shapes.py file defines:

    def build(ctx) -> list[dict]

returning a list of shape dicts, each one of:

  {"type": "ellipse", "cx", "cy", "rx", "ry", "rotation"?, "pivot"?,
   "color", "gradient_to"?, "depth"?}
  {"type": "circle", "cx", "cy", "r",
   "color", "gradient_to"?, "depth"?}
  {"type": "path", "d": "<svg path d-string, M/L/Q/Z only>",
   "color"?, "gradient_to"?, "stroke"?, "stroke_width"?, "depth"?}

Common fields:
  color         hex string "#RRGGBB" — required unless the shape is
                stroke-only (a bare line, e.g. a stem)
  gradient_to   optional hex string — a second stop for a soft two-tone
                gradient (linear for ellipse/circle, radial reads better for
                circle). Omit for a flat single color.
  depth         0..1, where 0 = furthest back, 1 = furthest forward. Only
                consulted by the 3D skeuomorphic renderer, which stacks
                shapes front-to-back by this value (the Apple-icon "layered"
                look — see {{doc:assets}} "shapes" section). The flat 2D
                renderer ignores it and uses list order (paint order) only —
                if the two disagree, list order wins for 2D, depth wins
                for 3D, since each is the unambiguous ordering for its own
                medium. Defaults to an even spread across the list if
                omitted, so old specs without explicit depth still stack
                sensibly in 3D.
  rotation      degrees, ellipse only — rotates the shape's own long axis
                AND its position around `pivot` (or its own centre if no
                pivot given). Used for e.g. flower petals arranged radially.
  pivot         (x, y) — rotation center; defaults to the shape's own centre.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import srgb_to_linear, hex_to_linear_rgba  # noqa: E402,F401 — re-exported for callers that do `ss.hex_to_linear_rgba(...)`


def rotate_point(x: float, y: float, pivot: tuple, angle_deg: float) -> tuple:
    px, py = pivot
    a = math.radians(angle_deg)
    dx, dy = x - px, y - py
    rx = dx * math.cos(a) - dy * math.sin(a)
    ry = dx * math.sin(a) + dy * math.cos(a)
    return px + rx, py + ry


def normalize(shapes: list) -> list:
    """Fill in defaults so both renderers can rely on every key existing."""
    out = []
    n = max(1, len(shapes) - 1)
    for i, s in enumerate(shapes):
        s = dict(s)
        s.setdefault("depth", i / n if n else 0.0)
        s.setdefault("gradient_to", None)
        s.setdefault("rotation", 0)
        s.setdefault("pivot", None)
        s.setdefault("stroke", None)
        s.setdefault("stroke_width", 0)
        out.append(s)
    return out


def effective_pivot(shape: dict) -> tuple:
    """The pivot to rotate around — explicit `pivot`, else the shape's own
    centre (works for ellipse/circle; path shapes should always set an
    explicit pivot if they use rotation, since they have no single centre)."""
    if shape.get("pivot"):
        return shape["pivot"]
    if shape["type"] in ("ellipse", "circle"):
        return (shape["cx"], shape["cy"])
    return (0.0, 0.0)
