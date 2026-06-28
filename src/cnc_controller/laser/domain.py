from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class LaserOperationType(str, Enum):
    CUT = "cut"
    LINE = "line engrave"
    FILL = "fill engrave"
    RASTER = "image / raster"


@dataclass
class LaserLayer:
    name: str
    color: str = "#1577d4"
    operation: LaserOperationType = LaserOperationType.LINE
    speed_mm_min: float = 1000.0
    power_percent: float = 40.0
    passes: int = 1
    enabled: bool = True
    feature_count: int | None = None

    def power_s(self, s_max: int) -> int:
        return round(max(0.0, min(100.0, self.power_percent)) * s_max / 100.0)


@dataclass
class LaserJob:
    source_path: Path
    source_kind: str
    layers: list[LaserLayer] = field(default_factory=list)
    bounds_mm: tuple[float, float, float, float] | None = None
    natural_size_mm: tuple[float, float] | None = None
    material: str = "Unspecified"
    thickness_mm: float | None = None
    origin: str = "front-left"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    gcode_lines: list[str] | None = None
    estimated_seconds: float | None = None

    @property
    def name(self) -> str:
        return self.source_path.name

    @property
    def enabled_layers(self) -> list[LaserLayer]:
        return [layer for layer in self.layers if layer.enabled]

    @property
    def is_generated(self) -> bool:
        return bool(self.gcode_lines)

    @property
    def can_generate(self) -> bool:
        return not self.errors and bool(self.enabled_layers)


@dataclass(frozen=True)
class LaserMaterialPreset:
    material: str
    thickness_mm: float
    operation: LaserOperationType
    speed_mm_min: float
    power_percent: float
    passes: int
    notes: str = ""


@dataclass(frozen=True)
class LaserMachineConfig:
    name: str
    work_area_mm: tuple[float, float]
    serial_port: str
    baud_rate: int
    laser_s_range: tuple[int, int]
    safe_travel_speed_mm_min: float = 3000.0
    default_origin: str = "front-left"
    homing_required: bool = True
    frame_speed_mm_min: float = 1200.0
