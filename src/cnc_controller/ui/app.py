"""Main application window and controller.

Entry points:
    python -m cnc_controller.ui.app           # try real serial, fall back to mock
    python -m cnc_controller.ui.app --mock    # force mock serial
    python -m cnc_controller.ui.app --port /dev/ttyUSB0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .qt_compat import (
    Qt, QTimer, QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QApplication, QMainWindow, QSizePolicy, QKeyEvent,
)
from .theme import STYLESHEET, STATUS_BAR_H, ACTION_RAIL_W
from .motion import MotionController, MotionMode
from .widgets.status_bar import StatusBar
from .widgets.action_rail import ActionRail
from .screens.splash import SplashScreen
from .screens.home import HomeScreen
from .screens.cnc_mode import CncModeScreen
from .screens.laser_mode import LaserModeScreen
from .screens.file_browser import FileBrowserScreen
from .screens.probing import ProbingScreen
from .screens.safety_review import SafetyReviewScreen
from .screens.settings import SettingsScreen
from .screens.diagnostics import DiagnosticsScreen
from .screens.pcb_wizard import PcbWizardScreen
from .screens.tools import ToolsScreen
from .screens.materials import MaterialsScreen

from ..grbl_worker import GrblWorker, GrblStatus
from ..mock_serial import MockSerial
from ..models import MachineMode, MachineProfile
from ..jobs import JobFile
from ..profiles import load_profiles
from .. import history


CONFIG_PATH = Path(__file__).parents[3] / "config" / "machines.json"

_DEFAULT_PROFILE = MachineProfile(
    name="Default",
    work_area_mm=(300.0, 300.0, 80.0),
    probe_thickness_mm=15.0,
    max_feed_mm_min=3000.0,
    laser_s_min=0,
    laser_s_max=1000,
    safe_z_mm=5.0,
    homing_required=True,
    serial_port="/dev/ttyUSB0",
    baud_rate=115200,
)

SCREEN_NAMES = [
    "splash",
    "home",
    "cnc_mode",
    "laser_mode",
    "file_browser",
    "probing",
    "safety_review",
    "settings",
    "pcb",
    "diagnostics",
    "tools",
    "materials",
]


def _load_profile() -> MachineProfile:
    try:
        data = json.loads(CONFIG_PATH.read_text())
        m = data["machines"][0]
        return MachineProfile(
            name=m.get("name", "Machine"),
            work_area_mm=tuple(m["work_area_mm"]),
            probe_thickness_mm=m.get("probe_thickness_mm", 15.0),
            max_feed_mm_min=m.get("max_feed_mm_min", 3000.0),
            laser_s_min=m.get("laser_s_min", 0),
            laser_s_max=m.get("laser_s_max", 1000),
            safe_z_mm=m.get("safe_z_mm", 5.0),
            homing_required=m.get("homing_required", True),
            serial_port=m.get("serial_port", "/dev/ttyUSB0"),
            baud_rate=m.get("baud_rate", 115200),
        )
    except Exception:
        return _DEFAULT_PROFILE


def _load_all_profiles() -> list[MachineProfile]:
    try:
        profiles = load_profiles(CONFIG_PATH)
        if profiles:
            return profiles
    except Exception:
        pass
    return [_load_profile()]


# ---------------------------------------------------------------------------
# AppController — central hub
# ---------------------------------------------------------------------------

class AppController:
    """Holds shared state and drives navigation between screens.

    All screens receive a reference to this object so they can:
    - Access self.worker (GrblWorker)
    - Access self.profile (MachineProfile)
    - Call self.navigate_to / navigate_back
    - Access self.status_bar / self.rail
    """

    def __init__(self, window: "MainWindow"):
        self._win = window
        self.motion = window.motion
        self.profiles: list[MachineProfile] = _load_all_profiles()
        self.active_profile_index: int = 0
        self.profile: MachineProfile = self.profiles[0]
        self.worker: GrblWorker | None = None
        self.mode: MachineMode = MachineMode.CNC
        self.job_file: JobFile | None = None
        self._nav_stack: list[str] = ["home"]

    @property
    def status_bar(self) -> StatusBar:
        return self._win.status_bar

    @property
    def rail(self) -> ActionRail:
        return self._win.rail

    def navigate_to(self, screen: str) -> None:
        if screen not in SCREEN_NAMES:
            return
        self._nav_stack.append(screen)
        self._win.show_screen(screen, direction=1)

    def navigate_back(self) -> None:
        if len(self._nav_stack) > 1:
            self._nav_stack.pop()
        self._win.show_screen(self._nav_stack[-1], direction=-1)

    def set_motion_mode(self, mode: MotionMode | str) -> None:
        self.motion.set_mode(mode)

    def set_job_file(self, path: Path) -> None:
        from ..jobs import load_job_file
        try:
            self.job_file = load_job_file(path)
        except ValueError:
            self.job_file = None
            return
        try:
            history.add_recent(path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def set_profile(self, index: int) -> None:
        if not (0 <= index < len(self.profiles)):
            return
        self.active_profile_index = index
        self.profile = self.profiles[index]
        if self.worker is not None:
            # The worker keeps its own reference for jog/safe-Z calculations.
            self.worker._profile = self.profile
        self.status_bar.set_profile_name(self.profile.name)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def reconnect_serial(self) -> None:
        if self.worker is not None and hasattr(self.worker, "reconnect"):
            self.worker.reconnect()
        else:
            self._win.reinit_serial()

    def disconnect_serial(self) -> None:
        if self.worker is not None:
            self.worker.detach_serial()

    def connect_worker(self, serial_obj) -> None:
        if self.worker is None:
            self.worker = GrblWorker(self.profile, self._win)
            self.worker.status_updated.connect(self._win.on_status)
            self.worker.job_progress.connect(self._win.on_job_progress)
            self.worker.job_finished.connect(self._win.on_job_finished)
            self.worker.response_received.connect(self._win.on_response)
            self.worker.error_occurred.connect(self._win.on_error)
            self.worker.connected.connect(self._win.on_connected)
            self.worker.disconnected.connect(self._win.on_disconnected)
            if hasattr(self.worker, "alarm_raised"):
                self.worker.alarm_raised.connect(self._win.on_alarm)
            self.worker.start()
        self.worker.attach_serial(serial_obj)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, use_mock: bool = True, port: str | None = None):
        super().__init__()
        self.setWindowTitle("CNC·CTRL")
        self.setFixedSize(1024, 600)
        self.setStyleSheet(STYLESHEET)
        self.motion = MotionController(self)
        application = QApplication.instance()
        if application is not None:
            self.motion.install(application)

        # Optionally hide the OS title bar in fullscreen kiosk mode
        # self.setWindowFlags(Qt.FramelessWindowHint)

        self._reconnect_pending = False
        self._controller = AppController(self)
        self._build_ui()
        self._connect_rail()

        # Start splash then auto-connect
        self.show_screen("splash")
        QTimer.singleShot(500, lambda: self._splash.set_progress(30, "Connecting to GRBL…"))
        QTimer.singleShot(1200, lambda: self._init_serial(use_mock, port))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Status bar (top, 46 px)
        self.status_bar = StatusBar(central, self.motion)
        root.addWidget(self.status_bar)

        # Content row
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        # Stacked screens
        self._stack = QStackedWidget(central)
        content_row.addWidget(self._stack, 1)

        # Action rail (right, 104 px)
        self.rail = ActionRail(central)
        content_row.addWidget(self.rail)

        root.addLayout(content_row, 1)

        ctrl = self._controller

        # Build all screens
        self._splash = SplashScreen(self._stack)
        self._home = HomeScreen(ctrl, self._stack)
        self._cnc = CncModeScreen(ctrl, self._stack)
        self._laser = LaserModeScreen(ctrl, self._stack)
        self._files = FileBrowserScreen(ctrl, self._stack)
        self._probing = ProbingScreen(ctrl, self._stack)
        self._safety = SafetyReviewScreen(ctrl, self._stack)
        self._settings = SettingsScreen(ctrl, self._stack)
        self._diag = DiagnosticsScreen(ctrl, self._stack)
        self._pcb = PcbWizardScreen(ctrl, self._stack)
        self._tools = ToolsScreen(ctrl, self._stack)
        self._materials = MaterialsScreen(ctrl, self._stack)

        self._screens: dict[str, QWidget] = {
            "splash": self._splash,
            "home": self._home,
            "cnc_mode": self._cnc,
            "laser_mode": self._laser,
            "file_browser": self._files,
            "probing": self._probing,
            "safety_review": self._safety,
            "settings": self._settings,
            "pcb": self._pcb,
            "diagnostics": self._diag,
            "tools": self._tools,
            "materials": self._materials,
        }

        for screen in self._screens.values():
            self._stack.addWidget(screen)

        # Reflect the active profile in the status bar from the start.
        self.status_bar.set_profile_name(ctrl.profile.name)

    def _make_placeholder(self, title: str, subtitle: str) -> QWidget:
        w = QWidget(self._stack)
        lyt = QVBoxLayout(w)
        lyt.setAlignment(Qt.AlignCenter)
        t = QLabel(title, w)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size: 26px; font-weight: 700; background: transparent; border: none;")
        s = QLabel(subtitle, w)
        s.setAlignment(Qt.AlignCenter)
        s.setStyleSheet("font-size: 15px; color: #5c636b; background: transparent; border: none;")
        lyt.addWidget(t)
        lyt.addWidget(s)
        return w

    def _connect_rail(self) -> None:
        self.rail.home_btn.clicked.connect(lambda: self._controller.navigate_to("home"))
        self.rail.back_btn.clicked.connect(self._controller.navigate_back)

    # ------------------------------------------------------------------
    # Screen navigation
    # ------------------------------------------------------------------

    def show_screen(self, name: str, direction: int = 1) -> None:
        screen = self._screens.get(name)
        if screen is None:
            return
        previous = self._stack.currentWidget()

        # Generic leave hook for the screen we are navigating away from.
        if previous is not None and previous is not screen and hasattr(previous, "on_leave"):
            try:
                previous.on_leave()
            except Exception:
                pass

        # Hide status bar and rail during splash
        is_splash = name == "splash"
        self.status_bar.setVisible(not is_splash)
        self.rail.setVisible(not is_splash)
        self.motion.show_page(
            self._stack,
            screen,
            direction=direction,
            animate=not is_splash and previous is not self._splash,
        )

        if hasattr(screen, "on_enter"):
            screen.on_enter()

    # ------------------------------------------------------------------
    # Serial initialisation
    # ------------------------------------------------------------------

    def _init_serial(self, use_mock: bool, port: str | None) -> None:
        self._splash.set_progress(60, "Initialising serial…")
        self._use_mock = use_mock
        self._explicit_port = port

        serial_obj = self._open_serial(use_mock, port, on_splash=True)

        self._controller.connect_worker(serial_obj)
        self._splash.set_progress(100, "Ready")
        QTimer.singleShot(400, lambda: self.show_screen("home"))

    def _open_serial(self, use_mock: bool, port: str | None, on_splash: bool = False):
        """Open a serial object, auto-detecting a port when none is given.

        Falls back to a MockSerial when no hardware can be reached.
        """
        def _progress(pct: int, msg: str) -> None:
            if on_splash:
                self._splash.set_progress(pct, msg)

        if use_mock:
            _progress(90, "Using simulated GRBL")
            return MockSerial()

        candidate = port or self._controller.profile.serial_port
        # When no explicit port was requested, try to auto-detect one.
        if not port:
            try:
                detected = GrblWorker.list_ports()
            except Exception:
                detected = []
            if detected:
                candidate = detected[0]

        try:
            import serial as _serial
            serial_obj = _serial.Serial(
                candidate, self._controller.profile.baud_rate, timeout=0.05
            )
            _progress(90, f"Connected: {candidate}")
            return serial_obj
        except Exception as exc:
            _progress(75, f"Serial failed, using mock: {exc}")
            return MockSerial()

    def reinit_serial(self) -> None:
        """Re-open the serial port using the same options as startup."""
        use_mock = getattr(self, "_use_mock", True)
        port = getattr(self, "_explicit_port", None)
        serial_obj = self._open_serial(use_mock, port, on_splash=False)
        self._controller.connect_worker(serial_obj)

    # ------------------------------------------------------------------
    # GRBL signal handlers
    # ------------------------------------------------------------------

    def on_status(self, status: GrblStatus) -> None:
        self.status_bar.set_status(status)

        current = self._stack.currentWidget()
        if hasattr(current, "on_status"):
            current.on_status(status)

    def on_job_progress(self, current: int, total: int) -> None:
        current_w = self._stack.currentWidget()
        if hasattr(current_w, "on_job_progress"):
            current_w.on_job_progress(current, total)

    def on_job_finished(self, success: bool) -> None:
        current = self._stack.currentWidget()
        if hasattr(current, "on_job_finished"):
            current.on_job_finished(success)

    def on_response(self, line: str) -> None:
        diag = getattr(self, "_diag", None)
        if diag is not None and hasattr(diag, "append_response"):
            try:
                diag.append_response(line)
            except Exception:
                pass

    def on_error(self, msg: str) -> None:
        # Surface the error text to the user without blocking the GRBL thread.
        self.status_bar.set_message(f"Error: {msg}")
        diag = getattr(self, "_diag", None)
        if diag is not None and hasattr(diag, "append_response"):
            try:
                diag.append_response(f"[error] {msg}")
            except Exception:
                pass

    def on_alarm(self, msg: str) -> None:
        """Handle an unsolicited ALARM/error line raised outside a job."""
        self.status_bar.set_message(f"ALARM: {msg}")
        diag = getattr(self, "_diag", None)
        if diag is not None and hasattr(diag, "append_response"):
            try:
                diag.append_response(f"[ALARM] {msg}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Connection state handlers
    # ------------------------------------------------------------------

    def on_connected(self) -> None:
        self._reconnect_pending = False
        self.status_bar.set_message("GRBL · Connected")

    def on_disconnected(self) -> None:
        self.status_bar.set_status(GrblStatus(state="Disconnected"))
        self.status_bar.set_message("GRBL · disconnected — Diagnostics ▸ Connect to retry")
        # No automatic reconnect. Reopening the port toggles DTR and resets GRBL,
        # and doing that blocking open on the GUI thread froze the UI when a
        # transient disconnect repeated. Reconnection is manual via Diagnostics.

    # ------------------------------------------------------------------
    # Keyboard input — maps to physical GPIO actions later
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        k = event.key()
        w = self._controller.worker

        if k == Qt.Key_Escape and w:
            w.soft_reset()
        elif k == Qt.Key_H:
            self._controller.navigate_to("home")
        elif k == Qt.Key_Backspace:
            self._controller.navigate_back()
        elif k == Qt.Key_1:
            self._controller.navigate_to("cnc_mode")
        elif k == Qt.Key_2:
            self._controller.navigate_to("laser_mode")
        elif k == Qt.Key_3:
            self._controller.navigate_to("probing")
        elif k == Qt.Key_4:
            self._controller.navigate_to("file_browser")
        elif k == Qt.Key_5:
            self._controller.navigate_to("settings")
        else:
            # Pass to current screen
            current = self._stack.currentWidget()
            if hasattr(current, "keyPressEvent"):
                current.keyPressEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="CNC·CTRL touchscreen UI")
    parser.add_argument("--mock", action="store_true", help="Use simulated GRBL (no hardware needed)")
    parser.add_argument("--port", help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--fullscreen", action="store_true", help="Run in fullscreen kiosk mode")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    if args.fullscreen:
        # Linux/Qt turns touchscreen taps into mouse clicks. In kiosk mode the
        # pointer must remain hidden so it cannot flash beneath a finger.
        QApplication.setOverrideCursor(Qt.BlankCursor)
    app.setApplicationName("CNC·CTRL")

    use_mock = args.mock or (args.port is None)
    window = MainWindow(use_mock=use_mock, port=args.port)

    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()

    sys.exit(app.exec() if hasattr(app, "exec") else app.exec_())


if __name__ == "__main__":
    main()
