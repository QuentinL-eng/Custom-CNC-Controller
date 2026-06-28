"""Persistent GitHub synchronization status for the controller UI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def default_status_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return root / "cnc-controller" / "update-status.json"


@dataclass(frozen=True)
class UpdateStatus:
    pull_count: int = 0
    last_pull_at: str | None = None
    last_check_at: str | None = None
    current_commit: str = ""
    result: str = "unknown"
    message: str = "No update check has been recorded."

    @property
    def last_pull_display(self) -> str:
        return _display_time(self.last_pull_at)

    @property
    def last_check_display(self) -> str:
        return _display_time(self.last_check_at)


class UpdateStatusStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_status_path()

    def load(self) -> UpdateStatus:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return UpdateStatus()
        return UpdateStatus(
            pull_count=max(0, int(data.get("pull_count", 0))),
            last_pull_at=data.get("last_pull_at"),
            last_check_at=data.get("last_check_at"),
            current_commit=str(data.get("current_commit", "")),
            result=str(data.get("result", "unknown")),
            message=str(data.get("message", "")),
        )

    def record(
        self,
        result: str,
        commit: str,
        message: str,
        *,
        pulled: bool = False,
    ) -> UpdateStatus:
        previous = self.load()
        now = datetime.now(timezone.utc).isoformat()
        status = UpdateStatus(
            pull_count=previous.pull_count + (1 if pulled else 0),
            last_pull_at=now if pulled else previous.last_pull_at,
            last_check_at=now,
            current_commit=commit,
            result=result,
            message=message,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(status), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return status


class UpdateManager:
    def __init__(
        self,
        store: UpdateStatusStore | None = None,
        runner=None,
    ):
        self.store = store or UpdateStatusStore()
        self._run = runner or subprocess.run

    def status(self) -> UpdateStatus:
        return self.store.load()

    def check_now(self) -> UpdateStatus:
        result = self._run(
            ["systemctl", "--user", "start", "cnc-git-sync.service"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Update service failed").strip()
            raise RuntimeError(detail)
        return self.store.load()


def _display_time(value: str | None) -> str:
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%b %d, %Y · %I:%M %p")
    except ValueError:
        return value


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--result", required=True)
    record.add_argument("--commit", default="")
    record.add_argument("--message", default="")
    record.add_argument("--pulled", action="store_true")
    args = parser.parse_args()
    if args.command == "record":
        UpdateStatusStore().record(
            args.result,
            args.commit,
            args.message,
            pulled=args.pulled,
        )


if __name__ == "__main__":
    main()
