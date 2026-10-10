"""Skeuomorphic 3D renderer for the "shapes" generator kind. Runs INSIDE
Blender. Builds a LAYERED STACK of beveled, glossy shapes from a shapes.py
shape-spec (see shape_spec.py) — the same source the flat 2D renderer
(shapes_svg_render.py) consumes — producing an "Apple icon" look (think the
old iOS Notes/Weather icons: separate rounded flat shapes at slightly
different depths with soft bevels and gloss, not one solid extrusion).

Invoked by pipeline.py as:
  blender -b -P shapes_blender_render.py -- \
      --script generated/<id>/shapes.py --palette palette.json \
      --out renders/<id>.png --size 720 --params '{...}'

Coordinate mapping (SVG plane -> Blender world):
  world X =  (svg_x - CENTER) / SCALE
  world Z =  (CENTER - svg_y) / SCALE      (SVG y-down -> world Z-up, flipped)
  world Y = -depth * DEPTH_SCALE           (higher depth = closer to camera;
                                             studio's default camera sits at
                                             negative Y looking toward +Y)

Each shape becomes its own mesh: ellipse/circle -> a filled circular mesh
scaled to (rx, ry), path -> a filled curve-to-mesh (M/L/Q/Z only — the small
subset our own shape specs actually emit, not a general SVG path parser).
Every shape gets a shallow Solidify (a few percent of its own size — Apple's
skeuomorphic depth is SHALLOW, a "sticker" not a solid block) + Bevel
(rounded edge) + a glossy Principled BSDF (color from the shape, optionally a
simple two-stop gradient via a Gradient Texture -> Color Ramp, matching the
flat renderer's gradient_to). All shapes are grouped under one root Empty so
the shared studio rig can light/frame/render them as a single scene.
"""

from __future__ import annotations

import argparse
import json
import math
import runpy
import sys
from pathlib import Path

import bpy  # noqa: F401 — Blender only
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shape_spec as ss  # noqa: E402
import studio  # noqa: E402
import driver_common as dc  # noqa: E402

CENTER = 256.0
SCALE = 130.0
DEPTH_SCALE = 0.55
BEVEL_WIDTH_FRAC = 0.06     # fraction of shape's own min(rx,ry) or r
SOLIDIFY_THICKNESS_FRAC = 0.10


def _to_world_xz(svg_x: float, svg_y: float) -> tuple:
    return (svg_x - CENTER) / SCALE, (CENTER - svg_y) / SCALE


def _make_material(name: str, color_hex: str, gradient_to: str | None,
                    gradient_kind: str = "linear"):
    """gradient_kind: 'linear' (for flat-ish shapes like petals — a spherical
    gradient barely varies across a thin disc viewed near face-on, which is
    what made the first prototype pass read pale/washed-out) or 'radial'
    (for round accents like the center, where radial reads as a natural
    highlight/pop, matching the flat 2D renderer's own gradient choice per
    shape type)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.28
    bsdf.inputs["Coat Weight"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    if gradient_to:
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "QUADRATIC" if gradient_kind == "radial" else "LINEAR"
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        els = ramp.color_ramp.elements
        els[0].position, els[0].color = 0.0, ss.hex_to_linear_rgba(gradient_to)
        els[1].position, els[1].color = 1.0, ss.hex_to_linear_rgba(color_hex)
        nt.links.new(grad.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = ss.hex_to_linear_rgba(color_hex)

    return mat


def _add_bevel_solidify(obj, ref_size: float):
    solid = obj.modifiers.new("Solidify", "SOLIDIFY")
    solid.thickness = max(0.01, ref_size * SOLIDIFY_THICKNESS_FRAC)
    solid.offset = 0.0
    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = max(0.002, ref_size * BEVEL_WIDTH_FRAC)
    bevel.segments = 4


def _build_ellipse(s: dict, index: int):
    cx, cz = _to_world_xz(s["cx"], s["cy"])
    rx, rz = s["rx"] / SCALE, s["ry"] / SCALE

    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=1.0, fill_type="NGON")
    obj = bpy.context.active_object
    obj.name = f"shape{index}_ellipse"
    obj.scale = (rx, rz, 1.0)
    # Built in the XY plane by default; rotate 90 deg about X so its face
    # points along -Y (toward the camera), matching our SVG-plane mapping.
    obj.rotation_euler = (math.radians(90), 0, 0)
    obj.location = (cx, -s["depth"] * DEPTH_SCALE, cz)

    if s["rotation"]:
        pivot_x, pivot_y = ss.effective_pivot(s)
        pcx, pcz = _to_world_xz(pivot_x, pivot_y)
        pivot = bpy.data.objects.new(f"pivot{index}", None)
        bpy.context.scene.collection.objects.link(pivot)
        pivot.location = (pcx, obj.location.y, pcz)
        bpy.context.view_layer.update()
        obj.parent = pivot
        obj.matrix_parent_inverse = pivot.matrix_world.inverted()
        # The icon lives in the world X-Z plane (X from svg_x, Z from
        # svg_y — see _to_world_xz), so an in-plane 2D rotation is a
        # rotation about the Y axis (the plane's normal), NOT Z — a Z
        # rotation would spin things out of the X-Z plane into the depth
        # axis instead of spreading them within their own plane.
        pivot.rotation_euler = (0, math.radians(-s["rotation"]), 0)

    ref_size = min(rx, rz)
    _add_bevel_solidify(obj, ref_size)
    obj.data.materials.append(
        _make_material(f"mat{index}", s["color"], s["gradient_to"], "linear")
    )
    return obj


def _build_circle(s: dict, index: int):
    cx, cz = _to_world_xz(s["cx"], s["cy"])
    r = s["r"] / SCALE

    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=r, fill_type="NGON")
    obj = bpy.context.active_object
    obj.name = f"shape{index}_circle"
    obj.rotation_euler = (math.radians(90), 0, 0)
    obj.location = (cx, -s["depth"] * DEPTH_SCALE, cz)

    _add_bevel_solidify(obj, r)
    obj.data.materials.append(
        _make_material(f"mat{index}", s["color"], s["gradient_to"], "radial")
    )
    return obj


def _parse_path_points(d: str) -> list:
    """Very small M/L/Q/Z parser — only what our own shape specs emit, not a
    general SVG path parser. Returns a flat list of (x, y) points tracing the
    path (quadratic curves are sampled into a handful of line segments)."""
    tokens = d.replace(",", " ").split()
    points = []
    i = 0
    cur = (0.0, 0.0)
    while i < len(tokens):
        cmd = tokens[i]
        if cmd == "M":
            cur = (float(tokens[i + 1]), float(tokens[i + 2]))
            points.append(cur)
            i += 3
        elif cmd == "L":
            cur = (float(tokens[i + 1]), float(tokens[i + 2]))
            points.append(cur)
            i += 3
        elif cmd == "Q":
            ctrl = (float(tokens[i + 1]), float(tokens[i + 2]))
            end = (float(tokens[i + 3]), float(tokens[i + 4]))
            for t in (0.25, 0.5, 0.75, 1.0):
                x = (1 - t) ** 2 * cur[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * end[0]
                y = (1 - t) ** 2 * cur[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * end[1]
                points.append((x, y))
            cur = end
            i += 5
        elif cmd == "Z":
            i += 1
        else:
            i += 1  # skip anything unrecognized rather than fail the render
    return points


def _build_path(s: dict, index: int):
    points = _parse_path_points(s["d"])
    world_pts = [_to_world_xz(x, y) for x, y in points]
    depth_y = -s["depth"] * DEPTH_SCALE

    if s.get("stroke"):
        # A thin line (e.g. a stem) needs REAL tube geometry — Solidify
        # requires faces to extrude and does nothing useful on a bare edge
        # mesh. A poly curve with bevel_depth natively extrudes a round tube
        # along the line, which is both correct and simpler.
        curve = bpy.data.curves.new(f"shape{index}_path_curve", type="CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = max(0.005, s.get("stroke_width", 6) / SCALE / 2)
        curve.bevel_resolution = 4
        curve.fill_mode = "FULL"
        spline = curve.splines.new("POLY")
        spline.points.add(len(world_pts) - 1)
        for i, (x, z) in enumerate(world_pts):
            spline.points[i].co = (x, depth_y, z, 1.0)
        obj = bpy.data.objects.new(f"shape{index}_path", curve)
        bpy.context.scene.collection.objects.link(obj)
        color = s["stroke"]
    else:
        mesh = bpy.data.meshes.new(f"shape{index}_path_mesh")
        obj = bpy.data.objects.new(f"shape{index}_path", mesh)
        bpy.context.scene.collection.objects.link(obj)
        verts = [(x, depth_y, z) for x, z in world_pts]
        mesh.from_pydata(verts, [], [list(range(len(verts)))])
        mesh.update()
        span = max(
            max(x for x, _ in world_pts) - min(x for x, _ in world_pts),
            max(z for _, z in world_pts) - min(z for _, z in world_pts),
            0.05,
        )
        _add_bevel_solidify(obj, span * 0.3)
        color = s["color"]

    obj.data.materials.append(_make_material(f"mat{index}", color, s.get("gradient_to")))
    return obj


def build_scene(shapes: list):
    """Build every shape and group them under one root Empty. Shared by the
    still renderer (below) and animate_shapes_render.py (the Tier-B baked
    motion counterpart), so the two never diverge on how a shape-spec becomes
    3D geometry — only what happens to the resulting root afterward differs.
    Returns the root object."""
    shapes = ss.normalize(shapes)
    built = []
    for i, s in enumerate(shapes):
        if s["type"] == "ellipse":
            built.append(_build_ellipse(s, i))
        elif s["type"] == "circle":
            built.append(_build_circle(s, i))
        elif s["type"] == "path":
            built.append(_build_path(s, i))
        else:
            raise SystemExit(f"unknown shape type: {s['type']!r}")

    root = bpy.data.objects.new("ShapesRoot", None)
    bpy.context.scene.collection.objects.link(root)
    for obj in built:
        # Only re-parent objects that aren't already parented to a rotation
        # pivot — those stay under their pivot, and the pivot itself has no
        # parent, so gather root-level objects instead.
        if obj.parent is None:
            obj.parent = root
    for obj in bpy.context.scene.collection.objects:
        if obj.name.startswith("pivot") and obj.parent is None:
            obj.parent = root
    return root


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True)
    p.add_argument("--palette", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--params", default="{}")
    p.add_argument("--contact-shadow", action="store_true",
                   help="ground the subject on a soft shadow pool (studio.add_contact_shadow)")
    args = p.parse_args(argv)

    palette = json.loads(Path(args.palette).read_text())["colors"]
    params = json.loads(args.params)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    ctx = dc.build_ctx(palette, params, linear=False)

    ns = runpy.run_path(args.script)
    build = ns.get("build")
    if build is None:
        raise SystemExit(f"{args.script} must define build(ctx)")
    root = build_scene(build(ctx))

    studio.setup_studio(bpy, root, args.size, contact_shadow=args.contact_shadow)
    bpy.context.scene.render.filepath = args.out
    bpy.ops.render.render(write_still=True)
    print(f"[gen:shapes:skeuomorphic] wrote {args.out}")


if __name__ == "__main__":
    main()
