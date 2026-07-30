"""Runtime manifest: what the Flutter app needs to know about a generated GLB.

The app should never hardcode a joint index, a morph index, or a camera
position — everything it needs to focus on a body part, grow it, or pick a
starting body type is described here, regenerated alongside the mesh so the two
can never drift apart.
"""

import math

from . import anthro
from .rig import HUMANOID_BONES

#: Vertical field of view the framing distances assume, in degrees.
FOCUS_FOV = 32.0


def _distance_for(radius, fov=FOCUS_FOV):
    """Camera distance at which a sphere of `radius` is tangent to the frustum.

    sin rather than tan: the limit is the angle the sphere subtends, not the
    half-width of a plane through its centre. The Dart FocusCamera repeats this
    with the viewport's own aspect ratio; this value is the square-viewport case.
    """
    return radius / math.sin(math.radians(fov) / 2.0)


def _view(view_id, label_ko, label_en, target, radius, height, groups,
          yaw=0.0, pitch=0.0, morph=None):
    # A part view is framed on the rest pose, but the user will see it at every
    # stage of growth. Reserve room for the group's own swell plus the overall
    # lean-mass shape, so a maxed-out biceps does not overflow its own close-up.
    if morph is not None:
        headroom = groups[morph].amount + groups["bulk"].amount
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
        "morph": morph,
    }


def build_focus_views(p, rig, groups):
    """Camera framings for the whole body and for each trainable muscle.

    Yaw is degrees around +Y with 0 facing the character's front (+Z); pitch is
    degrees above the horizon. Distance is metres from the target.

    Angles are chosen so the muscle in question faces the camera: the triceps
    sits on the back of the arm, so its view is behind the shoulder line, and the
    hamstrings view is behind the thigh. A single front-on shot per body part
    would hide half of these.
    """
    h = p.height
    sw = p.shoulder_half_w * h
    head_y = rig.world("Head")[1]

    def y(fraction):
        return fraction * h

    def midpoint(a, b):
        """Midpoint of a bone, taken from the rig.

        Derived rather than computed from landmark heights, because the arms are
        abducted: in an A-pose the middle of the humerus is neither at
        `(shoulder_y + elbow_y) / 2` nor on the body's centre line.
        """
        pa, pb = rig.world(a), rig.world(b)
        return tuple((pa[i] + pb[i]) * 0.5 for i in range(3))

    upperarm_mid = midpoint("UpperArm_L", "Forearm_L")
    forearm_mid = midpoint("Forearm_L", "Hand_L")
    thigh_mid = midpoint("Thigh_L", "Shin_L")
    shin_mid = midpoint("Shin_L", "Foot_L")

    def view(*args, **kwargs):
        return _view(*args, height=h, groups=groups, **kwargs)

    return [
        view("full_body", "전신", "Full body", (0.0, y(0.50), 0.0), 0.56 * h),
        view("upper_body", "상체", "Upper body", (0.0, y(0.70), 0.0), 0.30 * h),
        view("lower_body", "하체", "Lower body", (0.0, y(0.30), 0.0), 0.30 * h),
        view("face", "얼굴", "Face", (0.0, head_y, 0.0), 0.150 * h),

        # -- upper body -----------------------------------------------------
        view("traps", "승모근", "Traps",
             (0.0, y(p.shoulder_y + 0.005), 0.0), 0.215 * h,
             yaw=18.0, pitch=26.0, morph="traps"),
        view("delts", "어깨", "Shoulders",
             (sw * 0.72, y(p.shoulder_y), 0.0), 0.200 * h,
             yaw=34.0, pitch=12.0, morph="delts"),
        view("pecs", "가슴", "Chest",
             (0.0, y(p.chest_y + 0.015), 0.018 * h), 0.205 * h, morph="pecs"),
        view("lats", "등", "Back",
             (0.0, y((p.chest_y + p.waist_y) * 0.5), -0.018 * h), 0.240 * h,
             yaw=180.0, morph="lats"),

        # -- arms -----------------------------------------------------------
        view("biceps", "이두", "Biceps",
             upperarm_mid, 0.150 * h, yaw=30.0, morph="biceps"),
        view("triceps", "삼두", "Triceps",
             upperarm_mid, 0.150 * h, yaw=150.0, morph="triceps"),
        view("forearms", "전완", "Forearms",
             forearm_mid, 0.130 * h, yaw=30.0, morph="forearms"),

        # -- core -----------------------------------------------------------
        view("abs", "복근", "Abs",
             (0.0, y((p.crotch_y + p.chest_y) * 0.5), 0.018 * h), 0.185 * h,
             morph="abs"),
        view("obliques", "옆구리", "Obliques",
             (0.0, y(p.waist_y - 0.01), 0.0), 0.190 * h,
             yaw=68.0, morph="obliques"),

        # -- lower body -----------------------------------------------------
        view("glutes", "엉덩이", "Glutes",
             (0.0, y(p.hip_y - 0.005), -0.018 * h), 0.205 * h,
             yaw=172.0, pitch=-8.0, morph="glutes"),
        view("quads", "허벅지 앞", "Quads",
             thigh_mid, 0.195 * h, yaw=26.0, morph="quads"),
        view("hams", "허벅지 뒤", "Hamstrings",
             thigh_mid, 0.195 * h, yaw=154.0, morph="hams"),
        view("calves", "종아리", "Calves",
             shin_mid, 0.155 * h, yaw=154.0, morph="calves"),
    ]


#: How much high body fat hides abdominal definition.
#:
#: Visible abs are as much a body-composition fact as a training one — the
#: rectus abdominis can be well developed and completely invisible under a layer
#: of subcutaneous fat. Without this the character would show a six-pack on an
#: overweight body, which every user would read as wrong.
ABS_FAT_OCCLUSION = 0.90


def build_archetypes(p, groups):
    """Named starting body types, as explicit morph weights.

    These are the answer to "can it do 마른 / 평범 / 근육질": all of them are one
    mesh at different points in morph space. Nothing here is a separate asset.

    `muscle` is applied to every trainable group; `fat` is split between the two
    deposition patterns using the sex-typical ratio from `anthro.FAT_SPLIT`.
    """
    android_share, gynoid_share = anthro.FAT_SPLIT[p.sex]
    muscle_names = [g.name for g in groups.values() if g.kind == "muscle"]

    def weights(muscle, fat):
        w = {name: round(muscle, 4) for name in muscle_names}
        # abs are muscle you can only see at low body fat
        w["abs"] = round(muscle * (1.0 - fat * ABS_FAT_OCCLUSION), 4)
        w["bulk"] = round(muscle * 0.85, 4)
        w["fat_android"] = round(fat * android_share, 4)
        w["fat_gynoid"] = round(fat * gynoid_share, 4)
        return w

    spec = [
        ("lean", "마른 체형", "Lean", 0.00, 0.08,
         "훈련 이력이 없고 체지방이 낮은 몸. 기본 메시 그대로입니다."),
        ("average", "평범한 체형", "Average", 0.30, 0.42,
         "일반 성인 평균. 인체측정 평균 둘레에 해당합니다."),
        ("athletic", "운동하는 체형", "Athletic", 0.62, 0.24,
         "꾸준히 운동한 몸. 복근이 드러나기 시작합니다."),
        ("muscular", "근육질 체형", "Muscular", 0.92, 0.16,
         "훈련량이 많은 몸. 인체측정 trained 둘레에 해당합니다."),
        ("overweight", "과체중 체형", "Overweight", 0.22, 0.86,
         "체지방이 높은 몸. 근육이 있어도 복근은 보이지 않습니다."),
    ]
    return [
        {
            "id": key,
            "labelKo": ko,
            "labelEn": en,
            "muscleLevel": muscle,
            "fatLevel": fat,
            "noteKo": note,
            "weights": weights(muscle, fat),
        }
        for key, ko, en, muscle, fat, note in spec
    ]


def build_manifest(character, filename, mesh_names, face_texture):
    p, rig = character.p, character.rig
    groups = {g.name: g for g in character.morph_groups}

    return {
        "id": p.name,
        "sex": p.sex,
        "file": filename,
        "height": round(p.height, 4),
        "upAxis": "Y",
        "frontAxis": "+Z",
        "meshes": mesh_names,
        "baseState": "lean",
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
             "rest": [round(v, 5) for v in b.world],
             "humanoid": HUMANOID_BONES.get(b.name)}
            for b in rig.bones
        ],
        "humanoidBones": {
            humanoid: node for node, humanoid in HUMANOID_BONES.items()
        },
        "morphTargets": [
            {"index": i, "name": g.name, "kind": g.kind,
             "labelKo": g.label_ko, "labelEn": g.label_en,
             "muscleKo": g.muscle_ko, "muscleEn": g.muscle_en,
             "maxDisplacement": round(g.amount * p.height, 5)}
            for i, g in enumerate(character.morph_groups)
        ],
        "archetypes": build_archetypes(p, groups),
        "absFatOcclusion": ABS_FAT_OCCLUSION,
        "fatSplit": {"android": anthro.FAT_SPLIT[p.sex][0],
                     "gynoid": anthro.FAT_SPLIT[p.sex][1]},
        "focusViews": build_focus_views(p, rig, groups),
        "focusFovDeg": FOCUS_FOV,
        "stats": character.stats(),
    }
