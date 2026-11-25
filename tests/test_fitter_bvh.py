import pytest

from core import fitter
from core.clearance import evaluate_helmet_clearance
from core.contracts import HeadMeasurements, Transform3D, Vec3
from core.head_generator import generate_head_mesh
from tests.test_clearance import _offset_open_helmet_shell


@pytest.mark.parametrize("scale,y", [(1.0, 0.0), (0.96, 3.0), (1.08, -2.0)])
def test_local_candidate_matches_world_report(scale, y):
    head = generate_head_mesh(HeadMeasurements(580, 160, 200, 240), 16, 12)
    helmet = _offset_open_helmet_shell(head, inner_offset_mm=3, wall_thickness_mm=4)
    transform = Transform3D(Vec3(1, y, -2), Vec3(4, -7, 2), Vec3(scale, scale, scale))
    expected = evaluate_helmet_clearance(head, helmet, transform)
    actual = fitter._evaluate_candidate(
        fitter._TriangleBVH(helmet), fitter._TriangleBVH(head.mesh),
        fitter._collect_cranium_samples(head, max_samples=None), transform,
    )
    assert actual.intersecting_triangles == expected.intersecting_triangles
    assert actual.is_valid == expected.is_valid
    for field in ("min_clearance_mm", "mean_clearance_mm", "max_clearance_mm"):
        assert getattr(actual, field) == pytest.approx(getattr(expected, field), abs=1e-9, rel=0)


def test_solver_builds_only_two_bvhs(monkeypatch):
    head = generate_head_mesh(HeadMeasurements(580, 160, 200, 240), 16, 12)
    helmet = _offset_open_helmet_shell(head, inner_offset_mm=3, wall_thickness_mm=4)
    original = fitter._TriangleBVH
    inputs = []

    def track(mesh):
        inputs.append(mesh)
        return original(mesh)

    monkeypatch.setattr(fitter, "_TriangleBVH", track)
    result = fitter.fit_helmet(head, helmet)
    assert len(inputs) == 2 and inputs[0] is helmet and inputs[1] is head.mesh
    reference = evaluate_helmet_clearance(head, helmet, result.transform)
    assert result.report.intersecting_triangles == reference.intersecting_triangles
    assert result.report.mean_clearance_mm == pytest.approx(reference.mean_clearance_mm, abs=1e-9, rel=0)
