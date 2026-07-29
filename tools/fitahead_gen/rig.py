"""Skeleton definition.

Joint positions come from `anthro.HEIGHTS`, so the skeleton is anthropometric.
It is also FIXED across every body type: biacromial breadth, limb lengths and
joint centres are bone, and training does not move them. Everything that
distinguishes 마른 / 평범 / 근육질 is soft tissue, which is why they share one rig
and differ only in morph weights.

Node names are our own readable ones. Interoperability comes from the
`HUMANOID_BONES` map below, which is emitted both into the runtime manifest and
into the `EXT_skeleton_humanoid` glTF extension — that extension exists exactly
so a rig does not have to rename its nodes to be understood.
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
    sw = p.shoulder_half_w * h  # biacromial / 2 — where the arm hangs

    # The thoracic spine is split into Chest and UpperChest. Two segments let
    # the upper back round independently of the lower, which is what a shrug or
    # a row looks like, and it matches the humanoid bone set.
    upper_chest_y = p.chest_y + (p.shoulder_y - p.chest_y) * 0.62

    bones = [
        Bone("Root", None, (0.0, 0.0, 0.0)),
        Bone("Hips", "Root", (0.0, y(p.hip_y), 0.0)),
        Bone("Spine", "Hips", (0.0, y(p.waist_y), 0.0)),
        Bone("Chest", "Spine", (0.0, y(p.chest_y), 0.0)),
        Bone("UpperChest", "Chest", (0.0, y(upper_chest_y), 0.0)),
        Bone("Neck", "UpperChest", (0.0, y(p.neck_y), 0.0)),
        Bone("Head", "Neck", (0.0, y(p.head_center_y), 0.0)),
    ]

    for side, sx in (("L", 1.0), ("R", -1.0)):
        bones += [
            Bone(f"Shoulder_{side}", "UpperChest",
                 (sx * sw * 0.34, y(p.shoulder_y), 0.0)),
            Bone(f"UpperArm_{side}", f"Shoulder_{side}",
                 (sx * sw, y(p.shoulder_y) - p.upperarm_r * h * 0.5, 0.0)),
            Bone(f"Forearm_{side}", f"UpperArm_{side}",
                 (sx * sw * 1.05, y(p.elbow_y), 0.0)),
            Bone(f"Hand_{side}", f"Forearm_{side}",
                 (sx * sw * 1.09, y(p.wrist_y), 0.0)),
        ]

    for side, sx in (("L", 1.0), ("R", -1.0)):
        bones += [
            Bone(f"Thigh_{side}", "Hips", (sx * hip_half, y(p.crotch_y), 0.0)),
            Bone(f"Shin_{side}", f"Thigh_{side}",
                 (sx * hip_half * 0.94, y(p.knee_y), 0.0)),
            Bone(f"Foot_{side}", f"Shin_{side}",
                 (sx * hip_half * 0.90, y(p.ankle_y), 0.0)),
            Bone(f"Toe_{side}", f"Foot_{side}",
                 (sx * hip_half * 0.90, y(0.012), p.foot_len * h * 0.60)),
        ]

    return Rig(bones)


#: Our node name -> EXT_skeleton_humanoid bone name.
#:
#: Draft extension (takahirox/EXT_skeleton_humanoid), derived from the VRM
#: humanoid bone set. Emitting it is purely additive metadata: it lets humanoid
#: animation authored against any other rig be remapped onto this one by bone
#: role instead of by node index. Every bone in the set is optional, so the
#: finger and eye bones we do not have are simply absent.
HUMANOID_BONES = {
    "Hips": "hips",
    "Spine": "spine",
    "Chest": "chest",
    "UpperChest": "upperChest",
    "Neck": "neck",
    "Head": "head",
    "Shoulder_L": "leftShoulder",
    "UpperArm_L": "leftUpperArm",
    "Forearm_L": "leftLowerArm",
    "Hand_L": "leftHand",
    "Shoulder_R": "rightShoulder",
    "UpperArm_R": "rightUpperArm",
    "Forearm_R": "rightLowerArm",
    "Hand_R": "rightHand",
    "Thigh_L": "leftUpperLeg",
    "Shin_L": "leftLowerLeg",
    "Foot_L": "leftFoot",
    "Toe_L": "leftToes",
    "Thigh_R": "rightUpperLeg",
    "Shin_R": "rightLowerLeg",
    "Foot_R": "rightFoot",
    "Toe_R": "rightToes",
}

EXT_HUMANOID = "EXT_skeleton_humanoid"


#: Which joint drives each mesh part, and which joint it blends into near the
#: start of the segment. Keeps skin weights predictable without a heat solve.
PART_BONES = {
    "neck": ("Neck", "UpperChest"),
    "head": ("Head", "Neck"),
    "face": ("Head", "Head"),
}

for _side in ("L", "R"):
    PART_BONES[f"shoulder_{_side}"] = (f"Shoulder_{_side}", "UpperChest")
    PART_BONES[f"upperarm_{_side}"] = (f"UpperArm_{_side}", f"Shoulder_{_side}")
    PART_BONES[f"forearm_{_side}"] = (f"Forearm_{_side}", f"UpperArm_{_side}")
    PART_BONES[f"hand_{_side}"] = (f"Hand_{_side}", f"Forearm_{_side}")
    PART_BONES[f"thigh_{_side}"] = (f"Thigh_{_side}", "Hips")
    PART_BONES[f"shin_{_side}"] = (f"Shin_{_side}", f"Thigh_{_side}")
    PART_BONES[f"foot_{_side}"] = (f"Foot_{_side}", f"Shin_{_side}")
