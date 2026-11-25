"""Automatic uniform-scale + translation helmet fitting solver in mm (Y-up)."""
from dataclasses import dataclass
from functools import lru_cache
import math
from .clearance import (
    _Bounds, _BVHNode, _EPS, _Point, _TriangleBVH, _bounds, _overlaps,
    _triangles_intersect,
)
from .contracts import FitClearanceReport, HeadMeasurements, MeshData, Transform3D, Vec3
from .head_generator import GeneratedHead, generate_head_mesh
from .transforms import apply_transform


@dataclass(frozen=True)
class FitResult:
    """Result of automatic helmet fitting against a parametric head."""

    transform: Transform3D
    report: FitClearanceReport
    converged: bool


def _inv_rotate_xyz(x: float, y: float, z: float, rotation_deg: Vec3) -> tuple[float, float, float]:
    """Inverse of Rz(rz) * Ry(ry) * Rx(rx) is Rx(-rx) * Ry(-ry) * Rz(-rz)."""
    rx = math.radians(-rotation_deg.x)
    ry = math.radians(-rotation_deg.y)
    rz = math.radians(-rotation_deg.z)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    x, y = cz * x - sz * y, sz * x + cz * y
    x, z = cy * x + sy * z, -sy * x + cy * z
    y, z = cx * y - sx * z, sx * y + cx * z
    return x, y, z


def _fwd_rotate_xyz(x: float, y: float, z: float, rotation_deg: Vec3) -> tuple[float, float, float]:
    rx = math.radians(rotation_deg.x)
    ry = math.radians(rotation_deg.y)
    rz = math.radians(rotation_deg.z)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    y, z = cx * y - sx * z, sx * y + cx * z
    x, z = cy * x + sy * z, -sy * x + cy * z
    x, y = cz * x - sz * y, sz * x + cz * y
    return x, y, z


def _collect_cranium_samples(head: GeneratedHead, max_samples: int | None = 72) -> list[Vec3]:
    verts = head.mesh.vertices
    tris = head.mesh.triangles
    samples: list[Vec3] = []
    seen_verts: set[int] = set()

    for tri_idx in head.cranium_triangle_indices:
        i0, i1, i2 = tris[tri_idx]
        for vi in (i0, i1, i2):
            if vi not in seen_verts:
                seen_verts.add(vi)
                samples.append(verts[vi])
        v0, v1, v2 = verts[i0], verts[i1], verts[i2]
        samples.append(
            Vec3(
                (v0.x + v1.x + v2.x) / 3.0,
                (v0.y + v1.y + v2.y) / 3.0,
                (v0.z + v1.z + v2.z) / 3.0,
            )
        )

    if max_samples is None or len(samples) <= max_samples:
        return samples
    step = len(samples) / max_samples
    return [samples[int(i * step)] for i in range(max_samples)]


def _world_bounds(bounds: _Bounds, transform: Transform3D) -> _Bounds:
    """Propagate intervals through the same operations used for world vertices."""
    rx, ry, rz = map(math.radians, (transform.rotation.x, transform.rotation.y, transform.rotation.z))
    scale = transform.scale.x
    intervals = [(bounds[i] * scale, bounds[i + 3] * scale) for i in range(3)]

    def multiply(interval: tuple[float, float], factor: float) -> tuple[float, float]:
        low, high = interval
        return (low * factor, high * factor) if factor >= 0 else (high * factor, low * factor)

    def combine(a: int, b: int, left: float, right: float, subtract: bool) -> tuple[float, float]:
        low, high = multiply(intervals[a], left)
        other_low, other_high = multiply(intervals[b], right)
        if subtract:
            return low - other_high, high - other_low
        return low + other_low, high + other_high

    cx, sx = math.cos(rx), math.sin(rx)
    intervals[1], intervals[2] = combine(1, 2, cx, sx, True), combine(1, 2, sx, cx, False)
    cy, sy = math.cos(ry), math.sin(ry)
    intervals[0], intervals[2] = combine(0, 2, cy, sy, False), combine(0, 2, -sy, cy, False)
    cz, sz = math.cos(rz), math.sin(rz)
    intervals[0], intervals[1] = combine(0, 1, cz, sz, True), combine(0, 1, sz, cz, False)
    (x0, x1), (y0, y1), (z0, z1) = intervals
    t = transform.position
    return x0 + t.x, y0 + t.y, z0 + t.z, x1 + t.x, y1 + t.y, z1 + t.z


def _world_point(point: _Point, transform: Transform3D) -> _Point:
    scale = transform.scale.x
    x, y, z = _fwd_rotate_xyz(*(value * scale for value in point), transform.rotation)
    t = transform.position
    return x + t.x, y + t.y, z + t.z


def _count_transformed_collisions(
    helmet: _TriangleBVH, head: _TriangleBVH, transform: Transform3D,
) -> int:
    """Discard disjoint node pairs and transform triangles only at candidate leaves."""
    bounds_by_node: dict[_BVHNode, _Bounds] = {}
    @lru_cache(maxsize=512)
    def world_triangle(index: int) -> tuple[tuple[_Point, _Point, _Point], _Bounds]:
        a, b, c = (
            _world_point(helmet.vertices[i], transform) for i in helmet.triangles[index]
        )
        return (a, b, c), _bounds(a, b, c)

    hits: set[int] = set()
    stack = [(helmet.root, head.root)]
    while stack:
        helmet_node, head_node = stack.pop()
        bounds = bounds_by_node.get(helmet_node)
        if bounds is None:
            bounds = _world_bounds(helmet_node.bounds, transform)
            bounds_by_node[helmet_node] = bounds
        if not _overlaps(bounds, head_node.bounds):
            continue
        if helmet_node.left is not None and head_node.left is not None:
            for helmet_child in (helmet_node.left, helmet_node.right):
                for head_child in (head_node.left, head_node.right):
                    stack.append((helmet_child, head_child))
        elif helmet_node.left is not None:
            stack.extend(((helmet_node.left, head_node), (helmet_node.right, head_node)))
        elif head_node.left is not None:
            stack.extend(((helmet_node, head_node.left), (helmet_node, head_node.right)))
        else:
            for index in helmet_node.tri_indices:
                if index in hits:
                    continue
                face, face_bounds = world_triangle(index)
                if not _overlaps(face_bounds, head_node.bounds):
                    continue
                for other in head_node.tri_indices:
                    if not _overlaps(face_bounds, head._tri_bounds[other]):
                        continue
                    a, b, c = head.triangles[other]
                    if _triangles_intersect(*face, head.vertices[a], head.vertices[b], head.vertices[c]):
                        hits.add(index)
                        break
    world_triangle.cache_clear()
    return len(hits)


def _evaluate_candidate(
    helmet: _TriangleBVH, head: _TriangleBVH, samples: list[Vec3], transform: Transform3D,
) -> FitClearanceReport:
    scale = transform.scale.x
    t = transform.position
    minimum, maximum, total = math.inf, -math.inf, 0.0
    for p in samples:
        local = _inv_rotate_xyz(
            (p.x - t.x) / scale, (p.y - t.y) / scale, (p.z - t.z) / scale,
            transform.rotation,
        )
        distance, nearest = helmet._nearest_point(local)
        distance *= scale
        if distance > _EPS and head._is_point_inside(_world_point(nearest, transform)):
            distance = -distance
        minimum, maximum = min(minimum, distance), max(maximum, distance)
        total += distance
    return FitClearanceReport(
        min_clearance_mm=minimum,
        max_clearance_mm=maximum,
        mean_clearance_mm=total / len(samples),
        intersecting_triangles=_count_transformed_collisions(helmet, head, transform),
    )


def fit_helmet(
    head: GeneratedHead,
    helmet_mesh: MeshData,
    initial_rotation: Vec3 | None = None,
    target_clearance_mm: float = 3.0,
    min_clearance_mm: float = 2.0,
    max_clearance_mm: float = 4.0,
) -> FitResult:
    """Find a uniform scale and translation placing the helmet within 2-4 mm clearance."""
    if not isinstance(head, GeneratedHead):
        raise ValueError("head must be GeneratedHead")
    if not isinstance(helmet_mesh, MeshData):
        raise ValueError("helmet_mesh must be MeshData")
    head.mesh.__post_init__()
    helmet_mesh.__post_init__()

    rot = initial_rotation if initial_rotation is not None else Vec3(0.0, 0.0, 0.0)
    if not isinstance(rot, Vec3):
        raise ValueError("initial_rotation must be Vec3")

    for name, val in (
        ("target_clearance_mm", target_clearance_mm),
        ("min_clearance_mm", min_clearance_mm),
        ("max_clearance_mm", max_clearance_mm),
    ):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(f"{name} must be a finite number")
    if not (0.0 <= min_clearance_mm <= target_clearance_mm <= max_clearance_mm):
        raise ValueError("Expected 0 <= min_clearance_mm <= target_clearance_mm <= max_clearance_mm")

    oriented_helmet = apply_transform(helmet_mesh, Transform3D(rotation=rot))
    h_box = oriented_helmet.bounding_box
    if h_box.size.x <= 0.0 or h_box.size.y <= 0.0 or h_box.size.z <= 0.0:
        raise ValueError("Helmet mesh must have non-zero 3D extent")

    head_box = head.mesh.bounding_box
    helmet_bvh = _TriangleBVH(helmet_mesh)
    head_bvh = _TriangleBVH(head.mesh)
    zone = head.cranium_triangle_indices
    if not zone or any(type(i) is not int or not 0 <= i < len(head.mesh.triangles) for i in zone):
        raise ValueError("Invalid or empty cranium triangle indices")
    full_samples = _collect_cranium_samples(head, max_samples=None)
    step = len(full_samples) / 72
    samples = full_samples if len(full_samples) <= 72 else [full_samples[int(i * step)] for i in range(72)]

    h_center = h_box.center
    top_from_center = h_box.max_pt.y - h_center.y

    def to_world_position(scale: float, ax: float, ay: float, az: float) -> tuple[float, float, float]:
        return (
            ax - scale * h_center.x,
            ay - scale * h_center.y,
            az - scale * h_center.z,
        )

    def eval_stats(scale: float, ax: float, ay: float, az: float) -> tuple[float, float, float, float]:
        px, py, pz = to_world_position(scale, ax, ay, az)
        inv_s = 1.0 / scale
        min_c = float("inf")
        max_c = -float("inf")
        sum_c = 0.0
        sq_err = 0.0

        for sp in samples:
            lx, ly, lz = _inv_rotate_xyz(
                (sp.x - px) * inv_s,
                (sp.y - py) * inv_s,
                (sp.z - pz) * inv_s,
                rot,
            )
            local_dist, local_nearest = helmet_bvh.nearest_point(Vec3(lx, ly, lz))
            dist_mm = local_dist * scale
            wx, wy, wz = _fwd_rotate_xyz(
                local_nearest.x * scale,
                local_nearest.y * scale,
                local_nearest.z * scale,
                rot,
            )
            world_nearest = Vec3(wx + px, wy + py, wz + pz)
            signed_mm = -dist_mm if (dist_mm > 1e-9 and head_bvh.is_point_inside(world_nearest)) else dist_mm

            if signed_mm < min_c:
                min_c = signed_mm
            if signed_mm > max_c:
                max_c = signed_mm
            sum_c += signed_mm
            diff = signed_mm - target_clearance_mm
            sq_err += diff * diff

        n = len(samples)
        mean_c = sum_c / n
        mse = sq_err / n

        # Lexicographic priority: never trade collision/tightness for smaller max_clearance_mm
        penalty = mse
        if max_c > max_clearance_mm:
            excess = max_c - max_clearance_mm
            penalty += 25.0 * excess * excess
        if min_c < min_clearance_mm:
            deficit = min_clearance_mm - min_c
            penalty += 1e7 + 1e6 * deficit * deficit
        if min_c < 0.0:
            penalty += 1e9 + 1e7 * min_c * min_c
        return penalty, min_c, max_c, mean_c

    base_ratio = max(head_box.size.x / h_box.size.x, head_box.size.z / h_box.size.z)
    s_min = max(1e-4, 0.70 * base_ratio)
    s_max = max(s_min * 1.5, 2.25 * max(base_ratio, head_box.size.y / h_box.size.y))

    best_pen = float("inf")
    cur_s = base_ratio
    cur_ax = head_box.center.x
    cur_ay = head_box.max_pt.y + target_clearance_mm + 4.0 - cur_s * top_from_center
    cur_az = head_box.center.z
    candidates: list[tuple[float, float, float, float, float]] = []

    grid_steps = 20
    for i in range(grid_steps + 1):
        s = s_min + (s_max - s_min) * (i / grid_steps)
        base_ay = head_box.max_pt.y + target_clearance_mm + 4.0 - s * top_from_center
        for dy in (-8.0, -4.0, 0.0, 4.0, 8.0):
            ay = base_ay + dy
            pen, _, _, _ = eval_stats(s, head_box.center.x, ay, head_box.center.z)
            candidates.append((pen, s, head_box.center.x, ay, head_box.center.z))
            if pen < best_pen:
                best_pen = pen
                cur_s = s
                cur_ax = head_box.center.x
                cur_ay = ay
                cur_az = head_box.center.z

    for step_mm in (6.0, 3.0, 1.5, 0.75, 0.35):
        improved = True
        while improved:
            improved = False
            deltas = (
                (0.0, step_mm, 0.0),
                (0.0, -step_mm, 0.0),
                (0.0, 0.0, step_mm),
                (0.0, 0.0, -step_mm),
                (step_mm * 0.5, 0.0, 0.0),
                (-step_mm * 0.5, 0.0, 0.0),
            )
            for dx, dy, dz in deltas:
                nax, nay, naz = cur_ax + dx, cur_ay + dy, cur_az + dz
                pen, _, _, _ = eval_stats(cur_s, nax, nay, naz)
                if pen + 1e-6 < best_pen:
                    cur_ax, cur_ay, cur_az = nax, nay, naz
                    best_pen = pen
                    improved = True
                    candidates.append((best_pen, cur_s, cur_ax, cur_ay, cur_az))

        for s_delta in (-0.03, -0.012, -0.004, 0.004, 0.012, 0.03):
            ns = cur_s * (1.0 + s_delta)
            if not (s_min <= ns <= s_max):
                continue
            nay = cur_ay + (cur_s - ns) * top_from_center
            pen, _, _, _ = eval_stats(ns, cur_ax, nay, cur_az)
            if pen + 1e-6 < best_pen:
                cur_s = ns
                cur_ay = nay
                best_pen = pen
                candidates.append((best_pen, cur_s, cur_ax, cur_ay, cur_az))

    candidates.sort(key=lambda item: item[0])
    unique_transforms: list[Transform3D] = []
    for _, s, ax, ay, az in candidates:
        px, py, pz = to_world_position(s, ax, ay, az)
        t = Transform3D(
            position=Vec3(px, py, pz),
            rotation=rot,
            scale=Vec3(s, s, s),
        )
        if all(
            abs(t.scale.x - u.scale.x) > 1e-4
            or (t.position - u.position).length > 0.25
            for u in unique_transforms
        ):
            unique_transforms.append(t)
        if len(unique_transforms) >= 3:
            break

    best_transform = unique_transforms[0]
    best_report = _evaluate_candidate(helmet_bvh, head_bvh, full_samples, best_transform)

    def report_rank(rep: FitClearanceReport) -> tuple[int, int, int, float]:
        valid_flag = 0 if rep.is_valid else 1
        collision_flag = 0 if rep.intersecting_triangles == 0 else 1
        min_ok_flag = 0 if rep.min_clearance_mm >= min_clearance_mm else 1
        gap_err = (
            abs(rep.mean_clearance_mm - target_clearance_mm)
            + max(0.0, min_clearance_mm - rep.min_clearance_mm) * 50.0
            + max(0.0, rep.max_clearance_mm - max_clearance_mm) * 10.0
        )
        return (valid_flag, collision_flag, min_ok_flag, gap_err)

    for cand_t in unique_transforms[1:]:
        cand_rep = _evaluate_candidate(helmet_bvh, head_bvh, full_samples, cand_t)
        if report_rank(cand_rep) < report_rank(best_report):
            best_transform = cand_t
            best_report = cand_rep

    if best_report.intersecting_triangles > 0 or best_report.min_clearance_mm < min_clearance_mm:
        base_s = best_transform.scale.x
        base_ax = best_transform.position.x + base_s * h_center.x
        base_ay = best_transform.position.y + base_s * h_center.y
        base_az = best_transform.position.z + base_s * h_center.z
        for mult in (1.03, 1.07, 1.12, 1.20, 1.32):
            ns = base_s * mult
            px, py, pz = to_world_position(ns, base_ax, base_ay + (base_s - ns) * top_from_center, base_az)
            cand_t = Transform3D(position=Vec3(px, py, pz), rotation=rot, scale=Vec3(ns, ns, ns))
            cand_rep = _evaluate_candidate(helmet_bvh, head_bvh, full_samples, cand_t)
            if report_rank(cand_rep) < report_rank(best_report):
                best_transform = cand_t
                best_report = cand_rep
            if best_report.intersecting_triangles == 0 and best_report.min_clearance_mm >= min_clearance_mm:
                break

    return FitResult(
        transform=best_transform,
        report=best_report,
        converged=best_report.is_valid,
    )


def fit_helmet_to_mannequin(
    mannequin: GeneratedHead,
    helmet_mesh: MeshData,
    *,
    head_measurements: HeadMeasurements,
    initial_rotation: Vec3 = Vec3(0.0, 0.0, 0.0),
    target_clearance_mm: float = 3.5,
    min_clearance_mm: float = 1.5,
    max_clearance_mm: float = 25.0,
) -> FitResult:
    """Refine an ellipsoid fit against a Y-up, +Z-front anatomical mannequin.

    Clearance samples cover the head at Y >= 0, including the nose, ears, jaw
    and occiput. Collision tests include the entire mannequin. Convergence
    requires zero collisions and the requested minimum sampled clearance.
    The requested maximum and target rank feasible corrections; uncovered
    head surfaces can still report a large maximum. The search is bounded.
    """
    if not isinstance(mannequin, GeneratedHead):
        raise ValueError("mannequin must be GeneratedHead")
    mannequin.mesh.__post_init__()
    if not mannequin.mesh.triangles:
        raise ValueError("mannequin must contain triangles")

    # Use the established fitter and keep broad shoulders out of the seed.
    smooth_head = generate_head_mesh(head_measurements)
    seed = fit_helmet(
        smooth_head, helmet_mesh, initial_rotation,
        target_clearance_mm, min_clearance_mm, max_clearance_mm,
    ).transform
    helmet_bvh = _TriangleBVH(helmet_mesh)
    head_bvh = _TriangleBVH(mannequin.mesh)
    mesh = mannequin.mesh
    # The legacy cranium subset by itself can exclude the nose and ears.
    head_faces = [
        index for index, face in enumerate(mesh.triangles)
        if any(mesh.vertices[i].y >= 0 for i in face)
    ]
    sampling_head = GeneratedHead(mesh, head_faces, mannequin.actual_circumference_mm)
    samples = [
        point for point in _collect_cranium_samples(sampling_head, max_samples=None)
        if point.y >= 0
    ]
    if not samples:
        raise ValueError("mannequin has no head surface at Y >= 0")

    pivot = smooth_head.mesh.bounding_box.center

    def evaluated(transform: Transform3D) -> FitResult:
        report = _evaluate_candidate(helmet_bvh, head_bvh, samples, transform)
        converged = (
            report.intersecting_triangles == 0
            and report.min_clearance_mm >= min_clearance_mm
        )
        return FitResult(transform, report, converged)

    def rank(result: FitResult) -> tuple[bool, int, float, float]:
        report = result.report
        return (
            not result.converged,
            report.intersecting_triangles,
            max(0.0, min_clearance_mm - report.min_clearance_mm),
            abs(report.mean_clearance_mm - target_clearance_mm)
            + max(0.0, report.max_clearance_mm - max_clearance_mm),
        )

    best = evaluated(seed)
    if best.converged:
        return best

    # Scale around the smooth head centre in world space. Moving a +Z visor
    # forward can free the nose, but consumes rear clearance. A rearward move
    # can help with slanted geometry, so validate both signs against all samples.
    displacements = (0.0, 2.0, -2.0, 4.0, -4.0, 8.0, -8.0, 12.0, -12.0)
    for factor in (1.0, 1.025, 1.05, 1.08, 1.12, 1.18, 1.25, 1.32):
        position = pivot + _scaled_vector(seed.position - pivot, factor)
        scale = seed.scale.x * factor
        for shift in displacements:
            if factor == 1.0 and shift == 0.0:
                continue
            candidate = evaluated(Transform3D(
                position=Vec3(position.x, position.y, position.z + shift),
                rotation=seed.rotation,
                scale=Vec3(scale, scale, scale),
            ))
            if rank(candidate) < rank(best):
                best = candidate
        if best.converged:
            return best
    return best


def _scaled_vector(vector: Vec3, factor: float) -> Vec3:
    return Vec3(vector.x * factor, vector.y * factor, vector.z * factor)
