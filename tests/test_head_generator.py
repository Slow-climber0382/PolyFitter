from collections import Counter
import pytest
from core.contracts import HeadMeasurements
from core.head_generator import generate_head_mesh
from core.mesh_io import load_stl, save_stl
from core.sections import slice_mesh


def _signed_volume_mm3(vertices, triangles) -> float:
    total = 0.0
    for i0, i1, i2 in triangles:
        a, b, c = vertices[i0], vertices[i1], vertices[i2]
        cx = b.y * c.z - b.z * c.y
        cy = b.z * c.x - b.x * c.z
        cz = b.x * c.y - b.y * c.x
        total += a.x * cx + a.y * cy + a.z * cz
    return total / 6.0


def test_head_dimensions_and_circumference_accuracy():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=64, height_rings=48)

    box = head.mesh.bounding_box
    assert box.min_pt.y == pytest.approx(0.0, abs=1e-9)
    assert box.max_pt.y == pytest.approx(240.0, abs=1e-9)
    assert box.size.x == pytest.approx(160.0, abs=1e-6)
    assert box.size.y == pytest.approx(240.0, abs=1e-6)
    assert box.size.z == pytest.approx(200.0, abs=1e-6)
    assert head.actual_circumference_mm == pytest.approx(580.0, abs=1e-4)

    # Verify actual sliced horizontal perimeter at the brow level matches target circumference
    brow_y = (round(0.625 * 48) / 48) * 240.0
    segments = slice_mesh(head.mesh, axis="y", level_mm=brow_y)
    sliced_perimeter = sum((p2 - p1).length for p1, p2 in segments)
    assert sliced_perimeter == pytest.approx(580.0, abs=1e-3)


def test_head_is_watertight_manifold_with_outward_normals():
    m = HeadMeasurements(circumference_mm=560.0, width_mm=154.0, depth_mm=192.0, height_mm=230.0)
    head = generate_head_mesh(m, radial_segments=32, height_rings=24)

    directed_edges = Counter()
    undirected_edges = Counter()
    for i0, i1, i2 in head.mesh.triangles:
        for u, v in ((i0, i1), (i1, i2), (i2, i0)):
            directed_edges[(u, v)] += 1
            undirected_edges[(min(u, v), max(u, v))] += 1

    # Every undirected edge belongs to exactly 2 triangles in opposite directions
    assert all(count == 2 for count in undirected_edges.values())
    assert all(count == 1 for count in directed_edges.values())
    for (u, v) in directed_edges:
        assert directed_edges[(v, u)] == 1

    # Positive signed volume proves outward-facing winding order
    assert _signed_volume_mm3(head.mesh.vertices, head.mesh.triangles) > 1_000_000.0


def test_jaw_is_narrower_than_upper_cranium():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=48, height_rings=32)

    jaw_slice = slice_mesh(head.mesh, axis="y", level_mm=48.0)    # 20% height
    brow_slice = slice_mesh(head.mesh, axis="y", level_mm=150.0)  # 62.5% height
    jaw_width = max(p.x for seg in jaw_slice for p in seg) - min(p.x for seg in jaw_slice for p in seg)
    brow_width = max(p.x for seg in brow_slice for p in seg) - min(p.x for seg in brow_slice for p in seg)
    assert jaw_width < brow_width * 0.75


def test_cranium_zone_and_stl_roundtrip(tmp_path):
    m = HeadMeasurements(circumference_mm=590.0, width_mm=162.0, depth_mm=204.0, height_mm=245.0)
    head = generate_head_mesh(m, radial_segments=32, height_rings=24)

    assert len(head.cranium_triangle_indices) > 0
    assert len(head.cranium_triangle_indices) < len(head.mesh.triangles)
    for idx in head.cranium_triangle_indices:
        i0, i1, i2 = head.mesh.triangles[idx]
        cy = (head.mesh.vertices[i0].y + head.mesh.vertices[i1].y + head.mesh.vertices[i2].y) / 3.0
        assert cy >= 0.55 * m.height_mm

    out = tmp_path / "head.stl"
    save_stl(head.mesh, out, binary=True)
    reloaded = load_stl(out)
    assert len(reloaded.triangles) == len(head.mesh.triangles)
    assert reloaded.bounding_box.size.x == pytest.approx(m.width_mm, abs=1e-4)


def test_incompatible_circumference_and_bad_args_rejected():
    # Ellipse 150 x 190 mm has perimeter ~536.2 mm; 450 mm is physically impossible
    impossible_small = HeadMeasurements(circumference_mm=450.0, width_mm=150.0, depth_mm=190.0, height_mm=230.0)
    with pytest.raises(ValueError, match="incompatible"):
        generate_head_mesh(impossible_small)

    # Bounding rectangle perimeter is 2*(150+190) = 680 mm; 750 mm is impossible
    impossible_large = HeadMeasurements(circumference_mm=750.0, width_mm=150.0, depth_mm=190.0, height_mm=230.0)
    with pytest.raises(ValueError, match="incompatible"):
        generate_head_mesh(impossible_large)

    valid = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    with pytest.raises(ValueError):
        generate_head_mesh(valid, radial_segments=8)
    with pytest.raises(ValueError):
        generate_head_mesh(valid, height_rings=4)
