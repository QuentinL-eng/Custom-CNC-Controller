from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import MachineMode


class WorkflowStep(str, Enum):
    IDLE = "idle"
    LOAD_FILE = "load_file"
    PREVIEW = "preview"
    SAFETY_CHECK = "safety_check"
    SET_ZERO = "set_zero"
    PROBE_Z = "probe_z"
    FRAME = "frame"
    RUN = "run"
    TOOL_CHANGE = "tool_change"
    COMPLETE = "complete"


@dataclass
class WorkflowState:
    mode: MachineMode
    step: WorkflowStep = WorkflowStep.IDLE
    history: list[WorkflowStep] = field(default_factory=list)

    def advance(self, step: WorkflowStep) -> None:
        self.history.append(self.step)
        self.step = step

    def reset(self) -> None:
        self.history.append(self.step)
        self.step = WorkflowStep.IDLE


def default_workflow_steps(mode: MachineMode) -> list[WorkflowStep]:
    if mode is MachineMode.CNC:
        return [WorkflowStep.LOAD_FILE, WorkflowStep.PREVIEW, WorkflowStep.SAFETY_CHECK, WorkflowStep.SET_ZERO, WorkflowStep.PROBE_Z, WorkflowStep.RUN]
    if mode is MachineMode.LASER:
        return [WorkflowStep.LOAD_FILE, WorkflowStep.PREVIEW, WorkflowStep.SAFETY_CHECK, WorkflowStep.FRAME, WorkflowStep.RUN]
    return [WorkflowStep.LOAD_FILE, WorkflowStep.PREVIEW, WorkflowStep.SAFETY_CHECK, WorkflowStep.SET_ZERO, WorkflowStep.PROBE_Z, WorkflowStep.TOOL_CHANGE, WorkflowStep.RUN]
