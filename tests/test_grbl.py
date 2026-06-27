from cnc_controller.grbl import GrblController
from cnc_controller.models import MachineMode, MachineProfile


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
