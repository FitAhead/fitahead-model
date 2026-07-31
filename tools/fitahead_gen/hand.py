from typing import Final

from . import geom, vecmath as vm
from .params import BodyParams
from .rig import Rig

HAND_PROFILE: Final[list[tuple[float, float]]] = [
    (0.0, 0.78),
    (0.20, 1.00),
    (1.0, 0.94),
]
FINGER_LENGTHS: Final[tuple[float, ...]] = (0.78, 1.0, 0.92, 0.72)
FINGER_OFFSETS: Final[tuple[float, ...]] = (-1.35, -0.45, 0.45, 1.35)


def build(mesh: geom.MeshData, p: BodyParams, rig: Rig, side: str) -> None:
    wrist = rig.world(f"Hand_{side}")
    elbow = rig.world(f"Forearm_{side}")
    arm_dir = vm.normalize(vm.sub(wrist, elbow))
    _, across, axis = vm.basis_from_dir(arm_dir)
    hand_len = p.hand_len * p.height
    wrist_r = p.wrist_r * p.height
    palm_end = vm.add(wrist, vm.mul(axis, hand_len * 0.48))

    geom.tube(mesh, wrist, palm_end, wrist_r * 1.45, wrist_r * 1.55,
              f"hand_{side}", segments=18, slices=6,
              profile=HAND_PROFILE, aspect_x=0.44, cap_start=False)

    finger_r = wrist_r * 0.39
    finger_start = vm.add(palm_end, vm.mul(axis, -hand_len * 0.035))
    for offset, length in zip(FINGER_OFFSETS, FINGER_LENGTHS):
        base = vm.add(finger_start, vm.mul(across, offset * finger_r * 1.68))
        tip = vm.add(base, vm.mul(axis, hand_len * 0.54 * length))
        geom.tube(mesh, base, tip, finger_r, finger_r * 0.68,
                  f"hand_{side}", segments=8, slices=4,
                  aspect_x=0.72, round_end=finger_r * 0.72)

    sx = 1.0 if side == "L" else -1.0
    outward = across if across[0] * sx > 0.0 else vm.mul(across, -1.0)
    thumb_base = vm.add(
        vm.add(wrist, vm.mul(axis, hand_len * 0.27)),
        vm.mul(outward, wrist_r * 0.72),
    )
    thumb_dir = vm.normalize(vm.add(vm.mul(axis, 0.36), vm.mul(outward, 0.94)))
    thumb_tip = vm.add(thumb_base, vm.mul(thumb_dir, hand_len * 0.34))
    geom.tube(mesh, thumb_base, thumb_tip, finger_r * 1.08, finger_r * 0.72,
              f"hand_{side}", segments=8, slices=4,
              aspect_x=0.74, round_end=finger_r * 0.76)
