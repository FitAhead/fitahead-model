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

import math
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
        self._frames = {}

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

    def limb_frame(self, bone):
        """(origin, axis, front, side) for a limb's cross-section plane.

        `front` is +Z projected perpendicular to the bone, so an angle of 0 is
        always the anterior surface no matter how the limb is posed. Without
        this, angles measured in world axes would drift as soon as the arm was
        abducted.
        """
        frame = self._frames.get(bone)
        if frame is None:
            start, end = self.rig.segment(bone)
            axis = vm.normalize(vm.sub(end, start))
            z = (0.0, 0.0, 1.0)
            front = vm.normalize(vm.sub(z, vm.mul(axis, vm.dot(z, axis))))
            side = vm.normalize(vm.cross(axis, front))
            frame = (start, axis, front, side)
            self._frames[bone] = frame
        return frame

    def limb_angle(self, part, position):
        """Angle around the limb: 0 anterior, +90 lateral, 180 posterior.

        Signed by side so `+90` is away from the midline on both arms and legs,
        which lets one mask describe the vastus lateralis without a mirror case.
        """
        bone = self.limb_t(part)
        origin, axis, front, side = self.limb_frame(bone)
        radial = vm.sub(position, origin)
        radial = vm.sub(radial, vm.mul(axis, vm.dot(radial, axis)))
        return math.atan2(vm.dot(radial, side) * self.side_sign(part),
                          vm.dot(radial, front))

    def torso_angle(self, position):
        """Angle around the torso: 0 anterior, +/-90 lateral, 180 posterior."""
        return math.atan2(position[0], position[2])

    def lateral(self, position):
        """0 at the midline, 1 at the widest point of the shoulders."""
        return vm.clamp01(abs(position[0]) / (self.p.shoulder_half_w * self.h))


# -- mask primitives --------------------------------------------------------

def _band(y, lo, hi, feather=0.05):
    """Smooth window over a height range.

    `feather` may be a `(lower, upper)` pair. Asymmetry matters: a muscle that
    ends where another begins can fade slowly, but one that ends on open skin
    must fade over a long distance or its edge becomes a cliff. The pectoralis
    fading over 26 mm while displacing 46 mm produced a 45-degree step across the
    chest, which read as a rectangular slot cut into the model.
    """
    lo_f, hi_f = feather if isinstance(feather, tuple) else (feather, feather)
    return vm.smoothstep(lo - lo_f, lo + lo_f * 0.5, y) * (
        1.0 - vm.smoothstep(hi - hi_f * 0.5, hi + hi_f, y)
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


def _bump(x, center, half_width, fullness=1.6):
    """Raised-cosine lobe: 1 at `center`, 0 at `center +/- half_width`.

    Zero derivative at the edges, unlike the linear falloff this replaces — a
    linear cone meets its surroundings at an angle and reads as a facet.
    `fullness` > 1 flattens the top, which is what a muscle belly looks like.
    """
    d = abs(x - center) / max(half_width, 1e-9)
    if d >= 1.0:
        return 0.0
    return (0.5 + 0.5 * math.cos(math.pi * d)) ** (1.0 / fullness)


def _rim(x, center, half_width, rim_width):
    """Lobe sitting just OUTSIDE `center +/- half_width`, peaking mid-rim.

    This is the groove that makes a muscle read as a muscle. Anatomically it is
    the intermuscular septum — the seam where one muscle meets the next. Volume
    alone reads as swelling; all the definition comes from the boundary.
    """
    d = abs(x - center)
    lo = half_width
    hi = half_width + max(rim_width, 1e-9)
    if d <= lo or d >= hi:
        return 0.0
    return math.sin(math.pi * (d - lo) / (hi - lo))


def _rim_below(x, edge, width):
    """Groove sitting just BELOW `edge`, zero at both ends.

    A muscle's inferior border is a one-sided landmark: the inframammary line
    under the pectoralis and the gluteal fold under the glutes read as a crease
    below the muscle, with nothing matching it above.
    """
    if x >= edge or x <= edge - width:
        return 0.0
    return math.sin(math.pi * (x - (edge - width)) / width)


def _torso_muscle(ctx, pos, y_range, angular, septum=0.17, fold=0.0,
                  feather=0.045, mirror=False):
    """Torso muscle: a belly bounded by a septum groove, optionally a fold below.

    `angular` is `(centre_deg, half_deg)` around the torso, 0 anterior. When
    `mirror` is set the centre is taken on |angle|, which is how one entry
    describes both latissimus dorsi or both obliques.
    """
    y = ctx.yf(pos)
    lo, hi = y_range
    env = _band(y, lo, hi, feather)
    if env <= 1e-4:
        return 0.0
    ang = ctx.torso_angle(pos)
    if mirror:
        ang = abs(ang)
    g = _ang_bump(ang, angular[0], angular[1])
    grooves = septum * _ang_rim(ang, angular[0], angular[1],
                                angular[1] * 0.40) * env
    if fold:
        # Horizontal creases — the inframammary line, the gluteal fold — are OFF.
        # Vertical ring spacing on the torso is about 8 mm, so a crease narrow
        # enough to be one reads as a rectangular trench rather than a fold. This
        # detail belongs in a normal map; the parameter stays so it can be turned
        # back on if the torso ever gains UVs.
        grooves += fold * _rim_below(y, lo + (hi - lo) * 0.12,
                                    (hi - lo) * 0.26) * g
    return env * g - grooves


def _ang_delta(a, b):
    """Shortest signed distance between two angles, in radians."""
    d = (a - b) % (2.0 * math.pi)
    return d - 2.0 * math.pi if d > math.pi else d


def _ang_bump(angle, center_deg, half_deg, fullness=1.6):
    return _bump(_ang_delta(angle, math.radians(center_deg)), 0.0,
                 math.radians(half_deg), fullness)


def _ang_rim(angle, center_deg, half_deg, rim_deg):
    return _rim(_ang_delta(angle, math.radians(center_deg)), 0.0,
                math.radians(half_deg), math.radians(rim_deg))


def _muscle(t, angle, axial, angular, septum=0.17, tendon=0.10):
    """A muscle belly bounded by grooves.

    `axial` is `(centre, half_width)` along the bone and `angular` is
    `(centre_deg, half_deg)` around it. The belly is their product; the septum
    groove sits just outside the angular extent and the tendon groove just
    outside the axial extent, both gated by the muscle actually being there so a
    groove never floats on bare skin.
    """
    a = _bump(t, axial[0], axial[1])
    g = _ang_bump(angle, angular[0], angular[1])
    belly = a * g
    if belly <= 0.0 and a <= 0.0:
        return 0.0
    grooves = (septum * _ang_rim(angle, angular[0], angular[1],
                                 angular[1] * 0.42) * a
               + tendon * _rim(t, axial[0], axial[1], axial[1] * 0.35) * g)
    return belly - grooves


def _peak(t, center, width, falloff=0.85):
    """Legacy linear lobe, kept for masks that want a plain gradient."""
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
        # the lateral head caps the joint; grooves at the front and back are the
        # pec-delt and delt-triceps seams, two of the most recognisable
        # landmarks on a trained upper body
        return _muscle(ctx.along(ctx.limb_t(part), pos),
                       ctx.limb_angle(part, pos),
                       axial=(0.09, 0.36), angular=(80.0, 70.0),
                       septum=0.19, tendon=0.08)
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
    p = ctx.p
    # TWO bellies, lateral to the sternum, with the sternal valley between
    # them. A single belly centred on the midline is both anatomically wrong —
    # the pectoralis originates ON the sternum, it does not cross it — and it
    # is why the chest used to end in a cliff: 46 mm of displacement fading
    # over 26 mm of height is a 45-degree step, and its shadow read as a
    # rectangular slot cut into the chest. The lower edge now fades over 80 mm.
    return _torso_muscle(ctx, pos,
                         (p.chest_y - 0.030, p.shoulder_y - 0.004),
                         angular=(36.0, 36.0), septum=0.12, fold=0.0,
                         mirror=True, feather=(0.080, 0.028))


def _mask_lats(ctx, part, pos, nrm):
    """Latissimus dorsi — origin at the lower thoracic and lumbar spine,
    insertion on the humerus.

    Widest across the MID back, not at the shoulder: that is what produces the
    V-taper, because the flare sits above a waist that does not move.
    """
    if part not in TORSO_PARTS:
        return 0.0
    p, y = ctx.p, ctx.yf(pos)
    # centred on the posterolateral wall, mirrored so one entry covers both
    # sides; the anterior groove is the lat's leading border, visible from the
    # side on anyone who trains their back
    base = _torso_muscle(ctx, pos, (p.waist_y + 0.012, p.shoulder_y - 0.015),
                         angular=(122.0, 54.0), septum=0.15, mirror=True,
                         feather=(0.070, 0.040))
    # widest across the MID back: the flare has to sit above a waist that does
    # not move, or there is no V-taper, just a wider tube
    height_profile = _bump((y - p.waist_y) / (p.shoulder_y - p.waist_y),
                           0.55, 0.72)
    return base * height_profile


def _mask_biceps(ctx, part, pos, nrm):
    """Biceps brachii — anterior compartment, belly near mid-humerus."""
    if part not in UPPERARM_PARTS:
        return 0.0
    return _muscle(ctx.along(ctx.limb_t(part), pos),
                   ctx.limb_angle(part, pos),
                   axial=(0.52, 0.44), angular=(0.0, 78.0),
                   septum=0.18, tendon=0.11)


def _mask_triceps(ctx, part, pos, nrm):
    """Triceps brachii — posterior compartment, sits more proximal than the
    biceps because the long head runs up to the scapula."""
    if part not in UPPERARM_PARTS:
        return 0.0
    return _muscle(ctx.along(ctx.limb_t(part), pos),
                   ctx.limb_angle(part, pos),
                   axial=(0.36, 0.46), angular=(180.0, 72.0),
                   septum=0.18, tendon=0.10)


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

    # The paired straps are narrow: rectus abdominis spans roughly the middle
    # half of the abdominal wall, bounded medially by the linea alba and
    # laterally by the linea semilunaris. Wider than that and the six-pack reads
    # as corrugation across the whole belly.
    strap = vm.smoothstep(0.56, 0.34, au) * vm.smoothstep(0.06, 0.15, au)
    alba = -0.40 * (1.0 - vm.smoothstep(0.0, 0.11, au))
    # three tendinous intersections, shallower than the midline so the straps
    # still read as continuous columns rather than as stacked blocks
    lines = -(0.34 * _ridge(v, 0.34, 0.115)
              + 0.24 * _ridge(v, 0.57, 0.105)
              + 0.17 * _ridge(v, 0.78, 0.095))
    return envelope * (strap + alba + lines * strap)


def _mask_obliques(ctx, part, pos, nrm):
    """External oblique — the flanks, angling down toward the pubis."""
    if part not in TORSO_PARTS:
        return 0.0
    p = ctx.p
    return _torso_muscle(ctx, pos, (p.hip_y - 0.015, p.chest_y - 0.02),
                         angular=(74.0, 42.0), septum=0.13, mirror=True,
                         feather=0.040)


def _mask_glutes(ctx, part, pos, nrm):
    """Gluteus maximus — posterior, peaking just below the trochanter line."""
    if part not in TORSO_PARTS:
        return 0.0
    p = ctx.p
    # the fold below is the gluteal fold, the crease where the buttock meets the
    # thigh — without it the glutes merge into the hamstrings
    return _torso_muscle(ctx, pos, (p.crotch_y - 0.012, p.hip_y + 0.034),
                         angular=(180.0, 82.0), septum=0.13, fold=0.0,
                         feather=(0.030, 0.055))


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
    return _muscle(ctx.along(ctx.limb_t(part), pos),
                   ctx.limb_angle(part, pos),
                   axial=(0.48, 0.50), angular=(180.0, 68.0),
                   septum=0.14, tendon=0.10)


def _mask_calves(ctx, part, pos, nrm):
    """Gastrocnemius — the two heads sit high on the posterior calf and taper
    into the Achilles, so the peak is well proximal of mid-shin."""
    if part not in SHIN_PARTS:
        return 0.0
    t = ctx.along(ctx.limb_t(part), pos)
    angle = ctx.limb_angle(part, pos)
    # two heads, split by a shallow groove down the midline of the calf; the
    # medial head sits slightly lower, which is why the two are not symmetric
    medial = _muscle(t, angle, axial=(0.30, 0.36), angular=(206.0, 46.0),
                     septum=0.12, tendon=0.11)
    lateral = _muscle(t, angle, axial=(0.25, 0.34), angular=(154.0, 44.0),
                      septum=0.12, tendon=0.11) * 0.92
    return medial + lateral


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
                   "승모근 상부", "Upper trapezius", 0.0225, _mask_traps),
        MorphGroup("delts", "어깨", "Shoulders",
                   "삼각근", "Deltoid", arm * 1.05, _mask_delts),
        MorphGroup("pecs", "가슴", "Chest",
                   "대흉근", "Pectoralis major", 0.0265, _mask_pecs),
        MorphGroup("lats", "등", "Back",
                   "광배근", "Latissimus dorsi", 0.0200, _mask_lats),

        MorphGroup("biceps", "이두", "Biceps",
                   "상완이두근", "Biceps brachii", arm * 1.05, _mask_biceps),
        MorphGroup("triceps", "삼두", "Triceps",
                   "상완삼두근", "Triceps brachii", arm * 0.85, _mask_triceps),
        MorphGroup("forearms", "전완", "Forearms",
                   "완요골근·전완굴근", "Brachioradialis / flexors",
                   fore * 0.74, _mask_forearms),

        MorphGroup("abs", "복근", "Abs",
                   "복직근", "Rectus abdominis", 0.0150, _mask_abs),
        MorphGroup("obliques", "옆구리", "Obliques",
                   "외복사근", "External oblique", 0.0110, _mask_obliques),

        MorphGroup("glutes", "엉덩이", "Glutes",
                   "대둔근", "Gluteus maximus", 0.0285, _mask_glutes),
        MorphGroup("quads", "허벅지 앞", "Quads",
                   "대퇴사두근", "Quadriceps femoris", thigh * 1.62, _mask_quads),
        MorphGroup("hams", "허벅지 뒤", "Hamstrings",
                   "햄스트링", "Hamstrings", thigh * 1.28, _mask_hams),
        MorphGroup("calves", "종아리", "Calves",
                   "비복근", "Gastrocnemius", calf * 1.52, _mask_calves),

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
