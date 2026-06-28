"""CNC Mode screen — DRO, jog pad, job control."""
from __future__ import annotations

from pathlib import Path

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QProgressBar, QSizePolicy, QFileDialog,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_BLUE, C_AMBER, C_RED, C_BG, C_BTN_2ND,
    CARD_RADIUS, BTN_RADIUS, TOUCH_MIN, TOUCH_PRIMARY,
)
from ...grbl_worker import GrblStatus


# ---------------------------------------------------------------------------
# DRO row widget
# ---------------------------------------------------------------------------

class DRORow(QFrame):
    """One X/Y/Z row in the DRO panel."""

    def __init__(self, axis: str, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._axis = axis
        self._ctrl = ctrl
        self.setStyleSheet("background: transparent; border: none;")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 11, 0, 11)
        row.setSpacing(10)

        axis_lbl = QLabel(axis, self)
        axis_lbl.setObjectName("labelAxis")
        axis_lbl.setFixedWidth(20)
        row.addWidget(axis_lbl)

        nums = QWidget(self)
        nums.setStyleSheet("background: transparent; border: none;")
        nl = QVBoxLayout(nums)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(2)

        self._wpos = QLabel("0.000", nums)
        self._wpos.setObjectName("labelDRO")
        self._wpos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        nl.addWidget(self._wpos)

        self._mpos = QLabel("M 0.000", nums)
        self._mpos.setObjectName("labelMPos")
        self._mpos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        nl.addWidget(self._mpos)
        row.addWidget(nums, 1)

        zero_btn = QPushButton("Ø", self)
        zero_btn.setObjectName("btnSecondary")
        zero_btn.setFixedSize(46, 46)
        zero_btn.clicked.connect(self._zero_axis)
        row.addWidget(zero_btn)

    def update(self, wpos: float, mpos: float) -> None:
        self._wpos.setText(f"{wpos:.3f}")
        self._mpos.setText(f"M {mpos:.3f}")

    def _zero_axis(self) -> None:
        if self._ctrl.worker:
            self._ctrl.worker.set_work_zero(self._axis)


# ---------------------------------------------------------------------------
# DRO panel
# ---------------------------------------------------------------------------

class DROPanel(QFrame):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self.setObjectName("card")
        self.setFixedWidth(288)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(14, 14, 14, 14)
        lyt.setSpacing(0)

        header = QHBoxLayout()
        sec = QLabel("WORK POSITION", self)
        sec.setObjectName("labelSection")
        header.addWidget(sec)
        header.addStretch()
        wcs = QLabel("G54", self)
        wcs.setStyleSheet(
            f"color: {C_GREEN}; background: #e6f4ec; border: 1px solid #bfe3cf; "
            f"border-radius: 5px; font-size: 12px; font-weight: 700; padding: 3px 8px;"
        )
        header.addWidget(wcs)
        lyt.addLayout(header)
        lyt.addSpacing(6)

        def _hdiv():
            f = QFrame(self)
            f.setFixedHeight(1)
            f.setStyleSheet(f"background: {C_DIVIDER}; border: none;")
            return f

        self._x = DRORow("X", ctrl, self)
        lyt.addWidget(_hdiv())
        lyt.addWidget(self._x)

        self._y = DRORow("Y", ctrl, self)
        lyt.addWidget(_hdiv())
        lyt.addWidget(self._y)

        self._z = DRORow("Z", ctrl, self)
        lyt.addWidget(_hdiv())
        lyt.addWidget(self._z)

        lyt.addStretch()

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        zero_all = QPushButton("Zero All", self)
        zero_all.setObjectName("btnSecondary")
        zero_all.setFixedHeight(48)
        zero_all.clicked.connect(lambda: ctrl.worker and ctrl.worker.set_work_zero("XYZ"))
        goto = QPushButton("Go To 0", self)
        goto.setObjectName("btnSecondary")
        goto.setFixedHeight(48)
        goto.clicked.connect(lambda: ctrl.worker and ctrl.worker.goto_zero())
        btn_row.addWidget(zero_all, 1)
        btn_row.addWidget(goto, 1)
        lyt.addLayout(btn_row)

    def update_status(self, status: GrblStatus) -> None:
        wx, wy, wz = status.wpos
        mx, my, mz = status.mpos
        self._x.update(wx, mx)
        self._y.update(wy, my)
        self._z.update(wz, mz)


# ---------------------------------------------------------------------------
# Jog pad
# ---------------------------------------------------------------------------

JOG_STEPS = [0.01, 0.1, 1.0, 10.0]
JOG_FEED = 500.0


class JogPad(QFrame):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._step_idx = 2  # default 1.0 mm
        self.setObjectName("card")
        self.setFixedWidth(286)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(14, 14, 14, 14)
        lyt.setSpacing(0)

        sec = QLabel("JOG · STEP", self)
        sec.setObjectName("labelSection")
        lyt.addWidget(sec)
        lyt.addSpacing(10)

        # Step size selector
        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        self._step_btns: list[QPushButton] = []
        for i, step in enumerate(JOG_STEPS):
            lbl = str(step).rstrip("0").rstrip(".")
            btn = QPushButton(lbl, self)
            btn.setObjectName("btnStep")
            btn.setFixedHeight(42)
            btn.clicked.connect(lambda _, idx=i: self._select_step(idx))
            step_row.addWidget(btn)
            self._step_btns.append(btn)
        lyt.addLayout(step_row)
        lyt.addSpacing(12)
        self._select_step(self._step_idx)

        # Direction grid (3x3)
        dirs = [
            ("↖", -1, 1, False), ("↑", 0, 1, True),   ("↗", 1, 1, False),
            ("←", -1, 0, True),  ("●", 0, 0, False),   ("→", 1, 0, True),
            ("↙", -1, -1, False),("↓", 0, -1, True),   ("↘", 1, -1, False),
        ]
        grid = QGridLayout()
        grid.setSpacing(7)
        for idx, (arrow, dx, dy, active) in enumerate(dirs):
            row, col = idx // 3, idx % 3
            if dx == 0 and dy == 0:
                center = QFrame(self)
                center.setStyleSheet(
                    f"background: #eef6f1; border: 1px solid #bfe3cf; border-radius: {BTN_RADIUS}px;"
                )
                dot = QFrame(center)
                dot.setFixedSize(18, 18)
                dot.setStyleSheet(
                    f"background: transparent; border: 2px solid {C_GREEN}; border-radius: 9px;"
                )
                dot.move(11, 11)  # approximate center
                grid.addWidget(center, row, col)
            else:
                btn = QPushButton(arrow, self)
                btn.setObjectName("btnJog")
                color = C_TEXT if active else "#b3bcc4"
                btn.setStyleSheet(
                    f"QPushButton {{ background: {C_BTN_2ND}; border: 1px solid {C_CARD_BORDER}; "
                    f"border-radius: {BTN_RADIUS}px; font-size: {'26' if active else '22'}px; "
                    f"color: {color}; }}"
                    f"QPushButton:pressed {{ background: #dbe6f5; border-color: {C_BLUE}; }}"
                )
                btn.clicked.connect(lambda _, x=dx, y=dy: self._jog_xy(x, y))
                grid.addWidget(btn, row, col)

        for i in range(3):
            grid.setRowStretch(i, 1)
            grid.setColumnStretch(i, 1)
        lyt.addLayout(grid)

        # Z buttons
        z_row = QHBoxLayout()
        z_row.setSpacing(7)
        z_row.setContentsMargins(0, 10, 0, 0)
        zup = QPushButton("Z ↑", self)
        zup.setObjectName("btnJog")
        zup.setFixedHeight(50)
        zup.setStyleSheet(
            f"QPushButton {{ background: {C_BTN_2ND}; border: 1px solid {C_CARD_BORDER}; "
            f"border-radius: {BTN_RADIUS}px; font-size: 16px; font-weight: 700; color: {C_TEXT}; }}"
            f"QPushButton:pressed {{ background: #dbe6f5; border-color: {C_BLUE}; }}"
        )
        zup.clicked.connect(lambda: self._jog_z(1))
        zdn = QPushButton("Z ↓", self)
        zdn.setObjectName("btnJog")
        zdn.setFixedHeight(50)
        zdn.setStyleSheet(zup.styleSheet())
        zdn.clicked.connect(lambda: self._jog_z(-1))
        z_row.addWidget(zup, 1)
        z_row.addWidget(zdn, 1)
        lyt.addLayout(z_row)

    def _select_step(self, idx: int) -> None:
        self._step_idx = idx
        for i, btn in enumerate(self._step_btns):
            if i == idx:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {C_GREEN}; color: white; border: 1px solid {C_GREEN}; "
                    f"border-radius: 8px; font-size: 13px; font-weight: 700; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {C_BTN_2ND}; color: {C_MUTED}; "
                    f"border: 1px solid {C_CARD_BORDER}; border-radius: 8px; "
                    f"font-size: 13px; font-weight: 700; }}"
                )

    def _jog_xy(self, dx: int, dy: int) -> None:
        step = JOG_STEPS[self._step_idx]
        w = self._ctrl.worker
        if not w:
            return
        if dx != 0:
            w.jog("X", dx * step, JOG_FEED)
        if dy != 0:
            w.jog("Y", dy * step, JOG_FEED)

    def _jog_z(self, dz: int) -> None:
        step = JOG_STEPS[self._step_idx]
        w = self._ctrl.worker
        if w:
            w.jog("Z", dz * step, JOG_FEED / 2)

    def step_mm(self) -> float:
        return JOG_STEPS[self._step_idx]


# ---------------------------------------------------------------------------
# Job control panel
# ---------------------------------------------------------------------------

class JobPanel(QFrame):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._total_lines = 0
        self._job_path: Path | None = None

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(12)

        # Progress card
        prog_card = QFrame(self)
        prog_card.setObjectName("card")
        plyt = QVBoxLayout(prog_card)
        plyt.setContentsMargins(14, 14, 14, 14)
        plyt.setSpacing(0)

        top_row = QHBoxLayout()
        self._filename_lbl = QLabel("No job loaded", prog_card)
        self._filename_lbl.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
        top_row.addWidget(self._filename_lbl, 1)
        self._pct_lbl = QLabel("", prog_card)
        self._pct_lbl.setStyleSheet(
            f"color: {C_BLUE}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
        )
        top_row.addWidget(self._pct_lbl)
        plyt.addLayout(top_row)
        plyt.addSpacing(9)

        self._progress = QProgressBar(prog_card)
        self._progress.setFixedHeight(9)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        plyt.addWidget(self._progress)
        plyt.addSpacing(9)

        info_row = QHBoxLayout()
        self._line_lbl = QLabel("", prog_card)
        self._line_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; background: transparent; border: none;"
        )
        info_row.addWidget(self._line_lbl)
        info_row.addStretch()
        plyt.addLayout(info_row)
        plyt.addSpacing(12)

        top_btn_row = QHBoxLayout()
        top_btn_row.setSpacing(8)

        self._load_btn = QPushButton("Load File", prog_card)
        self._load_btn.setObjectName("btnSecondary")
        self._load_btn.setFixedHeight(54)
        self._load_btn.clicked.connect(self._load_file)
        top_btn_row.addWidget(self._load_btn, 1)

        self._run_btn = QPushButton("▶ Run", prog_card)
        self._run_btn.setObjectName("btnPrimary")
        self._run_btn.setFixedHeight(54)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_job)
        top_btn_row.addWidget(self._run_btn, 1)

        plyt.addLayout(top_btn_row)
        plyt.addSpacing(6)

        bot_btn_row = QHBoxLayout()
        bot_btn_row.setSpacing(8)

        self._hold_btn = QPushButton("Feed Hold", prog_card)
        self._hold_btn.setObjectName("btnWarning")
        self._hold_btn.setFixedHeight(54)
        self._hold_btn.setEnabled(False)
        self._hold_btn.clicked.connect(lambda: ctrl.worker and ctrl.worker.feed_hold())
        bot_btn_row.addWidget(self._hold_btn, 1)

        self._stop_btn = QPushButton("Stop", prog_card)
        self._stop_btn.setObjectName("btnDanger")
        self._stop_btn.setFixedHeight(54)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(lambda: ctrl.worker and ctrl.worker.stop_job())
        bot_btn_row.addWidget(self._stop_btn, 1)

        plyt.addLayout(bot_btn_row)
        lyt.addWidget(prog_card)

        # Info card
        info_card = QFrame(self)
        info_card.setObjectName("card")
        ilyt = QVBoxLayout(info_card)
        ilyt.setContentsMargins(14, 14, 14, 14)
        ilyt.setSpacing(11)

        # Spindle row
        sp_row = QHBoxLayout()
        sp_sec = QLabel("SPINDLE", info_card)
        sp_sec.setObjectName("labelSection")
        sp_row.addWidget(sp_sec)
        sp_row.addStretch()
        self._spindle_lbl = QLabel("—", info_card)
        self._spindle_lbl.setStyleSheet(
            f"color: {C_TEXT}; font-size: 18px; font-weight: 700; background: transparent; border: none;"
        )
        sp_row.addWidget(self._spindle_lbl)
        ilyt.addLayout(sp_row)

        def _kv_row(key, val, card):
            f = QFrame(card)
            f.setStyleSheet("background: transparent; border: none;")
            rl = QHBoxLayout(f)
            rl.setContentsMargins(0, 0, 0, 0)
            k = QLabel(key, f)
            k.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;")
            v = QLabel(val, f)
            v.setStyleSheet(f"color: {C_TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;")
            rl.addWidget(k)
            rl.addStretch()
            rl.addWidget(v)
            f._val = v
            return f

        self._feed_row = _kv_row("Feed rate", "—", info_card)
        ilyt.addWidget(self._feed_row)

        self._tool_row = _kv_row("Current tool", "—", info_card)
        ilyt.addWidget(self._tool_row)

        ilyt.addStretch()

        # Bottom: Probe + Spindle toggle
        bot = QHBoxLayout()
        bot.setSpacing(8)
        probe_btn = QPushButton("Probe Z", info_card)
        probe_btn.setObjectName("btnSecondary")
        probe_btn.setFixedHeight(50)
        probe_btn.clicked.connect(lambda: ctrl.navigate_to("probing"))
        spindle_btn = QPushButton("Spindle ⏻", info_card)
        spindle_btn.setObjectName("btnSecondary")
        spindle_btn.setFixedHeight(50)
        bot.addWidget(probe_btn, 1)
        bot.addWidget(spindle_btn, 1)
        ilyt.addLayout(bot)
        lyt.addWidget(info_card, 1)

    def update_status(self, status: GrblStatus) -> None:
        running = status.is_running
        self._hold_btn.setEnabled(running)
        self._stop_btn.setEnabled(running or status.is_hold)
        self._run_btn.setEnabled(self._job_path is not None and status.is_idle)
        self._load_btn.setEnabled(not running)

        if status.spindle > 0:
            self._spindle_lbl.setText(f"{status.spindle:.0f} rpm")
        else:
            self._spindle_lbl.setText("Off")

        if status.feed > 0:
            self._feed_row._val.setText(f"{status.feed:.0f} mm/min")

    def update_progress(self, current: int, total: int) -> None:
        self._total_lines = total
        pct = int(current / total * 100) if total else 0
        self._progress.setValue(pct)
        self._pct_lbl.setText(f"{pct}%")
        self._line_lbl.setText(f"Line {current} / {total}")

    def on_job_finished(self, success: bool) -> None:
        self._progress.setValue(100 if success else self._progress.value())
        self._pct_lbl.setText("Done ✓" if success else "Error")
        self._hold_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open G-code file", "",
            "G-code (*.nc *.gcode *.gc *.tap);;All files (*)"
        )
        if path:
            self._job_path = Path(path)
            self._filename_lbl.setText(self._job_path.name)
            self._progress.setValue(0)
            self._pct_lbl.setText("")
            self._line_lbl.setText("")
            self._run_btn.setEnabled(True)

    def _run_job(self) -> None:
        if not self._job_path or not self._ctrl.worker:
            return
        lines = self._job_path.read_text().splitlines()
        self._ctrl.worker.start_job(lines)
        self._run_btn.setEnabled(False)
        self._hold_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# CNC Mode screen
# ---------------------------------------------------------------------------

class CncModeScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        self._dro = DROPanel(self._ctrl, self)
        root.addWidget(self._dro)

        self._jog = JogPad(self._ctrl, self)
        root.addWidget(self._jog)

        self._job = JobPanel(self._ctrl, self)
        root.addWidget(self._job, 1)

    def on_status(self, status: GrblStatus) -> None:
        self._dro.update_status(status)
        self._job.update_status(status)

    def on_job_progress(self, current: int, total: int) -> None:
        self._job.update_progress(current, total)

    def on_job_finished(self, success: bool) -> None:
        self._job.on_job_finished(success)

    def on_enter(self) -> None:
        self._ctrl.status_bar.set_mode(self._ctrl.mode)
        self._ctrl.rail.set_enc1("JOG · X", f"step {self._jog.step_mm():.2f} mm")
        self._ctrl.rail.set_enc2("FEED", "100%")
        self._ctrl.rail.ctx_btn.setVisible(True)

    def keyPressEvent(self, event) -> None:
        k = event.key()
        step = self._jog.step_mm()
        w = self._ctrl.worker
        if not w:
            return
        if k == Qt.Key_Left:
            w.jog("X", -step, JOG_FEED)
        elif k == Qt.Key_Right:
            w.jog("X", step, JOG_FEED)
        elif k == Qt.Key_Up:
            w.jog("Y", step, JOG_FEED)
        elif k == Qt.Key_Down:
            w.jog("Y", -step, JOG_FEED)
        elif k == Qt.Key_PageUp:
            w.jog("Z", step, JOG_FEED / 2)
        elif k == Qt.Key_PageDown:
            w.jog("Z", -step, JOG_FEED / 2)
        elif k == Qt.Key_Space:
            w.cycle_start()
        elif k == Qt.Key_F:
            w.feed_hold()
        else:
            super().keyPressEvent(event)
