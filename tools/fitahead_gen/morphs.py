"""Morph target definitions — one blend shape per anatomical structure.

Each group is named for the muscle it represents and shaped to that muscle's
real region and direction of bulge. A mask function scores every vertex from
`(part, position, normal)`, and the vertex is displaced along its normal by
`amount * mask`.

Two things make this anatomical rather than decorative:

* **Direction.** Pectoralis major pushes forward, latissimus dorsi widens the
  flanks, triceps pushes back. A single "chest" shape that swelled in every
  direction would read as fat, not muscle.
* **Where along the muscle it peaks.** The biceps belly sits near mid-humerus;
  the triceps sits more proximal; the gastrocnemius heads sit high on the calf.
  Peaks in the wrong place look like swelling.

Masks may return NEGATIVE values. That is how grooves work — the linea alba
down the middle of the abdomen and the tendinous intersections that separate the
"six pack" are indentations, and a muscle that only ever pushes out cannot
produce them.

Displacement amounts come from `anthro` where a girth measurement exists, so a
morph at weight 1.0 moves the surface by the real lean-to-trained difference.
"""

from dataclasses import dataclass
from typing import Callable

from . import vecmath as vm

TORSO_PARTS = ("torso",)
HEAD_PARTS = ("head", "face")
UPPERARM_PARTS = ("upperarm_L", "upperarm_R")
FOREARM_PARTS = ("forearm_L", "forearm_R")
THIGH_PARTS = ("thigh_L", "thigh_R")
SHIN_PARTS = ("shin_L", "shin_R")


@dataclass(frozen=True)
class MorphGroup:
    name: str
    label_ko: str
    label_en: str
    muscle_ko: str
    muscle_en: str
    #: Displacement at weight 1.0, as a fraction of stature.
    amount: float
    mask: Callable
    #: "muscle" grows with training; "fat" comes from body composition;
    #: "composite" is derived from the others.
    kind: str = "muscle"


class MaskContext:
    """Everything a mask function needs to score a vertex."""

    def __init__(self, params, rig):
        self.p = params
        self.rig = rig
        self.h = params.height
        self._segments = {}

    def yf(self, position):
        """Height of a vertex as a fraction of stature."""
        return position[1] / self.h

    def along(self, bone, position):
        """0..1 position of a vertex projected onto a bone segment."""
        seg = self._segments.get(bone)
        if seg is None:
            seg = self.rig.segment(bone)
            self._segments[bone] = seg
        _, t = vm.dist_point_segment(position, seg[0], seg[1])
        return t

    def limb_t(self, part):
        """Bone name driving a limb part, for `along`."""
        prefix = {
            "upperarm": "UpperArm", "forearm": "Forearm",
            "thigh": "Thigh", "shin": "Shin",
        }
        base, side = part.rsplit("_", 1)
        return f"{prefix[base]}_{side}"

    @staticmethod
    def side_sign(part):
        """+1 for the character's left (+X), -1 for the right."""
        return 1.0 if part.endswith("_L") else -1.0

    def torso_uv(self, position):
        """Local abdominal coordinates.

        u: lateral offset normalised by the waist half-breadth, signed.
        v: 0 at the pubis, 1 at the sternum.
        """
        u = position[0] / (self.p.waist_rx * self.h)
        lo, hi = self.p.crotch_y + 0.015, self.p.chest_y - 0.015
        v = (self.yf(position) - lo) / (hi - lo)
        return u, v

    def lateral(self, position):
        """0 at the midline, 1 at the widest point of the shoulders."""
        return vm.clamp01(abs(position[0]) / (self.p.shoulder_half_w * self.h))


# -- mask primitives --------------------------------------------------------

def _band(y, lo, hi, feather=0.05):
    """Smooth window over a height range."""
    return vm.smoothstep(lo - feather, lo + feather * 0.5, y) * (
        1.0 - vm.smoothstep(hi - feather * 0.5, hi + feather, y)
    )


def _front(normal, power=1.0):
    return vm.clamp01(normal[2]) ** power


def _back(normal, power=1.0):
    return vm.clamp01(-normal[2]) ** power


def _side(normal):
    return vm.clamp01(abs(normal[0]))


def _outward(normal, sign):
    """Facing away from the body midline, for the given side."""
    return vm.clamp01(normal[0] * sign)


def _compartment(direction, bias):
    """Blend an all-round component with a compartment-biased one.

    A hypertrophied muscle increases the entire limb circumference; its own
    compartment simply gains more. A mask that is purely directional grows only
    the limb's depth, so from a front view — the app's default — the arm looks
    unchanged no matter how much the biceps morph is dialled in.

    `bias` is the share that is directional; the remainder applies all round.
    """
    return (1.0 - bias) + bias * direction


def _peak(t, center, width, falloff=0.85):
    """Bump centred at `center` along a bone, reaching 0 at +/- width."""
    d = abs(t - center) / max(width, 1e-6)
    return vm.clamp01(1.0 - d) ** falloff


def _ridge(x, center, width):
    """Narrow gaussian-ish ridge, for tendinous lines."""
    d = (x - center) / max(width, 1e-6)
    return max(0.0, 1.0 - d * d)


# -- individual masks -------------------------------------------------------

def _mask_bulk(ctx, part, pos, nrm):
    """General lean mass: neck, hands, feet and everything not covered by a
    named group. Excludes the head so growing does not inflate the face."""
    if part in HEAD_PARTS:
        return 0.0
    return 1.0


def _mask_traps(ctx, part, pos, nrm):
    """Upper trapezius — the slope from the neck out to the acromion.

    The single clearest silhouette cue for a trained upper body, and the one
    the first version of this model was missing entirely.
    """
    if part not in TORSO_PARTS:
        return 0.0
    y = ctx.yf(pos)
    p = ctx.p
    # peaks midway between neck and acromion, fades at both ends
    lateral = ctx.lateral(pos)
    profile = _peak(lateral, 0.42, 0.55)
    return _band(y, p.chest_y + 0.055, p.neck_y + 0.012, feather=0.035) * profile


def _mask_delts(ctx, part, pos, nrm):
    """Deltoid — caps the shoulder, bulges laterally and superiorly.

    Note this is soft tissue outside the acromion: biacromial breadth is bone
    and does not change, so a broader shoulder is entirely deltoid mass.
    """
    if part in UPPERARM_PARTS:
        t = ctx.along(ctx.limb_t(part), pos)
        return _peak(t, 0.10, 0.38) * (0.55 + 0.45 * _side(nrm))
    if part in ("shoulder_L", "shoulder_R"):
        return 1.0
    if part in TORSO_PARTS:
        y = ctx.yf(pos)
        band = _band(y, ctx.p.shoulder_y - 0.035, ctx.p.shoulder_y + 0.018,
                     feather=0.02)
        return band * ctx.lateral(pos) * 0.55
    return 0.0


def _mask_pecs(ctx, part, pos, nrm):
    """Pectoralis major — fans from clavicle and sternum to the humerus.

    Forward-facing and medial: it must not widen the flanks, or it reads as
    a swollen ribcage rather than a chest.
    """
    if part not in TORSO_PARTS:
        return 0.0
    p, y = ctx.p, ctx.yf(pos)
    band = _band(y, p.chest_y - 0.048, p.shoulder_y - 0.012, feather=0.032)
    lateral = ctx.lateral(pos)
    # taper off past the outer edge of the sternum-to-humerus fan
    fan = 1.0 - vm.smoothstep(0.62, 1.0, lateral)
    return band * _compartment(_front(nrm, 1.35), 0.76) * fan


def _mask_lats(ctx, part, pos, nrm):
    """Latissimus dorsi — origin at the lower thoracic and lumbar spine,
    insertion on the humerus.

    Widest across the MID back, not at the shoulder: that is what produces the
    V-taper, because the flare sits above a waist that does not move.
    """
    if part not in TORSO_PARTS:
        return 0.0
    p, y = ctx.p, ctx.yf(pos)
    band = _band(y, p.waist_y + 0.012, p.shoulder_y - 0.015, feather=0.045)
    # peak just below the chest line, where the lats are widest
    height_profile = _peak((y - p.waist_y) / (p.shoulder_y - p.waist_y),
                           0.55, 0.70)
    directional = vm.clamp01(_back(nrm) * 0.70 + _side(nrm) * 0.72)
    return band * height_profile * directional


def _mask_biceps(ctx, part, pos, nrm):
    """Biceps brachii — anterior compartment, belly near mid-humerus."""
    if part not in UPPERARM_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    return _peak(t, 0.52, 0.46) * _compartment(_front(nrm, 1.15), 0.55)


def _mask_triceps(ctx, part, pos, nrm):
    """Triceps brachii — posterior compartment, sits more proximal than the
    biceps because the long head runs up to the scapula."""
    if part not in UPPERARM_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    return _peak(t, 0.36, 0.50) * _compartment(_back(nrm, 1.15), 0.55)


def _mask_forearms(ctx, part, pos, nrm):
    """Brachioradialis and the flexor mass — bulk sits proximal, tapering to a
    wrist that barely changes with training."""
    if part not in FOREARM_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    return _peak(t, 0.22, 0.58) * (0.72 + 0.28 * _back(nrm))


def _mask_abs(ctx, part, pos, nrm):
    """Rectus abdominis, with the linea alba and the tendinous intersections.

    The two straps push out; the midline and the transverse lines pull in. That
    contrast is what reads as definition — an abdomen that only bulges outward
    looks like a fuller belly, which is the opposite of the intent.
    """
    if part not in TORSO_PARTS:
        return 0.0
    u, v = ctx.torso_uv(pos)
    if v < -0.1 or v > 1.1:
        return 0.0
    au = abs(u)
    front = _front(nrm, 1.5)
    envelope = _band(v, 0.02, 0.98, feather=0.16) * front
    if envelope <= 1e-4:
        return 0.0

    # the paired straps, absent at the midline and past the linea semilunaris
    strap = vm.smoothstep(0.70, 0.46, au) * vm.smoothstep(0.05, 0.17, au)
    # linea alba: the midline groove between them
    alba = -0.55 * (1.0 - vm.smoothstep(0.0, 0.13, au))
    # three tendinous intersections; the lowest pair is the least defined
    lines = -(0.50 * _ridge(v, 0.33, 0.075)
              + 0.55 * _ridge(v, 0.56, 0.070)
              + 0.45 * _ridge(v, 0.77, 0.065))
    return envelope * (strap + alba + lines * strap)


def _mask_obliques(ctx, part, pos, nrm):
    """External oblique — the flanks, angling down toward the pubis."""
    if part not in TORSO_PARTS:
        return 0.0
    p, y = ctx.p, ctx.yf(pos)
    band = _band(y, p.hip_y - 0.015, p.chest_y - 0.02, feather=0.04)
    return band * _side(nrm) * (0.55 + 0.45 * _front(nrm))


def _mask_glutes(ctx, part, pos, nrm):
    """Gluteus maximus — posterior, peaking just below the trochanter line."""
    if part not in TORSO_PARTS:
        return 0.0
    p, y = ctx.p, ctx.yf(pos)
    band = _band(y, p.crotch_y - 0.015, p.hip_y + 0.032, feather=0.03)
    return band * _compartment(_back(nrm, 1.15), 0.78)


def _mask_quads(ctx, part, pos, nrm):
    """Quadriceps — rectus femoris anterior mid-thigh, plus vastus lateralis
    which sits lower and further out and gives the thigh its outward sweep."""
    if part not in THIGH_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    sign = ctx.side_sign(part)
    rectus = _peak(t, 0.44, 0.60) * _compartment(_front(nrm, 1.2), 0.55)
    vastus = _peak(t, 0.62, 0.36) * _outward(nrm, sign) * 0.85
    return vm.clamp01(rectus + vastus)


def _mask_hams(ctx, part, pos, nrm):
    """Hamstrings — posterior thigh, fullest at mid-length."""
    if part not in THIGH_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    return _peak(t, 0.48, 0.55) * _compartment(_back(nrm, 1.2), 0.60)


def _mask_calves(ctx, part, pos, nrm):
    """Gastrocnemius — the two heads sit high on the posterior calf and taper
    into the Achilles, so the peak is well proximal of mid-shin."""
    if part not in SHIN_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    return _peak(t, 0.28, 0.46) * _compartment(_back(nrm), 0.60)


def _mask_fat_android(ctx, part, pos, nrm):
    """Abdominal ("apple") fat pattern: abdomen, flanks, and some on the chest
    and the back of the neck. The pattern that predominates in males."""
    p = ctx.p
    if part in TORSO_PARTS:
        y = ctx.yf(pos)
        belly = _band(y, p.crotch_y + 0.035, p.chest_y - 0.005, feather=0.075)
        belly *= vm.clamp01(_front(nrm, 1.05) * 1.0 + _side(nrm) * 0.45)
        upper = _band(y, p.chest_y - 0.01, p.shoulder_y, feather=0.05) * 0.30
        return vm.clamp01(belly + upper)
    if part == "neck":
        return 0.35
    return 0.0


def _mask_fat_gynoid(ctx, part, pos, nrm):
    """Gluteofemoral ("pear") fat pattern: hips, buttocks, proximal thighs and
    the back of the upper arms. The pattern that predominates in females."""
    p = ctx.p
    if part in TORSO_PARTS:
        y = ctx.yf(pos)
        hips = _band(y, p.crotch_y - 0.01, p.waist_y - 0.015, feather=0.055)
        return hips * vm.clamp01(_side(nrm) * 1.0 + _back(nrm) * 0.75
                                 + _front(nrm) * 0.30)
    if part in THIGH_PARTS:
        t = ctx.along(ctx.limb_t(part), pos)
        return _peak(t, 0.16, 0.60)
    if part in UPPERARM_PARTS:
        t = ctx.along(ctx.limb_t(part), pos)
        return _peak(t, 0.55, 0.55) * (0.35 + 0.65 * _back(nrm)) * 0.75
    return 0.0


# -- group table ------------------------------------------------------------

def build_groups(p):
    """Morph groups for a preset.

    Amounts are derived from `anthro` girth data where a measurement exists, so
    the travel of each morph is the real lean-to-trained difference rather than
    a number chosen to look right.
    """
    # Growth budgets are SHARED between the groups that overlap a site. An upper
    # arm vertex is touched by biceps, triceps, delts and bulk at once, so each
    # takes a share of the site's lean-to-trained gain rather than all of it.
    # The shares are calibrated with tools/measure.py against `anthro`; run it
    # after changing any amount here.
    arm = p.growth("upper_arm")
    fore = p.growth("forearm")
    thigh = p.growth("thigh")
    calf = p.growth("calf")

    return (
        MorphGroup("bulk", "전체 제지방", "Lean mass",
                   "전신", "Whole body", 0.0038, _mask_bulk, kind="composite"),

        MorphGroup("traps", "승모근", "Traps",
                   "승모근 상부", "Upper trapezius", 0.0165, _mask_traps),
        MorphGroup("delts", "어깨", "Shoulders",
                   "삼각근", "Deltoid", arm * 0.62, _mask_delts),
        MorphGroup("pecs", "가슴", "Chest",
                   "대흉근", "Pectoralis major", 0.0180, _mask_pecs),
        MorphGroup("lats", "등", "Back",
                   "광배근", "Latissimus dorsi", 0.0140, _mask_lats),

        MorphGroup("biceps", "이두", "Biceps",
                   "상완이두근", "Biceps brachii", arm * 0.58, _mask_biceps),
        MorphGroup("triceps", "삼두", "Triceps",
                   "상완삼두근", "Triceps brachii", arm * 0.46, _mask_triceps),
        MorphGroup("forearms", "전완", "Forearms",
                   "완요골근·전완굴근", "Brachioradialis / flexors",
                   fore * 0.62, _mask_forearms),

        MorphGroup("abs", "복근", "Abs",
                   "복직근", "Rectus abdominis", 0.0120, _mask_abs),
        MorphGroup("obliques", "옆구리", "Obliques",
                   "외복사근", "External oblique", 0.0080, _mask_obliques),

        MorphGroup("glutes", "엉덩이", "Glutes",
                   "대둔근", "Gluteus maximus", 0.0200, _mask_glutes),
        MorphGroup("quads", "허벅지 앞", "Quads",
                   "대퇴사두근", "Quadriceps femoris", thigh * 1.08, _mask_quads),
        MorphGroup("hams", "허벅지 뒤", "Hamstrings",
                   "햄스트링", "Hamstrings", thigh * 0.86, _mask_hams),
        MorphGroup("calves", "종아리", "Calves",
                   "비복근", "Gastrocnemius", calf * 0.86, _mask_calves),

        MorphGroup("fat_android", "복부 체지방", "Abdominal fat",
                   "복부 지방", "Abdominal adipose", 0.0430,
                   _mask_fat_android, kind="fat"),
        MorphGroup("fat_gynoid", "둔부 체지방", "Gluteofemoral fat",
                   "둔부·대퇴 지방", "Gluteofemoral adipose", 0.0275,
                   _mask_fat_gynoid, kind="fat"),
    )


#: Groups that grow with training, in display order.
MUSCLE_ORDER = (
    "traps", "delts", "pecs", "lats", "biceps", "triceps", "forearms",
    "abs", "obliques", "glutes", "quads", "hams", "calves",
)
