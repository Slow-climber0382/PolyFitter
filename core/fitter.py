"""Automatic uniform-scale + translation helmet fitting solver in mm (Y-up)."""
from dataclasses import dataclass
import math
from .clearance import _TriangleBVH, evaluate_helmet_clearance
from .contracts import FitClearanceReport, MeshData, Transform3D, Vec3
from .head_generator import GeneratedHead
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


def _collect_cranium_samples(head: GeneratedHead, max_samples: int = 160) -> list[Vec3]:
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

    if len(samples) <= max_samples:
        return samples
    step = len(samples) / max_samples
    return [samples[int(i * step)] for i in range(max_samples)]


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
    samples = _collect_cranium_samples(head, max_samples=160)

    # Parameterize around oriented helmet bounding-box center h_center:
    # world_pt = anchor + scale * (R(local_pt) - h_center)
    #          = (anchor - scale * h_center) + scale * R(local_pt)
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

        penalty = mse
        if min_c < min_clearance_mm:
            deficit = min_clearance_mm - min_c
            penalty += 2000.0 * deficit * deficit + 500.0
        if max_c > max_clearance_mm:
            excess = max_c - max_clearance_mm
            penalty += 150.0 * excess * excess + 50.0
        return penalty, min_c, max_c, mean_c

    # Physically bounded uniform scale range based on head-to-helmet extents
    base_ratio = max(head_box.size.x / h_box.size.x, head_box.size.z / h_box.size.z)
    s_min = max(1e-4, 0.70 * base_ratio)
    s_max = max(s_min * 1.5, 2.25 * max(base_ratio, head_box.size.y / h_box.size.y))

    # Coarse grid search over bounded scale and vertical crown alignment
    best_pen = float("inf")
    cur_s = base_ratio
    cur_ax = head_box.center.x
    cur_ay = head_box.max_pt.y + target_clearance_mm + 4.0 - cur_s * top_from_center
    cur_az = head_box.center.z
    candidates: list[tuple[float, float, float, float, float]] = []

    grid_steps = 24
    for i in range(grid_steps + 1):
        s = s_min + (s_max - s_min) * (i / grid_steps)
        base_ay = head_box.max_pt.y + target_clearance_mm + 4.0 - s * top_from_center
        for dy in (-10.0, -5.0, 0.0, 5.0, 10.0):
            ay = base_ay + dy
            pen, _, _, _ = eval_stats(s, head_box.center.x, ay, head_box.center.z)
            candidates.append((pen, s, head_box.center.x, ay, head_box.center.z))
            if pen < best_pen:
                best_pen = pen
                cur_s = s
                cur_ax = head_box.center.x
                cur_ay = ay
                cur_az = head_box.center.z

    # Coordinate pattern search over anchor translation (Y, Z, X) and in-place scale
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
            # Keep crown clearance constant while scaling around center
            nay = cur_ay + (cur_s - ns) * top_from_center
            pen, _, _, _ = eval_stats(ns, cur_ax, nay, cur_az)
            if pen + 1e-6 < best_pen:
                cur_s = ns
                cur_ay = nay
                best_pen = pen
                candidates.append((best_pen, cur_s, cur_ax, cur_ay, cur_az))

    # Verify top distinct candidates with full exact clearance & triangle collision check
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
        if len(unique_transforms) >= 4:
            break

    best_transform = unique_transforms[0]
    best_report = evaluate_helmet_clearance(head, helmet_mesh, helmet_transform=best_transform)

    def report_rank(rep: FitClearanceReport) -> tuple[int, int, float]:
        valid_flag = 0 if rep.is_valid else 1
        collision_flag = 0 if rep.intersecting_triangles == 0 else 1
        gap_err = (
            abs(rep.mean_clearance_mm - target_clearance_mm)
            + max(0.0, min_clearance_mm - rep.min_clearance_mm) * 50.0
            + max(0.0, rep.max_clearance_mm - max_clearance_mm) * 10.0
        )
        return (valid_flag, collision_flag, gap_err)

    for cand_t in unique_transforms[1:]:
        cand_rep = evaluate_helmet_clearance(head, helmet_mesh, helmet_transform=cand_t)
        if report_rank(cand_rep) < report_rank(best_report):
            best_transform = cand_t
            best_report = cand_rep

    # If full-mesh verification found minor collision on an incompatible geometry, step scale up cleanly
    if best_report.intersecting_triangles > 0 or best_report.min_clearance_mm < min_clearance_mm:
        for mult in (1.02, 1.05, 1.10, 1.18, 1.30):
            ns = best_transform.scale.x * mult
            px, py, pz = to_world_position(ns, cur_ax, cur_ay + (cur_s - ns) * top_from_center, cur_az)
            cand_t = Transform3D(position=Vec3(px, py, pz), rotation=rot, scale=Vec3(ns, ns, ns))
            cand_rep = evaluate_helmet_clearance(head, helmet_mesh, helmet_transform=cand_t)
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
