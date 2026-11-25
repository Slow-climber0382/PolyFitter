from collections import Counter
import math

import pytest

from core.clearance import evaluate_helmet_clearance, evaluate_regional_clearance
from core.contracts import HeadMeasurements, MeshData, Vec3
from core.mannequin import generate_mannequin


@pytest.fixture(scope="module")
def mannequin():
    return generate_mannequin(
        HeadMeasurements(580, 160, 200, 240), 360, radial_segments=32, height_rings=24
    )


def test_closed_oriented_surface(mannequin):
    mesh = mannequin.mesh
    edges = Counter()
    volume_times_six = 0.0
    for i, j, k in mesh.triangles:
        edges.update(((i, j), (j, k), (k, i)))
        a, b, c = (mesh.vertices[index] for index in (i, j, k))
        u, v = b - a, c - a
        assert math.hypot(u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z, u.x * v.y - u.y * v.x) > 0
        volume_times_six += (
            a.x * (b.y * c.z - b.z * c.y)
            + a.y * (b.z * c.x - b.x * c.z)
            + a.z * (b.x * c.y - b.y * c.x)
        )
    assert all(count == edges[j, i] == 1 for (i, j), count in edges.items())
    assert len(mesh.vertices) - len(edges) // 2 + len(mesh.triangles) == 2
    assert volume_times_six > 0


def _perimeter(points):
    return sum((a - b).length for a, b in zip(points, points[1:] + points[:1]))


def test_measurements_and_orientation(mannequin):
    points = mannequin.mesh.vertices
    brow = [p for p in points if p.y == 150]
    neck = [p for p in points if p.y == -0.22 * 240]
    shoulders = [p for p in points if p.y == -0.56 * 240]
    assert len(brow) == len(neck) == 32
    assert max(p.x for p in brow) - min(p.x for p in brow) == pytest.approx(160)
    assert max(p.z for p in brow) - min(p.z for p in brow) == pytest.approx(200)
    assert _perimeter(brow) == pytest.approx(580)
    assert mannequin.actual_circumference_mm == pytest.approx(580)
    assert _perimeter(neck) == pytest.approx(360)
    assert max(abs(p.x) for p in shoulders) > max(abs(p.x) for p in neck)
    assert max(p.y for p in points) == 240
    assert max(p.z for p in points if p.y == 0) > 0
    nose = max(points, key=lambda p: p.z)
    assert abs(nose.x) < 1e-8 and 60 < nose.y < 120 and nose.z > 110


def test_clearance_entry_points_detect_visor_collision(mannequin):
    visor = MeshData("visor", [Vec3(-20, 60, 112), Vec3(20, 60, 112), Vec3(0, 132, 112)], [(0, 1, 2)])
    contact = evaluate_helmet_clearance(mannequin, visor)
    regional = evaluate_regional_clearance(mannequin.mesh, visor, 240)
    assert contact.intersecting_triangles == regional.intersecting_triangles == 1
    assert regional.cranium.sample_count > 0
    assert regional.lower.sample_count > regional.cranium.sample_count


@pytest.mark.parametrize("neck", [0, -1, True, float("inf"), float("nan")])
def test_invalid_neck(neck):
    with pytest.raises(ValueError, match="neck_circumference_mm"):
        generate_mannequin(HeadMeasurements(580, 160, 200, 240), neck)
