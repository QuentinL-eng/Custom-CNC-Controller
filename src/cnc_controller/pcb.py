from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PcbWorkflow:
    copper_gerber: Path
    drill_file: Path
    cutout_file: Path | None = None

    def operation_sequence(self) -> list[str]:
        sequence = ["isolation", "tool_change_probe_z", "drilling"]
        if self.cutout_file:
            sequence.extend(["tool_change_probe_z", "cutout"])
        return sequence
