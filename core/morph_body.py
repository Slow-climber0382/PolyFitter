"""Indexed morph assets and calibration in millimetres, Y up, face toward +Z."""
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path

from .contracts import MeshData, Vec3
from .head_generator import GeneratedHead
from .mesh_io import _obj_lines
from .sections import slice_mesh

MorphTarget = list[tuple[int, float, float, float]]


def load_indexed_obj(path: str | Path) -> MeshData:
    """Read positions in OBJ declaration order so zero-based target indices survive."""
    vertices = []
    triangles = []
    for line, tokens in _obj_lines(path):
        kind, *values = tokens
        if kind == "v":
            if len(values) != 3:
                raise ValueError(f"Expected XYZ at OBJ line {line}")
            vertices.append(Vec3(*(float(value) for value in values)))
        elif kind == "f":
            indices = []
            for token in values:
                index = int(token.split("/", 1)[0])
                if index == 0 or not -len(vertices) <= index <= len(vertices):
                    raise ValueError(f"Invalid vertex index at OBJ line {line}")
                indices.append(index - 1 if index > 0 else len(vertices) + index)
            if len(indices) < 3:
                raise ValueError(f"Incomplete face at OBJ line {line}")
            triangles.extend((indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1))
    return MeshData(Path(path).stem, vertices, triangles)


def validate_closed_mesh(mesh: MeshData) -> None:
    """Require one connected, consistently outward manifold without loose vertices.

    This is a topology and degeneracy check, with no self-intersection search.
    """
    mesh.__post_init__()
    links: list[dict[int, int]] = [{} for _ in mesh.vertices]
    origin = mesh.vertices[0]
    volume_terms = []
    for i, j, k in mesh.triangles:
        a, b, c = (mesh.vertices[index] - origin for index in (i, j, k))
        u, v = b - a, c - a
        normal = Vec3(u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z, u.x * v.y - u.y * v.x)
        if normal.length == 0:
            raise ValueError("Mesh contains a zero-area face")
        volume_terms.append(a.x * normal.x + a.y * normal.y + a.z * normal.z)
        for center, start, end in ((i, j, k), (j, k, i), (k, i, j)):
            if start in links[center]:
                raise ValueError("Mesh has a non-manifold edge or inconsistent winding")
            links[center][start] = end

    for link in links:
        if not link:
            raise ValueError("Mesh contains unused vertices")
        if link.keys() != set(link.values()):
            raise ValueError("Mesh has a boundary or inconsistent winding")
        first = current = next(iter(link))
        for count in range(1, len(link) + 1):
            current = link.get(current)
            if current is None:
                raise ValueError("Mesh has a boundary or inconsistent winding")
            if current == first:
                if count != len(link):
                    raise ValueError("Mesh has a non-manifold vertex")
                break
        else:
            raise ValueError("Mesh has an inconsistent vertex fan")

    seen = {0}
    pending = [0]
    while pending:
        for neighbor in links[pending.pop()]:
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    if len(seen) != len(links):
        raise ValueError("Mesh must contain one connected body")
    if math.fsum(volume_terms) <= 0:
        raise ValueError("Mesh must have positive outward signed volume")


def _number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not -math.inf < value < math.inf:
        raise ValueError(f"{name} must be finite")
    return value


@dataclass
class MorphBody:
    """Base and sparse additive offsets sharing the same zero-based vertex order."""

    base: MeshData
    targets: dict[str, MorphTarget]

    def __post_init__(self) -> None:
        validate_closed_mesh(self.base)
        if not isinstance(self.targets, dict):
            raise ValueError("Morph targets must be a mapping")
        for name, target in self.targets.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(target, list):
                raise ValueError("Invalid morph name or offsets")
            indices = set()
            for row in target:
                if not isinstance(row, (list, tuple)) or len(row) != 4:
                    raise ValueError(f"Invalid morph row in {name}")
                index, dx, dy, dz = row
                if type(index) is not int or not 0 <= index < len(self.base.vertices) or index in indices:
                    raise ValueError(f"Invalid or duplicate vertex index in {name}")
                indices.add(index)
                for delta in (dx, dy, dz):
                    _number(delta, "morph offset")

    def apply(self, weights: Mapping[str, float]) -> MeshData:
        """Blend from the original base each time, in deterministic target order."""
        for name, weight in weights.items():
            if name not in self.targets:
                raise ValueError(f"Unknown morph: {name}")
            _number(weight, "morph weight")
        points = self.base.vertices.copy()
        for name in sorted(weights):
            weight = weights[name]
            if weight == 0:
                continue
            for index, dx, dy, dz in self.targets[name]:
                p = points[index]
                points[index] = Vec3(p.x + weight * dx, p.y + weight * dy, p.z + weight * dz)
        return MeshData(self.base.name, points, self.base.triangles.copy())


def load_morph_body(path: str | Path) -> MorphBody:
    """Load the index-preserving OBJ and JSON package emitted by the exporter."""
    manifest = Path(path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict) or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1 or data.get("units") != "mm"
        or data.get("up_axis") != "Y" or data.get("front_axis") != "+Z"
    ):
        raise ValueError("Expected version 1, mm, Y-up, +Z-front morph package")
    name = data.get("base_obj")
    if not isinstance(name, str) or not name.endswith(".obj") or Path(name).name != name or "\\" in name:
        raise ValueError("Expected a sibling OBJ filename")
    obj_path = manifest.with_name(name)
    if sha256(obj_path.read_bytes()).hexdigest() != data.get("base_sha256"):
        raise ValueError("Base OBJ checksum mismatch")
    targets = data.get("targets")
    if not isinstance(targets, dict):
        raise ValueError("Missing morph targets mapping")
    for name, rows in targets.items():
        if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
            raise ValueError(f"Expected JSON offset rows for morph {name}")
    return MorphBody(
        load_indexed_obj(obj_path),
        {name: [tuple(row) for row in rows] for name, rows in targets.items()},
    )


def section_circumference(mesh: MeshData, level_mm: float, *, tolerance_mm: float = 1e-8) -> float:
    """Sum polygonal contour lengths at Y=level, including disconnected loops.

    Reject empty or branching/open sections. Length uses original intersection
    endpoints, while the spatial tolerance only matches contour connectivity.
    """
    segments = slice_mesh(mesh, "y", level_mm, tolerance_mm)
    if not segments:
        raise ValueError("Section contains no closed contour")
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    points: list[Vec3] = []
    degrees: list[int] = []

    def endpoint(point: Vec3) -> int:
        cell = math.floor(point.x / tolerance_mm), math.floor(point.z / tolerance_mm)
        for dx, dz in product((-1, 0, 1), repeat=2):
            for index in cells.get((cell[0] + dx, cell[1] + dz), ()):
                other = points[index]
                if math.hypot(point.x - other.x, point.z - other.z) <= tolerance_mm:
                    return index
        index = len(points)
        cells[cell].append(index)
        points.append(point)
        degrees.append(0)
        return index

    for a, b in segments:
        degrees[endpoint(a)] += 1
        degrees[endpoint(b)] += 1
    if any(degree != 2 for degree in degrees):
        raise ValueError("Section is open or branching")
    return math.fsum(math.hypot(a.x - b.x, a.z - b.z) for a, b in segments)


@dataclass(frozen=True)
class CircumferenceConstraint:
    target: str
    level_mm: float
    circumference_mm: float
    min_weight: float = 0.0
    max_weight: float = 1.0
    front_only_from_z_mm: float | None = None


def solve_morph_weights(
    body: MorphBody,
    constraints: Sequence[CircumferenceConstraint],
    initial_weights: Mapping[str, float] | None = None,
    *,
    tolerance_mm: float = 0.01,
    max_passes: int = 12,
) -> dict[str, float]:
    """Coordinate bisection for locally monotonic circumference controls.

    Recheck every constraint together after each pass. Out-of-range controls
    are clamped during a pass so that other controls can move into range.
    Failure to meet every tolerance raises ValueError.
    """
    if not 0 < _number(tolerance_mm, "tolerance_mm") or type(max_passes) is not int or max_passes < 1:
        raise ValueError("Require positive tolerance and max_passes")
    weights = dict(initial_weights or {})
    for weight in weights.values():
        _number(weight, "morph weight")
    names = set()
    for item in constraints:
        if item.target not in body.targets or item.target in names:
            raise ValueError(f"Unknown or repeated calibration target: {item.target}")
        names.add(item.target)
        _number(item.level_mm, "level_mm")
        if _number(item.circumference_mm, "circumference_mm") <= 0:
            raise ValueError("circumference_mm must be positive")
        if _number(item.min_weight, "min_weight") >= _number(item.max_weight, "max_weight"):
            raise ValueError("Expected min_weight < max_weight")
        if item.front_only_from_z_mm is not None:
            cutoff = _number(item.front_only_from_z_mm, "front_only_from_z_mm")
            if any(
                body.base.vertices[index].z <= cutoff and (dx or dy or dz)
                for index, dx, dy, dz in body.targets[item.target]
            ):
                raise ValueError(f"Morph {item.target} moves vertices outside its front region")
        weights[item.target] = min(item.max_weight, max(item.min_weight, weights.get(item.target, 0.0)))

    def measure(mesh: MeshData, item: CircumferenceConstraint) -> float:
        return section_circumference(mesh, item.level_mm) - item.circumference_mm

    mesh = body.apply(weights)
    for _ in range(max_passes):
        if all(abs(measure(mesh, item)) <= tolerance_mm for item in constraints):
            validate_closed_mesh(mesh)
            return weights
        for item in constraints:
            name = item.target
            low, high = item.min_weight, item.max_weight
            weights[name] = low
            left = measure(body.apply(weights), item)
            weights[name] = high
            right = measure(body.apply(weights), item)
            if left * right >= 0:
                weights[name] = low if abs(left) <= abs(right) else high
                continue
            for _ in range(64):
                middle = low + (high - low) / 2
                weights[name] = middle
                error = measure(body.apply(weights), item)
                if abs(error) <= tolerance_mm / 2 or middle in (low, high):
                    break
                if (error < 0) == (left < 0):
                    low, left = middle, error
                else:
                    high = middle
        mesh = body.apply(weights)

    errors = {item.target: measure(mesh, item) for item in constraints}
    if all(abs(error) <= tolerance_mm for error in errors.values()):
        validate_closed_mesh(mesh)
        return weights
    raise ValueError(f"Could not reach circumference targets; residuals in mm: {errors}")


def to_generated_head(mesh: MeshData, brow_y_mm: float, *, chin_y_mm: float = 0.0) -> GeneratedHead:
    """Use the closed mesh for collision and the upper head for contact sampling."""
    validate_closed_mesh(mesh)
    chin = _number(chin_y_mm, "chin_y_mm")
    crown = max(point.y for point in mesh.vertices)
    if not chin < _number(brow_y_mm, "brow_y_mm") < crown:
        raise ValueError("Brow must lie between chin and crown")
    cutoff = chin + 0.45 * (crown - chin)
    cranium = [
        index for index, face in enumerate(mesh.triangles)
        if math.fsum(mesh.vertices[i].y for i in face) / 3 >= cutoff
    ]
    return GeneratedHead(mesh, cranium, section_circumference(mesh, brow_y_mm))
