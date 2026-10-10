"""Headless Blender driver for GENERATED 3D assets. Runs INSIDE Blender.

Invoked by pipeline.py `gen` as:
  blender -b -P scripts/gen_render.py -- \
      --script generated/<id>/gen.py --palette palette.json \
      --out renders/<id>.png --size 1024 --params '{...}'

Contract for a generated asset's gen.py: it must define

    def build(ctx):
        # build geometry + materials using ctx.bpy
        return subject_object   # the object to frame/light (or None)

`ctx` gives the script everything it needs without importing bpy paths itself:
  ctx.bpy              the bpy module
  ctx.params           dict from the manifest generator.params (+ 'seed')
  ctx.seed             int (params['seed'] or 0) — for deterministic jitter
  ctx.rng              random.Random(seed) — seeded RNG for variants
  ctx.palette          {key: {"hex","alpha"}} from palette.json (AppTokens)
  ctx.color(key)       -> linear RGBA tuple for a palette key
  ctx.hex(hexstr)      -> linear RGBA tuple for a literal hex

gen_render starts from a factory-empty scene, execs the gen.py to get build(),
calls it, then applies the shared studio rig (studio.py) and renders. The
subject object build() returns becomes the camera/light track target.
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

import bpy  # noqa: F401 — Blender only

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio  # noqa: E402
import driver_common as dc  # noqa: E402


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

    # Factory-empty scene: no default cube, no inherited render settings.
    bpy.ops.wm.read_factory_settings(use_empty=True)

    ctx = dc.build_ctx(palette, params, bpy=bpy, linear=True)

    # Exec the asset's gen.py and pull out build().
    ns = runpy.run_path(args.script)
    build = ns.get("build")
    if build is None:
        raise SystemExit(f"{args.script} must define build(ctx)")
    subject = build(ctx)

    studio.setup_studio(bpy, subject, args.size, contact_shadow=args.contact_shadow)
    bpy.context.scene.render.filepath = args.out
    bpy.ops.render.render(write_still=True)
    print(f"[gen:blender] wrote {args.out}")


if __name__ == "__main__":
    main()
