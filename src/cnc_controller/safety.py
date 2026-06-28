from __future__ import annotations

from .models import JobSettings, MachineProfile, MaterialRule, SafetyReport


def check_job_safety(profile: MachineProfile, job: JobSettings, rule: MaterialRule | None = None) -> SafetyReport:
    report = SafetyReport()
    max_feed = min(profile.max_feed_mm_min, rule.max_feed_mm_min if rule else profile.max_feed_mm_min)
    if job.feed_mm_min <= 0:
        report.errors.append("Feed rate must be greater than zero.")
    elif job.feed_mm_min > max_feed:
        report.warnings.append(f"Feed {job.feed_mm_min:.0f} mm/min exceeds limit {max_feed:.0f} mm/min.")
        report.corrections["feed_mm_min"] = max_feed

    if job.power_s is not None:
        if job.power_s < profile.laser_s_min or job.power_s > profile.laser_s_max:
            report.errors.append(
                f"Laser/spindle S value {job.power_s} is outside profile range "
                f"{profile.laser_s_min}-{profile.laser_s_max}."
            )
        if rule and rule.max_power_s is not None and job.power_s > rule.max_power_s:
            report.warnings.append(f"Power S{job.power_s} exceeds material limit S{rule.max_power_s}.")
            report.corrections["power_s"] = rule.max_power_s

    if job.passes < 1:
        report.errors.append("Pass count must be at least one.")

    # Plunge / Z-feed verification. JobSettings may not carry a plunge value on
    # every build, so probe for it gracefully rather than assuming the field.
    plunge = getattr(job, "plunge_mm_min", None)
    if plunge is None:
        plunge = getattr(job, "z_feed_mm_min", None)
    if plunge is not None:
        if plunge <= 0:
            report.errors.append("Plunge (Z) feed must be greater than zero.")
        elif plunge > max_feed:
            report.warnings.append(
                f"Plunge feed {plunge:.0f} mm/min exceeds limit {max_feed:.0f} mm/min."
            )
            report.corrections["plunge_mm_min"] = max_feed

    if job.bounds_mm is not None:
        min_x, min_y, max_x, max_y = job.bounds_mm
        work_x, work_y, _ = profile.work_area_mm
        if min_x < 0 or min_y < 0 or max_x > work_x or max_y > work_y:
            report.errors.append(
                f"Job bounds X{min_x:.1f}-{max_x:.1f} Y{min_y:.1f}-{max_y:.1f} exceed "
                f"work area X0-{work_x:.1f} Y0-{work_y:.1f}."
            )
    return report
