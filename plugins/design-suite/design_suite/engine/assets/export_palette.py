#!/usr/bin/env python3
"""Refresh the asset pipeline's palette.json from the design system's token graph.

## Why this is now a copy rather than a parse

It used to parse `lib/app/theme/app_theme.dart` for `AppTokens`. That file moved
to `package:ds_flutter`, so this script raised FileNotFoundError from the moment
the extraction landed — silently, because nothing runs it in CI. It was the
third script to break that way.

The design system now emits the palette itself, at
`dist/palette/<brand>.<mode>.json`, from the same token graph that produces the
Dart. Re-parsing generated Dart to recover values that already exist as data
would be strictly worse: it can drift, and it breaks again the next time the
theme is refactored.

So this resolves the package through the resolver the profile names — for Dart,
`.dart_tool/package_config.json`, the same mechanism Dart itself uses — and copies.
The output schema is unchanged, so `recolor_render.py`, `gen_render.py`,
`shapes_blender_render.py` and `manifest.json` are untouched.

## What moved to config when this became a plugin

The package name (`ds_flutter`), the resolver path, and the brand/mode the assets
are baked for were all module constants. They are now read from
`.design-suite/profile.json`:

    tokens.source.package      which package ships the palette
    tokens.source.resolveVia   how to find it
    assets.palette.brand/mode  which palette variant these assets are rendered for

Brand and mode belong in config rather than here because assets are baked per
brand: a second client renders its own set rather than recolouring someone else's.

A missing key is a hard error naming the key, not a default. Defaulting the brand
would silently produce a palette from the wrong design system,
and every asset rendered from it would be wrong in a way nobody would notice until
someone looked at the screen.

    python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/export_palette.py"            # refresh in place
    python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/export_palette.py" --check    # compare only
    python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/export_palette.py" --out F    # write to F

## Read-only modes

This script used to read no arguments at all, so `--help` was silently ignored
and the default refresh ran — overwriting `<pipelines.assets>/palette.json`.
`/audit-assets` called it that way as a "probe" (the read-only audit wrote to the
consumer's tree on its first step). So:

  --check   regenerate in memory and compare against the committed palette.json;
            writes nothing. Exit 0 current, 1 stale (or missing), 2 refused —
            the comparison could not be made (no profile, no package, no source
            palette). A 2 is never a pass and never "stale".
  --out F   write the fresh palette to F instead of the default target (the
            "regenerate to a temp file and diff" path). Refusals exit 2.

With neither flag, behaviour is unchanged: refresh in place, exit 1 on refusal.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from design_suite.project import project_root  # noqa: E402

REPO = project_root()
PROFILE = REPO / ".design-suite" / "profile.json"


def _profile() -> dict:
    if not PROFILE.is_file():
        raise SystemExit(f"no profile at {PROFILE.relative_to(REPO)}")
    return json.loads(PROFILE.read_text())


def _need(node: dict, dotted: str) -> str:
    """A profile value, or a hard error naming what is missing."""
    cur = node
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise SystemExit(
                f".design-suite/profile.json is missing {dotted!r}, which "
                f"export_palette.py needs.\nAdd it — this script will not guess, "
                f"because a wrong palette produces assets that are wrong on screen "
                f"without anything reporting it.")
        cur = cur[part]
    return cur


def _out_path(profile: dict) -> Path:
    pipelines = profile.get("pipelines", {}) or {}
    return REPO / pipelines.get("assets", "asset_pipeline") / "palette.json"


def _design_system_root(profile: dict) -> Path:
    source = profile.get("tokens", {}).get("source", {}) or {}
    if source.get("kind") != "package":
        raise SystemExit(
            f"tokens.source.kind is {source.get('kind')!r}; export_palette.py needs "
            "a package-resolved token source to find the generated palette.")

    want = _need(profile, "tokens.source.package")
    resolver = REPO / _need(profile, "tokens.source.resolveVia")
    if not resolver.is_file():
        raise SystemExit(
            f"{resolver.relative_to(REPO)} is missing — resolve dependencies first "
            f"(for Flutter, `flutter pub get`).")

    config = json.loads(resolver.read_text())
    for package in config.get("packages", []):
        if package.get("name") != want:
            continue
        root = package["rootUri"]
        root = root[len("file://"):] if root.startswith("file://") else root
        # <checkout>/packages/<name> -> <checkout>
        return (resolver.parent / root).resolve().parents[1]
    raise SystemExit(f"{want} is not in {resolver.relative_to(REPO)} — resolve "
                     f"dependencies first.")


def _source(profile: dict) -> Path:
    brand = _need(profile, "assets.palette.brand")
    mode = _need(profile, "assets.palette.mode")
    source = _design_system_root(profile) / "dist" / "palette" / f"{brand}.{mode}.json"
    if not source.is_file():
        raise SystemExit(
            f"the design system has no palette at {source}.\n"
            "It is generated: run `python3 tooling/generate.py` in that repo, or "
            "bump to a version that ships dist/palette/ (>= v0.3.0)."
        )
    return source


def _refresh(profile: dict) -> int:
    OUT = _out_path(profile)
    BRAND = _need(profile, "assets.palette.brand")
    MODE = _need(profile, "assets.palette.mode")
    source = _source(profile)
    before = OUT.read_text() if OUT.is_file() else None
    shutil.copyfile(source, OUT)

    if before == OUT.read_text():
        print(f"palette.json already current ({BRAND}.{MODE})")
    else:
        print(f"palette.json refreshed from the design system ({BRAND}.{MODE}).\n"
              "Re-render any affected assets — see the project's assets document "
              "({{doc:assets}}).")
    return 0


def _check(profile: dict) -> int:
    current = _out_path(profile)
    fresh = _source(profile).read_bytes()
    rel = current.relative_to(REPO) if current.is_relative_to(REPO) else current
    if not current.is_file():
        print(f"STALE: {rel} does not exist; a fresh export would create it.")
        return 1
    if current.read_bytes() != fresh:
        print(f"STALE: {rel} differs from a fresh export of the design system's palette.")
        return 1
    print(f"CURRENT: {rel} matches a fresh export.")
    return 0


def _write_to(profile: dict, dest: str) -> int:
    out = Path(dest)
    out.write_bytes(_source(profile).read_bytes())
    print(f"fresh palette written to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Refresh palette.json from the design system's token graph.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="compare only; write nothing (exit 0 current, 1 stale, 2 refused)")
    mode.add_argument("--out", metavar="PATH",
                      help="write the fresh palette to PATH, not the default target")
    args = ap.parse_args(argv)

    if not (args.check or args.out):
        return _refresh(_profile())
    try:
        profile = _profile()
        return _check(profile) if args.check else _write_to(profile, args.out)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        print(f"REFUSING: {exc.code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
