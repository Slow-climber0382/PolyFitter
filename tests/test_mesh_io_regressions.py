import tempfile
import math
import struct
import pytest
from core.contracts import Vec3, MeshData, Transform3D
from core.mesh_io import load_stl, save_stl, load_obj, list_obj_groups


def test_load_stl_ascii_utf8_solid_name_and_bom(tmp_path):
    p = tmp_path / "helm_pl.stl"
    content = (
        "\ufeffsolid Hełm_testowy_1\n"
        "  facet normal 0 0 1\n"
        "    outer loop\n"
        "      vertex 0 0 0\n"
        "      vertex 10 0 0\n"
        "      vertex 0 10 0\n"
        "    endloop\n"
        "  endfacet\n"
        "endsolid Hełm_testowy_1\n"
    )
    p.write_bytes(content.encode("utf-8"))
    mesh = load_stl(p)
    assert mesh.name == "helm_pl"
    assert len(mesh.triangles) == 1
    assert mesh.vertices == [Vec3(0, 0, 0), Vec3(10, 0, 0), Vec3(0, 10, 0)]


def test_load_obj_backslash_line_continuation(tmp_path):
    p = tmp_path / "wrapped.obj"
    p.write_text(
        "v 0 0 0\n"
        "v 10 0 0\n"
        "v 10 20 0\n"
        "v 0 20 0\n"
        "o visor\n"
        "f 1 2 \\\n"
        "  3 4\n",
        encoding="utf-8",
    )
    mesh = load_obj(p, group_name="visor")
    assert len(mesh.vertices) == 4
    assert mesh.triangles == [(0, 1, 2), (0, 2, 3)]


def test_load_obj_rejects_empty_group_name(tmp_path):
    p = tmp_path / "ungrouped_head.obj"
    p.write_text(
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "f 1 2 3\n"
        "o helmet\n"
        "f 1 3 2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_obj(p, group_name="")


def test_save_stl_preserves_existing_file_on_write_error(tmp_path, monkeypatch):
    p = tmp_path / "existing.stl"
    p.write_bytes(b"EXISTING_VALID_STL")
    mesh = MeshData(
        "tri",
        [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)],
        [(0, 1, 2)],
    )

    real_ntf = tempfile.NamedTemporaryFile

    class FailingTempFile:
        def __init__(self, *args, **kwargs):
            self._f = real_ntf(*args, **kwargs)
            self.name = self._f.name

        def write(self, data):
            self._f.close()
            raise OSError("Simulated disk full mid-export")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if not self._f.closed:
                self._f.close()
            return False

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", FailingTempFile)
    with pytest.raises(OSError):
        save_stl(mesh, p, binary=True)

    assert p.read_bytes() == b"EXISTING_VALID_STL"
    assert [f.name for f in tmp_path.iterdir()] == ["existing.stl"]


def test_save_stl_analytical_two_axis_rotation_and_non_uniform_scale(tmp_path):
    mesh = MeshData(
        "panel",
        [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0)],
        [(0, 1, 2)],
    )
    transform = Transform3D(
        position=Vec3(10.0, -20.0, 30.0),
        rotation=Vec3(90.0, 90.0, 0.0),
        scale=Vec3(2.0, 4.0, 1.0),
    )
    out = tmp_path / "transformed.stl"
    save_stl(mesh, out, binary=True, transform=transform)

    assert mesh.vertices == [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0)]

    reloaded = load_stl(out)
    expected_verts = [
        (10.0, -20.0, 30.0),
        (10.0, -20.0, 28.0),
        (14.0, -20.0, 30.0),
    ]
    for v, exp in zip(reloaded.vertices, expected_verts):
        assert (v.x, v.y, v.z) == pytest.approx(exp, abs=1e-6)

    normal = struct.unpack_from("<3f", out.read_bytes(), 84)
    assert normal == pytest.approx((0.0, -1.0, 0.0), abs=1e-6)

    tilted = MeshData(
        "tilted",
        [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 1.0), Vec3(0.0, 1.0, 0.0)],
        [(0, 1, 2)],
    )
    out_tilted = tmp_path / "tilted_scaled.stl"
    save_stl(tilted, out_tilted, binary=True, transform=Transform3D(scale=Vec3(2.0, 1.0, 1.0)))
    tilted_normal = struct.unpack_from("<3f", out_tilted.read_bytes(), 84)
    inv_sqrt5 = 1.0 / math.sqrt(5.0)
    assert tilted_normal == pytest.approx((-inv_sqrt5, 0.0, 2.0 * inv_sqrt5), abs=1e-6)


def test_load_obj_independent_o_g_comments_and_unused_vertices(tmp_path):
    p = tmp_path / "multi.obj"
    p.write_text(
        "# Naglowek komentarza\n"
        "v 100 200 300 # nieuzywany wierzcholek 1\n"
        "v 0 0 0\n"
        "v 5 0 0\n"
        "v 0 5 0\n"
        "v 0 0 5\n"
        "o outer_shell # obiekt glowny\n"
        "g front\n"
        "f 2 3 4 # trojkat w outer_shell + front\n"
        "o inner_liner\n"
        "f 2 4 5 # nadal w grupie front, ale nowy obiekt inner_liner\n",
        encoding="utf-8",
    )
    assert list_obj_groups(p) == ["outer_shell", "front", "inner_liner"]
    front = load_obj(p, group_name="front")
    assert len(front.triangles) == 2
    assert len(front.vertices) == 4
    assert Vec3(100, 200, 300) not in front.vertices
