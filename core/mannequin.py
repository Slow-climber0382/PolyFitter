"""Procedural fitting reference in mm, Y up, face toward +Z.

Width and depth describe the brow section, as in the legacy generator.
The nose and ears can extend beyond those dimensions. Facial landmarks and
shoulder proportions are estimated. The shoulder cut is capped for volume tests.
"""
import math

from .contracts import HeadMeasurements, MeshData, Vec3
from .head_generator import GeneratedHead, _solve_superellipse_exponent

_BROW = 0.625
# Height fraction, brow-relative half width/depth, depth-relative forward offset.
_PROFILE = (
    (0.0, 0.52, 0.55, 0.04),
    (0.10, 0.74, 0.72, 0.025),
    (0.23, 0.88, 0.85, 0.0),
    (0.39, 0.99, 0.94, 0.0),
    (0.54, 0.98, 0.97, 0.0),
    (_BROW, 1.0, 1.0, 0.0),
    (0.73, 0.97, 0.97, 0.0),
)


def _profile(t: float) -> tuple[float, float, float]:
    for (low, *start), (high, *end) in zip(_PROFILE, _PROFILE[1:]):
        if t <= high:
            blend = (t - low) / (high - low)
            return tuple(a + blend * (b - a) for a, b in zip(start, end))
    dome = math.sqrt(1 - ((t - 0.73) / 0.27) ** 2) * 0.97
    return dome, dome, 0.0


def _bump(t: float, angle: float, y: float, direction: float, vertical: float, angular: float) -> float:
    delta = math.remainder(angle - direction, math.tau)
    return math.exp(-0.5 * (((t - y) / vertical) ** 2 + (delta / angular) ** 2))


def _relief(t: float, angle: float) -> float:
    front = math.pi / 2
    relief = 0.32 * _bump(t, angle, 0.39, front, 0.08, 0.13)  # nose
    relief += 0.09 * _bump(t, angle, 0.09, front, 0.06, 0.31)  # chin
    for side in (-1, 1):
        eye = front + side * 0.32
        relief -= 0.11 * _bump(t, angle, 0.49, eye, 0.042, 0.17)
        relief += 0.11 * _bump(t, angle, 0.57, eye, 0.027, 0.22)
        relief += 0.21 * _bump(t, angle, 0.38, front + side * 1.65, 0.085, 0.11)
    # Keep the measured brow section exact and blend into the neck and dome.
    envelope = min(1.0, 0.5 + 10 * t, abs(t - _BROW) / 0.045)
    return 1.0 + envelope * relief


def generate_mannequin(
    measurements: HeadMeasurements,
    neck_circumference_mm: float | None = None,
    *,
    radial_segments: int = 64,
    height_rings: int = 40,
) -> GeneratedHead:
    """Build a capped, indexed reference compatible with evaluate_helmet_clearance.

    Use result.mesh for evaluate_regional_clearance and rendering. Chin height
    is zero at the front of the jaw/neck junction; the crown is height_mm.
    Neck circumference is measured on the ring at -0.22 * height_mm.
    """
    if not isinstance(measurements, HeadMeasurements):
        raise ValueError("measurements must be HeadMeasurements")
    measurements.__post_init__()
    if type(radial_segments) is not int or radial_segments < 32 or radial_segments % 4:
        raise ValueError("radial_segments must be a multiple of 4 and at least 32")
    if type(height_rings) is not int or height_rings < 24:
        raise ValueError("height_rings must be an integer of at least 24")
    neck = 0.64 * measurements.circumference_mm if neck_circumference_mm is None else neck_circumference_mm
    if isinstance(neck, bool) or not isinstance(neck, (int, float)) or not 100 <= neck <= 750:
        raise ValueError("neck_circumference_mm must be in [100, 750] mm")

    width = measurements.width_mm / 2
    depth = measurements.depth_mm / 2
    height = measurements.height_mm
    exponent, circumference = _solve_superellipse_exponent(
        width, depth, measurements.circumference_mm, radial_segments
    )
    angles = [math.tau * k / radial_segments for k in range(radial_segments)]
    circle = [(math.cos(angle), math.sin(angle)) for angle in angles]
    # Scale the discrete elliptical neck ring to the requested tape length.
    neck_outline = [(x, 0.87 * z) for x, z in circle]
    perimeter = sum(math.dist(a, b) for a, b in zip(neck_outline, neck_outline[1:] + neck_outline[:1]))
    radius = neck / perimeter
    shoulder_width = max(2.35 * width, 1.55 * radius)

    vertices: list[Vec3] = [Vec3(0, -0.56 * height, -0.16 * depth)]
    for t, rx, rz, shift in (
        (-0.56, shoulder_width, 1.09 * radius, -0.16),
        (-0.45, 0.96 * shoulder_width, 1.05 * radius, -0.16),
        (-0.33, max(1.28 * radius, 0.72 * shoulder_width), 0.96 * radius, -0.19),
        (-0.22, radius, 0.87 * radius, -0.21),
        (-0.10, radius, 0.87 * radius, -0.22),
    ):
        vertices.extend(Vec3(rx * x, t * height, rz * z + shift * depth) for x, z in circle)

    levels = sorted({_BROW, *(i / height_rings for i in range(height_rings))})
    for t in levels:
        sx, sz, shift = _profile(t)
        # Concentrate the calibrated superellipse near the tape plane.
        blend = max(0.0, 1.0 - abs(t - _BROW) / 0.16)
        power = 2.0 / (2.0 + (exponent - 2.0) * blend)
        for angle, (x, z) in zip(angles, circle):
            relief = _relief(t, angle)
            vertices.append(Vec3(
                width * sx * math.copysign(abs(x) ** power, x) * relief,
                t * height,
                depth * (sz * math.copysign(abs(z) ** power, z) * relief + shift),
            ))

    crown = len(vertices)
    vertices.append(Vec3(0.0, height, 0.0))
    triangles: list[tuple[int, int, int]] = []
    last_ring = crown - radial_segments
    for k in range(radial_segments):
        next_k = (k + 1) % radial_segments
        triangles.append((0, 1 + k, 1 + next_k))
        triangles.append((crown, last_ring + next_k, last_ring + k))
        for start in range(1, last_ring, radial_segments):
            a, b = start + k, start + next_k
            c, d = a + radial_segments, b + radial_segments
            triangles.extend(((a, c, b), (b, c, d)))

    cranium = [
        index for index, face in enumerate(triangles)
        if sum(vertices[i].y for i in face) / 3 >= 0.45 * height
    ]
    return GeneratedHead(MeshData("anatomical_mannequin", vertices, triangles), cranium, circumference)
