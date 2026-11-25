"""Starlette backend bridging PolyFitter's pure-Python core/ engine with the 3D Web GUI."""
from __future__ import annotations

import array
from dataclasses import asdict, dataclass, field, is_dataclass
import inspect
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import uuid

import anyio
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from core.clearance import evaluate_helmet_clearance
from core import clearance as clearance_mod
from core.contracts import (
    BodyRegion,
    HeadMeasurements,
    MeshData,
    Transform3D,
    Vec3,
)
from core.fitter import fit_helmet, fit_helmet_to_mannequin
from core.head_generator import generate_head_mesh
from core import mannequin as mannequin_mod
from core.mesh_io import load_obj, load_stl, save_stl
from core.project_io import ProjectData, ProjectPart, load_project, save_project

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _mesh_to_binary_buffers(mesh: MeshData) -> bytes:
    """Pack expanded triangle vertices and flat normals into compact float32 binary payload.

    Layout:
      uint32 triangle_count
      float32[triangle_count * 9] positions (x,y,z per corner)
      float32[triangle_count * 9] normals   (nx,ny,nz per corner)
    """
    tri_count = len(mesh.triangles)
    header = array.array("I", [tri_count])
    positions = array.array("f")
    normals = array.array("f")
    verts = mesh.vertices

    for i0, i1, i2 in mesh.triangles:
        v0, v1, v2 = verts[i0], verts[i1], verts[i2]
        ux, uy, uz = v1.x - v0.x, v1.y - v0.y, v1.z - v0.z
        vx, vy, vz = v2.x - v0.x, v2.y - v0.y, v2.z - v0.z
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        length = (nx * nx + ny * ny + nz * nz) ** 0.5
        if length > 1e-12:
            inv = 1.0 / length
            nx *= inv
            ny *= inv
            nz *= inv
        else:
            nx, ny, nz = 0.0, 1.0, 0.0

        positions.extend((v0.x, v0.y, v0.z, v1.x, v1.y, v1.z, v2.x, v2.y, v2.z))
        normals.extend((nx, ny, nz, nx, ny, nz, nx, ny, nz))

    return header.tobytes() + positions.tobytes() + normals.tobytes()


def _scaled_bbox_mm(mesh: MeshData, transform: Transform3D) -> dict[str, list[float]]:
    bb = mesh.bounding_box
    sx, sy, sz = transform.scale.x, transform.scale.y, transform.scale.z
    return {
        "raw_size_mm": [round(bb.size.x, 2), round(bb.size.y, 2), round(bb.size.z, 2)],
        "scaled_size_mm": [
            round(bb.size.x * sx, 2),
            round(bb.size.y * sy, 2),
            round(bb.size.z * sz, 2),
        ],
    }


def _safe_mesh_ref(source_ref: str, fallback_name: str) -> str:
    candidate = source_ref.replace("\\", "/").strip()
    if not candidate or candidate.startswith("/") or ":" in candidate or "\0" in candidate:
        candidate = Path(fallback_name).name
    parts = [p for p in candidate.split("/") if p not in ("", ".", "..")]
    clean = "/".join(parts) if parts else "part.stl"
    if not re.search(r"\.(stl|obj)$", clean, flags=re.IGNORECASE):
        clean += ".stl"
    return clean


@dataclass
class ScenePartEntry:
    part_id: str
    name: str
    source_ref: str
    mesh: MeshData
    transform: Transform3D = field(default_factory=Transform3D)
    visible: bool = True
    opacity: float = 1.0
    color: str = "#79c7ff"
    last_clearance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        dims = _scaled_bbox_mm(self.mesh, self.transform)
        return {
            "part_id": self.part_id,
            "name": self.name,
            "source_ref": self.source_ref,
            "triangles": len(self.mesh.triangles),
            "visible": self.visible,
            "opacity": round(self.opacity, 3),
            "color": self.color,
            "transform": {
                "position": [
                    round(self.transform.position.x, 3),
                    round(self.transform.position.y, 3),
                    round(self.transform.position.z, 3),
                ],
                "rotation": [
                    round(self.transform.rotation.x, 3),
                    round(self.transform.rotation.y, 3),
                    round(self.transform.rotation.z, 3),
                ],
                "scale": [
                    round(self.transform.scale.x, 5),
                    round(self.transform.scale.y, 5),
                    round(self.transform.scale.z, 5),
                ],
            },
            **dims,
            "last_clearance": self.last_clearance,
        }


PALETTE = ["#79c7ff", "#77e9ca", "#f6bd60", "#f28482", "#bdb2ff", "#9bf6ff"]


def _build_reference_body(
    measurements: HeadMeasurements,
    mode: str = "mannequin",
    neck_circumference_mm: float = 380.0,
) -> Any:
    gen_fn = getattr(mannequin_mod, "generate_mannequin", None)
    if mode == "mannequin" and callable(gen_fn):
        sig = inspect.signature(gen_fn)
        kwargs: dict[str, Any] = {}
        if "neck_circumference_mm" in sig.parameters:
            kwargs["neck_circumference_mm"] = neck_circumference_mm
        if "radial_segments" in sig.parameters:
            kwargs["radial_segments"] = 48
        if "height_rings" in sig.parameters:
            kwargs["height_rings"] = 32
        return gen_fn(measurements, **kwargs)
    return generate_head_mesh(measurements, radial_segments=48, height_rings=32)


class StudioState:
    def __init__(self) -> None:
        self.project_name: str = "Nowy projekt"
        self.measurements: HeadMeasurements = HeadMeasurements(
            circumference_mm=580.0,
            width_mm=160.0,
            depth_mm=200.0,
            height_mm=240.0,
        )
        self.reference_mode: str = "mannequin"
        self.neck_circumference_mm: float = 380.0
        self.head = _build_reference_body(self.measurements, self.reference_mode, self.neck_circumference_mm)
        self.head_visible: bool = True
        self.head_opacity: float = 0.92
        self.parts: dict[str, ScenePartEntry] = {}
        self.part_order: list[str] = []
        self.selected_part_id: str | None = None
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []

    def snapshot(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "reference_mode": self.reference_mode,
            "neck_circumference_mm": self.neck_circumference_mm,
            "measurements": asdict(self.measurements),
            "selected_part_id": self.selected_part_id,
            "parts": {
                pid: {
                    "name": p.name,
                    "visible": p.visible,
                    "opacity": p.opacity,
                    "position": (p.transform.position.x, p.transform.position.y, p.transform.position.z),
                    "rotation": (p.transform.rotation.x, p.transform.rotation.y, p.transform.rotation.z),
                    "scale": (p.transform.scale.x, p.transform.scale.y, p.transform.scale.z),
                }
                for pid, p in self.parts.items()
            },
        }

    def push_undo(self) -> None:
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def apply_snapshot(self, snap: dict[str, Any]) -> None:
        self.project_name = snap["project_name"]
        m_dict = snap["measurements"]
        new_m = HeadMeasurements(**m_dict)
        new_mode = snap.get("reference_mode", self.reference_mode)
        new_neck = float(snap.get("neck_circumference_mm", self.neck_circumference_mm))
        if new_m != self.measurements or new_mode != self.reference_mode or new_neck != self.neck_circumference_mm:
            self.measurements = new_m
            self.reference_mode = new_mode
            self.neck_circumference_mm = new_neck
            self.head = _build_reference_body(self.measurements, self.reference_mode, self.neck_circumference_mm)
        self.selected_part_id = snap["selected_part_id"]
        for pid, pdata in snap["parts"].items():
            if pid in self.parts:
                entry = self.parts[pid]
                entry.name = pdata["name"]
                entry.visible = pdata["visible"]
                entry.opacity = pdata["opacity"]
                entry.transform = Transform3D(
                    position=Vec3(*pdata["position"]),
                    rotation=Vec3(*pdata["rotation"]),
                    scale=Vec3(*pdata["scale"]),
                )
                entry.last_clearance = None

    def add_mesh(self, mesh: MeshData, source_ref: str, transform: Transform3D | None = None) -> ScenePartEntry:
        self.push_undo()
        pid = f"part_{uuid.uuid4().hex[:8]}"
        color = PALETTE[len(self.part_order) % len(PALETTE)]
        entry = ScenePartEntry(
            part_id=pid,
            name=mesh.name or Path(source_ref).stem,
            source_ref=source_ref,
            mesh=mesh,
            transform=transform or Transform3D(),
            color=color,
        )
        self.parts[pid] = entry
        self.part_order.append(pid)
        self.selected_part_id = pid
        return entry

    def to_summary(self) -> dict[str, Any]:
        if self.selected_part_id not in self.parts:
            self.selected_part_id = self.part_order[-1] if self.part_order else None
        return {
            "project_name": self.project_name,
            "can_undo": len(self.undo_stack) > 0,
            "can_redo": len(self.redo_stack) > 0,
            "selected_part_id": self.selected_part_id,
            "head": {
                "reference_mode": self.reference_mode,
                "neck_circumference_mm": round(self.neck_circumference_mm, 1),
                "measurements": asdict(self.measurements),
                "actual_circumference_mm": round(self.head.actual_circumference_mm, 2),
                "triangles": len(self.head.mesh.triangles),
                "visible": self.head_visible,
                "opacity": round(self.head_opacity, 3),
            },
            "parts": [self.parts[pid].to_dict() for pid in self.part_order if pid in self.parts],
        }


def _load_mesh_file(path: Path, unit_scale: float = 1.0) -> MeshData:
    ext = path.suffix.lower()
    if ext == ".stl":
        return load_stl(path, unit_scale=unit_scale)
    if ext == ".obj":
        return load_obj(path, unit_scale=unit_scale)
    raise ValueError(f"Nieobsługiwany format pliku '{ext}'. Użyj .stl lub .obj.")


def _run_clearance_analysis(head: Any, part: ScenePartEntry, height_mm: float | None = None) -> dict[str, Any]:
    rep = evaluate_helmet_clearance(head, part.mesh, helmet_transform=part.transform)
    result: dict[str, Any] = {
        "is_valid": rep.is_valid,
        "min_clearance_mm": round(rep.min_clearance_mm, 2),
        "mean_clearance_mm": round(rep.mean_clearance_mm, 2),
        "max_clearance_mm": round(rep.max_clearance_mm, 2),
        "intersecting_triangles": rep.intersecting_triangles,
    }
    eval_reg = getattr(clearance_mod, "evaluate_regional_clearance", None)
    if callable(eval_reg):
        sig = inspect.signature(eval_reg)
        kwargs: dict[str, Any] = {}
        if "helmet_transform" in sig.parameters:
            kwargs["helmet_transform"] = part.transform
        if "height_mm" in sig.parameters:
            kwargs["height_mm"] = height_mm if height_mm is not None else head.mesh.bounding_box.size.y
        reg_rep = eval_reg(head.mesh, part.mesh, **kwargs)
        if is_dataclass(reg_rep):
            result["regional"] = asdict(reg_rep)
    return result


def create_app(initial_helmet: Path | None = None, initial_rotation: Vec3 | None = None) -> Starlette:
    state = StudioState()

    if initial_helmet is not None and initial_helmet.exists():
        mesh = _load_mesh_file(initial_helmet, unit_scale=1.0)
        init_t = Transform3D(rotation=initial_rotation) if initial_rotation is not None else Transform3D()
        state.add_mesh(mesh, str(initial_helmet), transform=init_t)
        state.undo_stack.clear()

    def _get_part(part_id: str) -> ScenePartEntry:
        if part_id not in state.parts:
            raise HTTPException(status_code=404, detail=f"Nie znaleziono elementu: {part_id}")
        return state.parts[part_id]

    async def api_state(request: Request) -> JSONResponse:
        return JSONResponse(state.to_summary())

    async def api_reset(request: Request) -> JSONResponse:
        state.__init__()
        return JSONResponse(state.to_summary())

    async def api_undo(request: Request) -> JSONResponse:
        if state.undo_stack:
            state.redo_stack.append(state.snapshot())
            snap = state.undo_stack.pop()
            state.apply_snapshot(snap)
        return JSONResponse(state.to_summary())

    async def api_redo(request: Request) -> JSONResponse:
        if state.redo_stack:
            state.undo_stack.append(state.snapshot())
            snap = state.redo_stack.pop()
            state.apply_snapshot(snap)
        return JSONResponse(state.to_summary())

    async def api_head_update(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            if any(k in body for k in ("circumference_mm", "width_mm", "depth_mm", "height_mm", "neck_circumference_mm", "reference_mode")):
                state.push_undo()
                new_m = HeadMeasurements(
                    circumference_mm=float(body.get("circumference_mm", state.measurements.circumference_mm)),
                    width_mm=float(body.get("width_mm", state.measurements.width_mm)),
                    depth_mm=float(body.get("depth_mm", state.measurements.depth_mm)),
                    height_mm=float(body.get("height_mm", state.measurements.height_mm)),
                )
                if "neck_circumference_mm" in body:
                    neck_val = float(body["neck_circumference_mm"])
                    if neck_val <= 150.0 or neck_val >= 700.0:
                        raise ValueError("neck_circumference_mm musi być w zakresie 150..700 mm")
                    state.neck_circumference_mm = neck_val
                if "reference_mode" in body and body["reference_mode"] in ("mannequin", "head"):
                    state.reference_mode = str(body["reference_mode"])
                state.measurements = new_m
                state.head = _build_reference_body(state.measurements, state.reference_mode, state.neck_circumference_mm)
                for p in state.parts.values():
                    p.last_clearance = None
            if "visible" in body:
                state.head_visible = bool(body["visible"])
            if "opacity" in body:
                state.head_opacity = max(0.05, min(1.0, float(body["opacity"])))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(state.to_summary())

    async def api_head_geometry(request: Request) -> Response:
        buf = await anyio.to_thread.run_sync(_mesh_to_binary_buffers, state.head.mesh)
        return Response(content=buf, media_type="application/octet-stream")

    async def api_import_upload(request: Request) -> JSONResponse:
        form = await request.form()
        unit_scale = float(form.get("unit_scale", 1.0))
        files = form.getlist("files")
        if not files:
            raise HTTPException(status_code=400, detail="Nie wybrano żadnych plików STL/OBJ.")
        imported: list[dict[str, Any]] = []
        for item in files:
            filename = getattr(item, "filename", None) or "mesh.stl"
            suffix = Path(filename).suffix.lower()
            if suffix not in (".stl", ".obj"):
                raise HTTPException(status_code=400, detail=f"Nieobsługiwany plik: {filename}")
            raw_bytes = await item.read()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = Path(tmp.name)
            try:
                mesh = await anyio.to_thread.run_sync(_load_mesh_file, tmp_path, unit_scale)
                mesh = MeshData(name=Path(filename).stem, vertices=mesh.vertices, triangles=mesh.triangles)
            finally:
                tmp_path.unlink(missing_ok=True)
            entry = state.add_mesh(mesh, filename)
            imported.append(entry.to_dict())
        return JSONResponse({"imported": imported, "state": state.to_summary()})

    async def api_import_local(request: Request) -> JSONResponse:
        body = await request.json()
        raw_path = str(body.get("path", "")).strip()
        unit_scale = float(body.get("unit_scale", 1.0))
        if not raw_path:
            raise HTTPException(status_code=400, detail="Podaj ścieżkę do pliku STL lub OBJ.")
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"Plik nie istnieje: {path}")
        try:
            mesh = await anyio.to_thread.run_sync(_load_mesh_file, path, unit_scale)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        entry = state.add_mesh(mesh, str(path))
        return JSONResponse({"part": entry.to_dict(), "state": state.to_summary()})

    async def api_part_geometry(request: Request) -> Response:
        part = _get_part(request.path_params["part_id"])
        buf = await anyio.to_thread.run_sync(_mesh_to_binary_buffers, part.mesh)
        return Response(content=buf, media_type="application/octet-stream")

    async def api_part_select(request: Request) -> JSONResponse:
        part = _get_part(request.path_params["part_id"])
        state.selected_part_id = part.part_id
        return JSONResponse(state.to_summary())

    async def api_part_update(request: Request) -> JSONResponse:
        part = _get_part(request.path_params["part_id"])
        body = await request.json()
        try:
            if body.get("record_undo", False):
                state.push_undo()
            pos = body.get("position")
            rot = body.get("rotation")
            scl = body.get("scale")
            part.transform = Transform3D(
                position=Vec3(*pos) if pos is not None else part.transform.position,
                rotation=Vec3(*rot) if rot is not None else part.transform.rotation,
                scale=Vec3(*scl) if scl is not None else part.transform.scale,
            )
            if "visible" in body:
                part.visible = bool(body["visible"])
            if "opacity" in body:
                part.opacity = max(0.05, min(1.0, float(body["opacity"])))
            if "name" in body and str(body["name"]).strip():
                part.name = str(body["name"]).strip()
            part.last_clearance = None
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"part": part.to_dict(), "state": state.to_summary()})

    async def api_part_delete(request: Request) -> JSONResponse:
        part = _get_part(request.path_params["part_id"])
        state.push_undo()
        del state.parts[part.part_id]
        state.part_order = [pid for pid in state.part_order if pid != part.part_id]
        if state.selected_part_id == part.part_id:
            state.selected_part_id = state.part_order[-1] if state.part_order else None
        return JSONResponse(state.to_summary())

    async def api_part_autofit(request: Request) -> JSONResponse:
        part = _get_part(request.path_params["part_id"])
        body = await request.json() if await request.body() else {}
        target_mm = float(body.get("target_clearance_mm", 3.5))
        min_mm = float(body.get("min_clearance_mm", 2.0))
        max_mm = float(body.get("max_clearance_mm", 22.0))

        def _fit() -> Any:
            if state.reference_mode == "mannequin":
                return fit_helmet_to_mannequin(
                    state.head,
                    part.mesh,
                    head_measurements=state.measurements,
                    initial_rotation=part.transform.rotation,
                    target_clearance_mm=target_mm,
                    min_clearance_mm=min_mm,
                    max_clearance_mm=max_mm,
                )
            return fit_helmet(
                state.head,
                part.mesh,
                initial_rotation=part.transform.rotation,
                target_clearance_mm=target_mm,
                min_clearance_mm=min_mm,
                max_clearance_mm=max_mm,
            )

        fit_res = await anyio.to_thread.run_sync(_fit)
        state.push_undo()
        part.transform = fit_res.transform
        part.last_clearance = await anyio.to_thread.run_sync(_run_clearance_analysis, state.head, part, state.measurements.height_mm)
        return JSONResponse({"converged": fit_res.converged, "part": part.to_dict(), "state": state.to_summary()})

    async def api_part_clearance(request: Request) -> JSONResponse:
        part = _get_part(request.path_params["part_id"])
        report = await anyio.to_thread.run_sync(_run_clearance_analysis, state.head, part, state.measurements.height_mm)
        part.last_clearance = report
        return JSONResponse({"clearance": report, "part": part.to_dict(), "state": state.to_summary()})

    async def api_part_export_stl(request: Request) -> Response:
        part = _get_part(request.path_params["part_id"])
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # Eksport z transformacją sceny (bez zerowania pozycji - zgodnie z AGENTS.md)
            await anyio.to_thread.run_sync(save_stl, part.mesh, tmp_path, True, part.transform)
            data = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", part.name).strip("_") or "helmet_fitted"
        return Response(
            content=data,
            media_type="application/sla",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_fitted.stl"'},
        )

    async def api_project_export(request: Request) -> Response:
        parts_payload = [
            ProjectPart(
                part_id=p.part_id,
                name=p.name,
                mesh_path=_safe_mesh_ref(p.source_ref, f"{p.name}.stl"),
                region=BodyRegion.HEAD,
                transform=p.transform,
            )
            for pid in state.part_order
            if (p := state.parts.get(pid)) is not None
        ]
        proj = ProjectData(
            name=state.project_name,
            head_measurements=state.measurements,
            parts=parts_payload,
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            save_project(proj, tmp_path)
            raw = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        return Response(
            content=raw,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="polyfitter_project.json"'},
        )

    async def api_project_import(request: Request) -> JSONResponse:
        form = await request.form()
        file_item = form.get("file")
        if file_item is None:
            raise HTTPException(status_code=400, detail="Brak pliku projektu JSON.")
        raw = await file_item.read()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        try:
            proj = load_project(tmp_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Nieprawidłowy plik projektu: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        state.push_undo()
        state.project_name = proj.name
        if proj.head_measurements is not None:
            state.measurements = proj.head_measurements
            state.head = _build_reference_body(state.measurements, state.reference_mode, state.neck_circumference_mm)

        # Dopasuj transformacje z projektu do załadowanych już części (po part_id lub nazwie)
        by_name = {p.name: p for p in state.parts.values()}
        for pp in proj.parts:
            target = state.parts.get(pp.part_id) or by_name.get(pp.name)
            if target is not None:
                target.transform = pp.transform
                target.last_clearance = None
        return JSONResponse(state.to_summary())

    routes = [
        Route("/api/state", api_state, methods=["GET"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/api/undo", api_undo, methods=["POST"]),
        Route("/api/redo", api_redo, methods=["POST"]),
        Route("/api/head", api_head_update, methods=["POST"]),
        Route("/api/head/geometry", api_head_geometry, methods=["GET"]),
        Route("/api/import/upload", api_import_upload, methods=["POST"]),
        Route("/api/import/local", api_import_local, methods=["POST"]),
        Route("/api/parts/{part_id}/geometry", api_part_geometry, methods=["GET"]),
        Route("/api/parts/{part_id}/select", api_part_select, methods=["POST"]),
        Route("/api/parts/{part_id}/transform", api_part_update, methods=["POST"]),
        Route("/api/parts/{part_id}", api_part_delete, methods=["DELETE"]),
        Route("/api/parts/{part_id}/auto-fit", api_part_autofit, methods=["POST"]),
        Route("/api/parts/{part_id}/clearance", api_part_clearance, methods=["POST"]),
        Route("/api/parts/{part_id}/export-stl", api_part_export_stl, methods=["GET"]),
        Route("/api/project/export", api_project_export, methods=["GET"]),
        Route("/api/project/import", api_project_import, methods=["POST"]),
        Mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"),
    ]
    return Starlette(debug=False, routes=routes)
