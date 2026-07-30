"""Builds the character body: mesh groups, skin weights, and morph targets."""

import math

from . import geom, morphs, vecmath as vm
from .rig import PART_BONES, build_rig

#: The torso carries abdominal definition, which needs enough resolution to
#: resolve two rectus straps and the transverse lines between them. Below about
#: 40 segments the six-pack turns into a single lumpy panel.
SEGMENTS_TORSO = 48
TORSO_SUBDIVISIONS = 4
SEGMENTS_LIMB = 22

#: A foot is about 10 cm wide and 6 cm tall, so its cross-section is squashed.
FOOT_ASPECT = 0.66

# Radius profiles along each limb, as (t, multiplier) applied over the linear
# taper. Real limbs are not cones — the mass of a muscle sits at its belly, and a
# straight taper is what makes a figure read as a mannequin.
# Profiles must match in VALUE and roughly in SLOPE where two tubes meet. Equal
# values alone still creases: a radius falling into the elbow that then rises
# again over one segment reads as a ring cut around the joint.
PROFILE_UPPERARM = [(0.0, 1.07), (0.18, 1.03), (0.50, 1.00), (0.84, 0.98),
                    (1.0, 0.98)]
PROFILE_FOREARM = [(0.0, 0.98), (0.16, 1.02), (0.30, 1.05), (0.58, 0.97),
                   (1.0, 1.00)]
#: Thigh: fullest in the upper third, then a hard narrowing into the knee.
PROFILE_THIGH = [(0.0, 0.95), (0.18, 1.04), (0.50, 1.00), (0.86, 0.96),
                 (1.0, 0.95)]
#: Shin: dips just below the knee, swells into the gastrocnemius heads high on
#: the calf, then tapers to an ankle that training barely changes.
#: Matches PROFILE_THIGH's end value at t=0 — a mismatch across the knee shows
#: as a hard ring, and a bulge on one side meeting a dip on the other is worse
#: than either alone.
PROFILE_SHIN = [(0.0, 0.95), (0.16, 0.95), (0.36, 0.99), (0.68, 0.86),
                (1.0, 1.00)]
#: The hand is a flat paddle that follows the forearm.
PROFILE_HAND = [(0.0, 0.80), (0.22, 1.00), (0.70, 1.00), (1.0, 0.72)]


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
        """Key cross-sections of the torso, bottom to top.

        Each entry is `(y, rx, rz, front, back)` where `front`/`back` multiply the
        half-depth on that side. This is what gives the body a side profile
        instead of a straight tube:

        * buttocks project back most just below the trochanter (back 1.16)
        * the lumbar curve pulls the back surface IN at the natural waist (0.84)
        * the abdomen is fullest BELOW the waist, not at it
        * the upper back bulges over the scapulae (back 1.14)

        Every one of those is a real landmark, and their absence is why the first
        version read as a plank when seen from the side.
        """
        p = self.p
        uc = self._upper_chest_y()
        return [
            # the bottom sits high enough that the thigh caps cover it; a lower
            # bottom shows its end cap through the gap between the legs
            (p.crotch_y - 0.006, p.hip_rx * 0.80, p.hip_rz, 0.76, 0.94),
            (p.crotch_y + 0.022, p.hip_rx * 0.95, p.hip_rz, 0.86, 1.16),
            (p.hip_y, p.hip_rx, p.hip_rz, 0.90, 1.12),
            (p.hip_y + 0.038, p.hip_rx * 0.93, p.hip_rz * 0.96, 0.98, 0.96),
            # lower abdomen is fuller than the natural waist above it
            (p.waist_y - 0.028, p.waist_rx * 1.05, p.waist_rz, 1.06, 0.90),
            (p.waist_y, p.waist_rx, p.waist_rz, 0.98, 0.84),
            (p.waist_y + (p.chest_y - p.waist_y) * 0.52,
             p.waist_rx + (p.chest_rx - p.waist_rx) * 0.60,
             p.waist_rz + (p.chest_rz - p.waist_rz) * 0.60, 1.04, 0.95),
            (p.chest_y, p.chest_rx, p.chest_rz, 1.05, 1.03),
            (uc, p.shoulder_rx * 0.97, p.shoulder_rz, 0.98, 1.14),
            (p.shoulder_y, p.shoulder_rx, p.shoulder_rz, 0.90, 1.06),
            # trapezius slope: long enough that the shoulder line does not read
            # as a flat shelf with a head balanced on it
            (p.shoulder_y + 0.016, p.shoulder_rx * 0.70, p.shoulder_rz * 0.86,
             0.88, 1.02),
            (p.shoulder_y + 0.032, p.shoulder_rx * 0.36, p.shoulder_rz * 0.62,
             0.94, 1.00),
            # stop at the neck radius: any wider and the torso reads as a collar
            # with the neck hidden inside it
            (p.neck_y - 0.014, p.neck_r * 0.94, p.neck_r * 0.98, 1.0, 1.0),
        ]

    def _resample(self, sections, subdivisions=TORSO_SUBDIVISIONS):
        """Subdivide key sections into a smooth ring stack."""
        rings = []
        for i in range(len(sections) - 1):
            a, b = sections[i], sections[i + 1]
            for s in range(subdivisions):
                t = s / subdivisions
                # ease the radii so the silhouette curves rather than showing
                # straight facets between key sections
                e = t * t * (3.0 - 2.0 * t)
                rings.append((
                    a[0] + (b[0] - a[0]) * t,
                    *[a[k] + (b[k] - a[k]) * e for k in range(1, len(a))],
                ))
        rings.append(sections[-1])
        return rings

    def _torso_rings(self, scale=1.0):
        h, p = self.p.height, self.p
        return [
            {"center": (0.0, y * h, 0.0),
             "rx": rx * h * scale, "rz": rz * h * scale,
             "rz_front": rz * front * h * scale,
             "rz_back": rz * back * h * scale,
             "squash": p.torso_squash,
             "y": y}
            for (y, rx, rz, front, back) in self._resample(self._torso_sections())
        ]

    def _build_torso(self, mesh):
        geom.loft(mesh, self._torso_rings(), "torso",
                  segments=SEGMENTS_TORSO, cap_start=True, cap_end=True)

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
        elbow_r = p.forearm_r * h * 1.02
        geom.tube(mesh, upper, elbow,
                  p.upperarm_r * h, elbow_r,
                  f"upperarm_{side}", segments=SEGMENTS_LIMB, slices=14,
                  profile=PROFILE_UPPERARM,
                  cap_start=False, cap_end=False,
                  round_start=p.upperarm_r * h * 1.30)
        # matching radii across the elbow keep the two tubes seamless
        geom.tube(mesh, elbow, wrist,
                  elbow_r, p.wrist_r * h * 1.10,
                  f"forearm_{side}", segments=SEGMENTS_LIMB, slices=12,
                  profile=PROFILE_FOREARM,
                  cap_start=False, cap_end=False)

        # A mitten built ALONG the forearm, not a world-axis-aligned ellipsoid.
        # With the arm abducted 47 degrees, a sphere scaled on world Y elongates
        # vertically while the arm points diagonally — the hand ended up
        # crossing its own wrist.
        arm_dir = vm.normalize(vm.sub(wrist, elbow))
        hand_tip = vm.add(wrist, vm.mul(arm_dir, p.hand_len * h * 0.88))
        geom.tube(mesh, wrist, hand_tip,
                  p.wrist_r * h * 1.55, p.wrist_r * h * 1.35,
                  f"hand_{side}", segments=SEGMENTS_LIMB, slices=7,
                  profile=PROFILE_HAND, aspect_x=0.46,
                  cap_start=False, round_end=p.wrist_r * h * 0.9)

    def _foot_axis(self, ankle, toe):
        """Heel and toe-tip of a foot whose SOLE lies flat on y = 0.

        The sole is the one part of the body whose position is not negotiable:
        the character stands on it. Placing the foot as a tube centred on the
        ankle joint left the sole floating and made the figure measure 0.4%
        taller than its stated height, since the vertex is fixed at the top.

        Both ends sit at their own radius above the ground, so the tube's lowest
        surface is y = 0 along its whole length rather than only at one end.
        """
        p, h = self.p, self.p.height
        r_heel = p.foot_r * h * 0.60
        r_tip = p.foot_r * h * 0.40
        heel = (ankle[0], r_heel * FOOT_ASPECT,
                ankle[2] - p.foot_len * h * 0.23)
        tip = (toe[0], r_tip * FOOT_ASPECT, toe[2])
        return heel, tip, r_heel, r_tip

    def _build_leg(self, mesh, side):
        p, rig, h = self.p, self.rig, self.p.height
        hip = rig.world(f"Thigh_{side}")
        knee = rig.world(f"Shin_{side}")
        ankle = rig.world(f"Foot_{side}")
        toe = rig.world(f"Toe_{side}")

        knee_r = p.shin_r * h * 1.10
        # the thigh's start cap reaches up over the crotch and hides where the
        # torso loft is capped off
        geom.tube(mesh, hip, knee,
                  p.thigh_r * h, knee_r,
                  f"thigh_{side}", segments=SEGMENTS_LIMB, slices=14,
                  profile=PROFILE_THIGH,
                  cap_end=False,
                  round_start=p.thigh_r * h * geom.profile_at(PROFILE_THIGH, 0.0)
                  * 0.85)
        geom.tube(mesh, knee, ankle,
                  knee_r, p.ankle_r * h * 1.15,
                  f"shin_{side}", segments=SEGMENTS_LIMB, slices=14,
                  profile=PROFILE_SHIN,
                  cap_start=False, cap_end=False)
        # The foot starts BEHIND the ankle so the character has a heel. Running
        # it from the ankle joint forward left the leg balanced on the front of
        # its own ankle, which is a large part of why the figure looked unstable.
        heel, tip, r_heel, r_tip = self._foot_axis(ankle, toe)
        geom.tube(mesh, heel, tip, r_heel, r_tip,
                  f"foot_{side}", segments=SEGMENTS_LIMB, slices=7,
                  aspect=FOOT_ASPECT,
                  round_start=r_heel * 0.42,
                  round_end=r_tip * 0.80)

    def _build_outfit(self, mesh):
        """Shorts for everyone, plus a crop top on the female preset.

        The outfit is a shell offset from the body and tagged with the same part
        names, so it inherits the body's skin weights and morph masks and grows
        with whatever is underneath it.
        """
        p, rig, h = self.p, self.rig, self.p.height
        pad = 1.042

        # the waistband sits ON the hip, below where the abdominal fat morph
        # starts: any higher and the shorts inflate with the belly and read as a
        # nappy rather than as athletic shorts. Both ends stay open — a capped
        # waistband shows a disc floating between the legs.
        geom.loft(
            mesh,
            [r for r in self._torso_rings(scale=pad)
             if p.crotch_y + 0.012 <= r["y"] <= p.hip_y + 0.014],
            "torso", segments=SEGMENTS_TORSO, cap_start=False, cap_end=False,
        )

        for side in ("L", "R"):
            hip = rig.world(f"Thigh_{side}")
            knee = rig.world(f"Shin_{side}")
            leg_dir = vm.normalize(vm.sub(knee, hip))
            thigh_len = vm.length(vm.sub(knee, hip))
            # Placed as a fraction ALONG THE THIGH, starting just above the
            # femoral head so it tucks inside the waistband. Offsets relative to
            # the old crotch-rooted hip sent the cuff up past the waistband and
            # left a hole between the two.
            geom.tube(mesh,
                      vm.add(hip, vm.mul(leg_dir, -thigh_len * 0.03)),
                      vm.add(hip, vm.mul(leg_dir, thigh_len * 0.50)),
                      p.thigh_r * h * pad * geom.profile_at(PROFILE_THIGH, 0.0),
                      p.thigh_r * h * pad * geom.profile_at(PROFILE_THIGH, 0.50),
                      f"thigh_{side}", segments=SEGMENTS_LIMB, slices=6,
                      cap_start=False, cap_end=False)

            # trainers: a shell over the foot, which also stops the bare foot
            # from reading as a pale detached blob at the end of the leg
            ankle = rig.world(f"Foot_{side}")
            toe = rig.world(f"Toe_{side}")
            heel, tip, r_heel, r_tip = self._foot_axis(ankle, toe)
            geom.tube(mesh, heel, tip, r_heel * pad, r_tip * pad,
                      f"foot_{side}", segments=SEGMENTS_LIMB, slices=7,
                      aspect=FOOT_ASPECT,
                      round_start=r_heel * 0.42,
                      round_end=r_tip * 0.80)

        if p.tags.get("sex") == "female":
            geom.loft(
                mesh,
                [r for r in self._torso_rings(scale=pad)
                 if p.chest_y - 0.058 <= r["y"] <= p.shoulder_y - 0.022],
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

    def bounds(self):
        """Axis-aligned bounds of every mesh, at rest.

        Exposed so the app can frame the character without guessing, and so a
        test can assert the figure is exactly as tall as it claims — it stood
        3.6% over for a while and nothing caught it.
        """
        lo = [float("inf")] * 3
        hi = [float("-inf")] * 3
        for g in self.groups:
            for pos in g.mesh.positions:
                for i in range(3):
                    lo[i] = min(lo[i], pos[i])
                    hi[i] = max(hi[i], pos[i])
        return [round(v, 5) for v in lo], [round(v, 5) for v in hi]

    def stats(self):
        lo, hi = self.bounds()
        return {
            "boundsMin": lo,
            "boundsMax": hi,
            "measuredHeight": round(hi[1] - lo[1], 5),
            "vertices": sum(g.mesh.vertex_count for g in self.groups),
            "triangles": sum(g.mesh.triangle_count for g in self.groups),
            "joints": len(self.rig.bones),
            "morphTargets": len(self.morph_groups),
            "muscleGroups": sum(1 for g in self.morph_groups
                                if g.kind == "muscle"),
        }
