from dataclasses import dataclass

from cnc_controller.models import JobSettings, MachineMode, MachineProfile, MaterialRule
from cnc_controller.safety import check_job_safety


def profile():
    return MachineProfile("test", (100, 100, 40), 15, 2000, 0, 1000, 5)


def test_feed_correction_uses_material_limit():
    rule = MaterialRule("plywood", "laser", MachineMode.LASER, max_feed_mm_min=800, max_power_s=600)
    job = JobSettings(MachineMode.LASER, feed_mm_min=1200, power_s=700)
    report = check_job_safety(profile(), job, rule)
    assert report.ok_to_run
    assert report.corrections == {"feed_mm_min": 800, "power_s": 600}


def test_no_corrections_when_within_limits():
    job = JobSettings(MachineMode.CNC, feed_mm_min=500)
    report = check_job_safety(profile(), job)
    assert report.ok_to_run
    assert report.corrections == {}


def test_bounds_outside_work_area_is_error():
    job = JobSettings(MachineMode.CNC, feed_mm_min=500, bounds_mm=(0, 0, 120, 20))
    report = check_job_safety(profile(), job)
    assert not report.ok_to_run
    assert "exceed work area" in report.errors[0]


def test_bounds_inside_work_area_is_ok():
    job = JobSettings(MachineMode.CNC, feed_mm_min=500, bounds_mm=(0, 0, 80, 80))
    report = check_job_safety(profile(), job)
    assert report.ok_to_run
    assert report.errors == []


def test_negative_bounds_is_error():
    job = JobSettings(MachineMode.CNC, feed_mm_min=500, bounds_mm=(-5, 0, 50, 50))
    report = check_job_safety(profile(), job)
    assert not report.ok_to_run
    assert "exceed work area" in report.errors[0]


def test_plunge_over_limit_populates_correction():
    """A plunge/Z-feed attribute, when present, is clamped to the feed limit."""

    @dataclass
    class JobWithPlunge:
        mode: MachineMode = MachineMode.CNC
        feed_mm_min: float = 500
        power_s = None
        passes: int = 1
        bounds_mm = None
        plunge_mm_min: float = 5000

    report = check_job_safety(profile(), JobWithPlunge())
    assert report.ok_to_run
    assert report.corrections == {"plunge_mm_min": 2000}


def test_zero_plunge_is_error():
    @dataclass
    class JobWithPlunge:
        mode: MachineMode = MachineMode.CNC
        feed_mm_min: float = 500
        power_s = None
        passes: int = 1
        bounds_mm = None
        plunge_mm_min: float = 0

    report = check_job_safety(profile(), JobWithPlunge())
    assert not report.ok_to_run
    assert "Plunge" in report.errors[0]


def test_missing_plunge_is_skipped_gracefully():
    job = JobSettings(MachineMode.CNC, feed_mm_min=500)
    report = check_job_safety(profile(), job)
    assert "plunge_mm_min" not in report.corrections
