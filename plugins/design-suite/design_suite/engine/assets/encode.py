"""Encode a rendered PNG frame sequence into an animated deliverable.

Pure python3 (NOT run inside Blender). Portable + project-agnostic: it only
turns frames into files, and knows nothing about Flutter or any consuming
project. A different project picks whichever target(s) its platform wants.

  python3 encode.py --frames-dir <dir> --out <basename-no-ext> \
      --fps 30 --loop 0 --targets webp_anim,png_seq

TARGET REGISTRY — one rendered frame sequence, many output formats:

  webp_anim  animated WebP (alpha, one file)     img2webp   ✅ always available
  png_seq    raw frame sequence (any player)     (copy)     ✅ always available
  apng       animated PNG (alpha)                ffmpeg     ⚠ needs ffmpeg
  gif        animated GIF (no alpha, 256 colors) ffmpeg     ⚠ needs ffmpeg
  mp4        H.264 video (no alpha)              ffmpeg     ⚠ needs ffmpeg
  webm       VP9 video (alpha)                   ffmpeg     ⚠ needs ffmpeg
  lottie     vector animation                    —          ✗ not from 3D frames

Lottie is deliberately unsupported here: it's a VECTOR format and cannot be
genuinely produced from baked 3D raster frames (only a fake embedded-raster
hack that throws away everything Lottie is for). Lottie belongs to a separate
2D/vector authoring path — see {{doc:assets}} motion section.

Raster targets beyond WebP/PNG need ffmpeg (one tool covers apng/gif/mp4/webm);
until it's installed, those targets fail with an install hint rather than
silently doing nothing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _frames(frames_dir: Path) -> list[Path]:
    fs = sorted(frames_dir.glob("*.png"))
    if not fs:
        sys.exit(f"[encode] no PNG frames in {frames_dir}")
    return fs


def _require_ffmpeg(target: str) -> str:
    ff = shutil.which("ffmpeg")
    if ff is None:
        sys.exit(
            f"[encode] target '{target}' needs ffmpeg, which is not installed.\n"
            f"          Install it: brew install ffmpeg  "
            f"(or run: pipeline.py setup)"
        )
    return ff


def _ms_per_frame(fps: int) -> int:
    return max(1, round(1000 / max(1, fps)))


def enc_webp_anim(frames, frames_dir, out_base, fps, loop) -> Path:
    out = out_base.with_suffix(".webp")
    out.parent.mkdir(parents=True, exist_ok=True)
    # img2webp: file-level -loop, then per-frame -d/-lossy applied to all
    # subsequent frames. No -q flag exists; lossy uses the built-in default.
    cmd = ["img2webp", "-loop", str(loop), "-d", str(_ms_per_frame(fps)), "-lossy"]
    cmd += [str(f) for f in frames]
    cmd += ["-o", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def enc_png_seq(frames, frames_dir, out_base, fps, loop) -> Path:
    out_dir = out_base.parent / f"{out_base.name}_frames"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for i, f in enumerate(frames, start=1):
        shutil.copy2(f, out_dir / f"frame_{i:04d}.png")
    return out_dir


def _ffmpeg_glob_input(ff, fps, frames_dir):
    # -pattern_type glob avoids needing a printf-style numeric pattern.
    return [ff, "-y", "-framerate", str(fps),
            "-pattern_type", "glob", "-i", f"{frames_dir}/*.png"]


def enc_apng(frames, frames_dir, out_base, fps, loop) -> Path:
    ff = _require_ffmpeg("apng")
    out = out_base.with_suffix(".apng")
    cmd = _ffmpeg_glob_input(ff, fps, frames_dir)
    cmd += ["-f", "apng", "-plays", str(loop), str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def enc_gif(frames, frames_dir, out_base, fps, loop) -> Path:
    ff = _require_ffmpeg("gif")
    out = out_base.with_suffix(".gif")
    cmd = _ffmpeg_glob_input(ff, fps, frames_dir)
    cmd += ["-vf",
            "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            "-loop", str(loop), str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def enc_mp4(frames, frames_dir, out_base, fps, loop) -> Path:
    ff = _require_ffmpeg("mp4")
    out = out_base.with_suffix(".mp4")
    cmd = _ffmpeg_glob_input(ff, fps, frames_dir)
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def enc_webm(frames, frames_dir, out_base, fps, loop) -> Path:
    ff = _require_ffmpeg("webm")
    out = out_base.with_suffix(".webm")
    cmd = _ffmpeg_glob_input(ff, fps, frames_dir)
    cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def enc_lottie(frames, frames_dir, out_base, fps, loop) -> Path:
    sys.exit(
        "[encode] target 'lottie' is not supported for baked 3D motion — "
        "Lottie is a vector format and cannot be produced from 3D raster "
        "frames. Use a 2D/vector authoring path instead ({{doc:assets}})."
    )


TARGETS = {
    "webp_anim": enc_webp_anim,
    "png_seq": enc_png_seq,
    "apng": enc_apng,
    "gif": enc_gif,
    "mp4": enc_mp4,
    "webm": enc_webm,
    "lottie": enc_lottie,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--frames-dir", required=True)
    p.add_argument("--out", required=True, help="output basename, no extension")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--loop", type=int, default=0, help="0 = infinite")
    p.add_argument("--targets", default="webp_anim")
    args = p.parse_args()

    frames_dir = Path(args.frames_dir)
    out_base = Path(args.out)
    frames = _frames(frames_dir)

    wanted = [t.strip() for t in args.targets.split(",") if t.strip()]
    unknown = [t for t in wanted if t not in TARGETS]
    if unknown:
        sys.exit(f"[encode] unknown target(s): {', '.join(unknown)} — "
                 f"known: {', '.join(sorted(TARGETS))}")

    for t in wanted:
        out = TARGETS[t](frames, frames_dir, out_base, args.fps, args.loop)
        print(f"[encode] {t} -> {out}")


if __name__ == "__main__":
    main()
