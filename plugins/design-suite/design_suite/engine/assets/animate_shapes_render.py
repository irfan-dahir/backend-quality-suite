"""Headless Blender driver for BAKED (Tier-B) motion on "shapes"-kind
generated assets (see {{doc:assets}} §10). Runs INSIDE Blender. The
shapes-kind counterpart of animate_render.py (which covers plain gen.py
build(ctx) subjects) — reuses shapes_blender_render.build_scene() so the
still and animated renderers can never diverge on how a shape-spec becomes
3D geometry.

Invoked by pipeline.py `animate` as:
  blender -b -P animate_shapes_render.py -- \
      --script generated/<id>/shapes.py --palette palette.json \
      --out renders/<id>_frames/f_ --size 480 --params '{...}' \
      --preset pulse --motion-params '{...}' --frames 48 --fps 24

The whole shape-spec scene (the ShapesRoot empty every shape is grouped
under) IS the motion pivot here — unlike animate_render.py, no separate
pivot needs to be created, since build_scene() already produces one root
covering the entire composition.
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

import bpy  # noqa: F401 — Blender only

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shapes_blender_render as sbr  # noqa: E402 — build_scene()
import studio  # noqa: E402
import presets  # noqa: E402
import driver_common as dc  # noqa: E402
import contact_sheet  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True)
    p.add_argument("--palette", required=True)
    p.add_argument("--out", required=True)
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

    bpy.ops.wm.read_factory_settings(use_empty=True)

    ctx = dc.build_ctx(palette, params, linear=False)

    ns = runpy.run_path(args.script)
    build = ns.get("build")
    if build is None:
        raise SystemExit(f"{args.script} must define build(ctx)")
    root = sbr.build_scene(build(ctx))

    preset = presets.get(args.preset)
    frame_start, frame_end = 1, args.frames
    preset(bpy, root, frame_start, frame_end, json.loads(args.motion_params))

    scene = bpy.context.scene
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.render.fps = args.fps

    studio.setup_studio(bpy, root, args.size, auto_frame=False)
    studio.frame_object_over_range(bpy, scene.camera, root, frame_start, frame_end)

    scene.render.filepath = args.out
    bpy.ops.render.render(animation=True)
    print(f"[animate:shapes] wrote frames {args.out}NNNN.png "
          f"[{frame_start}..{frame_end}] @ {args.fps}fps (preset={args.preset})")

    if args.contact_out:
        frames_dir = str(Path(args.out).parent)
        contact_sheet.build_contact_sheet(frames_dir, args.contact_out)


if __name__ == "__main__":
    main()
