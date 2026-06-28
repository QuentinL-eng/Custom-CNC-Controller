"""Top 46 px status bar — always visible across all screens."""
from __future__ import annotations

import time

from ..qt_compat import (
    Qt, QTimer, QWidget, QLabel, QFrame, QHBoxLayout, QSizePolicy,
)
from ..theme import (
    C_TEXT, C_MUTED, C_DIM, C_BORDER, C_CARD_BORDER, C_STATUS_BAR,
    C_GREEN, C_GREEN_BG, C_GREEN_BORDER, C_GREEN_TEXT,
    C_BLUE, C_BLUE_BG, C_BLUE_BORDER, C_BLUE_TEXT,
    STATUS_BAR_H,
)
from ...grbl_worker import GrblStatus
from ...models import MachineMode


def _sep(parent: QWidget) -> QFrame:
    line = QFrame(parent)
    line.setFixedSize(1, 22)
    line.setStyleSheet(f"background: {C_BORDER}; border: none;")
    return line


class StatusBar(QFrame):
    """1024×46 px persistent header bar."""

    def __init__(self, parent: QWidget | None = None, motion=None):
        super().__init__(parent)
        self._motion = motion
        self._last_state = ""
        self.setObjectName("statusBar")
        self.setFixedHeight(STATUS_BAR_H)
        self.setStyleSheet(
            f"QFrame#statusBar {{ background: {C_STATUS_BAR}; "
            f"border-bottom: 1px solid {C_BORDER}; border-radius: 0; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        # Mode badge
        self._badge = QLabel("CNC", self)
        self._badge.setObjectName("badgeCNC")
        self._badge.setFixedHeight(30)
        layout.addWidget(self._badge)

        # State indicator dot + text
        self._dot = QLabel("●", self)
        self._dot.setStyleSheet(f"color: {C_DIM}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(self._dot)

        self._state_label = QLabel("Disconnected", self)
        self._state_label.setStyleSheet(
            f"color: {C_TEXT}; font-size: 14px; font-weight: 600; background: transparent; border: none;"
        )
        layout.addWidget(self._state_label)

        layout.addWidget(_sep(self))

        # Connection label
        self._conn_label = QLabel("GRBL · —", self)
        self._conn_label.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        layout.addWidget(self._conn_label)

        layout.addStretch()

        # Units toggle (display only — clicking handled by app)
        self._units_frame = QFrame(self)
        self._units_frame.setStyleSheet(
            f"QFrame {{ border: 1px solid {C_CARD_BORDER}; border-radius: 7px; background: transparent; }}"
        )
        ul = QHBoxLayout(self._units_frame)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.setSpacing(0)
        self._mm_btn = QLabel("mm", self._units_frame)
        self._mm_btn.setAlignment(Qt.AlignCenter)
        self._mm_btn.setFixedSize(42, 30)
        self._mm_btn.setStyleSheet(
            f"QLabel {{ background: {C_GREEN}; color: white; font-size: 13px; "
            f"font-weight: 700; border-radius: 6px; }}"
        )
        self._in_btn = QLabel("in", self._units_frame)
        self._in_btn.setAlignment(Qt.AlignCenter)
        self._in_btn.setFixedSize(36, 30)
        self._in_btn.setStyleSheet(
            f"QLabel {{ background: white; color: {C_MUTED}; font-size: 13px; font-weight: 700; }}"
        )
        ul.addWidget(self._mm_btn)
        ul.addWidget(self._in_btn)
        layout.addWidget(self._units_frame)

        # Clock
        self._clock = QLabel("", self)
        self._clock.setStyleSheet(
            f"color: {C_TEXT}; font-size: 14px; font-weight: 600; background: transparent; border: none;"
        )
        layout.addWidget(self._clock)

        # Clock timer
        timer = QTimer(self)
        timer.timeout.connect(self._update_clock)
        timer.start(10_000)
        self._update_clock()

        self._mode = MachineMode.CNC

    # ------------------------------------------------------------------
    def set_mode(self, mode: MachineMode) -> None:
        self._mode = mode
        if mode is MachineMode.LASER:
            self._badge.setText("LASER")
            self._badge.setObjectName("badgeLASER")
            self._badge.setStyleSheet(
                f"color: {C_BLUE_TEXT}; background: {C_BLUE_BG}; "
                f"border: 1px solid {C_BLUE_BORDER}; border-radius: 6px; "
                f"font-size: 13px; font-weight: 700; padding: 5px 10px;"
            )
        else:
            self._badge.setText("CNC")
            self._badge.setStyleSheet(
                f"color: {C_GREEN_TEXT}; background: {C_GREEN_BG}; "
                f"border: 1px solid {C_GREEN_BORDER}; border-radius: 6px; "
                f"font-size: 13px; font-weight: 700; padding: 5px 10px;"
            )

    def set_status(self, status: GrblStatus) -> None:
        state_changed = status.state != self._last_state
        self._last_state = status.state
        dot_color = status.state_color
        self._dot.setStyleSheet(
            f"color: {dot_color}; font-size: 10px; background: transparent; border: none;"
        )
        self._state_label.setText(status.state)
        if status.is_connected:
            self._conn_label.setText("GRBL · Connected")
        else:
            self._conn_label.setText("GRBL · —")

        if state_changed and self._motion is not None:
            self._motion.pulse(self._state_label)

    def set_job_name(self, name: str) -> None:
        self._conn_label.setText(name or "GRBL · Connected")

    def _update_clock(self) -> None:
        self._clock.setText(time.strftime("%H:%M"))
