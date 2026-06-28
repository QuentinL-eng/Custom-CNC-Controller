"""Probing screen — Z probe, XYZ corner, edge finder."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_GREEN_BG, C_GREEN_BORDER, C_RED,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus


PROBE_TYPES = [
    ("Probe Z", "Single touch to set Z zero on top of stock."),
    ("Probe XYZ Corner", "Find corner + set X, Y, Z from one cycle."),
    ("Edge Finder", "Touch a single X or Y edge of the stock."),
    ("Center / Bore", "Locate center of a hole or boss."),
]


def _kv(key: str, val: str, parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet("background: transparent; border: none;")
    rl = QHBoxLayout(f)
    rl.setContentsMargins(0, 6, 0, 6)
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


class ProbeTypeCard(QFrame):
    def __init__(self, title: str, desc: str, selected: bool,
                 on_click, parent: QWidget | None = None):
        super().__init__(parent)
        self._on_click = on_click
        self._update_style(selected)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(14, 14, 14, 14)
        lyt.setSpacing(8)
        lyt.setAlignment(Qt.AlignTop)

        t = QLabel(title, self)
        t.setStyleSheet(
            f"color: {C_TEXT}; font-size: 18px; font-weight: 700; background: transparent; border: none;"
        )
        d = QLabel(desc, self)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;")
        lyt.addWidget(t)
        lyt.addWidget(d)

    def _update_style(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(
                f"QFrame {{ background: {C_GREEN_BG}; border: 2px solid {C_GREEN}; border-radius: {CARD_RADIUS}px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {C_CARD}; border: 1px solid {C_CARD_BORDER}; border-radius: {CARD_RADIUS}px; }}"
            )

    def mousePressEvent(self, event):
        self._on_click()


class ProbingScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._selected = 0
        self._probe_cards: list[ProbeTypeCard] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Left: probe type grid
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        sec = QLabel("PROBE TYPE", left)
        sec.setObjectName("labelSection")
        ll.addWidget(sec)

        grid = QGridLayout()
        grid.setSpacing(10)
        for idx, (title, desc) in enumerate(PROBE_TYPES):
            card = ProbeTypeCard(title, desc, idx == 0, lambda i=idx: self._select(i), left)
            grid.addWidget(card, idx // 2, idx % 2)
            self._probe_cards.append(card)
        for i in range(2):
            grid.setRowStretch(i, 1)
            grid.setColumnStretch(i, 1)
        ll.addLayout(grid, 1)

        # Corner selector
        corner_frame = QFrame(left)
        corner_frame.setObjectName("card")
        cfl = QHBoxLayout(corner_frame)
        cfl.setContentsMargins(12, 12, 12, 12)
        cfl.setSpacing(14)

        corner_lbl = QLabel("CORNER", corner_frame)
        corner_lbl.setObjectName("labelSection")
        cfl.addWidget(corner_lbl)

        corner_grid = QGridLayout()
        corner_grid.setSpacing(5)
        for r in range(2):
            for c in range(2):
                cell = QFrame(corner_frame)
                active = (r == 0 and c == 0)
                cell.setFixedSize(28, 28)
                cell.setStyleSheet(
                    f"background: {C_GREEN if active else C_CARD}; "
                    f"border: 1px solid {C_CARD_BORDER}; border-radius: 6px;"
                )
                corner_grid.addWidget(cell, r, c)
        cfl.addLayout(corner_grid)
        cfl.addWidget(QLabel("Front-left corner selected (X0 Y0).", corner_frame), 1)
        ll.addWidget(corner_frame)

        root.addWidget(left, 1)

        # Right: settings + start
        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        right.setFixedWidth(300)

        settings_card = QFrame(right)
        settings_card.setObjectName("card")
        sl = QVBoxLayout(settings_card)
        sl.setContentsMargins(13, 13, 13, 13)
        sl.setSpacing(0)

        sec2 = QLabel("SETTINGS", settings_card)
        sec2.setObjectName("labelSection")
        sec2.setContentsMargins(0, 0, 0, 9)
        sl.addWidget(sec2)

        self._plate_row = _kv("Plate thickness", "—", settings_card)
        sl.addWidget(_hdiv(settings_card))
        sl.addWidget(self._plate_row)
        sl.addWidget(_hdiv(settings_card))
        sl.addWidget(_kv("Probe feed", "100 mm/min", settings_card))
        sl.addWidget(_hdiv(settings_card))
        sl.addWidget(_kv("Retract", "3.0 mm", settings_card))
        rl.addWidget(settings_card)

        result_card = QFrame(right)
        result_card.setObjectName("card")
        resl = QVBoxLayout(result_card)
        resl.setContentsMargins(13, 13, 13, 13)
        resl.setSpacing(0)

        sec3 = QLabel("LAST RESULT", result_card)
        sec3.setObjectName("labelSection")
        sec3.setContentsMargins(0, 0, 0, 9)
        resl.addWidget(sec3)

        self._z_touch_row = _kv("Z touch", "—", result_card)
        resl.addWidget(_hdiv(result_card))
        resl.addWidget(self._z_touch_row)
        resl.addWidget(_hdiv(result_card))
        self._z_set_row = _kv("Set Z zero", "—", result_card)
        resl.addWidget(self._z_set_row)
        rl.addWidget(result_card, 1)

        # Start probe button
        self._start_btn = QPushButton("Start Probe", right)
        self._start_btn.setObjectName("btnPrimary")
        self._start_btn.setFixedHeight(66)
        self._start_btn.clicked.connect(self._run_probe)
        rl.addWidget(self._start_btn)

        root.addWidget(right)

    def _select(self, idx: int) -> None:
        self._selected = idx
        for i, card in enumerate(self._probe_cards):
            card._update_style(i == idx)

    def _run_probe(self) -> None:
        w = self._ctrl.worker
        if not w:
            return
        p = self._ctrl.profile
        if p:
            thickness = p.probe_thickness_mm
            self._plate_row._val.setText(f"{thickness:.2f} mm")
        else:
            thickness = 15.0

        # GRBL Z probe macro
        w.send_command("G91")
        w.send_command(f"G38.2 Z-25 F100")
        w.send_command(f"G10 L20 P1 Z{thickness:.3f}")
        w.send_command("G0 Z3")
        w.send_command("G90")

    def on_status(self, status: GrblStatus) -> None:
        self._start_btn.setEnabled(status.is_idle)
        if status.probe_triggered:
            pz = status.probe_pos[2]
            self._z_touch_row._val.setText(f"{pz:.3f} mm")
            self._z_touch_row._val.setStyleSheet(
                f"color: {C_GREEN}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
            )
            self._z_set_row._val.setText("OK ✓")
            self._z_set_row._val.setStyleSheet(
                f"color: {C_GREEN}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
            )

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("JOG · Z", "step 0.1 mm")
        self._ctrl.rail.set_enc2("—", "idle")
        p = self._ctrl.profile
        if p:
            self._plate_row._val.setText(f"{p.probe_thickness_mm:.2f} mm")
