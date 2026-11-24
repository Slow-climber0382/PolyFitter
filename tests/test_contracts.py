"""Contract tests use only synthetic geometry, not proprietary model assets."""
from dataclasses import replace
import pytest
from core.contracts import (
    Vec3, BoundingBox3D, BodyRegion, HeadMeasurements,
    Transform3D, MeshData, FitClearanceReport,
)


def test_vec_operations():
    a, b = Vec3(1, 2, 3), Vec3(4, 5, 6)
    assert a + b == Vec3(5, 7, 9)
    assert b - a == Vec3(3, 3, 3)
    assert Vec3(2, 3, 6).length == 7
    assert Vec3(0, 0, 0).length == 0
    assert Vec3(1e200, 0, 0).length == 1e200


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), True, '2'])
def test_invalid_vector(bad):
    with pytest.raises(ValueError): Vec3(bad, 0, 0)


def test_bounds_and_flat_box():
    box = BoundingBox3D(Vec3(-2, 1, 4), Vec3(6, 7, 4))
    assert box.size == Vec3(8, 6, 0)
    assert box.center == Vec3(2, 4, 4)


@pytest.mark.parametrize('axis', range(3))
def test_inverted_bounds(axis):
    low = [0, 0, 0]
    low[axis] = 2
    with pytest.raises(ValueError): BoundingBox3D(Vec3(*low), Vec3(1, 1, 1))


def test_regions_and_transform():
    assert len(BodyRegion) == 6
    assert BodyRegion.HEAD.value == 'head'
    assert Transform3D().scale == Vec3(1, 1, 1)
    assert Transform3D().position == Vec3(0, 0, 0)
    assert Transform3D(rotation=Vec3(90, -45, 180)).rotation.y == -45
    with pytest.raises(ValueError): Transform3D(scale=Vec3(1, 0, 1))
    with pytest.raises(ValueError): Transform3D(scale=Vec3(-1, 1, 1))


def test_head_valid_and_boundaries():
    head = HeadMeasurements(580, 160, 200, 240)
    for name, low, high in HeadMeasurements.RANGES_MM:
        assert getattr(replace(head, **{name: low}), name) == low
        assert getattr(replace(head, **{name: high}), name) == high


@pytest.mark.parametrize('name,low,high', HeadMeasurements.RANGES_MM)
@pytest.mark.parametrize('bad', [-1, 0, float('nan'), float('inf')])
def test_head_invalid_values(name, low, high, bad):
    with pytest.raises(ValueError): replace(HeadMeasurements(580,160,200,240), **{name:bad})


@pytest.mark.parametrize('name,low,high', HeadMeasurements.RANGES_MM)
def test_head_unrealistic_ranges(name, low, high):
    for bad in (low - 1, high + 1):
        with pytest.raises(ValueError): replace(HeadMeasurements(580,160,200,240), **{name:bad})


def test_mesh_bounds_and_mutation():
    mesh = MeshData('helmet', [Vec3(-2,1,0), Vec3(5,3,0), Vec3(0,9,4)], [(0,1,2)])
    assert mesh.bounding_box == BoundingBox3D(Vec3(-2,1,0), Vec3(5,9,4))
    mesh.vertices.append(Vec3(10,0,-3))
    assert mesh.bounding_box.max_pt.x == 10
    assert mesh.bounding_box.min_pt.z == -3


@pytest.mark.parametrize('triangles', [[(0,1,3)], [(-1,1,2)], [(0,1)], [(0,0,2)], [(True,1,2)]])
def test_bad_triangles(triangles):
    with pytest.raises(ValueError): MeshData('part', [Vec3(0,0,0)] * 3, triangles)


def test_empty_mesh_and_normals():
    with pytest.raises(ValueError): MeshData('empty', [], [])
    v = [Vec3(0,0,0), Vec3(1,0,0), Vec3(0,1,0)]
    assert MeshData('part',v,[(0,1,2)],[Vec3(0,0,1)]*3).normals is not None
    with pytest.raises(ValueError): MeshData('part',v,[(0,1,2)],[Vec3(0,0,1)])
    with pytest.raises(ValueError): MeshData('part',v,[(0,1,2)],[Vec3(0,0,0)]*3)


@pytest.mark.parametrize('low,high,mean,count,valid', [
    (2,4,3,0,True), (2,2,2,0,True), (4,4,4,0,True),
    (1.99,4,3,0,False), (2,4.01,3,0,False), (2,4,3,1,False),
    (-1,4,2,3,False), (0,0,0,0,False),
])
def test_clearance_validity(low, high, mean, count, valid):
    assert FitClearanceReport(low,high,mean,count).is_valid is valid


@pytest.mark.parametrize('values', [(4,2,3,0),(2,4,5,0),(2,4,3,-1),(2,4,3,1.5),(2,4,3,True),(float('nan'),4,3,0)])
def test_bad_report(values):
    with pytest.raises(ValueError): FitClearanceReport(*values)
