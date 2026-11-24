"""Version 1 project metadata: mm, Y-up. Mesh references are never opened.

Atomic replacement protects an existing project from failed writes; this is
not a power-loss durability guarantee. Path checks are lexical, not a sandbox.
"""
from dataclasses import dataclass, field, fields
import json
import os
from pathlib import Path
import tempfile
from .contracts import BodyRegion, HeadMeasurements, Transform3D, Vec3

MAX_PROJECT_BYTES = 1024 * 1024


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')


def _mesh_path(value: str) -> None:
    _text(value, 'mesh_path')
    if '\\' in value or ':' in value or '\0' in value or any(s in ('', '..', '.') for s in value.split('/')):
        raise ValueError('mesh_path must be a relative POSIX reference without empty or traversal segments')


def _transform(value: Transform3D) -> None:
    if not isinstance(value, Transform3D):
        raise ValueError('transform must be Transform3D')
    value.__post_init__()
    for vector in (value.position, value.rotation, value.scale):
        vector.__post_init__()


@dataclass
class ProjectPart:
    part_id: str
    name: str
    mesh_path: str
    region: BodyRegion
    transform: Transform3D

    def __post_init__(self) -> None:
        _text(self.part_id, 'part_id')
        _text(self.name, 'part name')
        _mesh_path(self.mesh_path)
        if not isinstance(self.region, BodyRegion):
            raise ValueError('region must be BodyRegion')
        _transform(self.transform)


@dataclass
class ProjectData:
    name: str
    head_measurements: HeadMeasurements | None = None
    parts: list[ProjectPart] = field(default_factory=list)
    schema_version: int = 1
    units: str = 'mm'
    up_axis: str = 'Y'

    def __post_init__(self) -> None:
        _text(self.name, 'project name')
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('Unsupported schema_version: expected integer 1')
        if self.units != 'mm' or self.up_axis != 'Y':
            raise ValueError('Project requires units mm and up_axis Y')
        if self.head_measurements is not None:
            if not isinstance(self.head_measurements, HeadMeasurements):
                raise ValueError('head_measurements must be HeadMeasurements or None')
            self.head_measurements.__post_init__()
        if not isinstance(self.parts, list):
            raise ValueError('parts must be a list')
        ids = set()
        for part in self.parts:
            if not isinstance(part, ProjectPart):
                raise ValueError('parts must contain ProjectPart instances')
            part.__post_init__()
            if part.part_id in ids:
                raise ValueError(f'Duplicate part_id: {part.part_id}')
            ids.add(part.part_id)


def _object(data: object, keys: set[str], name: str) -> dict:
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError(f'{name} requires exactly these fields: {sorted(keys)}')
    return data


def _vector(data: object) -> Vec3:
    return Vec3(**_object(data, {'x', 'y', 'z'}, 'Vec3'))


def _decode(data: object) -> ProjectData:
    root = _object(data, {f.name for f in fields(ProjectData)}, 'project')
    head = root['head_measurements']
    if head is not None:
        head = HeadMeasurements(**_object(head, {f.name for f in fields(HeadMeasurements)}, 'head_measurements'))
    if not isinstance(root['parts'], list):
        raise ValueError('parts must be a list')
    parts = []
    for item in root['parts']:
        part = _object(item, {f.name for f in fields(ProjectPart)}, 'part')
        raw = _object(part['transform'], {'position', 'rotation', 'scale'}, 'transform')
        if not isinstance(part['region'], str):
            raise ValueError('region must be a string')
        transform = Transform3D(**{k: _vector(v) for k, v in raw.items()})
        parts.append(ProjectPart(part['part_id'], part['name'], part['mesh_path'], BodyRegion(part['region']), transform))
    return ProjectData(root['name'], head, parts, root['schema_version'], root['units'], root['up_axis'])


def _encode(project: ProjectData) -> dict:
    if not isinstance(project, ProjectData):
        raise ValueError('Expected ProjectData')
    project.__post_init__()
    parts = []
    for part in project.parts:
        transform = {key: {axis: getattr(getattr(part.transform, key), axis) for axis in ('x', 'y', 'z')} for key in ('position', 'rotation', 'scale')}
        parts.append(dict(part_id=part.part_id, name=part.name, mesh_path=part.mesh_path, region=part.region.value, transform=transform))
    head = None if project.head_measurements is None else {f.name: getattr(project.head_measurements, f.name) for f in fields(HeadMeasurements)}
    return dict(name=project.name, head_measurements=head, parts=parts, schema_version=project.schema_version, units=project.units, up_axis=project.up_axis)


def save_project(project: ProjectData, path: str | Path) -> None:
    payload = json.dumps(_encode(project), ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    if len(payload) > MAX_PROJECT_BYTES:
        raise ValueError('Project exceeds 1 MiB')
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _reject_constant(value: str) -> None:
    raise ValueError(f'Non-finite JSON constant: {value}')


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def load_project(path: str | Path) -> ProjectData:
    path = Path(path)
    if path.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError('Project exceeds 1 MiB')
    with path.open('rb') as stream:
        payload = stream.read(MAX_PROJECT_BYTES + 1)
    if len(payload) > MAX_PROJECT_BYTES:
        raise ValueError('Project exceeds 1 MiB')
    try:
        data = json.loads(payload.decode('utf-8-sig'), parse_constant=_reject_constant, object_pairs_hook=_unique_keys)
    except (UnicodeError, RecursionError) as error:
        raise ValueError('Invalid project JSON') from error
    return _decode(data)
