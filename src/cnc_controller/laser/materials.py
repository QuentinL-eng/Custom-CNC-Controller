from __future__ import annotations

import json
from pathlib import Path

from .domain import LaserMaterialPreset, LaserOperationType


def load_laser_presets(path: Path) -> list[LaserMaterialPreset]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    presets = []
    for item in data.get("presets", []):
        presets.append(
            LaserMaterialPreset(
                material=item["material"],
                thickness_mm=float(item["thickness_mm"]),
                operation=LaserOperationType(item["operation"]),
                speed_mm_min=float(item["speed_mm_min"]),
                power_percent=float(item["power_percent"]),
                passes=int(item["passes"]),
                notes=item.get("notes", ""),
            )
        )
    return presets


def save_laser_presets(path: Path, presets: list[LaserMaterialPreset]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "presets": [
            {
                "material": preset.material,
                "thickness_mm": preset.thickness_mm,
                "operation": preset.operation.value,
                "speed_mm_min": preset.speed_mm_min,
                "power_percent": preset.power_percent,
                "passes": preset.passes,
                "notes": preset.notes,
            }
            for preset in presets
        ]
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
