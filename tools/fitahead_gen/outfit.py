from __future__ import annotations

import math
from typing import Final

from . import geom, vecmath as vm
from .params import BodyParams
from .rig import Rig

GRID_SIZE: Final = (19, 23, 17)
GARMENT_CLEARANCE: Final = 0.009
TETRAHEDRA: Final = (
    (0, 1, 2, 6),
    (0, 2, 3, 6),
    (0, 3, 7, 6),
    (0, 7, 4, 6),
    (0, 4, 5, 6),
    (0, 5, 1, 6),
)
CUBE_CORNERS: Final = (
    (0, 0, 0),
    (1, 0, 0),
    (1, 1, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 1),
    (0, 1, 1),
)
TETRA_EDGES: Final = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def build_shorts(params: BodyParams, rig: Rig) -> geom.MeshData:
    height = params.height
    clearance = GARMENT_CLEARANCE * height
    upper_y = (params.waist_y - 0.025) * height
    hip_y = params.hip_y * height
    crotch_y = (params.crotch_y + 0.012) * height
    hem_y = (params.crotch_y - 0.075) * height
    hip_x = abs(rig.world("Thigh_L")[0])

    waist_rx = params.waist_rx * height * 1.06 + clearance
    waist_rz = params.waist_rz * height * 1.07 + clearance
    hip_rx = params.hip_rx * height * 1.04 + clearance
    hip_rz = params.hip_rz * height * 1.07 + clearance
    leg_top_rx = max(params.thigh_r * height * 1.14 + clearance, hip_x * 1.08)
    leg_hem_rx = min(params.thigh_r * height * 0.82 + clearance, hip_x * 0.91)

    def slab(value: float, low: float, high: float) -> float:
        return max(low - value, value - high)

    def ellipse(x: float, z: float, rx: float, rz: float) -> float:
        radius = math.sqrt((x / rx) ** 2 + (z / rz) ** 2)
        return (radius - 1.0) * min(rx, rz)

    def field(point: tuple[float, float, float]) -> float:
        x, y, z = point
        torso_t = min(max((y - hip_y) / max(upper_y - hip_y, 1e-9), 0.0), 1.0)
        torso_rx = hip_rx + (waist_rx - hip_rx) * torso_t
        torso_rz = hip_rz + (waist_rz - hip_rz) * torso_t
        if z < 0.0:
            torso_rz *= 1.10
        else:
            torso_rz *= 0.98
        pelvis = max(ellipse(x, z, torso_rx, torso_rz), slab(y, crotch_y, upper_y))

        leg_t = min(max((y - hem_y) / max(hip_y - hem_y, 1e-9), 0.0), 1.0)
        leg_rx = leg_hem_rx + (leg_top_rx - leg_hem_rx) * leg_t
        leg_rz = leg_rx * (1.10 if z < 0.0 else 1.02)
        left = max(ellipse(x - hip_x, z, leg_rx, leg_rz), slab(y, hem_y, hip_y))
        right = max(ellipse(x + hip_x, z, leg_rx, leg_rz), slab(y, hem_y, hip_y))
        return min(pelvis, left, right)

    x_extent = hip_rx * 1.12
    z_extent = hip_rz * 1.28
    bounds = (
        (-x_extent, x_extent),
        (hem_y - 0.012 * height, upper_y + 0.012 * height),
        (-z_extent, z_extent),
    )
    axes = [
        [low + (high - low) * i / (count - 1) for i in range(count)]
        for (low, high), count in zip(bounds, GRID_SIZE)
    ]
    points: list[tuple[float, float, float]] = []
    values: list[float] = []
    nx, ny, nz = GRID_SIZE
    for z in axes[2]:
        for y in axes[1]:
            for x in axes[0]:
                point = (x, y, z)
                points.append(point)
                values.append(field(point))

    def grid_index(x: int, y: int, z: int) -> int:
        return (z * ny + y) * nx + x

    mesh = geom.MeshData("Shorts")
    edge_vertices: dict[tuple[int, int], int] = {}

    def vertex(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key in edge_vertices:
            return edge_vertices[key]
        va, vb = values[a], values[b]
        t = va / (va - vb)
        pa, pb = points[a], points[b]
        position = tuple(pa[i] + (pb[i] - pa[i]) * t for i in range(3))
        part = "torso" if position[1] > crotch_y + 0.018 * height else (
            "thigh_L" if position[0] >= 0.0 else "thigh_R"
        )
        index = mesh.add_vertex(position, (0.0, 0.0), part)
        edge_vertices[key] = index
        return index

    epsilon = height * 1e-4

    def gradient(point: tuple[float, float, float]) -> tuple[float, float, float]:
        result = []
        for axis in range(3):
            before = list(point)
            after = list(point)
            before[axis] -= epsilon
            after[axis] += epsilon
            result.append(
                (field(tuple(after)) - field(tuple(before))) / (2.0 * epsilon)
            )
        return tuple(result)

    def add_face(indices: list[int]) -> None:
        if len(indices) < 3:
            return
        if len(indices) == 4:
            centre = tuple(
                sum(mesh.positions[index][axis] for index in indices) / 4.0
                for axis in range(3)
            )
            right, up, _ = vm.basis_from_dir(gradient(centre))
            indices.sort(
                key=lambda index: math.atan2(
                    vm.dot(vm.sub(mesh.positions[index], centre), up),
                    vm.dot(vm.sub(mesh.positions[index], centre), right),
                )
            )
        faces = ((0, 1, 2),) if len(indices) == 3 else ((0, 1, 2), (0, 2, 3))
        for ia, ib, ic in faces:
            a, b, c = indices[ia], indices[ib], indices[ic]
            pa, pb, pc = mesh.positions[a], mesh.positions[b], mesh.positions[c]
            normal = vm.cross(vm.sub(pb, pa), vm.sub(pc, pa))
            centre = tuple((pa[i] + pb[i] + pc[i]) / 3.0 for i in range(3))
            if vm.dot(normal, gradient(centre)) < 0.0:
                mesh.add_triangle(a, c, b)
            else:
                mesh.add_triangle(a, b, c)

    for z in range(nz - 1):
        for y in range(ny - 1):
            for x in range(nx - 1):
                cube = [
                    grid_index(x + dx, y + dy, z + dz)
                    for dx, dy, dz in CUBE_CORNERS
                ]
                for tetra in TETRAHEDRA:
                    crossings = []
                    for edge_a, edge_b in TETRA_EDGES:
                        a, b = cube[tetra[edge_a]], cube[tetra[edge_b]]
                        if (values[a] < 0.0) != (values[b] < 0.0):
                            crossings.append(vertex(a, b))
                    add_face(crossings)

    mesh.compute_normals(weld=False)
    return mesh
