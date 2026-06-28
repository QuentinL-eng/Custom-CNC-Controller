"""Home screen — mode picker grid and machine status panel."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_BLUE, C_AMBER, C_BG,
    C_GREEN_BG, C_GREEN_BORDER, C_GREEN_TEXT,
    C_AMBER_BG, C_AMBER_BORDER, C_AMBER_TEXT,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------

def _divider(parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C_DIVIDER}; border: none;")
    return f


def _kv(key: str, val: str, parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet("background: transparent; border: none;")
    row = QHBoxLayout(f)
    row.setContentsMargins(0, 5, 0, 5)
    k = QLabel(key, f)
    k.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;")
    v = QLabel(val, f)
    v.setStyleSheet(f"color: {C_TEXT}; font-size: 13px; font-weight: 600; background: transparent; border: none;")
    row.addWidget(k)
    row.addStretch()
    row.addWidget(v)
    f._val = v
    return f


class TileButton(QPushButton):
    """Large home-screen tile with color accent bar."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        accent: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("btnTile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        inner = QWidget(self)
        inner.setAttribute(Qt.WA_TransparentForMouseEvents)
        lyt = QVBoxLayout(inner)
        lyt.setContentsMargins(14, 14, 14, 14)
        lyt.setSpacing(0)

        accent_bar = QFrame(inner)
        accent_bar.setFixedSize(42, 6)
        accent_bar.setStyleSheet(
            f"background: {accent}; border-radius: 3px; border: none;"
        )
        lyt.addWidget(accent_bar)
        lyt.addStretch()

        title_lbl = QLabel(title, inner)
        title_lbl.setStyleSheet(
            f"color: {C_TEXT}; font-size: 21px; font-weight: 700; background: transparent; border: none;"
        )
        lyt.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle, inner)
        sub_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        lyt.addWidget(sub_lbl)

        self._inner = inner

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._inner.setGeometry(0, 0, self.width(), self.height())


class SmallTile(QPushButton):
    """Smaller grid tile (Files, Settings, etc.)."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("btnTile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        inner = QWidget(self)
        inner.setAttribute(Qt.WA_TransparentForMouseEvents)
        lyt = QVBoxLayout(inner)
        lyt.setContentsMargins(13, 0, 13, 0)
        lyt.setAlignment(Qt.AlignVCenter)
        lyt.setSpacing(4)

        t = QLabel(title, inner)
        t.setStyleSheet(
            f"color: {C_TEXT}; font-size: 17px; font-weight: 700; background: transparent; border: none;"
        )
        s = QLabel(subtitle, inner)
        s.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; background: transparent; border: none;"
        )
        lyt.addWidget(t)
        lyt.addWidget(s)
        self._inner = inner

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._inner.setGeometry(0, 0, self.width(), self.height())


# ---------------------------------------------------------------------------
# Home screen
# ---------------------------------------------------------------------------

class HomeScreen(QWidget):
    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = controller
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # ---------- Left: tile grid ----------
        grid_frame = QWidget(self)
        grid = QGridLayout(grid_frame)
        grid.setSpacing(12)

        # Large tiles (row 0, 128px implied by stretch)
        self._tile_cnc = TileButton("CNC Routing", "Mill · route · drill", C_GREEN, self)
        self._tile_laser = TileButton("Laser", "Engrave · cut", C_BLUE, self)
        self._tile_pcb = TileButton("PCB Wizard", "Gerber → toolpaths", C_AMBER, self)
        grid.addWidget(self._tile_cnc, 0, 0)
        grid.addWidget(self._tile_laser, 0, 1)
        grid.addWidget(self._tile_pcb, 0, 2)

        # Small tiles rows 1–2
        small = [
            ("Files", "USB · SD · internal"),
            ("Probing", "Z · XYZ · edge"),
            ("Machine Setup", "Home · offsets"),
            ("Materials", "Feeds · speeds"),
            ("Tools", "Library · offsets"),
            ("Settings", "Machine · display"),
        ]
        self._small_tiles = []
        for i, (title, sub) in enumerate(small):
            tile = SmallTile(title, sub, self)
            row, col = (i // 3) + 1, i % 3
            grid.addWidget(tile, row, col)
            self._small_tiles.append(tile)

        grid.setRowStretch(0, 10)
        grid.setRowStretch(1, 6)
        grid.setRowStretch(2, 6)

        root.addWidget(grid_frame, 17)

        # ---------- Right: sidebar ----------
        sidebar = QWidget(self)
        sb_lyt = QVBoxLayout(sidebar)
        sb_lyt.setContentsMargins(0, 0, 0, 0)
        sb_lyt.setSpacing(12)
        sidebar.setFixedWidth(296)

        # Machine card
        machine_card = QFrame(self)
        machine_card.setObjectName("card")
        mc_lyt = QVBoxLayout(machine_card)
        mc_lyt.setContentsMargins(14, 14, 14, 14)
        mc_lyt.setSpacing(0)

        sec = QLabel("MACHINE", machine_card)
        sec.setObjectName("labelSection")
        sec.setContentsMargins(0, 0, 0, 10)
        mc_lyt.addWidget(sec)

        # Homing warning banner
        self._homing_banner = QFrame(machine_card)
        self._homing_banner.setStyleSheet(
            f"background: {C_AMBER_BG}; border: 1px solid {C_AMBER_BORDER}; border-radius: 9px;"
        )
        hbl = QHBoxLayout(self._homing_banner)
        hbl.setContentsMargins(10, 10, 10, 10)
        hbl.setSpacing(10)
        warn_dot = QLabel("!", self._homing_banner)
        warn_dot.setFixedSize(22, 22)
        warn_dot.setAlignment(Qt.AlignCenter)
        warn_dot.setStyleSheet(
            f"background: {C_AMBER}; color: white; border-radius: 11px; "
            f"font-size: 14px; font-weight: 700; border: none;"
        )
        hbl.addWidget(warn_dot)
        hbl.addWidget(QLabel("Homing required", self._homing_banner))
        mc_lyt.addWidget(self._homing_banner)
        mc_lyt.addSpacing(12)

        # Home All Axes button
        self._home_btn = QPushButton("Home All Axes", machine_card)
        self._home_btn.setObjectName("btnPrimary")
        self._home_btn.setFixedHeight(54)
        self._home_btn.clicked.connect(self._on_home)
        mc_lyt.addWidget(self._home_btn)
        mc_lyt.addSpacing(12)

        # Position row
        mc_lyt.addWidget(_divider(machine_card))
        pos_row = _kv("Position", "X — · Y — · Z —", machine_card)
        self._pos_label = pos_row._val
        mc_lyt.addWidget(pos_row)

        mc_lyt.addWidget(_divider(machine_card))
        sp_row = _kv("Spindle", "Off", machine_card)
        mc_lyt.addWidget(sp_row)

        mc_lyt.addWidget(_divider(machine_card))
        mc_lyt.addWidget(_kv("WCS", "G54", machine_card))

        sb_lyt.addWidget(machine_card)

        # Recent jobs card
        jobs_card = QFrame(self)
        jobs_card.setObjectName("card")
        jc_lyt = QVBoxLayout(jobs_card)
        jc_lyt.setContentsMargins(14, 14, 14, 14)
        jc_lyt.setSpacing(0)

        sec2 = QLabel("RECENT JOBS", jobs_card)
        sec2.setObjectName("labelSection")
        sec2.setContentsMargins(0, 0, 0, 10)
        jc_lyt.addWidget(sec2)

        recent = [
            (C_GREEN, "bracket_v3.nc", "CNC · 29 min · today"),
            (C_BLUE, "logo_engrave.svg", "Laser · 8 min · yest."),
            (C_AMBER, "board_top.gbr", "PCB · 41 min · Mon"),
        ]
        for color, name, meta in recent:
            jc_lyt.addWidget(_divider(jobs_card))
            row = QFrame(jobs_card)
            row.setStyleSheet("background: transparent; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 9, 0, 9)
            rl.setSpacing(10)
            dot = QFrame(row)
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color}; border-radius: 2px; border: none;")
            rl.addWidget(dot)
            info = QWidget(row)
            info.setStyleSheet("background: transparent; border: none;")
            il = QVBoxLayout(info)
            il.setContentsMargins(0, 0, 0, 0)
            il.setSpacing(0)
            il.addWidget(QLabel(name, info))
            m = QLabel(meta, info)
            m.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;")
            il.addWidget(m)
            rl.addWidget(info)
            jc_lyt.addWidget(row)

        sb_lyt.addWidget(jobs_card, 1)
        root.addWidget(sidebar, 0)

        # Wire up tile signals
        self._tile_cnc.clicked.connect(lambda: self._ctrl.navigate_to("cnc_mode"))
        self._tile_laser.clicked.connect(lambda: self._ctrl.navigate_to("laser_mode"))
        self._tile_pcb.clicked.connect(lambda: self._ctrl.navigate_to("pcb"))
        self._small_tiles[0].clicked.connect(lambda: self._ctrl.navigate_to("file_browser"))
        self._small_tiles[1].clicked.connect(lambda: self._ctrl.navigate_to("probing"))
        self._small_tiles[2].clicked.connect(lambda: self._ctrl.navigate_to("cnc_mode"))
        self._small_tiles[3].clicked.connect(lambda: self._ctrl.navigate_to("file_browser"))
        self._small_tiles[4].clicked.connect(lambda: self._ctrl.navigate_to("file_browser"))
        self._small_tiles[5].clicked.connect(lambda: self._ctrl.navigate_to("settings"))

    def on_status(self, status: GrblStatus) -> None:
        """Update machine panel from GRBL status."""
        need_home = (
            self._ctrl.profile.homing_required
            and (status.is_alarm or status.state == "Disconnected")
        )
        self._homing_banner.setVisible(need_home)
        self._home_btn.setVisible(need_home)

        x, y, z = status.wpos
        if status.is_connected:
            self._pos_label.setText(f"X {x:.3f} · Y {y:.3f} · Z {z:.3f}")
        else:
            self._pos_label.setText("X — · Y — · Z —")

    def _on_home(self) -> None:
        if self._ctrl.worker:
            self._ctrl.worker.home_all()

    def on_enter(self) -> None:
        """Called when this screen becomes active."""
        self._ctrl.rail.set_enc1("NAV", "menu")
        self._ctrl.rail.set_enc2("—", "idle")
        self._ctrl.rail.ctx_btn.setVisible(False)
