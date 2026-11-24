import pytest
from core.clearance import (
    closest_point_on_triangle,
    evaluate_clearance,
    evaluate_helmet_clearance,
    triangles_intersect,
)
from core.contracts import HeadMeasurements, MeshData, Transform3D, Vec3
from core.head_generator import GeneratedHead, generate_head_mesh


def _offset_open_helmet_shell(head: GeneratedHead, inner_offset_mm: float, wall_thickness_mm: float = 4.0) -> MeshData:
    """Build a thick-walled open-bottom helmet shell around the head's cranium."""
    verts = head.mesh.vertices
    tris = head.mesh.triangles
    # Compute smooth outward vertex normals
    accum = [[0.0, 0.0, 0.0] for _ in verts]
    for i0, i1, i2 in tris:
        a, b, c = verts[i0], verts[i1], verts[i2]
        ab = b - a
        ac = c - a
        nx = ab.y * ac.z - ab.z * ac.y
        ny = ab.z * ac.x - ab.x * ac.z
        nz = ab.x * ac.y - ab.y * ac.x
        for vi in (i0, i1, i2):
            accum[vi][0] += nx
            accum[vi][1] += ny
            accum[vi][2] += nz

    normals: list[Vec3] = []
    for nx, ny, nz in accum:
        n = Vec3(nx, ny, nz)
        l = n.length
        normals.append(Vec3(nx / l, ny / l, nz / l) if l > 0.0 else Vec3(0.0, 1.0, 0.0))

    # Build inner and outer shell covering upper head (y >= 0.45 * height), open at bottom
    cutoff_y = 0.45 * head.mesh.bounding_box.size.y
    selected_tris = [
        (i0, i1, i2)
        for i0, i1, i2 in tris
        if (verts[i0].y + verts[i1].y + verts[i2].y) / 3.0 >= cutoff_y
    ]

    shell_vertices: list[Vec3] = []
    inner_map: dict[int, int] = {}
    outer_map: dict[int, int] = {}
    for i0, i1, i2 in selected_tris:
        for vi in (i0, i1, i2):
            if vi not in inner_map:
                v = verts[vi]
                n = normals[vi]
                inner_map[vi] = len(shell_vertices)
                shell_vertices.append(
                    Vec3(
                        v.x + n.x * inner_offset_mm,
                        v.y + n.y * inner_offset_mm,
                        v.z + n.z * inner_offset_mm,
                    )
                )
                outer_map[vi] = len(shell_vertices)
                shell_vertices.append(
                    Vec3(
                        v.x + n.x * (inner_offset_mm + wall_thickness_mm),
                        v.y + n.y * (inner_offset_mm + wall_thickness_mm),
                        v.z + n.z * (inner_offset_mm + wall_thickness_mm),
                    )
                )

    shell_triangles: list[tuple[int, int, int]] = []
    for i0, i1, i2 in selected_tris:
        # Inner wall (facing inward toward head)
        shell_triangles.append((inner_map[i0], inner_map[i2], inner_map[i1]))
        # Outer wall (facing outward)
        shell_triangles.append((outer_map[i0], outer_map[i1], outer_map[i2]))

    return MeshData(name="open_helmet_shell", vertices=shell_vertices, triangles=shell_triangles)


def test_analytical_point_to_triangle_distance():
    a = Vec3(0.0, 0.0, 0.0)
    b = Vec3(10.0, 0.0, 0.0)
    c = Vec3(0.0, 10.0, 0.0)

    # Interior projection
    d_sq, pt = closest_point_on_triangle(Vec3(2.0, 2.0, 5.0), a, b, c)
    assert d_sq == pytest.approx(25.0, abs=1e-12)
    assert pt == Vec3(2.0, 2.0, 0.0)

    # Vertex region
    d_sq_v, pt_v = closest_point_on_triangle(Vec3(-3.0, -4.0, 0.0), a, b, c)
    assert d_sq_v == pytest.approx(25.0, abs=1e-12)
    assert pt_v == a

    # Hypotenuse edge region
    d_sq_e, pt_e = closest_point_on_triangle(Vec3(6.0, 6.0, 0.0), a, b, c)
    assert d_sq_e == pytest.approx(2.0, abs=1e-12)
    assert (pt_e.x, pt_e.y, pt_e.z) == pytest.approx((5.0, 5.0, 0.0), abs=1e-12)


def test_triangles_intersect_cases():
    t1 = (Vec3(0.0, 0.0, 0.0), Vec3(10.0, 0.0, 0.0), Vec3(0.0, 10.0, 0.0))
    # Piercing triangle
    t_cross = (Vec3(2.0, 2.0, -5.0), Vec3(2.0, 2.0, 5.0), Vec3(8.0, 2.0, 0.0))
    assert triangles_intersect(t1, t_cross) is True

    # Separated parallel triangle
    t_far = (Vec3(0.0, 0.0, 3.0), Vec3(10.0, 0.0, 3.0), Vec3(0.0, 10.0, 3.0))
    assert triangles_intersect(t1, t_far) is False


def test_valid_helmet_clearance_in_2_to_4mm_range():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=28, height_rings=20)
    helmet = _offset_open_helmet_shell(head, inner_offset_mm=3.0, wall_thickness_mm=4.0)

    report = evaluate_helmet_clearance(head, helmet)
    assert report.intersecting_triangles == 0
    assert 2.0 <= report.min_clearance_mm <= 4.0
    assert 2.0 <= report.max_clearance_mm <= 4.0
    assert report.mean_clearance_mm == pytest.approx(3.0, abs=0.25)
    assert report.is_valid is True


def test_too_tight_and_too_loose_helmets_are_rejected():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=24, height_rings=16)

    tight_helmet = _offset_open_helmet_shell(head, inner_offset_mm=1.0)
    tight_report = evaluate_helmet_clearance(head, tight_helmet)
    assert tight_report.intersecting_triangles == 0
    assert tight_report.min_clearance_mm < 2.0
    assert tight_report.is_valid is False

    # Bucket-fit helmet (12 mm gap) must be rejected by the 4 mm upper bound
    loose_helmet = _offset_open_helmet_shell(head, inner_offset_mm=12.0)
    loose_report = evaluate_helmet_clearance(head, loose_helmet)
    assert loose_report.intersecting_triangles == 0
    assert loose_report.max_clearance_mm > 4.0
    assert loose_report.is_valid is False


def test_penetrating_and_inside_head_helmets_report_negative_clearance():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=24, height_rings=16)

    # Helmet intersecting the head wall (-2 mm inner offset, +3 mm outer wall)
    colliding_helmet = _offset_open_helmet_shell(head, inner_offset_mm=-2.0, wall_thickness_mm=5.0)
    colliding_report = evaluate_helmet_clearance(head, colliding_helmet)
    assert colliding_report.intersecting_triangles > 0
    assert colliding_report.min_clearance_mm < 0.0
    assert colliding_report.is_valid is False

    # Helmet shrunk by 50% completely inside the watertight head mesh without touching surface
    shrunk_report = evaluate_helmet_clearance(
        head,
        head.mesh,
        helmet_transform=Transform3D(position=Vec3(0.0, 60.0, 0.0), scale=Vec3(0.5, 0.5, 0.5)),
    )
    assert shrunk_report.intersecting_triangles == 0
    assert shrunk_report.min_clearance_mm < 0.0
    assert shrunk_report.is_valid is False


def test_transform_parameter_moves_helmet_into_valid_fit():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=24, height_rings=16)
    shifted_helmet = _offset_open_helmet_shell(head, inner_offset_mm=3.0)

    # Shift helmet +20 mm in Y -> causes neck/jaw collision or excessive crown gap
    bad_report = evaluate_helmet_clearance(
        head,
        shifted_helmet,
        helmet_transform=Transform3D(position=Vec3(0.0, 20.0, 0.0)),
    )
    assert bad_report.is_valid is False

    # Identity transform restores exact 3 mm clearance
    good_report = evaluate_helmet_clearance(head, shifted_helmet, helmet_transform=Transform3D())
    assert good_report.is_valid is True


def test_clearance_validation_errors():
    m = HeadMeasurements(circumference_mm=580.0, width_mm=160.0, depth_mm=200.0, height_mm=240.0)
    head = generate_head_mesh(m, radial_segments=16, height_rings=12)

    with pytest.raises(ValueError):
        evaluate_clearance(head.mesh, head.mesh, zone_triangle_indices=[])
    with pytest.raises(ValueError):
        evaluate_clearance(head.mesh, head.mesh, zone_triangle_indices=[999999])
