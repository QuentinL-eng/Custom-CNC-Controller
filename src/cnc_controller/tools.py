"""Tool library backend — pure-python, no Qt.

Persists a list of cutting tools (end mills, V-bits, drills, laser, etc.) to
``config/tools.json``. Used by the Tools screen for touch-friendly editing.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Default location for the persisted tool library.
DEFAULT_TOOLS_PATH = Path("config/tools.json")

TOOL_TYPES = ("end_mill", "ball_nose", "v_bit", "drill", "engraver", "laser", "other")


@dataclass
class ToolRecord:
    name: str
    tool_type: str = "end_mill"
    diameter_mm: float = 3.175
    flutes: int = 2
    rec_feed_mm_min: float = 600.0
    rec_rpm: int = 12000
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ToolRecord":
        return cls(
            name=str(data.get("name", "")),
            tool_type=str(data.get("tool_type", "end_mill")),
            diameter_mm=float(data.get("diameter_mm", 0.0) or 0.0),
            flutes=int(data.get("flutes", 0) or 0),
            rec_feed_mm_min=float(data.get("rec_feed_mm_min", 0.0) or 0.0),
            rec_rpm=int(data.get("rec_rpm", 0) or 0),
            notes=str(data.get("notes", "")),
        )


def _default_tools() -> list[ToolRecord]:
    return [
        ToolRecord("1/8in 2-flute flat", "end_mill", 3.175, 2, 600.0, 12000,
                   "General wood/plastic roughing."),
        ToolRecord("1mm engraving V-bit", "v_bit", 1.0, 1, 180.0, 10000,
                   "PCB isolation routing / fine detail."),
        ToolRecord("0.8mm PCB drill", "drill", 0.8, 2, 60.0, 12000,
                   "Through-hole drilling."),
    ]


def load_tools(path: Path | str = DEFAULT_TOOLS_PATH) -> list[ToolRecord]:
    """Load tools from *path*. Returns sensible defaults if the file is absent."""
    p = Path(path)
    if not p.exists():
        return _default_tools()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_tools()
    items = data.get("tools", []) if isinstance(data, dict) else data
    return [ToolRecord.from_dict(item) for item in items]


def save_tools(path: Path | str, tools: list[ToolRecord]) -> None:
    """Persist *tools* to *path* as JSON, creating parent dirs as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tools": [t.to_dict() for t in tools]}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def add_tool(tools: list[ToolRecord], tool: ToolRecord) -> list[ToolRecord]:
    """Append *tool* and return the list (mutates in place)."""
    tools.append(tool)
    return tools


def update_tool(tools: list[ToolRecord], index: int, tool: ToolRecord) -> list[ToolRecord]:
    """Replace the tool at *index* with *tool*."""
    if 0 <= index < len(tools):
        tools[index] = tool
    return tools


def remove_tool(tools: list[ToolRecord], index: int) -> list[ToolRecord]:
    """Remove the tool at *index* if it exists."""
    if 0 <= index < len(tools):
        del tools[index]
    return tools
