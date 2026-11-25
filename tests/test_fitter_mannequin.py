from core.clearance import _TriangleBVH, evaluate_clearance
from core.contracts import HeadMeasurements, MeshData, Vec3
from core.transforms import apply_transform
from core.fitter import fit_helmet, fit_helmet_to_mannequin
from core.head_generator import generate_head_mesh
from core.mannequin import generate_mannequin


def _tight_visor_helmet() -> MeshData:
    # Open-bottom fixture: the +Z wall models a flat visor.
    vertices = [
        Vec3(x, y, z)
        for y in (35, 246)
        for x, z in ((-89, -105), (89, -105), (89, 110), (-89, 110))
    ]
    triangles = [(4, 5, 6), (4, 6, 7)]
    for i in range(4):
        j = (i + 1) % 4
        triangles.extend(((i, j, i + 4), (j, j + 4, i + 4)))
    return MeshData("tight visor", vertices, triangles)


def test_tight_visor_clears_mannequin_nose():
    measurements = HeadMeasurements(580, 160, 200, 240)
    mannequin = generate_mannequin(measurements, radial_segments=32, height_rings=24)
    helmet = _tight_visor_helmet()
    seed = fit_helmet(
        generate_head_mesh(measurements), helmet, target_clearance_mm=3.5,
        min_clearance_mm=1.5, max_clearance_mm=25,
    ).transform
    visor = MeshData("visor only", helmet.vertices, helmet.triangles[6:8])
    assert evaluate_clearance(mannequin.mesh, visor, helmet_transform=seed).intersecting_triangles > 0
    result = fit_helmet_to_mannequin(mannequin, helmet, head_measurements=measurements)
    assert result.converged
    assert result.report.min_clearance_mm >= 1.5
    assert result.report.intersecting_triangles == 0
    assert result.transform != seed
    assert result.transform.scale.x == result.transform.scale.y == result.transform.scale.z
    assert evaluate_clearance(
        mannequin.mesh, helmet, helmet_transform=result.transform
    ).intersecting_triangles == 0

    world_helmet = _TriangleBVH(apply_transform(helmet, result.transform))
    head_points = [point for point in mannequin.mesh.vertices if point.y >= 0]
    nose = max(head_points, key=lambda point: point.z)
    occiput = min(head_points, key=lambda point: point.z)
    for point in (nose, occiput):
        assert world_helmet.nearest_point(point)[0] >= 1.5
