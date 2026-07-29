"""Morph target definitions: the muscle groups the app can grow.

Each group is a named blend shape whose per-vertex mask is derived from the
vertex's part tag, its height along the body, and which way its normal faces.
Growth is applied along the vertex normal, so a group swells outward instead of
translating, and the same mask works for the body and for the clothing shell
generated over it.

`amount` is a displacement at weight 1.0, expressed as a fraction of body height,
so both presets grow by a visually equivalent amount.
"""

from dataclasses import dataclass
from typing import Callable

from . import vecmath as vm

TORSO_PARTS = ("torso",)
HEAD_PARTS = ("head", "face", "neck")


@dataclass(frozen=True)
class MorphGroup:
    name: str
    label_ko: str
    label_en: str
    amount: float
    mask: Callable  # (ctx, part, position, normal) -> 0..1
    #: True for groups that represent losing shape rather than gaining it.
    is_regression: bool = False


class MaskContext:
    """Everything a mask function needs to score a vertex."""

    def __init__(self, params, rig):
        self.p = params
        self.rig = rig
        self.h = params.height
        self._segments = {}

    def yf(self, position):
        """Height of a vertex as a fraction of total body height."""
        return position[1] / self.h

    def along(self, bone, position):
        """0..1 position of a vertex projected onto a bone segment."""
        seg = self._segments.get(bone)
        if seg is None:
            seg = self.rig.segment(bone)
            self._segments[bone] = seg
        _, t = vm.dist_point_segment(position, seg[0], seg[1])
        return t


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


def _peak(t, center, width):
    """Bump centred on `center` along a bone, 0 at +/- width."""
    d = abs(t - center) / max(width, 1e-6)
    return vm.clamp01(1.0 - d) ** 0.8


# -- individual masks -------------------------------------------------------

def _mask_bulk(ctx, part, pos, nrm):
    # overall size: everything but the head, so the character reads as growing
    # without the head ballooning along with it
    if part in HEAD_PARTS:
        return 0.0
    return 1.0


def _mask_chest(ctx, part, pos, nrm):
    if part not in TORSO_PARTS:
        return 0.0
    y = ctx.yf(pos)
    return _band(y, ctx.p.chest_y - 0.045, ctx.p.shoulder_y - 0.005) * _front(nrm, 1.3)


def _mask_back(ctx, part, pos, nrm):
    if part not in TORSO_PARTS:
        return 0.0
    y = ctx.yf(pos)
    # lats flare the sides as well as the back — that V-taper is the payoff
    directional = _back(nrm) * 0.75 + _side(nrm) * 0.9
    return _band(y, ctx.p.waist_y - 0.01, ctx.p.shoulder_y) * vm.clamp01(directional)


def _mask_shoulders(ctx, part, pos, nrm):
    if part in ("shoulder_L", "shoulder_R"):
        return 1.0
    if part in ("upperarm_L", "upperarm_R"):
        bone = "UpperArm_" + part[-1]
        return vm.clamp01(1.0 - vm.smoothstep(0.05, 0.35, ctx.along(bone, pos)))
    if part in TORSO_PARTS:
        return _band(ctx.yf(pos), ctx.p.shoulder_y - 0.03, ctx.p.shoulder_y + 0.02) * 0.5
    return 0.0


def _mask_arms(ctx, part, pos, nrm):
    if part in ("upperarm_L", "upperarm_R"):
        t = ctx.along("UpperArm_" + part[-1], pos)
        return _peak(t, 0.42, 0.55)
    if part in ("forearm_L", "forearm_R"):
        # must reach 0 at t=0, where the upper arm's own mask has already
        # faded out — any mismatch shows as a hard step ringing the elbow
        t = ctx.along("Forearm_" + part[-1], pos)
        return _peak(t, 0.35, 0.35) * 0.62
    return 0.0


def _mask_abs(ctx, part, pos, nrm):
    if part not in TORSO_PARTS:
        return 0.0
    y = ctx.yf(pos)
    return _band(y, ctx.p.hip_y - 0.02, ctx.p.chest_y - 0.02) * _front(nrm, 1.6)


def _mask_glutes(ctx, part, pos, nrm):
    if part not in TORSO_PARTS:
        return 0.0
    y = ctx.yf(pos)
    return _band(y, ctx.p.crotch_y - 0.02, ctx.p.hip_y + 0.025, feather=0.035) * _back(nrm, 1.2)


def _mask_thighs(ctx, part, pos, nrm):
    if part not in ("thigh_L", "thigh_R"):
        return 0.0
    t = ctx.along("Thigh_" + part[-1], pos)
    return _peak(t, 0.3, 0.75)


def _mask_calves(ctx, part, pos, nrm):
    if part not in ("shin_L", "shin_R"):
        return 0.0
    t = ctx.along("Shin_" + part[-1], pos)
    return _peak(t, 0.26, 0.55)


def _mask_belly(ctx, part, pos, nrm):
    if part not in TORSO_PARTS:
        return 0.0
    y = ctx.yf(pos)
    core = _band(y, ctx.p.crotch_y + 0.02, ctx.p.chest_y - 0.01, feather=0.07)
    return core * vm.clamp01(_front(nrm, 1.1) * 0.95 + _side(nrm) * 0.35)


#: Ordered — the index of each group is its morph target index in the GLB, and
#: the Flutter side indexes by name from the manifest rather than by position.
GROUPS = (
    MorphGroup("bulk", "전체 체격", "Overall size", 0.0125, _mask_bulk),
    MorphGroup("chest", "가슴", "Chest", 0.0245, _mask_chest),
    MorphGroup("back", "등", "Back", 0.0225, _mask_back),
    MorphGroup("shoulders", "어깨", "Shoulders", 0.0205, _mask_shoulders),
    MorphGroup("arms", "팔", "Arms", 0.0185, _mask_arms),
    MorphGroup("abs", "복근", "Abs", 0.0110, _mask_abs),
    MorphGroup("glutes", "엉덩이", "Glutes", 0.0200, _mask_glutes),
    MorphGroup("thighs", "허벅지", "Thighs", 0.0185, _mask_thighs),
    MorphGroup("calves", "종아리", "Calves", 0.0165, _mask_calves),
    MorphGroup("belly", "뱃살", "Belly", 0.0430, _mask_belly, is_regression=True),
)

GROUPS_BY_NAME = {g.name: g for g in GROUPS}
