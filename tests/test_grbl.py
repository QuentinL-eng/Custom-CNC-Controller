from cnc_controller.grbl import GrblController
from cnc_controller.grbl_worker import GrblWorker, parse_status
from cnc_controller.mock_serial import MockSerial
from cnc_controller.models import MachineMode, MachineProfile


def _profile() -> MachineProfile:
    # name, work_area, probe_thickness, max_feed, laser_s_min, laser_s_max, safe_z
    return MachineProfile("test", (100.0, 100.0, 50.0), 0.1, 1000.0, 0, 1000, 5.0)


class FakeSerial:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def readline(self):
        return b"ok\n"

    def close(self):
        pass


def test_mode_switch_writes_grbl_laser_setting():
    serial = FakeSerial()
    controller = GrblController(MachineProfile("test", (1, 1, 1), 1, 1, 0, 1000, 1), serial)
    assert controller.set_mode(MachineMode.LASER) == "ok"
    assert serial.writes[-1] == b"$32=1\n"


def test_jog_formats_incremental_command():
    serial = FakeSerial()
    controller = GrblController(MachineProfile("test", (1, 1, 1), 1, 1000, 0, 1000, 1), serial)
    controller.jog("x", 1.25, 300)
    assert serial.writes[-1] == b"$J=G91 G21 X1.250 F300\n"


# ---------------------------------------------------------------------------
# GrblWorker command-queue behaviour (no running thread / no Qt event loop)
# ---------------------------------------------------------------------------

def _drain_cmds(worker: GrblWorker) -> list[str]:
    out = []
    while not worker._cmd_queue.empty():
        out.append(worker._cmd_queue.get_nowait())
    return out


def test_set_work_zero_emits_persistent_g10_l20():
    worker = GrblWorker(_profile())
    worker.set_work_zero("XYZ")
    cmds = _drain_cmds(worker)
    assert cmds == ["G10 L20 P1 X0 Y0 Z0\n"]
    assert "G92" not in cmds[0]


def test_set_work_zero_respects_axis_subset():
    worker = GrblWorker(_profile())
    worker.set_work_zero("Z")
    assert _drain_cmds(worker) == ["G10 L20 P1 Z0\n"]


def test_goto_zero_lifts_to_safe_z_first():
    worker = GrblWorker(_profile())
    worker.goto_zero()
    cmds = _drain_cmds(worker)
    assert cmds == ["G90 G0 Z5.000\n", "G90 G0 X0 Y0\n"]


def test_goto_machine_zero_lifts_then_g53():
    worker = GrblWorker(_profile())
    worker.goto_machine_zero()
    cmds = _drain_cmds(worker)
    assert cmds == ["G90 G0 Z5.000\n", "G90 G53 G0 X0 Y0\n"]


def test_spindle_commands():
    worker = GrblWorker(_profile())
    worker.spindle_on(12000)
    worker.spindle_off()
    worker.set_spindle_speed(8000)
    assert _drain_cmds(worker) == ["M3 S12000\n", "M5\n", "S8000\n"]


def test_feed_override_emits_realtime_bytes():
    worker = GrblWorker(_profile())
    worker.feed_override_reset()
    worker.feed_override_up()
    worker.feed_override_down()
    rt = []
    while not worker._rt_queue.empty():
        rt.append(worker._rt_queue.get_nowait())
    assert rt == [b"\x90", b"\x91", b"\x92"]


def test_list_ports_is_static_and_returns_list():
    assert isinstance(GrblWorker.list_ports(), list)


# ---------------------------------------------------------------------------
# MockSerial responses to the new commands
# ---------------------------------------------------------------------------

def test_mock_serial_spindle_on_off():
    mock = MockSerial()
    mock.flushInput()
    mock.write(b"M3 S8000\n")
    assert mock.readline() == b"ok\r\n"
    assert mock._spindle_on is True
    assert mock._spindle == 8000.0
    mock.write(b"M5\n")
    assert mock.readline() == b"ok\r\n"
    assert mock._spindle_on is False
    assert mock._spindle == 0.0
    mock.close()


def test_mock_serial_g10_l20_sets_work_zero():
    mock = MockSerial()
    mock.flushInput()
    mock._mpos = [10.0, 20.0, 30.0]
    mock.write(b"G10 L20 P1 X0 Y0 Z0\n")
    assert mock.readline() == b"ok\r\n"
    assert mock._wco == [10.0, 20.0, 30.0]
    mock.close()


def test_mock_serial_g53_uses_machine_coords():
    mock = MockSerial()
    mock.flushInput()
    mock._wco = [5.0, 5.0, 0.0]
    mock.write(b"G90 G53 G0 X0 Y0\n")
    assert mock.readline() == b"ok\r\n"
    # G53 ignores the work offset -> machine position is the literal coords
    assert mock._mpos[0] == 0.0
    assert mock._mpos[1] == 0.0
    mock.close()


def test_mock_serial_feed_override_bytes_and_ov_field():
    mock = MockSerial()
    mock.flushInput()
    mock.write(bytes([0x91]))  # +10%
    mock.write(bytes([0x91]))  # +10%
    assert mock._ov_feed == 120
    mock.write(bytes([0x92]))  # -10%
    assert mock._ov_feed == 110
    mock.write(bytes([0x90]))  # reset
    assert mock._ov_feed == 100
    mock.flushInput()
    mock.write(b"?")
    status_line = mock.readline().decode()
    assert "Ov:100,100,100" in status_line
    parsed = parse_status(status_line)
    assert parsed is not None and parsed.overrides == (100, 100, 100)
    mock.close()


def test_enable_auto_connect_sets_target_without_blocking():
    worker = GrblWorker(_profile())
    worker.enable_auto_connect("/dev/ttyUSB0", 115200)
    assert worker._auto_connect is True
    assert worker._target_port == "/dev/ttyUSB0"
    assert worker._target_baud == 115200
    assert worker._next_connect_attempt == 0.0
    assert worker.is_connected is False  # nothing opened on the calling thread


def test_attach_mock_marks_simulation_and_disables_autoconnect():
    worker = GrblWorker(_profile())
    worker.enable_auto_connect("/dev/ttyUSB0")
    worker.attach_serial(MockSerial(), is_mock=True)
    assert worker.is_simulation is True
    assert worker._auto_connect is False
    assert worker.is_connected is True


def test_attach_real_serial_is_not_simulation():
    worker = GrblWorker(_profile())
    worker.attach_serial(FakeSerial())
    assert worker.is_simulation is False
    assert worker.is_connected is True


def test_request_disconnect_stops_autoconnect_and_closes():
    worker = GrblWorker(_profile())
    worker.attach_serial(MockSerial())
    worker.request_disconnect()
    assert worker._auto_connect is False
    assert worker.is_connected is False


def test_detach_clears_streaming_state():
    worker = GrblWorker(_profile())
    worker.attach_serial(MockSerial())
    worker._streaming = True
    worker._job_lines = ["G0 X1", "G0 X2"]
    worker._job_index = 1
    worker.detach_serial()
    assert worker._streaming is False
    assert worker._job_lines == []
    assert worker._job_index == 0


def test_try_open_without_target_is_noop():
    worker = GrblWorker(_profile())
    worker._try_open()  # no target port set — must not raise
    assert worker.is_connected is False
