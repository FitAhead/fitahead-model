"""Builds the character body: mesh groups, skin weights, and morph targets."""

import math

from . import deform, geom, hand, morphs, outfit, vecmath as vm
from .rig import build_rig

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
#: How far the thigh tube reaches ABOVE the hip joint, as a fraction of stature.
#: The tube is buried inside the pelvis so its top never becomes a visible
#: surface; what shows is the line where the thigh emerges from the hip, which is
#: the inguinal (groin) fold. Capping the thigh at the hip joint instead left a
#: sphere intersecting the torso and the other thigh, and the resulting shelf was
#: the ugliest thing on the model once the shorts stopped hiding it.
THIGH_OVERLAP = 0.058


def _shift_profile(profile, t0, head_value):
    """Remap a 0..1 profile into t0..1, holding `head_value` before t0."""
    return ([(0.0, head_value)]
            + [(t0 + t * (1.0 - t0), v) for t, v in profile])


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

        self.groups = [
            MeshGroup(body, "skin"),
            MeshGroup(face, "face", morphable=False, textured=True),
        ]
        if p.sex == "male":
            self.groups.append(MeshGroup(outfit.build_shorts(p, rig), "accent"))

        ctx = morphs.MaskContext(p, rig)
        for group in self.groups:
            deform.skin(self, group)
            if group.morphable:
                deform.bake_morphs(self, group, ctx)

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
            (p.crotch_y + 0.030, p.hip_rx * 0.54, p.hip_rz * 0.86, 0.74, 0.92),
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
        # One tube through shoulder, elbow and wrist: the elbow ring is shared,
        # so there is no seam there at all.
        elbow_r = p.forearm_r * h * 1.02
        geom.polytube(
            mesh,
            [(upper, p.upperarm_r * h), (elbow, elbow_r),
             (wrist, p.wrist_r * h * 1.10)],
            [f"upperarm_{side}", f"forearm_{side}"],
            profiles=[PROFILE_UPPERARM, PROFILE_FOREARM],
            segments=SEGMENTS_LIMB, slices=13,
            cap_start=False, cap_end=False,
            round_start=p.upperarm_r * h * 1.30)

        hand.build(mesh, p, rig, side)

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
        leg_dir = vm.normalize(vm.sub(knee, hip))
        thigh_len = vm.length(vm.sub(knee, hip))
        over = THIGH_OVERLAP * h
        top = vm.add(hip, vm.mul(leg_dir, -over))
        t0 = over / (thigh_len + over)
        # one tube through hip, knee and ankle — shared knee ring, no seam
        geom.polytube(
            mesh,
            [(top, p.thigh_r * h), (knee, knee_r),
             (ankle, p.ankle_r * h * 1.15)],
            [f"thigh_{side}", f"shin_{side}"],
            profiles=[_shift_profile(PROFILE_THIGH, t0, 1.22), PROFILE_SHIN],
            segments=SEGMENTS_LIMB, slices=15,
            cap_start=True, cap_end=False)
        # The foot starts BEHIND the ankle so the character has a heel. Running
        # it from the ankle joint forward left the leg balanced on the front of
        # its own ankle, which is a large part of why the figure looked unstable.
        heel, tip, r_heel, r_tip = self._foot_axis(ankle, toe)
        geom.tube(mesh, heel, tip, r_heel, r_tip,
                  f"foot_{side}", segments=SEGMENTS_LIMB, slices=7,
                  aspect=FOOT_ASPECT,
                  round_start=r_heel * 0.42,
                  round_end=r_tip * 0.80)

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
