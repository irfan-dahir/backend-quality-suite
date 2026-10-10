---
name: animate-asset
description: "Add baked motion to an existing asset: pick a preset, render the frame sequence, encode an animated file plus a static reduce-motion poster, and bundle both. Produces real files, so it must be invoked explicitly."
invocation: explicit
maturity: unverified
---

# /animate-asset

> Documents are referenced by role, e.g. `{{doc:assets}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" assets`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You add motion to an asset already in the pipeline — pick the right tier, author it, preview it cheaply, iterate, and promote. Full system + the two-tier model: `{{doc:assets}}` §9.

**The split rule decides everything:** does the motion only translate/scale/rotate/fade the whole silhouette in 2D? → **Tier A** (Flutter-native, animate the existing still, no render). Does it need a new 3D angle, a changing silhouette, or a material/lighting change? → **Tier B** (baked Blender frames → animated file). Get this call right before writing anything — it's the difference between a client-side code change and a render pipeline run.

---

## Step 0 — Preconditions (self-bootstrapping)

Run `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" check`. If any required tool is ✗, run `pipeline.py setup` for the user and re-check. `ffmpeg` showing `·` (not `✗`) is fine — it's optional, only needed for the `apng`/`gif`/`mp4`/`webm` encode targets; `webp_anim` (the default) needs nothing extra.

Confirm you're on a feature branch, not `demo`/`main`.

**Default is no motion.** Only proceed if the user has actually asked for movement on a specific asset — don't suggest animating things speculatively. Motion is opt-in and used with restraint, especially for this app's 50+ demographic.

**Efficiency note — batch headless inspection into ONE Blender call.** Each `blender -b ...` invocation has real startup overhead (~1–2s) independent of what it does. If you need multiple facts about a `.blend` (object names, positions, materials, camera state), write ONE Python script/`--python-expr` that prints everything you need and run it once — never make a separate Blender call per question. This matters most before authoring `motion.objects` targeting (Step 2b): one script that dumps every top-level mesh's name + world bounding-box centre + material is enough to cluster objects into visual groups by position, replacing several rounds of render-and-guess.

## Step 1 — Identify the asset and pick the tier

Ask (if not already clear): which existing asset (manifest `id`), and what motion is wanted (idle loop, entrance, emphasis, a showcase spin, etc.)?

Apply the split rule:

| The motion... | Tier | Where it lives |
|---|---|---|
| Only moves/scales/rotates/fades the whole shape (pop-in, idle bob, pulse, wobble) | **A — Flutter-native** | `<source.sharedComponentDir>/app_asset.dart` `AssetMotion` enum + a private motion widget |
| Needs a new angle, a changing silhouette, or a material/lighting change (turntable, shimmer sweep, morph) | **B — baked** | `${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/presets.py` + the asset's manifest `motion` field |

If genuinely ambiguous, ask the user rather than guessing — the cost of building the wrong tier is a full render cycle (Tier B) or a rejected PR (client-side motion that should have been baked).

**If the composition has multiple distinct visual elements** (e.g. an icon pairing two objects, like a document + a bottle), ask whether they should move together (cheapest, lowest risk, one preset on the whole group) or whether only a specific part should move (needs identifying which objects belong to that part — see Step 2b's targeting note — a real fork worth asking about, not guessing).

**Tier B works on both origins.** `origin: "generated"` renders via `animate_render.py` (the `build(ctx)` subject is the pivot target). `origin: "envato"` (purchased `.blend`, the default) renders via `animate_recolor_render.py` — recoloring is identical to `/add-asset`'s (`materials`/`materialsHex`/`colorRamp`); by default every top-level MESH object is parented to the pivot together so the whole composition moves as one group. If the user wants only PART of a multi-element composition to move (e.g. just the bottle within a paper+bottle icon), use the manifest's `motion.objects` field to name that subset — see Step 2b. Framing always covers the whole composition regardless, so the static part never gets cropped out. The scene's own authored camera/lights are reused as-is, only re-framed.

## Step 2a — Tier A: author a Flutter preset

1. Check `AssetMotion` in `app_asset.dart` for an existing preset that fits (currently `popIn`). If one fits, just use it: `AppAsset(name: '<slot>', motion: AssetMotion.popIn)`.
2. If a new preset is needed, add an enum value + a small private widget (see `_PopIn` as the reference shape: driven by `TweenAnimationBuilder`, no controller lifecycle, uses `AppTokens` duration/curve tokens — never hardcode a duration or curve). Keep it a pure function of the still — no network/state dependencies.
3. **Reduce-motion is non-negotiable.** Every Tier-A preset must be skipped when `MediaQuery.of(context).disableAnimations` is true — `AppAsset.build` already gates on this before dispatching to any preset; adding a new `case` to the switch is sufficient, don't re-implement the check per-preset.
4. Verify: run the existing widget tests (`flutter test test/shared/components/app_asset_test.dart`) and add a case for the new preset following the same pattern (motion plays; reduce-motion forces static).
5. No pipeline render, no manifest change — this ships as a normal Dart commit.

## Step 2b — Tier B: author + render a baked preset

1. Check `presets.py`'s `PRESETS` registry for an existing preset (`turntable`, `idle_float`, `pulse`). If one fits with different `params`, skip to Step 3.
2. If a new preset is needed, add a function following the existing shape: `fn(bpy, pivot, frame_start, frame_end, params) -> extent`. Keyframe the **pivot**, never the subject directly (the subject is parented to it, keeping its own build-time transform). For a seamless loop, keyframe across `[frame_start, frame_end + 1]` and let the renderer output `[frame_start, frame_end]`. Register it in `PRESETS`.
3. Add a `motion` field to the asset's manifest entry:
   ```jsonc
   "motion": {
     "tier": "baked",
     "preset": "turntable",
     "params": { "axis": "Z", "turns": 1 },
     "frames": 48, "fps": 24, "px": 480, "loop": true,
     "targets": ["webp_anim"],
     "objects": ["Cylinder", "Cylinder.001"]
   }
   ```
   `objects` is optional and **envato-origin only** — a list of top-level MESH object names that should move; omit it to move the whole composition together (the default). Use it whenever the user wants only part of a multi-element purchased asset to move. **Identify the right names efficiently, in one pass, before rendering anything**: a single headless Blender call that prints every top-level mesh's name, world bounding-box centre, and material (see the diagnostic script pattern in Step 0's efficiency note) is enough to cluster objects into visual groups by position — don't render-and-guess.

   Keep `frames`/`px` modest for iteration — see Step 3's `--quick` flag, which does this automatically without hand-editing the manifest back and forth.

## Step 3 — Render → preview via contact sheet → iterate (Tier B only)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" animate <id> --quick
```

**Always iterate with `--quick` first** (caps frames/resolution, skips extra encode targets) — it's materially faster and cheaper per iteration than the full settings, and iteration is where most `animate` calls happen while a preset is being tuned. Only drop `--quick` for the final pass once the motion is approved (Step 5).

Every `animate` call renders the frame sequence, encodes the configured target(s), and writes a **contact sheet** to `renders/<id>_contact.png` — a grid of sampled frames, in the SAME Blender process (no second `blender -b ...` spawn). **Read the contact sheet and show it to the user, always stating its absolute path**, exactly like every other render preview in this pipeline. A contact sheet is the token-cheap way to judge motion: one image instead of reading N frames individually. Do not judge motion from a single frame, and do not skip straight to encoding without looking.

**Also play the actual animated file in the Browser pane** — a contact sheet shows the motion's shape, but you (and the user) haven't actually *watched* it play until this step. The Browser pane cannot load `file://` URLs (blocked), so serve `outputs/` over a throwaway local HTTP server first:
```bash
python3 -m http.server 8934 --bind 127.0.0.1 --directory asset_pipeline/outputs &
```
then navigate the Browser pane to `http://127.0.0.1:8934/<id-or-slot>.webp` (Chromium plays animated WebP natively). Stop the server (`kill %1` or by PID) once you're done reviewing — it's a review aid, not something to leave running.

Check specifically for:
- **The motion actually reads** (e.g. a turntable's asymmetric feature visibly sweeps across the grid, or watch it loop live in the browser).
- **Framing holds across every tile** — no growing/shrinking/clipping subject, no blank tiles (the camera frames over the whole motion automatically, but a preset with much larger declared movement than usual is worth a second look).
- **The loop is seamless** — first and last tiles should look continuous, not jump; `pipeline.py verify-motion <id>` quantifies this (mean pixel diff between first/last frame, plus centroid/bbox range across all frames) instead of eyeballing it or hand-writing a one-off numpy check.
- **If `objects` narrows the motion to a subset**, the rest of the composition should look identical across tiles. The visual check from the contact sheet is usually enough — only reach for `verify-motion` (optionally with the asset's `motion.verifyStaticRegion`, if set) when the visual check is genuinely ambiguous at grid scale, not as a routine step. **Judge by mean pixel diff, not max** — max is dominated by a handful of edge/antialiasing pixels wherever the silhouette shifts by even a sub-pixel amount, and will flag a perfectly fine loop or a genuinely static region as broken (confirmed: a real seamless loop showed max diff ~0.98 from 0.07% of pixels while mean was ~0.0007). Also draw any `verifyStaticRegion` with a safety margin away from the moving/static boundary — a crop flush against it can clip a few edge pixels of the mover and give a false "moved" verdict.

Iterate on `params`/`frames`/`fps` and re-run `animate --quick` until approved. Every render is scratch (`renders/`, `outputs/` are gitignored) until Step 5 promotes it — say so up front.

## Step 4 — Decide the encode target(s) (Tier B only)

Default `webp_anim` (alpha, one file, no extra tooling) is almost always right. Only add `png_seq`/`apng`/`gif`/`mp4`/`webm` if the user has an actual need for that format (e.g. cross-project reuse outside Flutter) — ask rather than assume. `apng`/`gif`/`mp4`/`webm` need ffmpeg; if it's not installed, `encode` fails with an install hint — relay it, don't work around it.

Never offer `lottie` for this path — it's a vector format and cannot be genuinely produced from baked 3D frames. If the user specifically wants Lottie, say plainly that it needs a separate 2D/vector authoring path (not built), not a fake raster-embedded approximation.

## Step 5 — Promote (Tier B only)

1. Confirm the asset has real `slots` (needed for `animate` to name outputs per-slot and bundle them — an id-named/no-slots asset is preview-only, see `{{doc:assets}}` §9).
2. Re-run `animate` **without `--quick`** — this uses the manifest's real `frames`/`fps`/`px` (not the capped iteration settings), producing the final-quality bundle.
3. `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" sync` — bundles `<slot>.webp` (animated) and `<slot>_poster.webp` (static, reduce-motion fallback) into the project's asset root. Report both absolute paths.
4. Display it: `AppAsset(name: '<slot>', motion: AssetMotion.baked)`. Confirm in a running app (or a widget test against the real bundled files, like the Stage-3 verification) that both the animated file and the poster decode.
5. **Bundle-budget reminder:** baked motion is single-resolution by design (no 1x/2x/3x fan-out) — don't add density variants for an animated asset.

## Step 6 — Commit + docs

Commit code, then docs, per `{{doc:pr}}`:
- Tier A: the `app_asset.dart` change (+ test) is a normal feature commit.
- Tier B: `presets.py`/manifest changes + the synced the project's asset root files, committed with the feature that uses them.
- If this introduces a new preset (either tier) or a new visual pattern, add it to `{{doc:design}}`'s "Bundled Assets" section and log the decision in `{{doc:decisions}}`, per `{{doc:documentation-rules}}`.

---

## What you must never do

- Bake (Tier B) something a 2D transform could do in Flutter (Tier A) — check the split rule first, every time
- Guess which mesh objects belong to which visual element instead of checking their positions/materials in one inspection pass — an ungrouped or wrongly-grouped `motion.objects` list moves the wrong thing
- Move only part of a composition without framing on the WHOLE composition (`animate_recolor_render.py` already does this correctly by default — don't reframe on just the moving subset if you're ever touching that code)
- Skip the contact-sheet review before encoding, or encode without showing the user the sheet and its absolute path
- Ship any motion (either tier) without a working reduce-motion fallback
- Offer or fake a Lottie output from baked 3D frames
- Add density-variant (1x/2x/3x) outputs for baked motion
- Hand-place files in the project's asset root outside the `sync` stage, or hand-edit `palette.json`
- Commit `renders/`/`outputs/` intermediates
- Animate an asset the user didn't actually ask to have motion added to
- Skip `--quick` during iteration, or forget to drop it for the final promote render
- Judge a loop seam or static-region check by MAX pixel diff instead of MEAN — max alone will misreport a fine loop/region as broken
- Leave the throwaway browser-preview HTTP server running after review
