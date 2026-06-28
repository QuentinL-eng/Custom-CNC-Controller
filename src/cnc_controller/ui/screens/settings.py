"""Touchscreen settings, including SSH status and Wi-Fi configuration."""
from __future__ import annotations

from ..qt_compat import (
    Qt,
    QTimer,
    QEvent,
    QLabel,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QThread,
    QVBoxLayout,
    QWidget,
    Signal,
)
from ..theme import (
    C_BLUE,
    C_CARD_BORDER,
    C_DIM,
    C_GREEN,
    C_GREEN_BG,
    C_GREEN_BORDER,
    C_GREEN_TEXT,
    C_MUTED,
)
from ..widgets.touch_keyboard import TouchKeyboard
from ..motion import MotionMode
from ...network import NetworkManager, NetworkSnapshot, WifiNetwork
from ...update_status import UpdateManager, UpdateStatus


SECTIONS = [
    "Machine Profiles",
    "GRBL Settings ($)",
    "Display",
    "Units",
    "Network",
    "Updates",
    "Controller Config",
    "Diagnostics",
]


class NetworkTask(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        manager: NetworkManager,
        action: str,
        ssid: str = "",
        password: str = "",
        security: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._manager = manager
        self._action = action
        self._ssid = ssid
        self._password = password
        self._security = security

    def run(self) -> None:
        try:
            if self._action == "status":
                result = self._manager.snapshot()
            elif self._action == "scan":
                result = self._manager.scan_wifi()
            else:
                result = self._manager.connect_wifi(
                    self._ssid, self._password, self._security
                )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._password = ""


class UpdateTask(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, manager: UpdateManager, check_now: bool, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._check_now = check_now

    def run(self) -> None:
        try:
            result = (
                self._manager.check_now()
                if self._check_now
                else self._manager.status()
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


def _button(text: str, style: str = "btnSecondary", height: int = 48):
    button = QPushButton(text)
    button.setObjectName(style)
    button.setFixedHeight(height)
    return button


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


class SettingsScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._active_section = "Display"
        self._network = NetworkManager()
        self._network_task: NetworkTask | None = None
        self._updates = UpdateManager()
        self._update_task: UpdateTask | None = None
        self._selected_wifi: WifiNetwork | None = None
        self._build_ui()
        self._keyboard = TouchKeyboard(self, self._ctrl.motion)
        self._keyboard.opened.connect(self._keyboard_opened)
        self._keyboard.dismissed.connect(self._keyboard_dismissed)
        self._ctrl.motion.mode_changed.connect(
            lambda _mode: self._refresh_motion_buttons()
        )
        self._position_keyboard()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        self._root_layout = root

        nav = QFrame(self)
        nav.setObjectName("card")
        nav.setFixedWidth(240)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(3)
        self._nav_btns: list[QPushButton] = []
        for section in SECTIONS:
            button = QPushButton(section, nav)
            button.setFixedHeight(46)
            button.clicked.connect(
                lambda _checked=False, name=section: self._show_section(name)
            )
            self._nav_btns.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch()
        root.addWidget(nav)

        self._content_scroll = QScrollArea(self)
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none}"
        )
        self._content = QFrame(self._content_scroll)
        self._content.setObjectName("card")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 16, 16, 16)
        self._content_layout.setSpacing(12)
        self._content_scroll.setWidget(self._content)
        root.addWidget(self._content_scroll, 1)
        self._show_section(self._active_section)

    def _show_section(self, section: str) -> None:
        if hasattr(self, "_keyboard"):
            self._keyboard.hide_keyboard(clear_target=True)
        self._active_section = section
        self._refresh_nav()
        _clear(self._content_layout)
        title = QLabel(section.upper(), self._content)
        title.setObjectName("labelSection")
        self._content_layout.addWidget(title)
        if section == "Display":
            self._build_display()
        elif section == "Network":
            self._build_network()
        elif section == "Updates":
            self._build_updates()
        else:
            self._build_placeholder(section)

    def _build_display(self) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Theme", self._content))
        row.addStretch()
        value = QLabel("Light · high-brightness shop display", self._content)
        value.setStyleSheet(f"color:{C_MUTED};background:transparent;border:none")
        row.addWidget(value)
        self._content_layout.addLayout(row)

        timeout = QHBoxLayout()
        timeout.addWidget(QLabel("Screen timeout", self._content))
        timeout.addStretch()
        timeout.addWidget(QLabel("Never", self._content))
        self._content_layout.addLayout(timeout)

        motion_card = QFrame(self._content)
        motion_card.setObjectName("card")
        motion_layout = QHBoxLayout(motion_card)
        motion_layout.setContentsMargins(12, 10, 12, 10)
        motion_text = QVBoxLayout()
        motion_title = QLabel("Motion", motion_card)
        motion_title.setStyleSheet(
            "font-size:15px;font-weight:700;background:transparent;border:none"
        )
        motion_note = QLabel("30 FPS · optimized for Raspberry Pi 3B", motion_card)
        motion_note.setStyleSheet(
            f"color:{C_MUTED};font-size:12px;background:transparent;border:none"
        )
        motion_text.addWidget(motion_title)
        motion_text.addWidget(motion_note)
        motion_layout.addLayout(motion_text, 1)
        self._motion_buttons: dict[MotionMode, QPushButton] = {}
        for mode, label in (
            (MotionMode.STANDARD, "Standard"),
            (MotionMode.REDUCED, "Reduced"),
            (MotionMode.OFF, "Off"),
        ):
            button = _button(label, height=44)
            button.setFixedWidth(92)
            button.clicked.connect(
                lambda _checked=False, selected=mode: self._set_motion_mode(
                    selected
                )
            )
            self._motion_buttons[mode] = button
            motion_layout.addWidget(button)
        self._content_layout.addWidget(motion_card)
        self._refresh_motion_buttons()

        self._content_layout.addStretch()
        sleep = _button("Sleep", height=54)
        sleep.clicked.connect(self._sleep_display)
        self._content_layout.addWidget(sleep)

    def _set_motion_mode(self, mode: MotionMode) -> None:
        self._ctrl.set_motion_mode(mode)
        self._refresh_motion_buttons()

    def _refresh_motion_buttons(self) -> None:
        if not hasattr(self, "_motion_buttons"):
            return
        selected = self._ctrl.motion.mode
        for mode, button in self._motion_buttons.items():
            button.setObjectName(
                "btnPrimary" if mode is selected else "btnSecondary"
            )
            button.style().unpolish(button)
            button.style().polish(button)

    def _build_network(self) -> None:
        addresses = QFrame(self._content)
        addresses.setObjectName("card")
        address_layout = QVBoxLayout(addresses)
        address_layout.setContentsMargins(13, 11, 13, 11)
        address_layout.setSpacing(5)
        self._network_state = QLabel("Reading network addresses…", addresses)
        self._network_state.setStyleSheet(
            "font-size:16px;font-weight:700;background:transparent;border:none"
        )
        address_layout.addWidget(self._network_state)
        self._ethernet_ip = QLabel("Ethernet  —", addresses)
        self._wifi_ip = QLabel("Wi-Fi  —", addresses)
        self._ssh_command = QLabel("SSH  —", addresses)
        self._ssh_command.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._ssh_command.setStyleSheet(
            f"color:{C_BLUE};font-size:15px;font-weight:700;"
            "font-family:monospace;background:transparent;border:none"
        )
        address_layout.addWidget(self._ethernet_ip)
        address_layout.addWidget(self._wifi_ip)
        address_layout.addWidget(self._ssh_command)
        self._content_layout.addWidget(addresses)

        controls = QHBoxLayout()
        refresh = _button("Refresh IP", height=46)
        refresh.clicked.connect(self._refresh_network)
        controls.addWidget(refresh)
        self._scan_btn = _button("Scan Wi-Fi", "btnPrimary", 46)
        self._scan_btn.clicked.connect(self._scan_wifi)
        controls.addWidget(self._scan_btn)
        self._content_layout.addLayout(controls)

        connection = QFrame(self._content)
        connection.setObjectName("card")
        connection_layout = QVBoxLayout(connection)
        connection_layout.setContentsMargins(12, 10, 12, 10)
        connection_layout.setSpacing(7)
        self._ssid = QLineEdit(connection)
        self._ssid.setPlaceholderText("Select a network below or enter SSID")
        self._ssid.setFixedHeight(44)
        self._ssid.installEventFilter(self)
        self._password = QLineEdit(connection)
        self._password.setPlaceholderText("Wi-Fi password")
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setFixedHeight(44)
        self._password.installEventFilter(self)
        connect = _button("Connect", "btnPrimary", 50)
        connect.clicked.connect(self._connect_wifi)
        fields = QHBoxLayout()
        fields.addWidget(self._ssid, 3)
        fields.addWidget(self._password, 3)
        fields.addWidget(connect, 2)
        connection_layout.addLayout(fields)
        self._content_layout.addWidget(connection)

        self._wifi_scroll = QScrollArea(self._content)
        self._wifi_scroll.setWidgetResizable(True)
        self._wifi_host = QWidget(self._wifi_scroll)
        self._wifi_layout = QVBoxLayout(self._wifi_host)
        self._wifi_layout.setContentsMargins(0, 0, 4, 0)
        self._wifi_layout.setSpacing(6)
        hint = QLabel("Tap Scan Wi-Fi to list nearby networks.", self._wifi_host)
        hint.setStyleSheet(f"color:{C_DIM};background:transparent;border:none")
        self._wifi_layout.addWidget(hint)
        self._wifi_layout.addStretch()
        self._wifi_scroll.setWidget(self._wifi_host)
        self._content_layout.addWidget(self._wifi_scroll, 1)
        self._refresh_network()

    def _build_updates(self) -> None:
        summary = QFrame(self._content)
        summary.setObjectName("card")
        layout = QHBoxLayout(summary)
        layout.setContentsMargins(15, 12, 15, 12)
        count_box = QVBoxLayout()
        count_label = QLabel("SUCCESSFUL PULLS", summary)
        count_label.setObjectName("labelSection")
        self._pull_count = QLabel("—", summary)
        self._pull_count.setStyleSheet(
            f"color:{C_GREEN};font-size:46px;font-weight:700;"
            "background:transparent;border:none"
        )
        count_box.addWidget(count_label)
        count_box.addWidget(self._pull_count)
        layout.addLayout(count_box, 1)
        details = QVBoxLayout()
        self._last_pull = QLabel("Last pull  —", summary)
        self._last_check = QLabel("Last check  —", summary)
        self._current_commit = QLabel("Commit  —", summary)
        for label in (
            self._last_pull,
            self._last_check,
            self._current_commit,
        ):
            label.setStyleSheet(
                "font-size:14px;font-weight:600;background:transparent;border:none"
            )
            details.addWidget(label)
        layout.addLayout(details, 2)
        self._content_layout.addWidget(summary)

        self._update_message = QLabel(
            "Reading update status…", self._content
        )
        self._update_message.setWordWrap(True)
        self._update_message.setStyleSheet(
            f"background:{C_GREEN_BG};color:{C_GREEN_TEXT};"
            f"border:1px solid {C_GREEN_BORDER};border-radius:10px;"
            "padding:12px;font-size:14px;font-weight:700"
        )
        self._content_layout.addWidget(self._update_message)
        self._content_layout.addStretch()
        self._check_updates = _button(
            "Check GitHub Now", "btnPrimary", 58
        )
        self._check_updates.clicked.connect(
            lambda: self._refresh_updates(check_now=True)
        )
        self._content_layout.addWidget(self._check_updates)
        self._refresh_updates()

    def _build_placeholder(self, section: str) -> None:
        text = QLabel(
            f"{section} controls will be added as the controller hardware is configured.",
            self._content,
        )
        text.setWordWrap(True)
        text.setStyleSheet(
            f"color:{C_MUTED};font-size:15px;background:transparent;border:none"
        )
        self._content_layout.addWidget(text)
        self._content_layout.addStretch()

    def _refresh_nav(self) -> None:
        for button, section in zip(self._nav_btns, SECTIONS):
            if section == self._active_section:
                button.setStyleSheet(
                    f"QPushButton{{background:{C_GREEN_BG};color:{C_GREEN_TEXT};"
                    f"border:1px solid {C_GREEN_BORDER};border-radius:9px;"
                    "font-size:15px;font-weight:700;text-align:left;padding-left:14px}"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{C_MUTED};border:none;"
                    "font-size:15px;font-weight:600;text-align:left;padding-left:14px}"
                )

    def _start_network_task(
        self,
        action: str,
        ssid: str = "",
        password: str = "",
        security: str = "",
    ):
        if self._network_task and self._network_task.isRunning():
            return
        self._network_task = NetworkTask(
            self._network, action, ssid, password, security, self
        )
        self._network_task.failed.connect(self._network_failed)
        if action == "scan":
            self._network_task.completed.connect(self._show_wifi_networks)
        else:
            self._network_task.completed.connect(self._show_network_snapshot)
        self._network_task.start()

    def _refresh_network(self) -> None:
        if hasattr(self, "_network_state"):
            self._network_state.setText("Reading network addresses…")
        self._start_network_task("status")

    def _scan_wifi(self) -> None:
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("Scanning…")
        self._start_network_task("scan")

    def _connect_wifi(self) -> None:
        ssid = self._ssid.text().strip()
        password = self._password.text()
        if not ssid:
            QMessageBox.warning(self, "Wi-Fi", "Select or enter a network name.")
            return
        selected = self._selected_wifi
        security = (
            selected.security
            if selected is not None and selected.ssid == ssid
            else ("WPA2" if password else "Open")
        )
        self._network_state.setText(f"Connecting to {ssid}…")
        self._start_network_task("connect", ssid, password, security)
        self._password.clear()

    def _show_network_snapshot(self, snapshot: NetworkSnapshot) -> None:
        if self._active_section != "Network":
            return
        addresses = {item.name: item.address for item in snapshot.interfaces}
        ethernet = next(
            (value for name, value in addresses.items() if name.startswith(("eth", "en"))),
            "—",
        )
        wifi = next(
            (value for name, value in addresses.items() if name.startswith(("wlan", "wlp"))),
            "—",
        )
        self._network_state.setText(f"{snapshot.hostname} · SSH ready")
        self._ethernet_ip.setText(f"Ethernet  {ethernet}")
        self._wifi_ip.setText(f"Wi-Fi  {wifi}")
        self._ssh_command.setText(f"SSH  {snapshot.ssh_command}")

    def _show_wifi_networks(self, networks: list[WifiNetwork]) -> None:
        if self._active_section != "Network":
            return
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("Scan Wi-Fi")
        _clear(self._wifi_layout)
        if not networks:
            self._wifi_layout.addWidget(QLabel("No Wi-Fi networks found.", self._wifi_host))
        for network in networks:
            lock = "Secured" if network.security != "Open" else "Open"
            active = " · CONNECTED" if network.connected else ""
            button = _button(
                f"{network.ssid}   {network.signal}% · {lock}{active}",
                "btnPrimary" if network.connected else "btnSecondary",
                46,
            )
            button.clicked.connect(
                lambda _checked=False, item=network: self._select_wifi(item)
            )
            self._wifi_layout.addWidget(button)
        self._wifi_layout.addStretch()

    def _select_wifi(self, network: WifiNetwork) -> None:
        self._selected_wifi = network
        self._ssid.setText(network.ssid)
        self._password.setFocus()

    def _network_failed(self, message: str) -> None:
        if self._active_section != "Network":
            return
        if hasattr(self, "_scan_btn"):
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Scan Wi-Fi")
        if hasattr(self, "_network_state"):
            self._network_state.setText("Network action failed")
        QMessageBox.critical(self, "Network", message)

    def _refresh_updates(self, check_now: bool = False) -> None:
        if self._update_task and self._update_task.isRunning():
            return
        if hasattr(self, "_check_updates"):
            self._check_updates.setEnabled(False)
            self._check_updates.setText(
                "Checking GitHub…" if check_now else "Reading status…"
            )
        self._update_task = UpdateTask(
            self._updates, check_now, self
        )
        self._update_task.completed.connect(self._show_update_status)
        self._update_task.failed.connect(self._update_failed)
        self._update_task.start()

    def _show_update_status(self, status: UpdateStatus) -> None:
        if self._active_section != "Updates":
            return
        self._pull_count.setText(str(status.pull_count))
        self._last_pull.setText(f"Last pull  {status.last_pull_display}")
        self._last_check.setText(f"Last check  {status.last_check_display}")
        commit = status.current_commit or "Unknown"
        self._current_commit.setText(f"Commit  {commit}")
        self._update_message.setText(status.message)
        self._check_updates.setEnabled(True)
        self._check_updates.setText("Check GitHub Now")

    def _update_failed(self, message: str) -> None:
        if self._active_section != "Updates":
            return
        self._update_message.setText(f"Update check failed: {message}")
        self._check_updates.setEnabled(True)
        self._check_updates.setText("Check GitHub Now")

    def _sleep_display(self) -> None:
        import sys

        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        else:
            import subprocess

            subprocess.run(
                ["xset", "dpms", "force", "off"],
                capture_output=True,
                check=False,
            )

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("SELECT", "setting")
        self._ctrl.rail.set_enc2("ADJUST", "value")
        if self._active_section == "Network":
            self._refresh_network()
        elif self._active_section == "Updates":
            self._refresh_updates()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            if watched is getattr(self, "_ssid", None):
                self._keyboard.show_for(self._ssid, "Wi-Fi network name")
            elif watched is getattr(self, "_password", None):
                self._keyboard.show_for(self._password, "Wi-Fi password")
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_keyboard()

    def _position_keyboard(self) -> None:
        if hasattr(self, "_keyboard"):
            self._keyboard.setGeometry(
                0,
                max(0, self.height() - self._keyboard.HEIGHT),
                self.width(),
                self._keyboard.HEIGHT,
            )

    def _keyboard_opened(self, target: QLineEdit) -> None:
        # Make the unobstructed area real layout space, then scroll the active
        # field into it. This prevents the keyboard from covering input text.
        self._root_layout.setContentsMargins(
            14, 14, 14, self._keyboard.HEIGHT + 14
        )
        QTimer.singleShot(
            0,
            lambda: self._content_scroll.ensureWidgetVisible(target, 20, 20),
        )

    def _keyboard_dismissed(self) -> None:
        self._root_layout.setContentsMargins(14, 14, 14, 14)
        self._content_scroll.verticalScrollBar().setValue(0)
