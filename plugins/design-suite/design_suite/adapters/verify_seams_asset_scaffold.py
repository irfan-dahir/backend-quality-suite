#!/usr/bin/env python3
"""Prove the asset and scaffold seams work, including that they refuse correctly.

Companion to verify_seam.py, which covers the language seam. Runs in CI.

Two things get asserted, and the second matters as much as the first:

1. The Flutter implementations do the right thing — including the case a naive
   implementation gets wrong, where a *directory* entry in pubspec.yaml registers
   every file beneath it.
2. The `bundler` adapter **raises** rather than answering. A stack with no asset
   registry must produce a refusal, never False (a permanent false finding on
   every asset) and never True (hiding every real one).

    python3 design_suite/adapters/verify_seams_asset_scaffold.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from design_suite.adapters import assets as asset_seam        # noqa: E402
from design_suite.adapters import scaffold as scaffold_seam   # noqa: E402
from design_suite.adapters.base import AdapterContext, CapabilityError  # noqa: E402

PUBSPEC = """\
name: fixture_app

dependencies:
  flutter:
    sdk: flutter

flutter:
  uses-material-design: true

  # A directory entry. Everything under it is registered — this is the case a
  # literal-path implementation gets wrong.
  assets:
    - assets/images/
    - assets/data/seed.json

  fonts:
    - family: Inter
"""

PROFILE = {
    "source": {"root": "lib"},
    "pipelines": {"assets": "asset_pipeline"},
    "adapters": {"assets": "flutter_pubspec", "scaffold": "flutter"},
}

problems: list[str] = []


def check(label: str, got, want):
    if got != want:
        problems.append(f"{label}: got {got!r}, want {want!r}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "pubspec.yaml").write_text(PUBSPEC)
    ctx = AdapterContext(repo=tmp, profile=PROFILE, exceptions={})

    # ---- asset seam: flutter_pubspec -------------------------------------
    fp = asset_seam.load("flutter_pubspec")

    entries = fp.registered_entries(ctx)
    check("registered_entries", entries, ["assets/images/", "assets/data/seed.json"])

    # The `fonts:` list must not leak in, and neither must the top-level
    # dependencies block.
    for leaked in ("family: Inter", "flutter"):
        if any(leaked in e for e in entries):
            problems.append(f"registered_entries leaked {leaked!r} from another block")

    # Directory registration — the subtle one.
    check("dir-covered asset", fp.is_registered(ctx, "assets/images/hero.webp"), True)
    check("dir-covered 2.0x variant",
          fp.is_registered(ctx, "assets/images/2.0x/hero.webp"), True)
    check("literal entry", fp.is_registered(ctx, "assets/data/seed.json"), True)
    check("not registered", fp.is_registered(ctx, "assets/audio/beep.mp3"), False)
    check("leading ./ tolerated", fp.is_registered(ctx, "./assets/images/a.webp"), True)

    check("manifest_path", fp.manifest_path(ctx), "asset_pipeline/manifest.json")
    check("local_manifest_path", fp.local_manifest_path(ctx),
          "asset_pipeline/manifest.local.json")

    # register() must be idempotent and must not touch an already-covered path.
    before = (tmp / "pubspec.yaml").read_text()
    fp.register(ctx, "assets/images/hero.webp")
    if (tmp / "pubspec.yaml").read_text() != before:
        problems.append("register() rewrote pubspec.yaml for an already-covered asset")

    fp.register(ctx, "assets/audio/beep.mp3")
    if not fp.is_registered(ctx, "assets/audio/beep.mp3"):
        problems.append("register() did not actually register a new asset")
    fp.register(ctx, "assets/audio/beep.mp3")
    if (tmp / "pubspec.yaml").read_text().count("assets/audio/beep.mp3") != 1:
        problems.append("register() is not idempotent — duplicated an entry")

    # ---- asset seam: bundler must REFUSE ---------------------------------
    bundler = asset_seam.load("bundler")
    for fn, args in (("is_registered", ("public/x.png",)),
                     ("register", ("public/x.png",)),
                     ("registered_entries", ())):
        try:
            getattr(bundler, fn)(ctx, *args)
            problems.append(
                f"bundler.{fn} returned instead of raising — a stack with no asset "
                f"registry must refuse, not answer")
        except CapabilityError:
            pass
    check("bundler asset_root", bundler.asset_root(ctx), "public")

    # An unknown adapter must be a hard error, not a silent default.
    try:
        asset_seam.load("no_such_adapter")
        problems.append("load() accepted an unknown asset adapter")
    except SystemExit:
        pass

    # ---- scaffold seam ---------------------------------------------------
    fl = scaffold_seam.load("flutter")
    check("screen_path",
          fl.screen_path(ctx, "condition reports", feature="archive"),
          "lib/features/archive/presentation/pages/condition_reports_screen.dart")

    body = fl.render(ctx, "condition reports", feature="archive")
    for needle in ("CONDITION REPORTS SCREEN CONTRACT", "class ConditionReportsScreen",
                   "ArchiveAdapter adapter", "DECIDE", "Do not fetch data."):
        if needle not in body:
            problems.append(f"render() output is missing {needle!r}")
    # The three-state core is the portable part; loading and error get their own
    # widgets, content is inline.
    for needle in ("_ConditionReportsLoading", "_ConditionReportsError"):
        if needle not in body:
            problems.append(f"render() did not emit a state widget: {needle!r}")

    companions = fl.companion_files(ctx, "condition reports", feature="archive")
    if not companions:
        problems.append("companion_files() returned nothing — the adapter class is mandatory")
    else:
        c = companions[0]
        check("companion path", c["path"], "lib/features/archive/archive_adapter.dart")
        if "class ArchiveAdapter" not in c["body"]:
            problems.append("companion adapter body does not declare the class")

    edits = fl.register(ctx, "lab results", feature="labs")
    if not any("app_router.dart" in e["file"] for e in edits):
        problems.append("register() did not describe the router edit")
    if not any(e["file"] == "DOC:flows" for e in edits):
        problems.append("register() did not require the flows doc update")

    # ---- report ----------------------------------------------------------
    print(f"asset seam: {len(entries)} pubspec entr(ies) parsed; "
          f"flutter_pubspec answered, bundler refused 3/3")
    print(f"scaffold seam: {len(body.splitlines())}-line screen + "
          f"{len(companions)} companion + {len(edits)} described edit(s)")

    if problems:
        print("\nSEAM BROKEN:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\nBoth seams hold: implementations answer, and the stack that cannot "
          "answer raises instead of guessing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
