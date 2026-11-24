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

    def eval_stats(scale: float, px: float, py: float, pz: float) -> tuple[float, float, float, float]:
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
            penalty += 1000.0 * deficit * deficit + 500.0
        if max_c > max_clearance_mm:
            excess = max_c - max_clearance_mm
            penalty += 250.0 * excess * excess + 100.0
        return penalty, min_c, max_c, mean_c

    def solve_scale_for_offset(px: float, py: float, pz: float, seed_scale: float) -> tuple[float, float]:
        # Maintain relative alignment of the helmet crown/center while scaling
        anchor_x = px + seed_scale * h_box.center.x
        anchor_y = py + seed_scale * h_box.max_pt.y
        anchor_z = pz + seed_scale * h_box.center.z

        def pos_at(s: float) -> tuple[float, float, float]:
            return (
                anchor_x - s * h_box.center.x,
                anchor_y - s * h_box.max_pt.y,
                anchor_z - s * h_box.center.z,
            )

        low = max(1e-4, seed_scale * 0.4)
        high = seed_scale * 2.5
        for _ in range(16):
            p_hi = pos_at(high)
            _, min_hi, _, _ = eval_stats(high, *p_hi)
            if min_hi >= target_clearance_mm:
                break
            low = high
            high *= 1.4

        for _ in range(16):
            mid = 0.5 * (low + high)
            p_mid = pos_at(mid)
            _, min_mid, _, _ = eval_stats(mid, *p_mid)
            if min_mid < target_clearance_mm:
                low = mid
            else:
                high = mid

        best_s = high
        best_pen = float("inf")
        for mult in (0.97, 0.985, 0.995, 1.0, 1.005, 1.015, 1.03):
            cand_s = best_s * mult
            if cand_s <= 1e-4:
                continue
            cand_p = pos_at(cand_s)
            pen, _, _, _ = eval_stats(cand_s, *cand_p)
            if pen < best_pen:
                best_pen = pen
                best_s = cand_s
        return best_s, best_pen

    # Initial alignment: match X/Z centers and align top of helmet above head crown
    est_wall_mm = 4.0
    scale_x = (head_box.size.x + 2.0 * (target_clearance_mm + est_wall_mm)) / h_box.size.x
    scale_z = (head_box.size.z + 2.0 * (target_clearance_mm + est_wall_mm)) / h_box.size.z
    cur_s = max(1e-3, max(scale_x, scale_z))
    cur_px = head_box.center.x - cur_s * h_box.center.x
    cur_py = (head_box.max_pt.y + target_clearance_mm + est_wall_mm) - cur_s * h_box.max_pt.y
    cur_pz = head_box.center.z - cur_s * h_box.center.z

    cur_s, _ = solve_scale_for_offset(cur_px, cur_py, cur_pz, cur_s)
    cur_px = head_box.center.x - cur_s * h_box.center.x
    cur_py = (head_box.max_pt.y + target_clearance_mm + est_wall_mm) - cur_s * h_box.max_pt.y
    cur_pz = head_box.center.z - cur_s * h_box.center.z
    cur_pen, _, _, _ = eval_stats(cur_s, cur_px, cur_py, cur_pz)

    candidates: list[tuple[float, float, float, float, float]] = [(cur_pen, cur_s, cur_px, cur_py, cur_pz)]

    # Coordinate pattern search over translation (Y, Z, X) and uniform scale
    for step_mm in (16.0, 8.0, 4.0, 2.0, 1.0, 0.5):
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
                nx, ny, nz = cur_px + dx, cur_py + dy, cur_pz + dz
                pen, _, _, _ = eval_stats(cur_s, nx, ny, nz)
                if pen + 1e-6 < cur_pen:
                    cur_px, cur_py, cur_pz = nx, ny, nz
                    cur_pen = pen
                    improved = True
                    candidates.append((cur_pen, cur_s, cur_px, cur_py, cur_pz))

        for s_delta in (-0.03, -0.01, -0.003, 0.003, 0.01, 0.03):
            ns = cur_s * (1.0 + s_delta)
            if ns <= 1e-4:
                continue
            # Scale about current head crown contact point
            nx = cur_px + (cur_s - ns) * h_box.center.x
            ny = cur_py + (cur_s - ns) * h_box.max_pt.y
            nz = cur_pz + (cur_s - ns) * h_box.center.z
            pen, _, _, _ = eval_stats(ns, nx, ny, nz)
            if pen + 1e-6 < cur_pen:
                cur_s = ns
                cur_px, cur_py, cur_pz = nx, ny, nz
                cur_pen = pen
                candidates.append((cur_pen, cur_s, cur_px, cur_py, cur_pz))

    # Verify top distinct candidates with full exact clearance & triangle collision check
    candidates.sort(key=lambda item: item[0])
    unique_transforms: list[Transform3D] = []
    for _, s, px, py, pz in candidates:
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
    best_report = evaluate_helmet_clearance(head, helmet_mesh, helmet_transform=best_transform)

    def report_rank(rep: FitClearanceReport) -> tuple[int, int, float]:
        valid_flag = 0 if rep.is_valid else 1
        collision_flag = 0 if rep.intersecting_triangles == 0 else 1
        gap_err = (
            abs(rep.mean_clearance_mm - target_clearance_mm)
            + max(0.0, min_clearance_mm - rep.min_clearance_mm) * 50.0
            + max(0.0, rep.max_clearance_mm - max_clearance_mm) * 20.0
        )
        return (valid_flag, collision_flag, gap_err)

    for cand_t in unique_transforms[1:]:
        cand_rep = evaluate_helmet_clearance(head, helmet_mesh, helmet_transform=cand_t)
        if report_rank(cand_rep) < report_rank(best_report):
            best_transform = cand_t
            best_report = cand_rep

    return FitResult(
        transform=best_transform,
        report=best_report,
        converged=best_report.is_valid,
    )
