import pytest
from core.contracts import HeadMeasurements, Transform3D, Vec3
from core.fitter import fit_helmet
from core.head_generator import generate_head_mesh
from core.transforms import apply_transform
from tests.test_clearance import _offset_open_helmet_shell


def test_fitter_recovers_fit_from_shifted_and_misscaled_helmet():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=24, height_rings=16)

    # Create a valid 3 mm helmet, then shrink it by 50% and shift far away from the head
    ideal_helmet = _offset_open_helmet_shell(head, inner_offset_mm=3.0, wall_thickness_mm=4.0)
    unfitted_helmet = apply_transform(
        ideal_helmet,
        Transform3D(position=Vec3(450.0, -320.0, 210.0), scale=Vec3(0.5, 0.5, 0.5)),
    )

    result = fit_helmet(head, unfitted_helmet)
    assert result.converged is True
    assert result.report.is_valid is True
    assert result.report.intersecting_triangles == 0
    assert 2.0 <= result.report.min_clearance_mm <= 4.0
    assert 2.0 <= result.report.max_clearance_mm <= 4.0
    assert result.report.mean_clearance_mm == pytest.approx(3.0, abs=0.4)


def test_fitter_handles_rotated_import_orientation():
    m = HeadMeasurements(circumference_mm=565.0, width_mm=155.0, depth_mm=195.0, height_mm=235.0)
    head = generate_head_mesh(m, radial_segments=24, height_rings=16)

    ideal_helmet = _offset_open_helmet_shell(head, inner_offset_mm=3.0, wall_thickness_mm=4.0)
    # Simulate a helmet exported sideways (+90 deg around X) and scaled to cm (0.1x)
    sideways_cm_helmet = apply_transform(
        ideal_helmet,
        Transform3D(position=Vec3(-100.0, 50.0, 80.0), rotation=Vec3(90.0, 0.0, 0.0), scale=Vec3(0.1, 0.1, 0.1)),
    )

    result = fit_helmet(head, sideways_cm_helmet, initial_rotation=Vec3(-90.0, 0.0, 0.0))
    assert result.converged is True
    assert result.report.is_valid is True
    assert result.report.intersecting_triangles == 0


def test_fitter_reports_non_convergence_for_incompatible_helmet_aspect_ratio():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=20, height_rings=14)

    # Stretch helmet depth by 1.6x while keeping width 1.0x -> uniform scaling cannot fit within 2-4 mm everywhere
    base_helmet = _offset_open_helmet_shell(head, inner_offset_mm=3.0, wall_thickness_mm=4.0)
    distorted_helmet = apply_transform(base_helmet, Transform3D(scale=Vec3(1.0, 1.0, 1.6)))

    result = fit_helmet(head, distorted_helmet)
    assert result.converged is False
    assert result.report.is_valid is False
    assert result.report.intersecting_triangles == 0
    assert result.report.min_clearance_mm >= 2.0


def test_fitter_input_validation():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=16, height_rings=12)

    with pytest.raises(ValueError):
        fit_helmet(head, head.mesh, target_clearance_mm=5.0)
    with pytest.raises(ValueError):
        fit_helmet(head, head.mesh, min_clearance_mm=3.5, max_clearance_mm=3.0)
