"""Tests for the Diagnostics screen and its pure helpers."""
from __future__ import annotations

import pytest

from cnc_controller.ui.screens.diagnostics import parse_setting_line


# ---------------------------------------------------------------------------
# Pure parser tests (no Qt required)
# ---------------------------------------------------------------------------

def test_parse_setting_line_basic():
    assert parse_setting_line("$110=2000.000") == ("$110", "2000.000")


def test_parse_setting_line_strips_whitespace():
    assert parse_setting_line("  $0=10  ") == ("$0", "10")


def test_parse_setting_line_rejects_non_setting():
    assert parse_setting_line("ok") is None
    assert parse_setting_line("<Idle|MPos:0,0,0>") is None
    assert parse_setting_line("$H") is None
    assert parse_setting_line("") is None


# ---------------------------------------------------------------------------
# Screen construction tests (skipped if Qt / display unavailable)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    try:
        from cnc_controller.ui.qt_compat import QApplication
    except Exception:
        pytest.skip("Qt not available")
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeWorker:
    def __init__(self):
        self.sent: list[str] = []

    def send_command(self, cmd: str) -> None:
        self.sent.append(cmd)


class _FakeController:
    def __init__(self, worker=None):
        self.worker = worker
        self.rail = None
        self.profile = None
        self.reconnected = 0
        self.disconnected = 0

    def reconnect_serial(self):
        self.reconnected += 1

    def disconnect_serial(self):
        self.disconnected += 1


def test_screen_constructs_without_worker(qapp):
    from cnc_controller.ui.screens.diagnostics import DiagnosticsScreen
    screen = DiagnosticsScreen(_FakeController(worker=None))
    # append methods must not raise when worker is None
    screen.append_sent("$X")
    screen.append_response("ok")


def test_send_command_calls_worker_and_records_recent(qapp):
    from cnc_controller.ui.screens.diagnostics import DiagnosticsScreen
    worker = _FakeWorker()
    screen = DiagnosticsScreen(_FakeController(worker=worker))
    screen._cmd_input.setText("$X")
    screen._send_command()
    assert worker.sent == ["$X"]
    assert screen._recent[0] == "$X"
    assert screen._cmd_input.text() == ""


def test_read_settings_sends_dollar_dollar_and_parses_response(qapp):
    from cnc_controller.ui.screens.diagnostics import DiagnosticsScreen
    worker = _FakeWorker()
    screen = DiagnosticsScreen(_FakeController(worker=worker))
    screen._read_settings()
    assert worker.sent == ["$$"]
    screen.append_response("$110=1500.000")
    assert screen._settings["$110"] == "1500.000"


def test_add_alarm_history(qapp):
    from cnc_controller.ui.screens.diagnostics import DiagnosticsScreen
    screen = DiagnosticsScreen(_FakeController())
    screen.add_alarm("ALARM:1")
    screen.add_alarm("error:9")
    assert screen._alarms[0] == "error:9"
    assert "ALARM:1" in screen._alarms


def test_recent_capped_at_max(qapp):
    from cnc_controller.ui.screens.diagnostics import DiagnosticsScreen
    screen = DiagnosticsScreen(_FakeController(worker=_FakeWorker()))
    for i in range(15):
        screen._push_recent(f"G{i}")
    assert len(screen._recent) == DiagnosticsScreen.MAX_RECENT


def test_connect_disconnect_buttons(qapp):
    from cnc_controller.ui.screens.diagnostics import DiagnosticsScreen
    ctrl = _FakeController()
    screen = DiagnosticsScreen(ctrl)
    screen._reconnect()
    screen._disconnect()
    assert ctrl.reconnected == 1
    assert ctrl.disconnected == 1
