"""Anthropometric reference data.

Every proportion in the character comes from here rather than from eyeballing,
so the body reads as a plausible human and so the three body types are separated
by real measurements instead of by taste.

Sources, all expressed as a fraction of stature (H):

* Segment heights — Drillis & Contini (1966), the table reproduced in most
  biomechanics texts and in NASA-STD-3000 vol. I §3.
* Breadths and depths — NASA-STD-3000 / ANSUR-style adult 50th percentile.
* Girths at three training states — the lean/average/trained spread that
  bodybuilding and kinanthropometry references converge on. These are the ones
  that matter most here: they set how far the muscle morphs travel.

THE SKELETON DOES NOT CHANGE. Biacromial breadth, limb lengths and joint
positions are bone, and training does not move them. Only soft tissue does.
That is why every body type in this project shares one rig and one set of joint
positions, and differs only in surface morphs.
"""

# ---------------------------------------------------------------------------
# Segment heights (fraction of stature), measured from the floor.
# Shared by both sexes; the silhouette difference is breadth, not landmark
# height. Female values differ by ~0.005H at most, below what reads on screen.
# ---------------------------------------------------------------------------
HEIGHTS = {
    "ankle": 0.039,      # sphyrion
    "knee": 0.285,       # tibiale
    "crotch": 0.485,     # perineum
    "hip": 0.530,        # greater trochanter
    "waist": 0.620,      # natural waist, narrowest point
    "chest": 0.720,      # nipple line
    "shoulder": 0.818,   # acromion
    "neck": 0.870,       # cervicale
    "elbow": 0.630,      # radiale
    "wrist": 0.485,      # stylion
    "vertex": 1.000,
}

#: Head height (chin to vertex) as a fraction of stature. Anatomically 0.130,
#: giving the classic 7.7-heads figure. The character uses a larger head — see
#: HEAD_STYLE_SCALE — because a 7.7-head figure at phone size has an
#: unreadable face, and the face is where the user's own drawing goes.
HEAD_HEIGHT = 0.130

#: Deliberate stylisation: the head is enlarged so the face stays readable at
#: phone size, giving roughly a 6.9-head figure instead of 7.7. This is the one
#: proportion knowingly taken away from anatomy, and the only one.
#:
#: It is bounded by the neck: the chin sits at HEAD_HEIGHT below the vertex, and
#: the acromion at 0.818H, so a scale much past 1.15 leaves no visible neck and
#: the head appears to rest straight on the shoulders.
HEAD_STYLE_SCALE = 1.12


def head_center_y(style_scale=None):
    """Head centre height, derived from the vertex downward.

    Deriving the head from the TOP rather than upward from the neck is what
    keeps the figure exactly `height` tall. Building it upward from the neck
    landmark made the character 3.6% taller than requested, because the
    stylisation scale was added on top of an anatomical neck height.
    """
    scale = HEAD_STYLE_SCALE if style_scale is None else style_scale
    radius = HEAD_HEIGHT * scale / 2.0
    return HEIGHTS["vertex"] - radius * HEAD_SQUASH_Y


#: The head sphere is very slightly egg-shaped; this is its vertical scale.
HEAD_SQUASH_Y = 1.05

FOOT_LENGTH = 0.152
HAND_LENGTH = 0.108

# ---------------------------------------------------------------------------
# Breadths (side to side) and depths (front to back), as fractions of stature.
# Values are full widths; the mesh uses half of each as an ellipse radius.
# ---------------------------------------------------------------------------
BREADTHS = {
    "male": {
        "biacromial": 0.245,   # acromion to acromion — SKELETAL, never morphs
        "chest": 0.174,
        "waist": 0.158,
        "hip": 0.185,
    },
    "female": {
        "biacromial": 0.228,
        "chest": 0.160,
        "waist": 0.148,
        "hip": 0.202,          # wider than male: obstetric pelvis
    },
}

DEPTHS = {
    "male": {"chest": 0.126, "waist": 0.110, "hip": 0.125},
    "female": {"chest": 0.132, "waist": 0.100, "hip": 0.135},
}

# ---------------------------------------------------------------------------
# Girths (circumferences) at three training states, as fractions of stature.
#
# `lean` is the base mesh: an untrained, low-body-fat adult. The muscle morphs
# travel from `lean` to `trained`. Starting from `average` instead would leave
# the character with a bodybuilder's arm before the user has trained once, and
# nowhere to grow — which is what the first version of this model did.
# ---------------------------------------------------------------------------
GIRTHS = {
    "male": {
        "neck":      {"lean": 0.198, "average": 0.217, "trained": 0.243},
        "upper_arm": {"lean": 0.158, "average": 0.183, "trained": 0.228},
        "forearm":   {"lean": 0.136, "average": 0.154, "trained": 0.180},
        "wrist":     {"lean": 0.094, "average": 0.098, "trained": 0.103},
        "thigh":     {"lean": 0.272, "average": 0.314, "trained": 0.372},
        "calf":      {"lean": 0.187, "average": 0.211, "trained": 0.244},
        "ankle":     {"lean": 0.125, "average": 0.131, "trained": 0.138},
    },
    "female": {
        "neck":      {"lean": 0.183, "average": 0.198, "trained": 0.215},
        "upper_arm": {"lean": 0.144, "average": 0.170, "trained": 0.203},
        "forearm":   {"lean": 0.124, "average": 0.140, "trained": 0.160},
        "wrist":     {"lean": 0.087, "average": 0.091, "trained": 0.096},
        "thigh":     {"lean": 0.278, "average": 0.322, "trained": 0.372},
        "calf":      {"lean": 0.183, "average": 0.207, "trained": 0.236},
        "ankle":     {"lean": 0.119, "average": 0.125, "trained": 0.131},
    },
}

TWO_PI = 6.283185307179586


def radius(sex, site, state="lean"):
    """Convert a girth to an ellipse radius, as a fraction of stature."""
    return GIRTHS[sex][site][state] / TWO_PI


def girth_growth(sex, site):
    """How much radius a site gains going from lean to trained, in stature units.

    This is what sizes the muscle morphs: the displacement at weight 1.0 is the
    real difference between an untrained and a trained limb, not a guess.
    """
    return radius(sex, site, "trained") - radius(sex, site, "lean")


# ---------------------------------------------------------------------------
# Where body fat is deposited. Both patterns exist in both sexes; the ratio is
# what differs, and the app chooses it per user rather than per preset.
# ---------------------------------------------------------------------------
FAT_PATTERNS = {
    # apple / abdominal, more common in males: visceral and abdominal
    "android": {"label_ko": "복부형", "label_en": "Abdominal"},
    # pear / gluteofemoral, more common in females: hips, thighs, upper arms
    "gynoid": {"label_ko": "둔부·대퇴형", "label_en": "Gluteofemoral"},
}

#: Typical android:gynoid split by sex, used as the app's default when it has no
#: body-composition data of its own.
FAT_SPLIT = {"male": (0.78, 0.22), "female": (0.32, 0.68)}
