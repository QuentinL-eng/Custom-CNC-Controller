from __future__ import annotations

import json
from pathlib import Path

from .models import MachineProfile


def load_profiles(path: Path) -> list[MachineProfile]:
    data = json.loads(path.read_text())
    return [MachineProfile(**item) for item in data["machines"]]
