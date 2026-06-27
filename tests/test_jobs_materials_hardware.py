from pathlib import Path

from cnc_controller.hardware import HardwareAction, HardwareEvent, HardwareInputRouter
from cnc_controller.jobs import load_job_file, settings_from_gcode
from cnc_controller.materials import find_material_rule, load_material_rules
from cnc_controller.models import MachineMode
from cnc_controller.workflows import WorkflowStep, default_workflow_steps


def test_load_job_file_analyzes_gcode(tmp_path: Path):
    job_path = tmp_path / "part.nc"
    job_path.write_text("G21\nG90\nG1 X3 Y4 F250\n")
    job = load_job_file(job_path)
    settings = settings_from_gcode(job)
    assert job.guessed_mode is MachineMode.CNC
    assert settings.bounds_mm == (3.0, 4.0, 3.0, 4.0)
    assert settings.feed_mm_min == 250


def test_material_lookup_matches_case_insensitively(tmp_path: Path):
    material_path = tmp_path / "materials.json"
    material_path.write_text('{"rules":[{"material":"Maple","tool":"End Mill","mode":"cnc","max_feed_mm_min":500}]}')
    rules = load_material_rules(material_path)
    assert find_material_rule(rules, "maple", "END MILL", MachineMode.CNC) == rules[0]


def test_hardware_router_dispatches_bound_actions():
    seen = []
    router = HardwareInputRouter()
    router.bind(HardwareAction.PROBE_Z, lambda event: seen.append(event.value))
    router.dispatch(HardwareEvent(HardwareAction.PROBE_Z, value=-1))
    assert seen == [-1]


def test_default_laser_workflow_includes_frame_before_run():
    steps = default_workflow_steps(MachineMode.LASER)
    assert steps[-2:] == [WorkflowStep.FRAME, WorkflowStep.RUN]
