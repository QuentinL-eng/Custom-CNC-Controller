from pathlib import Path

from cnc_controller.laser.domain import (
    LaserMachineConfig,
    LaserMaterialPreset,
    LaserOperationType,
)
from cnc_controller.laser.importer import import_laser_file
from cnc_controller.laser.safety import review_laser_job
from cnc_controller.laser.rayforge_adapter import RayforgeGeneration


def machine() -> LaserMachineConfig:
    return LaserMachineConfig(
        name="test",
        work_area_mm=(100.0, 100.0),
        serial_port="mock",
        baud_rate=115200,
        laser_s_range=(0, 1000),
    )


def test_gcode_import_is_analyzed_and_kept_verbatim(tmp_path: Path):
    path = tmp_path / "mark.nc"
    source = ["G21", "G90", "M4 S300", "G1 X20 Y10 F800", "M5"]
    path.write_text("\n".join(source))

    job = import_laser_file(path)

    assert job.gcode_lines == source
    assert job.bounds_mm == (20.0, 10.0, 20.0, 10.0)
    assert job.layers[0].speed_mm_min == 800


def test_safety_requires_confirmed_grbl_laser_mode(tmp_path: Path):
    path = tmp_path / "mark.nc"
    path.write_text("G21\nM4 S300\nG1 X20 Y10 F800\nM5\n")
    job = import_laser_file(path)

    report = review_laser_job(job, machine(), laser_mode_confirmed=False)

    assert not report.ok_to_run
    assert any("$32=1" in error for error in report.errors)


def test_safety_warns_when_laser_is_on_during_rapid(tmp_path: Path):
    path = tmp_path / "unsafe.nc"
    path.write_text("G21\nM4 S300\nG0 X20 Y10\nM5\n")
    job = import_laser_file(path)

    report = review_laser_job(job, machine(), laser_mode_confirmed=True)

    assert report.ok_to_run
    assert any("rapid move" in warning for warning in report.warnings)


def test_safety_does_not_apply_material_corrections(tmp_path: Path):
    path = tmp_path / "hot.nc"
    path.write_text("G21\nM4 S900\nG1 X20 Y10 F2000\nM5\n")
    job = import_laser_file(path)
    job.material = "Birch"
    preset = LaserMaterialPreset(
        "Birch", 3.0, LaserOperationType.LINE, 800, 40, 1
    )

    report = review_laser_job(job, machine(), True, preset)

    assert report.requires_confirmation
    assert job.layers[0].speed_mm_min == 2000
    assert job.layers[0].power_percent == 90


def test_svg_fallback_discovers_size_and_layers(tmp_path: Path):
    path = tmp_path / "shape.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm">'
        '<path id="cut" stroke="#ff0000" d="M0 0L20 10"/>'
        "</svg>"
    )

    job = import_laser_file(path)

    assert job.natural_size_mm == (20.0, 10.0)
    assert job.layers[0].name == "cut"
    assert not job.is_generated


def test_frame_is_laser_off_and_uses_known_bounds(tmp_path: Path):
    from cnc_controller.laser.service import LaserApplicationService

    path = tmp_path / "mark.nc"
    path.write_text("G21\nM4 S300\nG1 X20 Y10 F800\nM5\n")
    service = LaserApplicationService(machine(), tmp_path / "presets.json")
    service.import_file(path)

    lines = service.frame_lines()

    assert lines[2] == "M5"
    assert lines[-1] == "M5"
    assert all("M3" not in line and "M4" not in line for line in lines)


def test_mock_grbl_reports_confirmed_laser_setting():
    from cnc_controller.mock_serial import MockSerial

    serial = MockSerial(timeout=0.01)
    serial.write(b"$32=1\n")
    assert serial.readline().strip().startswith(b"Grbl")
    assert serial.readline().startswith(b"[MSG")
    assert serial.readline().strip() == b"ok"
    serial.write(b"$$\n")
    settings = [serial.readline().strip() for _ in range(4)]
    serial.close()

    assert b"$32=1" in settings


def test_rayforge_generation_is_analyzed_without_rewriting(tmp_path: Path):
    from cnc_controller.laser.service import LaserApplicationService

    class FakeRayforge:
        def scan(self, path):
            from cnc_controller.laser.rayforge_adapter import RayforgeScan

            return RayforgeScan(
                layers=[
                    {
                        "name": "outline",
                        "color": "#ff0000",
                        "feature_count": 1,
                        "enabled": True,
                    }
                ],
                natural_size_mm=(20.0, 10.0),
                warnings=[],
                errors=[],
            )

        def generate(self, job, machine_config):
            return RayforgeGeneration(
                gcode_lines=[
                    "G21",
                    "G90",
                    "M4 S400",
                    "G1 X0 Y0 F800",
                    "G1 X20 Y10",
                    "M5",
                ],
                estimated_seconds=12.5,
                warnings=[],
            )

    path = tmp_path / "shape.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm">'
        '<path id="outline" stroke="#ff0000" d="M0 0L20 10"/>'
        "</svg>"
    )
    service = LaserApplicationService(
        machine(), tmp_path / "presets.json", rayforge=FakeRayforge()
    )
    service.import_file(path)

    generated = service.generate_gcode()

    assert generated.gcode_lines == [
        "G21",
        "G90",
        "M4 S400",
        "G1 X0 Y0 F800",
        "G1 X20 Y10",
        "M5",
    ]
    assert generated.bounds_mm == (0.0, 0.0, 20.0, 10.0)
    assert generated.estimated_seconds == 12.5


def test_generated_vector_job_still_requires_laser_mode(tmp_path: Path):
    from cnc_controller.laser.service import LaserApplicationService

    class FakeRayforge:
        def scan(self, path):
            from cnc_controller.laser.rayforge_adapter import RayforgeScan

            return RayforgeScan(
                layers=[],
                natural_size_mm=(10.0, 10.0),
                warnings=[],
                errors=[],
            )

        def generate(self, job, machine_config):
            return RayforgeGeneration(
                ["G21", "M4 S200", "G1 X10 Y10 F500", "M5"],
                5.0,
                [],
            )

    path = tmp_path / "shape.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm">'
        '<path d="M0 0L10 10"/></svg>'
    )
    service = LaserApplicationService(
        machine(), tmp_path / "presets.json", rayforge=FakeRayforge()
    )
    service.import_file(path)
    service.generate_gcode()

    report = service.safety_review()

    assert not report.ok_to_run
    assert any("$32=1" in error for error in report.errors)


def test_safety_blocks_gcode_power_outside_machine_range(tmp_path: Path):
    path = tmp_path / "overpower.nc"
    path.write_text("G21\nM4 S1200\nG1 X10 Y10 F500\nM5\n")
    job = import_laser_file(path)

    report = review_laser_job(job, machine(), laser_mode_confirmed=True)

    assert not report.ok_to_run
    assert any("outside the machine laser range" in item for item in report.errors)
