"""Recent-jobs history — tiny JSON store under the config dir.

Pure Python, no Qt. Records the most recently loaded job files so the home
screen can offer quick re-loading.
"""
from __future__ import annotations

import json
from pathlib import Path

# Stored alongside the machine profiles in the project config directory.
HISTORY_PATH = Path(__file__).parents[2] / "config" / "recent_jobs.json"

_MAX_ENTRIES = 20


def _store_path() -> Path:
    return HISTORY_PATH


def load_recent(limit: int = 10) -> list[str]:
    """Return up to ``limit`` recent job paths, most-recent first."""
    try:
        data = json.loads(_store_path().read_text())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    paths = [str(p) for p in data if isinstance(p, str)]
    if limit is not None and limit >= 0:
        return paths[:limit]
    return paths


def add_recent(path: str | Path) -> None:
    """Record ``path`` as the most-recent job (deduplicated, capped)."""
    path = str(Path(path))
    existing = load_recent(limit=_MAX_ENTRIES)
    # Move to front, removing any prior occurrence.
    deduped = [p for p in existing if p != path]
    deduped.insert(0, path)
    deduped = deduped[:_MAX_ENTRIES]
    try:
        store = _store_path()
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(deduped, indent=2))
    except Exception:
        # History is best-effort; never break the caller.
        pass
