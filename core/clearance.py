"""Exact 3D mesh-to-mesh clearance and triangle intersection analysis in mm (Y-up)."""
from collections.abc import Sequence
import math
from .contracts import FitClearanceReport, MeshData, Transform3D, Vec3
from .head_generator import GeneratedHead
from .transforms import apply_transform

_EPS = 1e-9


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _scale_vec(v: Vec3, s: float) -> Vec3:
    return Vec3(v.x * s, v.y * s, v.z * s)


def _dist_sq(a: Vec3, b: Vec3) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return dx * dx + dy * dy + dz * dz


def closest_point_on_triangle(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> tuple[float, Vec3]:
    """Return (squared_distance_mm2, closest_point) from p to triangle (a, b, c)."""
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return _dist_sq(p, a), a

    bp = p - b
    d3 = _dot(ab, bp)
    d4 = _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return _dist_sq(p, b), b

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        denom = d1 - d3
        v = d1 / denom if denom != 0.0 else 0.0
        q = a + _scale_vec(ab, v)
        return _dist_sq(p, q), q

    cp = p - c
    d5 = _dot(ab, cp)
    d6 = _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return _dist_sq(p, c), c

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denom = d2 - d6
        w = d2 / denom if denom != 0.0 else 0.0
        q = a + _scale_vec(ac, w)
        return _dist_sq(p, q), q

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        denom = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / denom if denom != 0.0 else 0.0
        q = b + _scale_vec(c - b, w)
        return _dist_sq(p, q), q

    denom = va + vb + vc
    if denom == 0.0:
        return _dist_sq(p, a), a
    inv_denom = 1.0 / denom
    v = vb * inv_denom
    w = vc * inv_denom
    q = a + _scale_vec(ab, v) + _scale_vec(ac, w)
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


def _segment_intersects_triangle(p0: Vec3, p1: Vec3, a: Vec3, b: Vec3, c: Vec3) -> bool:
    d = p1 - p0
    e1 = b - a
    e2 = c - a
    h = _cross(d, e2)
    det = _dot(e1, h)

    if abs(det) > _EPS:
        inv_det = 1.0 / det
        s = p0 - a
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
    n_len = normal.length
    if n_len <= _EPS:
        return False
    if abs(_dot(p0 - a, normal)) > _EPS * n_len:
        return False

    if closest_point_on_triangle(p0, a, b, c)[0] <= _EPS * _EPS:
        return True
    if closest_point_on_triangle(p1, a, b, c)[0] <= _EPS * _EPS:
        return True

    ax, ay, az = abs(normal.x), abs(normal.y), abs(normal.z)
    if ax >= ay and ax >= az:
        proj = lambda pt: (pt.y, pt.z)
    elif ay >= ax and ay >= az:
        proj = lambda pt: (pt.x, pt.z)
    else:
        proj = lambda pt: (pt.x, pt.y)

    sp0, sp1 = proj(p0), proj(p1)
    sa, sb, sc = proj(a), proj(b), proj(c)
    return (
        _segments_intersect_2d(sp0, sp1, sa, sb)
        or _segments_intersect_2d(sp0, sp1, sb, sc)
        or _segments_intersect_2d(sp0, sp1, sc, sa)
    )


def triangles_intersect(
    t1: tuple[Vec3, Vec3, Vec3],
    t2: tuple[Vec3, Vec3, Vec3],
) -> bool:
    """Return True if two 3D triangles intersect or touch within tolerance."""
    a0, a1, a2 = t1
    b0, b1, b2 = t2

    if (
        max(a0.x, a1.x, a2.x) + _EPS < min(b0.x, b1.x, b2.x)
        or min(a0.x, a1.x, a2.x) - _EPS > max(b0.x, b1.x, b2.x)
        or max(a0.y, a1.y, a2.y) + _EPS < min(b0.y, b1.y, b2.y)
        or min(a0.y, a1.y, a2.y) - _EPS > max(b0.y, b1.y, b2.y)
        or max(a0.z, a1.z, a2.z) + _EPS < min(b0.z, b1.z, b2.z)
        or min(a0.z, a1.z, a2.z) - _EPS > max(b0.z, b1.z, b2.z)
    ):
        return False

    return (
        _segment_intersects_triangle(a0, a1, b0, b1, b2)
        or _segment_intersects_triangle(a1, a2, b0, b1, b2)
        or _segment_intersects_triangle(a2, a0, b0, b1, b2)
        or _segment_intersects_triangle(b0, b1, a0, a1, a2)
        or _segment_intersects_triangle(b1, b2, a0, a1, a2)
        or _segment_intersects_triangle(b2, b0, a0, a1, a2)
    )


class _BVHNode:
    __slots__ = ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z", "left", "right", "tri_indices")

    def __init__(
        self,
        bounds: tuple[float, float, float, float, float, float],
        left: "_BVHNode | None" = None,
        right: "_BVHNode | None" = None,
        tri_indices: tuple[int, ...] = (),
    ) -> None:
        self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z = bounds
        self.left = left
        self.right = right
        self.tri_indices = tri_indices


class _TriangleBVH:
    def __init__(self, mesh: MeshData) -> None:
        self.vertices = mesh.vertices
        self.triangles = mesh.triangles
        n = len(self.triangles)
        self._tri_bounds: list[tuple[float, float, float, float, float, float]] = []
        self._centroids: list[tuple[float, float, float]] = []
        for i0, i1, i2 in self.triangles:
            v0, v1, v2 = self.vertices[i0], self.vertices[i1], self.vertices[i2]
            self._tri_bounds.append(
                (
                    min(v0.x, v1.x, v2.x),
                    min(v0.y, v1.y, v2.y),
                    min(v0.z, v1.z, v2.z),
                    max(v0.x, v1.x, v2.x),
                    max(v0.y, v1.y, v2.y),
                    max(v0.z, v1.z, v2.z),
                )
            )
            self._centroids.append(
                (
                    (v0.x + v1.x + v2.x) / 3.0,
                    (v0.y + v1.y + v2.y) / 3.0,
                    (v0.z + v1.z + v2.z) / 3.0,
                )
            )
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
    def _box_dist_sq(node: _BVHNode, p: Vec3) -> float:
        dx = node.min_x - p.x if p.x < node.min_x else (p.x - node.max_x if p.x > node.max_x else 0.0)
        dy = node.min_y - p.y if p.y < node.min_y else (p.y - node.max_y if p.y > node.max_y else 0.0)
        dz = node.min_z - p.z if p.z < node.min_z else (p.z - node.max_z if p.z > node.max_z else 0.0)
        return dx * dx + dy * dy + dz * dz

    def nearest_point(self, p: Vec3) -> tuple[float, Vec3]:
        best_dist_sq = float("inf")
        best_point = Vec3(0.0, 0.0, 0.0)

        def visit(node: _BVHNode, lower_sq: float) -> None:
            nonlocal best_dist_sq, best_point
            if lower_sq >= best_dist_sq:
                return
            if node.left is None or node.right is None:
                for idx in node.tri_indices:
                    i0, i1, i2 = self.triangles[idx]
                    d_sq, pt = closest_point_on_triangle(p, self.vertices[i0], self.vertices[i1], self.vertices[i2])
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
        r = self.root
        if p.x < r.min_x or p.x > r.max_x or p.y < r.min_y or p.y > r.max_y or p.z < r.min_z or p.z > r.max_z:
            return False

        ray_dir = Vec3(1.0, 0.13719, 0.07311)
        max_dx = r.max_x - p.x + 1.0
        candidates = self.query_aabb(
            p.x - _EPS,
            p.y - _EPS,
            p.z - _EPS,
            r.max_x + 1.0,
            p.y + ray_dir.y * max_dx + _EPS,
            p.z + ray_dir.z * max_dx + _EPS,
        )

        hit_t: list[float] = []
        for idx in candidates:
            i0, i1, i2 = self.triangles[idx]
            a, b, c = self.vertices[i0], self.vertices[i1], self.vertices[i2]
            e1 = b - a
            e2 = c - a
            h = _cross(ray_dir, e2)
            det = _dot(e1, h)
            if abs(det) <= 1e-12:
                continue
            inv_det = 1.0 / det
            s = p - a
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


def evaluate_clearance(
    head_mesh: MeshData,
    helmet_mesh: MeshData,
    zone_triangle_indices: Sequence[int] | None = None,
    helmet_transform: Transform3D | None = None,
    head_is_watertight: bool = True,
) -> FitClearanceReport:
    """Measure 3D signed clearance and triangle collisions in mm (Y-up)."""
    if not isinstance(head_mesh, MeshData):
        raise ValueError("head_mesh must be MeshData")
    if not isinstance(helmet_mesh, MeshData):
        raise ValueError("helmet_mesh must be MeshData")
    head_mesh.__post_init__()
    helmet_mesh.__post_init__()

    world_helmet = apply_transform(helmet_mesh, helmet_transform) if helmet_transform is not None else helmet_mesh
    helmet_bvh = _TriangleBVH(world_helmet)
    head_bvh = _TriangleBVH(head_mesh)

    # 1. Count helmet triangles intersecting any triangle of the full head mesh
    intersecting_helmet_tris = 0
    for h_idx, (hi0, hi1, hi2) in enumerate(world_helmet.triangles):
        ha = world_helmet.vertices[hi0]
        hb = world_helmet.vertices[hi1]
        hc = world_helmet.vertices[hi2]
        candidates = head_bvh.query_aabb(
            min(ha.x, hb.x, hc.x) - _EPS,
            min(ha.y, hb.y, hc.y) - _EPS,
            min(ha.z, hb.z, hc.z) - _EPS,
            max(ha.x, hb.x, hc.x) + _EPS,
            max(ha.y, hb.y, hc.y) + _EPS,
            max(ha.z, hb.z, hc.z) + _EPS,
        )
        for head_tri_idx in candidates:
            ti0, ti1, ti2 = head_mesh.triangles[head_tri_idx]
            if triangles_intersect(
                (ha, hb, hc),
                (head_mesh.vertices[ti0], head_mesh.vertices[ti1], head_mesh.vertices[ti2]),
            ):
                intersecting_helmet_tris += 1
                break

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

    sample_points: list[Vec3] = []
    seen_vertex_indices: set[int] = set()
    for tri_idx in selected_tris:
        i0, i1, i2 = head_mesh.triangles[tri_idx]
        for vi in (i0, i1, i2):
            if vi not in seen_vertex_indices:
                seen_vertex_indices.add(vi)
                sample_points.append(head_mesh.vertices[vi])
        v0, v1, v2 = head_mesh.vertices[i0], head_mesh.vertices[i1], head_mesh.vertices[i2]
        sample_points.append(
            Vec3(
                (v0.x + v1.x + v2.x) / 3.0,
                (v0.y + v1.y + v2.y) / 3.0,
                (v0.z + v1.z + v2.z) / 3.0,
            )
        )

    min_clearance = float("inf")
    max_clearance = -float("inf")
    total_clearance = 0.0

    for sample in sample_points:
        dist_mm, nearest_pt = helmet_bvh.nearest_point(sample)
        if head_is_watertight and dist_mm > _EPS and head_bvh.is_point_inside(nearest_pt):
            signed_mm = -dist_mm
        else:
            signed_mm = dist_mm

        if signed_mm < min_clearance:
            min_clearance = signed_mm
        if signed_mm > max_clearance:
            max_clearance = signed_mm
        total_clearance += signed_mm

    mean_clearance = total_clearance / len(sample_points)
    return FitClearanceReport(
        min_clearance_mm=min_clearance,
        max_clearance_mm=max_clearance,
        mean_clearance_mm=mean_clearance,
        intersecting_triangles=intersecting_helmet_tris,
    )


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
