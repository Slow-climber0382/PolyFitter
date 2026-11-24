"""Scene-space 3D transformations in millimetres (right-handed Y-up)."""
import math
from .contracts import MeshData, Transform3D, Vec3


def _rotate_xyz(x: float, y: float, z: float, rotation_deg: Vec3) -> tuple[float, float, float]:
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


def _normalize_components(x: float, y: float, z: float) -> Vec3:
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        raise ValueError("Transformed vector components must be finite")
    peak = max(abs(x), abs(y), abs(z))
    if peak == 0.0:
        raise ValueError("Cannot normalize zero-length vector")
    ux, uy, uz = x / peak, y / peak, z / peak
    norm = math.sqrt(ux * ux + uy * uy + uz * uz)
    if norm == 0.0 or not math.isfinite(norm):
        raise ValueError("Cannot normalize degenerate vector")
    return Vec3(ux / norm, uy / norm, uz / norm)


def transform_point(point: Vec3, transform: Transform3D) -> Vec3:
    """Apply axial scale, Euler XYZ rotation (degrees), and translation in mm."""
    if not isinstance(point, Vec3):
        raise ValueError("point must be Vec3")
    if not isinstance(transform, Transform3D):
        raise ValueError("transform must be Transform3D")

    sx = point.x * transform.scale.x
    sy = point.y * transform.scale.y
    sz = point.z * transform.scale.z
    rx, ry, rz = _rotate_xyz(sx, sy, sz, transform.rotation)
    return Vec3(
        rx + transform.position.x,
        ry + transform.position.y,
        rz + transform.position.z,
    )


def _transform_normal(normal: Vec3, transform: Transform3D) -> Vec3:
    # Inverse-transpose of Rz * Ry * Rx * S is Rz * Ry * Rx * S^-1.
    nx = normal.x / transform.scale.x
    ny = normal.y / transform.scale.y
    nz = normal.z / transform.scale.z
    unit_scaled = _normalize_components(nx, ny, nz)
    rx, ry, rz = _rotate_xyz(unit_scaled.x, unit_scaled.y, unit_scaled.z, transform.rotation)
    return _normalize_components(rx, ry, rz)


def apply_transform(
    mesh: MeshData,
    transform: Transform3D,
    new_name: str | None = None,
) -> MeshData:
    """Return a transformed copy of mesh in world coordinates without centring."""
    if not isinstance(mesh, MeshData):
        raise ValueError("mesh must be MeshData")
    if not isinstance(transform, Transform3D):
        raise ValueError("transform must be Transform3D")
    mesh.__post_init__()

    if new_name is not None:
        if not isinstance(new_name, str) or not new_name.strip():
            raise ValueError("new_name must not be empty")
        target_name = new_name
    else:
        target_name = mesh.name

    transformed_vertices = [transform_point(v, transform) for v in mesh.vertices]
    transformed_normals = (
        [_transform_normal(n, transform) for n in mesh.normals]
        if mesh.normals is not None
        else None
    )
    return MeshData(
        name=target_name,
        vertices=transformed_vertices,
        triangles=list(mesh.triangles),
        normals=transformed_normals,
    )
