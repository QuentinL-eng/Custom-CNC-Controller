"""Diagnostics screen — GRBL console, $-settings, live state, alarm history."""
from __future__ import annotations

import re

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QPlainTextEdit, QScrollArea,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_BLUE, C_RED, C_BTN_2ND, C_RED_BG, C_RED_BORDER,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus


# Matches a GRBL setting line such as "$110=2000.000"
_SETTING_RE = re.compile(r"^\$(\d+)=(.+)$")


def parse_setting_line(line: str) -> tuple[str, str] | None:
    """Parse a GRBL ``$N=value`` setting line.

    Returns a ``(key, value)`` tuple like ``("$110", "2000.000")`` or
    ``None`` if the line is not a setting line. Pure helper for testing.
    """
    m = _SETTING_RE.match(line.strip())
    if not m:
        return None
    return (f"${m.group(1)}", m.group(2).strip())


def _kv(key: str, val: str, parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet("background: transparent; border: none;")
    rl = QHBoxLayout(f)
    rl.setContentsMargins(0, 5, 0, 5)
    k = QLabel(key, f)
    k.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;")
    v = QLabel(val, f)
    v.setStyleSheet(f"color: {C_TEXT}; font-size: 14px; font-weight: 700; background: transparent; border: none;")
    rl.addWidget(k)
    rl.addStretch()
    rl.addWidget(v)
    f._val = v
    return f


def _hdiv(parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C_DIVIDER}; border: none;")
    return f


class DiagnosticsScreen(QWidget):
    """Global diagnostics: GRBL console, settings, live state, alarms."""

    MAX_RECENT = 10
    MAX_ALARMS = 12

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = controller
        self._connected_signal = False
        self._recent: list[str] = []
        self._alarms: list[str] = []
        self._settings: dict[str, str] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._build_console(), 1)
        root.addWidget(self._build_sidebar())

    def _build_console(self) -> QWidget:
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        sec = QLabel("GRBL CONSOLE", left)
        sec.setObjectName("labelSection")
        ll.addWidget(sec)

        # Console log
        self._log = QPlainTextEdit(left)
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet(
            f"QPlainTextEdit {{ background: {C_CARD}; color: {C_TEXT}; "
            f"border: 1px solid {C_CARD_BORDER}; border-radius: {CARD_RADIUS}px; "
            f"font-family: 'DejaVu Sans Mono', 'Consolas', monospace; font-size: 13px; "
            f"padding: 8px; }}"
        )
        ll.addWidget(self._log, 1)

        # Command input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._cmd_input = QLineEdit(left)
        self._cmd_input.setPlaceholderText("Type a GRBL command…")
        self._cmd_input.setFixedHeight(48)
        self._cmd_input.setStyleSheet(
            f"QLineEdit {{ background: {C_CARD}; color: {C_TEXT}; "
            f"border: 1px solid {C_CARD_BORDER}; border-radius: {BTN_RADIUS}px; "
            f"font-family: 'DejaVu Sans Mono', 'Consolas', monospace; font-size: 15px; "
            f"padding: 0 12px; }}"
        )
        self._cmd_input.returnPressed.connect(self._send_command)
        input_row.addWidget(self._cmd_input, 1)

        send_btn = QPushButton("Send", left)
        send_btn.setObjectName("btnPrimary")
        send_btn.setFixedSize(96, 48)
        send_btn.clicked.connect(self._send_command)
        input_row.addWidget(send_btn)
        ll.addLayout(input_row)

        # Quick-action buttons row
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        read_btn = QPushButton("Read $$", left)
        read_btn.setObjectName("btnSecondary")
        read_btn.setFixedHeight(44)
        read_btn.clicked.connect(self._read_settings)
        quick_row.addWidget(read_btn)

        clear_btn = QPushButton("Clear log", left)
        clear_btn.setObjectName("btnSecondary")
        clear_btn.setFixedHeight(44)
        clear_btn.clicked.connect(self._log.clear)
        quick_row.addWidget(clear_btn)

        connect_btn = QPushButton("Connect", left)
        connect_btn.setObjectName("btnSecondary")
        connect_btn.setFixedHeight(44)
        connect_btn.clicked.connect(self._reconnect)
        quick_row.addWidget(connect_btn)

        disconnect_btn = QPushButton("Disconnect", left)
        disconnect_btn.setObjectName("btnSecondary")
        disconnect_btn.setFixedHeight(44)
        disconnect_btn.clicked.connect(self._disconnect)
        quick_row.addWidget(disconnect_btn)
        ll.addLayout(quick_row)

        return left

    def _build_sidebar(self) -> QWidget:
        right = QWidget(self)
        right.setFixedWidth(312)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        # --- Live state card ---
        state_card = QFrame(right)
        state_card.setObjectName("card")
        scl = QVBoxLayout(state_card)
        scl.setContentsMargins(13, 13, 13, 13)
        scl.setSpacing(0)

        sec = QLabel("LIVE STATE", state_card)
        sec.setObjectName("labelSection")
        sec.setContentsMargins(0, 0, 0, 8)
        scl.addWidget(sec)

        self._state_row = _kv("Connection", "Disconnected", state_card)
        scl.addWidget(self._state_row)
        scl.addWidget(_hdiv(state_card))
        self._mpos_row = _kv("Machine pos", "—", state_card)
        scl.addWidget(self._mpos_row)
        scl.addWidget(_hdiv(state_card))
        self._wpos_row = _kv("Work pos", "—", state_card)
        scl.addWidget(self._wpos_row)
        scl.addWidget(_hdiv(state_card))
        self._fs_row = _kv("Feed / Spindle", "—", state_card)
        scl.addWidget(self._fs_row)
        scl.addWidget(_hdiv(state_card))
        self._ov_row = _kv("Overrides %", "100 / 100 / 100", state_card)
        scl.addWidget(self._ov_row)
        scl.addWidget(_hdiv(state_card))
        self._probe_row = _kv("Probe", "—", state_card)
        scl.addWidget(self._probe_row)
        rl.addWidget(state_card)

        # --- Tabs: Settings / Alarms / Recent in a scroll area ---
        scroll = QScrollArea(right)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_body = QWidget(scroll)
        sbl = QVBoxLayout(scroll_body)
        sbl.setContentsMargins(0, 0, 0, 0)
        sbl.setSpacing(10)

        # $-settings card
        settings_card = QFrame(scroll_body)
        settings_card.setObjectName("card")
        setl = QVBoxLayout(settings_card)
        setl.setContentsMargins(13, 13, 13, 13)
        setl.setSpacing(0)
        ssec = QLabel("$ SETTINGS", settings_card)
        ssec.setObjectName("labelSection")
        ssec.setContentsMargins(0, 0, 0, 8)
        setl.addWidget(ssec)
        self._settings_lyt = setl
        self._settings_empty = QLabel("Tap “Read $$” to load settings.", settings_card)
        self._settings_empty.setWordWrap(True)
        self._settings_empty.setStyleSheet(
            f"color: {C_DIM}; font-size: 13px; background: transparent; border: none;"
        )
        setl.addWidget(self._settings_empty)
        self._setting_rows: list[QFrame] = []
        sbl.addWidget(settings_card)

        # Alarm history card
        alarm_card = QFrame(scroll_body)
        alarm_card.setObjectName("card")
        al = QVBoxLayout(alarm_card)
        al.setContentsMargins(13, 13, 13, 13)
        al.setSpacing(0)
        asec = QLabel("ALARM HISTORY", alarm_card)
        asec.setObjectName("labelSection")
        asec.setContentsMargins(0, 0, 0, 8)
        al.addWidget(asec)
        self._alarm_lyt = al
        self._alarm_empty = QLabel("No alarms recorded.", alarm_card)
        self._alarm_empty.setStyleSheet(
            f"color: {C_DIM}; font-size: 13px; background: transparent; border: none;"
        )
        al.addWidget(self._alarm_empty)
        self._alarm_rows: list[QWidget] = []
        sbl.addWidget(alarm_card)

        # Recent commands card
        recent_card = QFrame(scroll_body)
        recent_card.setObjectName("card")
        rcl = QVBoxLayout(recent_card)
        rcl.setContentsMargins(13, 13, 13, 13)
        rcl.setSpacing(0)
        rsec = QLabel("RECENT COMMANDS", recent_card)
        rsec.setObjectName("labelSection")
        rsec.setContentsMargins(0, 0, 0, 8)
        rcl.addWidget(rsec)
        self._recent_lyt = rcl
        self._recent_empty = QLabel("No commands sent yet.", recent_card)
        self._recent_empty.setStyleSheet(
            f"color: {C_DIM}; font-size: 13px; background: transparent; border: none;"
        )
        rcl.addWidget(self._recent_empty)
        self._recent_rows: list[QWidget] = []
        sbl.addWidget(recent_card)

        sbl.addStretch()
        scroll.setWidget(scroll_body)
        rl.addWidget(scroll, 1)

        return right

    # ------------------------------------------------------------------
    # Console / command handling
    # ------------------------------------------------------------------

    def _send_command(self) -> None:
        text = self._cmd_input.text().strip()
        if not text:
            return
        w = self._ctrl.worker
        if w is not None:
            w.send_command(text)
        self.append_sent(text)
        self._push_recent(text)
        self._cmd_input.clear()

    def _read_settings(self) -> None:
        w = self._ctrl.worker
        if w is not None:
            w.send_command("$$")
        self.append_sent("$$")
        self._push_recent("$$")

    def _reconnect(self) -> None:
        if hasattr(self._ctrl, "reconnect_serial"):
            self._ctrl.reconnect_serial()

    def _disconnect(self) -> None:
        if hasattr(self._ctrl, "disconnect_serial"):
            self._ctrl.disconnect_serial()

    def append_response(self, line: str) -> None:
        """Append an incoming GRBL line to the console log."""
        line = (line or "").rstrip("\r\n")
        if not line:
            return
        self._log.appendPlainText(f"< {line}")
        kv = parse_setting_line(line)
        if kv is not None:
            self._settings[kv[0]] = kv[1]
            self._refresh_settings()

    def append_sent(self, line: str) -> None:
        """Append an outgoing command to the console log."""
        line = (line or "").rstrip("\r\n")
        if not line:
            return
        self._log.appendPlainText(f"> {line}")

    # ------------------------------------------------------------------
    # Recent commands
    # ------------------------------------------------------------------

    def _push_recent(self, cmd: str) -> None:
        self._recent.insert(0, cmd)
        del self._recent[self.MAX_RECENT:]
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        for row in self._recent_rows:
            row.deleteLater()
        self._recent_rows.clear()
        self._recent_empty.setVisible(not self._recent)
        for cmd in self._recent:
            lbl = QLabel(cmd, self)
            lbl.setStyleSheet(
                f"color: {C_TEXT}; font-size: 13px; "
                f"font-family: 'DejaVu Sans Mono', 'Consolas', monospace; "
                f"background: transparent; border: none; padding: 3px 0;"
            )
            self._recent_lyt.addWidget(lbl)
            self._recent_rows.append(lbl)

    # ------------------------------------------------------------------
    # $-settings rendering
    # ------------------------------------------------------------------

    def _refresh_settings(self) -> None:
        for row in self._setting_rows:
            row.deleteLater()
        self._setting_rows.clear()
        self._settings_empty.setVisible(not self._settings)
        for key in sorted(self._settings, key=lambda k: int(k.lstrip("$"))):
            row = _kv(key, self._settings[key], self)
            self._settings_lyt.addWidget(row)
            self._setting_rows.append(row)

    # ------------------------------------------------------------------
    # Alarm history
    # ------------------------------------------------------------------

    def add_alarm(self, msg: str) -> None:
        """Record an alarm/error message in the in-memory history."""
        msg = (msg or "").strip()
        if not msg:
            return
        self._alarms.insert(0, msg)
        del self._alarms[self.MAX_ALARMS:]
        self._refresh_alarms()

    def _refresh_alarms(self) -> None:
        for row in self._alarm_rows:
            row.deleteLater()
        self._alarm_rows.clear()
        self._alarm_empty.setVisible(not self._alarms)
        for msg in self._alarms:
            lbl = QLabel(msg, self)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {C_RED}; background: {C_RED_BG}; border: 1px solid {C_RED_BORDER}; "
                f"border-radius: 7px; font-size: 13px; font-weight: 600; padding: 6px 9px;"
            )
            self._alarm_lyt.addWidget(lbl)
            self._alarm_rows.append(lbl)

    # ------------------------------------------------------------------
    # Live state
    # ------------------------------------------------------------------

    def on_status(self, status: GrblStatus) -> None:
        self._state_row._val.setText(status.state)
        self._state_row._val.setStyleSheet(
            f"color: {status.state_color}; font-size: 14px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        self._mpos_row._val.setText(
            f"{status.mpos[0]:.3f}  {status.mpos[1]:.3f}  {status.mpos[2]:.3f}"
        )
        self._wpos_row._val.setText(
            f"{status.wpos[0]:.3f}  {status.wpos[1]:.3f}  {status.wpos[2]:.3f}"
        )
        self._fs_row._val.setText(f"{status.feed:.0f} / {status.spindle:.0f}")
        ov = status.overrides
        self._ov_row._val.setText(f"{ov[0]} / {ov[1]} / {ov[2]}")
        if status.probe_triggered:
            pp = status.probe_pos
            self._probe_row._val.setText(
                f"PRB {pp[0]:.3f} {pp[1]:.3f} {pp[2]:.3f}"
            )
        else:
            self._probe_row._val.setText("not triggered")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self) -> None:
        if hasattr(self._ctrl, "rail") and self._ctrl.rail is not None:
            try:
                self._ctrl.rail.set_enc1("SCROLL", "console")
                self._ctrl.rail.set_enc2("—", "idle")
            except Exception:
                pass
        w = self._ctrl.worker
        if w is not None and not self._connected_signal:
            try:
                w.response_received.connect(self.append_response)
                self._connected_signal = True
            except Exception:
                pass
