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


def test_bounds_outside_work_area_is_error():
    job = JobSettings(MachineMode.CNC, feed_mm_min=500, bounds_mm=(0, 0, 120, 20))
    report = check_job_safety(profile(), job)
    assert not report.ok_to_run
    assert "exceed work area" in report.errors[0]
