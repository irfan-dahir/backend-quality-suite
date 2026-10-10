"""Headless Blender driver for BAKED (Tier-B) motion on GENERATED 3D assets.
Runs INSIDE Blender. The animation counterpart of gen_render.py.

Invoked by pipeline.py `animate` as:
  blender -b -P scripts/animate_render.py -- \
      --script generated/<id>/gen.py --palette palette.json \
      --out renders/<id>_frames/f_ --size 512 --params '{...}' \
      --preset turntable --motion-params '{...}' --frames 60 --fps 30

Same build(ctx) contract as gen_render.py (see that file). The extra motion
step: the subject build() returns is parented to a MOTION PIVOT empty at its
bounding-box centre, a preset (presets.py) keyframes the pivot over the frame
range, the camera is framed over the WHOLE motion (studio.frame_object_over_range
— so a growing/drifting subject never clips or blanks), and the scene renders
as a PNG frame sequence (animation=True) which encode.py then turns into an
animated file.

This path covers GENERATED assets. Baked motion for purchased .blend assets
(recolor_render.py's sibling) is a later addition — the preset/framing/encode
machinery here is written to be reused by it.
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

import bpy  # noqa: F401 — Blender only
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio  # noqa: E402
import presets  # noqa: E402
import driver_common as dc  # noqa: E402
import contact_sheet  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True)
    p.add_argument("--palette", required=True)
    p.add_argument("--out", required=True)  # frame prefix, e.g. .../f_
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--params", default="{}")
    p.add_argument("--preset", required=True)
    p.add_argument("--motion-params", default="{}")
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--contact-out", default=None)
    args = p.parse_args(argv)

    palette = json.loads(Path(args.palette).read_text())["colors"]
    params = json.loads(args.params)
    motion_params = json.loads(args.motion_params)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    ctx = dc.build_ctx(palette, params, bpy=bpy, linear=True)

    ns = runpy.run_path(args.script)
    build = ns.get("build")
    if build is None:
        raise SystemExit(f"{args.script} must define build(ctx)")
    subject = build(ctx)
    if subject is None:
        raise SystemExit(f"{args.script} build(ctx) returned None — need a subject")

    # Parent the subject to a motion pivot at its bounding-box centre, so
    # presets can spin/scale/bob about the visual centre while the subject
    # keeps its own build-time transform.
    bpy.context.view_layer.update()
    corners = studio._world_corners(subject)
    xs, ys, zs = zip(*corners)
    center = Vector(
        ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    )
    pivot = bpy.data.objects.new("MotionPivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = center
    bpy.context.view_layer.update()
    subject.parent = pivot
    subject.matrix_parent_inverse = pivot.matrix_world.inverted()

    # Studio rig aimed at the pivot (stable centre — the camera won't chase a
    # bobbing subject). Skip the static frame; we frame over the range below.
    studio.setup_studio(bpy, pivot, args.size, auto_frame=False)

    frame_start = 1
    frame_end = args.frames

    preset = presets.get(args.preset)
    preset(bpy, pivot, frame_start, frame_end, motion_params)

    scene = bpy.context.scene
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.render.fps = args.fps

    studio.frame_object_over_range(bpy, scene.camera, pivot, frame_start, frame_end)

    scene.render.filepath = args.out
    bpy.ops.render.render(animation=True)
    print(f"[animate] wrote frames {args.out}NNNN.png "
          f"[{frame_start}..{frame_end}] @ {args.fps}fps (preset={args.preset})")

    if args.contact_out:
        # Same Blender process, no second `blender -b ...` spawn (~1-2s
        # startup) just for the review sheet.
        frames_dir = str(Path(args.out).parent)
        contact_sheet.build_contact_sheet(frames_dir, args.contact_out)


if __name__ == "__main__":
    main()
