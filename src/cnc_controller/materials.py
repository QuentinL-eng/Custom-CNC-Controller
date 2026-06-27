from __future__ import annotations

import json
from pathlib import Path

from .models import MachineMode, MaterialRule


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
