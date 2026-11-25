from dataclasses import replace

import pytest

from core.clearance import evaluate_clearance, evaluate_regional_clearance
from core.contracts import FitClearanceReport, MeshData, RegionalClearance, Transform3D, Vec3


def triangle(name, x, y):
    return MeshData(name, [Vec3(x, y, 0), Vec3(x, y + 1, 0), Vec3(x, y, 1)], [(0, 1, 2)])


def test_regional_samples_and_boundary():
    upper = triangle("upper", 0, 45)
    lower = triangle("lower", 0, 0)
    head = MeshData("head", upper.vertices + lower.vertices, [(0, 1, 2), (3, 4, 5)])

    helmet_upper = triangle("upper shell", 3, 45)
    helmet_lower = triangle("lower shell", 7, 0)
    helmet = MeshData(
        "helmet", helmet_upper.vertices + helmet_lower.vertices, [(0, 1, 2), (3, 4, 5)]
    )
    report = evaluate_regional_clearance(head, helmet, 100, head_is_watertight=False)
    assert report.cranium == RegionalClearance(3, 3, 3, 4)
    assert report.lower == RegionalClearance(7, 7, 7, 4)
    assert replace(report, cranium=None, lower=None) == FitClearanceReport(3, 7, 5, 0)
    assert evaluate_clearance(head, helmet, head_is_watertight=False) == FitClearanceReport(3, 7, 5, 0)


@pytest.mark.parametrize("y, populated", [(0, "lower"), (45, "cranium")])
def test_empty_region_and_helmet_transform(y, populated):
    head = triangle("head", 0, y)
    helmet = triangle("helmet", 0, y)
    transform = Transform3D(position=Vec3(2, 0, 0))
    report = evaluate_regional_clearance(head, helmet, 100, transform, False)
    assert getattr(report, populated) == RegionalClearance(2, 2, 2, 4)
    assert getattr(report, "lower" if populated == "cranium" else "cranium") is None
    assert report.is_valid


@pytest.mark.parametrize("height", [0, -1, True, "100", float("nan"), float("inf")])
def test_reject_invalid_height(height):
    mesh = triangle("part", 0, 0)
    with pytest.raises(ValueError, match="height_mm"):
        evaluate_regional_clearance(mesh, mesh, height)
