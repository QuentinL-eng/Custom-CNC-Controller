from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .models import MachineProfile


_FIELD_NAMES = {f.name for f in dataclasses.fields(MachineProfile)}


def _profile_from_dict(item: dict) -> MachineProfile:
    data = {k: v for k, v in item.items() if k in _FIELD_NAMES}
    if "work_area_mm" in data and data["work_area_mm"] is not None:
        data["work_area_mm"] = tuple(data["work_area_mm"])
    if data.get("soft_limits_mm") is not None:
        data["soft_limits_mm"] = tuple(data["soft_limits_mm"])
    return MachineProfile(**data)


def _profile_to_dict(profile: MachineProfile) -> dict:
    d = dataclasses.asdict(profile)
    # JSON has no tuple type; lists round-trip cleanly back to tuples on load.
    if d.get("work_area_mm") is not None:
        d["work_area_mm"] = list(d["work_area_mm"])
    if d.get("soft_limits_mm") is not None:
        d["soft_limits_mm"] = list(d["soft_limits_mm"])
    return d


def load_profiles(path: Path) -> list[MachineProfile]:
    """Load all machine profiles from ``path``.

    Returns a list of :class:`MachineProfile`. Raises on malformed input so
    callers can fall back to a default profile.
    """
    data = json.loads(Path(path).read_text())
    return [_profile_from_dict(item) for item in data["machines"]]


def save_profiles(path: Path, profiles: list[MachineProfile]) -> None:
    """Persist ``profiles`` to ``path`` as JSON (machines array)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"machines": [_profile_to_dict(p) for p in profiles]}
    path.write_text(json.dumps(payload, indent=2))
