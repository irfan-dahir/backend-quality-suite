"""Portable baked-motion (Tier-B) preset registry. Runs INSIDE Blender.

A baked preset lays keyframes on a MOTION PIVOT — an Empty placed at the
subject's bounding-box centre, with the subject parented to it. Presets only
ever transform the pivot, so:
  - the subject keeps its own build-time orientation/position, and
  - rotation/scale happen about the visual centre, not the object origin.

This file is deliberately PROJECT-AGNOSTIC: no Flutter, no consumer-project specifics,
no palette/theming. It only knows Blender. That keeps it reusable across other
projects (web/React/Swift) that bake the same motions — the split rule lives in
{{doc:assets}}, the consuming/adapter layer lives elsewhere.

Preset contract:
    fn(bpy, pivot, frame_start, frame_end, params) -> extent
where `extent` = {"scale_max": float, "drift": float} declares how far past the
rest pose the motion travels (a scale multiplier and a world-unit translation).
It's advisory only — animate_render frames the camera by SAMPLING the real
bounding box across the range, so a preset that under-declares its extent still
frames correctly; the value is kept for documentation/budgeting.

Seamless loops: each preset keyframes a FULL cycle across [frame_start ..
frame_end + 1] so that frame_end + 1 lands back on the frame_start pose. The
renderer outputs [frame_start .. frame_end] (not the duplicate endpoint), so
the WebP loops without a hitch.
"""

import math

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def _default_interp(bpy, mode):
    """Set the interpolation new keyframes are created with. Done via the user
    preference (not by walking action.fcurves afterwards) because Blender's
    slotted-actions API (4.4+/5.x) removed the flat `action.fcurves` accessor —
    setting the pref up front is version-robust and needs no fcurve traversal."""
    bpy.context.preferences.edit.keyframe_new_interpolation_type = mode


def turntable(bpy, pivot, frame_start, frame_end, params):
    """Full-revolution spin about an axis (default vertical Z). The canonical
    Tier-B motion — it reveals new 3D angles, so it cannot be faked by a 2D
    transform of a still. Rotation is framing-invariant (the bounding sphere is
    unchanged by rotation), so no extra framing pad is needed."""
    axis = params.get("axis", "Z").upper()
    turns = params.get("turns", 1)
    idx = _AXIS_INDEX.get(axis, 2)

    _default_interp(bpy, "LINEAR")  # constant angular velocity
    pivot.rotation_euler[idx] = 0.0
    pivot.keyframe_insert("rotation_euler", index=idx, frame=frame_start)
    pivot.rotation_euler[idx] = 2.0 * math.pi * turns
    pivot.keyframe_insert("rotation_euler", index=idx, frame=frame_end + 1)

    return {"scale_max": 1.0, "drift": 0.0}


def idle_float(bpy, pivot, frame_start, frame_end, params):
    """Gentle vertical bob — an ambient "alive" idle. Silhouette-changing only
    in position, but baked here so the camera stays put while the subject moves
    within frame (a Flutter-native translate could also do this; baking is used
    when it's combined with, e.g., a subtle turn). One sine cycle."""
    amplitude = params.get("amplitude", 0.12)
    base_z = pivot.location.z

    _default_interp(bpy, "BEZIER")  # smooth ease through each turning point
    # z = base + A*sin(2*pi*t), sampled at t = 0, .25, .5, .75, 1 across the
    # cycle: {0, +A, 0, -A, 0} — a smooth up/down/return.
    span = (frame_end + 1) - frame_start
    for i, factor in enumerate((0.0, 1.0, 0.0, -1.0, 0.0)):
        frame = frame_start + round(span * i / 4)
        pivot.location.z = base_z + amplitude * factor
        pivot.keyframe_insert("location", index=2, frame=frame)

    pivot.location.z = base_z
    return {"scale_max": 1.0, "drift": amplitude}


def pulse(bpy, pivot, frame_start, frame_end, params):
    """Uniform scale breathe (1 -> 1+amount -> 1). Emphasis/attention motion."""
    amount = params.get("amount", 0.08)
    peak = 1.0 + amount

    _default_interp(bpy, "BEZIER")  # smooth ease at the peak
    span = (frame_end + 1) - frame_start
    for i, s in enumerate((1.0, peak, 1.0)):
        frame = frame_start + round(span * i / 2)
        pivot.scale = (s, s, s)
        pivot.keyframe_insert("scale", frame=frame)

    pivot.scale = (1.0, 1.0, 1.0)
    return {"scale_max": peak, "drift": 0.0}


# Registry — name -> preset fn. animate_render looks presets up here by the
# manifest's motion.preset value.
PRESETS = {
    "turntable": turntable,
    "idle_float": idle_float,
    "pulse": pulse,
}


def get(name):
    fn = PRESETS.get(name)
    if fn is None:
        raise SystemExit(
            f"[animate] unknown motion preset '{name}' — known: "
            f"{', '.join(sorted(PRESETS))}"
        )
    return fn
