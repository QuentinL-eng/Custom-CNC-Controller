from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class MachineMode(str, Enum):
    CNC = "cnc"
    LASER = "laser"
    PCB = "pcb"


@dataclass(frozen=True)
class MachineProfile:
    name: str
    work_area_mm: tuple[float, float, float]
    probe_thickness_mm: float
    max_feed_mm_min: float
    laser_s_min: int
    laser_s_max: int
    safe_z_mm: float
    homing_required: bool = True
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200


@dataclass(frozen=True)
class MaterialRule:
    material: str
    tool: str
    mode: MachineMode
    max_feed_mm_min: float
    max_power_s: int | None = None
    notes: str = ""


@dataclass
class JobSettings:
    mode: MachineMode
    feed_mm_min: float
    power_s: int | None = None
    passes: int = 1
    source_file: Path | None = None
    bounds_mm: tuple[float, float, float, float] | None = None


@dataclass
class SafetyReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    corrections: dict[str, float | int] = field(default_factory=dict)

    @property
    def ok_to_run(self) -> bool:
        return not self.errors
