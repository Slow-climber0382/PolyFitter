"""Axis-aligned 1D mesh sections in mm/Y-up, without modifying the scene.

Fully coplanar triangles (all vertices in the tolerance band) are omitted:
area sections require a separate polygon-returning API. Vertex-only contacts
and segments no longer than tolerance are omitted. Two on-plane vertices
produce their projected edge. Results are segments, not loops or proof of fit.

Deduplication compares BOTH endpoint distances, in either orientation, to
previously retained representatives. It is intentionally not transitive
clustering. Sorting candidates first makes representative selection independent
of triangle order. A four-dimensional spatial grid indexes the two in-plane
coordinates of both endpoints; only neighbouring cells are searched.
"""
from itertools import product
import math
from .contracts import MeshData, Vec3


def _xyz(p: Vec3) -> tuple[float, float, float]:
    return p.x, p.y, p.z


def _number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite number')
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f'{name} exceeds float range') from error
    if not math.isfinite(result):
        raise ValueError(f'{name} must be finite')
    return result


def slice_mesh(mesh: MeshData, axis: str, level_mm: float, tolerance_mm: float = 1e-6) -> list[tuple[Vec3, Vec3]]:
    """Return lexicographically ordered segments and endpoints in scene space.

    Tolerance is inclusive, Euclidean and expressed in mm. No axis conversion,
    scaling, centring, loop stitching or splitting overlapping segments occurs.
    Extreme coordinate/tolerance ratios outside float range raise ValueError.
    """
    mesh.__post_init__()
    if not isinstance(axis, str) or axis not in ('x', 'y', 'z'):
        raise ValueError("axis must be exactly 'x', 'y' or 'z'")
    level = _number(level_mm, 'level_mm')
    tolerance = _number(tolerance_mm, 'tolerance_mm')
    if tolerance <= 0:
        raise ValueError('tolerance_mm must be positive')
    normal_axis = ('x', 'y', 'z').index(axis)
    plane_axes = [i for i in range(3) if i != normal_axis]

    def project(p: Vec3) -> Vec3:
        coordinates = list(_xyz(p))
        coordinates[normal_axis] = level
        return Vec3(*coordinates)

    def crossing(a: Vec3, b: Vec3) -> Vec3:
        # Canonical edge order avoids winding-dependent rounding.
        if _xyz(b) < _xyz(a):
            a, b = b, a
        da, db = abs(getattr(a, axis)-level), abs(getattr(b, axis)-level)
        scale = max(da, db)
        t = (da/scale) / (da/scale + db/scale)
        coordinates = [(1-t)*x + t*y for x, y in zip(_xyz(a), _xyz(b))]
        coordinates[normal_axis] = level
        return Vec3(*coordinates)

    candidates = []
    for indices in mesh.triangles:
        points = [mesh.vertices[i] for i in indices]
        distances = [getattr(p, axis)-level for p in points]
        if not all(math.isfinite(d) for d in distances):
            raise ValueError('Plane distance exceeds float range')
        sides = [0 if abs(d) <= tolerance else 1 if d > 0 else -1 for d in distances]
        on = [i for i, side in enumerate(sides) if side == 0]
        if len(on) == 3:
            continue
        hits = [project(points[i]) for i in on]
        for i, j in ((0,1),(1,2),(2,0)):
            if sides[i]*sides[j] == -1:
                hits.append(crossing(points[i], points[j]))
        if len(hits) != 2 or math.dist(_xyz(hits[0]), _xyz(hits[1])) <= tolerance:
            continue
        candidates.append(tuple(sorted(hits, key=_xyz)))
    candidates.sort(key=lambda segment: (_xyz(segment[0]), _xyz(segment[1])))

    cells: dict[tuple[int, ...], list[int]] = {}
    result: list[tuple[Vec3, Vec3]] = []
    offsets = tuple(product((-1, 0, 1), repeat=4))

    def key(a: Vec3, b: Vec3) -> tuple[int, ...]:
        values = [_xyz(p)[i]/tolerance for p in (a,b) for i in plane_axes]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Coordinate/tolerance ratio exceeds float range')
        return tuple(math.floor(v) for v in values)

    def close(a: Vec3, b: Vec3) -> bool:
        return math.dist(_xyz(a), _xyz(b)) <= tolerance

    for a, b in candidates:
        duplicate = False
        for base in (key(a,b), key(b,a)):
            for offset in offsets:
                cell = tuple(x+d for x,d in zip(base,offset))
                for index in cells.get(cell, ()):
                    c, d = result[index]
                    if (close(a,c) and close(b,d)) or (close(a,d) and close(b,c)):
                        duplicate = True
                        break
                if duplicate:
                    break
            if duplicate:
                break
        if not duplicate:
            cells.setdefault(key(a,b), []).append(len(result))
            result.append((a,b))
    return result
