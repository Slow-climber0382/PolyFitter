"""Geometry contracts: millimetres, right-handed coordinates, Y up.

No geometry solver is implemented here. Mesh normals, when supplied, are
per-vertex vectors. Euler angles describe rotations about X, then Y, then Z.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


def _finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not -float("inf") < value < float("inf"):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "z"):
            _finite(getattr(self, name), name)

    def __add__(self, other: "Vec3") -> "Vec3":
        if not isinstance(other, Vec3):
            return NotImplemented
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        if not isinstance(other, Vec3):
            return NotImplemented
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    @property
    def length(self) -> float:
        # Rescale before squaring to avoid intermediate overflow/underflow.
        scale = max(abs(self.x), abs(self.y), abs(self.z))
        if scale == 0:
            return 0.0
        return scale * ((self.x / scale)**2 + (self.y / scale)**2 + (self.z / scale)**2)**0.5


@dataclass(frozen=True)
class BoundingBox3D:
    min_pt: Vec3
    max_pt: Vec3

    def __post_init__(self) -> None:
        if not isinstance(self.min_pt, Vec3) or not isinstance(self.max_pt, Vec3):
            raise ValueError("Bounds must be Vec3")
        if any(getattr(self.min_pt, a) > getattr(self.max_pt, a) for a in ("x", "y", "z")):
            raise ValueError("Bounding box minimum exceeds maximum")

    @property
    def size(self) -> Vec3:
        return self.max_pt - self.min_pt

    @property
    def center(self) -> Vec3:
        return Vec3(*(getattr(self.min_pt, a)/2 + getattr(self.max_pt, a)/2 for a in ("x", "y", "z")))


class BodyRegion(Enum):
    HEAD = "head"
    TORSO = "torso"
    ARM_LEFT = "arm_left"
    ARM_RIGHT = "arm_right"
    LEG_LEFT = "leg_left"
    LEG_RIGHT = "leg_right"


@dataclass(frozen=True)
class HeadMeasurements:
    """Broad input guardrails, not medically validated anthropometric limits.

    Width is measured above the ears; depth front-to-back; height crown-to-chin.
    Values outside the supported range require explicit future profile support.
    """
    circumference_mm: float
    width_mm: float
    depth_mm: float
    height_mm: float

    # Inclusive ranges; consistency of the resulting anatomical mesh is separate.
    RANGES_MM: ClassVar[tuple[tuple[str, float, float], ...]] = (
        ("circumference_mm", 300.0, 800.0),
        ("width_mm", 80.0, 250.0),
        ("depth_mm", 100.0, 350.0),
        ("height_mm", 120.0, 400.0),
    )

    def __post_init__(self) -> None:
        for name, low, high in self.RANGES_MM:
            value = getattr(self, name)
            _finite(value, name)
            if not low <= value <= high:
                raise ValueError(f"{name} must be in [{low}, {high}] mm")


@dataclass(frozen=True)
class Transform3D:
    """Transform data only. Positive axis scales; uniform-scale policy is separate."""
    position: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    rotation: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))

    def __post_init__(self) -> None:
        if not all(isinstance(v, Vec3) for v in (self.position, self.rotation, self.scale)):
            raise ValueError("Transform fields must be Vec3")
        if min(self.scale.x, self.scale.y, self.scale.z) <= 0:
            raise ValueError("Scale components must be positive")


@dataclass
class MeshData:
    """Indexed triangle mesh. Bounds are recomputed to reflect mutable vertices.

    This validates representation, not watertightness, winding or collisions.
    Repeated triangle indices are rejected; collinear vertices remain possible.
    """
    name: str
    vertices: list[Vec3]
    triangles: list[tuple[int, int, int]]
    normals: list[Vec3] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Mesh name must not be empty")
        self._validate_vertices()
        for tri in self.triangles:
            if len(tri) != 3 or any(type(i) is not int or not 0 <= i < len(self.vertices) for i in tri):
                raise ValueError("Triangle requires three valid vertex indices")
            if len(set(tri)) != 3:
                raise ValueError("Triangle indices must be distinct")
        if self.normals is not None:
            if len(self.normals) != len(self.vertices) or any(not isinstance(n, Vec3) or n.length == 0 for n in self.normals):
                raise ValueError("Provide one nonzero normal per vertex")

    def _validate_vertices(self) -> None:
        if not self.vertices or any(not isinstance(v, Vec3) for v in self.vertices):
            raise ValueError("Mesh requires nonempty Vec3 vertices")

    @property
    def bounding_box(self) -> BoundingBox3D:
        self._validate_vertices()
        return BoundingBox3D(
            Vec3(*(min(getattr(v, a) for v in self.vertices) for a in ("x", "y", "z"))),
            Vec3(*(max(getattr(v, a) for v in self.vertices) for a in ("x", "y", "z"))),
        )


@dataclass(frozen=True)
class FitClearanceReport:
    """Validity of supplied statistics, NOT proof of a complete collision check.

    Signed negative clearance is allowed to describe penetration. Thresholds
    2–4 mm are inclusive and apply to both extrema, not just to the mean.
    """
    min_clearance_mm: float
    max_clearance_mm: float
    mean_clearance_mm: float
    intersecting_triangles: int

    def __post_init__(self) -> None:
        for name in ("min_clearance_mm", "max_clearance_mm", "mean_clearance_mm"):
            _finite(getattr(self, name), name)
        if not self.min_clearance_mm <= self.mean_clearance_mm <= self.max_clearance_mm:
            raise ValueError("Expected min <= mean <= max")
        if type(self.intersecting_triangles) is not int or self.intersecting_triangles < 0:
            raise ValueError("Collision count must be a nonnegative integer")

    @property
    def is_valid(self) -> bool:
        return self.intersecting_triangles == 0 and 2.0 <= self.min_clearance_mm <= self.max_clearance_mm <= 4.0
