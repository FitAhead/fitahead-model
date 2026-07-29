#!/usr/bin/env python3
"""Measure a generated body and compare it against the anthropometric table.

    python3 tools/measure.py                    # every archetype, both sexes
    python3 tools/measure.py --preset male --archetype muscular

Renders are easy to misread — a limb can look unchanged because the growth went
into depth rather than width, or because the camera is too far away. This
measures the mesh instead: it applies an archetype's morph weights to the actual
vertices and reports the resulting girths, so "does 근육질 reach trained
proportions" has a numeric answer.

Girths are measured as the perimeter of the vertex ring closest to the requested
height, which slightly underestimates a smooth limb (a polygon inscribed in a
circle) — reported alongside the reference so the comparison stays fair.
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fitahead_gen import anthro, params, vecmath as vm  # noqa: E402
from fitahead_gen.body import Character  # noqa: E402
from fitahead_gen.manifest import build_archetypes  # noqa: E402

#: site -> (mesh part, height as a fraction of stature, anthro girth key)
#: Heights are where each girth is conventionally taken.
#: site -> (label, mesh parts, height fraction, anthro key, bone or None)
#: The bone is what rings are identified along; see `ring_perimeter`.
SITES = [
    ("upper arm", ("upperarm_L",), 0.740, "upper_arm", "UpperArm_L"),
    ("forearm", ("forearm_L",), 0.588, "forearm", "Forearm_L"),
    ("thigh", ("thigh_L",), 0.450, "thigh", "Thigh_L"),
    ("calf", ("shin_L",), 0.230, "calf", "Shin_L"),
    ("neck", ("neck",), 0.845, "neck", "Neck"),
]


def morphed_positions(character, weights):
    """Base mesh positions with an archetype's morph weights applied."""
    body = character.groups[0]
    names = [t["name"] for t in body.targets]
    positions = list(body.mesh.positions)
    for name, target in zip(names, body.targets):
        w = weights.get(name, 0.0)
        if w == 0.0:
            continue
        deltas = target["positions"]
        for i, d in enumerate(deltas):
            if d[0] or d[1] or d[2]:
                px, py, pz = positions[i]
                positions[i] = (px + d[0] * w, py + d[1] * w, pz + d[2] * w)
    return positions


def ring_perimeter(character, positions, parts, target_y, tolerance, bone):
    """Perimeter of the vertex ring nearest `target_y` within the given parts.

    Rings are identified by ring CENTRE height rather than by vertex height: a
    limb tube's cross-sections are perpendicular to its bone, and the arms and
    legs are not perfectly vertical, so the vertices of one ring differ in y by
    a fraction of a millimetre. Grouping on exact vertex y therefore found rings
    of one vertex each and reported nothing at all.
    """
    body = character.groups[0].mesh
    candidates = [
        i for i in range(body.vertex_count)
        if body.parts[i] in parts
        and abs(body.positions[i][1] - target_y) < tolerance
    ]
    if not candidates:
        return None

    # Bucket by distance along the BONE, not by height. A limb tube's rings are
    # perpendicular to its bone, and even a 2-degree tilt spreads one ring over
    # several millimetres of height — height bucketing split each ring into
    # quarters and under-reported every girth by about 4x.
    start, end = character.rig.segment(bone)
    axis = vm.normalize(vm.sub(end, start))
    buckets = {}
    for i in candidates:
        along = vm.dot(vm.sub(body.positions[i], start), axis)
        buckets.setdefault(round(along * 2000), []).append(i)
    rings = [r for r in buckets.values() if len(r) >= 3]
    if not rings:
        return None
    ring = min(rings, key=lambda r: abs(
        sum(body.positions[i][1] for i in r) / len(r) - target_y))

    # order around the ring in its own plane, then sum true 3D edge lengths
    centre = (sum(positions[i][0] for i in ring) / len(ring),
              sum(positions[i][1] for i in ring) / len(ring),
              sum(positions[i][2] for i in ring) / len(ring))
    right, up, _ = vm.basis_from_dir(axis)
    def angle(i):
        d = vm.sub(positions[i], centre)
        return math.atan2(vm.dot(d, up), vm.dot(d, right))
    ordered = sorted(ring, key=angle)
    perimeter = 0.0
    for a, b in zip(ordered, ordered[1:] + ordered[:1]):
        perimeter += vm.length(vm.sub(positions[a], positions[b]))
    return perimeter


def report(preset_name, archetype_ids):
    p = params.PRESETS[preset_name]
    character = Character(p)
    groups = {g.name: g for g in character.morph_groups}
    archetypes = {a["id"]: a for a in build_archetypes(p, groups)}
    h = p.height

    print(f"\n=== {preset_name} (stature {h:.2f} m) ===")
    print("girths in cm; reference is the anthropometric table for this sex\n")

    header = f"{'site':11s}"
    for key in archetype_ids:
        header += f"{key:>12s}"
    header += f"{'ref lean':>10s}{'ref avg':>9s}{'ref trained':>12s}"
    print(header)

    for label, parts, y_fraction, girth_key, bone in SITES:
        row = f"{label:11s}"
        for key in archetype_ids:
            positions = morphed_positions(character, archetypes[key]["weights"])
            value = ring_perimeter(character, positions, parts,
                                   y_fraction * h, 0.05 * h, bone)
            row += f"{value * 100:12.1f}" if value else f"{'-':>12s}"
        ref = anthro.GIRTHS[p.sex][girth_key]
        row += (f"{ref['lean'] * h * 100:10.1f}"
                f"{ref['average'] * h * 100:9.1f}"
                f"{ref['trained'] * h * 100:12.1f}")
        print(row)

    # Torso breadths. Restricted to the torso part: the arms hang past the waist,
    # so measuring the whole body at waist height reports the span between the
    # two forearms rather than the waist.
    print("breadths in cm, torso only\n")
    mesh = character.groups[0].mesh
    refs = {
        "shoulder W": anthro.BREADTHS[p.sex]["biacromial"],
        "chest W": anthro.BREADTHS[p.sex]["chest"],
        "waist W": anthro.BREADTHS[p.sex]["waist"],
        "hip W": anthro.BREADTHS[p.sex]["hip"],
    }
    for label, y_fraction in (("shoulder W", p.shoulder_y),
                              ("chest W", p.chest_y),
                              ("waist W", p.waist_y),
                              ("hip W", p.hip_y)):
        row = f"{label:11s}"
        band = [i for i in range(mesh.vertex_count)
                if mesh.parts[i] == "torso"
                and abs(mesh.positions[i][1] - y_fraction * h) < 0.010 * h]
        for key in archetype_ids:
            positions = morphed_positions(character, archetypes[key]["weights"])
            width = (max(positions[i][0] for i in band)
                     - min(positions[i][0] for i in band)) if band else 0
            row += f"{width * 100:12.1f}"
        row += f"{refs[label] * h * 100:10.1f}"
        print(row)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", action="append", choices=sorted(params.PRESETS))
    ap.add_argument("--archetype", action="append")
    args = ap.parse_args(argv)

    ids = args.archetype or ["lean", "average", "athletic", "muscular",
                             "overweight"]
    for name in args.preset or sorted(params.PRESETS):
        report(name, ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
