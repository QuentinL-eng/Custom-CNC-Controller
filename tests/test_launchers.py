import sys
from unittest.mock import Mock, patch

import pytest

from cnc_controller.launchers import (
    ApplicationLaunchError,
    BcncLauncher,
    default_bcnc_command,
)


def test_default_bcnc_command_uses_current_python(monkeypatch):
    monkeypatch.delenv("CNC_CONTROLLER_BCNC_COMMAND", raising=False)
    assert default_bcnc_command() == [sys.executable, "-m", "bCNC"]


def test_configured_bcnc_command_is_used(monkeypatch):
    monkeypatch.setenv("CNC_CONTROLLER_BCNC_COMMAND", "/opt/bcnc/run --fullscreen")
    assert default_bcnc_command() == ["/opt/bcnc/run", "--fullscreen"]


@patch("cnc_controller.launchers.subprocess.Popen")
def test_launcher_does_not_open_duplicate_process(popen):
    process = Mock()
    process.poll.return_value = None
    popen.return_value = process
    launcher = BcncLauncher(["python", "-m", "bCNC"])

    assert launcher.launch() is process
    assert launcher.launch() is process
    popen.assert_called_once_with(["python", "-m", "bCNC"])


@patch("cnc_controller.launchers.find_spec", return_value=None)
def test_launcher_reports_missing_default_package(_find_spec, monkeypatch):
    monkeypatch.delenv("CNC_CONTROLLER_BCNC_COMMAND", raising=False)
    with pytest.raises(ApplicationLaunchError, match="not installed"):
        BcncLauncher().launch()
