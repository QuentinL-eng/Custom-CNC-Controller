from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import MachineMode, MaterialRule

# Default location for the persisted material-preset library.
DEFAULT_PRESETS_PATH = Path("config/material_presets.json")


@dataclass
class MaterialPreset:
    """Richer, editable material preset used by the Materials screen.

    Distinct from the frozen ``MaterialRule`` (a hard safety limit). A preset
    captures recommended cutting parameters the operator can tweak.
    """

    name: str
    mode: str = "cnc"
    feed_mm_min: float = 600.0
    plunge_mm_min: float = 200.0
    rpm: int = 12000
    laser_power_pct: int = 0
    passes: int = 1
    favorite: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MaterialPreset":
        return cls(
            name=str(data.get("name", "")),
            mode=str(data.get("mode", "cnc")),
            feed_mm_min=float(data.get("feed_mm_min", 0.0) or 0.0),
            plunge_mm_min=float(data.get("plunge_mm_min", 0.0) or 0.0),
            rpm=int(data.get("rpm", 0) or 0),
            laser_power_pct=int(data.get("laser_power_pct", 0) or 0),
            passes=int(data.get("passes", 1) or 1),
            favorite=bool(data.get("favorite", False)),
            notes=str(data.get("notes", "")),
        )


def _default_presets() -> list[MaterialPreset]:
    return [
        MaterialPreset("Birch Plywood 6mm", "cnc", 700.0, 250.0, 14000, 0, 2,
                       True, "Climb cut, light passes."),
        MaterialPreset("Acrylic 3mm", "cnc", 400.0, 120.0, 16000, 0, 1,
                       False, "Single pass, watch for melting."),
        MaterialPreset("Birch Ply (laser cut)", "laser", 600.0, 0.0, 0, 80, 2,
                       False, "Two-pass cut on diode laser."),
    ]


def load_material_presets(path: Path | str = DEFAULT_PRESETS_PATH) -> list[MaterialPreset]:
    """Load material presets from *path*. Returns defaults if absent/invalid."""
    p = Path(path)
    if not p.exists():
        return _default_presets()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_presets()
    items = data.get("presets", []) if isinstance(data, dict) else data
    return [MaterialPreset.from_dict(item) for item in items]


def save_material_presets(path: Path | str, presets: list[MaterialPreset]) -> None:
    """Persist *presets* to *path* as JSON, creating parent dirs as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"presets": [preset.to_dict() for preset in presets]}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_material_rules(path: Path) -> list[MaterialRule]:
    data = json.loads(path.read_text())
    rules: list[MaterialRule] = []
    for item in data["rules"]:
        rules.append(
            MaterialRule(
                material=item["material"],
                tool=item["tool"],
                mode=MachineMode(item["mode"]),
                max_feed_mm_min=float(item["max_feed_mm_min"]),
                max_power_s=item.get("max_power_s"),
                notes=item.get("notes", ""),
            )
        )
    return rules


def find_material_rule(rules: list[MaterialRule], material: str, tool: str, mode: MachineMode) -> MaterialRule | None:
    material_key = material.casefold()
    tool_key = tool.casefold()
    for rule in rules:
        if rule.material.casefold() == material_key and rule.tool.casefold() == tool_key and rule.mode is mode:
            return rule
    return None
