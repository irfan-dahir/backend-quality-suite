"""Headless Blender recolor + render. Runs INSIDE Blender, not plain python3.

Invoked by pipeline.py as:
  blender -b sources/<id>/<id>.blend -P scripts/recolor_render.py -- \
      --palette palette.json --out renders/<id>.png --size 1440 \
      [--map '{"MaterialName": "paletteKey", ...}'] \
      [--hexmap '{"MaterialName": "#hex", ...}'] \
      [--ramp '{"MaterialName": ["#hex1", "#hex2", ...], ...}']

Three independent recoloring paths — a material can use any combination:

1. **Flat Base Color, palette-driven** (`--map`, or the `theme_<key>` naming
   convention): any material named `theme_<key>`, or listed in --map, gets
   its Principled BSDF Base Color set to palette color <key> from
   palette.json. Use this for real, shipping assets — it stays correct
   automatically when AppTokens change.

2. **Flat Base Color, literal hex** (`--hexmap`): material name → literal hex
   string, set directly with no palette.json lookup. This is for one-off/
   synthetic test palettes only (e.g. trying out color schemes before a
   design-system mapping exists for this asset) — real shipping assets
   should use --map instead so they re-theme with the rest of the library.

3. **Color Ramp gradient** (`--ramp`): some assets drive Base Color through a
   Gradient Texture → Color Ramp chain rather than a flat value (common for
   iridescent/rainbow shaders) — overwriting the BSDF's Base Color directly
   does nothing there since it's not what's actually plugged in. --ramp takes
   a material name → list of hex colors (2+), rewrites the FIRST Color Ramp
   node found anywhere in that material's node tree to exactly those stops,
   evenly spaced across 0..1. Colors here are literal hex, not palette keys —
   this path is for one-off/test palettes; wire it through palette.json keys
   once a design-system mapping exists for this asset.

Hex colors are sRGB; Blender node sockets expect linear RGB, so we convert —
skipping this renders visibly washed-out colors.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy  # noqa: F401 — available inside Blender only

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import (  # noqa: E402
    apply_render_determinism,
    hex_to_linear_rgba,
    srgb_to_linear,
)

THEME_PREFIX = "theme_"


def palette_key_for(material_name: str, explicit_map: dict) -> str | None:
    if material_name in explicit_map:
        return explicit_map[material_name]
    if material_name.startswith(THEME_PREFIX):
        return material_name[len(THEME_PREFIX) :]
    return None


def recolor(palette: dict, explicit_map: dict) -> int:
    changed = 0
    for mat in bpy.data.materials:
        key = palette_key_for(mat.name, explicit_map)
        if key is None:
            continue
        entry = palette.get(key)
        if entry is None:
            print(f"[recolor] WARNING: material '{mat.name}' wants palette "
                  f"key '{key}' but it does not exist — skipped")
            continue
        rgba = hex_to_linear_rgba(entry["hex"], entry.get("alpha", 1.0))
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Base Color"].default_value = rgba
                    changed += 1
        else:
            mat.diffuse_color = rgba
            changed += 1
    print(f"[recolor] updated {changed} material(s)")
    return changed


def recolor_hexmap(hex_map: dict) -> int:
    changed = 0
    for mat_name, hex_color in hex_map.items():
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            print(f"[recolor] WARNING: material '{mat_name}' not found for "
                  f"--hexmap — skipped")
            continue
        rgba = hex_to_linear_rgba(hex_color, 1.0)
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Base Color"].default_value = rgba
                    changed += 1
        else:
            mat.diffuse_color = rgba
            changed += 1
    print(f"[recolor] hexmap updated {changed} material(s)")
    return changed


def recolor_ramps(ramp_map: dict) -> int:
    changed = 0
    for mat_name, hex_colors in ramp_map.items():
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            print(f"[recolor] WARNING: material '{mat_name}' not found for "
                  f"--ramp — skipped")
            continue
        ramp_node = next(
            (n for n in mat.node_tree.nodes if n.type == "VALTORGB"), None
        )
        if ramp_node is None:
            print(f"[recolor] WARNING: material '{mat_name}' has no Color "
                  f"Ramp node — skipped")
            continue
        elements = ramp_node.color_ramp.elements
        n = len(hex_colors)
        # Resize to exactly n stops: add first, then trim from the end (a
        # ColorRamp always keeps at least one element, so grow before shrink).
        while len(elements) < n:
            elements.new(1.0)
        while len(elements) > n:
            elements.remove(elements[-1])
        for i, hex_color in enumerate(hex_colors):
            pos = i / (n - 1) if n > 1 else 0.0
            elements[i].position = pos
            elements[i].color = hex_to_linear_rgba(hex_color, 1.0)
        changed += 1
        print(f"[recolor] '{mat_name}' Color Ramp -> {hex_colors}")
    return changed


def configure_render(out_path: str, long_edge_px: int) -> None:
    scene = bpy.context.scene
    render = scene.render
    # Preserve the scene's authored aspect ratio; scale the long edge.
    aspect = render.resolution_x / render.resolution_y
    if aspect >= 1:
        render.resolution_x = long_edge_px
        render.resolution_y = round(long_edge_px / aspect)
    else:
        render.resolution_y = long_edge_px
        render.resolution_x = round(long_edge_px * aspect)
    render.resolution_percentage = 100
    render.film_transparent = True
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGBA"
    render.filepath = out_path

    # Same colour and determinism pinning as studio.py — measurements are documented on
    # driver_common.apply_render_determinism.
    #
    # It matters MORE on this path than on the generated one, because this opens a
    # PURCHASED .blend rather than building a scene from scratch. An opened file carries
    # its own view transform and sampling seed, and Blender 5.0 added a per-file working
    # colour space — so a purchased asset can shift every colour silently. Setting these
    # after load is the only way to know what we actually rendered with.
    applied = apply_render_determinism(scene)
    print(f"[recolor] render pinned: {applied}")


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--palette", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--map", default="{}")
    parser.add_argument("--hexmap", default="{}")
    parser.add_argument("--ramp", default="{}")
    args = parser.parse_args(argv)

    with open(args.palette) as f:
        palette = json.load(f)["colors"]
    explicit_map = json.loads(args.map)
    hex_map = json.loads(args.hexmap)
    ramp_map = json.loads(args.ramp)

    recolor(palette, explicit_map)
    recolor_hexmap(hex_map)
    recolor_ramps(ramp_map)
    configure_render(args.out, args.size)
    bpy.ops.render.render(write_still=True)
    print(f"[render] wrote {args.out}")


if __name__ == "__main__":
    main()
