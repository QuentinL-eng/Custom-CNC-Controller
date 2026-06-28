"""Tests for the PCB wizard run-plan sequencing logic.

These tests exercise the pure (Qt-free) PcbRunPlan helper so they run fast
with no display or serial port. The helper is what the PcbWizardScreen uses
to decide which prompt to show before each stage and when to advance.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cnc_controller.ui.screens.pcb_wizard import (
    PcbRunPlan,
    PROMPT_NONE,
    PROMPT_TOOL_CHANGE,
    PROMPT_PROBE_Z,
    tool_change_text,
    probe_z_text,
)


@dataclass
class FakeStage:
    """Duck-typed stand-in for pcb.PcbStage (same attribute contract)."""
    name: str
    gcode_lines: list = field(default_factory=list)
    requires_tool_change: bool = False
    requires_probe_z: bool = False
    description: str = ""


def _typical_stages():
    return [
        FakeStage("Isolation", ["G0 X0 Y0", "G1 X1"], description="Mill isolation"),
        FakeStage("Drill", ["G81 X1 Y1"], requires_tool_change=True,
                  requires_probe_z=True, description="Drill holes"),
        FakeStage("Cutout", ["G1 X10"], requires_tool_change=True,
                  description="Cut board outline"),
    ]


def test_empty_plan_is_finished():
    plan = PcbRunPlan([])
    assert plan.finished
    assert plan.total == 0
    assert plan.current is None
    assert plan.next_prompt() == (PROMPT_NONE, None)


def test_first_stage_no_flag_starts_immediately():
    stages = _typical_stages()
    plan = PcbRunPlan(stages)
    prompt, stage = plan.next_prompt()
    assert prompt == PROMPT_NONE
    assert stage is stages[0]
    assert plan.gcode_for_current() == ["G0 X0 Y0", "G1 X1"]


def test_tool_change_takes_priority_over_probe():
    # Drill stage declares both flags; tool-change is surfaced first.
    plan = PcbRunPlan(_typical_stages())
    plan.advance()  # move to Drill
    prompt, stage = plan.next_prompt()
    assert prompt == PROMPT_TOOL_CHANGE
    assert stage.name == "Drill"


def test_confirm_clears_prompt_for_current_stage():
    plan = PcbRunPlan(_typical_stages())
    plan.advance()  # Drill (tool change)
    assert plan.next_prompt()[0] == PROMPT_TOOL_CHANGE
    plan.confirm()
    prompt, stage = plan.next_prompt()
    assert prompt == PROMPT_NONE
    assert stage.name == "Drill"


def test_advance_resets_confirmation():
    plan = PcbRunPlan(_typical_stages())
    plan.advance()
    plan.confirm()
    assert plan.next_prompt()[0] == PROMPT_NONE
    plan.advance()  # Cutout — confirmation must be reset
    assert plan.next_prompt()[0] == PROMPT_TOOL_CHANGE


def test_probe_only_stage_yields_probe_prompt():
    stages = [FakeStage("Z-touch", ["G38.2"], requires_probe_z=True)]
    plan = PcbRunPlan(stages)
    prompt, _ = plan.next_prompt()
    assert prompt == PROMPT_PROBE_Z


def test_full_sequence_order_of_prompts():
    plan = PcbRunPlan(_typical_stages())
    seq = plan.prompt_sequence()
    assert seq == [
        (PROMPT_NONE, "Isolation"),
        (PROMPT_TOOL_CHANGE, "Drill"),
        (PROMPT_TOOL_CHANGE, "Cutout"),
    ]


def test_full_run_walkthrough():
    stages = _typical_stages()
    plan = PcbRunPlan(stages)

    seen = []
    while not plan.finished:
        prompt, stage = plan.next_prompt()
        if prompt != PROMPT_NONE:
            seen.append((stage.name, prompt))
            plan.confirm()
            # after confirming, no further prompt for this stage
            assert plan.next_prompt()[0] == PROMPT_NONE
        # "stream" the stage then advance on success
        assert plan.gcode_for_current() == stage.gcode_lines
        plan.advance()

    assert plan.finished
    assert plan.index == 3
    assert seen == [("Drill", PROMPT_TOOL_CHANGE), ("Cutout", PROMPT_TOOL_CHANGE)]


def test_gcode_for_current_when_finished_is_empty():
    plan = PcbRunPlan(_typical_stages())
    for _ in range(3):
        plan.advance()
    assert plan.finished
    assert plan.gcode_for_current() == []


def test_prompt_text_helpers_include_stage_name():
    stage = FakeStage("Drill", requires_tool_change=True)
    assert "Drill" in tool_change_text(stage)
    assert "Continue" in tool_change_text(stage)
    assert "Drill" in probe_z_text(stage)
    # Probe prompt reassures that X/Y zero is kept.
    assert "X/Y" in probe_z_text(stage)
