import math
import pytest
from core.contracts import MeshData, Transform3D, Vec3
from core.sections import slice_mesh
from core.transforms import apply_transform, transform_point


def test_identity_transform():
    mesh = MeshData(
        name="shell",
        vertices=[Vec3(1.0, 2.0, 3.0), Vec3(4.0, 2.0, 3.0), Vec3(1.0, 5.0, 3.0)],
        triangles=[(0, 1, 2)],
        normals=[Vec3(0.0, 0.0, 1.0)] * 3,
    )
    result = apply_transform(mesh, Transform3D())
    assert result.name == "shell"
    assert result.vertices == mesh.vertices
    assert result.triangles == mesh.triangles
    assert result.normals == mesh.normals
    assert result is not mesh
    assert result.vertices is not mesh.vertices
    assert result.triangles is not mesh.triangles


def test_analytical_two_axis_rotation_scale_and_translation():
    # scale(2, 4, 1) -> Rx(90) -> Ry(90) -> translate(10, -20, 30)
    # (1, 0, 0) -> (2, 0, 0) -> (2, 0, 0) -> (0, 0, -2) -> (10, -20, 28)
    # (0, 1, 0) -> (0, 4, 0) -> (0, 0, 4) -> (4, 0, 0) -> (14, -20, 30)
    t = Transform3D(
        position=Vec3(10.0, -20.0, 30.0),
        rotation=Vec3(90.0, 90.0, 0.0),
        scale=Vec3(2.0, 4.0, 1.0),
    )
    p_b = transform_point(Vec3(1.0, 0.0, 0.0), t)
    p_c = transform_point(Vec3(0.0, 1.0, 0.0), t)
    assert (p_b.x, p_b.y, p_b.z) == pytest.approx((10.0, -20.0, 28.0), abs=1e-12)
    assert (p_c.x, p_c.y, p_c.z) == pytest.approx((14.0, -20.0, 30.0), abs=1e-12)


def test_non_uniform_scale_preserves_normal_orthogonality():
    # Triangle in plane x + y = 1; geometric normal is (1, 1, 0) / sqrt(2)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    n0 = Vec3(inv_sqrt2, inv_sqrt2, 0.0)
    mesh = MeshData(
        name="slant",
        vertices=[Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Vec3(0.0, 1.0, 5.0)],
        triangles=[(0, 1, 2)],
        normals=[n0, n0, n0],
    )
    t = Transform3D(
        position=Vec3(-15.0, 40.0, 5.0),
        rotation=Vec3(25.0, -40.0, 15.0),
        scale=Vec3(3.0, 0.5, 2.0),
    )
    transformed = apply_transform(mesh, t, new_name="slant_world")
    assert transformed.name == "slant_world"

    e1 = transformed.vertices[1] - transformed.vertices[0]
    e2 = transformed.vertices[2] - transformed.vertices[0]
    for n in transformed.normals:
        assert n.length == pytest.approx(1.0, abs=1e-12)
        dot1 = n.x * e1.x + n.y * e1.y + n.z * e1.z
        dot2 = n.x * e2.x + n.y * e2.y + n.z * e2.z
        assert dot1 == pytest.approx(0.0, abs=1e-12)
        assert dot2 == pytest.approx(0.0, abs=1e-12)


def test_extreme_scale_normal_normalization_and_overflow_rejection():
    mesh = MeshData(
        name="tiny_scale",
        vertices=[Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0)],
        triangles=[(0, 1, 2)],
        normals=[Vec3(1.0, 0.0, 0.0)] * 3,
    )
    ok = apply_transform(mesh, Transform3D(scale=Vec3(1e-200, 1.0, 1.0)))
    assert ok.normals[0] == Vec3(1.0, 0.0, 0.0)

    with pytest.raises(ValueError):
        apply_transform(mesh, Transform3D(scale=Vec3(1e-310, 1.0, 1.0)))


def test_input_mesh_not_mutated_and_validation():
    mesh = MeshData(
        name="part",
        vertices=[Vec3(0.0, 0.0, 0.0), Vec3(2.0, 0.0, 0.0), Vec3(0.0, 2.0, 0.0)],
        triangles=[(0, 1, 2)],
    )
    _ = apply_transform(mesh, Transform3D(position=Vec3(10.0, 20.0, 30.0)))
    assert mesh.vertices == [Vec3(0.0, 0.0, 0.0), Vec3(2.0, 0.0, 0.0), Vec3(0.0, 2.0, 0.0)]

    with pytest.raises(ValueError):
        apply_transform(mesh, Transform3D(), new_name="   ")
    with pytest.raises(ValueError):
        transform_point((0.0, 0.0, 0.0), Transform3D())  # type: ignore[arg-type]

    mesh.triangles.append((0, 1, 99))
    with pytest.raises(ValueError):
        apply_transform(mesh, Transform3D())


def test_integration_with_slice_mesh():
    # Local triangle y in [0, 10], scaled by 2 in Y and shifted by +100 mm -> y in [100, 120]
    tri = MeshData(
        name="fin",
        vertices=[Vec3(0.0, 0.0, 0.0), Vec3(10.0, 0.0, 0.0), Vec3(0.0, 10.0, 0.0)],
        triangles=[(0, 1, 2)],
    )
    world_tri = apply_transform(
        tri,
        Transform3D(position=Vec3(5.0, 100.0, -3.0), scale=Vec3(1.0, 2.0, 1.0)),
    )
    segments = slice_mesh(world_tri, axis="y", level_mm=110.0)
    assert len(segments) == 1
    p1, p2 = segments[0]
    assert (p1.x, p1.y, p1.z) == pytest.approx((5.0, 110.0, -3.0))
    assert (p2.x, p2.y, p2.z) == pytest.approx((10.0, 110.0, -3.0))
