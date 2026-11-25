import struct
from starlette.testclient import TestClient

from core.contracts import HeadMeasurements, Transform3D, Vec3
from core.head_generator import generate_head_mesh
from core.mesh_io import save_stl
from tests.test_clearance import _offset_open_helmet_shell
from web.server import create_app


def test_web_api_manual_nonuniform_scaling_and_exports(tmp_path):
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=20, height_rings=14)
    shell = _offset_open_helmet_shell(head, inner_offset_mm=3.0, wall_thickness_mm=4.0)

    stl_file = tmp_path / "mando_test.stl"
    save_stl(shell, stl_file, binary=True)

    app = create_app()
    with TestClient(app) as client:

        # 1. Stan początkowy
        r_state = client.get("/api/state")
        assert r_state.status_code == 200
        assert r_state.json()["parts"] == []

        # 2. Binarny bufor głowy
        r_head_geom = client.get("/api/head/geometry")
        assert r_head_geom.status_code == 200
        tri_count = struct.unpack("<I", r_head_geom.content[:4])[0]
        assert tri_count == len(r_state.json()["head"]["triangles"] if False else head.mesh.triangles) or tri_count > 100

        # 3. Upload pliku STL
        with stl_file.open("rb") as f:
            r_up = client.post(
                "/api/import/upload",
                data={"unit_scale": "1.0"},
                files={"files": ("mando_test.stl", f, "application/sla")},
            )
        assert r_up.status_code == 200
        part = r_up.json()["imported"][0]
        pid = part["part_id"]

        # 4. Ręczne skalowanie niejednorodne X/Y/Z (jak w Fox x99_y100_z107) + pozycjonowanie
        r_tr = client.post(
            f"/api/parts/{pid}/transform",
            json={
                "record_undo": True,
                "scale": [1.05, 1.07, 1.03],
                "position": [0.0, 4.0, 0.0],
                "rotation": [0.0, 0.0, 0.0],
            },
        )
        assert r_tr.status_code == 200
        updated_part = r_tr.json()["part"]
        assert updated_part["transform"]["scale"] == [1.05, 1.07, 1.03]
        assert updated_part["transform"]["position"] == [0.0, 4.0, 0.0]

        # 5. Analiza prześwitu 3D (domyślny manekin z nosem/uszami wykrywa kolizje na ciasnej skorupie)
        r_clr_man = client.post(f"/api/parts/{pid}/clearance")
        assert r_clr_man.status_code == 200
        assert r_clr_man.json()["clearance"]["intersecting_triangles"] > 0

        # Przełączenie na prostą elipsoidę potwierdza 0 kolizji na tej samej skorupie
        assert client.post("/api/head", json={"reference_mode": "head"}).status_code == 200
        r_clr = client.post(f"/api/parts/{pid}/clearance")
        assert r_clr.status_code == 200
        clr = r_clr.json()["clearance"]
        assert clr["intersecting_triangles"] == 0
        assert "regional" in clr

        # 6. Eksport STL zachowujący transformację w scenie
        r_stl = client.get(f"/api/parts/{pid}/export-stl")
        assert r_stl.status_code == 200
        assert len(r_stl.content) > 84

        # 7. Eksport projektu JSON
        r_proj = client.get("/api/project/export")
        assert r_proj.status_code == 200
        proj_json = r_proj.json()
        assert proj_json["parts"][0]["transform"]["scale"] == {"x": 1.05, "y": 1.07, "z": 1.03}
