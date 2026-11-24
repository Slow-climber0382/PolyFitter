"""STL/OBJ I/O in mm, Y-up; no implicit axis changes or centring.

STL deduplication uses Euclidean distance <= 1e-6 mm to existing
representatives (not transitive clustering). Collapsed faces are rejected.
OBJ fan triangulation is intended for convex planar polygons; no tessellator
for concave polygons is provided. Imported facet/OBJ normals are ignored.
"""
import math
from pathlib import Path
import struct
from typing import Iterator
from .contracts import Vec3, MeshData, Transform3D

TOLERANCE_MM = 1e-6
_RECORD = struct.Struct('<12fH')


def _scale(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('unit_scale must be finite and positive')


def _ascii_faces(path: Path) -> Iterator[list[Vec3]]:
    state, points = 'solid', []
    with path.open(encoding='ascii') as stream:
        for number, line in enumerate(stream, 1):
            words = line.split()
            if not words:
                continue
            lower = [w.lower() for w in words]
            if state == 'solid' and lower[0] == 'solid':
                state = 'facet'
            elif state == 'facet' and lower[0] == 'endsolid':
                state = 'done'
            elif state == 'facet' and len(words) == 5 and lower[:2] == ['facet', 'normal']:
                Vec3(*(float(x) for x in words[2:]))
                state = 'outer'
            elif state == 'outer' and lower == ['outer', 'loop']:
                state, points = 'vertex', []
            elif state == 'vertex' and len(words) == 4 and lower[0] == 'vertex':
                points.append(Vec3(*(float(x) for x in words[1:])))
                if len(points) == 3:
                    state = 'endloop'
            elif state == 'endloop' and lower == ['endloop']:
                state = 'endfacet'
            elif state == 'endfacet' and lower == ['endfacet']:
                yield points
                state = 'facet'
            else:
                raise ValueError(f'Malformed ASCII STL at line {number}')
    if state != 'done':
        raise ValueError('Incomplete ASCII STL')


def _stl_faces(path: Path) -> Iterator[list[Vec3]]:
    with path.open('rb') as stream:
        header = stream.read(84)
        count = struct.unpack_from('<I', header, 80)[0] if len(header) == 84 else 0
        if len(header) == 84 and path.stat().st_size == 84 + count * 50:
            for _ in range(count):
                row = stream.read(50)
                if len(row) != 50:
                    raise ValueError('Truncated binary STL')
                values = _RECORD.unpack(row)
                yield [Vec3(*values[i:i+3]) for i in (3, 6, 9)]
            if stream.read(1):
                raise ValueError('STL changed while reading')
            return
    try:
        yield from _ascii_faces(path)
    except UnicodeError as error:
        raise ValueError('Invalid STL encoding or binary length') from error


def load_stl(path: str | Path, part_name: str | None = None, unit_scale: float = 1.0) -> MeshData:
    _scale(unit_scale)
    path = Path(path)
    vertices: list[Vec3] = []
    triangles: list[tuple[int, int, int]] = []
    cells: dict[tuple[int, int, int], list[int]] = {}
    for face in _stl_faces(path):
        indices = []
        for raw in face:
            point = Vec3(raw.x * unit_scale, raw.y * unit_scale, raw.z * unit_scale)
            scaled = [v / TOLERANCE_MM for v in (point.x, point.y, point.z)]
            if not all(math.isfinite(v) for v in scaled):
                raise ValueError('Coordinate too large for deduplication')
            key = tuple(math.floor(v) for v in scaled)
            found = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for index in cells.get((key[0]+dx, key[1]+dy, key[2]+dz), ()):
                            candidate = vertices[index]
                            if math.dist((point.x, point.y, point.z), (candidate.x, candidate.y, candidate.z)) <= TOLERANCE_MM:
                                found = index if found is None else min(found, index)
            if found is None:
                found = len(vertices)
                vertices.append(point)
                cells.setdefault(key, []).append(found)
            indices.append(found)
        if len(set(indices)) != 3:
            raise ValueError('STL triangle collapsed within deduplication tolerance')
        triangles.append(tuple(indices))
    if not triangles:
        raise ValueError('STL contains no triangles')
    return MeshData(part_name if part_name is not None else path.stem, vertices, triangles)


def _transformed(mesh: MeshData, transform: Transform3D | None) -> list[Vec3]:
    if transform is None:
        return mesh.vertices
    t = transform
    rx, ry, rz = (math.radians(v) for v in (t.rotation.x, t.rotation.y, t.rotation.z))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    result = []
    for p in mesh.vertices:
        x, y, z = p.x*t.scale.x, p.y*t.scale.y, p.z*t.scale.z
        y, z = cx*y-sx*z, sx*y+cx*z
        x, z = cy*x+sy*z, -sy*x+cy*z
        x, y = cz*x-sz*y, sz*x+cz*y
        result.append(Vec3(x+t.position.x, y+t.position.y, z+t.position.z))
    return result


def _normal(a: Vec3, b: Vec3, c: Vec3) -> tuple[float, float, float]:
    u, v = b-a, c-a
    us, vs = max(abs(u.x), abs(u.y), abs(u.z)), max(abs(v.x), abs(v.y), abs(v.z))
    if not us or not vs:
        return (0., 0., 0.)
    ux, uy, uz = u.x/us, u.y/us, u.z/us
    vx, vy, vz = v.x/vs, v.y/vs, v.z/vs
    n = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    length = math.hypot(*n)
    return tuple(x/length for x in n) if length else (0., 0., 0.)


def save_stl(mesh: MeshData, path: str | Path, binary: bool = True, transform: Transform3D | None = None) -> None:
    """Export world coordinates, scale then Rx/Ry/Rz then translation.

    Existing output is replaced. Binary STL uses float32, so coordinates are
    rounded to that representation. Degenerate faces receive a zero normal.
    """
    mesh.__post_init__()  # MeshData lists are mutable: revalidate before export.
    if not mesh.triangles:
        raise ValueError('Cannot export a mesh without triangles')
    vertices = _transformed(mesh, transform)
    if binary and (len(mesh.triangles) > 0xffffffff or any(abs(v) > 3.4028234663852886e38 for p in vertices for v in (p.x,p.y,p.z))):
        raise ValueError('Mesh exceeds binary STL representation')
    path = Path(path)
    with path.open('wb' if binary else 'w') as stream:
        if binary:
            stream.write(b'PolyFitter mm Y-up'.ljust(80, b'\0'))
            stream.write(struct.pack('<I', len(mesh.triangles)))
        else:
            stream.write('solid PolyFitter\n')
        for face in mesh.triangles:
            points = [vertices[i] for i in face]
            normal = _normal(*points)
            if binary:
                stream.write(_RECORD.pack(*normal, *(v for p in points for v in (p.x,p.y,p.z)), 0))
            else:
                stream.write('  facet normal ' + ' '.join(format(x,'.17g') for x in normal) + '\n    outer loop\n')
                for p in points:
                    stream.write(f'      vertex {p.x:.17g} {p.y:.17g} {p.z:.17g}\n')
                stream.write('    endloop\n  endfacet\n')
        if not binary:
            stream.write('endsolid PolyFitter\n')


def _obj_lines(path: str | Path) -> Iterator[tuple[int, list[str]]]:
    with Path(path).open(encoding='utf-8-sig') as stream:
        for number, line in enumerate(stream, 1):
            words = line.split('#',1)[0].split()
            if words:
                yield number, words


def list_obj_groups(path: str | Path) -> list[str]:
    """Unique declared object/group names in file order; no synthetic groups."""
    names = []
    for _, words in _obj_lines(path):
        current = [' '.join(words[1:])] if words[0] == 'o' and len(words)>1 else words[1:] if words[0]=='g' else []
        for name in current:
            if name not in names:
                names.append(name)
    return names


def load_obj(path: str | Path, group_name: str | None = None, unit_scale: float = 1.0) -> MeshData:
    """Objects and groups are independent states; a face can belong to both.

    Negative indices refer to vertices defined so far. UV and normal indices
    are ignored. Only referenced vertices are returned for the selected faces.
    Ungrouped files cannot be separated automatically by semantic part names.
    """
    _scale(unit_scale)
    vertices: list[Vec3] = []
    triangles: list[tuple[int,int,int]] = []
    obj, groups = '', []
    for line, words in _obj_lines(path):
        tag = words[0]
        if tag == 'v':
            if len(words) != 4:
                raise ValueError(f'Expected XYZ vertex at OBJ line {line}')
            vertices.append(Vec3(*(float(v)*unit_scale for v in words[1:])))
        elif tag == 'o':
            obj = ' '.join(words[1:])
        elif tag == 'g':
            groups = words[1:]
        elif tag == 'f':
            if len(words) < 4:
                raise ValueError(f'Face has fewer than 3 vertices at line {line}')
            indices = []
            for token in words[1:]:
                parts = token.split('/')
                if len(parts)>3:
                    raise ValueError(f'Invalid face token at line {line}')
                index = int(parts[0])
                index = index-1 if index>0 else len(vertices)+index if index<0 else -1
                if not 0 <= index < len(vertices):
                    raise ValueError(f'Invalid vertex index at line {line}')
                indices.append(index)
            if group_name is None or group_name == obj or group_name in groups:
                triangles.extend((indices[0], indices[i], indices[i+1]) for i in range(1,len(indices)-1))
    if not triangles:
        raise ValueError('No faces found for the requested OBJ selection')
    remap: dict[int,int] = {}
    selected = []
    faces = []
    for face in triangles:
        mapped = []
        for index in face:
            if index not in remap:
                remap[index] = len(selected)
                selected.append(vertices[index])
            mapped.append(remap[index])
        faces.append(tuple(mapped))
    return MeshData(group_name if group_name is not None else Path(path).stem, selected, faces)
