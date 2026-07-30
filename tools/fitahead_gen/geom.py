"""Procedural mesh primitives for the FitAhead character.

The body is built from lofted tubes (limbs, torso) and spheres (head, joints).
Every vertex carries a `part` tag so the skinning and morph-target passes can
address "the left biceps" without a separate selection step.

Faces are wound by comparing each candidate normal against an outward reference
point rather than by reasoning about basis handedness per primitive — the two
conventions disagree between a vertical torso loft and an arbitrary-axis limb
tube, and getting it wrong only shows up as invisible backfaces at render time.
"""

import math

from . import vecmath as vm


class MeshData:
    """Accumulates a triangle mesh: positions, normals, uvs, indices, tags."""

    def __init__(self, name="mesh"):
        self.name = name
        self.positions = []
        self.normals = []
        self.uvs = []
        self.indices = []
        self.parts = []  # per-vertex part tag, e.g. "upperarm_L"

    @property
    def vertex_count(self):
        return len(self.positions)

    @property
    def triangle_count(self):
        return len(self.indices) // 3

    def add_vertex(self, position, uv, part):
        self.positions.append(tuple(position))
        self.uvs.append(tuple(uv))
        self.parts.append(part)
        self.normals.append((0.0, 0.0, 0.0))
        return len(self.positions) - 1

    def add_triangle(self, a, b, c):
        self.indices.extend((a, b, c))

    def add_triangle_facing(self, a, b, c, ref):
        """Add a triangle wound so its normal points away from `ref`."""
        pa, pb, pc = self.positions[a], self.positions[b], self.positions[c]
        n = vm.cross(vm.sub(pb, pa), vm.sub(pc, pa))
        centroid = vm.mul(vm.add(vm.add(pa, pb), pc), 1.0 / 3.0)
        if vm.dot(n, vm.sub(centroid, ref)) < 0.0:
            self.indices.extend((a, c, b))
        else:
            self.indices.extend((a, b, c))

    def add_quad_facing(self, a, b, c, d, ref):
        self.add_triangle_facing(a, b, c, ref)
        pa, pb, pc = self.positions[a], self.positions[b], self.positions[c]
        # keep the second triangle consistent with whatever the first chose
        flipped = self.indices[-2] == c
        if flipped:
            self.indices.extend((a, d, c))
        else:
            self.indices.extend((a, c, d))

    def compute_normals(self, weld=True):
        self.normals = compute_normals_for(self.positions, self.indices)
        if weld:
            self.normals = weld_normals(self.positions, self.normals)


def weld_normals(positions, normals, tolerance=2e-4):
    """Average normals across coincident vertices.

    Limb tubes are built as separate lofts that meet at shared positions but not
    shared indices, so each side of a seam gets normals from its own triangles
    only. The result is a hard shading line ringing every knee, elbow and hip
    even when the two radii match exactly.

    Welding for SHADING only: indices and positions are untouched, so the
    topology the morph targets are baked against does not change.
    """
    canonical = {}
    remap = []
    for i, pos in enumerate(positions):
        key = (round(pos[0] / tolerance), round(pos[1] / tolerance),
               round(pos[2] / tolerance))
        remap.append(canonical.setdefault(key, i))

    acc = {}
    for i, n in enumerate(normals):
        c = remap[i]
        acc[c] = vm.add(acc.get(c, (0.0, 0.0, 0.0)), n)
    return [vm.normalize(acc[remap[i]]) for i in range(len(positions))]


def compute_normals_for(positions, indices):
    """Area-weighted smooth vertex normals."""
    acc = [(0.0, 0.0, 0.0)] * len(positions)
    for i in range(0, len(indices), 3):
        ia, ib, ic = indices[i], indices[i + 1], indices[i + 2]
        pa, pb, pc = positions[ia], positions[ib], positions[ic]
        # the unnormalized cross product weights by triangle area, which is the
        # cheap way to get sane normals on unevenly tessellated lofts
        n = vm.cross(vm.sub(pb, pa), vm.sub(pc, pa))
        acc[ia] = vm.add(acc[ia], n)
        acc[ib] = vm.add(acc[ib], n)
        acc[ic] = vm.add(acc[ic], n)
    return [vm.normalize(n) for n in acc]


def _ellipse_point(angle, rx, rz_front, rz_back, squash=1.0):
    """Point on a cross-section that may differ front to back.

    A human torso is not an ellipse at any height. The pelvis is deep behind and
    shallow in front, the small of the back curves IN while the abdomen curves
    out, and the upper back bulges over the scapulae. One radius per axis cannot
    express that, so front and back depth are independent.
    """
    c, s = math.cos(angle), math.sin(angle)
    rz = rz_front if s >= 0.0 else rz_back
    if abs(squash - 1.0) < 1e-6:
        return c * rx, s * rz
    e = 1.0 / squash
    fx = math.copysign(abs(c) ** e, c)
    fz = math.copysign(abs(s) ** e, s)
    return fx * rx, fz * rz


def loft(mesh, rings, part, segments=24, cap_start=False, cap_end=False):
    """Build a tube through a list of cross-section rings.

    Each ring is a dict: {center, rx, rz, rz_front?, rz_back?, squash?, right?,
    forward?}. `rz_front`/`rz_back` default to `rz`. `right`/`forward` define the
    ring plane and default to world X/Z, so a vertical stack of rings (the torso)
    needs no axis bookkeeping.
    """
    parts = part if isinstance(part, list) else [part] * len(rings)
    ring_indices = []
    for ring, ring_part in zip(rings, parts):
        center = ring["center"]
        rx, rz = ring["rx"], ring["rz"]
        rz_front = ring.get("rz_front", rz)
        rz_back = ring.get("rz_back", rz)
        squash = ring.get("squash", 1.0)
        right = ring.get("right", (1.0, 0.0, 0.0))
        forward = ring.get("forward", (0.0, 0.0, 1.0))
        row = []
        for s in range(segments):
            angle = 2.0 * math.pi * s / segments
            ex, ez = _ellipse_point(angle, rx, rz_front, rz_back, squash)
            p = vm.add(center, vm.add(vm.mul(right, ex), vm.mul(forward, ez)))
            row.append(mesh.add_vertex(p, (0.0, 0.0), ring_part))
        ring_indices.append(row)

    for i in range(len(ring_indices) - 1):
        lo, hi = ring_indices[i], ring_indices[i + 1]
        axis_ref = vm.mul(vm.add(rings[i]["center"], rings[i + 1]["center"]), 0.5)
        for s in range(segments):
            n = (s + 1) % segments
            mesh.add_quad_facing(lo[s], lo[n], hi[n], hi[s], axis_ref)

    if cap_start:
        _cap(mesh, ring_indices[0], rings[0]["center"], rings[1]["center"],
             parts[0])
    if cap_end:
        _cap(mesh, ring_indices[-1], rings[-1]["center"], rings[-2]["center"],
             parts[-1])
    return ring_indices


def _cap(mesh, ring, center, inner_center, part):
    """Close a ring with a triangle fan facing away from `inner_center`."""
    hub = mesh.add_vertex(center, (0.0, 0.0), part)
    n = len(ring)
    for s in range(n):
        mesh.add_triangle_facing(hub, ring[s], ring[(s + 1) % n], inner_center)


def profile_at(profile, t):
    """Piecewise-linear lookup over (t, multiplier) control points."""
    if not profile:
        return 1.0
    if t <= profile[0][0]:
        return profile[0][1]
    for (t0, v0), (t1, v1) in zip(profile, profile[1:]):
        if t <= t1:
            k = (t - t0) / max(t1 - t0, 1e-9)
            return v0 + (v1 - v0) * k
    return profile[-1][1]


def tube(mesh, start, end, r_start, r_end, part, segments=20, slices=8,
         profile=None, aspect=1.0, aspect_x=1.0,
         cap_start=True, cap_end=True,
         round_start=0.0, round_end=0.0):
    """A tapered tube from `start` to `end`.

    `profile` is a list of `(t, multiplier)` control points applied on top of the
    linear taper. Real limbs are not cones: the thigh is fullest in its upper
    third and narrows hard at the knee, the gastrocnemius sits high on the calf,
    and the forearm's mass is proximal. A straight taper reads as a table leg.

    `aspect` and `aspect_x` squash the cross-section on each of its two axes. A
    foot is wider than it is tall and a hand is a flat paddle; a circular tube
    reads as a snowshoe and a sausage respectively. Which world axis each maps to
    depends on the tube's direction, so both are exposed rather than guessed.

    `round_start`/`round_end` extend the tube past its endpoints with a
    hemispherical cap, so shoulders, hips and ankles read as joints rather than
    as flat discs.
    """
    direction = vm.sub(end, start)
    right, up, axis = vm.basis_from_dir(direction)
    length = vm.length(direction)

    rings = []
    if round_start > 0.0:
        rings.extend(_hemisphere_rings(start, axis, right, up, r_start,
                                       round_start, slices=4, invert=True,
                                       aspect=aspect, aspect_x=aspect_x))
    for i in range(slices + 1):
        t = i / slices
        r = (r_start + (r_end - r_start) * t) * profile_at(profile, t)
        rings.append({
            "center": vm.add(start, vm.mul(axis, length * t)),
            "rx": r * aspect_x, "rz": r * aspect,
            "right": right, "forward": up,
        })
    if round_end > 0.0:
        rings.extend(_hemisphere_rings(end, axis, right, up, r_end,
                                       round_end, slices=4, invert=False,
                                       aspect=aspect, aspect_x=aspect_x))

    return loft(mesh, rings, part, segments=segments,
                cap_start=cap_start and round_start <= 0.0,
                cap_end=cap_end and round_end <= 0.0)


def _hemisphere_rings(apex_center, axis, right, up, radius, extent, slices,
                      invert, aspect=1.0, aspect_x=1.0):
    """Rings tracing a hemisphere cap; `invert` points it backwards along axis."""
    rings = []
    order = range(slices, 0, -1) if invert else range(1, slices + 1)
    for i in order:
        t = i / slices
        # quarter-circle sweep: the radius shrinks as the cap pushes out
        r = radius * math.cos(t * math.pi / 2.0)
        offset = extent * math.sin(t * math.pi / 2.0)
        center = vm.add(apex_center, vm.mul(axis, -offset if invert else offset))
        # the caps must carry the tube's own aspect ratio, or a flattened foot
        # grows a circular hemisphere at the heel that dips below the sole
        rings.append({"center": center,
                      "rx": max(r * aspect_x, 1e-4),
                      "rz": max(r * aspect, 1e-4),
                      "right": right, "forward": up})
    return rings


def polytube(mesh, nodes, part, profiles=None, segments=20, slices=8,
             aspect=1.0, aspect_x=1.0, cap_start=True, cap_end=True,
             round_start=0.0, round_end=0.0):
    """A tube through a polyline, SHARING the ring at every corner.

    Two separate tubes meeting at a joint cannot be welded: their rings are
    perpendicular to different axes, so the vertices land a fraction of a
    millimetre apart and each side keeps its own normals. That is the hard line
    ringing every knee and elbow. Here the corner ring exists once, lies in the
    plane bisecting the two segments, and is shared — so there is no seam to
    smooth in the first place.

    `nodes` is a list of `(point, radius)`; `profiles` is one radius profile per
    segment, applied over that segment's linear taper.
    """
    assert len(nodes) >= 2
    profiles = profiles or [None] * (len(nodes) - 1)
    points = [n[0] for n in nodes]
    dirs = [vm.normalize(vm.sub(points[i + 1], points[i]))
            for i in range(len(points) - 1)]

    def plane_at(index):
        """Ring plane normal: segment direction at the ends, bisector inside."""
        if index == 0:
            return dirs[0]
        if index == len(points) - 1:
            return dirs[-1]
        return vm.normalize(vm.add(dirs[index - 1], dirs[index]))

    # A single reference vector, parallel-transported, keeps consecutive rings
    # rotationally aligned; deriving each frame independently twists the tube.
    ref = (0.0, 0.0, 1.0)

    def frame(normal):
        right = vm.cross(ref, normal)
        if vm.length(right) < 1e-6:
            right = vm.cross((1.0, 0.0, 0.0), normal)
        right = vm.normalize(right)
        return right, vm.normalize(vm.cross(normal, right))

    seg_parts = part if isinstance(part, list) else [part] * (len(points) - 1)
    rings, ring_parts = [], []
    if round_start > 0.0:
        right, up = frame(dirs[0])
        caps = _hemisphere_rings(points[0], dirs[0], right, up,
                                 nodes[0][1], round_start, slices=4,
                                 invert=True, aspect=aspect, aspect_x=aspect_x)
        rings.extend(caps)
        ring_parts.extend([seg_parts[0]] * len(caps))

    for seg in range(len(points) - 1):
        r0, r1 = nodes[seg][1], nodes[seg + 1][1]
        n0, n1 = plane_at(seg), plane_at(seg + 1)
        # the first ring of a later segment is the previous segment's last ring
        first = 1 if seg > 0 else 0
        for i in range(first, slices + 1):
            t = i / slices
            r = (r0 + (r1 - r0) * t) * profile_at(profiles[seg], t)
            normal = vm.normalize(vm.lerp(n0, n1, t))
            right, up = frame(normal)
            rings.append({
                "center": vm.lerp(points[seg], points[seg + 1], t),
                "rx": r * aspect_x, "rz": r * aspect,
                "right": right, "forward": up,
            })
            ring_parts.append(seg_parts[seg])

    if round_end > 0.0:
        right, up = frame(dirs[-1])
        caps = _hemisphere_rings(points[-1], dirs[-1], right, up,
                                 nodes[-1][1], round_end, slices=4,
                                 invert=False, aspect=aspect, aspect_x=aspect_x)
        rings.extend(caps)
        ring_parts.extend([seg_parts[-1]] * len(caps))

    return loft(mesh, rings, ring_parts, segments=segments,
                cap_start=cap_start and round_start <= 0.0,
                cap_end=cap_end and round_end <= 0.0)


def sphere(mesh, center, radius, part, segments=28, rings=20,
           scale=(1.0, 1.0, 1.0)):
    """UV sphere with a standard longitude/latitude UV layout."""
    grid = []
    for r in range(rings + 1):
        v = r / rings
        phi = v * math.pi
        row = []
        for s in range(segments + 1):
            u = s / segments
            theta = u * 2.0 * math.pi
            nx = math.sin(phi) * math.sin(theta)
            ny = math.cos(phi)
            nz = math.sin(phi) * math.cos(theta)
            p = (
                center[0] + nx * radius * scale[0],
                center[1] + ny * radius * scale[1],
                center[2] + nz * radius * scale[2],
            )
            row.append(mesh.add_vertex(p, (u, v), part))
        grid.append(row)

    for r in range(rings):
        for s in range(segments):
            a, b = grid[r][s], grid[r][s + 1]
            c, d = grid[r + 1][s + 1], grid[r + 1][s]
            if r == 0:
                mesh.add_triangle_facing(a, c, d, center)
            elif r == rings - 1:
                mesh.add_triangle_facing(a, b, d, center)
            else:
                mesh.add_quad_facing(a, b, c, d, center)
    return grid


def spherical_cap(mesh, center, radius, half_angle, part, scale=(1.0, 1.0, 1.0),
                  segments=36, rings=10, lift=1.006):
    """A cap of a sphere facing +Z, UV-mapped so the cap fills the 0..1 square.

    This is the face plate. It sits a hair proud of the head sphere (`lift`) to
    avoid z-fighting, and its UV disc is inscribed in the texture square, so a
    square drawing of a face lands upright and centred.
    """
    hub = mesh.add_vertex(
        (center[0], center[1], center[2] + radius * scale[2] * lift),
        (0.5, 0.5), part,
    )
    grid = []
    for r in range(1, rings + 1):
        t = r / rings
        phi = t * half_angle
        sin_p, cos_p = math.sin(phi), math.cos(phi)
        row = []
        for s in range(segments):
            theta = 2.0 * math.pi * s / segments
            nx, ny, nz = sin_p * math.cos(theta), sin_p * math.sin(theta), cos_p
            p = (
                center[0] + nx * radius * scale[0] * lift,
                center[1] + ny * radius * scale[1] * lift,
                center[2] + nz * radius * scale[2] * lift,
            )
            row.append(mesh.add_vertex(
                p, (0.5 + 0.5 * t * math.cos(theta), 0.5 - 0.5 * t * math.sin(theta)),
                part,
            ))
        grid.append(row)

    for s in range(segments):
        mesh.add_triangle_facing(hub, grid[0][s], grid[0][(s + 1) % segments], center)
    for r in range(rings - 1):
        for s in range(segments):
            n = (s + 1) % segments
            mesh.add_quad_facing(grid[r][s], grid[r][n],
                                 grid[r + 1][n], grid[r + 1][s], center)
    return grid
