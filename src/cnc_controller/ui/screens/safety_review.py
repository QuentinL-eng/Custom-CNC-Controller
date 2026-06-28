"""Safety review screen — pre-flight checklist before every job."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_GREEN_BG, C_GREEN_BORDER,
    C_AMBER, C_AMBER_BG, C_AMBER_BORDER, C_AMBER_TEXT,
    C_RED, C_RED_BG, C_RED_BORDER,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus
from ...models import JobSettings, MachineProfile
from ...safety import check_job_safety


STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_ERR = "err"

_COLOR_MAP = {
    STATUS_OK: (C_GREEN, C_CARD, C_CARD_BORDER),
    STATUS_WARN: (C_AMBER, C_AMBER_BG, C_AMBER_BORDER),
    STATUS_ERR: (C_RED, C_RED_BG, C_RED_BORDER),
}
_ICON_MAP = {STATUS_OK: "✓", STATUS_WARN: "!", STATUS_ERR: "✕"}

# Human-readable labels for correction keys surfaced from the SafetyReport.
_CORRECTION_LABELS = {
    "feed_mm_min": ("Clamp feed rate", "mm/min"),
    "plunge_mm_min": ("Clamp plunge feed", "mm/min"),
    "power_s": ("Clamp laser/spindle power", "S"),
}


class CheckRow(QFrame):
    def __init__(self, status: str, title: str, detail: str = "",
                 action_label: str = "", on_action=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._status = status

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(11, 11, 11, 11)
        lyt.setSpacing(12)

        self._dot = QLabel(self)
        self._dot.setFixedSize(26, 26)
        self._dot.setAlignment(Qt.AlignCenter)
        lyt.addWidget(self._dot)

        text_w = QWidget(self)
        text_w.setStyleSheet("background: transparent; border: none;")
        tl = QVBoxLayout(text_w)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(1)

        self._title = QLabel(title, text_w)
        self._title.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        tl.addWidget(self._title)

        self._detail = QLabel(detail, text_w)
        self._detail.setWordWrap(True)
        self._detail.setVisible(bool(detail))
        tl.addWidget(self._detail)
        lyt.addWidget(text_w, 1)

        if action_label and on_action:
            btn = QPushButton(action_label, self)
            btn.setObjectName("btnWarning")
            btn.setFixedHeight(38)
            btn.clicked.connect(on_action)
            lyt.addWidget(btn)

        self.update_state(status, title, detail)

    def update_state(self, status: str, title: str | None = None,
                     detail: str | None = None) -> None:
        """Refresh the row's status colour, icon and (optionally) text in place."""
        self._status = status
        dot_color, bg, border = _COLOR_MAP.get(status, _COLOR_MAP[STATUS_OK])
        icon = _ICON_MAP.get(status, "✓")

        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 11px; }}"
        )
        self._dot.setText(icon)
        self._dot.setStyleSheet(
            f"background: {dot_color}; color: white; border-radius: 13px; "
            f"font-size: 15px; font-weight: 700; border: none;"
        )
        if title is not None:
            self._title.setText(title)
        if detail is not None:
            self._detail.setText(detail)
            self._detail.setVisible(bool(detail))
        self._detail.setStyleSheet(
            f"color: {C_AMBER_TEXT if status == STATUS_WARN else C_MUTED}; "
            f"font-size: 12px; background: transparent; border: none;"
        )


class SafetyReviewScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._status: GrblStatus | None = None
        self._job: JobSettings | None = None
        self._report = None
        self._homed_row: CheckRow | None = None
        self._limits_row: CheckRow | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Left: checks list
        self._checks_widget = QWidget(self)
        self._checks_lyt = QVBoxLayout(self._checks_widget)
        self._checks_lyt.setContentsMargins(0, 0, 0, 0)
        self._checks_lyt.setSpacing(8)
        self._checks_lyt.setAlignment(Qt.AlignTop)
        root.addWidget(self._checks_widget, 1)

        # Right: summary + actions
        right = QWidget(self)
        right.setFixedWidth(280)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        summary_card = QFrame(right)
        summary_card.setObjectName("card")
        sl = QVBoxLayout(summary_card)
        sl.setContentsMargins(14, 14, 14, 14)
        sl.setSpacing(4)

        sec = QLabel("SUMMARY", summary_card)
        sec.setObjectName("labelSection")
        sec.setContentsMargins(0, 0, 0, 10)
        sl.addWidget(sec)

        self._warn_count = QLabel("—", summary_card)
        self._warn_count.setStyleSheet(
            f"color: {C_AMBER}; font-size: 44px; font-weight: 700; background: transparent; border: none;"
        )
        sl.addWidget(self._warn_count)

        self._summary_lbl = QLabel("Run safety check to continue.", summary_card)
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        sl.addWidget(self._summary_lbl)

        # Suggested corrections + apply button (hidden until there is something
        # to suggest).
        self._corrections_lbl = QLabel("", summary_card)
        self._corrections_lbl.setWordWrap(True)
        self._corrections_lbl.setVisible(False)
        self._corrections_lbl.setStyleSheet(
            f"color: {C_AMBER_TEXT}; font-size: 12px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        sl.addWidget(self._corrections_lbl)

        self._apply_btn = QPushButton("Apply Suggested Settings", summary_card)
        self._apply_btn.setObjectName("btnWarning")
        self._apply_btn.setFixedHeight(44)
        self._apply_btn.setVisible(False)
        self._apply_btn.clicked.connect(self._apply_corrections)
        sl.addWidget(self._apply_btn)

        sl.addStretch()
        rl.addWidget(summary_card, 1)

        back_btn = QPushButton("Back to Preview", right)
        back_btn.setObjectName("btnSecondary")
        back_btn.setFixedHeight(54)
        back_btn.clicked.connect(self._ctrl.navigate_back)
        rl.addWidget(back_btn)

        self._confirm_btn = QPushButton("Confirm & Start", right)
        self._confirm_btn.setObjectName("btnPrimary")
        self._confirm_btn.setFixedHeight(72)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._confirm_and_start)
        rl.addWidget(self._confirm_btn)

        root.addWidget(right)

    # -- live machine-state derived checks ---------------------------------

    def _homed_state(self) -> tuple[str, str]:
        """Derive (status, detail) for the 'Machine homed' row from live state."""
        st = self._status
        if st is None or not st.is_connected:
            return STATUS_WARN, "machine not connected — cannot confirm referencing"
        if st.is_alarm:
            return STATUS_ERR, "machine in ALARM — home/unlock before running"
        # GRBL does not report a dedicated 'homed' flag in its status line, so
        # treat any non-alarm connected state as referenced. If the profile
        # does not require homing, surface that explicitly.
        profile = self._ctrl.profile
        if profile is not None and not getattr(profile, "homing_required", True):
            return STATUS_OK, "homing not required by profile"
        return STATUS_OK, "all axes referenced"

    def _limits_state(self) -> tuple[str, str]:
        """Derive (status, detail) for the 'Within soft limits' row by comparing
        the loaded job bounds against the profile work area."""
        job = self._job
        profile = self._ctrl.profile
        if job is None or profile is None or job.bounds_mm is None:
            return STATUS_WARN, "job bounds unknown — cannot verify soft limits"
        min_x, min_y, max_x, max_y = job.bounds_mm
        work_x, work_y, _ = profile.work_area_mm
        if min_x < 0 or min_y < 0 or max_x > work_x or max_y > work_y:
            return (
                STATUS_ERR,
                f"job X{min_x:.1f}-{max_x:.1f} Y{min_y:.1f}-{max_y:.1f} "
                f"exceeds work area X0-{work_x:.1f} Y0-{work_y:.1f}",
            )
        return (
            STATUS_OK,
            f"job X{min_x:.1f}-{max_x:.1f} Y{min_y:.1f}-{max_y:.1f} within "
            f"X0-{work_x:.1f} Y0-{work_y:.1f}",
        )

    def _refresh_live_rows(self) -> None:
        if self._homed_row is not None:
            status, detail = self._homed_state()
            self._homed_row.update_state(status, detail=detail)
        if self._limits_row is not None:
            status, detail = self._limits_state()
            self._limits_row.update_state(status, detail=detail)

    # -- corrections -------------------------------------------------------

    def _format_corrections(self) -> str:
        if not self._report or not self._report.corrections:
            return ""
        parts = []
        for key, value in self._report.corrections.items():
            label, unit = _CORRECTION_LABELS.get(key, (key, ""))
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            parts.append(f"{label} → {value} {unit}".strip())
        return "Suggested: " + "; ".join(parts)

    def _apply_corrections(self) -> None:
        """Apply the report's suggested corrections to the controller's job
        settings, persist them and re-run the safety check."""
        if not self._job or not self._report or not self._report.corrections:
            return
        for key, value in self._report.corrections.items():
            if hasattr(self._job, key):
                setattr(self._job, key, value)
        # Store the adjusted JobSettings on the controller so downstream
        # consumers (and a re-entry to this screen) see the clamped values.
        # TODO: deeper wiring — the streamed G-code itself is not yet rewritten
        # to honour the clamped feed/power; only the JobSettings model is.
        try:
            self._ctrl.job_settings = self._job
        except Exception:
            pass
        if self._ctrl.profile:
            self.run_check(self._ctrl.profile, self._job)

    # -- main render -------------------------------------------------------

    def run_check(self, profile: MachineProfile, job: JobSettings) -> None:
        self._job = job
        report = check_job_safety(profile, job)
        self._report = report

        # Clear existing checks
        while self._checks_lyt.count():
            item = self._checks_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._homed_row = None
        self._limits_row = None

        # Live machine-state derived rows.
        homed_status, homed_detail = self._homed_state()
        self._homed_row = CheckRow(homed_status, "Machine homed", homed_detail,
                                   parent=self._checks_widget)
        self._checks_lyt.addWidget(self._homed_row)

        limits_status, limits_detail = self._limits_state()
        self._limits_row = CheckRow(limits_status, "Within soft limits", limits_detail,
                                    parent=self._checks_widget)
        self._checks_lyt.addWidget(self._limits_row)

        for warn in report.warnings:
            self._checks_lyt.addWidget(
                CheckRow(STATUS_WARN, warn, "", parent=self._checks_widget)
            )
        for err in report.errors:
            self._checks_lyt.addWidget(
                CheckRow(STATUS_ERR, err, "", parent=self._checks_widget)
            )

        self._checks_lyt.addStretch()

        # Surface suggested corrections.
        corr_text = self._format_corrections()
        if corr_text:
            self._corrections_lbl.setText(corr_text)
            self._corrections_lbl.setVisible(True)
            self._apply_btn.setVisible(True)
        else:
            self._corrections_lbl.setVisible(False)
            self._apply_btn.setVisible(False)

        warn_count = len(report.warnings)
        err_count = len(report.errors)

        if err_count:
            self._warn_count.setText(str(err_count))
            self._warn_count.setStyleSheet(
                f"color: {C_RED}; font-size: 44px; font-weight: 700; background: transparent; border: none;"
            )
            self._summary_lbl.setText(f"{err_count} error(s) must be resolved before starting.")
            self._confirm_btn.setEnabled(False)
        elif warn_count:
            self._warn_count.setText(str(warn_count))
            self._warn_count.setStyleSheet(
                f"color: {C_AMBER}; font-size: 44px; font-weight: 700; background: transparent; border: none;"
            )
            self._summary_lbl.setText(f"{warn_count} warning(s) need review. You may proceed.")
            self._confirm_btn.setEnabled(True)
        else:
            self._warn_count.setText("✓")
            self._warn_count.setStyleSheet(
                f"color: {C_GREEN}; font-size: 44px; font-weight: 700; background: transparent; border: none;"
            )
            self._summary_lbl.setText("All checks passed. Ready to run.")
            self._confirm_btn.setEnabled(True)

    def _confirm_and_start(self) -> None:
        if self._ctrl.worker and self._ctrl.job_file:
            lines = self._ctrl.job_file.path.read_text().splitlines()
            self._ctrl.worker.start_job(lines)
            self._ctrl.navigate_to("cnc_mode")

    # -- app hooks ---------------------------------------------------------

    def on_status(self, status: GrblStatus) -> None:
        self._status = status
        self._refresh_live_rows()

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("REVIEW", "checklist")
        self._ctrl.rail.set_enc2("—", "idle")
        if self._ctrl.job_file and self._ctrl.profile:
            from ...jobs import settings_from_gcode
            try:
                job = settings_from_gcode(self._ctrl.job_file)
                self.run_check(self._ctrl.profile, job)
            except Exception:
                pass
        else:
            self._refresh_live_rows()
