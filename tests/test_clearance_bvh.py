from core.clearance import evaluate_clearance
from core.contracts import MeshData, Vec3


def test_helmet_triangle_counted_once_across_head_leaves():
    vertices = [Vec3(-1, 0, -1), Vec3(1, 0, -1), Vec3(0, 0, 1)]
    # Identical faces appear in both head subtrees.
    head = MeshData("head", vertices, [(0, 1, 2)] * 18)
    helmet = MeshData(
        "helmet",
        vertices + [Vec3(point.x + 100, point.y, point.z) for point in vertices],
        [(2, 1, 0)] + [(3, 4, 5)] * 18,
    )
    report = evaluate_clearance(head, helmet, head_is_watertight=False)
    assert report.intersecting_triangles == 1
    assert report.min_clearance_mm == 0.0
