from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass, field

try:
    from PySide6.QtCore import QThread, Signal, QObject
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal as Signal, QObject

from .models import MachineProfile


# ---------------------------------------------------------------------------
# Status data model
# ---------------------------------------------------------------------------

@dataclass
class GrblStatus:
    state: str = "Disconnected"
    mpos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    wpos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    wco: tuple[float, float, float] = (0.0, 0.0, 0.0)
    feed: float = 0.0
    spindle: float = 0.0
    overrides: tuple[int, int, int] = (100, 100, 100)
    probe_triggered: bool = False
    probe_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def is_idle(self) -> bool:
        return self.state == "Idle"

    @property
    def is_running(self) -> bool:
        return self.state in ("Run", "Jog")

    @property
    def is_alarm(self) -> bool:
        return self.state.startswith("Alarm")

    @property
    def is_hold(self) -> bool:
        return self.state.startswith("Hold")

    @property
    def is_connected(self) -> bool:
        return self.state != "Disconnected"

    @property
    def state_color(self) -> str:
        if not self.is_connected:
            return "#97a0a8"
        if self.is_alarm:
            return "#d23b2f"
        if self.is_hold:
            return "#d98a0a"
        if self.is_running:
            return "#1577d4"
        return "#109a5b"


# ---------------------------------------------------------------------------
# Status line parser
# ---------------------------------------------------------------------------

_STATUS_RE = re.compile(
    r"<([^|>]+)"
    r"\|MPos:([+-]?\d+\.\d+),([+-]?\d+\.\d+),([+-]?\d+\.\d+)"
    r"(?:\|WPos:([+-]?\d+\.\d+),([+-]?\d+\.\d+),([+-]?\d+\.\d+))?"
    r"(?:\|WCO:([+-]?\d+\.\d+),([+-]?\d+\.\d+),([+-]?\d+\.\d+))?"
    r"(?:\|FS:([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?))?"
    r"(?:\|Ov:(\d+),(\d+),(\d+))?"
)

_PROBE_RE = re.compile(
    r"\[PRB:([+-]?\d+\.\d+),([+-]?\d+\.\d+),([+-]?\d+\.\d+):([01])\]"
)


def parse_status(line: str) -> GrblStatus | None:
    m = _STATUS_RE.search(line)
    if not m:
        return None

    raw_state = m.group(1)
    state = raw_state.split(":")[0]

    mx, my, mz = float(m.group(2)), float(m.group(3)), float(m.group(4))
    mpos = (mx, my, mz)

    if m.group(8) is not None:
        wco = (float(m.group(8)), float(m.group(9)), float(m.group(10)))
        wpos = (mx - wco[0], my - wco[1], mz - wco[2])
    elif m.group(5) is not None:
        wpos = (float(m.group(5)), float(m.group(6)), float(m.group(7)))
        wco = (mx - wpos[0], my - wpos[1], mz - wpos[2])
    else:
        wpos = mpos
        wco = (0.0, 0.0, 0.0)

    feed = float(m.group(11)) if m.group(11) else 0.0
    spindle = float(m.group(12)) if m.group(12) else 0.0
    ov = (int(m.group(13)), int(m.group(14)), int(m.group(15))) if m.group(13) else (100, 100, 100)

    return GrblStatus(
        state=state, mpos=mpos, wpos=wpos, wco=wco,
        feed=feed, spindle=spindle, overrides=ov
    )


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class GrblWorker(QThread):
    """QThread that owns the serial port and handles all GRBL I/O.

    Commands from the main thread arrive via thread-safe queues.
    State is pushed to the UI via Qt signals.
    """

    status_updated = Signal(object)    # GrblStatus
    response_received = Signal(str)    # raw line from GRBL
    job_progress = Signal(int, int)    # current_line, total_lines
    job_finished = Signal(bool)        # True=success, False=error
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)
    alarm_raised = Signal(str)         # unsolicited ALARM:/error: when not streaming

    def __init__(self, profile: MachineProfile, parent: QObject | None = None):
        super().__init__(parent)
        self._profile = profile
        self._serial = None
        self._serial_lock = threading.Lock()

        # Command queues
        self._rt_queue: queue.Queue[bytes] = queue.Queue()   # real-time bytes
        self._cmd_queue: queue.Queue[object] = queue.Queue()  # normal commands/job batches

        # Job streaming state (only touched in run() thread)
        self._job_lines: list[str] = []
        self._job_index: int = 0
        self._streaming: bool = False
        self._awaiting_ok: bool = False

        self._stop_flag = threading.Event()
        self._last_status = GrblStatus()

        # Auto-connect state. ALL serial opens happen on this worker thread so
        # the GUI thread can never block/freeze on a port open (which also
        # toggles DTR and resets GRBL).
        self._target_port: str | None = None
        self._target_baud: int = profile.baud_rate
        self._auto_connect: bool = False
        self._next_connect_attempt: float = 0.0
        self._is_mock: bool = False

    # ------------------------------------------------------------------
    # Public API — called from main thread
    # ------------------------------------------------------------------

    def attach_serial(self, serial_obj, is_mock: bool = False) -> None:
        with self._serial_lock:
            self._serial = serial_obj
        self._is_mock = is_mock
        if is_mock:
            self._auto_connect = False
        self.connected.emit()

    def detach_serial(self) -> None:
        with self._serial_lock:
            if self._serial:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
        # A disconnect ends any in-flight job; don't let streaming state leak
        # into a later reconnect.
        self._streaming = False
        self._awaiting_ok = False
        self._job_lines = []
        self._job_index = 0
        self._last_status = GrblStatus()
        self.disconnected.emit()

    @property
    def is_simulation(self) -> bool:
        return self._is_mock

    def enable_auto_connect(self, port: str, baud: int | None = None) -> None:
        """Keep trying to open `port` on the worker thread until the machine
        appears. Used for real hardware so a missing device at boot never
        silently falls back to the simulator."""
        self._target_port = port
        if baud:
            self._target_baud = baud
        self._is_mock = False
        self._auto_connect = True
        self._next_connect_attempt = 0.0

    def request_connect(self) -> None:
        """Manual (re)connect — non-blocking; the worker thread does the open."""
        if not self._target_port:
            self._target_port = self._profile.serial_port
            self._target_baud = self._profile.baud_rate
        self._auto_connect = True
        self._next_connect_attempt = 0.0

    def request_disconnect(self) -> None:
        """Manual disconnect — stop auto-connect and close the port."""
        self._auto_connect = False
        self.detach_serial()

    def _try_open(self) -> None:
        """Attempt to open the target port (worker thread only). Tries the
        configured port first, then any auto-detected USB-serial port."""
        if not self._target_port:
            return
        try:
            import serial as _serial
        except ImportError:
            return
        candidates = [self._target_port]
        try:
            for c in self.list_ports():
                if c not in candidates:
                    candidates.append(c)
        except Exception:
            pass
        for port in candidates:
            try:
                ser = _serial.Serial(port, self._target_baud, timeout=0.05)
            except Exception:
                continue
            with self._serial_lock:
                self._serial = ser
            self._is_mock = False
            self.connected.emit()
            return

    @property
    def is_connected(self) -> bool:
        with self._serial_lock:
            return self._serial is not None

    def reconnect(self) -> bool:
        """Best-effort reopen of the configured serial port. Returns success."""
        try:
            import serial  # type: ignore
        except ImportError:
            self.error_occurred.emit("pyserial not available")
            return False

        self.detach_serial()
        try:
            ser = serial.Serial(
                self._profile.serial_port,
                self._profile.baud_rate,
                timeout=0.05,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            self.error_occurred.emit(f"Reconnect failed: {exc}")
            return False

        self.attach_serial(ser)
        return True

    @staticmethod
    def list_ports() -> list[str]:
        """Candidate GRBL serial ports, USB-serial hints first. [] if unavailable."""
        try:
            from serial.tools import list_ports as _list_ports  # type: ignore
        except ImportError:
            return []

        try:
            ports = list(_list_ports.comports())
        except Exception:  # pragma: no cover - platform dependent
            return []

        hints = ("usb", "ch340", "ftdi", "arduino", "cp210", "ttyusb", "ttyacm", "wch")

        def _is_usb(port) -> bool:
            blob = " ".join(
                str(getattr(port, attr, "") or "")
                for attr in ("description", "hwid", "manufacturer", "product", "device")
            ).lower()
            return any(h in blob for h in hints)

        preferred = [p.device for p in ports if _is_usb(p)]
        rest = [p.device for p in ports if not _is_usb(p)]
        return preferred + rest

    def send_realtime(self, byte_val: int | bytes) -> None:
        if isinstance(byte_val, int):
            byte_val = bytes([byte_val])
        self._rt_queue.put(byte_val)

    def send_command(self, cmd: str) -> None:
        self._cmd_queue.put(cmd.strip() + "\n")

    def cycle_start(self) -> None:
        self.send_realtime(ord("~"))

    def feed_hold(self) -> None:
        self.send_realtime(ord("!"))

    def soft_reset(self) -> None:
        self.send_realtime(0x18)

    def jog(self, axis: str, distance: float, feed: float) -> None:
        axis = axis.upper()
        self.send_command(f"$J=G91 G21 {axis}{distance:.3f} F{feed:.0f}")

    def home_all(self) -> None:
        self.send_command("$H")

    def unlock(self) -> None:
        self.send_command("$X")

    def set_laser_mode(self, on: bool) -> None:
        self.send_command("$32=1" if on else "$32=0")

    def set_work_zero(self, axes: str = "XYZ") -> None:
        parts = " ".join(f"{a}0" for a in axes.upper() if a in "XYZ")
        self.send_command(f"G10 L20 P1 {parts}")

    def goto_zero(self) -> None:
        safe_z = self._profile.safe_z_mm
        self.send_command(f"G90 G0 Z{safe_z:.3f}")
        self.send_command("G90 G0 X0 Y0")

    def goto_machine_zero(self) -> None:
        safe_z = self._profile.safe_z_mm
        self.send_command(f"G90 G0 Z{safe_z:.3f}")
        self.send_command("G90 G53 G0 X0 Y0")

    def spindle_on(self, rpm: int) -> None:
        self.send_command(f"M3 S{int(rpm)}")

    def spindle_off(self) -> None:
        self.send_command("M5")

    def set_spindle_speed(self, rpm: int) -> None:
        self.send_command(f"S{int(rpm)}")

    def feed_override_reset(self) -> None:
        self.send_realtime(0x90)

    def feed_override_up(self) -> None:
        self.send_realtime(0x91)

    def feed_override_down(self) -> None:
        self.send_realtime(0x92)

    def start_job(self, lines: list[str]) -> None:
        clean = [ln for ln in lines if ln.strip() and not ln.strip().startswith(";")]
        self._cmd_queue.put(("__START_JOB__", clean))

    def stop_job(self) -> None:
        self._cmd_queue.put("__STOP_JOB__")
        self.feed_hold()

    # ------------------------------------------------------------------
    # Thread main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        last_poll = 0.0

        while not self._stop_flag.is_set():
            with self._serial_lock:
                serial = self._serial

            if serial is None:
                if self._auto_connect:
                    now = time.monotonic()
                    if now >= self._next_connect_attempt:
                        self._next_connect_attempt = now + 2.0
                        self._try_open()
                self.msleep(100)
                continue

            now = time.monotonic()

            # Status poll every 200 ms
            if now - last_poll >= 0.2:
                last_poll = now
                try:
                    serial.write(b"?")
                except Exception as exc:
                    self.error_occurred.emit(str(exc))
                    self.detach_serial()
                    continue

            # Drain real-time queue first
            while not self._rt_queue.empty():
                try:
                    rt = self._rt_queue.get_nowait()
                    serial.write(rt)
                except queue.Empty:
                    break
                except Exception as exc:
                    self.error_occurred.emit(str(exc))

            # Process one normal command (or job control token)
            if not self._cmd_queue.empty() and not self._awaiting_ok:
                try:
                    item = self._cmd_queue.get_nowait()
                except queue.Empty:
                    item = None

                if item:
                    if isinstance(item, tuple) and item[0] == "__START_JOB__":
                        self._job_lines = list(item[1])
                        self._job_index = 0
                        self._streaming = bool(self._job_lines)
                        self._awaiting_ok = False
                        if self._streaming:
                            self._send_next_job_line(serial)
                        else:
                            self.job_finished.emit(True)
                    elif item == "__STOP_JOB__":
                        self._streaming = False
                        self._awaiting_ok = False
                        self._job_lines = []
                        self._job_index = 0
                    else:
                        try:
                            serial.write(item.encode("ascii"))
                            self._awaiting_ok = True
                        except Exception as exc:
                            self.error_occurred.emit(str(exc))

            # Read responses
            try:
                raw = serial.readline()
            except Exception as exc:
                self.error_occurred.emit(str(exc))
                self.detach_serial()
                continue

            if not raw:
                continue

            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue

            if line.startswith("<"):
                status = parse_status(line)
                if status:
                    self._last_status = status
                    self.status_updated.emit(status)
            elif line.startswith("[PRB:"):
                pm = _PROBE_RE.search(line)
                if pm:
                    px, py, pz = float(pm.group(1)), float(pm.group(2)), float(pm.group(3))
                    triggered = pm.group(4) == "1"
                    self._last_status.probe_triggered = triggered
                    self._last_status.probe_pos = (px, py, pz)
                self.response_received.emit(line)
            elif line.startswith("ok"):
                self._awaiting_ok = False
                self.response_received.emit(line)
                if self._streaming:
                    if self._job_index < len(self._job_lines):
                        self._send_next_job_line(serial)
                    else:
                        self._streaming = False
                        self.job_finished.emit(True)
            elif line.startswith("error"):
                self._awaiting_ok = False
                self.response_received.emit(line)
                if self._streaming:
                    self._streaming = False
                    self.job_finished.emit(False)
                    self.error_occurred.emit(f"GRBL error during job: {line}")
                else:
                    self.alarm_raised.emit(line)
            elif line.startswith("ALARM"):
                self.response_received.emit(line)
                if not self._streaming:
                    self.alarm_raised.emit(line)
            else:
                self.response_received.emit(line)

    def _send_next_job_line(self, serial) -> None:
        if self._job_index >= len(self._job_lines):
            return
        line = self._job_lines[self._job_index]
        self._job_index += 1
        try:
            serial.write((line.strip() + "\n").encode("ascii"))
            self._awaiting_ok = True
            self.job_progress.emit(self._job_index, len(self._job_lines))
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def stop(self) -> None:
        self._stop_flag.set()
        self.wait(3000)
