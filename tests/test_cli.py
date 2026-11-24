import json
from core.contracts import HeadMeasurements, Transform3D, Vec3
from core.head_generator import generate_head_mesh
from core.mesh_io import load_stl, save_stl
from core.project_io import load_project
from core.transforms import apply_transform
import polyfitter
from tests.test_clearance import _offset_open_helmet_shell


def test_cli_end_to_end_fit_and_exports(tmp_path, capsys):
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=24, height_rings=16)

    ideal_helmet = _offset_open_helmet_shell(head, inner_offset_mm=3.0, wall_thickness_mm=4.0)
    raw_helmet = apply_transform(
        ideal_helmet,
        Transform3D(position=Vec3(120.0, -80.0, 45.0), scale=Vec3(0.65, 0.65, 0.65)),
    )

    in_stl = tmp_path / "raw_helmet.stl"
    out_stl = tmp_path / "fitted_helmet.stl"
    out_head = tmp_path / "head.stl"
    out_proj = tmp_path / "scene.json"
    save_stl(raw_helmet, in_stl, binary=True)

    exit_code = polyfitter.main(
        [
            str(in_stl),
            "--circumference", "580",
            "--width", "160",
            "--depth", "200",
            "--height", "240",
            "--radial-segments", "24",
            "--height-rings", "16",
            "--out-mesh", str(out_stl),
            "--out-head", str(out_head),
            "--out-project", str(out_proj),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "PASS"
    assert payload["converged"] is True
    assert payload["clearance_mm"]["intersecting_triangles"] == 0
    assert 2.0 <= payload["clearance_mm"]["min"] <= 4.0
    assert 2.0 <= payload["clearance_mm"]["max"] <= 4.0

    assert out_stl.exists()
    assert out_head.exists()
    assert out_proj.exists()

    reloaded_helmet = load_stl(out_stl)
    assert len(reloaded_helmet.triangles) == len(raw_helmet.triangles)

    reloaded_project = load_project(out_proj)
    assert reloaded_project.head == m
    assert len(reloaded_project.parts) == 1
    assert reloaded_project.parts[0].transform.scale.x == payload["transform"]["scale"]


def test_cli_no_fit_failure_returns_exit_code_2(tmp_path, capsys):
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=20, height_rings=14)
    tight_helmet = _offset_open_helmet_shell(head, inner_offset_mm=0.8, wall_thickness_mm=4.0)

    in_stl = tmp_path / "tight.stl"
    save_stl(tight_helmet, in_stl, binary=True)

    exit_code = polyfitter.main(
        [
            str(in_stl),
            "--circumference", "580",
            "--width", "160",
            "--depth", "200",
            "--height", "240",
            "--radial-segments", "20",
            "--height-rings", "14",
            "--no-fit",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "FAIL" in captured.out


def test_cli_invalid_arguments_return_exit_code_1(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.stl"
    exit_code = polyfitter.main(
        [
            str(missing),
            "--circumference", "580",
            "--width", "160",
            "--depth", "200",
            "--height", "240",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error:" in captured.err
