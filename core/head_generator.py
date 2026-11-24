"""Parametric watertight 3D head mesh generator in millimetres (right-handed Y-up)."""
from dataclasses import dataclass
import math
from .contracts import HeadMeasurements, MeshData, Vec3


@dataclass(frozen=True)
class GeneratedHead:
    """Watertight head mesh with calibrated brow circumference and cranium zone."""

    mesh: MeshData
    cranium_triangle_indices: list[int]
    actual_circumference_mm: float


def _superellipse_ring(
    half_width: float,
    half_depth: float,
    y_mm: float,
    exponent: float,
    radial_segments: int,
) -> list[Vec3]:
    power = 2.0 / exponent
    points: list[Vec3] = []
    for k in range(radial_segments):
        theta = (2.0 * math.pi * k) / radial_segments
        c = math.cos(theta)
        s = math.sin(theta)
        x = half_width * math.copysign(abs(c) ** power, c) if c != 0.0 else 0.0
        z = half_depth * math.copysign(abs(s) ** power, s) if s != 0.0 else 0.0
        points.append(Vec3(x, y_mm, z))
    return points


def _ring_perimeter(points: list[Vec3]) -> float:
    total = 0.0
    count = len(points)
    for i in range(count):
        total += (points[(i + 1) % count] - points[i]).length
    return total


def _solve_superellipse_exponent(
    half_width: float,
    half_depth: float,
    target_circumference_mm: float,
    radial_segments: int,
) -> tuple[float, float]:
    min_exp = 2.0
    max_exp = 200.0
    min_circ = _ring_perimeter(_superellipse_ring(half_width, half_depth, 0.0, min_exp, radial_segments))
    max_circ = _ring_perimeter(_superellipse_ring(half_width, half_depth, 0.0, max_exp, radial_segments))

    if target_circumference_mm < min_circ - 1e-6 or target_circumference_mm > max_circ + 1e-6:
        raise ValueError(
            f"circumference_mm ({target_circumference_mm:.2f} mm) is geometrically incompatible "
            f"with width_mm and depth_mm (valid polygon range [{min_circ:.2f}, {max_circ:.2f}] mm)"
        )

    if target_circumference_mm <= min_circ:
        return min_exp, min_circ
    if target_circumference_mm >= max_circ:
        return max_exp, max_circ

    low = min_exp
    high = max_exp
    for _ in range(60):
        mid = 0.5 * (low + high)
        circ = _ring_perimeter(_superellipse_ring(half_width, half_depth, 0.0, mid, radial_segments))
        if circ < target_circumference_mm:
            low = mid
        else:
            high = mid

    solved_exp = 0.5 * (low + high)
    actual_circ = _ring_perimeter(_superellipse_ring(half_width, half_depth, 0.0, solved_exp, radial_segments))
    return solved_exp, actual_circ


def _profile_scales(t: float, brow_t: float) -> tuple[float, float]:
    if t <= 0.0 or t >= 1.0:
        return 0.0, 0.0
    if t >= brow_t:
        u = (t - brow_t) / (1.0 - brow_t)
        base = math.sqrt(max(0.0, 1.0 - u * u))
        return base, base
    u = (brow_t - t) / brow_t
    base = max(0.0, 1.0 - u * u)
    # Jaw and chin taper more narrowly in width than the upper cranial dome.
    return base**0.85, base**0.70


def generate_head_mesh(
    measurements: HeadMeasurements,
    radial_segments: int = 64,
    height_rings: int = 48,
) -> GeneratedHead:
    """Generate a closed, outward-oriented parametric head mesh in mm (Y-up)."""
    if not isinstance(measurements, HeadMeasurements):
        raise ValueError("measurements must be HeadMeasurements")
    measurements.__post_init__()

    if type(radial_segments) is not int or radial_segments < 12:
        raise ValueError("radial_segments must be an integer >= 12")
    if type(height_rings) is not int or height_rings < 8:
        raise ValueError("height_rings must be an integer >= 8")

    half_width = measurements.width_mm / 2.0
    half_depth = measurements.depth_mm / 2.0
    height = measurements.height_mm

    brow_ring = max(2, min(height_rings - 2, round(0.625 * height_rings)))
    brow_t = brow_ring / height_rings

    exponent, actual_circumference = _solve_superellipse_exponent(
        half_width=half_width,
        half_depth=half_depth,
        target_circumference_mm=measurements.circumference_mm,
        radial_segments=radial_segments,
    )

    vertices: list[Vec3] = [Vec3(0.0, 0.0, 0.0)]  # index 0: chin pole
    for ring_idx in range(1, height_rings):
        t = ring_idx / height_rings
        sx, sz = _profile_scales(t, brow_t)
        ring_vertices = _superellipse_ring(
            half_width=half_width * sx,
            half_depth=half_depth * sz,
            y_mm=t * height,
            exponent=exponent,
            radial_segments=radial_segments,
        )
        vertices.extend(ring_vertices)
    top_pole_idx = len(vertices)
    vertices.append(Vec3(0.0, height, 0.0))  # crown pole

    triangles: list[tuple[int, int, int]] = []

    def ring_vertex_index(ring_idx: int, seg_idx: int) -> int:
        return 1 + (ring_idx - 1) * radial_segments + (seg_idx % radial_segments)

    # Bottom cap (outward normal points -Y)
    for k in range(radial_segments):
        a = ring_vertex_index(1, k)
        b = ring_vertex_index(1, k + 1)
        triangles.append((0, a, b))

    # Intermediate quad strips split into two outward-facing triangles
    for r in range(1, height_rings - 1):
        for k in range(radial_segments):
            a = ring_vertex_index(r, k)
            b = ring_vertex_index(r, k + 1)
            c = ring_vertex_index(r + 1, k)
            d = ring_vertex_index(r + 1, k + 1)
            triangles.append((a, c, b))
            triangles.append((b, c, d))

    # Top cap (outward normal points +Y)
    last_ring = height_rings - 1
    for k in range(radial_segments):
        a = ring_vertex_index(last_ring, k)
        b = ring_vertex_index(last_ring, k + 1)
        triangles.append((top_pole_idx, b, a))

    cranium_cutoff_y = 0.55 * height
    cranium_indices: list[int] = []
    for tri_idx, (i0, i1, i2) in enumerate(triangles):
        centroid_y = (vertices[i0].y + vertices[i1].y + vertices[i2].y) / 3.0
        if centroid_y >= cranium_cutoff_y:
            cranium_indices.append(tri_idx)

    mesh = MeshData(name="parametric_head", vertices=vertices, triangles=triangles)
    return GeneratedHead(
        mesh=mesh,
        cranium_triangle_indices=cranium_indices,
        actual_circumference_mm=actual_circumference,
    )
