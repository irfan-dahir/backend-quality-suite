"""Tile a rendered frame sequence into ONE contact-sheet PNG for review.
Runs INSIDE Blender (uses its bundled numpy) — so it needs no extra tooling
(ImageMagick/PIL/ffmpeg), keeping the pipeline portable.

  blender -b -P scripts/contact_sheet.py -- \
      --frames-dir renders/<id>_frames --out renders/<id>_contact.png \
      [--cols 4] [--max 16] [--thumb 240]

Why: you can't judge motion from a single frame, and reading N frames one by
one is expensive. A grid of sampled frames lets the whole motion be reviewed in
a single image (one look), which is the token-cheap way to iterate on motion.
Frames are sampled evenly up to --max, so a 60-frame turntable still reviews as
a compact grid.

`build_contact_sheet()` is also called DIRECTLY by the animate drivers
(animate_render.py / animate_recolor_render.py / animate_shapes_render.py)
in the same Blender process right after rendering frames — avoiding a second
`blender -b ...` spawn (~1-2s startup) per `animate` call just for this. This
file remains runnable standalone (e.g. to regenerate a contact sheet from
already-rendered frames without a full re-render).
"""

import argparse
import glob
import math
import os
import sys

import bpy
import numpy as np


def build_contact_sheet(frames_dir: str, out: str, cols: int = 4,
                         max_frames: int = 16, thumb: int = 240) -> None:
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frames:
        sys.exit(f"[contact] no PNG frames in {frames_dir}")

    # Sample evenly up to max_frames so long sequences stay a compact grid.
    if len(frames) > max_frames:
        idxs = sorted({round(i * (len(frames) - 1) / (max_frames - 1))
                       for i in range(max_frames)})
        frames = [frames[i] for i in idxs]

    n = len(frames)
    cols = min(cols, n)
    rows = math.ceil(n / cols)
    t = thumb
    width, height = cols * t, rows * t

    # Blender image pixel buffers are RGBA float, row-major BOTTOM-to-top
    # (origin bottom-left). Build the sheet in that same space, composited
    # over an OPAQUE WHITE background rather than left transparent — a
    # contact sheet is for human review, and relying on a viewer to composite
    # alpha consistently is fragile (confirmed: some viewers render
    # transparent regions black instead of white, even though the underlying
    # render alpha is correct). Baking in a white background makes the
    # review image reliable regardless of viewer.
    sheet = np.ones((height, width, 4), dtype=np.float32)  # opaque white
    for i, f in enumerate(frames):
        img = bpy.data.images.load(f)
        img.scale(t, t)
        buf = np.empty(t * t * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        tile = buf.reshape(t, t, 4)
        r, c = divmod(i, cols)
        # visual row r (0 = top) → its band sits high in bottom-left coords
        y0 = height - (r + 1) * t
        x0 = c * t
        tile_rgb, tile_a = tile[..., :3], tile[..., 3:4]
        white = np.ones_like(tile_rgb)
        composited = tile_rgb * tile_a + white * (1.0 - tile_a)
        sheet[y0:y0 + t, x0:x0 + t, :3] = composited
        # alpha stays 1.0 (opaque) — already initialised that way above
        bpy.data.images.remove(img)

    out_img = bpy.data.images.new("contact", width, height, alpha=True)
    out_img.pixels.foreach_set(sheet.ravel())
    out_img.filepath_raw = out
    out_img.file_format = "PNG"
    out_img.save()
    # Blender keeps this image datablock around even after saving; clean it
    # up so repeated in-process calls (from an animate driver) don't leak.
    bpy.data.images.remove(out_img)
    print(f"[contact] wrote {out}  ({n} frames, {cols}x{rows} grid)")


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--frames-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--max", type=int, default=16)
    p.add_argument("--thumb", type=int, default=240)
    a = p.parse_args(argv)
    build_contact_sheet(a.frames_dir, a.out, a.cols, a.max, a.thumb)


if __name__ == "__main__":
    main()
