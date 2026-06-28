from __future__ import annotations

import math
import queue
import re
import threading
import time


class MockSerial:
    """Simulated GRBL serial port for development without hardware.

    Responds to GRBL 1.1 protocol: status reports, ok/error, jog commands.
    """

    def __init__(self, port: str = "MOCK", baudrate: int = 115200, timeout: float = 0.05):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self.in_waiting = 0

        self._lock = threading.Lock()
        self._rx: queue.Queue[bytes] = queue.Queue()
        self._mpos = [0.0, 0.0, 0.0]
        self._wco = [0.0, 0.0, 0.0]
        self._state = "Alarm"
        self._feed = 0.0
        self._spindle = 0.0
        self._laser_mode = False
        self._homed = False
        self._sim_thread = threading.Thread(target=self._sim_loop, daemon=True)
        self._sim_thread.start()

        self._rx.put(b"\r\nGrbl 1.1h ['$' for help]\r\n")
        self._rx.put(b"[MSG:'$H'|'$X' to unlock]\r\n")

    # -- Internal simulation --------------------------------------------------

    def _sim_loop(self) -> None:
        while self.is_open:
            time.sleep(0.1)
            with self._lock:
                self.in_waiting = self._rx.qsize()

    def _build_status(self) -> bytes:
        x, y, z = self._mpos
        wx = x - self._wco[0]
        wy = y - self._wco[1]
        wz = z - self._wco[2]
        state = self._state
        return (
            f"<{state}|MPos:{x:.3f},{y:.3f},{z:.3f}"
            f"|WCO:{self._wco[0]:.3f},{self._wco[1]:.3f},{self._wco[2]:.3f}"
            f"|FS:{self._feed:.0f},{self._spindle:.0f}>\r\n"
        ).encode()

    def _handle(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            return

        # Real-time status
        if cmd == "?":
            self._rx.put(self._build_status())
            return

        # Soft reset
        if cmd == "\x18":
            self._state = "Idle"
            self._rx.put(b"\r\nGrbl 1.1h ['$' for help]\r\n")
            return

        # Real-time cycle start
        if cmd == "~":
            if self._state.startswith("Hold"):
                self._state = "Run"
            return

        # Real-time feed hold
        if cmd == "!":
            self._state = "Hold:0"
            return

        # Homing
        if cmd in ("$H", "$HX", "$HY", "$HZ"):
            self._homed = True
            self._mpos = [0.0, 0.0, 0.0]
            self._state = "Idle"
            self._rx.put(b"ok\r\n")
            return

        # Unlock alarm
        if cmd == "$X":
            self._state = "Idle"
            self._rx.put(b"[MSG:Caution: Unlocked]\r\nok\r\n")
            return

        # Laser mode
        if cmd == "$32=1":
            self._laser_mode = True
            self._rx.put(b"ok\r\n")
            return
        if cmd == "$32=0":
            self._laser_mode = False
            self._rx.put(b"ok\r\n")
            return

        # Settings read
        if cmd == "$$":
            self._rx.put(b"$0=10\r\n$1=25\r\n$32=0\r\nok\r\n")
            return

        # Jog command
        if cmd.upper().startswith("$J="):
            self._handle_jog(cmd[3:])
            return

        # G38.2 probe
        if cmd.upper().startswith("G38"):
            mz = self._mpos[2]
            touch_z = mz - 5.0  # simulate touching 5mm down
            self._mpos[2] = touch_z
            self._rx.put(
                f"[PRB:{self._mpos[0]:.3f},{self._mpos[1]:.3f},{touch_z:.3f}:1]\r\nok\r\n".encode()
            )
            return

        # G10 L20 - set WCO
        m = re.search(r"G10\s+L20\s+P\d+\s+Z([+-]?\d+\.?\d*)", cmd, re.I)
        if m:
            probe_z = float(m.group(1))
            self._wco[2] = self._mpos[2] - probe_z
            self._rx.put(b"ok\r\n")
            return

        # Zero work position G92
        if cmd.upper().startswith("G92"):
            x_m = re.search(r"X([+-]?\d+\.?\d*)", cmd, re.I)
            y_m = re.search(r"Y([+-]?\d+\.?\d*)", cmd, re.I)
            z_m = re.search(r"Z([+-]?\d+\.?\d*)", cmd, re.I)
            if x_m:
                self._wco[0] = self._mpos[0] - float(x_m.group(1))
            if y_m:
                self._wco[1] = self._mpos[1] - float(y_m.group(1))
            if z_m:
                self._wco[2] = self._mpos[2] - float(z_m.group(1))
            self._rx.put(b"ok\r\n")
            return

        # Motion (G0/G1)
        m_g = re.search(r"G([01])\b", cmd, re.I)
        if m_g:
            x_m = re.search(r"X([+-]?\d+\.?\d*)", cmd, re.I)
            y_m = re.search(r"Y([+-]?\d+\.?\d*)", cmd, re.I)
            z_m = re.search(r"Z([+-]?\d+\.?\d*)", cmd, re.I)
            f_m = re.search(r"F([+-]?\d+\.?\d*)", cmd, re.I)
            if x_m:
                self._mpos[0] = self._wco[0] + float(x_m.group(1))
            if y_m:
                self._mpos[1] = self._wco[1] + float(y_m.group(1))
            if z_m:
                self._mpos[2] = self._wco[2] + float(z_m.group(1))
            if f_m:
                self._feed = float(f_m.group(1))
            self._rx.put(b"ok\r\n")
            return

        # S command (spindle/laser)
        if re.match(r"^S\d+$", cmd, re.I):
            self._spindle = float(cmd[1:])
            self._rx.put(b"ok\r\n")
            return

        # Default: acknowledge
        self._rx.put(b"ok\r\n")

    def _handle_jog(self, params: str) -> None:
        rel = "G91" in params.upper()
        x_m = re.search(r"X([+-]?\d+\.?\d*)", params, re.I)
        y_m = re.search(r"Y([+-]?\d+\.?\d*)", params, re.I)
        z_m = re.search(r"Z([+-]?\d+\.?\d*)", params, re.I)
        f_m = re.search(r"F([+-]?\d+\.?\d*)", params, re.I)
        if f_m:
            self._feed = float(f_m.group(1))
        if rel:
            if x_m:
                self._mpos[0] = round(self._mpos[0] + float(x_m.group(1)), 3)
            if y_m:
                self._mpos[1] = round(self._mpos[1] + float(y_m.group(1)), 3)
            if z_m:
                self._mpos[2] = round(self._mpos[2] + float(z_m.group(1)), 3)
        else:
            if x_m:
                self._mpos[0] = float(x_m.group(1))
            if y_m:
                self._mpos[1] = float(y_m.group(1))
            if z_m:
                self._mpos[2] = float(z_m.group(1))
        self._rx.put(b"ok\r\n")

    # -- Serial interface ------------------------------------------------------

    def write(self, data: bytes) -> int:
        text = data.decode("ascii", errors="replace")
        # Split by newlines; real-time single-byte commands have no newline
        if text in ("\x18", "?", "~", "!"):
            self._handle(text)
        else:
            for line in text.splitlines():
                if line:
                    self._handle(line)
        return len(data)

    def readline(self) -> bytes:
        try:
            return self._rx.get(timeout=self.timeout)
        except queue.Empty:
            return b""

    def read(self, size: int = 1) -> bytes:
        try:
            return self._rx.get(timeout=self.timeout)
        except queue.Empty:
            return b""

    def flushInput(self) -> None:
        while not self._rx.empty():
            try:
                self._rx.get_nowait()
            except queue.Empty:
                break

    def close(self) -> None:
        self.is_open = False
