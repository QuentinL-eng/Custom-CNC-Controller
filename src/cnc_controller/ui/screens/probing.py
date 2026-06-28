"""Probing screen — Z probe, XYZ corner, edge finder, center/bore."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_GREEN_BG, C_GREEN_BORDER, C_RED, C_BTN_2ND,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus


# Probe kinds — index aligned with PROBE_TYPES below.
KIND_Z = "z"
KIND_CORNER = "corner"
KIND_EDGE = "edge"
KIND_CENTER = "center"

PROBE_TYPES = [
    (KIND_Z, "Probe Z", "Single touch to set Z zero on top of stock."),
    (KIND_CORNER, "Probe XYZ Corner", "Find corner + set X, Y, Z from one cycle."),
    (KIND_EDGE, "Edge Finder", "Touch a single X or Y edge of the stock."),
    (KIND_CENTER, "Center / Bore", "Locate center of a hole or boss."),
]


# ---------------------------------------------------------------------------
# Pure G-code macro generation (testable, no Qt)
# ---------------------------------------------------------------------------

def build_probe_commands(
    kind: str,
    thickness: float = 0.0,
    feed: float = 100.0,
    retract: float = 3.0,
    probe_distance: float = 25.0,
    corner: tuple[str, str] = ("front", "left"),
    edge_axis: str = "X",
    edge_dir: int = 1,
    tool_radius: float = 1.5,
) -> list[str]:
    """Return the GRBL command list for a probe cycle of ``kind``.

    The list contains ONLY the motion/probe commands; the work-offset update
    (``G10 L20 P1 ...``) is applied by the screen *after* the probe is
    confirmed to have triggered, so it is intentionally NOT emitted here.

    Parameters use millimetres / mm-per-minute. ``probe_distance`` is the
    maximum search travel; ``retract`` is the lift after a touch.

    ``corner`` is (front|back, left|right) and controls the X/Y search
    direction for the corner macro. ``edge_axis``/``edge_dir`` control the
    single-axis edge finder. ``tool_radius`` compensates the probe/tool tip
    radius for edge and corner touches.
    """
    feed_i = max(1, int(round(feed)))

    if kind == KIND_Z:
        # Plunge -Z to find the top of the stock, then retract.
        return [
            "G91",
            f"G38.2 Z-{probe_distance:.3f} F{feed_i}",
            f"G0 Z{retract:.3f}",
            "G90",
        ]

    if kind == KIND_EDGE:
        # Single edge touch along one axis. edge_dir +1 probes in +axis.
        axis = edge_axis.upper()
        if axis not in ("X", "Y"):
            axis = "X"
        sign = "" if edge_dir >= 0 else "-"
        back_sign = "-" if edge_dir >= 0 else ""
        return [
            "G91",
            f"G38.2 {axis}{sign}{probe_distance:.3f} F{feed_i}",
            f"G0 {axis}{back_sign}{retract:.3f}",
            "G90",
            # TODO: caller applies G10 L20 P1 {axis}{±tool_radius} after a
            # confirmed touch to set the work zero on the edge face.
        ]

    if kind == KIND_CORNER:
        # Best-effort XYZ corner: Z touch first, retract, then X then Y edges.
        front_back, left_right = corner
        x_sign = "" if left_right == "left" else "-"
        x_back = "-" if left_right == "left" else ""
        y_sign = "" if front_back == "front" else "-"
        y_back = "-" if front_back == "front" else ""
        return [
            "G91",
            # Z top of stock
            f"G38.2 Z-{probe_distance:.3f} F{feed_i}",
            f"G0 Z{retract:.3f}",
            # X edge
            f"G38.2 X{x_sign}{probe_distance:.3f} F{feed_i}",
            f"G0 X{x_back}{retract:.3f}",
            # Y edge
            f"G38.2 Y{y_sign}{probe_distance:.3f} F{feed_i}",
            f"G0 Y{y_back}{retract:.3f}",
            "G90",
            # TODO: a robust corner cycle needs to lift Z and reposition
            # between the X and Y edge touches using known stock geometry;
            # this sequence assumes the probe stays beside the corner.
        ]

    if kind == KIND_CENTER:
        # TODO: Center/bore finding requires four touches (+X,-X,+Y,-Y) with
        # midpoint math that GRBL alone cannot resolve. This emits a single
        # exploratory +X / -X pair as a starting point only.
        return [
            "G91",
            f"G38.2 X{probe_distance:.3f} F{feed_i}",
            f"G0 X-{retract:.3f}",
            f"G38.2 X-{probe_distance:.3f} F{feed_i}",
            f"G0 X{retract:.3f}",
            "G90",
            # TODO: capture both PRB X positions, compute midpoint, repeat for
            # Y, then G10 L20 P1 X<mid> Y<mid>.
        ]

    raise ValueError(f"unknown probe kind: {kind!r}")


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

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


def _stepper(label: str, parent: QWidget, on_minus, on_plus) -> tuple[QFrame, QLabel]:
    """A '- value +' editable numeric row. Returns (row, value_label)."""
    f = QFrame(parent)
    f.setStyleSheet("background: transparent; border: none;")
    rl = QHBoxLayout(f)
    rl.setContentsMargins(0, 6, 0, 6)
    rl.setSpacing(8)
    k = QLabel(label, f)
    k.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;")
    rl.addWidget(k)
    rl.addStretch()

    minus = QPushButton("−", f)
    minus.setObjectName("btnStep")
    minus.setFixedSize(38, 38)
    minus.clicked.connect(on_minus)
    rl.addWidget(minus)

    v = QLabel("—", f)
    v.setMinimumWidth(96)
    v.setAlignment(Qt.AlignCenter)
    v.setStyleSheet(f"color: {C_TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;")
    rl.addWidget(v)

    plus = QPushButton("+", f)
    plus.setObjectName("btnStep")
    plus.setFixedSize(38, 38)
    plus.clicked.connect(on_plus)
    rl.addWidget(plus)
    return f, v


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


class CornerCell(QFrame):
    """Clickable corner selector cell."""

    def __init__(self, front_back: str, left_right: str, active: bool,
                 on_click, parent: QWidget | None = None):
        super().__init__(parent)
        self.front_back = front_back
        self.left_right = left_right
        self._on_click = on_click
        self.setFixedSize(28, 28)
        self.set_active(active)

    def set_active(self, active: bool) -> None:
        self.setStyleSheet(
            f"background: {C_GREEN if active else C_CARD}; "
            f"border: 1px solid {C_GREEN if active else C_CARD_BORDER}; border-radius: 6px;"
        )

    def mousePressEvent(self, event):
        self._on_click(self)


class ProbingScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._selected = 0
        self._probe_cards: list[ProbeTypeCard] = []
        self._corner_cells: list[CornerCell] = []
        # Editable settings (seeded from profile in on_enter).
        self._thickness = 15.0
        self._feed = 100.0
        self._retract = 3.0
        # (front|back, left|right)
        self._corner: tuple[str, str] = ("front", "left")
        # Probe-cycle tracking for success verification.
        self._probe_pending = False
        self._prev_triggered = False
        self._baseline_probe_pos: tuple[float, float, float] | None = None
        self._build_ui()
        self._seed_from_profile()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

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
        for idx, (_kind, title, desc) in enumerate(PROBE_TYPES):
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
        # rows: 0=back, 1=front ; cols: 0=left, 1=right
        for r in range(2):
            for c in range(2):
                fb = "back" if r == 0 else "front"
                lr = "left" if c == 0 else "right"
                active = (fb == self._corner[0] and lr == self._corner[1])
                cell = CornerCell(fb, lr, active, self._select_corner, corner_frame)
                corner_grid.addWidget(cell, r, c)
                self._corner_cells.append(cell)
        cfl.addLayout(corner_grid)
        self._corner_lbl = QLabel(self._corner_text(), corner_frame)
        self._corner_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        cfl.addWidget(self._corner_lbl, 1)
        ll.addWidget(corner_frame)

        root.addWidget(left, 1)

        # Right: settings + start
        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        right.setFixedWidth(320)

        settings_card = QFrame(right)
        settings_card.setObjectName("card")
        sl = QVBoxLayout(settings_card)
        sl.setContentsMargins(13, 13, 13, 13)
        sl.setSpacing(0)

        sec2 = QLabel("SETTINGS", settings_card)
        sec2.setObjectName("labelSection")
        sec2.setContentsMargins(0, 0, 0, 9)
        sl.addWidget(sec2)

        plate_row, self._plate_val = _stepper(
            "Plate thickness", settings_card,
            lambda: self._bump_thickness(-0.5), lambda: self._bump_thickness(0.5),
        )
        sl.addWidget(_hdiv(settings_card))
        sl.addWidget(plate_row)
        sl.addWidget(_hdiv(settings_card))
        feed_row, self._feed_val = _stepper(
            "Probe feed", settings_card,
            lambda: self._bump_feed(-25), lambda: self._bump_feed(25),
        )
        sl.addWidget(feed_row)
        sl.addWidget(_hdiv(settings_card))
        retract_row, self._retract_val = _stepper(
            "Retract", settings_card,
            lambda: self._bump_retract(-0.5), lambda: self._bump_retract(0.5),
        )
        sl.addWidget(retract_row)
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

        # Live probe pin state.
        self._pin_row = _kv("Probe pin", "—", result_card)
        resl.addWidget(self._pin_row)
        resl.addWidget(_hdiv(result_card))
        self._z_touch_row = _kv("Last [PRB]", "—", result_card)
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
        self._refresh_settings()

    # ------------------------------------------------------------------
    # Selection / editing
    # ------------------------------------------------------------------

    def _select(self, idx: int) -> None:
        self._selected = idx
        for i, card in enumerate(self._probe_cards):
            card._update_style(i == idx)

    def _kind(self) -> str:
        return PROBE_TYPES[self._selected][0]

    def _corner_text(self) -> str:
        fb, lr = self._corner
        return f"{fb.capitalize()}-{lr} corner selected (X0 Y0)."

    def _select_corner(self, cell: CornerCell) -> None:
        self._corner = (cell.front_back, cell.left_right)
        for c in self._corner_cells:
            c.set_active(c.front_back == self._corner[0] and c.left_right == self._corner[1])
        self._corner_lbl.setText(self._corner_text())

    def _seed_from_profile(self) -> None:
        p = getattr(self._ctrl, "profile", None)
        if p is not None:
            self._thickness = float(p.probe_thickness_mm)
        self._refresh_settings()

    def _bump_thickness(self, delta: float) -> None:
        self._thickness = max(0.0, round(self._thickness + delta, 3))
        self._refresh_settings()

    def _bump_feed(self, delta: float) -> None:
        self._feed = max(1.0, round(self._feed + delta, 0))
        self._refresh_settings()

    def _bump_retract(self, delta: float) -> None:
        self._retract = max(0.0, round(self._retract + delta, 3))
        self._refresh_settings()

    def _refresh_settings(self) -> None:
        self._plate_val.setText(f"{self._thickness:.2f} mm")
        self._feed_val.setText(f"{self._feed:.0f} mm/min")
        self._retract_val.setText(f"{self._retract:.1f} mm")

    # ------------------------------------------------------------------
    # Probe cycle
    # ------------------------------------------------------------------

    def _run_probe(self) -> None:
        w = self._ctrl.worker
        if not w:
            return

        kind = self._kind()
        cmds = build_probe_commands(
            kind,
            thickness=self._thickness,
            feed=self._feed,
            retract=self._retract,
            corner=self._corner,
        )

        # Arm success tracking: do NOT apply the offset until we confirm a
        # trigger via on_status (probe_triggered True / [PRB:...:1]).
        self._probe_pending = True
        self._prev_triggered = False
        # Remember the last [PRB] position so a new result (hit OR miss) is
        # detectable even when probe_triggered stays False on a miss.
        self._baseline_probe_pos = None
        self._set_result_pending()

        for cmd in cmds:
            w.send_command(cmd)

    def _set_result_pending(self) -> None:
        self._z_set_row._val.setText("probing…")
        self._z_set_row._val.setStyleSheet(
            f"color: {C_MUTED}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
        )

    def _apply_offset(self, pz: float) -> None:
        """Apply the work-Z offset only after a confirmed Z touch."""
        w = self._ctrl.worker
        if not w:
            return
        if self._kind() == KIND_Z:
            w.send_command(f"G10 L20 P1 Z{self._thickness:.3f}")
            self._z_set_row._val.setText("OK ✓")
            self._z_set_row._val.setStyleSheet(
                f"color: {C_GREEN}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
            )
        else:
            # Non-Z kinds report the touch but do not auto-apply offsets yet.
            self._z_set_row._val.setText("touch OK ✓")
            self._z_set_row._val.setStyleSheet(
                f"color: {C_GREEN}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
            )

    def _show_failure(self) -> None:
        self._z_set_row._val.setText("no contact ✗")
        self._z_set_row._val.setStyleSheet(
            f"color: {C_RED}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
        )

    # ------------------------------------------------------------------
    # Status hooks
    # ------------------------------------------------------------------

    def on_status(self, status: GrblStatus) -> None:
        self._start_btn.setEnabled(status.is_idle and not self._probe_pending)

        # Live probe pin / last [PRB] readout.
        triggered = bool(status.probe_triggered)
        self._pin_row._val.setText("TRIGGERED" if triggered else "open")
        self._pin_row._val.setStyleSheet(
            f"color: {C_GREEN if triggered else C_MUTED}; font-size: 14px; "
            f"font-weight: 700; background: transparent; border: none;"
        )
        pos = status.probe_pos
        px, py, pz = pos
        self._z_touch_row._val.setText(f"{px:.2f}, {py:.2f}, {pz:.2f}")

        # Verify probe success while a cycle is pending. A confirmed touch sets
        # probe_triggered True. A miss reports [PRB:...:0] (triggered False) but
        # still updates probe_pos, so a change from the captured baseline means
        # the cycle finished without contact.
        if self._probe_pending:
            if self._baseline_probe_pos is None:
                self._baseline_probe_pos = pos
            if triggered and not self._prev_triggered:
                self._probe_pending = False
                self._apply_offset(pz)
            elif not triggered and pos != self._baseline_probe_pos:
                self._probe_pending = False
                self._show_failure()

        self._prev_triggered = triggered

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("JOG · Z", "step 0.1 mm")
        self._ctrl.rail.set_enc2("—", "idle")
        self._seed_from_profile()
