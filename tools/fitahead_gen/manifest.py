"""Runtime manifest: what the Flutter app needs to know about a generated GLB.

The app should never hardcode a joint index, a morph index, or a camera
position — everything it needs to focus on a body part and grow it is described
here, regenerated alongside the mesh so the two can never drift apart.
"""

import math

from . import morphs

#: Vertical field of view the framing distances assume, in degrees.
FOCUS_FOV = 32.0


def _distance_for(radius, fov=FOCUS_FOV):
    """Camera distance at which a sphere of `radius` is tangent to the frustum.

    sin rather than tan: the limit is the angle the sphere subtends, not the
    half-width of a plane through its centre. The Dart FocusCamera repeats this
    with the viewport's own aspect ratio; this value is the square-viewport case.
    """
    return radius / math.sin(math.radians(fov) / 2.0)


def _view(view_id, label_ko, label_en, target, radius, height, yaw=0.0,
          pitch=0.0, morph=None):
    # A part view is framed on the rest pose, but the user will see it at every
    # stage of growth. Reserve room for the group's own swell plus the overall
    # `bulk` shape, so a maxed-out biceps does not overflow its own close-up.
    if morph is not None:
        headroom = morphs.GROUPS_BY_NAME[morph].amount
        headroom += morphs.GROUPS_BY_NAME["bulk"].amount
        radius += headroom * height * 1.7
    return {
        "id": view_id,
        "labelKo": label_ko,
        "labelEn": label_en,
        "target": [round(v, 5) for v in target],
        "yawDeg": yaw,
        "pitchDeg": pitch,
        "distance": round(_distance_for(radius), 5),
        "framingRadius": round(radius, 5),
        "growthHeadroom": morph is not None,
        "morph": morph,
    }


def build_focus_views(p, rig):
    """Camera framings for the whole body and for each trainable part.

    Yaw is degrees around +Y with 0 facing the character's front (+Z); pitch is
    degrees above the horizon. Distance is metres from the target.
    """
    h = p.height
    sw = p.shoulder_half_w * h
    hip_half = p.hip_rx * h * p.leg_stance
    head_y = rig.world("Head")[1]

    def y(fraction):
        return fraction * h

    return [
        _view("full_body", "전신", "Full body",
              (0.0, y(0.50), 0.0), 0.56 * h, h),
        _view("upper_body", "상체", "Upper body",
              (0.0, y(0.70), 0.0), 0.29 * h, h),
        _view("lower_body", "하체", "Lower body",
              (0.0, y(0.30), 0.0), 0.30 * h, h),
        _view("face", "얼굴", "Face",
              (0.0, head_y, 0.0), 0.150 * h, h),

        _view("chest", "가슴", "Chest",
              (0.0, y(p.chest_y), 0.015 * h), 0.210 * h, h, morph="chest"),
        _view("back", "등", "Back",
              (0.0, y((p.chest_y + p.waist_y) * 0.5), -0.015 * h), 0.245 * h, h,
              yaw=180.0, morph="back"),
        _view("shoulders", "어깨", "Shoulders",
              (0.0, y(p.shoulder_y), 0.0), 0.235 * h, h,
              yaw=26.0, pitch=9.0, morph="shoulders"),
        _view("arms", "팔", "Arms",
              (sw * 1.02, y((p.shoulder_y + p.elbow_y) * 0.5), 0.0), 0.185 * h, h,
              yaw=42.0, morph="arms"),
        _view("abs", "복근", "Abs",
              (0.0, y(p.waist_y + 0.012), 0.015 * h), 0.200 * h, h, morph="abs"),
        _view("glutes", "엉덩이", "Glutes",
              (0.0, y(p.hip_y), -0.015 * h), 0.210 * h, h,
              yaw=172.0, pitch=-6.0, morph="glutes"),
        _view("thighs", "허벅지", "Thighs",
              (hip_half, y((p.crotch_y + p.knee_y) * 0.5), 0.0), 0.225 * h, h,
              yaw=22.0, morph="thighs"),
        _view("calves", "종아리", "Calves",
              (hip_half, y((p.knee_y + p.ankle_y) * 0.5), 0.0), 0.185 * h, h,
              yaw=22.0, morph="calves"),
    ]


def build_manifest(character, filename, mesh_names, face_texture):
    p, rig = character.p, character.rig
    return {
        "id": p.name,
        "sex": p.tags.get("sex", p.name),
        "file": filename,
        "height": round(p.height, 4),
        "upAxis": "Y",
        "frontAxis": "+Z",
        "meshes": mesh_names,
        "face": {
            "mesh": "Face",
            "material": "Face",
            "uvLayout": "disc-inscribed-in-square",
            "defaultTexture": face_texture,
            "note": "Replace this texture with the user's own drawing; "
                    "the plate's UVs fill the full 0..1 square.",
        },
        "joints": [
            {"index": b.index, "name": b.name, "parent": b.parent,
             "rest": [round(v, 5) for v in b.world]}
            for b in rig.bones
        ],
        "morphTargets": [
            {"index": i, "name": g.name, "labelKo": g.label_ko,
             "labelEn": g.label_en,
             "maxDisplacement": round(g.amount * p.height, 5),
             "isRegression": g.is_regression}
            for i, g in enumerate(morphs.GROUPS)
        ],
        "focusViews": build_focus_views(p, rig),
        "focusFovDeg": FOCUS_FOV,
        "stats": character.stats(),
    }
