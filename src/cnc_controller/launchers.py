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


class DisplayControlError(RuntimeError):
    pass


def default_bcnc_command() -> list[str]:
    configured = os.environ.get("CNC_CONTROLLER_BCNC_COMMAND")
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    return [sys.executable, "-m", "bCNC"]


def default_display_sleep_command() -> list[str]:
    configured = os.environ.get("CNC_CONTROLLER_DISPLAY_SLEEP_COMMAND")
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    return ["xset", "dpms", "force", "off"]


def sleep_display(command: Sequence[str] | None = None) -> None:
    sleep_command = list(command or default_display_sleep_command())
    if not sleep_command:
        raise DisplayControlError("The configured display sleep command is empty.")
    try:
        subprocess.run(sleep_command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise DisplayControlError(
            f"Could not put the display to sleep using {sleep_command[0]!r}: {exc}"
        ) from exc


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
