#!/usr/bin/env python3
"""Asset pipeline driver. Full workflow docs: the project's assets document
({{doc:assets}}).

Pipeline DATA (manifest, palette, sources, renders) lives in the project under
`pipelines.assets`; this code lives in the plugin. `P` below is
`"${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py"`.

    python3 "$P" setup       # install all tooling
    python3 "$P" check       # report tooling state
    python3 "$P" gen      [id | --all]   # generated assets → master
    python3 "$P" render   [id | --all]   # purchased .blend → master
    python3 "$P" optimize [id | --all]
    python3 "$P" sync
    python3 "$P" all      [id | --all]   # produce → optimize → sync
    python3 "$P" animate  [id | --all] [--quick]  # baked (Tier-B) motion → animated file + contact sheet
    python3 "$P" verify-motion <id>  # quantify an already-rendered motion (run animate first)

Baked motion (Tier B): an asset with a `motion` field of tier "baked" renders a
PNG frame sequence (a preset from presets.py keyframes a pivot; the camera is
framed over the whole motion), which encode.py turns into an animated file
(animated WebP by default; png_seq/apng/gif/mp4/webm also available) plus a
static POSTER frame for the reduce-motion fallback. Outputs are named per
`slots[]` (then `sync` bundles them into the project's asset root), or
id-named as a preview when there are no slots. `animate` also writes a contact
sheet to renders/ for review. Baked motion is single-resolution (no 1x/2x/3x
fan-out — bundle budget). Works for BOTH origins: "generated" assets render via
animate_render.py (build(ctx)'s subject is the pivot target); "envato"
(purchased .blend) assets render via animate_recolor_render.py (by default
every top-level MESH object is parented to the pivot together; an optional
manifest `motion.objects` list narrows this to a NAMED SUBSET so only part of
a multi-element composition moves — e.g. a bottle within a paper+bottle icon —
while framing still covers the whole composition. The scene's own authored
camera/lights are reused — only re-framed, never replaced).

`--quick` caps frames/resolution and skips extra encode targets for fast,
cheap iteration while a preset is being tuned — re-run without it for the
final promote render. Tier-A
("flutter") motion is played in the client from the static still and is not
rendered here.

`verify-motion` quantifies an already-rendered motion (centroid/bbox range
across frames, a loop-seam delta, and an optional static-region diff if the
asset's `motion.verifyStaticRegion` is set — e.g. "0,0,0.5,1" for the left
half) instead of hand-writing a one-off numpy script per review, which is
what every motion review did before this existed.

An asset is one of two ORIGINS (manifest `origin` field):
  • "envato" (default) — a purchased .blend in sources/, recolored + rendered
    by `render` (see recolor_render.py).
  • "generated" — built from a script we author, produced by `gen`:
      kind "svg"     — source generated/<id>/<id>.svg, rasterized (rsvg-convert)
      kind "blender" — source generated/<id>/gen.py (build(ctx) contract),
                       lit by the shared studio rig (studio.py) and rendered
Both origins land a master PNG in renders/<id>.png, so optimize/sync/all are
origin-agnostic. `all` auto-routes each asset to gen or render by origin.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from design_suite.project import project_root  # noqa: E402

# Three roots that used to be one directory. Inside the app, `parents[1]` meant all
# of "where the scripts are", "where the pipeline data is", and "which project to
# bundle into". As a plugin those are three different places, and conflating them
# points the pipeline at its own directory instead of the project — the same trap
# _bootstrap.py exists to avoid for the audits.
REPO = project_root()                       # the project being worked on
SCRIPTS = Path(__file__).resolve().parent   # the render drivers, here in the plugin


def _load_profile() -> dict:
    path = REPO / ".design-suite" / "profile.json"
    if not path.is_file():
        raise SystemExit(f"no profile at {path} — is this a configured project?")
    return json.loads(path.read_text())


PROFILE = _load_profile()

# Pipeline DATA stays in the project — manifests, palette, sources, renders, outputs.
# Only the code moved.
PIPELINE = REPO / (PROFILE.get("pipelines", {}) or {}).get("assets", "asset_pipeline")
MANIFEST = PIPELINE / "manifest.json"
MANIFEST_LOCAL = PIPELINE / "manifest.local.json"
PALETTE = PIPELINE / "palette.json"
SOURCES = PIPELINE / "sources"
GENERATED = PIPELINE / "generated"
RENDERS = PIPELINE / "renders"
OUTPUTS = PIPELINE / "outputs"


def bundle_dir() -> Path:
    """Where `sync` puts finished assets, per the asset adapter.

    Not a literal: `assets/images` is a Flutter convention. A bundler-driven project
    uses `public/`, and its adapter is what knows that. Resolved lazily so every
    other subcommand still works on a project whose adapters.assets is unset.
    """
    from design_suite.adapters import assets as asset_seam
    from design_suite.adapters.base import AdapterContext
    name = (PROFILE.get("adapters", {}) or {}).get("assets")
    if not name:
        raise SystemExit(
            ".design-suite/profile.json does not set adapters.assets — the pipeline "
            "cannot know where this stack bundles assets, and will not guess.")
    ctx = AdapterContext(repo=REPO, profile=PROFILE, exceptions={})
    return REPO / asset_seam.load(name).asset_root(ctx)


RECOLOR_SCRIPT = SCRIPTS / "recolor_render.py"
GEN_RENDER_SCRIPT = SCRIPTS / "gen_render.py"
ANIMATE_RENDER_SCRIPT = SCRIPTS / "animate_render.py"
ANIMATE_RECOLOR_SCRIPT = SCRIPTS / "animate_recolor_render.py"
ANIMATE_SHAPES_SCRIPT = SCRIPTS / "animate_shapes_render.py"
SHAPES_SVG_SCRIPT = SCRIPTS / "shapes_svg_render.py"
SHAPES_BLENDER_SCRIPT = SCRIPTS / "shapes_blender_render.py"
ENCODE_SCRIPT = SCRIPTS / "encode.py"
VERIFY_MOTION_SCRIPT = SCRIPTS / "verify_motion.py"
EXPORT_PALETTE = SCRIPTS / "export_palette.py"

BLENDER_CANDIDATES = ["blender", "/Applications/Blender.app/Contents/MacOS/Blender"]
BREW_CANDIDATES = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
WEBP_QUALITY = "82"

# Homebrew packages the pipeline needs. (formula, is_cask, provides-binary)
BREW_FORMULAE = [
    ("blender", True, "blender"),
    ("webp", False, "cwebp"),
    ("librsvg", False, "rsvg-convert"),
    ("git-lfs", False, "git-lfs"),
    ("ffmpeg", False, "ffmpeg"),  # baked-motion apng/gif/mp4/webm targets
]


def fail(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_bin(candidates: list[str], env_var: str | None = None) -> str | None:
    names = ([os.environ[env_var]] if env_var and os.environ.get(env_var) else [])
    for c in names + candidates:
        found = shutil.which(c) or (c if Path(c).is_file() else None)
        if found:
            return found
    return None


def find_blender() -> str | None:
    return find_bin(BLENDER_CANDIDATES, "BLENDER")


def find_brew() -> str | None:
    return find_bin(BREW_CANDIDATES)


def _merged_assets() -> list[dict]:
    """manifest.json (committed) + manifest.local.json (gitignored WIP
    overlay), merged by id — local wins on collision, else is appended.

    Why: WIP assets (no license yet, placement undecided) used to be added
    directly to manifest.json and hand-stripped out again before every commit
    of an unrelated pipeline change — slow, and it already caused two real
    slips (a stray re-encoding diff, a duplicate section from a bad merge).
    manifest.local.json holds exactly that in-progress state instead;
    manifest.json never needs editing just to keep it out of a commit.
    """
    assets = json.loads(MANIFEST.read_text())["assets"]
    if MANIFEST_LOCAL.is_file():
        local_assets = json.loads(MANIFEST_LOCAL.read_text()).get("assets", [])
        by_id = {a["id"]: i for i, a in enumerate(assets)}
        for local in local_assets:
            if local["id"] in by_id:
                assets[by_id[local["id"]]] = local
            else:
                assets.append(local)
    return assets


def load_assets(selector: str | None, origin: str | None = None) -> list[dict]:
    assets = _merged_assets()
    assets = [a for a in assets if not a["id"].startswith("example_")]
    if origin:
        assets = [a for a in assets if a.get("origin", "envato") == origin]
    if selector and selector != "--all":
        assets = [a for a in assets if a["id"] == selector]
        if not assets:
            fail(f"asset '{selector}' not found in manifest.json (origin filter: {origin})")
    if not assets:
        where = f" with origin '{origin}'" if origin else ""
        fail(f"no (non-example) assets{where} in manifest.json")
    return assets


# ── setup ────────────────────────────────────────────────────────────────────

def cmd_setup(_: str | None) -> None:
    """Idempotently install everything a designer needs. Safe to re-run."""
    brew = find_brew()
    if not brew:
        print(
            "Homebrew is required and needs your password to install (one time):\n\n"
            '  /bin/bash -c "$(curl -fsSL '
            'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n\n'
            "Then follow its 'Next steps' to add brew to your PATH, open a new\n"
            "terminal, and re-run this script with `setup`"
        )
        sys.exit(1)

    for formula, is_cask, _binary in BREW_FORMULAE:
        listed = subprocess.run(
            [brew, "list", "--versions", formula],
            capture_output=True, text=True,
        )
        if listed.returncode == 0:
            print(f"  ✓ {formula} already installed")
            continue
        print(f"  … installing {formula}")
        cmd = [brew, "install"] + (["--cask"] if is_cask else []) + [formula]
        subprocess.run(cmd, check=True)

    print("  … git lfs install")
    subprocess.run(["git", "lfs", "install"], check=True)

    print("  … regenerating palette.json from AppTokens")
    subprocess.run([sys.executable, str(EXPORT_PALETTE)], check=True)

    print("\nSetup complete. Verifying:")
    _run_check(exit_on_fail=False)


# ── check ──────────────────────────────────────────────────────────────────────

def _run_check(exit_on_fail: bool) -> bool:
    ok = True

    def report(name: str, found: bool, hint: str) -> None:
        nonlocal ok
        print(f"  {'✓' if found else '✗'} {name}" + ("" if found else f" — {hint}"))
        ok = ok and found

    print("Tooling:")
    report("blender (3D generate/render)", find_blender() is not None,
           "re-run this script with `setup`")
    report("cwebp (optimize)", shutil.which("cwebp") is not None,
           "run: pipeline.py setup")
    report("rsvg-convert (2D svg rasterize)", shutil.which("rsvg-convert") is not None,
           "run: pipeline.py setup")
    report("sips (macOS built-in)", shutil.which("sips") is not None, "expected on macOS")
    report("git-lfs (purchased .blend sources)", shutil.which("git-lfs") is not None,
           "run: pipeline.py setup")
    # Optional — only the img2webp/png_seq motion targets are required; ffmpeg
    # unlocks the apng/gif/mp4/webm baked-motion targets. Not required, so it
    # never flips the overall check result.
    have_ffmpeg = shutil.which("ffmpeg") is not None
    print(f"  {'✓' if have_ffmpeg else '·'} ffmpeg (optional — apng/gif/mp4/webm "
          f"motion targets)" + ("" if have_ffmpeg else " — run: pipeline.py setup"))
    print("Files:")
    report("manifest.json", MANIFEST.is_file(), "missing")
    report("palette.json", PALETTE.is_file(),
           "re-run export_palette.py from the plugin")
    has_local = MANIFEST_LOCAL.is_file()
    print(f"  {'✓' if has_local else '·'} manifest.local.json "
          f"(optional — gitignored WIP overlay, merged in at load time)"
          + (f" — {len(json.loads(MANIFEST_LOCAL.read_text()).get('assets', []))} "
             f"asset(s)" if has_local else ""))
    if exit_on_fail:
        sys.exit(0 if ok else 1)
    return ok


def cmd_check(_: str | None) -> None:
    _run_check(exit_on_fail=True)


# ── gen (generated assets → master PNG) ─────────────────────────────────────────

def _produce_generated(asset: dict) -> None:
    aid = asset["id"]
    source_id = asset.get("source", aid)
    gen = asset.get("generator", {})
    kind = gen.get("kind")
    size = asset.get("render", {}).get("masterPx", 1024)
    RENDERS.mkdir(exist_ok=True)
    out = RENDERS / f"{aid}.png"

    if kind == "svg":
        rsvg = shutil.which("rsvg-convert") or fail(
            "rsvg-convert not found — run: pipeline.py setup"
        )
        svg = GENERATED / source_id / f"{source_id}.svg"
        if not svg.is_file():
            fail(f"missing {svg.relative_to(REPO)}")
        print(f"[gen:svg] {aid} → {out.relative_to(REPO)}")
        subprocess.run(
            [rsvg, "-w", str(size), "-h", str(size), "-a",
             str(svg), "-o", str(out)],
            check=True,
        )
    elif kind == "blender":
        blender = find_blender() or fail("Blender not found — run: pipeline.py setup")
        script = GENERATED / source_id / "gen.py"
        if not script.is_file():
            fail(f"missing {script.relative_to(REPO)}")
        print(f"[gen:blender] {aid} (source: {source_id}) → {out.relative_to(REPO)}")
        subprocess.run(
            [blender, "-b", "-P", str(GEN_RENDER_SCRIPT), "--",
             "--script", str(script),
             "--palette", str(PALETTE),
             "--out", str(out),
             "--size", str(size),
             "--params", json.dumps(gen.get("params", {}))],
            check=True,
        )
    elif kind == "shapes":
        # One data-driven shape-spec (generated/<id>/shapes.py), two possible
        # renderers picked by generator.style: 'flat' (default, plain python3
        # + rsvg-convert, no Blender) or 'skeuomorphic' (layered/beveled/
        # glossy 3D via Blender, reusing the shared studio rig). See
        # {{doc:assets}} "shapes" section.
        script = GENERATED / source_id / "shapes.py"
        if not script.is_file():
            fail(f"missing {script.relative_to(REPO)}")
        style = gen.get("style", "flat")
        if style == "flat":
            print(f"[gen:shapes:flat] {aid} (source: {source_id}) → "
                  f"{out.relative_to(REPO)}")
            subprocess.run(
                [sys.executable, str(SHAPES_SVG_SCRIPT),
                 "--script", str(script),
                 "--palette", str(PALETTE),
                 "--out", str(out),
                 "--size", str(size),
                 "--params", json.dumps(gen.get("params", {}))],
                check=True,
            )
        elif style == "skeuomorphic":
            blender = find_blender() or fail("Blender not found — run: pipeline.py setup")
            print(f"[gen:shapes:skeuomorphic] {aid} (source: {source_id}) → "
                  f"{out.relative_to(REPO)}")
            subprocess.run(
                [blender, "-b", "-P", str(SHAPES_BLENDER_SCRIPT), "--",
                 "--script", str(script),
                 "--palette", str(PALETTE),
                 "--out", str(out),
                 "--size", str(size),
                 "--params", json.dumps(gen.get("params", {}))],
                check=True,
            )
        else:
            fail(f"asset '{aid}' generator.style must be 'flat' or 'skeuomorphic' "
                 f"(got {style!r})")
    else:
        fail(f"asset '{aid}' generator.kind must be 'svg', 'blender', or 'shapes' "
             f"(got {kind!r})")


def cmd_gen(selector: str | None) -> None:
    for asset in load_assets(selector, origin="generated"):
        _produce_generated(asset)


# ── render (purchased .blend → master PNG) ──────────────────────────────────────

def _produce_envato(asset: dict) -> None:
    blender = find_blender() or fail("Blender not found — run: pipeline.py setup")
    RENDERS.mkdir(exist_ok=True)
    aid = asset["id"]
    source_id = asset.get("source", aid)
    blend = SOURCES / source_id / f"{source_id}.blend"
    if not blend.is_file():
        fail(f"missing {blend.relative_to(REPO)}")
    out = RENDERS / f"{aid}.png"
    print(f"[render] {aid} (source: {source_id}) → {out.relative_to(REPO)}")
    subprocess.run(
        [blender, "-b", str(blend), "-P", str(RECOLOR_SCRIPT), "--",
         "--palette", str(PALETTE),
         "--out", str(out),
         "--size", str(asset.get("render", {}).get("masterPx", 1440)),
         "--map", json.dumps(asset.get("materials", {})),
         "--hexmap", json.dumps(asset.get("materialsHex", {})),
         "--ramp", json.dumps(asset.get("colorRamp", {}))],
        check=True,
    )


def cmd_render(selector: str | None) -> None:
    for asset in load_assets(selector, origin="envato"):
        _produce_envato(asset)


def _produce(asset: dict) -> None:
    if asset.get("origin", "envato") == "generated":
        _produce_generated(asset)
    else:
        _produce_envato(asset)


# ── animate (baked Tier-B motion → animated file + contact sheet) ───────────────

def _produce_motion(asset: dict, quick: bool = False) -> None:
    """Render a baked-motion asset to a PNG frame sequence, encode it to the
    configured target format(s) + a static POSTER frame, and render a contact
    sheet for review.

    Output naming: if the asset has `slots`, outputs are written per slot name
    (`outputs/<slot>.webp` animated + `outputs/<slot>_poster.webp` static) so
    `sync` bundles them into the project's asset root for baked motion. With
    no slots, outputs are id-named — a preview-only author loop, not bundled.

    Bundle-budget policy: baked motion is emitted at a SINGLE resolution
    (motion.px), NOT the 1x/2x/3x density fan-out static assets get — an
    animated WebP × N frames × 3 densities is too heavy for a decorative asset.
    Flutter scales the one file; the poster is likewise single-resolution.

    `quick=True` (the `--quick` CLI flag) caps frames/resolution and skips
    every encode target but the first, for fast/cheap iteration while a preset
    is still being tuned — the manifest's real frames/px/targets are used for
    the final promote run. See {{doc:assets}} §9.
    """
    aid = asset["id"]
    motion = asset.get("motion") or fail(f"asset '{aid}' has no 'motion' field")
    if motion.get("tier") != "baked":
        fail(f"asset '{aid}' motion.tier must be 'baked' to animate (got "
             f"{motion.get('tier')!r}); Tier-A 'flutter' motion is played in "
             f"the client from the static still and needs no render")

    blender = find_blender() or fail("Blender not found — run: pipeline.py setup")
    origin = asset.get("origin", "envato")
    source_id = asset.get("source", aid)

    preset = motion.get("preset") or fail(f"asset '{aid}' motion.preset is required")
    px = motion.get("px", 512)
    frames = motion.get("frames", 60)
    fps = motion.get("fps", 30)
    targets = motion.get("targets", ["webp_anim"])
    loop = 0 if motion.get("loop", True) else 1
    target_objects = motion.get("objects", [])

    if quick:
        px = min(px, 320)
        frames = min(frames, 16)
        targets = targets[:1]  # skip extra encode targets while iterating

    frames_dir = RENDERS / f"{aid}_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    print(f"[animate] {aid} (source: {source_id}, origin: {origin}"
          f"{', quick' if quick else ''}): preset={preset} frames={frames} "
          f"fps={fps} px={px} targets={','.join(targets)}")

    contact = RENDERS / f"{aid}_contact.png"

    if origin == "generated":
        gen_kind = asset.get("generator", {}).get("kind", "blender")
        if gen_kind == "shapes":
            script = GENERATED / source_id / "shapes.py"
            driver = ANIMATE_SHAPES_SCRIPT
            label = "[animate:shapes]"
        else:
            script = GENERATED / source_id / "gen.py"
            driver = ANIMATE_RENDER_SCRIPT
            label = "[animate]"
        if not script.is_file():
            fail(f"missing {script.relative_to(REPO)}")
        print(f"  {label} driver={driver.name}")
        subprocess.run(
            [blender, "-b", "-P", str(driver), "--",
             "--script", str(script),
             "--palette", str(PALETTE),
             "--out", str(frames_dir / "f_"),
             "--size", str(px),
             "--params", json.dumps(asset.get("generator", {}).get("params", {})),
             "--preset", preset,
             "--motion-params", json.dumps(motion.get("params", {})),
             "--frames", str(frames),
             "--fps", str(fps),
             # Same Blender process renders the contact sheet right after the
             # frames — no second `blender -b ...` spawn (~1-2s startup) just
             # for the review image.
             "--contact-out", str(contact)],
            check=True,
        )
    else:
        blend = SOURCES / source_id / f"{source_id}.blend"
        if not blend.is_file():
            fail(f"missing {blend.relative_to(REPO)}")
        subprocess.run(
            [blender, "-b", str(blend), "-P", str(ANIMATE_RECOLOR_SCRIPT), "--",
             "--palette", str(PALETTE),
             "--out", str(frames_dir / "f_"),
             "--size", str(px),
             "--map", json.dumps(asset.get("materials", {})),
             "--hexmap", json.dumps(asset.get("materialsHex", {})),
             "--ramp", json.dumps(asset.get("colorRamp", {})),
             "--preset", preset,
             "--motion-params", json.dumps(motion.get("params", {})),
             "--frames", str(frames),
             "--fps", str(fps),
             "--target-objects", json.dumps(target_objects),
             "--contact-out", str(contact)],
            check=True,
        )

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    first_frame = sorted(frames_dir.glob("f_*.png"))[0]
    slots = asset.get("slots", [])
    bases = [s["name"] for s in slots] if slots else [aid]

    for base in bases:
        subprocess.run(
            [sys.executable, str(ENCODE_SCRIPT),
             "--frames-dir", str(frames_dir),
             "--out", str(OUTPUTS / base),
             "--fps", str(fps),
             "--loop", str(loop),
             "--targets", ",".join(targets)],
            check=True,
        )
        # Static poster (first frame) for the reduce-motion fallback — a Tier-B
        # asset ships the animated file AND this still, and AppAsset picks the
        # poster when the OS "reduce motion" setting is on.
        if shutil.which("cwebp"):
            poster = OUTPUTS / f"{base}_poster.webp"
            subprocess.run(
                ["cwebp", "-quiet", "-q", WEBP_QUALITY, "-metadata", "none",
                 str(first_frame), "-o", str(poster)],
                check=True,
            )
            print(f"  poster → {poster.relative_to(REPO)}")

    # Contact sheet was already rendered above, in the same Blender process
    # as the frames (via --contact-out) — no separate spawn here.
    tail = ("run `sync` to bundle into the project's asset root"
            if slots else "preview only — add slots[] to bundle it")
    print(f"[animate] {aid} done — contact sheet: {contact.relative_to(REPO)}; "
          f"{tail}")


def cmd_animate(selector: str | None, quick: bool = False) -> None:
    ran = 0
    for asset in load_assets(selector):
        if asset.get("motion"):
            _produce_motion(asset, quick=quick)
            ran += 1
        else:
            print(f"  (skip {asset['id']} — no motion field)")
    if ran == 0:
        print("[animate] no assets with a 'motion' field matched")


# ── verify-motion (quantitative check of an already-rendered frame seq) ────────

def cmd_verify_motion(selector: str | None) -> None:
    """Quantitatively verify a motion asset's ALREADY-RENDERED frames (run
    `animate` first) — replaces the ad-hoc verification scripts hand-written
    during motion review this session (centroid/bbox across frames, a
    loop-seam check, an optional static-region diff for `motion.objects`
    targeting). See verify_motion.py for exactly what it reports."""
    if not selector or selector == "--all":
        fail("verify-motion needs a single asset id (not --all)")
    blender = find_blender() or fail("Blender not found — run: pipeline.py setup")
    asset = load_assets(selector)[0]
    aid = asset["id"]
    frames_dir = RENDERS / f"{aid}_frames"
    if not frames_dir.is_dir() or not any(frames_dir.glob("*.png")):
        fail(f"no rendered frames for '{aid}' at {frames_dir.relative_to(REPO)} "
             f"— run `pipeline.py animate {aid}` first")

    static_region = asset.get("motion", {}).get("verifyStaticRegion")
    cmd = [blender, "-b", "-P", str(VERIFY_MOTION_SCRIPT), "--",
           "--frames-dir", str(frames_dir)]
    if static_region:
        cmd += ["--static-region", static_region]
    subprocess.run(cmd, check=True)


# ── optimize ───────────────────────────────────────────────────────────────────

def cmd_optimize(selector: str | None) -> None:
    if not shutil.which("cwebp"):
        fail("cwebp not found — run: pipeline.py setup")
    for asset in load_assets(selector):
        aid = asset["id"]
        master = RENDERS / f"{aid}.png"
        if not master.is_file():
            fail(f"no master for '{aid}' — run the gen/render stage first")
        master_px = asset.get("render", {}).get("masterPx", 1440)
        for slot in asset["slots"]:
            name, dp = slot["name"], slot["dp"]
            if dp * 3 > master_px:
                print(f"  WARNING: slot '{name}' 3x ({dp * 3}px) exceeds the "
                      f"{master_px}px master — raise render.masterPx")
            for scale, subdir in ((1, ""), (2, "2.0x"), (3, "3.0x")):
                dest_dir = OUTPUTS / subdir if subdir else OUTPUTS
                dest_dir.mkdir(parents=True, exist_ok=True)
                tmp = dest_dir / f"{name}.tmp.png"
                dest = dest_dir / f"{name}.webp"
                subprocess.run(
                    ["sips", "-Z", str(dp * scale), str(master), "--out", str(tmp)],
                    check=True, capture_output=True,
                )
                subprocess.run(
                    ["cwebp", "-quiet", "-mt", "-q", WEBP_QUALITY,
                     "-metadata", "none", str(tmp), "-o", str(dest)],
                    check=True,
                )
                tmp.unlink()
                print(f"  {dest.relative_to(REPO)}  ({dest.stat().st_size / 1024:.0f} KB)")


# ── sync ───────────────────────────────────────────────────────────────────────

def cmd_sync(_: str | None) -> None:
    if not OUTPUTS.is_dir():
        fail("nothing in outputs/ — run the optimize stage first")
    target = bundle_dir()
    copied = 0
    for webp in OUTPUTS.rglob("*.webp"):
        dest = target / webp.relative_to(OUTPUTS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(webp, dest)
        copied += 1
        print(f"  → {dest.relative_to(REPO)}")
    print(f"[sync] {copied} file(s) into {target.relative_to(REPO)}/ — commit them "
          f"with the feature that uses them")


def cmd_all(selector: str | None) -> None:
    for asset in load_assets(selector):
        _produce(asset)
    cmd_optimize(selector)
    cmd_sync(None)


COMMANDS = {
    "setup": cmd_setup,
    "check": cmd_check,
    "gen": cmd_gen,
    "render": cmd_render,
    "optimize": cmd_optimize,
    "sync": cmd_sync,
    "all": cmd_all,
    "animate": cmd_animate,
    "verify-motion": cmd_verify_motion,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "animate":
        quick = "--quick" in rest
        rest = [a for a in rest if a != "--quick"]
        cmd_animate(rest[0] if rest else None, quick=quick)
    else:
        COMMANDS[cmd](rest[0] if rest else None)


if __name__ == "__main__":
    main()
