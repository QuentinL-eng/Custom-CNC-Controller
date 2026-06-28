from __future__ import annotations

import os
import shlex
import subprocess
import sys
from importlib.util import find_spec
from collections.abc import Sequence
from dataclasses import dataclass


class ApplicationLaunchError(RuntimeError):
    pass


def default_bcnc_command() -> list[str]:
    configured = os.environ.get("CNC_CONTROLLER_BCNC_COMMAND")
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    return [sys.executable, "-m", "bCNC"]


@dataclass
class BcncLauncher:
    command: Sequence[str] | None = None
    process: subprocess.Popen[bytes] | None = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def launch(self) -> subprocess.Popen[bytes]:
        if self.is_running:
            assert self.process is not None
            return self.process

        using_packaged_bcnc = self.command is None and not os.environ.get(
            "CNC_CONTROLLER_BCNC_COMMAND"
        )
        if using_packaged_bcnc and find_spec("bCNC") is None:
            raise ApplicationLaunchError(
                "The bCNC Python package is not installed."
            )

        command = list(self.command or default_bcnc_command())
        if not command:
            raise ApplicationLaunchError("The configured bCNC command is empty.")
        try:
            self.process = subprocess.Popen(command)
        except OSError as exc:
            raise ApplicationLaunchError(
                f"Could not start bCNC using {command[0]!r}: {exc}"
            ) from exc
        return self.process
