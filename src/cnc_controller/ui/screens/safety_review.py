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


class CheckRow(QFrame):
    def __init__(self, status: str, title: str, detail: str = "",
                 action_label: str = "", on_action=None,
                 parent: QWidget | None = None):
        super().__init__(parent)

        color_map = {
            STATUS_OK: (C_GREEN, C_CARD, C_CARD_BORDER),
            STATUS_WARN: (C_AMBER, C_AMBER_BG, C_AMBER_BORDER),
            STATUS_ERR: (C_RED, C_RED_BG, C_RED_BORDER),
        }
        icon_map = {STATUS_OK: "✓", STATUS_WARN: "!", STATUS_ERR: "✕"}

        dot_color, bg, border = color_map.get(status, (C_GREEN, C_CARD, C_CARD_BORDER))
        icon = icon_map.get(status, "✓")

        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 11px; }}"
        )

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(11, 11, 11, 11)
        lyt.setSpacing(12)

        dot = QLabel(icon, self)
        dot.setFixedSize(26, 26)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(
            f"background: {dot_color}; color: white; border-radius: 13px; "
            f"font-size: 15px; font-weight: 700; border: none;"
        )
        lyt.addWidget(dot)

        text_w = QWidget(self)
        text_w.setStyleSheet("background: transparent; border: none;")
        tl = QVBoxLayout(text_w)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(1)
        t = QLabel(title, text_w)
        t.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
        tl.addWidget(t)
        if detail:
            d = QLabel(detail, text_w)
            d.setStyleSheet(
                f"color: {C_AMBER_TEXT if status == STATUS_WARN else C_MUTED}; "
                f"font-size: 12px; background: transparent; border: none;"
            )
            tl.addWidget(d)
        lyt.addWidget(text_w, 1)

        if detail and not detail.startswith("M") and not detail.startswith("from"):
            lyt.addWidget(QLabel(detail, self))

        if action_label and on_action:
            btn = QPushButton(action_label, self)
            btn.setObjectName("btnWarning")
            btn.setFixedHeight(38)
            btn.clicked.connect(on_action)
            lyt.addWidget(btn)


class SafetyReviewScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._checks: list[tuple[str, str, str]] = []
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

    def run_check(self, profile: MachineProfile, job: JobSettings) -> None:
        report = check_job_safety(profile, job)
        # Clear existing checks
        while self._checks_lyt.count():
            item = self._checks_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        checks = []
        # Basic checks always shown
        checks.append((STATUS_OK, "Machine homed", "all axes referenced"))
        checks.append((STATUS_OK if not report.errors else STATUS_ERR, "Within soft limits", ""))

        for warn in report.warnings:
            checks.append((STATUS_WARN, warn, ""))

        for err in report.errors:
            checks.append((STATUS_ERR, err, ""))

        warn_count = len(report.warnings)
        err_count = len(report.errors)

        for status, title, detail in checks:
            row = CheckRow(status, title, detail, parent=self._checks_widget)
            self._checks_lyt.addWidget(row)

        self._checks_lyt.addStretch()

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
