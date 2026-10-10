"""Flat 2D renderer for the "shapes" generator kind. Plain python3 — no bpy,
no Blender. Builds an SVG string from a shapes.py shape-spec (see
shape_spec.py) using the same gradient + soft-drop-shadow recipe as
hand-authored icon SVGs, writes it to a temp file, and rasterizes via
rsvg-convert (same tool the "svg" generator kind already uses).

Invoked by pipeline.py as:
  python3 shapes_svg_render.py --script generated/<id>/shapes.py \
      --palette palette.json --out renders/<id>.png --size 512 \
      --params '{...}'
"""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shape_spec as ss  # noqa: E402
import driver_common as dc  # noqa: E402


def _path_shape_svg(s: dict, grad_id: str | None) -> str:
    fill = f"url(#{grad_id})" if grad_id else (s.get("color") or "none")
    stroke_attr = (
        f'stroke="{s["stroke"]}" stroke-width="{s["stroke_width"]}" '
        f'stroke-linecap="round"' if s.get("stroke") else ""
    )
    return f'<path d="{s["d"]}" fill="{fill}" {stroke_attr} />'


def build_svg(shapes: list, size: int = 512) -> str:
    shapes = ss.normalize(shapes)
    defs = []
    body = []

    for i, s in enumerate(shapes):
        grad_id = None
        if s.get("color") and s.get("gradient_to"):
            grad_id = f"grad{i}"
            kind = "radialGradient" if s["type"] == "circle" else "linearGradient"
            attrs = 'cx="35%" cy="35%" r="70%"' if kind == "radialGradient" \
                else 'x1="0%" y1="0%" x2="100%" y2="100%"'
            defs.append(
                f'<{kind} id="{grad_id}" {attrs}>'
                f'<stop offset="0%" stop-color="{s["gradient_to"]}" />'
                f'<stop offset="100%" stop-color="{s["color"]}" />'
                f'</{kind}>'
            )

        fill = f"url(#{grad_id})" if grad_id else (s.get("color") or "none")

        if s["type"] == "ellipse":
            # SVG's own rotate(angle, px, py) transform handles pivot
            # rotation of both position and orientation natively — no need
            # to pre-compute a rotated centre ourselves for the flat path.
            pivot = ss.effective_pivot(s)
            transform = (
                f'transform="rotate({s["rotation"]} {pivot[0]} {pivot[1]})"'
                if s["rotation"] else ""
            )
            body.append(
                f'<ellipse cx="{s["cx"]}" cy="{s["cy"]}" rx="{s["rx"]}" '
                f'ry="{s["ry"]}" fill="{fill}" {transform} />'
            )
        elif s["type"] == "circle":
            body.append(
                f'<circle cx="{s["cx"]}" cy="{s["cy"]}" r="{s["r"]}" '
                f'fill="{fill}" />'
            )
        elif s["type"] == "path":
            body.append(_path_shape_svg(s, grad_id))
        else:
            raise ValueError(f"unknown shape type: {s['type']!r}")

    defs_str = "\n    ".join(defs)
    body_str = "\n    ".join(body)
    return f'''<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    {defs_str}
    <filter id="softShadow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="10" result="blur" />
      <feOffset in="blur" dx="0" dy="10" result="offsetBlur" />
      <feComponentTransfer in="offsetBlur" result="shadow">
        <feFuncA type="linear" slope="0.28" />
      </feComponentTransfer>
      <feMerge>
        <feMergeNode in="shadow" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>
  <g filter="url(#softShadow)">
    {body_str}
  </g>
</svg>
'''


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True)
    p.add_argument("--palette", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--params", default="{}")
    args = p.parse_args()

    palette = json.loads(Path(args.palette).read_text())["colors"]
    params = json.loads(args.params)

    ctx = dc.build_ctx(palette, params, linear=False)

    ns = runpy.run_path(args.script)
    build = ns.get("build")
    if build is None:
        raise SystemExit(f"{args.script} must define build(ctx)")
    shapes = build(ctx)

    svg_text = build_svg(shapes, args.size)
    tmp_svg = Path(args.out).with_suffix(".tmp.svg")
    tmp_svg.write_text(svg_text)

    subprocess.run(
        ["rsvg-convert", "-w", str(args.size), "-h", str(args.size),
         "-a", str(tmp_svg), "-o", args.out],
        check=True,
    )
    tmp_svg.unlink()
    print(f"[gen:shapes:flat] wrote {args.out}")


if __name__ == "__main__":
    main()
