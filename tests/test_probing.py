"""Tests for the probe G-code macro generator (no Qt display needed)."""
import pytest

from cnc_controller.ui.screens.probing import (
    build_probe_commands,
    KIND_Z, KIND_CORNER, KIND_EDGE, KIND_CENTER,
)


def test_z_probe_basic_sequence():
    cmds = build_probe_commands(KIND_Z, thickness=15.0, feed=100.0, retract=3.0,
                                probe_distance=25.0)
    assert cmds == [
        "G91",
        "G38.2 Z-25.000 F100",
        "G0 Z3.000",
        "G90",
    ]


def test_z_probe_omits_offset_command():
    # The G10 work-offset must NOT be emitted by the macro; the screen applies
    # it only after a confirmed trigger.
    cmds = build_probe_commands(KIND_Z, thickness=12.7)
    assert not any("G10" in c for c in cmds)


def test_z_probe_feed_rounded_to_int():
    cmds = build_probe_commands(KIND_Z, feed=133.7)
    assert "G38.2 Z-25.000 F134" in cmds


def test_z_probe_uses_relative_then_absolute():
    cmds = build_probe_commands(KIND_Z)
    assert cmds[0] == "G91"
    assert cmds[-1] == "G90"


def test_edge_default_positive_x():
    cmds = build_probe_commands(KIND_EDGE, feed=80, retract=2.0,
                                probe_distance=20.0, edge_axis="X", edge_dir=1)
    assert "G38.2 X20.000 F80" in cmds
    assert "G0 X-2.000" in cmds
    assert cmds[0] == "G91" and cmds[-1] == "G90"


def test_edge_negative_y_direction():
    cmds = build_probe_commands(KIND_EDGE, edge_axis="Y", edge_dir=-1,
                                probe_distance=10.0, retract=1.0)
    assert "G38.2 Y-10.000 F100" in cmds
    assert "G0 Y1.000" in cmds


def test_edge_invalid_axis_falls_back_to_x():
    cmds = build_probe_commands(KIND_EDGE, edge_axis="Z", probe_distance=5.0)
    assert any(c.startswith("G38.2 X") for c in cmds)


def test_corner_front_left_directions():
    cmds = build_probe_commands(KIND_CORNER, feed=120, retract=2.0,
                                probe_distance=15.0, corner=("front", "left"))
    # Z first, then +X edge, then +Y edge for a front-left corner.
    assert "G38.2 Z-15.000 F120" in cmds
    assert "G38.2 X15.000 F120" in cmds
    assert "G38.2 Y15.000 F120" in cmds
    assert cmds[0] == "G91" and cmds[-1] == "G90"


def test_corner_back_right_flips_signs():
    cmds = build_probe_commands(KIND_CORNER, probe_distance=15.0,
                                corner=("back", "right"))
    assert "G38.2 X-15.000 F100" in cmds
    assert "G38.2 Y-15.000 F100" in cmds


def test_center_emits_paired_x_touches():
    cmds = build_probe_commands(KIND_CENTER, probe_distance=12.0, retract=1.5)
    assert "G38.2 X12.000 F100" in cmds
    assert "G38.2 X-12.000 F100" in cmds
    assert cmds[0] == "G91" and cmds[-1] == "G90"


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        build_probe_commands("bogus")
