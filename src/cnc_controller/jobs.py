from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gcode import GcodeAnalysis, analyze_gcode_file
from .models import JobSettings, MachineMode


SUPPORTED_EXTENSIONS = {
    ".gcode": MachineMode.CNC,
    ".gc": MachineMode.CNC,
    ".nc": MachineMode.CNC,
    ".tap": MachineMode.CNC,
    ".svg": MachineMode.LASER,
    ".dxf": MachineMode.LASER,
}


@dataclass(frozen=True)
class JobFile:
    path: Path
    guessed_mode: MachineMode
    analysis: GcodeAnalysis | None = None


def load_job_file(path: Path) -> JobFile:
    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported job file extension: {path.suffix}")
    mode = SUPPORTED_EXTENSIONS[suffix]
    analysis = analyze_gcode_file(path) if mode is MachineMode.CNC else None
    return JobFile(path=path, guessed_mode=mode, analysis=analysis)


def settings_from_gcode(job_file: JobFile, fallback_feed_mm_min: float = 500.0) -> JobSettings:
    if job_file.analysis is None:
        raise ValueError("Job file does not include G-code analysis")
    return JobSettings(
        mode=job_file.guessed_mode,
        feed_mm_min=job_file.analysis.max_feed_mm_min or fallback_feed_mm_min,
        power_s=job_file.analysis.max_power_s,
        source_file=job_file.path,
        bounds_mm=job_file.analysis.bounds_mm,
    )
