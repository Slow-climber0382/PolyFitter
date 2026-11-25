"""Pack an exported, closed MPFB2/MakeHuman OBJ and matching sparse targets.

Run with Python from any directory. For example:
    python tools/export_mpfb2_base.py body.obj bundle --unit-scale 100 \
        --up Y --front +Z --target head_width=head-width.target

Use one clean body with outward winding. Export it and the target offsets in
the same coordinate frame, preserving original vertex indices. A raw base
containing helpers or holes needs preparation and corresponding target
remapping before export. The output directory must be new.
"""
import argparse
from collections.abc import Callable
from hashlib import sha256
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contracts import MeshData, Vec3
from core.morph_body import MorphBody, MorphTarget, _number, load_indexed_obj


def _axis(name: str) -> tuple[int, int]:
    return "XYZ".index(name[-1]), -1 if name.startswith("-") else 1


def _mapper(up: str, front: str, scale: float) -> Callable[[tuple[float, float, float]], Vec3]:
    y, sy = _axis(up)
    z, sz = _axis(front)
    if y == z:
        raise ValueError("Up and front must use different axes")
    x = 3 - y - z
    # Right-handed basis: right = up cross front.
    sx = sy * sz * (1 if (y + 1) % 3 == z else -1)

    def orient(values: tuple[float, float, float]) -> Vec3:
        return Vec3(values[x] * sx * scale, values[y] * sy * scale, values[z] * sz * scale)

    return orient


def _read_target(path: Path, orient: Callable[[tuple[float, float, float]], Vec3]) -> MorphTarget:
    offsets = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if len(words) != 4:
            raise ValueError(f"Expected index and three offsets in {path} at line {number}")
        delta = orient(tuple(float(value) for value in words[1:]))
        offsets.append((int(words[0]), delta.x, delta.y, delta.z))
    return offsets


def export_package(
    base_obj: Path, output_dir: Path, targets: dict[str, Path], *,
    unit_scale: float, up: str, front: str, chin_y_mm: float = 0.0,
) -> Path:
    """Convert the base and deltas with one proper rotation and unit scale."""
    if _number(unit_scale, "unit_scale") <= 0:
        raise ValueError("unit_scale must be positive")
    _number(chin_y_mm, "chin_y_mm")
    orient = _mapper(up, front, unit_scale)
    source = load_indexed_obj(base_obj)
    points = []
    for vertex in source.vertices:
        point = orient((vertex.x, vertex.y, vertex.z))
        points.append(Vec3(point.x, point.y - chin_y_mm, point.z))
    body = MorphBody(
        MeshData("body", points, source.triangles),
        {name: _read_target(path, orient) for name, path in targets.items()},
    )

    lines = ["# PolyFitter mm Y-up +Z-front"]
    lines.extend(f"v {p.x:.17g} {p.y:.17g} {p.z:.17g}" for p in body.base.vertices)
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in body.base.triangles)
    obj = ("\n".join(lines) + "\n").encode("ascii")
    data = {
        "schema_version": 1, "units": "mm", "up_axis": "Y", "front_axis": "+Z",
        "base_obj": "base.obj", "base_sha256": sha256(obj).hexdigest(),
        "targets": body.targets,
    }
    manifest = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    output_dir.mkdir()
    (output_dir / "base.obj").write_bytes(obj)
    path = output_dir / "morphs.json"
    path.write_text(manifest, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    axes = ["X", "Y", "Z", "+X", "+Y", "+Z", "-X", "-Y", "-Z"]
    parser.add_argument("base_obj", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--unit-scale", type=float, required=True, help="Millimetres per source unit")
    parser.add_argument("--up", choices=axes, required=True)
    parser.add_argument("--front", choices=axes, required=True)
    parser.add_argument("--chin-y-mm", type=float, default=0.0, help="Chin Y after rotation and conversion, before translation")
    parser.add_argument("--target", action="append", default=[], metavar="NAME=FILE.target")
    args = parser.parse_args()
    targets = {}
    for pair in args.target:
        name, sep, filename = pair.partition("=")
        if not sep or not name.strip() or not filename or name in targets:
            parser.error("Expected a unique NAME=FILE.target")
        targets[name] = Path(filename)
    try:
        print(export_package(
            args.base_obj, args.output_dir, targets, unit_scale=args.unit_scale,
            up=args.up, front=args.front, chin_y_mm=args.chin_y_mm,
        ))
    except (OSError, ValueError) as error:
        parser.exit(2, f"Export failed: {error}\n")


if __name__ == "__main__":
    main()
