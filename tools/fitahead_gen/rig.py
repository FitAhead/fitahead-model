"""Skeleton definition.

Joint layout follows the Khronos RiggedFigure sample's topology (torso chain,
mirrored arm and leg chains) but adds a head joint and splits the torso into
hips / spine / chest so the waist can bend and so morph masks have clean height
bands to key off.

The rest pose is translation-only, which makes the inverse bind matrix of every
joint just a negated translation.
"""

from . import vecmath as vm


class Bone:
    __slots__ = ("name", "parent", "world", "children", "index")

    def __init__(self, name, parent, world):
        self.name = name
        self.parent = parent
        self.world = world
        self.children = []
        self.index = -1


class Rig:
    def __init__(self, bones):
        self.bones = bones
        self.by_name = {}
        for i, b in enumerate(bones):
            b.index = i
            self.by_name[b.name] = b
        for b in bones:
            if b.parent:
                self.by_name[b.parent].children.append(b.name)

    def world(self, name):
        return self.by_name[name].world

    def local_translation(self, name):
        b = self.by_name[name]
        if b.parent is None:
            return b.world
        return vm.sub(b.world, self.by_name[b.parent].world)

    def inverse_bind(self, name):
        w = self.by_name[name].world
        return vm.translation_matrix((-w[0], -w[1], -w[2]))

    def segment(self, name):
        """(start, end) of the bone: from this joint to the mean of its children,
        or a short stub along +Y for leaf joints."""
        b = self.by_name[name]
        if not b.children:
            return b.world, vm.add(b.world, (0.0, 0.02, 0.0))
        acc = (0.0, 0.0, 0.0)
        for c in b.children:
            acc = vm.add(acc, self.by_name[c].world)
        return b.world, vm.mul(acc, 1.0 / len(b.children))


def build_rig(p):
    """Build the joint hierarchy for a BodyParams preset."""
    h = p.height

    def y(fraction):
        return fraction * h

    hip_half = p.hip_rx * h * p.leg_stance
    sw = p.shoulder_half_w * h

    bones = [
        Bone("Root", None, (0.0, 0.0, 0.0)),
        Bone("Hips", "Root", (0.0, y(p.hip_y), 0.0)),
        Bone("Spine", "Hips", (0.0, y(p.waist_y), 0.0)),
        Bone("Chest", "Spine", (0.0, y(p.chest_y), 0.0)),
        Bone("Neck", "Chest", (0.0, y(p.neck_y), 0.0)),
        Bone("Head", "Neck", (0.0, y(p.neck_y) + p.head_r * h * 0.95, 0.0)),
    ]

    for side, sx in (("L", 1.0), ("R", -1.0)):
        bones += [
            Bone(f"Shoulder_{side}", "Chest",
                 (sx * sw * 0.36, y(p.shoulder_y), 0.0)),
            Bone(f"UpperArm_{side}", f"Shoulder_{side}",
                 (sx * sw, y(p.shoulder_y) - p.upperarm_r * h * 0.4, 0.0)),
            Bone(f"Forearm_{side}", f"UpperArm_{side}",
                 (sx * sw * 1.07, y(p.elbow_y), 0.0)),
            Bone(f"Hand_{side}", f"Forearm_{side}",
                 (sx * sw * 1.12, y(p.wrist_y), 0.0)),
        ]

    for side, sx in (("L", 1.0), ("R", -1.0)):
        bones += [
            Bone(f"Thigh_{side}", "Hips", (sx * hip_half, y(p.crotch_y), 0.0)),
            Bone(f"Shin_{side}", f"Thigh_{side}",
                 (sx * hip_half * 0.94, y(p.knee_y), 0.0)),
            Bone(f"Foot_{side}", f"Shin_{side}",
                 (sx * hip_half * 0.90, y(p.ankle_y), 0.0)),
            Bone(f"Toe_{side}", f"Foot_{side}",
                 (sx * hip_half * 0.90, y(0.012), p.foot_len * h * 0.62)),
        ]

    return Rig(bones)


#: Which joint drives each mesh part, and which joint it blends into near the
#: start of the segment. Keeps skin weights predictable without a heat solve.
PART_BONES = {
    "torso": ("Spine", "Hips"),
    "chest_shell": ("Chest", "Spine"),
    "neck": ("Neck", "Chest"),
    "head": ("Head", "Neck"),
    "face": ("Head", "Head"),
    "hips": ("Hips", "Hips"),
}

for _side in ("L", "R"):
    PART_BONES[f"shoulder_{_side}"] = (f"Shoulder_{_side}", "Chest")
    PART_BONES[f"upperarm_{_side}"] = (f"UpperArm_{_side}", f"Shoulder_{_side}")
    PART_BONES[f"forearm_{_side}"] = (f"Forearm_{_side}", f"UpperArm_{_side}")
    PART_BONES[f"hand_{_side}"] = (f"Hand_{_side}", f"Forearm_{_side}")
    PART_BONES[f"thigh_{_side}"] = (f"Thigh_{_side}", "Hips")
    PART_BONES[f"shin_{_side}"] = (f"Shin_{_side}", f"Thigh_{_side}")
    PART_BONES[f"foot_{_side}"] = (f"Foot_{_side}", f"Shin_{_side}")
