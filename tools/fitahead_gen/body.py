"""Builds the character body: mesh groups, skin weights, and morph targets."""

import math

from . import geom, morphs, vecmath as vm
from .rig import PART_BONES, build_rig

#: The torso carries abdominal definition, which needs enough resolution to
#: resolve two rectus straps and the transverse lines between them. Below about
#: 40 segments the six-pack turns into a single lumpy panel.
SEGMENTS_TORSO = 48
TORSO_SUBDIVISIONS = 4
SEGMENTS_LIMB = 20


class MeshGroup:
    """One mesh + material pairing that becomes a glTF mesh node."""

    def __init__(self, mesh, material, morphable=True, textured=False):
        self.mesh = mesh
        self.material = material  # "skin" | "face" | "accent"
        self.morphable = morphable
        #: Only textured meshes carry UVs; the body and outfit are flat colours,
        #: and an unused TEXCOORD_0 is dead payload in every vertex.
        self.textured = textured
        self.joints = []   # per-vertex list of 4 joint indices
        self.weights = []  # per-vertex list of 4 weights
        self.targets = []  # list of {name, positions, normals}


class Character:
    def __init__(self, params):
        self.p = params
        self.rig = build_rig(params)
        self.morph_groups = morphs.build_groups(params)
        self.groups = []
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self):
        p, rig, h = self.p, self.rig, self.p.height

        body = geom.MeshData("Body")
        self._build_torso(body)
        self._build_head_and_neck(body)
        for side in ("L", "R"):
            self._build_arm(body, side)
            self._build_leg(body, side)
        body.compute_normals()

        face = geom.MeshData("Face")
        head_c = rig.world("Head")
        geom.spherical_cap(
            face, head_c, p.head_r * h,
            half_angle=math.asin(min(p.face_r_ratio, 0.995)),
            part="face", scale=(1.0, p.head_squash_y, p.head_squash_z),
            segments=40, rings=12,
        )
        face.compute_normals()

        outfit = geom.MeshData("Outfit")
        self._build_outfit(outfit)
        outfit.compute_normals()

        self.groups = [
            MeshGroup(body, "skin"),
            MeshGroup(face, "face", morphable=False, textured=True),
            MeshGroup(outfit, "accent"),
        ]

        ctx = morphs.MaskContext(p, rig)
        for group in self.groups:
            self._skin(group)
            if group.morphable:
                self._bake_morphs(group, ctx)

    def _upper_chest_y(self):
        p = self.p
        return p.chest_y + (p.shoulder_y - p.chest_y) * 0.62

    def _torso_sections(self):
        """Key cross-sections of the torso, bottom to top."""
        p = self.p
        uc = self._upper_chest_y()
        return [
            # the bottom sits high enough that the thigh caps cover it; a lower
            # bottom shows its end cap through the gap between the legs
            (p.crotch_y - 0.008, p.hip_rx * 0.84, p.hip_rz * 0.86),
            (p.crotch_y + 0.025, p.hip_rx * 0.97, p.hip_rz * 0.96),
            (p.hip_y, p.hip_rx, p.hip_rz),
            (p.waist_y, p.waist_rx, p.waist_rz),
            (p.waist_y + (p.chest_y - p.waist_y) * 0.55,
             p.waist_rx + (p.chest_rx - p.waist_rx) * 0.66,
             p.waist_rz + (p.chest_rz - p.waist_rz) * 0.66),
            (p.chest_y, p.chest_rx, p.chest_rz),
            (uc, p.shoulder_rx * 0.97, p.shoulder_rz * 1.0),
            (p.shoulder_y, p.shoulder_rx, p.shoulder_rz),
            # trapezius slope: long enough that the shoulder line does not read
            # as a flat shelf with a head balanced on it
            (p.shoulder_y + 0.016, p.shoulder_rx * 0.70, p.shoulder_rz * 0.86),
            (p.shoulder_y + 0.032, p.shoulder_rx * 0.36, p.shoulder_rz * 0.62),
            # stop at the neck radius: any wider and the torso reads as a collar
            # with the neck hidden inside it
            (p.neck_y - 0.012, p.neck_r * 1.12, p.neck_r * 1.18),
        ]

    def _resample(self, sections, subdivisions=TORSO_SUBDIVISIONS):
        """Subdivide key sections into a smooth ring stack."""
        rings = []
        for i in range(len(sections) - 1):
            y0, rx0, rz0 = sections[i]
            y1, rx1, rz1 = sections[i + 1]
            for s in range(subdivisions):
                t = s / subdivisions
                # ease the radius so the silhouette curves rather than showing
                # straight facets between key sections
                e = t * t * (3.0 - 2.0 * t)
                rings.append((y0 + (y1 - y0) * t,
                              rx0 + (rx1 - rx0) * e,
                              rz0 + (rz1 - rz0) * e))
        rings.append(sections[-1])
        return rings

    def _build_torso(self, mesh):
        h, p = self.p.height, self.p
        rings = [
            {"center": (0.0, y * h, 0.0), "rx": rx * h, "rz": rz * h,
             "squash": p.torso_squash}
            for (y, rx, rz) in self._resample(self._torso_sections())
        ]
        geom.loft(mesh, rings, "torso", segments=SEGMENTS_TORSO,
                  cap_start=True, cap_end=True)

    def _build_head_and_neck(self, mesh):
        p, rig, h = self.p, self.rig, self.p.height
        neck_base = (0.0, (p.shoulder_y + 0.012) * h, 0.0)
        head_c = rig.world("Head")
        neck_top = (0.0, head_c[1] - p.head_r * h * 0.70, 0.0)
        geom.tube(mesh, neck_base, neck_top,
                  p.neck_r * h * 1.04, p.neck_r * h * 0.92,
                  "neck", segments=SEGMENTS_LIMB, slices=5,
                  cap_start=False, cap_end=False)
        geom.sphere(mesh, head_c, p.head_r * h, "head",
                    segments=32, rings=24,
                    scale=(1.0, p.head_squash_y, p.head_squash_z))

    def _build_arm(self, mesh, side):
        p, rig, h = self.p, self.rig, self.p.height
        upper = rig.world(f"UpperArm_{side}")
        elbow = rig.world(f"Forearm_{side}")
        wrist = rig.world(f"Hand_{side}")

        # The deltoid is the upper arm's own rounded cap rather than a separate
        # sphere: a standalone ball leaves a crease where it meets the tube, and
        # the crease is exactly where the delts morph swells. The cap radius is
        # generous enough to overlap the torso, so the joint reads as continuous.
        elbow_r = p.forearm_r * h * 1.12
        geom.tube(mesh, upper, elbow,
                  p.upperarm_r * h, elbow_r,
                  f"upperarm_{side}", segments=SEGMENTS_LIMB, slices=12,
                  cap_start=False, cap_end=False,
                  round_start=p.upperarm_r * h * 1.25)
        # matching radii across the elbow keep the two tubes seamless
        geom.tube(mesh, elbow, wrist,
                  elbow_r, p.wrist_r * h * 1.20,
                  f"forearm_{side}", segments=SEGMENTS_LIMB, slices=10,
                  cap_start=False, cap_end=False)

        # mitten-shaped hand: flattened front-to-back, elongated down the arm
        arm_dir = vm.normalize(vm.sub(wrist, elbow))
        hand_c = vm.add(wrist, vm.mul(arm_dir, p.hand_r * h * 0.55))
        geom.sphere(mesh, hand_c, p.hand_r * h, f"hand_{side}",
                    segments=18, rings=14, scale=(0.60, 1.30, 0.42))

    def _build_leg(self, mesh, side):
        p, rig, h = self.p, self.rig, self.p.height
        hip = rig.world(f"Thigh_{side}")
        knee = rig.world(f"Shin_{side}")
        ankle = rig.world(f"Foot_{side}")
        toe = rig.world(f"Toe_{side}")

        knee_r = p.shin_r * h * 1.06
        # the thigh's start cap reaches up over the crotch and hides where the
        # torso loft is capped off
        geom.tube(mesh, hip, knee,
                  p.thigh_r * h, knee_r,
                  f"thigh_{side}", segments=SEGMENTS_LIMB, slices=12,
                  cap_end=False, round_start=p.thigh_r * h * 0.95)
        geom.tube(mesh, knee, ankle,
                  knee_r, p.ankle_r * h * 1.25,
                  f"shin_{side}", segments=SEGMENTS_LIMB, slices=12,
                  cap_start=False, cap_end=False)
        geom.tube(mesh, ankle, toe,
                  p.foot_r * h * 0.78, p.foot_r * h * 0.52,
                  f"foot_{side}", segments=SEGMENTS_LIMB, slices=5,
                  round_start=p.foot_r * h * 0.62,
                  round_end=p.foot_r * h * 0.50)

    def _build_outfit(self, mesh):
        """Shorts for everyone, plus a crop top on the female preset.

        The outfit is a shell offset from the body and tagged with the same part
        names, so it inherits the body's skin weights and morph masks and grows
        with whatever is underneath it.
        """
        p, rig, h = self.p, self.rig, self.p.height
        pad = 1.042

        shorts = [
            (y, rx * pad, rz * pad)
            for (y, rx, rz) in self._resample(self._torso_sections())
            # the waistband sits ON the hip, below where the abdominal fat morph
            # starts: any higher and the shorts inflate with the belly and read
            # as a nappy rather than as athletic shorts
            if p.crotch_y - 0.018 <= y <= p.hip_y + 0.016
        ]
        # both ends open: a capped waistband would show a disc floating between
        # the legs, and the body underneath already closes the silhouette
        geom.loft(
            mesh,
            [{"center": (0.0, y * h, 0.0), "rx": rx * h, "rz": rz * h,
              "squash": p.torso_squash} for (y, rx, rz) in shorts],
            "torso", segments=SEGMENTS_TORSO, cap_start=False, cap_end=False,
        )

        for side in ("L", "R"):
            hip = rig.world(f"Thigh_{side}")
            knee = rig.world(f"Shin_{side}")
            leg_dir = vm.normalize(vm.sub(knee, hip))
            thigh_len = vm.length(vm.sub(knee, hip))
            # start above the hip joint so the cuff overlaps the waistband
            geom.tube(mesh,
                      vm.add(hip, vm.mul(leg_dir, -thigh_len * 0.34)),
                      vm.add(hip, vm.mul(leg_dir, thigh_len * 0.52)),
                      p.thigh_r * h * pad, p.thigh_r * h * 0.92 * pad,
                      f"thigh_{side}", segments=SEGMENTS_LIMB, slices=5,
                      cap_start=False, cap_end=False)

            # trainers: a shell over the foot, which also stops the bare foot
            # from reading as a pale detached blob at the end of the leg
            ankle = rig.world(f"Foot_{side}")
            toe = rig.world(f"Toe_{side}")
            foot_dir = vm.normalize(vm.sub(toe, ankle))
            geom.tube(mesh,
                      vm.add(ankle, vm.mul(foot_dir, -0.012 * h)), toe,
                      p.foot_r * h * 0.78 * pad, p.foot_r * h * 0.52 * pad,
                      f"foot_{side}", segments=SEGMENTS_LIMB, slices=5,
                      round_start=p.foot_r * h * 0.62,
                      round_end=p.foot_r * h * 0.50)

        if p.tags.get("sex") == "female":
            top = [
                (y, rx * pad, rz * pad)
                for (y, rx, rz) in self._resample(self._torso_sections())
                if p.chest_y - 0.055 <= y <= p.shoulder_y - 0.020
            ]
            geom.loft(
                mesh,
                [{"center": (0.0, y * h, 0.0), "rx": rx * h, "rz": rz * h,
                  "squash": p.torso_squash} for (y, rx, rz) in top],
                "torso", segments=SEGMENTS_TORSO, cap_start=False,
                cap_end=False,
            )

    # -- skinning ----------------------------------------------------------

    def _skin(self, group):
        rig = self.rig
        mesh = group.mesh
        for i in range(mesh.vertex_count):
            part = mesh.parts[i]
            pos = mesh.positions[i]
            if part == "torso":
                pairs = self._torso_weights(pos)
            else:
                primary, parent = PART_BONES.get(part, ("Hips", "Hips"))
                if primary == parent:
                    pairs = [(primary, 1.0)]
                else:
                    t = vm.clamp01(
                        vm.dist_point_segment(pos, *rig.segment(primary))[1]
                    )
                    blend = vm.smoothstep(0.0, 0.32, t)
                    pairs = [(primary, blend), (parent, 1.0 - blend)]
            joints, weights = self._pack_influences(pairs)
            group.joints.append(joints)
            group.weights.append(weights)

    def _torso_weights(self, pos):
        """Blend the spine chain by height.

        Anchors are the joint heights themselves, so a vertex level with a joint
        is fully owned by it and vertices between two joints share them. Only two
        influences are ever non-zero, which keeps the deformation predictable.
        """
        p = self.p
        y = pos[1] / p.height
        anchors = [
            ("Hips", p.hip_y),
            ("Spine", p.waist_y),
            ("Chest", p.chest_y),
            ("UpperChest", self._upper_chest_y()),
        ]
        if y <= anchors[0][1]:
            return [(anchors[0][0], 1.0)]
        if y >= anchors[-1][1]:
            return [(anchors[-1][0], 1.0)]
        for (lo_name, lo_y), (hi_name, hi_y) in zip(anchors, anchors[1:]):
            if lo_y <= y <= hi_y:
                t = (y - lo_y) / max(hi_y - lo_y, 1e-9)
                # smoothstep rather than linear: a linear blend creases visibly
                # at the anchor heights when the spine bends
                t = t * t * (3.0 - 2.0 * t)
                return [(lo_name, 1.0 - t), (hi_name, t)]
        return [(anchors[-1][0], 1.0)]

    def _pack_influences(self, pairs):
        """Normalise (bone, weight) pairs into the fixed 4-wide glTF layout.

        Joint slots whose weight rounds to zero are forced to index 0: the spec
        treats a non-zero joint index paired with a zero weight as a validation
        warning, and some runtimes still count it against the 4-influence budget.
        """
        kept = [(self.rig.by_name[n].index, max(0.0, w))
                for n, w in pairs if w > 1e-6]
        kept.sort(key=lambda iw: -iw[1])
        kept = kept[:4]
        total = sum(w for _, w in kept) or 1.0

        joints = [0, 0, 0, 0]
        weights = [0.0, 0.0, 0.0, 0.0]
        for slot, (index, weight) in enumerate(kept):
            joints[slot] = index
            weights[slot] = weight / total
        return joints, weights

    # -- morph targets -----------------------------------------------------

    def _bake_morphs(self, group, ctx):
        mesh = group.mesh
        h = self.p.height
        for grp in self.morph_groups:
            displacement = grp.amount * h
            deltas = []
            touched = 0
            positions = list(mesh.positions)
            for i in range(mesh.vertex_count):
                m = grp.mask(ctx, mesh.parts[i], mesh.positions[i],
                             mesh.normals[i])
                # masks may be negative: grooves such as the linea alba and the
                # transverse ab lines pull the surface in
                if abs(m) <= 1e-4:
                    deltas.append((0.0, 0.0, 0.0))
                    continue
                touched += 1
                d = vm.mul(mesh.normals[i], displacement * m)
                deltas.append(d)
                positions[i] = vm.add(mesh.positions[i], d)

            if touched == 0:
                # a group that touches nothing in this mesh still needs a slot:
                # glTF requires every primitive of a mesh to expose the same
                # target count in the same order
                zeros = [(0.0, 0.0, 0.0)] * mesh.vertex_count
                group.targets.append({"name": grp.name, "positions": zeros,
                                      "normals": zeros, "touched": 0})
                continue

            morphed_normals = geom.compute_normals_for(positions, mesh.indices)
            normal_deltas = [vm.sub(morphed_normals[i], mesh.normals[i])
                             for i in range(mesh.vertex_count)]
            group.targets.append({"name": grp.name, "positions": deltas,
                                  "normals": normal_deltas, "touched": touched})

    # -- reporting ---------------------------------------------------------

    def stats(self):
        return {
            "vertices": sum(g.mesh.vertex_count for g in self.groups),
            "triangles": sum(g.mesh.triangle_count for g in self.groups),
            "joints": len(self.rig.bones),
            "morphTargets": len(self.morph_groups),
            "muscleGroups": sum(1 for g in self.morph_groups
                                if g.kind == "muscle"),
        }
