"""Settings screen."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_GREEN_BG, C_GREEN_BORDER, C_GREEN_TEXT,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus


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


class SettingsScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._active_section = "Display"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Left nav
        nav = QFrame(self)
        nav.setObjectName("card")
        nav.setFixedWidth(240)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(8, 8, 8, 8)
        nl.setSpacing(3)

        self._nav_btns: list[QPushButton] = []
        for section in SECTIONS:
            btn = QPushButton(section, nav)
            btn.setFixedHeight(46)
            btn.clicked.connect(lambda _, s=section: self._show_section(s))
            self._nav_btns.append(btn)
            nl.addWidget(btn)
        nl.addStretch()
        root.addWidget(nav)

        self._refresh_nav()

        # Right: content area
        self._content = QFrame(self)
        self._content.setObjectName("card")
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(14)

        self._content_sec = QLabel("DISPLAY", self._content)
        self._content_sec.setObjectName("labelSection")
        cl.addWidget(self._content_sec)

        # Brightness row
        br = QHBoxLayout()
        br.addWidget(QLabel("Brightness", self._content))
        br.addStretch()
        br.addWidget(QLabel("80%", self._content))
        cl.addLayout(br)

        # Theme toggle
        theme_row = QHBoxLayout()
        theme_info = QWidget(self._content)
        theme_info.setStyleSheet("background: transparent; border: none;")
        til = QVBoxLayout(theme_info)
        til.setContentsMargins(0, 0, 0, 0)
        til.addWidget(QLabel("Theme", theme_info))
        sub = QLabel("high-brightness shop display", theme_info)
        sub.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;")
        til.addWidget(sub)
        theme_row.addWidget(theme_info, 1)
        theme_toggle = QFrame(self._content)
        theme_toggle.setStyleSheet(
            f"QFrame {{ border: 1px solid {C_CARD_BORDER}; border-radius: 8px; background: transparent; }}"
        )
        ttl = QHBoxLayout(theme_toggle)
        ttl.setContentsMargins(0, 0, 0, 0)
        ttl.setSpacing(0)
        light = QLabel("Light", theme_toggle)
        light.setAlignment(Qt.AlignCenter)
        light.setFixedSize(60, 36)
        light.setStyleSheet(
            f"background: {C_GREEN}; color: white; font-size: 13px; font-weight: 700; border-radius: 7px;"
        )
        dark = QLabel("Dark", theme_toggle)
        dark.setAlignment(Qt.AlignCenter)
        dark.setFixedSize(50, 36)
        dark.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; font-weight: 700; background: transparent;")
        ttl.addWidget(light)
        ttl.addWidget(dark)
        theme_row.addWidget(theme_toggle)
        cl.addLayout(theme_row)

        # Screen timeout
        to_row = QHBoxLayout()
        to_info = QWidget(self._content)
        to_info.setStyleSheet("background: transparent; border: none;")
        toil = QVBoxLayout(to_info)
        toil.setContentsMargins(0, 0, 0, 0)
        toil.addWidget(QLabel("Screen timeout", to_info))
        tos = QLabel("dim after inactivity", to_info)
        tos.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;")
        toil.addWidget(tos)
        to_row.addWidget(to_info, 1)
        to_row.addWidget(QLabel("Never", self._content))
        cl.addLayout(to_row)

        cl.addStretch()

        # Shutdown button at bottom
        shutdown_btn = QPushButton("Shutdown", self._content)
        shutdown_btn.setObjectName("btnDanger")
        shutdown_btn.setFixedHeight(54)
        shutdown_btn.clicked.connect(self._shutdown)
        cl.addWidget(shutdown_btn)

        root.addWidget(self._content, 1)

    def _show_section(self, section: str) -> None:
        self._active_section = section
        self._refresh_nav()
        self._content_sec.setText(section.upper())

    def _refresh_nav(self) -> None:
        for btn, section in zip(self._nav_btns, SECTIONS):
            if section == self._active_section:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {C_GREEN_BG}; color: {C_GREEN_TEXT}; "
                    f"border: 1px solid {C_GREEN_BORDER}; border-radius: 9px; "
                    f"font-size: 15px; font-weight: 700; text-align: left; padding-left: 14px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {C_MUTED}; border: none; "
                    f"font-size: 15px; font-weight: 600; text-align: left; padding-left: 14px; }}"
                )

    def _shutdown(self) -> None:
        import subprocess
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"])
        except Exception:
            pass

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("SELECT", "setting")
        self._ctrl.rail.set_enc2("ADJUST", "value")
