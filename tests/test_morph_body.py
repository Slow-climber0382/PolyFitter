from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from core.contracts import MeshData, Vec3
from core.morph_body import (
    CircumferenceConstraint, MorphBody, load_morph_body, section_circumference,
    solve_morph_weights, to_generated_head,
)


@pytest.fixture
def body():
    vertices = [
        Vec3(x, y, z)
        for y in (0, 10, 20, 30)
        for x, z in ((1, -2), (1, 2), (-1, 2), (-1, -2))
    ]
    triangles = [(0, 1, 2), (0, 2, 3), (12, 14, 13), (12, 15, 14)]
    for r in (0, 4, 8):
        for i in range(4):
            a, b = r + i, r + (i + 1) % 4
            triangles.extend(((a, a + 4, b), (b, a + 4, b + 4)))
    return MorphBody(
        MeshData("prism", vertices, triangles),
        {
            "bust_volume": [(i, 0, 0, 3) for i in (1, 2, 5, 6)],
            "head_width": [(i, vertices[i].x, 0, 0) for i in range(8, 16)],
            "bad_bust": [(0, 0, 0, -1)],
        },
    )


def test_section_length_between_rings_and_on_ring(body):
    assert section_circumference(body.base, 5) == pytest.approx(12)
    assert section_circumference(body.base, 10) == pytest.approx(12)
    with pytest.raises(ValueError, match="closed contour"):
        section_circumference(body.base, 31)


def test_calibration_and_front_back_isolation(body):
    constraints = [
        CircumferenceConstraint("bust_volume", 5, 15.321, front_only_from_z_mm=0),
        CircumferenceConstraint("head_width", 25, 13.234),
    ]
    weights = solve_morph_weights(body, constraints)
    result = body.apply(weights)
    for goal in constraints:
        assert section_circumference(result, goal.level_mm) == pytest.approx(goal.circumference_mm, abs=0.01)
    for before, after in zip(body.base.vertices[:8], result.vertices[:8]):
        if before.z < 0:
            assert after == before
        else:
            assert after.z > before.z
    assert to_generated_head(result, 25).actual_circumference_mm == pytest.approx(13.234, abs=0.01)


def test_rejects_back_movement_and_unreachable_goal(body):
    with pytest.raises(ValueError, match="outside its front region"):
        solve_morph_weights(body, [CircumferenceConstraint("bad_bust", 5, 14, front_only_from_z_mm=0)])
    with pytest.raises(ValueError, match="residuals"):
        solve_morph_weights(body, [CircumferenceConstraint("bust_volume", 5, 100)], max_passes=2)


def test_rejects_open_base_and_invalid_indices(body):
    with pytest.raises(ValueError, match="boundary"):
        MorphBody(replace(body.base, triangles=body.base.triangles[1:]), {})
    with pytest.raises(ValueError, match="vertex index"):
        MorphBody(body.base, {"bad": [(len(body.base.vertices), 1, 0, 0)]})


def test_export_orientation_and_vertex_order(body, tmp_path):
    # Invert the selected source transform: mm (X,Y,Z) = 10 * (X,Z,-Y).
    obj = tmp_path / "source.obj"
    lines = [f"v {v.x / 10} {-v.z / 10} {v.y / 10}" for v in body.base.vertices]
    # A face referencing late vertices comes first, exposing accidental OBJ remapping.
    lines += [f"f {a+1} {b+1} {c+1}" for a, b, c in reversed(body.base.triangles)]
    obj.write_text("\n".join(lines), encoding="ascii")
    target = tmp_path / "front.target"
    target.write_text("1 0 -0.3 0\n", encoding="ascii")
    out = tmp_path / "package"
    script = Path(__file__).resolve().parents[1] / "tools/export_mpfb2_base.py"
    subprocess.run([
        sys.executable, str(script), str(obj), str(out), "--unit-scale", "10",
        "--up", "Z", "--front=-Y", "--target", f"bust_volume={target}",
    ], check=True, cwd=tmp_path)
    loaded = load_morph_body(out / "morphs.json")
    assert loaded.base.vertices == body.base.vertices
    assert loaded.targets == {"bust_volume": [(1, 0, 0, 3)]}
    assert loaded.apply({"bust_volume": 1}).vertices[1] == Vec3(1, 0, 5)
    base = out / "base.obj"
    base.write_bytes(base.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum"):
        load_morph_body(out / "morphs.json")
