import math
import struct
import pytest
from core.contracts import Vec3, MeshData, Transform3D
from core.mesh_io import load_stl, save_stl, load_obj, list_obj_groups


@pytest.fixture
def mesh():
    return MeshData('plate', [Vec3(1,2,3),Vec3(3,2,3),Vec3(3,5,3),Vec3(1,5,3)], [(0,1,2),(0,2,3)])


def coords(mesh):
    return [(v.x,v.y,v.z) for v in mesh.vertices]


@pytest.mark.parametrize('binary',[True,False])
def test_stl_roundtrip(tmp_path,mesh,binary):
    p=tmp_path/'plate.stl'
    save_stl(mesh,p,binary=binary)
    result=load_stl(p,part_name='new')
    assert result.name=='new'
    assert coords(result)==coords(mesh)
    assert result.triangles==mesh.triangles
    assert result.bounding_box==mesh.bounding_box
    if binary:
        assert p.stat().st_size==184
        assert struct.unpack_from('<3f',p.read_bytes(),84)==(0,0,1)
    else:
        assert p.stat().st_size>80
        assert p.read_text().startswith('solid ')
        assert 'facet normal 0 0 1' in p.read_text()


def test_solid_binary(tmp_path,mesh):
    p=tmp_path/'solid.stl'
    save_stl(mesh,p)
    with p.open('r+b') as f: f.write(b'solid binary despite name')
    assert coords(load_stl(p))==coords(mesh)


@pytest.mark.parametrize('binary',[True,False])
def test_transform_world_coordinates(tmp_path,mesh,binary):
    p=tmp_path/'world.stl'
    transform=Transform3D(position=Vec3(100,200,-50),rotation=Vec3(90,90,90),scale=Vec3(2,3,4))
    original=coords(mesh)
    save_stl(mesh,p,binary,transform)
    result=load_stl(p)
    # XYZ quarter turns map scaled (x,y,z) to (z,y,-x).
    expected=[(100+4*z,200+3*y,-50-2*x) for x,y,z in original]
    for actual,want in zip(coords(result),expected): assert actual==pytest.approx(want)
    assert coords(mesh)==original
    if binary:
        assert struct.unpack_from('<3f',p.read_bytes(),84)==pytest.approx((1,0,0),abs=1e-6)


def test_tolerance_crosses_cell_boundary(tmp_path):
    p=tmp_path/'dedup.stl'
    source=MeshData('part',[Vec3(.9e-6,0,0),Vec3(1,0,0),Vec3(0,1,0),Vec3(1.1e-6,0,0),Vec3(0,0,1)],[(0,1,2),(3,2,4)])
    save_stl(source,p,False)
    result=load_stl(p)
    assert len(result.vertices)==4
    assert result.triangles==[(0,1,2),(0,2,3)]
    # Tolerance is measured after conversion to mm.
    assert len(load_stl(p,unit_scale=10).vertices)==5


def test_collapsed_triangle_rejected(tmp_path):
    p=tmp_path/'tiny.stl'
    source=MeshData('part',[Vec3(0,0,0),Vec3(1e-8,0,0),Vec3(0,1,0)],[(0,1,2)])
    save_stl(source,p)
    with pytest.raises(ValueError,match='collapsed'): load_stl(p)


@pytest.mark.parametrize('scale',[0,-1,math.nan,math.inf,True])
def test_bad_scale(tmp_path,scale):
    for loader in (load_obj,load_stl):
        with pytest.raises(ValueError): loader(tmp_path/'unused',unit_scale=scale)


def test_stl_scale(tmp_path,mesh):
    p=tmp_path/'cm.stl'
    save_stl(mesh,p)
    assert load_stl(p,unit_scale=10).vertices[0]==Vec3(10,20,30)


OBJ='''# test scene
v 1 2 3
v 3 2 3
v 3 5 3
v 1 5 3
v 0 0 8
o torso
g body visible
f 1/1 2/2 3/3 4/4
o helmet
g shell visible
f -5//1 -3//1 -1//1
g rim
f 1/1/1 2/2/1 5/3/1
o box
g
f 2 3 5
'''


def test_obj_groups_faces_units(tmp_path):
    p=tmp_path/'scene.obj'; p.write_text(OBJ)
    assert list_obj_groups(p)==['torso','body','visible','helmet','shell','rim','box']
    all_mesh=load_obj(p)
    assert len(all_mesh.triangles)==5
    torso=load_obj(p,'body',unit_scale=10)
    assert torso.triangles==[(0,1,2),(0,2,3)]
    assert torso.bounding_box.min_pt==Vec3(10,20,30)
    assert torso.bounding_box.max_pt==Vec3(30,50,30)
    assert len(load_obj(p,'helmet').triangles)==2
    assert len(load_obj(p,'visible').triangles)==3
    assert len(load_obj(p,'shell').vertices)==3
    assert len(load_obj(p,'box').triangles)==1
    with pytest.raises(ValueError): load_obj(p,'missing')


@pytest.mark.parametrize('face',['f 0 1 2','f 1 2 9','f -8 -2 -1','f 1 2','f 1 1 2'])
def test_bad_obj(tmp_path,face):
    p=tmp_path/'bad.obj'; p.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\n'+face)
    with pytest.raises(ValueError): load_obj(p)


def test_ungrouped_obj(tmp_path):
    p=tmp_path/'plain.obj'; p.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    assert list_obj_groups(p)==[]
    assert len(load_obj(p).triangles)==1
    with pytest.raises(ValueError): load_obj(p,'Avatar')


def test_damaged_binary(tmp_path,mesh):
    p=tmp_path/'bad.stl'; save_stl(mesh,p)
    p.write_bytes(p.read_bytes()[:-1])
    with pytest.raises(ValueError): load_stl(p)


def test_nonfinite_input(tmp_path):
    p=tmp_path/'bad.obj'; p.write_text('v nan 0 0\n')
    with pytest.raises(ValueError): load_obj(p)


def test_invalid_export_does_not_truncate(tmp_path,mesh):
    p=tmp_path/'keep.stl'; p.write_bytes(b'original')
    mesh.triangles.append((0,1,90))
    with pytest.raises(ValueError): save_stl(mesh,p)
    assert p.read_bytes()==b'original'
