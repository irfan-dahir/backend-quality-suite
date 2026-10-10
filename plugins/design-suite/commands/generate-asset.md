---
name: generate-asset
description: "Generate a new asset from a script we author rather than a purchased source — SVG, Blender, or the shapes icon-as-data kind — then render, optimise and bundle it. Produces real files, so it must be invoked explicitly."
invocation: explicit
maturity: unverified
---

# /generate-asset

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

You generate a brand-new asset from a text prompt — no purchase — by authoring a small generator (an SVG for 2D, or a Blender `bpy` script for 3D), rendering variants, letting the user pick, and promoting the winner into the pipeline. Everything runs locally via headless Blender / rsvg. Full system: `{{doc:assets}}`.

**The generator source (SVG file or `gen.py`) is the source of truth — small, diffable, no Git LFS.** This is the key difference from `/add-asset` (purchased `.blend` binaries).

---

## Step 0 — Preconditions (self-bootstrapping)

Run `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" check`. If any tool is ✗, run `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" setup` for the user (it installs blender/webp/librsvg/git-lfs via Homebrew, idempotently) and re-check. Only if Homebrew itself is missing will `setup` stop and print the one command that needs the user's password — relay it and wait. Never hand-roll installs.

Confirm you're on a feature branch, not `demo`/`main`.

## Step 1 — Interpret the prompt → pick a modality

Decide with the user (state your recommendation, it's usually clear from the prompt):

| Prompt shape | Modality | `generator.kind` | Source |
|---|---|---|---|
| Flat/UI icon, badge, pictogram, simple illustration | **2D** | `svg` | `generated/<id>/<id>.svg` |
| Glossy/tactile 3D icon, skeuomorphic object, blob/capsule/orb | **3D** | `blender` | `generated/<id>/gen.py` |
| Icon that should exist BOTH as a flat 2D asset AND a layered "Apple-icon" skeuomorphic 3D version, from one source | **Both** | `shapes` | `generated/<id>/shapes.py` (two manifest entries share it via `source`, one per `generator.style`: `flat` / `skeuomorphic`) |

Honesty rule: this pipeline excels at abstract/organic/geometric glossy forms and clean vector icons. It is **not** good at detailed figurative subjects (a realistic anatomical heart, a human face). If the prompt needs that, say so and steer to `/add-asset` (buy it from Envato) instead of producing something off-brand.

The `shapes` modality is a prototype (validated on one icon so far, not battle-tested broadly) — see `{{doc:assets}}` §10 for the shape-spec format, the coordinate-mapping gotchas already found (rotation axis, stroke geometry, gradient type per shape), and the honestly-stated limitations (pastel colors vs. the flat version, no ground contact shadow yet). Don't oversell it as production-hardened; it's real and working, but young.

Motion/animation is built as a separate step — see `/animate-asset` and `{{doc:assets}}` §9. This skill produces the still; if the user wants it to move, point them at `/animate-asset` once it's promoted rather than folding motion authoring in here.

## Step 1b — Optional: match a reference image

The user may hand you an existing image (a competitor icon, a purchased asset render, a screenshot) and ask for something similar, or something different that shares its look. You do this with your own vision, not an external API:

1. **Read the reference image** (the `Read` tool renders it for you).
2. **Write down a style spec in plain English before writing any code** — do not skip straight to geometry. Cover at minimum: **form** (organic/geometric/faceted, silhouette complexity), **material** (glossy/matte/metallic/iridescent, roughness impression, coat/clearcoat), **palette** (name the actual hues you see, and whether transitions are clean gradients or patchy/organic), **lighting** (soft studio vs. dramatic, colored bounce or neutral), **composition** (single mass vs. multiple elements, proportions).
3. **Translate the spec into concrete parameters** for the new generator — literal hex stops for a Color Ramp, a `Roughness`/`Coat Weight`/`Metallic` value per material property named in the spec, a primitive/metaball choice matching the form. Comment the `gen.py` with the extraction so the reasoning is reviewable, not just the output.
4. If the user wants the **same subject**, build close geometry. If they want **something different in the same aesthetic** (e.g. "a ring like this blob"), the shape can and should differ — what must transfer is the material/palette/lighting/composition language, proven by the 2026-07-13 synthetic test (a blob's duotone-glossy-organic style successfully reapplied to an unrelated torus+sphere).
5. Show the reference and the new render side by side, **state the new render's absolute path**, and **name any gap honestly** (e.g. "the reference's color transitions are patchier from its metaball surface; this primitive's gradient is smoother") rather than overselling the match.

This mode composes with Step 4's normal render → preview → iterate loop — a style spec is just a richer starting point for the generator, not a different pipeline.

## Step 2 — Author the generator

Colors must come from the palette (`asset_pipeline/palette.json`, generated from `AppTokens`) unless the user explicitly wants a test/other palette — say which you're using.

**2D (`svg`):** author `generated/<id>/<id>.svg`, `viewBox="0 0 512 512"`. Use gradients + a soft drop shadow for the skeuomorphic feel (see the badge produced in the 2026-07-13 synthetic test as reference). You can inspect it live — write it and read the render.

**3D (`blender`):** author `generated/<id>/gen.py` defining `build(ctx)` (contract in `scripts/gen_render.py`): build geometry + a coated glossy material, color via `ctx.color("<paletteKey>")` or `ctx.hex("#...")`, return the subject object. The shared studio rig (camera + 3-point lights + transparent film) is applied automatically — do not add your own lights/camera. Use `ctx.rng` (seeded) for any per-variant jitter.

## Step 3 — Manifest entries (one per variant)

Give each variant its own entry (or share one source via `source` + differing `generator.params`, e.g. `{"seed": 1}`, `{"seed": 2}` for 3D). `origin: "generated"`, no `envato`/license block, a `_comment` recording the prompt, `render.masterPx` (512–1024 for icons), and `slots` (empty until placement is decided). See the manifest `_readme`.

## Step 4 — Render variants → preview → iterate

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" gen --all   # or a single id
```

**Read each render PNG and show the user, and always state its absolute path** (e.g. `/Users/…/asset_pipeline/renders/<id>.png`) right alongside the inline preview — the chat preview is not a substitute for the user being able to find the file themselves in Finder/Preview. Iterate on the generator until they approve — this loop is cheap (svg is instant; a 512px blender render is ~5–8s). Do not proceed on an unseen result.

**Every asset is scratch until promoted.** Renders/outputs get deleted at Step 5's cleanup once the user has picked and the pipeline has moved on to the real slots/optimize/sync — say so up front so "where did that preview go?" doesn't come as a surprise later. If the user wants to keep looking at a specific render past that point, say so explicitly rather than silently deleting it.

## Step 5 — Promote the winner

Once the user picks a variant:
1. Drop the losing variants' manifest entries and source dirs.
2. Give the winner its real `slots` (name = Flutter asset filename, dp = layout size; `masterPx ≥ 3 × largest dp`).
3. `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" all <id>` (produce → optimize → sync). Report WebP sizes **and the absolute path** of each synced file under the project's asset root.
4. Commit the generator source + manifest + synced the project's asset root files together with the feature that uses them, per `{{doc:pr}}`. Generated sources are **not** LFS (they're text) — no `.blend` LFS dance needed.

Then update `{{doc:design}}` / `{{doc:decisions}}` if this introduces a new visual pattern, per `{{doc:documentation-rules}}`.

---

## What you must never do

- Produce a final asset without showing the user the render
- Show a preview without also stating its absolute file path — an inline chat preview is not a substitute for the user being able to locate the file on their own machine
- Add lights/cameras inside a `gen.py` (the studio rig owns those)
- Hand-edit `palette.json`, or hand-place files in the project's asset root
- Author motion inside this skill — that's `/animate-asset`'s job
- Force an off-brand result when the prompt really needs a purchased asset — recommend `/add-asset` instead
- Skip straight to code on a reference-image request without first writing the style spec in words
- Claim a style match without showing the reference and the result side by side, and naming any real gap
