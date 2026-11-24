import json
import pytest
from core.contracts import BodyRegion, HeadMeasurements, Transform3D, Vec3
from core.project_io import ProjectPart, ProjectData, save_project, load_project
from core import project_io


@pytest.fixture
def project():
    return ProjectData('Hełm', HeadMeasurements(580,160,210,240), [
        ProjectPart('a','Hełm','meshes/helmet.stl',BodyRegion.HEAD,Transform3D(Vec3(10,20,-30),Vec3(12,-25,90),Vec3(1.1,1.2,1.3))),
        ProjectPart('b','Torso','missing/torso.obj',BodyRegion.TORSO,Transform3D())])


@pytest.fixture
def document(project,tmp_path):
    path=tmp_path/'project.json';save_project(project,path)
    return json.loads(path.read_text())


def read_doc(doc,tmp_path):
    path=tmp_path/'input.json';path.write_text(json.dumps(doc))
    return load_project(path)


def test_roundtrip(project,tmp_path):
    path=tmp_path/'project.json';save_project(project,path)
    assert load_project(path)==project
    data=json.loads(path.read_text())
    assert data['parts'][0]['region']=='head'
    assert data['parts'][0]['transform']['position']=={'x':10,'y':20,'z':-30}
    assert set(data)=={'name','head_measurements','parts','schema_version','units','up_axis'}
    assert not (tmp_path/'missing/torso.obj').exists()


def test_empty_and_independent_defaults(tmp_path):
    a,b=ProjectData('A'),ProjectData('B')
    assert a.parts is not b.parts
    path=tmp_path/'empty.json';save_project(a,path)
    assert load_project(path)==a


@pytest.mark.parametrize('field,value',[
    ('schema_version',True),('schema_version',1.0),('schema_version',2),('schema_version','1'),
    ('units','cm'),('units',None),('up_axis','Z'),('up_axis',False),('name',' '),('name',42),
    ('parts',{}),('parts',[None]),('head_measurements',[]),
])
def test_invalid_root(document,tmp_path,field,value):
    document[field]=value
    with pytest.raises(ValueError):read_doc(document,tmp_path)


@pytest.mark.parametrize('path',['',' ','/absolute.stl','../x','a/../x','a\\x','a//x','a/','C:x','C:/x','./x'])
def test_bad_mesh_path(document,tmp_path,path):
    document['parts'][0]['mesh_path']=path
    with pytest.raises(ValueError):read_doc(document,tmp_path)


@pytest.mark.parametrize('field,value', [('part_id',''),('name',' '),('region','unknown'),('region',2),('transform',None),('mesh_path',12)])
def test_invalid_part(document,tmp_path,field,value):
    document['parts'][0][field]=value
    with pytest.raises(ValueError):read_doc(document,tmp_path)


@pytest.mark.parametrize('value',[0,-1,'580',True,1e99])
def test_invalid_measurements(document,tmp_path,value):
    document['head_measurements']['circumference_mm']=value
    with pytest.raises(ValueError):read_doc(document,tmp_path)


@pytest.mark.parametrize('value',[True,'10',None,float('inf')])
def test_invalid_vector(document,tmp_path,value):
    document['parts'][0]['transform']['position']['x']=value
    with pytest.raises(ValueError):read_doc(document,tmp_path)


def test_bad_scale_and_duplicate_ids(document,tmp_path):
    document['parts'][0]['transform']['scale']['y']=0
    with pytest.raises(ValueError):read_doc(document,tmp_path)
    document['parts'][0]['transform']['scale']['y']=1
    document['parts'][1]['part_id']='a'
    with pytest.raises(ValueError):read_doc(document,tmp_path)


@pytest.mark.parametrize('target',['root','head','part','transform','vector'])
@pytest.mark.parametrize('action',['missing','extra'])
def test_exact_keys(document,tmp_path,target,action):
    obj={'root':document,'head':document['head_measurements'],'part':document['parts'][0],
         'transform':document['parts'][0]['transform'],'vector':document['parts'][0]['transform']['position']}[target]
    if action=='missing':obj.pop(next(iter(obj)))
    else:obj['unknown']=1
    with pytest.raises(ValueError):read_doc(document,tmp_path)


@pytest.mark.parametrize('constant',['NaN','Infinity','-Infinity'])
def test_json_constants(tmp_path,constant):
    path=tmp_path/'bad.json';path.write_text('{"name":'+constant+'}')
    with pytest.raises(ValueError):load_project(path)


def test_oversize_before_parse(tmp_path,monkeypatch):
    path=tmp_path/'big.json';path.write_bytes(b' '*(1024*1024+1))
    def forbidden(*args,**kwargs):raise AssertionError('Parser called')
    monkeypatch.setattr(project_io.json,'loads',forbidden)
    with pytest.raises(ValueError,match='1 MiB'):load_project(path)


def test_revalidate_mutation_before_save(project,tmp_path):
    path=tmp_path/'old.json';path.write_bytes(b'old')
    project.parts.append(project.parts[0])
    with pytest.raises(ValueError):save_project(project,path)
    assert path.read_bytes()==b'old'
    project.parts.pop();project.parts[0].mesh_path='../bad'
    with pytest.raises(ValueError):save_project(project,path)
    assert list(tmp_path.iterdir())==[path]


@pytest.mark.parametrize('failure',['write','replace'])
def test_failed_save_preserves_file(project,tmp_path,monkeypatch,failure):
    path=tmp_path/'old.json';path.write_bytes(b'original')
    factory=project_io.tempfile.NamedTemporaryFile
    class Broken:
        def __init__(self,*args,**kwargs):
            self.stream=factory(*args,**kwargs);self.name=self.stream.name
        def __enter__(self):return self
        def write(self,data):
            self.stream.write(data[:10])
            raise OSError('disk full')
        def __exit__(self,*args):self.stream.close()
    if failure=='write':monkeypatch.setattr(project_io.tempfile,'NamedTemporaryFile',Broken)
    else:
        def fail(*args):raise OSError('replace failed')
        monkeypatch.setattr(project_io.os,'replace',fail)
    with pytest.raises(OSError):save_project(project,path)
    assert path.read_bytes()==b'original'
    assert list(tmp_path.iterdir())==[path]


def test_successful_replace_no_temporary(project,tmp_path):
    path=tmp_path/'old.json';path.write_bytes(b'old')
    save_project(project,path)
    assert load_project(path)==project
    assert list(tmp_path.iterdir())==[path]


def test_duplicate_json_keys(tmp_path):
    path=tmp_path/'bad.json';path.write_text('{"name":"a","name":"b"}')
    with pytest.raises(ValueError,match='Duplicate'):load_project(path)
