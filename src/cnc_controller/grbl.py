from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import MachineMode, MachineProfile


class SerialLike(Protocol):
    def write(self, data: bytes) -> int: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...


@dataclass
class GrblController:
    """Small GRBL command facade used by the touchscreen UI.

    The class is intentionally independent of pyserial so tests can use an
    in-memory serial object and the UI can inject a real serial connection.
    """

    profile: MachineProfile
    serial: SerialLike | None = None

    def connect(self) -> None:
        if self.serial is not None:
            return
        import serial

        self.serial = serial.Serial(self.profile.serial_port, self.profile.baud_rate, timeout=1)

    def close(self) -> None:
        if self.serial:
            self.serial.close()
            self.serial = None

    def send_line(self, command: str) -> str:
        if self.serial is None:
            raise RuntimeError("GRBL serial connection is not open")
        line = command.strip() + "\n"
        self.serial.write(line.encode("ascii"))
        return self.serial.readline().decode("ascii", errors="replace").strip()

    def set_mode(self, mode: MachineMode) -> str:
        return self.send_line("$32=1" if mode is MachineMode.LASER else "$32=0")

    def cycle_start(self) -> str:
        return self.send_line("~")

    def feed_hold(self) -> str:
        return self.send_line("!")

    def reset(self) -> str:
        if self.serial is None:
            raise RuntimeError("GRBL serial connection is not open")
        self.serial.write(b"\x18")
        return self.serial.readline().decode("ascii", errors="replace").strip()

    def jog(self, axis: str, distance_mm: float, feed_mm_min: float) -> str:
        axis = axis.upper()
        if axis not in {"X", "Y", "Z"}:
            raise ValueError(f"Unsupported jog axis: {axis}")
        return self.send_line(f"$J=G91 G21 {axis}{distance_mm:.3f} F{feed_mm_min:.0f}")

    def probe_z(self, depth_mm: float = -25.0, feed_mm_min: float = 80.0) -> str:
        return self.send_line(f"G38.2 Z{depth_mm:.3f} F{feed_mm_min:.0f}")
