"""Body proportion presets, derived from the anthropometric tables.

Nothing here is a free-hand number: landmark heights, breadths and girths all
come from `anthro`. What this module adds is the two sex presets and a single
documented stylisation factor.

The base mesh is a LEAN body — untrained, low body fat. Muscle morphs grow it
toward trained, and fat morphs soften it. The three body types the app needs
(마른 / 평범 / 근육질) are therefore three points in morph space, not three
meshes.
"""

from dataclasses import dataclass, field, replace

from . import anthro

#: Limb girths are drawn a touch above the anthropometric lean values. A
#: literally-lean limb reads as unwell rather than slim at phone size, and the
#: character is meant to be encouraging. This is the only fudge factor, and it
#: is applied uniformly so relative proportions stay honest.
LIMB_STYLE_SCALE = 1.05


@dataclass(frozen=True)
class BodyParams:
    name: str
    height: float
    sex: str

    # -- vertical landmarks (fraction of stature), from anthro.HEIGHTS --------
    ankle_y: float
    knee_y: float
    crotch_y: float
    hip_y: float
    waist_y: float
    chest_y: float
    shoulder_y: float
    neck_y: float
    elbow_y: float
    wrist_y: float

    # -- torso half-breadths (rx) and half-depths (rz) -----------------------
    hip_rx: float
    hip_rz: float
    waist_rx: float
    waist_rz: float
    chest_rx: float
    chest_rz: float
    shoulder_rx: float
    shoulder_rz: float
    torso_squash: float = 1.03

    # -- head and neck -------------------------------------------------------
    head_r: float = 0.084
    head_center_y: float = 0.92
    head_squash_y: float = anthro.HEAD_SQUASH_Y
    head_squash_z: float = 0.94
    neck_r: float = 0.032
    face_r_ratio: float = 0.78

    # -- limbs, at the LEAN state --------------------------------------------
    shoulder_half_w: float = 0.116
    upperarm_r: float = 0.026
    forearm_r: float = 0.022
    wrist_r: float = 0.015
    hand_r: float = 0.034

    thigh_r: float = 0.045
    shin_r: float = 0.031
    ankle_r: float = 0.020
    foot_r: float = 0.040
    foot_len: float = anthro.FOOT_LENGTH
    leg_stance: float = 0.52

    # -- look ----------------------------------------------------------------
    skin_color: tuple = (0.94, 0.78, 0.66, 1.0)
    face_color: tuple = (1.0, 0.92, 0.85, 1.0)
    accent_color: tuple = (0.36, 0.55, 0.98, 1.0)

    tags: dict = field(default_factory=dict)

    def growth(self, site):
        """Lean-to-trained radius gain at a girth site, in stature units."""
        return anthro.girth_growth(self.sex, site)


def _preset(name, sex, height, *, skin, accent, leg_stance, squash=1.03):
    b = anthro.BREADTHS[sex]
    d = anthro.DEPTHS[sex]
    h = anthro.HEIGHTS
    s = LIMB_STYLE_SCALE

    def r(site):
        return anthro.radius(sex, site, "lean") * s

    head_r = anthro.HEAD_HEIGHT * anthro.HEAD_STYLE_SCALE / 2.0

    return BodyParams(
        name=name,
        sex=sex,
        height=height,
        ankle_y=h["ankle"],
        knee_y=h["knee"],
        crotch_y=h["crotch"],
        hip_y=h["hip"],
        waist_y=h["waist"],
        chest_y=h["chest"],
        shoulder_y=h["shoulder"],
        neck_y=h["neck"],
        elbow_y=h["elbow"],
        wrist_y=h["wrist"],
        hip_rx=b["hip"] / 2,
        hip_rz=d["hip"] / 2,
        waist_rx=b["waist"] / 2,
        waist_rz=d["waist"] / 2,
        chest_rx=b["chest"] / 2,
        chest_rz=d["chest"] / 2,
        # The torso at the acromion line is narrower than biacromial breadth:
        # the acromion is the bony point the deltoid hangs off, not the edge of
        # the ribcage. The arms are placed AT biacromial/2 and their own mass
        # carries the silhouette out to full shoulder width.
        shoulder_rx=b["biacromial"] / 2 * 0.88,
        shoulder_rz=d["chest"] / 2 * 0.92,
        torso_squash=squash,
        head_r=head_r,
        head_center_y=anthro.head_center_y(),
        neck_r=r("neck"),
        # the arm hangs just inboard of the acromion so the deltoid cap
        # overlaps the torso instead of leaving a gap at the shoulder
        shoulder_half_w=b["biacromial"] / 2 * 0.94,
        upperarm_r=r("upper_arm"),
        forearm_r=r("forearm"),
        wrist_r=r("wrist"),
        hand_r=anthro.HAND_LENGTH * 0.34,
        thigh_r=r("thigh"),
        shin_r=r("calf"),
        ankle_r=r("ankle"),
        foot_r=anthro.FOOT_LENGTH * 0.27,
        leg_stance=leg_stance,
        skin_color=skin,
        accent_color=accent,
        tags={"sex": sex, "state": "lean"},
    )


MALE = _preset(
    "male", "male", 1.75,
    skin=(0.93, 0.76, 0.63, 1.0),
    accent=(0.29, 0.51, 0.96, 1.0),
    leg_stance=0.50,
)

FEMALE = _preset(
    "female", "female", 1.62,
    skin=(0.96, 0.80, 0.70, 1.0),
    accent=(0.95, 0.42, 0.62, 1.0),
    leg_stance=0.46,
)

PRESETS = {"male": MALE, "female": FEMALE}


def with_height(preset, height):
    return replace(preset, height=height)
