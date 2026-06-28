from __future__ import annotations

from pathlib import Path

import pytest

from cnc_controller.gerber import parse_excellon, parse_gerber
from cnc_controller.models import MachineProfile
from cnc_controller.pcb import PcbStage, generate_pcb_jobs


# A tiny RS-274X file: metric, one circular aperture, one trace draw, one flash.
SAMPLE_GERBER = """\
%FSLAX24Y24*%
%MOMM*%
%ADD10C,0.200000*%
D10*
X0Y0D02*
X100000Y0D01*
X100000Y50000D03*
M02*
"""

# Tiny Excellon: two tools (0.8mm, 1.0mm), two hits each.
SAMPLE_EXCELLON = """\
M48
METRIC
T01C0.800
T02C1.000
%
T01
X1000Y1000
X2000Y1000
T02
X3000Y3000
X4000Y4000
M30
"""

PROFILE = MachineProfile(
    name="test",
    work_area_mm=(300.0, 200.0, 50.0),
    probe_thickness_mm=1.0,
    max_feed_mm_min=2000.0,
    laser_s_min=0,
    laser_s_max=1000,
    safe_z_mm=5.0,
)


def test_parse_gerber_extracts_segment_and_pad():
    data = parse_gerber(SAMPLE_GERBER)
    assert data.units_mm is True
    assert 10 in data.apertures
    assert data.apertures[10].shape == "C"
    assert data.apertures[10].diameter_mm == pytest.approx(0.2)
    # One D01 draw -> one segment; one D03 flash -> one pad.
    assert len(data.segments) == 1
    assert len(data.pads) == 1
    seg = data.segments[0]
    assert seg.start == pytest.approx((0.0, 0.0))
    assert seg.end == pytest.approx((10.0, 0.0))  # 100000 / 10^4 = 10mm
    pad = data.pads[0]
    assert pad.position == pytest.approx((10.0, 5.0))


def test_parse_gerber_bounds():
    data = parse_gerber(SAMPLE_GERBER)
    bounds = data.bounds_mm
    assert bounds is not None
    min_x, min_y, max_x, max_y = bounds
    assert (min_x, min_y) == pytest.approx((0.0, 0.0))
    assert (max_x, max_y) == pytest.approx((10.0, 5.0))


def test_parse_excellon_tools_and_hits():
    data = parse_excellon(SAMPLE_EXCELLON)
    assert data.units_mm is True
    assert data.tools == {1: pytest.approx(0.8), 2: pytest.approx(1.0)}
    assert len(data.hits) == 4
    diameters = {round(h.diameter_mm, 3) for h in data.hits}
    assert diameters == {0.8, 1.0}
    first = data.hits[0]
    assert first.position == pytest.approx((0.1, 0.1))  # 1000 / 10^4 mm


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_generate_pcb_jobs_ordered_stages(tmp_path):
    copper = _write(tmp_path, "copper.gbr", SAMPLE_GERBER)
    drill = _write(tmp_path, "drill.drl", SAMPLE_EXCELLON)

    stages = generate_pcb_jobs(copper, drill, None, PROFILE)

    assert all(isinstance(s, PcbStage) for s in stages)
    # isolation, two drill groups, cutout.
    names = [s.name for s in stages]
    assert names[0] == "isolation"
    assert names[-1] == "cutout"
    assert sum(1 for n in names if n.startswith("drill_")) == 2

    # Every stage emits non-empty G-code.
    assert all(s.gcode_lines for s in stages)


def test_generate_pcb_jobs_flags():
    # Use in-memory files via tmp through pytest's tmp_path indirectly.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        copper = base / "c.gbr"
        copper.write_text(SAMPLE_GERBER)
        drill = base / "d.drl"
        drill.write_text(SAMPLE_EXCELLON)

        stages = generate_pcb_jobs(copper, drill, None, PROFILE)

    by_name = {s.name: s for s in stages}
    assert by_name["isolation"].requires_tool_change is False
    assert by_name["isolation"].requires_probe_z is False

    drill_stages = [s for s in stages if s.name.startswith("drill_")]
    # Each drill group requires a tool change and a Z re-probe after it.
    for s in drill_stages:
        assert s.requires_tool_change is True
        assert s.requires_probe_z is True

    assert by_name["cutout"].requires_tool_change is True
    assert by_name["cutout"].requires_probe_z is True


def test_isolation_and_cutout_gcode_is_plausible(tmp_path):
    copper = _write(tmp_path, "copper.gbr", SAMPLE_GERBER)
    drill = _write(tmp_path, "drill.drl", SAMPLE_EXCELLON)

    stages = generate_pcb_jobs(copper, drill, None, PROFILE)
    text = "\n".join("\n".join(s.gcode_lines) for s in stages)

    assert "G21" in text  # mm
    assert "G90" in text  # absolute
    assert "Z5" in text   # retract to safe_z
    # Drilling reaches roughly the configured depth.
    assert any("Z-1.8" in line for s in stages for line in s.gcode_lines)


def test_cutout_falls_back_to_bounding_rectangle(tmp_path):
    copper = _write(tmp_path, "copper.gbr", SAMPLE_GERBER)
    drill = _write(tmp_path, "drill.drl", SAMPLE_EXCELLON)

    stages = generate_pcb_jobs(copper, drill, None, PROFILE)
    cutout = [s for s in stages if s.name == "cutout"][0]
    # Rectangle perimeter should reference both extreme corners.
    text = "\n".join(cutout.gcode_lines)
    assert "X0" in text or "X0.0" in text
    assert "X10" in text
