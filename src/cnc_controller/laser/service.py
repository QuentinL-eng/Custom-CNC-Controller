from __future__ import annotations

from pathlib import Path

from .domain import LaserJob, LaserMachineConfig, LaserMaterialPreset
from .importer import import_laser_file
from .materials import load_laser_presets
from .rayforge_adapter import RayforgeAdapter
from .safety import LaserSafetyReport, review_laser_job


class LaserApplicationService:
    """UI-independent state and use cases for the complete laser workflow."""

    def __init__(
        self,
        machine: LaserMachineConfig,
        presets_path: Path,
        rayforge: RayforgeAdapter | None = None,
    ):
        self.machine = machine
        self.presets_path = presets_path
        self.rayforge = rayforge or RayforgeAdapter()
        self.presets = load_laser_presets(presets_path)
        self.job: LaserJob | None = None
        self.laser_mode_confirmed = False
        self.warning_confirmation = False

    def import_file(self, path: Path) -> LaserJob:
        self.job = import_laser_file(path, self.rayforge)
        self.warning_confirmation = False
        return self.job

    def select_preset(self, preset: LaserMaterialPreset) -> None:
        if not self.job:
            return
        self.job.material = preset.material
        self.job.thickness_mm = preset.thickness_mm
        for layer in self.job.enabled_layers:
            layer.operation = preset.operation
            layer.speed_mm_min = preset.speed_mm_min
            layer.power_percent = preset.power_percent
            layer.passes = preset.passes
        self.warning_confirmation = False

    def safety_review(self) -> LaserSafetyReport:
        if not self.job:
            return LaserSafetyReport(errors=["No laser job is loaded."])
        preset = next(
            (
                item
                for item in self.presets
                if item.material.casefold() == self.job.material.casefold()
                and item.operation == self.job.enabled_layers[0].operation
            ),
            None,
        )
        return review_laser_job(
            self.job, self.machine, self.laser_mode_confirmed, preset
        )

    def frame_lines(self) -> list[str]:
        if not self.job or not self.job.bounds_mm:
            raise ValueError("Known job bounds are required for framing.")
        min_x, min_y, max_x, max_y = self.job.bounds_mm
        feed = self.machine.frame_speed_mm_min
        return [
            "G21",
            "G90",
            "M5",
            f"G0 X{min_x:.3f} Y{min_y:.3f}",
            f"G1 X{max_x:.3f} Y{min_y:.3f} F{feed:.0f}",
            f"G1 X{max_x:.3f} Y{max_y:.3f}",
            f"G1 X{min_x:.3f} Y{max_y:.3f}",
            f"G1 X{min_x:.3f} Y{min_y:.3f}",
            "M5",
        ]
