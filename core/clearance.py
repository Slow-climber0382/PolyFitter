"""Exact 3D mesh-to-mesh clearance and triangle intersection analysis in mm (Y-up)."""
from collections.abc import Sequence
import math
from sys import float_info
from .contracts import FitClearanceReport, MeshData, RegionalClearance, Transform3D, Vec3
from .head_generator import GeneratedHead
from .transforms import apply_transform

_EPS = 1e-9


_Point = tuple[float, float, float]
_Triangle = tuple[_Point, _Point, _Point]
_Bounds = tuple[float, float, float, float, float, float]
_RAY_DIRECTION = (1.0, 0.13719, 0.07311)


def _xyz(point: Vec3) -> _Point:
    return point.x, point.y, point.z


def _sub(a: _Point, b: _Point) -> _Point:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _dot(a: _Point, b: _Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: _Point, b: _Point) -> _Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _offset(a: _Point, direction: _Point, scale: float) -> _Point:
    return (
        a[0] + direction[0] * scale,
        a[1] + direction[1] * scale,
        a[2] + direction[2] * scale,
    )


def _dist_sq(a: _Point, b: _Point) -> float:
    dx, dy, dz = _sub(a, b)
    return dx * dx + dy * dy + dz * dz


def closest_point_on_triangle(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> tuple[float, Vec3]:
    """Return (squared_distance_mm2, closest_point) from p to triangle (a, b, c)."""
    distance, point = _closest_point(_xyz(p), _xyz(a), _xyz(b), _xyz(c))
    return distance, Vec3(*point)


def _closest_point(p: _Point, a: _Point, b: _Point, c: _Point) -> tuple[float, _Point]:
    ab = _sub(b, a)
    ac = _sub(c, a)
    ap = _sub(p, a)
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return _dist_sq(p, a), a

    bp = _sub(p, b)
    d3 = _dot(ab, bp)
    d4 = _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return _dist_sq(p, b), b

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        denom = d1 - d3
        v = d1 / denom if denom != 0.0 else 0.0
        q = _offset(a, ab, v)
        return _dist_sq(p, q), q

    cp = _sub(p, c)
    d5 = _dot(ab, cp)
    d6 = _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return _dist_sq(p, c), c

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denom = d2 - d6
        w = d2 / denom if denom != 0.0 else 0.0
        q = _offset(a, ac, w)
        return _dist_sq(p, q), q

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        denom = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / denom if denom != 0.0 else 0.0
        q = _offset(b, _sub(c, b), w)
        return _dist_sq(p, q), q

    denom = va + vb + vc
    if denom == 0.0:
        return _dist_sq(p, a), a
    inv_denom = 1.0 / denom
    v = vb * inv_denom
    w = vc * inv_denom
    q = _offset(_offset(a, ab, v), ac, w)
    return _dist_sq(p, q), q


def _segments_intersect_2d(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> bool:
    def orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_seg(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
        return (
            min(a[0], b[0]) - _EPS <= c[0] <= max(a[0], b[0]) + _EPS
            and min(a[1], b[1]) - _EPS <= c[1] <= max(a[1], b[1]) + _EPS
        )

    o1 = orient(p1, p2, q1)
    o2 = orient(p1, p2, q2)
    o3 = orient(q1, q2, p1)
    o4 = orient(q1, q2, p2)

    if ((o1 > _EPS and o2 < -_EPS) or (o1 < -_EPS and o2 > _EPS)) and (
        (o3 > _EPS and o4 < -_EPS) or (o3 < -_EPS and o4 > _EPS)
    ):
        return True
    if abs(o1) <= _EPS and on_seg(p1, p2, q1):
        return True
    if abs(o2) <= _EPS and on_seg(p1, p2, q2):
        return True
    if abs(o3) <= _EPS and on_seg(q1, q2, p1):
        return True
    if abs(o4) <= _EPS and on_seg(q1, q2, p2):
        return True
    return False


def _segment_intersects_triangle(p0: _Point, p1: _Point, a: _Point, b: _Point, c: _Point) -> bool:
    d = _sub(p1, p0)
    e1 = _sub(b, a)
    e2 = _sub(c, a)
    h = _cross(d, e2)
    det = _dot(e1, h)

    if abs(det) > _EPS:
        inv_det = 1.0 / det
        s = _sub(p0, a)
        u = inv_det * _dot(s, h)
        if u < -_EPS or u > 1.0 + _EPS:
            return False
        q = _cross(s, e1)
        v = inv_det * _dot(d, q)
        if v < -_EPS or u + v > 1.0 + _EPS:
            return False
        t = inv_det * _dot(e2, q)
        return -_EPS <= t <= 1.0 + _EPS

    # Parallel or coplanar segment vs triangle
    normal = _cross(e1, e2)
    scale = max(abs(normal[0]), abs(normal[1]), abs(normal[2]))
    if scale == 0.0:
        return False
    nx, ny, nz = normal[0] / scale, normal[1] / scale, normal[2] / scale
    n_len = scale * (nx**2 + ny**2 + nz**2)**0.5
    if n_len <= _EPS:
        return False
    if abs(_dot(_sub(p0, a), normal)) > _EPS * n_len:
        return False

    if _closest_point(p0, a, b, c)[0] <= _EPS * _EPS:
        return True
    if _closest_point(p1, a, b, c)[0] <= _EPS * _EPS:
        return True

    ax, ay, az = abs(normal[0]), abs(normal[1]), abs(normal[2])
    if ax >= ay and ax >= az:
        proj = lambda pt: (pt[1], pt[2])
    elif ay >= ax and ay >= az:
        proj = lambda pt: (pt[0], pt[2])
    else:
        proj = lambda pt: (pt[0], pt[1])

    sp0, sp1 = proj(p0), proj(p1)
    sa, sb, sc = proj(a), proj(b), proj(c)
    return (
        _segments_intersect_2d(sp0, sp1, sa, sb)
        or _segments_intersect_2d(sp0, sp1, sb, sc)
        or _segments_intersect_2d(sp0, sp1, sc, sa)
    )


def _bounds(a: _Point, b: _Point, c: _Point) -> _Bounds:
    return (
        min(a[0], b[0], c[0]), min(a[1], b[1], c[1]), min(a[2], b[2], c[2]),
        max(a[0], b[0], c[0]), max(a[1], b[1], c[1]), max(a[2], b[2], c[2]),
    )


def _overlaps(a: _Bounds, b: _Bounds) -> bool:
    # Preserve the original order and rounding of the helmet-side padding.
    return not (
        a[3] + _EPS < b[0] or a[0] - _EPS > b[3]
        or a[4] + _EPS < b[1] or a[1] - _EPS > b[4]
        or a[5] + _EPS < b[2] or a[2] - _EPS > b[5]
    )


def triangles_intersect(
    t1: tuple[Vec3, Vec3, Vec3],
    t2: tuple[Vec3, Vec3, Vec3],
) -> bool:
    """Return True if two 3D triangles intersect or touch within tolerance."""
    a = (_xyz(t1[0]), _xyz(t1[1]), _xyz(t1[2]))
    b = (_xyz(t2[0]), _xyz(t2[1]), _xyz(t2[2]))
    return _overlaps(_bounds(*a), _bounds(*b)) and _triangles_intersect(*a, *b)


def _triangles_intersect(
    a0: _Point, a1: _Point, a2: _Point, b0: _Point, b1: _Point, b2: _Point,
) -> bool:
    return (
        _segment_intersects_triangle(a0, a1, b0, b1, b2)
        or _segment_intersects_triangle(a1, a2, b0, b1, b2)
        or _segment_intersects_triangle(a2, a0, b0, b1, b2)
        or _segment_intersects_triangle(b0, b1, a0, a1, a2)
        or _segment_intersects_triangle(b1, b2, a0, a1, a2)
        or _segment_intersects_triangle(b2, b0, a0, a1, a2)
    )


class _BVHNode:
    __slots__ = ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z", "left", "right", "tri_indices", "bounds")

    def __init__(
        self,
        bounds: tuple[float, float, float, float, float, float],
        left: "_BVHNode | None" = None,
        right: "_BVHNode | None" = None,
        tri_indices: tuple[int, ...] = (),
    ) -> None:
        self.bounds = bounds
        self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z = bounds
        self.left = left
        self.right = right
        self.tri_indices = tri_indices


class _TriangleBVH:
    def __init__(self, mesh: MeshData) -> None:
        self.vertices = [_xyz(point) for point in mesh.vertices]
        self.triangles = mesh.triangles
        n = len(self.triangles)
        self._tri_bounds: list[tuple[float, float, float, float, float, float]] = []
        self._centroids: list[tuple[float, float, float]] = []
        for i0, i1, i2 in self.triangles:
            v0, v1, v2 = self.vertices[i0], self.vertices[i1], self.vertices[i2]
            self._tri_bounds.append(_bounds(v0, v1, v2))
            self._centroids.append((
                (v0[0] + v1[0] + v2[0]) / 3.0,
                (v0[1] + v1[1] + v2[1]) / 3.0,
                (v0[2] + v1[2] + v2[2]) / 3.0,
            ))
        self.root = self._build(list(range(n)), depth=0)

    def _build(self, indices: list[int], depth: int) -> _BVHNode:
        min_x = min(self._tri_bounds[i][0] for i in indices)
        min_y = min(self._tri_bounds[i][1] for i in indices)
        min_z = min(self._tri_bounds[i][2] for i in indices)
        max_x = max(self._tri_bounds[i][3] for i in indices)
        max_y = max(self._tri_bounds[i][4] for i in indices)
        max_z = max(self._tri_bounds[i][5] for i in indices)
        bounds = (min_x, min_y, min_z, max_x, max_y, max_z)

        if len(indices) <= 8 or depth >= 28:
            return _BVHNode(bounds, tri_indices=tuple(indices))

        extents = (max_x - min_x, max_y - min_y, max_z - min_z)
        axis = 0 if extents[0] >= extents[1] and extents[0] >= extents[2] else (1 if extents[1] >= extents[2] else 2)
        indices.sort(key=lambda idx: self._centroids[idx][axis])
        mid = len(indices) // 2
        return _BVHNode(
            bounds,
            left=self._build(indices[:mid], depth + 1),
            right=self._build(indices[mid:], depth + 1),
        )

    @staticmethod
    def _box_dist_sq(node: _BVHNode, p: _Point) -> float:
        dx = node.min_x - p[0] if p[0] < node.min_x else (p[0] - node.max_x if p[0] > node.max_x else 0.0)
        dy = node.min_y - p[1] if p[1] < node.min_y else (p[1] - node.max_y if p[1] > node.max_y else 0.0)
        dz = node.min_z - p[2] if p[2] < node.min_z else (p[2] - node.max_z if p[2] > node.max_z else 0.0)
        return dx * dx + dy * dy + dz * dz

    def nearest_point(self, p: Vec3) -> tuple[float, Vec3]:
        distance, point = self._nearest_point(_xyz(p))
        return distance, Vec3(*point)

    def _nearest_point(self, p: _Point) -> tuple[float, _Point]:
        best_dist_sq = float("inf")
        best_point = (0.0, 0.0, 0.0)

        def visit(node: _BVHNode, lower_sq: float) -> None:
            nonlocal best_dist_sq, best_point
            if lower_sq >= best_dist_sq:
                return
            if node.left is None or node.right is None:
                for idx in node.tri_indices:
                    i0, i1, i2 = self.triangles[idx]
                    d_sq, pt = _closest_point(p, self.vertices[i0], self.vertices[i1], self.vertices[i2])
                    if d_sq < best_dist_sq:
                        best_dist_sq = d_sq
                        best_point = pt
                return

            d_left = self._box_dist_sq(node.left, p)
            d_right = self._box_dist_sq(node.right, p)
            if d_left < d_right:
                visit(node.left, d_left)
                visit(node.right, d_right)
            else:
                visit(node.right, d_right)
                visit(node.left, d_left)

        visit(self.root, self._box_dist_sq(self.root, p))
        return math.sqrt(best_dist_sq), best_point

    def query_aabb(
        self,
        q_min_x: float,
        q_min_y: float,
        q_min_z: float,
        q_max_x: float,
        q_max_y: float,
        q_max_z: float,
    ) -> list[int]:
        hits: list[int] = []

        def visit(node: _BVHNode) -> None:
            if (
                node.max_x < q_min_x
                or node.min_x > q_max_x
                or node.max_y < q_min_y
                or node.min_y > q_max_y
                or node.max_z < q_min_z
                or node.min_z > q_max_z
            ):
                return
            if node.left is None or node.right is None:
                hits.extend(node.tri_indices)
                return
            visit(node.left)
            visit(node.right)

        visit(self.root)
        return hits

    def is_point_inside(self, p: Vec3) -> bool:
        """Odd-even ray cast test for a closed watertight mesh."""
        return self._is_point_inside(_xyz(p))

    def _is_point_inside(self, p: _Point) -> bool:
        r = self.root
        if p[0] < r.min_x or p[0] > r.max_x or p[1] < r.min_y or p[1] > r.max_y or p[2] < r.min_z or p[2] > r.max_z:
            return False

        ray_dir = _RAY_DIRECTION
        max_dx = r.max_x - p[0] + 1.0
        candidates = self.query_aabb(
            p[0] - _EPS,
            p[1] - _EPS,
            p[2] - _EPS,
            r.max_x + 1.0,
            p[1] + ray_dir[1] * max_dx + _EPS,
            p[2] + ray_dir[2] * max_dx + _EPS,
        )

        hit_t: list[float] = []
        for idx in candidates:
            i0, i1, i2 = self.triangles[idx]
            a, b, c = self.vertices[i0], self.vertices[i1], self.vertices[i2]
            e1 = _sub(b, a)
            e2 = _sub(c, a)
            h = _cross(ray_dir, e2)
            det = _dot(e1, h)
            if abs(det) <= 1e-12:
                continue
            inv_det = 1.0 / det
            s = _sub(p, a)
            u = inv_det * _dot(s, h)
            if u < 0.0 or u > 1.0:
                continue
            q = _cross(s, e1)
            v = inv_det * _dot(ray_dir, q)
            if v < 0.0 or u + v > 1.0:
                continue
            t = inv_det * _dot(e2, q)
            if t > 1e-7:
                hit_t.append(t)

        hit_t.sort()
        unique_hits = 0
        prev_t = -1.0
        for t in hit_t:
            if unique_hits == 0 or abs(t - prev_t) > 1e-5:
                unique_hits += 1
                prev_t = t
        return (unique_hits % 2) == 1


def _count_intersections(helmet: _TriangleBVH, head: _TriangleBVH) -> int:
    """Prune disjoint node pairs and count each helmet triangle at most once."""
    intersecting: set[int] = set()
    stack = [(helmet.root, head.root)]
    while stack:
        helmet_node, head_node = stack.pop()
        if not _overlaps(helmet_node.bounds, head_node.bounds):
            continue
        if helmet_node.left is not None and (
            head_node.left is None
            or max(helmet_node.max_x - helmet_node.min_x,
                   helmet_node.max_y - helmet_node.min_y,
                   helmet_node.max_z - helmet_node.min_z)
            >= max(head_node.max_x - head_node.min_x,
                   head_node.max_y - head_node.min_y,
                   head_node.max_z - head_node.min_z)
        ):
            stack.append((helmet_node.left, head_node))
            stack.append((helmet_node.right, head_node))
        elif head_node.left is not None:
            stack.append((helmet_node, head_node.left))
            stack.append((helmet_node, head_node.right))
        else:
            for helmet_index in helmet_node.tri_indices:
                if helmet_index in intersecting:
                    continue
                bounds = helmet._tri_bounds[helmet_index]
                if not _overlaps(bounds, head_node.bounds):
                    continue
                a, b, c = helmet.triangles[helmet_index]
                for head_index in head_node.tri_indices:
                    if not _overlaps(bounds, head._tri_bounds[head_index]):
                        continue
                    d, e, f = head.triangles[head_index]
                    if _triangles_intersect(
                        helmet.vertices[a], helmet.vertices[b], helmet.vertices[c],
                        head.vertices[d], head.vertices[e], head.vertices[f],
                    ):
                        intersecting.add(helmet_index)
                        break
    return len(intersecting)


def evaluate_clearance(
    head_mesh: MeshData,
    helmet_mesh: MeshData,
    zone_triangle_indices: Sequence[int] | None = None,
    helmet_transform: Transform3D | None = None,
    head_is_watertight: bool = True,
) -> FitClearanceReport:
    """Measure 3D signed clearance and triangle collisions in mm (Y-up)."""
    return _evaluate_clearance(
        head_mesh, helmet_mesh, zone_triangle_indices, helmet_transform, head_is_watertight
    )


def evaluate_regional_clearance(
    head_mesh: MeshData,
    helmet_mesh: MeshData,
    height_mm: float,
    helmet_transform: Transform3D | None = None,
    head_is_watertight: bool = True,
) -> FitClearanceReport:
    """Sample the entire head, with the chin at Y=0 and crown at Y=height_mm.

    The boundary at 45% of height belongs to cranium. Empty regions are None.
    Collision counts describe the full mesh pair; they are not regional counts.
    """
    if (
        isinstance(height_mm, bool)
        or not isinstance(height_mm, (int, float))
        or not 0 < height_mm <= float_info.max
    ):
        raise ValueError("height_mm must be finite and positive")
    return _evaluate_clearance(
        head_mesh, helmet_mesh, None, helmet_transform, head_is_watertight,
        regional_cutoff_y=0.45 * height_mm,
    )


def _evaluate_clearance(
    head_mesh: MeshData,
    helmet_mesh: MeshData,
    zone_triangle_indices: Sequence[int] | None,
    helmet_transform: Transform3D | None,
    head_is_watertight: bool,
    regional_cutoff_y: float | None = None,
) -> FitClearanceReport:
    if not isinstance(head_mesh, MeshData):
        raise ValueError("head_mesh must be MeshData")
    if not isinstance(helmet_mesh, MeshData):
        raise ValueError("helmet_mesh must be MeshData")
    head_mesh.__post_init__()
    helmet_mesh.__post_init__()

    world_helmet = apply_transform(helmet_mesh, helmet_transform) if helmet_transform is not None else helmet_mesh
    helmet_bvh = _TriangleBVH(world_helmet)
    head_bvh = _TriangleBVH(head_mesh)

    intersecting_helmet_tris = _count_intersections(helmet_bvh, head_bvh)

    # 2. Sample points on the contact zone (unique vertices + triangle centroids)
    if zone_triangle_indices is None:
        selected_tris = list(range(len(head_mesh.triangles)))
    else:
        selected_tris = list(zone_triangle_indices)
        if not selected_tris:
            raise ValueError("zone_triangle_indices must not be empty")
        num_tris = len(head_mesh.triangles)
        for idx in selected_tris:
            if type(idx) is not int or not (0 <= idx < num_tris):
                raise ValueError("Invalid triangle index in zone_triangle_indices")

    sample_points: list[_Point] = []
    seen_vertex_indices: set[int] = set()
    for tri_idx in selected_tris:
        i0, i1, i2 = head_mesh.triangles[tri_idx]
        for vi in (i0, i1, i2):
            if vi not in seen_vertex_indices:
                seen_vertex_indices.add(vi)
                sample_points.append(head_bvh.vertices[vi])
        v0, v1, v2 = head_bvh.vertices[i0], head_bvh.vertices[i1], head_bvh.vertices[i2]
        sample_points.append((
            (v0[0] + v1[0] + v2[0]) / 3.0,
            (v0[1] + v1[1] + v2[1]) / 3.0,
            (v0[2] + v1[2] + v2[2]) / 3.0,
        ))

    min_clearance = float("inf")
    max_clearance = -float("inf")
    total_clearance = 0.0

    cranium_samples: list[float] = []
    lower_samples: list[float] = []
    for sample in sample_points:
        dist_mm, nearest_pt = helmet_bvh._nearest_point(sample)
        if head_is_watertight and dist_mm > _EPS and head_bvh._is_point_inside(nearest_pt):
            signed_mm = -dist_mm
        else:
            signed_mm = dist_mm

        if signed_mm < min_clearance:
            min_clearance = signed_mm
        if signed_mm > max_clearance:
            max_clearance = signed_mm
        total_clearance += signed_mm
        if regional_cutoff_y is not None:
            region = cranium_samples if sample[1] >= regional_cutoff_y else lower_samples
            region.append(signed_mm)

    mean_clearance = total_clearance / len(sample_points)
    return FitClearanceReport(
        min_clearance_mm=min_clearance,
        max_clearance_mm=max_clearance,
        mean_clearance_mm=mean_clearance,
        intersecting_triangles=intersecting_helmet_tris,
        cranium=_regional_statistics(cranium_samples),
        lower=_regional_statistics(lower_samples),
    )


def _regional_statistics(samples: list[float]) -> RegionalClearance | None:
    if not samples:
        return None
    return RegionalClearance(min(samples), max(samples), sum(samples) / len(samples), len(samples))


def evaluate_helmet_clearance(
    head: GeneratedHead,
    helmet_mesh: MeshData,
    helmet_transform: Transform3D | None = None,
) -> FitClearanceReport:
    """Evaluate 3D clearance (target 2-4 mm) across the head's cranial contact zone."""
    if not isinstance(head, GeneratedHead):
        raise ValueError("head must be GeneratedHead")
    return evaluate_clearance(
        head_mesh=head.mesh,
        helmet_mesh=helmet_mesh,
        zone_triangle_indices=head.cranium_triangle_indices,
        helmet_transform=helmet_transform,
        head_is_watertight=True,
    )
