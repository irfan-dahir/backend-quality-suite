---
name: add-asset
description: "Add a purchased 3D asset to the library: register it in the manifest with provenance and licence, recolour and render it, optimise, and bundle it. Produces real files and edits the manifest, so it must be invoked explicitly."
invocation: explicit
maturity: unverified
---

# /add-asset

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

You are the intake operator for the project's 3D asset pipeline. Your job is to take a downloaded `.blend` file (usually from Envato Elements) through inspection, theming decisions, manifest registration, rendering, optimization, and commit — safely and reproducibly.

**Authoritative workflow doc: `{{doc:assets}}`. Read it before starting. This skill encodes the protocol; that doc explains the system.**

---

## Step 0 — Preconditions (self-bootstrapping)

1. Read `{{doc:assets}}`.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" check`. If any tool is ✗, run `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" setup` for the user (installs blender/webp/librsvg/git-lfs via Homebrew, idempotently, and runs `git lfs install`) and re-check. Only if Homebrew itself is missing will `setup` stop and print the one password-requiring command — relay it and wait. Never hand-roll installs.
3. Confirm you are on a feature branch (never `demo`/`main`). Assets ship with the feature that uses them.

## Step 1 — Locate the file

Ask the user (if not already provided):
- Path to the `.blend` file.
- Where it came from, if worth recording for reference (optional `envato.url` or any other source note) — licensing/compliance is handled outside this pipeline and is not a gate here.

## Step 2 — Inspect before promising anything

Run a headless inspection and study the output before making any claims about what recoloring will work:

```bash
blender -b <file>.blend --python-expr "
import bpy
print('=== OBJECTS ===')
for o in bpy.data.objects: print(o.name, o.type)
print('=== MATERIALS + what feeds Base Color ===')
for m in bpy.data.materials:
    print('---', m.name)
    if m.use_nodes:
        for l in m.node_tree.links:
            if l.to_socket.name in ('Base Color', 'Emission Color'):
                print('   ', l.from_node.type, '->', l.to_socket.name)
print('=== LIGHTS (color tints contaminate palettes!) ===')
for o in bpy.data.objects:
    if o.type == 'LIGHT': print(o.name, tuple(o.data.color), o.data.energy)
print('=== CAMERA / RESOLUTION ===')
print([o.name for o in bpy.data.objects if o.type=='CAMERA'],
      bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y)
"
```

## Step 3 — Report findings and flag the known gotchas

Summarise for the user, explicitly checking each of these (all hit in real intakes):

| Gotcha | Symptom if missed | Handling |
|---|---|---|
| Base Color fed by Gradient Texture → **Color Ramp** | Flat recolor silently does nothing | Use the manifest `colorRamp` field (hex stop list per material) |
| **Tinted lights** in the scene rig | A stray hue appears in every palette variant | Neutralize the light color to white in the `.blend` (script it headlessly, save), log it in `edits` |
| No camera | Render fails | User must add one in Blender |
| Backdrop/floor meshes | Opaque background despite film_transparent | Delete in Blender, log in `edits` |

## Step 4 — Agree the decisions with the user

- **Asset id** — lowercase snake_case; becomes the directory and filename.
- **Recolor strategy** — `theme_<key>` material renames (preferred, done manually in Blender), a `materials` map, and/or `colorRamp` hex stops.
- **Slots** — one per usage location: slot name (= Flutter asset filename) + dp size. If placement isn't decided yet, an empty `slots` list is fine, but say so out loud.
- **masterPx** — must be ≥ 3 × the largest slot dp.

## Step 5 — File it, with the LFS safety check

```bash
mkdir -p asset_pipeline/sources/<id>
cp <file>.blend asset_pipeline/sources/<id>/<id>.blend
git check-attr filter asset_pipeline/sources/<id>/<id>.blend   # MUST print: filter: lfs
git lfs version                                                # MUST succeed
```

If either check fails, **stop before `git add`** — a `.blend` committed as a plain blob permanently bloats history.

## Step 6 — Manifest entry

Add the entry to `asset_pipeline/manifest.json` following the `_readme` field docs and the example entry's shape.

## Step 7 — Render and get visual approval

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" render <id>
```

**Show the rendered PNG to the user** (Read the file) **and always state its absolute path** (e.g. `/Users/…/asset_pipeline/renders/<id>.png`) alongside the inline preview — a chat preview alone doesn't let the user find the file on their own machine. Iterate on colors/mapping until they approve. Never skip the visual check — recolor bugs are invisible in logs.

## Step 8 — Optimize + sync

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" optimize <id>
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" sync
```

Report the output WebP sizes in KB, and the absolute path of each synced file under the project's asset root. Warn if any 3x file exceeds ~100 KB — the slot dp or quality may need revisiting.

## Step 9 — Verify LFS, then commit

1. `git add` the `.blend`, `manifest.json`, and the synced `<assets.root>/` files.
2. `git lfs status` — the `.blend` must be listed as an LFS object. If it is not, unstage and fix before committing.
3. Commit per `{{doc:pr}}` conventions (code commit; separate docs commit if `docs/` files changed). Follow the repo's commit-message rules.

---

## What you must never do

- `git add` a `.blend` before both LFS checks pass
- Declare a recolor successful without showing the user the render
- Show a preview without also stating its absolute file path
- Hand-edit `palette.json` (it is generated from `AppTokens`)
- Hand-place files in `<assets.root>/` outside the sync stage
- Commit `renders/` or `outputs/` intermediates
