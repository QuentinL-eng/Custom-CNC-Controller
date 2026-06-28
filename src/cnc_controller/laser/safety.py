from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..gcode import parse_words, strip_comments
from .domain import LaserJob, LaserMachineConfig, LaserMaterialPreset


SUPPORTED_G_CODES = {0, 1, 2, 3, 4, 20, 21, 53, 54, 55, 56, 57, 58, 59, 90, 91, 92}
SUPPORTED_M_CODES = {3, 4, 5}
_CODE_RE = re.compile(r"(?<![A-Z])([GMT])\s*([+-]?\d+(?:\.\d+)?)", re.I)


@dataclass
class LaserSafetyReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok_to_run(self) -> bool:
        return not self.errors

    @property
    def requires_confirmation(self) -> bool:
        return bool(self.warnings)


def review_laser_job(
    job: LaserJob,
    machine: LaserMachineConfig,
    laser_mode_confirmed: bool,
    preset: LaserMaterialPreset | None = None,
) -> LaserSafetyReport:
    report = LaserSafetyReport(errors=list(job.errors), warnings=list(job.warnings))
    if not laser_mode_confirmed:
        report.errors.append("GRBL laser mode ($32=1) has not been confirmed.")
    if not job.enabled_layers:
        report.errors.append("At least one operation layer must be enabled.")

    if job.bounds_mm:
        min_x, min_y, max_x, max_y = job.bounds_mm
        work_x, work_y = machine.work_area_mm
        if min_x < 0 or min_y < 0 or max_x > work_x or max_y > work_y:
            report.errors.append(
                f"Job bounds X{min_x:.1f}–{max_x:.1f} Y{min_y:.1f}–{max_y:.1f} "
                f"exceed the {work_x:.1f} × {work_y:.1f} mm work area."
            )
    else:
        report.warnings.append("Job bounds are unknown and cannot be checked.")

    for layer in job.enabled_layers:
        if layer.speed_mm_min <= 0:
            report.errors.append(f"{layer.name}: speed must be greater than zero.")
        if not 0 <= layer.power_percent <= 100:
            report.errors.append(f"{layer.name}: power must be between 0% and 100%.")
        if layer.passes < 1:
            report.errors.append(f"{layer.name}: passes must be at least one.")
        if layer.speed_mm_min > machine.safe_travel_speed_mm_min:
            report.warnings.append(
                f"{layer.name}: {layer.speed_mm_min:.0f} mm/min exceeds the "
                f"machine profile limit ({machine.safe_travel_speed_mm_min:.0f})."
            )
        if preset:
            if layer.speed_mm_min > preset.speed_mm_min:
                report.warnings.append(
                    f"{layer.name}: {layer.speed_mm_min:.0f} mm/min exceeds the "
                    f"{preset.material} preset ({preset.speed_mm_min:.0f})."
                )
            if layer.power_percent > preset.power_percent:
                report.warnings.append(
                    f"{layer.name}: {layer.power_percent:.0f}% power exceeds the "
                    f"{preset.material} preset ({preset.power_percent:.0f}%)."
                )
            if layer.passes > preset.passes:
                report.warnings.append(
                    f"{layer.name}: {layer.passes} passes exceeds the "
                    f"{preset.material} preset ({preset.passes})."
                )

    if job.gcode_lines:
        _review_gcode(job.gcode_lines, machine, report)
    else:
        report.errors.append("Generate G-code before running this job.")
    report.errors = _unique(report.errors)
    report.warnings = _unique(report.warnings)
    return report


def _review_gcode(
    lines: list[str],
    machine: LaserMachineConfig,
    report: LaserSafetyReport,
) -> None:
    laser_on = False
    power = 0.0
    for line_number, raw in enumerate(lines, 1):
        clean = strip_comments(raw).upper()
        if not clean:
            continue
        for letter, value in _CODE_RE.findall(clean):
            code = int(float(value))
            if letter == "G" and code not in SUPPORTED_G_CODES:
                report.warnings.append(f"Line {line_number}: unsupported G{code} command.")
            elif letter == "M":
                if code not in SUPPORTED_M_CODES:
                    report.warnings.append(f"Line {line_number}: unsupported M{code} command.")
                if code in {3, 4}:
                    laser_on = True
                elif code == 5:
                    laser_on = False
            elif letter == "T" and code != 0:
                report.warnings.append(
                    f"Line {line_number}: unsupported laser tool T{code}."
                )
        words = parse_words(clean)
        if "S" in words:
            power = words["S"]
            s_min, s_max = machine.laser_s_range
            if power < s_min or power > s_max:
                report.errors.append(
                    f"Line {line_number}: S{power:g} is outside the machine "
                    f"laser range S{s_min}–S{s_max}."
                )
        if int(words.get("G", -1)) == 0 and laser_on and power > 0:
            report.warnings.append(
                f"Line {line_number}: laser appears on (S{power:g}) during a G0 rapid move."
            )


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
