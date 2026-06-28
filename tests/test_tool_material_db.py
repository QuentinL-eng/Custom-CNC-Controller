"""Round-trip tests for the tool library and material preset persistence."""
from __future__ import annotations

from cnc_controller.tools import (
    ToolRecord, load_tools, save_tools,
    add_tool, update_tool, remove_tool,
)
from cnc_controller.materials import (
    MaterialPreset, load_material_presets, save_material_presets,
    load_material_rules, find_material_rule,
)
from cnc_controller.models import MachineMode


def test_tools_round_trip(tmp_path):
    path = tmp_path / "tools.json"
    tools = [
        ToolRecord("1/8in flat", "end_mill", 3.175, 2, 600.0, 12000, "general"),
        ToolRecord("V-bit 30deg", "v_bit", 0.2, 1, 180.0, 10000, "pcb"),
    ]
    save_tools(path, tools)
    loaded = load_tools(path)

    assert loaded == tools
    assert loaded[0].diameter_mm == 3.175
    assert loaded[1].flutes == 1


def test_load_tools_missing_returns_defaults(tmp_path):
    loaded = load_tools(tmp_path / "does_not_exist.json")
    assert len(loaded) > 0
    assert all(isinstance(t, ToolRecord) for t in loaded)


def test_tool_helpers():
    tools: list[ToolRecord] = []
    add_tool(tools, ToolRecord("A"))
    add_tool(tools, ToolRecord("B"))
    assert len(tools) == 2

    update_tool(tools, 0, ToolRecord("A2"))
    assert tools[0].name == "A2"

    remove_tool(tools, 1)
    assert len(tools) == 1
    assert tools[0].name == "A2"

    # out-of-range is a no-op
    remove_tool(tools, 99)
    update_tool(tools, 99, ToolRecord("X"))
    assert len(tools) == 1


def test_material_presets_round_trip(tmp_path):
    path = tmp_path / "presets.json"
    presets = [
        MaterialPreset("Plywood 6mm", "cnc", 700.0, 250.0, 14000, 0, 2, True, "ok"),
        MaterialPreset("Ply laser", "laser", 600.0, 0.0, 0, 80, 2, False, ""),
    ]
    save_material_presets(path, presets)
    loaded = load_material_presets(path)

    assert loaded == presets
    assert loaded[0].favorite is True
    assert loaded[1].mode == "laser"
    assert loaded[1].laser_power_pct == 80


def test_load_presets_missing_returns_defaults(tmp_path):
    loaded = load_material_presets(tmp_path / "nope.json")
    assert len(loaded) > 0
    assert all(isinstance(p, MaterialPreset) for p in loaded)


def test_material_rules_still_work(tmp_path):
    """The legacy MaterialRule API must remain intact alongside presets."""
    path = tmp_path / "materials.json"
    path.write_text(
        """
        {
          "rules": [
            {
              "material": "aluminum",
              "tool": "1/8in end mill",
              "mode": "cnc",
              "max_feed_mm_min": 300.0,
              "notes": "test"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    rules = load_material_rules(path)
    assert len(rules) == 1
    found = find_material_rule(rules, "Aluminum", "1/8in End Mill", MachineMode.CNC)
    assert found is not None
    assert found.max_feed_mm_min == 300.0
