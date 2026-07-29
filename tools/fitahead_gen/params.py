"""Body proportion presets.

Every measurement is a fraction of total height, so a preset stays coherent when
the height changes. Landmark heights are shared between the sexes; the silhouette
difference comes from the widths and limb radii.
"""

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class BodyParams:
    name: str
    height: float

    # -- vertical landmarks, as a fraction of height -----------------------
    ankle_y: float = 0.045
    knee_y: float = 0.278
    crotch_y: float = 0.480
    hip_y: float = 0.545
    waist_y: float = 0.640
    chest_y: float = 0.752
    shoulder_y: float = 0.812
    neck_y: float = 0.845
    elbow_y: float = 0.622
    wrist_y: float = 0.452

    # -- torso widths (rx = side to side, rz = front to back) --------------
    hip_rx: float = 0.088
    hip_rz: float = 0.062
    waist_rx: float = 0.078
    waist_rz: float = 0.057
    chest_rx: float = 0.098
    chest_rz: float = 0.069
    shoulder_rx: float = 0.104
    shoulder_rz: float = 0.062
    torso_squash: float = 1.03  # >1 rounds the cross-section toward a rectangle

    # -- head and neck -----------------------------------------------------
    head_r: float = 0.084
    head_squash_z: float = 0.94
    neck_r: float = 0.032
    face_r_ratio: float = 0.78  # face plate radius, as a fraction of head_r

    # -- limbs -------------------------------------------------------------
    shoulder_half_w: float = 0.116
    upperarm_r: float = 0.036
    forearm_r: float = 0.030
    hand_r: float = 0.036
    biceps_bulge: float = 0.006

    thigh_r: float = 0.058
    shin_r: float = 0.042
    foot_r: float = 0.042
    foot_len: float = 0.108
    calf_bulge: float = 0.007
    leg_stance: float = 0.56  # hip half-width multiplier: how far apart the legs are

    # -- look --------------------------------------------------------------
    skin_color: tuple = (0.94, 0.78, 0.66, 1.0)
    face_color: tuple = (1.0, 0.92, 0.85, 1.0)
    accent_color: tuple = (0.36, 0.55, 0.98, 1.0)

    tags: dict = field(default_factory=dict)

    def abs_y(self, fraction):
        """Convert a height fraction into world metres."""
        return fraction * self.height

    def scaled(self, value):
        return value * self.height


MALE = BodyParams(
    name="male",
    height=1.75,
    hip_rx=0.098,
    hip_rz=0.068,
    waist_rx=0.076,
    waist_rz=0.055,
    chest_rx=0.100,
    chest_rz=0.070,
    shoulder_rx=0.108,
    shoulder_rz=0.063,
    shoulder_half_w=0.120,
    upperarm_r=0.037,
    forearm_r=0.031,
    hand_r=0.037,
    thigh_r=0.053,
    shin_r=0.043,
    biceps_bulge=0.007,
    calf_bulge=0.008,
    skin_color=(0.93, 0.76, 0.63, 1.0),
    accent_color=(0.29, 0.51, 0.96, 1.0),
    tags={"sex": "male"},
)

FEMALE = BodyParams(
    name="female",
    height=1.62,
    hip_rx=0.108,
    hip_rz=0.074,
    waist_rx=0.068,
    waist_rz=0.050,
    chest_rx=0.088,
    chest_rz=0.067,
    shoulder_rx=0.092,
    shoulder_rz=0.057,
    shoulder_half_w=0.101,
    waist_y=0.648,
    upperarm_r=0.031,
    forearm_r=0.026,
    hand_r=0.032,
    thigh_r=0.052,
    shin_r=0.038,
    biceps_bulge=0.004,
    calf_bulge=0.006,
    head_r=0.086,
    leg_stance=0.50,
    skin_color=(0.96, 0.80, 0.70, 1.0),
    accent_color=(0.95, 0.42, 0.62, 1.0),
    tags={"sex": "female"},
)

PRESETS = {"male": MALE, "female": FEMALE}


def with_height(preset, height):
    return replace(preset, height=height)
