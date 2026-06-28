"""Touch-first laser operator workflow.

This module contains presentation only.  Import, safety, presets, framing,
and Rayforge integration live in ``cnc_controller.laser``.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..qt_compat import (
    Qt,
    QFileDialog,
    QFrame,
    QColor,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPainter,
    QPen,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)
from ..theme import (
    C_AMBER,
    C_AMBER_BG,
    C_AMBER_BORDER,
    C_BLUE,
    C_BORDER,
    C_BTN_2ND,
    C_CARD_BORDER,
    C_DIM,
    C_GREEN,
    C_MUTED,
    C_RED,
    C_TEXT,
)
from ...grbl_worker import GrblStatus
from ...laser.domain import (
    LaserLayer,
    LaserMachineConfig,
    LaserOperationType,
)
from ...laser.service import LaserApplicationService
from ...models import MachineMode


CONFIG_ROOT = Path(__file__).parents[4] / "config"


def _button(text: str, style: str = "btnSecondary", height: int = 48) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(style)
    button.setFixedHeight(height)
    return button


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("labelSection")
    return label


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


class ToolpathCanvas(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bounds: tuple[float, float, float, float] | None = None
        self.setMinimumHeight(220)
        self.setStyleSheet(
            f"background: {C_BTN_2ND}; border: 1px dashed {C_CARD_BORDER}; border-radius: 9px;"
        )

    def set_bounds(self, bounds: tuple[float, float, float, float] | None) -> None:
        self._bounds = bounds
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(C_BORDER), 1))
        for x in range(20, self.width(), 20):
            painter.drawLine(x, 0, x, self.height())
        for y in range(20, self.height(), 20):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QPen(QColor(C_BLUE), 3))
        margin = 28
        painter.drawRect(margin, margin, max(1, self.width() - 2 * margin), max(1, self.height() - 2 * margin))
        painter.setPen(QPen(QColor(C_MUTED), 1))
        text = "Load artwork or G-code"
        if self._bounds:
            min_x, min_y, max_x, max_y = self._bounds
            text = f"{max_x - min_x:.1f} × {max_y - min_y:.1f} mm"
        painter.drawText(self.rect(), Qt.AlignCenter, text)


class RayforgeGenerationThread(QThread):
    generated = Signal(object)
    failed = Signal(str)

    def __init__(self, service: LaserApplicationService, parent=None):
        super().__init__(parent)
        self._service = service

    def run(self) -> None:
        try:
            self.generated.emit(self._service.generate_gcode())
        except Exception as exc:
            self.failed.emit(str(exc))


class LayerEditor(QFrame):
    def __init__(self, layer: LaserLayer, changed, parent: QWidget | None = None):
        super().__init__(parent)
        self.layer = layer
        self.changed = changed
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        dot = QFrame(self)
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(f"background:{layer.color};border:none;border-radius:3px")
        header.addWidget(dot)
        title = QLabel(layer.name, self)
        title.setStyleSheet("font-size:15px;font-weight:700;background:transparent;border:none")
        header.addWidget(title, 1)
        self.enabled = _button("ON" if layer.enabled else "OFF", height=40)
        self.enabled.setFixedWidth(68)
        self.enabled.clicked.connect(self._toggle)
        header.addWidget(self.enabled)
        layout.addLayout(header)

        controls = QGridLayout()
        controls.setSpacing(7)
        self.operation = _button(layer.operation.value.title(), height=42)
        self.operation.clicked.connect(self._cycle_operation)
        controls.addWidget(self.operation, 0, 0, 1, 2)
        self.speed = _button("", height=42)
        self.speed.clicked.connect(lambda: self._adjust("speed", 100))
        controls.addWidget(self.speed, 0, 2)
        self.power = _button("", height=42)
        self.power.clicked.connect(lambda: self._adjust("power", 5))
        controls.addWidget(self.power, 1, 0)
        self.passes = _button("", height=42)
        self.passes.clicked.connect(lambda: self._adjust("passes", 1))
        controls.addWidget(self.passes, 1, 1)
        minus = _button("− Selected", height=42)
        minus.clicked.connect(self._decrement)
        controls.addWidget(minus, 1, 2)
        layout.addLayout(controls)
        self._refresh()

    def _toggle(self) -> None:
        self.layer.enabled = not self.layer.enabled
        self.changed()
        self._refresh()

    def _cycle_operation(self) -> None:
        values = list(LaserOperationType)
        self.layer.operation = values[(values.index(self.layer.operation) + 1) % len(values)]
        self.changed()
        self._refresh()

    def _adjust(self, field: str, amount: int) -> None:
        if field == "speed":
            self.layer.speed_mm_min = min(20000, self.layer.speed_mm_min + amount)
        elif field == "power":
            self.layer.power_percent = min(100, self.layer.power_percent + amount)
        else:
            self.layer.passes = min(99, self.layer.passes + amount)
        self.changed()
        self._refresh()

    def _decrement(self) -> None:
        # One large decrement target avoids a row of tiny +/- controls.
        if self.layer.passes > 1:
            self.layer.passes -= 1
        elif self.layer.power_percent > 0:
            self.layer.power_percent = max(0, self.layer.power_percent - 5)
        else:
            self.layer.speed_mm_min = max(100, self.layer.speed_mm_min - 100)
        self.changed()
        self._refresh()

    def _refresh(self) -> None:
        self.enabled.setText("ON" if self.layer.enabled else "OFF")
        self.operation.setText(self.layer.operation.value.title())
        self.speed.setText(f"Speed  {self.layer.speed_mm_min:.0f}")
        self.power.setText(f"Power  {self.layer.power_percent:.0f}%")
        self.passes.setText(f"Passes  {self.layer.passes}")


class LaserModeScreen(QWidget):
    PAGES = ("Setup", "Layers", "Preview", "Run", "Console")

    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        profile = ctrl.profile
        self._service = LaserApplicationService(
            LaserMachineConfig(
                name=profile.name,
                work_area_mm=(profile.work_area_mm[0], profile.work_area_mm[1]),
                serial_port=profile.serial_port,
                baud_rate=profile.baud_rate,
                laser_s_range=(profile.laser_s_min, profile.laser_s_max),
                safe_travel_speed_mm_min=profile.max_feed_mm_min,
                homing_required=profile.homing_required,
            ),
            CONFIG_ROOT / "laser_materials.json",
        )
        self._status = GrblStatus()
        self._responses_connected = False
        self._job_started_at: float | None = None
        self._generation_thread: RayforgeGenerationThread | None = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        summary = QFrame(self)
        summary.setStyleSheet("background:transparent;border:none")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(2, 0, 2, 0)
        self._file_label = QLabel("No file loaded", summary)
        self._file_label.setStyleSheet("font-size:15px;font-weight:700;background:transparent;border:none")
        summary_layout.addWidget(self._file_label)
        self._operation_label = QLabel("No operation", summary)
        self._operation_label.setStyleSheet(f"color:{C_MUTED};background:transparent;border:none")
        summary_layout.addWidget(self._operation_label)
        summary_layout.addStretch()
        self._safety_badge = QLabel("NOT REVIEWED", summary)
        self._safety_badge.setStyleSheet(
            f"color:#8a5a06;background:{C_AMBER_BG};border:1px solid {C_AMBER_BORDER};"
            "border-radius:6px;padding:5px 9px;font-size:12px;font-weight:700"
        )
        summary_layout.addWidget(self._safety_badge)
        root.addWidget(summary)

        navigation = QHBoxLayout()
        navigation.setSpacing(6)
        self._nav_buttons = []
        for index, label in enumerate(self.PAGES):
            button = _button(label, height=44)
            button.clicked.connect(lambda _checked=False, page=index: self._show_page(page))
            navigation.addWidget(button, 1)
            self._nav_buttons.append(button)
        root.addLayout(navigation)

        self._pages = QStackedWidget(self)
        self._pages.addWidget(self._build_setup())
        self._pages.addWidget(self._build_layers())
        self._pages.addWidget(self._build_preview())
        self._pages.addWidget(self._build_run())
        self._pages.addWidget(self._build_console())
        root.addWidget(self._pages, 1)
        self._show_page(0)

    def _build_setup(self) -> QWidget:
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        file_card = _card()
        fl = QVBoxLayout(file_card)
        fl.setContentsMargins(14, 14, 14, 14)
        fl.addWidget(_section("File import"))
        self._source_text = QLabel(
            "SVG · DXF · PDF · PNG · JPG · BMP · G-code\n"
            "Internal · USB · SD · future network storage",
            file_card,
        )
        self._source_text.setWordWrap(True)
        self._source_text.setStyleSheet(f"font-size:14px;color:{C_MUTED};background:transparent;border:none")
        fl.addWidget(self._source_text)
        fl.addStretch()
        load = _button("Load File…", "btnPrimary", 60)
        load.clicked.connect(self._load_file)
        fl.addWidget(load)
        layout.addWidget(file_card, 3)

        preset_card = _card()
        pl = QVBoxLayout(preset_card)
        pl.setContentsMargins(14, 14, 14, 14)
        pl.addWidget(_section("Material preset"))
        self._preset_label = QLabel("Unspecified", preset_card)
        self._preset_label.setStyleSheet("font-size:21px;font-weight:700;background:transparent;border:none")
        pl.addWidget(self._preset_label)
        self._preset_notes = QLabel("Tap a preset to apply speed, power, passes, and operation.", preset_card)
        self._preset_notes.setWordWrap(True)
        self._preset_notes.setStyleSheet(f"color:{C_MUTED};background:transparent;border:none")
        pl.addWidget(self._preset_notes)
        pl.addStretch()
        for preset in self._service.presets[:3]:
            button = _button(
                f"{preset.material} · {preset.thickness_mm:g} mm · {preset.operation.value}",
                height=46,
            )
            button.clicked.connect(lambda _checked=False, item=preset: self._apply_preset(item))
            pl.addWidget(button)
        layout.addWidget(preset_card, 4)

        origin_card = _card()
        ol = QVBoxLayout(origin_card)
        ol.setContentsMargins(14, 14, 14, 14)
        ol.addWidget(_section("Origin"))
        self._origin_label = QLabel("Front-left", origin_card)
        self._origin_label.setStyleSheet("font-size:21px;font-weight:700;background:transparent;border:none")
        ol.addWidget(self._origin_label)
        ol.addStretch()
        for origin in ("Front-left", "Center", "Current position"):
            button = _button(origin, height=46)
            button.clicked.connect(lambda _checked=False, value=origin: self._set_origin(value))
            ol.addWidget(button)
        layout.addWidget(origin_card, 3)
        return page

    def _build_layers(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._layer_scroll = QScrollArea(page)
        self._layer_scroll.setWidgetResizable(True)
        self._layer_host = QWidget(self._layer_scroll)
        self._layer_layout = QVBoxLayout(self._layer_host)
        self._layer_layout.setContentsMargins(0, 0, 4, 0)
        self._layer_layout.setSpacing(8)
        self._layer_layout.addWidget(QLabel("Load a file to detect layers.", self._layer_host))
        self._layer_layout.addStretch()
        self._layer_scroll.setWidget(self._layer_host)
        layout.addWidget(self._layer_scroll)
        return page

    def _build_preview(self) -> QWidget:
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        preview = _card()
        pl = QVBoxLayout(preview)
        pl.setContentsMargins(12, 12, 12, 12)
        header = QHBoxLayout()
        header.addWidget(_section("Job preview"))
        header.addStretch()
        self._bounds_label = QLabel("Bounds —", preview)
        self._bounds_label.setStyleSheet(f"color:{C_MUTED};background:transparent;border:none")
        header.addWidget(self._bounds_label)
        pl.addLayout(header)
        self._canvas = ToolpathCanvas(preview)
        pl.addWidget(self._canvas, 1)
        layout.addWidget(preview, 7)

        actions = QWidget(page)
        al = QVBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        self._preview_summary = QLabel("Load a file to preview.", actions)
        self._preview_summary.setWordWrap(True)
        self._preview_summary.setStyleSheet(
            f"background:white;border:1px solid {C_CARD_BORDER};border-radius:12px;"
            f"padding:13px;color:{C_MUTED};font-size:13px"
        )
        al.addWidget(self._preview_summary, 1)
        self._frame_btn = _button("Frame", height=56)
        self._frame_btn.clicked.connect(self._frame)
        al.addWidget(self._frame_btn)
        self._generate_btn = _button("Generate G-code", height=56)
        self._generate_btn.clicked.connect(self._generate)
        al.addWidget(self._generate_btn)
        self._review_btn = _button("Safety Review", "btnPrimary", 64)
        self._review_btn.clicked.connect(self._review)
        al.addWidget(self._review_btn)
        layout.addWidget(actions, 3)
        return page

    def _build_run(self) -> QWidget:
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        state_card = _card()
        sl = QVBoxLayout(state_card)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.addWidget(_section("Job state"))
        self._run_state = QLabel("IDLE", state_card)
        self._run_state.setAlignment(Qt.AlignCenter)
        self._run_state.setStyleSheet(f"font-size:42px;font-weight:700;color:{C_GREEN};background:transparent;border:none")
        sl.addWidget(self._run_state, 1)
        self._progress = QProgressBar(state_card)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(12)
        sl.addWidget(self._progress)
        self._line_label = QLabel("Line 0 / 0", state_card)
        self._line_label.setAlignment(Qt.AlignCenter)
        sl.addWidget(self._line_label)
        timing = QHBoxLayout()
        self._elapsed = QLabel("Elapsed  00:00", state_card)
        self._remaining = QLabel("Remaining  —", state_card)
        timing.addWidget(self._elapsed)
        timing.addStretch()
        timing.addWidget(self._remaining)
        sl.addLayout(timing)
        layout.addWidget(state_card, 6)

        control = QWidget(page)
        cl = QGridLayout(control)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        self._start_btn = _button("Start", "btnPrimary", 64)
        self._start_btn.clicked.connect(self._start)
        pause = _button("Pause / Hold", "btnWarning", 64)
        pause.clicked.connect(self._pause)
        resume = _button("Resume", "btnPrimary", 64)
        resume.clicked.connect(self._resume)
        stop = _button("Stop / Reset", "btnDanger", 64)
        stop.clicked.connect(self._stop)
        cl.addWidget(self._start_btn, 0, 0, 1, 2)
        cl.addWidget(pause, 1, 0)
        cl.addWidget(resume, 1, 1)
        cl.addWidget(stop, 2, 0, 1, 2)
        self._override = QLabel("Feed 100%  ·  Rapid 100%  ·  Power 100%", control)
        self._override.setAlignment(Qt.AlignCenter)
        self._override.setWordWrap(True)
        self._override.setStyleSheet(
            f"background:white;border:1px solid {C_CARD_BORDER};border-radius:10px;"
            f"padding:10px;color:{C_MUTED};font-weight:700"
        )
        cl.addWidget(self._override, 3, 0, 1, 2)
        layout.addWidget(control, 4)
        return page

    def _build_console(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        status = QHBoxLayout()
        self._console_status = QLabel("GRBL disconnected", page)
        self._console_status.setStyleSheet("font-size:15px;font-weight:700;background:transparent;border:none")
        status.addWidget(self._console_status)
        status.addStretch()
        settings = _button("Read $$", height=44)
        settings.clicked.connect(lambda: self._send_command("$$"))
        status.addWidget(settings)
        clear = _button("Clear", height=44)
        clear.clicked.connect(lambda: self._console.clear())
        status.addWidget(clear)
        layout.addLayout(status)
        self._console = QPlainTextEdit(page)
        self._console.setReadOnly(True)
        self._console.setStyleSheet(
            "background:#15191d;color:#e9ecef;border:1px solid #d4d9de;"
            "border-radius:10px;font-family:monospace;font-size:13px;padding:7px"
        )
        layout.addWidget(self._console, 1)
        command_row = QHBoxLayout()
        self._command = QLineEdit(page)
        self._command.setPlaceholderText("Raw GRBL command")
        self._command.setFixedHeight(50)
        self._command.returnPressed.connect(self._send_console)
        command_row.addWidget(self._command, 1)
        send = _button("Send", "btnPrimary", 50)
        send.clicked.connect(self._send_console)
        command_row.addWidget(send)
        layout.addLayout(command_row)
        return page

    def _show_page(self, index: int) -> None:
        previous = self._pages.currentIndex()
        page = self._pages.widget(index)
        self._ctrl.motion.show_page(
            self._pages,
            page,
            direction=1 if index >= previous else -1,
        )
        for button_index, button in enumerate(self._nav_buttons):
            button.setStyleSheet(
                f"background:{C_BLUE};color:white;border:1px solid {C_BLUE};"
                "border-radius:9px;font-weight:700"
                if button_index == index
                else ""
            )
        hints = (
            ("SELECT", "job setup"),
            ("SELECT", "layer"),
            ("ZOOM", "preview"),
            ("NAVIGATE", "controls"),
            ("SCROLL", "console"),
        )
        self._ctrl.rail.set_enc1(*hints[index])

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open laser job",
            "",
            "Laser files (*.svg *.dxf *.pdf *.png *.jpg *.jpeg *.bmp *.gcode *.gc *.nc *.tap)",
        )
        if not path:
            return
        try:
            job = self._service.import_file(Path(path))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Cannot load file", str(exc))
            return
        self._file_label.setText(job.name)
        self._source_text.setText(
            f"{job.name}\n{job.source_kind.upper()} · "
            f"{len(job.layers)} detected operation layer(s)"
        )
        self._canvas.set_bounds(job.bounds_mm)
        self._rebuild_layers()
        self._refresh_job_summary()
        self._show_page(1)

    def _rebuild_layers(self) -> None:
        while self._layer_layout.count():
            item = self._layer_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        job = self._service.job
        if job:
            for layer in job.layers:
                self._layer_layout.addWidget(LayerEditor(layer, self._job_changed, self._layer_host))
        self._layer_layout.addStretch()

    def _apply_preset(self, preset) -> None:
        self._service.select_preset(preset)
        self._preset_label.setText(f"{preset.material} · {preset.thickness_mm:g} mm")
        self._preset_notes.setText(preset.notes)
        self._rebuild_layers()
        self._refresh_job_summary()

    def _set_origin(self, origin: str) -> None:
        if self._service.job:
            self._service.job.origin = origin.casefold()
        self._origin_label.setText(origin)
        self._job_changed()

    def _job_changed(self) -> None:
        self._service.warning_confirmation = False
        self._safety_badge.setText("NOT REVIEWED")
        self._refresh_job_summary()

    def _refresh_job_summary(self) -> None:
        job = self._service.job
        if not job:
            return
        enabled = job.enabled_layers
        self._operation_label.setText(
            f"{len(enabled)} operation(s) · {job.material} · origin {job.origin}"
        )
        if job.bounds_mm:
            x0, y0, x1, y1 = job.bounds_mm
            self._bounds_label.setText(f"Bounds {x1 - x0:.1f} × {y1 - y0:.1f} mm")
        generated = "G-code ready" if job.is_generated else "G-code required"
        warnings = "\n".join(f"• {item}" for item in job.warnings[:3]) or "• No import warnings"
        operations = "\n".join(
            f"• {layer.name}: {layer.operation.value}, {layer.speed_mm_min:.0f} mm/min, "
            f"{layer.power_percent:.0f}%, {layer.passes} pass(es)"
            for layer in enabled[:4]
        )
        self._preview_summary.setText(
            f"{job.material}\n{generated}\n\n{operations}\n\n{warnings}"
        )

    def _review(self) -> None:
        report = self._service.safety_review()
        if report.errors:
            self._safety_badge.setText(f"{len(report.errors)} BLOCKER(S)")
            self._safety_badge.setStyleSheet(
                f"color:white;background:{C_RED};border:none;border-radius:6px;"
                "padding:5px 9px;font-size:12px;font-weight:700"
            )
            QMessageBox.critical(self, "Safety review blocked", "\n\n".join(report.errors + report.warnings))
            return
        if report.warnings:
            answer = QMessageBox.warning(
                self,
                "Confirm safety warnings",
                "\n\n".join(report.warnings)
                + "\n\nNo G-code will be altered. Confirm these warnings to enable Start.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            self._service.warning_confirmation = answer == QMessageBox.Yes
        else:
            self._service.warning_confirmation = True
        if self._service.warning_confirmation:
            self._safety_badge.setText("REVIEWED")
            self._safety_badge.setStyleSheet(
                f"color:white;background:{C_GREEN};border:none;border-radius:6px;"
                "padding:5px 9px;font-size:12px;font-weight:700"
            )
            self._show_page(3)

    def _frame(self) -> None:
        if not self._ctrl.worker:
            return
        try:
            lines = self._service.frame_lines()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot frame", str(exc))
            return
        # M5 is included before every frame move.
        self._ctrl.worker.start_job(lines)

    def _generate(self) -> None:
        job = self._service.job
        if not job:
            QMessageBox.warning(self, "No job", "Load a laser file first.")
            return
        if job.is_generated:
            QMessageBox.information(
                self, "G-code ready", "The loaded G-code has been validated and is ready for safety review."
            )
            return
        if self._generation_thread and self._generation_thread.isRunning():
            return
        self._generate_btn.setEnabled(False)
        self._generate_btn.setText("Generating…")
        self._review_btn.setEnabled(False)
        self._generation_thread = RayforgeGenerationThread(
            self._service, self
        )
        self._generation_thread.generated.connect(
            self._on_generation_complete
        )
        self._generation_thread.failed.connect(self._on_generation_failed)
        self._generation_thread.start()

    def _on_generation_complete(self, job) -> None:
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("G-code Ready")
        self._review_btn.setEnabled(True)
        self._canvas.set_bounds(job.bounds_mm)
        self._refresh_job_summary()
        estimate = (
            self._format_time(job.estimated_seconds)
            if job.estimated_seconds is not None
            else "unavailable"
        )
        QMessageBox.information(
            self,
            "Rayforge generation complete",
            f"Generated {len(job.gcode_lines or [])} lines.\n"
            f"Estimated runtime: {estimate}.\n\n"
            "Run Safety Review before starting.",
        )

    def _on_generation_failed(self, message: str) -> None:
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("Generate G-code")
        self._review_btn.setEnabled(True)
        QMessageBox.critical(
            self, "Rayforge generation failed", message
        )

    def _start(self) -> None:
        report = self._service.safety_review()
        if not report.ok_to_run or (report.requires_confirmation and not self._service.warning_confirmation):
            self._review()
            return
        job = self._service.job
        if not job or not job.gcode_lines or not self._ctrl.worker:
            return
        self._job_started_at = time.monotonic()
        self._elapsed_timer.start(1000)
        self._progress.setValue(0)
        self._ctrl.worker.start_job(job.gcode_lines)

    def _pause(self) -> None:
        if self._ctrl.worker:
            self._ctrl.worker.feed_hold()

    def _resume(self) -> None:
        if self._ctrl.worker:
            self._ctrl.worker.cycle_start()

    def _stop(self) -> None:
        if not self._ctrl.worker:
            return
        answer = QMessageBox.warning(
            self,
            "Stop laser job?",
            "This sends feed hold followed by GRBL soft reset.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._ctrl.worker.stop_job()
            QTimer.singleShot(150, self._ctrl.worker.soft_reset)

    def _send_console(self) -> None:
        command = self._command.text().strip()
        if command:
            self._send_command(command)
            self._command.clear()

    def _send_command(self, command: str) -> None:
        if self._ctrl.worker:
            self._console.appendPlainText(f"> {command}")
            self._ctrl.worker.send_command(command)

    def on_response(self, line: str) -> None:
        self._console.appendPlainText(line)
        if line.strip().startswith("$32="):
            self._service.laser_mode_confirmed = line.strip().split("=", 1)[1] == "1"
            self._refresh_mode_badge()

    def _refresh_mode_badge(self) -> None:
        if self._service.laser_mode_confirmed:
            self._console_status.setText("GRBL connected · laser mode $32=1 confirmed")
        else:
            self._console_status.setText("GRBL connected · laser mode NOT confirmed")

    def on_status(self, status: GrblStatus) -> None:
        state_changed = status.state != self._status.state
        self._status = status
        state = status.state.upper()
        color = status.state_color
        self._run_state.setText(state)
        self._run_state.setStyleSheet(
            f"font-size:42px;font-weight:700;color:{color};background:transparent;border:none"
        )
        if state_changed:
            self._ctrl.motion.pulse(self._run_state)
        feed, rapid, spindle = status.overrides
        self._override.setText(f"Feed {feed}%  ·  Rapid {rapid}%  ·  Power {spindle}%")
        self._console_status.setText(
            f"GRBL {status.state} · "
            f"{'laser mode $32=1 confirmed' if self._service.laser_mode_confirmed else 'laser mode NOT confirmed'}"
        )
        self._start_btn.setEnabled(
            status.is_idle
            and self._service.laser_mode_confirmed
            and self._service.job is not None
        )

    def on_job_progress(self, current: int, total: int) -> None:
        self._line_label.setText(f"Line {current} / {total}")
        self._ctrl.motion.animate_value(
            self._progress,
            round(current * 100 / total) if total else 0,
        )
        if self._job_started_at and current:
            elapsed = time.monotonic() - self._job_started_at
            remaining = max(0, elapsed * (total - current) / current)
            self._remaining.setText(f"Remaining  {self._format_time(remaining)}")

    def on_job_finished(self, success: bool) -> None:
        self._elapsed_timer.stop()
        if success:
            self._ctrl.motion.animate_value(self._progress, 100)
        self._run_state.setText("COMPLETE" if success else "ALARM")
        self._run_state.setStyleSheet(
            f"font-size:42px;font-weight:700;color:{C_GREEN if success else C_RED};"
            "background:transparent;border:none"
        )
        self._ctrl.motion.pulse(self._run_state)

    def _update_elapsed(self) -> None:
        if self._job_started_at:
            self._elapsed.setText(
                f"Elapsed  {self._format_time(time.monotonic() - self._job_started_at)}"
            )

    @staticmethod
    def _format_time(seconds: float) -> str:
        value = max(0, round(seconds))
        return f"{value // 60:02d}:{value % 60:02d}"

    def on_enter(self) -> None:
        self._ctrl.status_bar.set_mode(MachineMode.LASER)
        self._ctrl.rail.set_enc1("SELECT", "job setup")
        self._ctrl.rail.set_enc2("POWER", "override")
        worker = self._ctrl.worker
        if worker:
            if not self._responses_connected:
                worker.response_received.connect(self.on_response)
                self._responses_connected = True
            # Confirmation comes only from the subsequent $$ response.
            self._service.laser_mode_confirmed = False
            worker.set_laser_mode(True)
            worker.send_command("$$")

    def keyPressEvent(self, event) -> None:
        """Keyboard development adapter; GPIO will dispatch the same actions."""
        key = event.key()
        if key == Qt.Key_Space:
            self._start()
        elif key == Qt.Key_F:
            self._pause()
        elif key == Qt.Key_R:
            self._resume()
        elif key == Qt.Key_X and self._ctrl.worker:
            self._ctrl.worker.soft_reset()
        elif key == Qt.Key_B:
            self._frame()
        elif key == Qt.Key_C:
            self._show_page((self._pages.currentIndex() + 1) % len(self.PAGES))
        else:
            super().keyPressEvent(event)
