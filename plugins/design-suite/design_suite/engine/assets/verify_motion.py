"""Quantitatively verify a rendered baked-motion frame sequence. Runs INSIDE
Blender (uses its bundled numpy, same as contact_sheet.py — no extra tooling).

  blender -b -P scripts/verify_motion.py -- \
      --frames-dir renders/<id>_frames \
      [--static-region "0,0,0.5,1"]

Replaces the ad-hoc one-off verification scripts written by hand for each
motion review this session (alpha-weighted centroid across frames, bbox
width/height, a static-region pixel diff for `motion.objects` targeting) —
the same handful of numpy lines were being rewritten from scratch each time.

Reports, for the full frame sequence:
  - alpha-weighted centroid (x, y) range across all frames — how far the
    subject actually moves in pixel space (turntable/idle_float/pulse should
    show real movement; a bug that silently no-ops would show ~0 range)
  - bounding-box width/height range — catches scale motion (pulse) or a
    subject rotating out of a thin axis (the "petals vanish" class of bug)
  - loop-seam delta — MEAN abs pixel diff between the FIRST and LAST rendered
    frame (the verdict signal), with max also reported for context. Presets
    keyframe across [start, end+1] and render [start, end], so a good loop's
    last frame should already be very close to the first. Mean, not max, is
    the verdict: max is dominated by a handful of edge/antialiasing pixels
    wherever the silhouette shifts by even a sub-pixel amount — confirmed on
    a genuinely seamless pulse loop, where max diff was ~0.98 (looks like a
    total blowout) from just 0.07% of pixels, while mean diff was ~0.0007.
    Judging by max alone would have wrongly flagged a fine loop as broken.

`--static-region "x0,y0,x1,y1"` (fractions of frame width/height, e.g. the
left half is "0,0,0.5,1") additionally reports the mean (verdict) and max
(context) pixel diff within that crop across the SAME two frames — for
confirming a `motion.objects`-targeted subset really left the rest of the
composition untouched. Optional; omit it for a plain motion-range report.

Gotcha found while validating this tool: draw the region with a SAFETY
MARGIN away from the moving/static boundary, not flush against it. Framing
(studio.frame_objects_over_range) re-fits the camera to the actual rendered
frame count/resolution, so the composition can land a few pixels differently
between a `--quick` run and the final promote render — a crop drawn exactly
at the boundary can then clip a few edge pixels of the MOVING part, giving a
false "MOVED" verdict for a region that's conceptually static. Confirmed on
the real prescription bottle asset: "0,0,0.5,1" (flush against the bottle's
edge) reported moved (mean diff 0.00104, ~60 stray edge pixels); pulling it
in to "0,0,0.4,1" reported confirmed static (mean diff 0.00045).
"""

import argparse
import glob
import os
import sys

import bpy
import numpy as np


def _load_rgba(path: str) -> np.ndarray:
    img = bpy.data.images.load(path)
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    arr = buf.reshape(h, w, 4)
    bpy.data.images.remove(img)
    return arr


def _centroid_and_bbox(arr: np.ndarray):
    alpha = arr[:, :, 3]
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) == 0:
        return None, None
    cx = float((xs * alpha[ys, xs]).sum() / alpha[ys, xs].sum())
    cy = float((ys * alpha[ys, xs]).sum() / alpha[ys, xs].sum())
    bbox_w = float(xs.max() - xs.min())
    bbox_h = float(ys.max() - ys.min())
    return (cx, cy), (bbox_w, bbox_h)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--frames-dir", required=True)
    p.add_argument("--static-region", default=None,
                   help="x0,y0,x1,y1 as fractions of frame size, e.g. 0,0,0.5,1")
    args = p.parse_args(argv)

    frames = sorted(glob.glob(os.path.join(args.frames_dir, "*.png")))
    if not frames:
        sys.exit(f"[verify-motion] no PNG frames in {args.frames_dir}")

    centroids, bboxes = [], []
    first_arr, last_arr = None, None
    for i, f in enumerate(frames):
        arr = _load_rgba(f)
        if i == 0:
            first_arr = arr
        if i == len(frames) - 1:
            last_arr = arr
        c, b = _centroid_and_bbox(arr)
        if c is not None:
            centroids.append(c)
            bboxes.append(b)

    if not centroids:
        sys.exit("[verify-motion] every frame is fully transparent — "
                 "nothing rendered (check clip_end / framing)")

    cxs, cys = zip(*centroids)
    bws, bhs = zip(*bboxes)
    print(f"[verify-motion] {len(frames)} frames")
    print(f"  centroid x: {min(cxs):.1f} .. {max(cxs):.1f}  "
          f"(range {max(cxs) - min(cxs):.1f}px)")
    print(f"  centroid y: {min(cys):.1f} .. {max(cys):.1f}  "
          f"(range {max(cys) - min(cys):.1f}px)")
    print(f"  bbox width:  {min(bws):.1f} .. {max(bws):.1f}  "
          f"(range {max(bws) - min(bws):.1f}px)")
    print(f"  bbox height: {min(bhs):.1f} .. {max(bhs):.1f}  "
          f"(range {max(bhs) - min(bhs):.1f}px)")

    # Verdict is based on MEAN diff, not max — max is dominated by a handful
    # of edge/antialiasing pixels wherever the subject's silhouette shifts by
    # even a sub-pixel amount between two frames (confirmed: a real seamless
    # pulse loop showed max diff ~0.98 from ~0.07% of pixels, while mean diff
    # was ~0.0007 — max alone would have wrongly flagged a fine loop as
    # broken). Max is still reported for context, not as the verdict signal.
    seam_diff = np.abs(first_arr - last_arr)
    seam_mean, seam_max = float(seam_diff.mean()), float(seam_diff.max())
    verdict = "seamless" if seam_mean < 0.01 else "VISIBLE JUMP"
    print(f"  loop seam (first vs last frame): mean diff {seam_mean:.5f}, "
          f"max {seam_max:.4f} — {verdict}")

    if args.static_region:
        x0f, y0f, x1f, y1f = (float(v) for v in args.static_region.split(","))
        h, w = first_arr.shape[:2]
        x0, x1 = int(x0f * w), int(x1f * w)
        y0, y1 = int(y0f * h), int(y1f * h)
        region_diff = np.abs(first_arr[y0:y1, x0:x1] - last_arr[y0:y1, x0:x1])
        region_mean, region_max = float(region_diff.mean()), float(region_diff.max())
        verdict = "confirmed static" if region_mean < 0.0005 else "MOVED — not static"
        print(f"  static region {args.static_region} (first vs last frame): "
              f"mean diff {region_mean:.5f}, max {region_max:.4f} — {verdict}")


if __name__ == "__main__":
    main()
