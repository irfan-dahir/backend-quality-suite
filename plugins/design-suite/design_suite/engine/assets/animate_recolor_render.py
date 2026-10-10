"""Headless Blender driver for BAKED (Tier-B) motion on PURCHASED (envato)
.blend assets. Runs INSIDE Blender. The purchased-asset counterpart of
animate_render.py (which covers generated assets).

Invoked by pipeline.py `animate` as:
  blender -b sources/<id>/<id>.blend -P scripts/animate_recolor_render.py -- \
      --palette palette.json --out renders/<id>_frames/f_ --size 480 \
      [--map '{...}'] [--hexmap '{...}'] [--ramp '{...}'] \
      --preset turntable --motion-params '{...}' --frames 48 --fps 24 \
      [--target-objects '["Cylinder", "Cylinder.001"]']

Recoloring is IDENTICAL to recolor_render.py (imported from it directly, not
duplicated) — same --map/--hexmap/--ramp semantics.

The key difference from the generated-asset path: a purchased .blend has no
build(ctx) subject — it's an existing scene the artist authored, usually with
several top-level mesh objects that together form the visible result (see
{{doc:assets}} §8 "isolating which mesh object is actually visible" — some
objects are only ever seen through another's translucent shell).

By default (no --target-objects) every top-level MESH object (parent is None)
is parented to a motion pivot at their combined bounding-box centre — the
whole composition moves together as one rigid body, keeping the authored
relative arrangement intact.

--target-objects narrows this to a NAMED SUBSET (e.g. only the objects making
up one element of a multi-element composition, like a bottle within a
paper+bottle icon) — only those are parented to the pivot; everything else
stays exactly where the artist put it. This is the mechanism for "only part
of the composition moves" without writing a new preset — any existing preset
(idle_float, pulse, turntable) works unchanged on the narrowed subset.

Framing always covers the FULL composition (every top-level object, moving or
not) sampled across the whole motion — not just the moving subset — otherwise
the camera would crop/recentre onto only the part that moves and cut the
static part out of frame. See studio.frame_objects_over_range.

The scene's OWN authored camera and lights are used as-is (never replaced) —
only re-aimed/re-distanced so the existing look is preserved.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy  # noqa: F401 — Blender only

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recolor_render as rr  # noqa: E402 — recolor()/recolor_hexmap()/recolor_ramps()/configure_render()
import studio  # noqa: E402
import presets  # noqa: E402
import contact_sheet  # noqa: E402


def _top_level_mesh_objects() -> list:
    objs = [o for o in bpy.data.objects if o.parent is None and o.type == "MESH"]
    if not objs:
        sys.exit("[animate] no top-level MESH objects found to animate — "
                 "is this the right .blend?")
    return objs


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--palette", required=True)
    p.add_argument("--out", required=True)  # frame prefix, e.g. .../f_
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--map", default="{}")
    p.add_argument("--hexmap", default="{}")
    p.add_argument("--ramp", default="{}")
    p.add_argument("--preset", required=True)
    p.add_argument("--motion-params", default="{}")
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--target-objects", default="[]")
    p.add_argument("--contact-out", default=None)
    args = p.parse_args(argv)

    with open(args.palette) as f:
        palette = json.load(f)["colors"]
    rr.recolor(palette, json.loads(args.map))
    rr.recolor_hexmap(json.loads(args.hexmap))
    rr.recolor_ramps(json.loads(args.ramp))

    cam = bpy.context.scene.camera
    if cam is None:
        sys.exit("[animate] scene has no camera — this .blend needs one authored")

    all_targets = _top_level_mesh_objects()

    wanted_names = json.loads(args.target_objects)
    if wanted_names:
        by_name = {o.name: o for o in all_targets}
        missing = [n for n in wanted_names if n not in by_name]
        if missing:
            sys.exit(
                f"[animate] --target-objects names not found: {missing} — "
                f"available top-level mesh objects: {sorted(by_name)}"
            )
        moving = [by_name[n] for n in wanted_names]
    else:
        moving = all_targets  # default: whole composition moves together

    # Motion pivot at the combined bounding-box centre of the MOVING subset
    # only (not the whole composition) — so e.g. a bottle bobs about its own
    # centre, not the paper+bottle composition's centre.
    bpy.context.view_layer.update()
    corners = [c for obj in moving for c in studio._world_corners(obj)]
    xs, ys, zs = zip(*corners)
    from mathutils import Vector
    center = Vector(
        ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    )
    pivot = bpy.data.objects.new("MotionPivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = center
    bpy.context.view_layer.update()
    for obj in moving:
        obj.parent = pivot
        obj.matrix_parent_inverse = pivot.matrix_world.inverted()

    preset = presets.get(args.preset)
    frame_start, frame_end = 1, args.frames
    preset(bpy, pivot, frame_start, frame_end, json.loads(args.motion_params))

    scene = bpy.context.scene
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.render.fps = args.fps

    # Re-frame the scene's OWN camera over the whole motion — never replaced,
    # only re-distanced/re-aimed. Framed on ALL top-level objects (moving +
    # static), not just the moving subset, so a static part of the
    # composition never gets cropped out by a camera centred on the mover.
    studio.frame_objects_over_range(bpy, cam, all_targets, frame_start, frame_end)

    rr.configure_render(args.out, args.size)
    bpy.ops.render.render(animation=True)
    print(f"[animate] wrote frames {args.out}NNNN.png "
          f"[{frame_start}..{frame_end}] @ {args.fps}fps (preset={args.preset})")

    if args.contact_out:
        frames_dir = str(Path(args.out).parent)
        contact_sheet.build_contact_sheet(frames_dir, args.contact_out)


if __name__ == "__main__":
    main()
