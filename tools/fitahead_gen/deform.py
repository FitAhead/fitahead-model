from . import geom, vecmath as vm
from .rig import PART_BONES


def skin(character, group):
    rig = character.rig
    mesh = group.mesh
    for i in range(mesh.vertex_count):
        part = mesh.parts[i]
        pos = mesh.positions[i]
        if part == "torso":
            pairs = _torso_weights(character, pos)
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
        joints, weights = _pack_influences(character, pairs)
        group.joints.append(joints)
        group.weights.append(weights)


def _torso_weights(character, pos):
    p = character.p
    y = pos[1] / p.height
    anchors = [
        ("Hips", p.hip_y),
        ("Spine", p.waist_y),
        ("Chest", p.chest_y),
        ("UpperChest", character._upper_chest_y()),
    ]
    if y <= anchors[0][1]:
        return [(anchors[0][0], 1.0)]
    if y >= anchors[-1][1]:
        return [(anchors[-1][0], 1.0)]
    for (lo_name, lo_y), (hi_name, hi_y) in zip(anchors, anchors[1:]):
        if lo_y <= y <= hi_y:
            t = (y - lo_y) / max(hi_y - lo_y, 1e-9)
            t = t * t * (3.0 - 2.0 * t)
            return [(lo_name, 1.0 - t), (hi_name, t)]
    return [(anchors[-1][0], 1.0)]


def _pack_influences(character, pairs):
    kept = [(character.rig.by_name[n].index, max(0.0, w))
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


def bake_morphs(character, group, ctx):
    mesh = group.mesh
    h = character.p.height
    for morph_group in character.morph_groups:
        displacement = morph_group.amount * h
        deltas = []
        touched = 0
        positions = list(mesh.positions)
        for i in range(mesh.vertex_count):
            mask = morph_group.mask(
                ctx, mesh.parts[i], mesh.positions[i], mesh.normals[i]
            )
            if abs(mask) <= 1e-4:
                deltas.append((0.0, 0.0, 0.0))
                continue
            touched += 1
            delta = vm.mul(mesh.normals[i], displacement * mask)
            deltas.append(delta)
            positions[i] = vm.add(mesh.positions[i], delta)

        if touched == 0:
            zeros = [(0.0, 0.0, 0.0)] * mesh.vertex_count
            group.targets.append({"name": morph_group.name, "positions": zeros,
                                  "normals": zeros, "touched": 0})
            continue

        morphed_normals = geom.weld_normals(
            positions, geom.compute_normals_for(positions, mesh.indices))
        normal_deltas = [vm.sub(morphed_normals[i], mesh.normals[i])
                         for i in range(mesh.vertex_count)]
        group.targets.append({"name": morph_group.name, "positions": deltas,
                              "normals": normal_deltas, "touched": touched})
