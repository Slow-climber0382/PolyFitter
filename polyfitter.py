#!/usr/bin/env python3
"""PolyFitter CLI: parametric head generation, 3D clearance check, and helmet fitting."""
import argparse
import json
from pathlib import Path
import sys

from core.clearance import evaluate_helmet_clearance
from core.contracts import (
    BodyRegion,
    HeadMeasurements,
    MeshData,
    Transform3D,
    Vec3,
)
from core.fitter import fit_helmet
from core.head_generator import generate_head_mesh
from core.mesh_io import load_mesh, save_obj, save_stl
from core.project_io import ProjectData, ProjectPart, save_project
from core.transforms import apply_transform


def _parse_vec3(raw: str, label: str) -> Vec3:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise ValueError(f"{label} must have 3 comma-separated numbers (x,y,z), got {raw!r}")
    try:
        x, y, z = (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise ValueError(f"{label} must contain valid numbers, got {raw!r}") from exc
    return Vec3(x, y, z)


def _merge_meshes(meshes: list[MeshData], name: str) -> MeshData:
    if len(meshes) == 1:
        return meshes[0]
    vertices: list[Vec3] = []
    triangles: list[tuple[int, int, int]] = []
    for m in meshes:
        offset = len(vertices)
        vertices.extend(m.vertices)
        triangles.extend((i0 + offset, i1 + offset, i2 + offset) for i0, i1, i2 in m.triangles)
    return MeshData(name=name, vertices=vertices, triangles=triangles)


def _save_mesh_by_ext(mesh: MeshData, path: Path) -> None:
    ext = path.suffix.lower()
    if ext == ".stl":
        save_stl(mesh, path, binary=True)
    elif ext == ".obj":
        save_obj([mesh], path)
    else:
        raise ValueError(f"Unsupported output mesh extension {ext!r}; use .stl or .obj")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polyfitter",
        description="Fit a 3D helmet mesh (STL/OBJ) to parametric head measurements in mm (Y-up).",
    )
    parser.add_argument("helmet", type=Path, help="Input helmet .stl or .obj file")
    parser.add_argument("--circumference", type=float, required=True, help="Head circumference at brow in mm")
    parser.add_argument("--width", type=float, required=True, help="Head width (ear-to-ear) in mm")
    parser.add_argument("--depth", type=float, required=True, help="Head depth (brow-to-occiput) in mm")
    parser.add_argument("--height", type=float, required=True, help="Head height (chin-to-crown) in mm")

    parser.add_argument(
        "--rotation",
        type=str,
        default="0,0,0",
        help="Initial XYZ Euler rotation in degrees before fitting (default: 0,0,0)",
    )
    parser.add_argument(
        "--no-fit",
        action="store_true",
        help="Evaluate clearance as-is without running automatic scale/position solver",
    )
    parser.add_argument("--scale", type=float, default=None, help="Manual uniform scale (used with --no-fit)")
    parser.add_argument("--position", type=str, default="0,0,0", help="Manual XYZ position in mm (used with --no-fit)")

    parser.add_argument("--target-clearance", type=float, default=3.0, help="Target cranial gap in mm (default: 3.0)")
    parser.add_argument("--min-clearance", type=float, default=2.0, help="Minimum allowed gap in mm (default: 2.0)")
    parser.add_argument("--max-clearance", type=float, default=4.0, help="Maximum allowed gap in mm (default: 4.0)")

    parser.add_argument("--radial-segments", type=int, default=48, help="Head horizontal segments (default: 48)")
    parser.add_argument("--height-rings", type=int, default=32, help="Head vertical rings (default: 32)")

    parser.add_argument("--out-mesh", type=Path, default=None, help="Export fitted helmet (.stl or .obj)")
    parser.add_argument("--out-head", type=Path, default=None, help="Export generated head (.stl or .obj)")
    parser.add_argument("--out-project", type=Path, default=None, help="Export PolyFitter scene project (.json)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        measurements = HeadMeasurements(
            circumference_mm=args.circumference,
            width_mm=args.width,
            depth_mm=args.depth,
            height_mm=args.height,
        )
        rotation = _parse_vec3(args.rotation, "--rotation")
        loaded_parts = load_mesh(args.helmet)
        helmet_mesh = _merge_meshes(loaded_parts, name=args.helmet.stem)
        head = generate_head_mesh(
            measurements,
            radial_segments=args.radial_segments,
            height_rings=args.height_rings,
        )

        if args.no_fit:
            pos = _parse_vec3(args.position, "--position")
            s = 1.0 if args.scale is None else args.scale
            transform = Transform3D(position=pos, rotation=rotation, scale=Vec3(s, s, s))
            report = evaluate_helmet_clearance(head, helmet_mesh, helmet_transform=transform)
            converged = report.is_valid
        else:
            if args.scale is not None:
                raise ValueError("--scale requires --no-fit")
            fit_res = fit_helmet(
                head,
                helmet_mesh,
                initial_rotation=rotation,
                target_clearance_mm=args.target_clearance,
                min_clearance_mm=args.min_clearance,
                max_clearance_mm=args.max_clearance,
            )
            transform = fit_res.transform
            report = fit_res.report
            converged = fit_res.converged

        fitted_helmet = apply_transform(helmet_mesh, transform)

        if args.out_mesh is not None:
            _save_mesh_by_ext(fitted_helmet, args.out_mesh)
        if args.out_head is not None:
            _save_mesh_by_ext(head.mesh, args.out_head)
        if args.out_project is not None:
            project = ProjectData(
                name=args.out_project.stem,
                head_measurements=measurements,
                parts=[
                    ProjectPart(
                        part_id="helmet_primary",
                        name=helmet_mesh.name,
                        mesh_path=str(args.helmet),
                        region=BodyRegion.HEAD,
                        transform=transform,
                    )
                ],
            )
            save_project(project, args.out_project)

        summary = {
            "status": "PASS" if report.is_valid else "FAIL",
            "converged": converged,
            "helmet_file": str(args.helmet),
            "helmet_triangles": len(helmet_mesh.triangles),
            "head_circumference_actual_mm": round(head.actual_circumference_mm, 4),
            "transform": {
                "position_mm": [round(transform.position.x, 4), round(transform.position.y, 4), round(transform.position.z, 4)],
                "rotation_deg": [round(transform.rotation.x, 4), round(transform.rotation.y, 4), round(transform.rotation.z, 4)],
                "scale": round(transform.scale.x, 6),
            },
            "clearance_mm": {
                "min": round(report.min_clearance_mm, 4),
                "mean": round(report.mean_clearance_mm, 4),
                "max": round(report.max_clearance_mm, 4),
                "intersecting_triangles": report.intersecting_triangles,
            },
        }

        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"PolyFitter Status : {summary['status']}")
            print(f"Helmet            : {args.helmet} ({len(helmet_mesh.triangles)} triangles)")
            print(
                f"Head (mm)         : circ={head.actual_circumference_mm:.2f}, "
                f"W={measurements.width_mm:.1f}, D={measurements.depth_mm:.1f}, H={measurements.height_mm:.1f}"
            )
            print(
                f"Transform         : scale={transform.scale.x:.5f}, "
                f"pos=({transform.position.x:.2f}, {transform.position.y:.2f}, {transform.position.z:.2f}) mm, "
                f"rot=({transform.rotation.x:.1f}, {transform.rotation.y:.1f}, {transform.rotation.z:.1f}) deg"
            )
            print(
                f"Clearance (mm)    : min={report.min_clearance_mm:.2f}, "
                f"mean={report.mean_clearance_mm:.2f}, max={report.max_clearance_mm:.2f}, "
                f"collisions={report.intersecting_triangles}"
            )
            if args.out_mesh is not None:
                print(f"Saved fitted mesh : {args.out_mesh}")
            if args.out_head is not None:
                print(f"Saved head mesh   : {args.out_head}")
            if args.out_project is not None:
                print(f"Saved project     : {args.out_project}")

        return 0 if report.is_valid else 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
