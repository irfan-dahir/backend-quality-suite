"""Shared studio rig for generated 3D assets. Imported by gen_render.py inside
Blender. One rig for every generated asset so lighting/framing stay identical
(lighting dominates perceived quality — keep it in one place).
"""

import math

from mathutils import Vector

# gen_render.py puts this directory on sys.path before importing us, so a bare import
# matches how every other driver in this package resolves its siblings.
import driver_common

# Camera FOV is fixed; only distance changes when we auto-frame.
_DEFAULT_CAM_LOCATION = (0.0, -4.4, 1.7)

# Key (bright, front-right), fill (soft, front-left), rim (back, separates the
# subject from the transparent background). Offsets are relative to the subject
# centre, at the scale the camera sits at _DEFAULT_CAM_LOCATION — see
# _scale_rig for what happens when auto-framing moves the camera off that.
_LIGHT_RIG = [
    ("Key", (3.0, -2.5, 3.0), 900, 3.0),
    ("Fill", (-3.5, -2.0, 1.2), 350, 4.0),
    ("Rim", (0.0, 3.5, 2.8), 700, 3.0),
]

_DEFAULT_CAM_DISTANCE = Vector(_DEFAULT_CAM_LOCATION).length

# The empty every Track-To constraint points at. See setup_studio.
_AIM_NAME = "AimTarget"


def setup_studio(bpy, target, size, auto_frame=True, contact_shadow=False):
    """Add a camera + 3-point area-light rig + transparent film to the current
    scene, framed on `target` (an object, or None). Idempotent-ish: assumes an
    otherwise empty scene (gen_render.py starts from factory-empty).

    Pass auto_frame=False to skip the static single-frame framing — the
    animation path (animate_render.py) frames over the whole motion range
    instead, so the static pass would just be redundant work.

    contact_shadow=True grounds the subject on a soft shadow pool (see
    add_contact_shadow). Off by default: it changes the silhouette of every
    asset it touches, and it is wrong for anything that floats or bobs, so it
    is opted into per asset rather than applied to the whole library."""
    scene = bpy.context.scene

    # Everything aims at an empty parked on the subject's bounding-box centre,
    # NOT at the subject itself. Track-To aims at an object's ORIGIN, which is
    # wherever the generator happened to leave it — for medication_bottle_icon
    # that is 0.87 units below the bbox centre. Since _aim_camera *positions*
    # the camera from the bbox centre, aiming at the origin tilted the subject
    # off-centre in frame (the "~1px top margin vs ~28px bottom" asymmetry
    # logged against that asset). _aim_camera parks this empty on the centre it
    # computes, so position and aim finally agree.
    aim = None
    if target is not None:
        aim = bpy.data.objects.new(_AIM_NAME, None)  # an Empty; never renders
        scene.collection.objects.link(aim)

    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    cam.location = _DEFAULT_CAM_LOCATION
    scene.camera = cam
    if aim is not None:
        cam.constraints.new("TRACK_TO").target = aim

    # Three-point rig at its tuned scale; _scale_rig adjusts it if auto-framing
    # has to dolly the camera for a subject outside that range.
    for name, loc, energy, ssize in _LIGHT_RIG:
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size = energy, ssize  # white — never tint the key light
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        lo.location = loc
        if aim is not None:
            lo.constraints.new("TRACK_TO").target = aim

    r = scene.render
    r.resolution_x = r.resolution_y = size
    r.resolution_percentage = 100
    r.film_transparent = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"

    # Colour management and stamp metadata — both were unset, and both defaults are wrong
    # for brand assets. See driver_common.apply_render_determinism for the measurements.
    driver_common.apply_render_determinism(scene)

    if target is not None and auto_frame:
        frame_object(bpy, cam, target)

    if target is not None and contact_shadow:
        add_contact_shadow(bpy, target)


def add_contact_shadow(bpy, target, spread=1.6, strength=0.5):
    """Lay a soft elliptical shadow on the ground under `target`, so the subject
    reads as resting on a surface instead of floating.

    NOT a ray-traced shadow: `is_shadow_catcher` is Cycles-only and these
    renders are EEVEE, so a real catcher would mean switching engines for every
    asset. This is the same trick the flat SVGs use — a soft drop-shadow — as a
    black plane whose alpha falls off radially, sized from the subject's own
    footprint, composited over the transparent film exactly like the SVG's
    filter. See {{doc:assets}} §8.

    Call AFTER framing: the plane is deliberately not part of the camera's
    bounding-box calculation, or every asset would zoom out to fit its own
    shadow. `spread` multiplies the footprint radius (bigger = softer, wider
    pool); `strength` is peak opacity directly under the subject. The default
    spread stays near the camera's own 1.35 framing margin on purpose — a wider
    pool spills past the frame edge and crops to a straight line, which reads as
    a background wash rather than a shadow.
    """
    corners = _world_corners(target)
    if not corners:
        return None

    xs, ys, zs = zip(*corners)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    footprint = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    if footprint < 1e-6:
        return None

    bpy.ops.mesh.primitive_plane_add(
        size=footprint * 2 * spread,
        # A hair below the lowest point: coplanar with the subject's base
        # z-fights, and the flicker only shows up in the render.
        location=(cx, cy, min(zs) - footprint * 0.002),
    )
    plane = bpy.context.active_object
    plane.name = "ContactShadow"

    mat = bpy.data.materials.new("ContactShadow")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    # Black albedo, no specular — the rig's lights can then never tint the
    # shadow grey or lay a highlight across it. It stays pure alpha.
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    for spec in ("Specular IOR Level", "Specular"):
        if spec in bsdf.inputs:
            bsdf.inputs[spec].default_value = 0.0
            break

    coord = nt.nodes.new("ShaderNodeTexCoord")
    # Object coords are centred on the plane's origin; Generated coords run 0..1
    # from a CORNER, which puts the gradient's centre at the plane's edge and
    # leaves a hard square visible in the render. Scaling by 1/half_size then
    # puts |p| = 1 exactly at the rim.
    half_size = footprint * spread
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / half_size,) * 3

    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    # Spherical Fac = 1 - |p|: 1 at the centre, 0 at the rim, and already 0
    # before the square corners (|p| = 1.41 there), so the plane can never show
    # its own silhouette. Darkest directly under the subject, feathering out.
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 0.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (strength,) * 3 + (1.0,)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Alpha"])

    # Alpha blending, across the EEVEE-Next rename and the legacy name.
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    # A receiver, never a caster — the plane must not shadow itself.
    if hasattr(plane, "visible_shadow"):
        plane.visible_shadow = False

    plane.data.materials.append(mat)
    return plane


def _world_corners(target):
    """World-space bounding-box corners of `target` and all its descendants."""
    objs = [target] + list(getattr(target, "children_recursive", []))
    return [obj.matrix_world @ Vector(c) for obj in objs for c in obj.bound_box]


def _constraining_half_angle(cam, scene):
    """The camera's true half-FOV for the render's actual aspect ratio.

    `camera.data.angle_x`/`angle_y` report the RAW sensor-based angles and do
    NOT reflect how `sensor_fit='AUTO'` actually reprojects for the current
    render resolution — for a square render on this rig's non-square (36x24mm)
    sensor, the effective FOV that lands in the final pixels differs from
    both nominal angles (discovered empirically: a test sphere's measured
    pixel extent matched neither angle_x- nor angle_y-based predictions,
    off by ~1.5x). `camera.data.view_frame(scene)` returns the actual frame
    corners Blender uses for this scene's resolution/aspect/sensor_fit, so
    deriving the half-angle from THAT is correct regardless of sensor_fit
    convention. Returns the narrower (constraining) of the two axes.
    """
    frame = cam.data.view_frame(scene=scene)
    xs = [abs(p.x) for p in frame]
    ys = [abs(p.y) for p in frame]
    zs = [abs(p.z) for p in frame]
    half_w, half_h, depth = max(xs), max(ys), max(zs)
    half_angle_x = math.atan(half_w / depth)
    half_angle_y = math.atan(half_h / depth)
    return min(half_angle_x, half_angle_y)


def _scale_rig(scene, center, scale):
    """Re-place the 3-point rig for a subject the camera had to dolly for, and
    re-centre it on the subject rather than the world origin.

    The rig used to sit at fixed world positions while only the camera moved to
    fit the subject. A subject much larger than the tuned ~1-2 unit range then
    rendered correctly framed but essentially unlit, because the lights ended up
    inside or just under its surface; a much smaller one washed out. See
    {{doc:assets}} §8.

    Three things scale together to keep the look identical at any subject size:
    offsets linearly (the rig keeps its shape and the subject stays inside the
    lit volume), area size linearly (constant softness *relative to the
    subject*, so highlights don't harden as it grows), and energy with the
    square of distance (inverse-square falloff, so exposure is unchanged).
    """
    for name, offset, energy, ssize in _LIGHT_RIG:
        light = scene.objects.get(name)
        if light is None:
            continue
        light.location = center + Vector(offset) * scale
        light.data.energy = energy * scale * scale
        light.data.size = ssize * scale


def _aim_camera(cam, corners, margin, scene):
    """Dolly `cam` along its existing viewing direction so `corners` fill the
    frame with `margin` headroom, and widen clip_end to cover the new distance.

    Discovered the hard way: dollying back to fit a larger bounding box can
    push the camera past the far clip plane, which clips the whole subject with
    NO error or warning — just a blank PNG. See {{doc:assets}} §8.
    """
    if not corners:
        return

    xs, ys, zs = zip(*corners)
    center = Vector(
        ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    )
    radius = max((c - center).length for c in corners)
    if radius < 1e-6:
        return

    # Aim and position now share one centre. For a MOVING subject this is the
    # centre of the whole swept range, so the camera holds still through the
    # animation instead of panning to chase the subject.
    aim = scene.objects.get(_AIM_NAME)
    if aim is not None:
        aim.location = center

    direction = cam.location - center
    if direction.length < 1e-6:
        direction = Vector((0, -1, 0.4))
    direction.normalize()

    half_angle = _constraining_half_angle(cam, scene)
    distance = (radius / math.sin(half_angle)) * margin
    cam.location = center + direction * distance

    if not cam.constraints:
        look = (center - cam.location).normalized()
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()

    cam.data.clip_end = max(cam.data.clip_end, distance + radius * 2)

    # The camera's dolly ratio IS the rig's scale factor — no second magic
    # constant, and a subject that needed no dolly leaves the rig untouched.
    _scale_rig(scene, center, distance / _DEFAULT_CAM_DISTANCE)


def frame_object(bpy, cam, target, margin=1.35):
    """Dolly the camera so `target` (and all its children, recursively) fills
    the frame with `margin` headroom. For a STATIC subject."""
    bpy.context.view_layer.update()
    _aim_camera(cam, _world_corners(target), margin, bpy.context.scene)


def frame_object_over_range(
    bpy, cam, target, frame_start, frame_end, samples=16, margin=1.35
):
    """Frame a MOVING subject: sample `target`'s world bounding box at several
    frames across [frame_start, frame_end], union all the corners, and frame on
    that. A subject that grows/drifts during the animation is thus contained for
    the WHOLE motion, not just frame 1 — otherwise later frames clip, or (worse)
    fall past clip_end and render blank. Works for any preset without trusting
    its declared extent, since it measures the real bounding box.

    Leaves the scene on `frame_start` when done. Thin wrapper over
    frame_objects_over_range for the common single-target case."""
    frame_objects_over_range(bpy, cam, [target], frame_start, frame_end, samples, margin)


def frame_objects_over_range(
    bpy, cam, targets, frame_start, frame_end, samples=16, margin=1.35
):
    """Like frame_object_over_range, but for MULTIPLE independent objects —
    e.g. when only some of a composition moves (a subset parented to a motion
    pivot) while the rest stays static. Framing must still cover the WHOLE
    composition, not just the moving part, or the camera will crop out
    whatever wasn't included. Pass every top-level object in the composition
    here (moving and static alike); each is sampled at its actual world
    position per frame, so static ones contribute a fixed footprint and moving
    ones contribute their full swept range.

    Leaves the scene on `frame_start` when done."""
    scene = bpy.context.scene
    corners = []
    n = max(2, samples)
    for i in range(n):
        frame = frame_start + round((frame_end - frame_start) * i / (n - 1))
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for target in targets:
            corners.extend(_world_corners(target))
    scene.frame_set(frame_start)
    bpy.context.view_layer.update()
    _aim_camera(cam, corners, margin, scene)
