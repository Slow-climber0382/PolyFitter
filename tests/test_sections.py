from copy import deepcopy
from itertools import permutations
import pytest
from core.contracts import MeshData, Vec3
from core.sections import slice_mesh


def mesh(points,faces=None):
    return MeshData('test',[Vec3(*p) for p in points],faces if faces is not None else [(0,1,2)])


def values(segments):
    return [tuple((p.x,p.y,p.z) for p in pair) for pair in segments]


@pytest.mark.parametrize('axis,expected',[
    ('x',[((1,0,3),(1,2,0))]),
    ('y',[((0,1,4.5),(1.5,1,0))]),
    ('z',[((0,10/3,1),(5/3,0,1))]),
])
def test_triangle_each_axis(axis,expected):
    result=values(slice_mesh(mesh([(2,0,0),(0,4,0),(0,0,6)]),axis,1))
    assert len(result)==1
    for got,want in zip(result[0],expected[0]): assert got==pytest.approx(want)


def test_outside_tangent_coplanar():
    for points in ([(0,2,0),(1,2,0),(0,3,1)],[(0,0,0),(1,2,0),(0,3,1)],[(0,0,0),(1,0,0),(0,0,1)]):
        assert slice_mesh(mesh(points),'y',0)==[]


def test_vertex_and_opposite_sides():
    result=slice_mesh(mesh([(0,0,0),(2,2,0),(2,-2,0)]),'y',0)
    assert values(result)==[((0,0,0),(2,0,0))]


def test_shared_edge_once():
    m=mesh([(0,0,0),(2,0,0),(0,1,1),(0,-1,-1)],[(0,1,2),(1,0,3)])
    assert values(slice_mesh(m,'y',0))==[((0,0,0),(2,0,0))]


def test_translated_tetrahedron_and_nonmutation():
    m=mesh([(-4,10,-6),(0,10,-6),(-4,14,-6),(-4,10,-2)],[(0,1,2),(0,3,1),(0,2,3),(1,3,2)])
    original=deepcopy(m)
    result=slice_mesh(m,'y',12)
    assert values(result)==[
        ((-4,12,-6),(-4,12,-4)),
        ((-4,12,-6),(-2,12,-6)),
        ((-4,12,-4),(-2,12,-6)),
    ]
    assert m==original
    for faces in permutations(m.triangles):
        variant=MeshData('test',m.vertices,[tuple(reversed(f)) for f in faces])
        assert slice_mesh(variant,'y',12)==result


def test_negative_level():
    m=mesh([(-4,-4,-2),(0,0,-2),(0,-4,2)])
    assert values(slice_mesh(m,'y',-2))==[((-2,-2,-2),(0,-2,0))]


@pytest.mark.parametrize('distance',[0.5e-6,1e-6,-1e-6])
def test_band_inclusive_and_projection(distance):
    m=mesh([(0,distance,0),(2,-distance,0),(0,2,1)])
    result=slice_mesh(m,'y',0)
    assert values(result)==[((0,0,0),(2,0,0))]
    assert all(type(p.y) is float for s in result for p in s)


def test_outside_band_and_coplanar_band():
    assert slice_mesh(mesh([(0,1.01e-6,0),(1,1.01e-6,0),(0,2,1)]),'y',0)==[]
    assert slice_mesh(mesh([(0,1e-6,0),(1,-1e-6,0),(0,0,1)]),'y',0)==[]


@pytest.mark.parametrize('length',[0.5e-6,1e-6])
def test_short_edge_omitted(length):
    assert slice_mesh(mesh([(0,0,0),(length,0,0),(0,1,0)]),'y',0)==[]


def test_edge_longer_than_tolerance():
    assert len(slice_mesh(mesh([(0,0,0),(1.01e-6,0,0),(0,1,0)]),'y',0))==1


def test_dedup_neighbours_and_reversed_order():
    # Distinct vertices/triangles, endpoints on opposite cell boundaries.
    m=mesh([(0.9e-6,0,0),(2,0,0),(0,1,0),(1.1e-6,0,0),(2+0.2e-6,0,0),(0,-1,0)],[(0,1,2),(4,3,5)])
    assert values(slice_mesh(m,'y',0))==[((0.9e-6,0,0),(2,0,0))]
    m.triangles.reverse()
    assert values(slice_mesh(m,'y',0))==[((0.9e-6,0,0),(2,0,0))]


def test_distinct_segments_not_merged():
    m=mesh([(0,0,0),(2,0,0),(0,1,0),(0,0,2e-6),(2,0,2e-6),(0,-1,0)],[(0,1,2),(3,4,5)])
    assert len(slice_mesh(m,'y',0))==2


@pytest.mark.parametrize('axis',['X','Y','Z','',None,1,True,[],{}])
def test_invalid_axis(axis):
    with pytest.raises(ValueError):slice_mesh(mesh([(0,0,0),(1,0,0),(0,1,0)]),axis,0)


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-float('inf'),'0',None,10**400])
def test_invalid_level(value):
    with pytest.raises(ValueError):slice_mesh(mesh([(0,0,0),(1,0,0),(0,1,0)]),'y',value)


@pytest.mark.parametrize('value',[True,False,0,-1,float('nan'),float('inf'),-float('inf'),'1',None])
def test_invalid_tolerance(value):
    with pytest.raises(ValueError):slice_mesh(mesh([(0,0,0),(1,0,0),(0,1,0)]),'y',0,value)


def test_revalidation_before_arguments():
    m=mesh([(0,0,0),(1,0,0),(0,1,0)])
    m.vertices.pop()
    with pytest.raises(ValueError,match='indices'):slice_mesh(m,'BAD',0)


def test_no_faces():
    assert slice_mesh(mesh([(0,0,0)],[]),'y',0)==[]
