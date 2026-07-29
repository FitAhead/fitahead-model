"""Minimal 3D vector / matrix helpers (no numpy dependency)."""

import math

Vec3 = tuple  # (x, y, z)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a):
    return math.sqrt(dot(a, a))


def normalize(a):
    n = length(a)
    if n < 1e-9:
        return (0.0, 1.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def lerp(a, b, t):
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def basis_from_dir(d):
    """Return (right, up, dir) orthonormal basis with `dir` == normalized d."""
    d = normalize(d)
    ref = (0.0, 0.0, 1.0) if abs(d[1]) > 0.99 else (0.0, 1.0, 0.0)
    right = normalize(cross(ref, d))
    up = normalize(cross(d, right))
    return right, up, d


def translation_matrix(t):
    """Column-major 4x4 translation matrix, as glTF expects."""
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        t[0], t[1], t[2], 1.0,
    ]


def smoothstep(edge0, edge1, x):
    if edge1 - edge0 < 1e-9:
        return 0.0 if x < edge0 else 1.0
    t = (x - edge0) / (edge1 - edge0)
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def clamp01(x):
    return max(0.0, min(1.0, x))


def dist_point_segment(p, a, b):
    """Distance from point p to segment ab, plus the parameter t along ab."""
    ab = sub(b, a)
    denom = dot(ab, ab)
    if denom < 1e-12:
        return length(sub(p, a)), 0.0
    t = clamp01(dot(sub(p, a), ab) / denom)
    closest = add(a, mul(ab, t))
    return length(sub(p, closest)), t
