"""Splash / loading screen shown while the app initialises."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QProgressBar, QFrame,
    QSizePolicy,
)
from ..theme import C_GREEN, C_TEXT, C_DIM, C_MUTED, C_BG, C_BORDER, C_CARD


class SplashScreen(QWidget):
    """Full-screen splash that shows startup progress."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {C_BG};")

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        # Logo lockup
        logo_box = QFrame(self)
        logo_box.setFixedSize(84, 84)
        logo_box.setStyleSheet(
            f"QFrame {{ border: 3px solid {C_TEXT}; border-radius: 18px; background: transparent; }}"
        )
        # inner dot
        dot = QFrame(logo_box)
        dot.setFixedSize(34, 34)
        dot.setStyleSheet(f"QFrame {{ border: 3px solid {C_GREEN}; border-radius: 17px; background: transparent; }}")
        dot.move(22, 22)

        wordmark = QLabel("CNC<span style='color:#109a5b'>·</span>CTRL", self)
        wordmark.setTextFormat(Qt.RichText)
        wordmark.setAlignment(Qt.AlignCenter)
        wordmark.setStyleSheet(
            f"color: {C_TEXT}; font-size: 30px; font-weight: 700; "
            f"letter-spacing: 5px; background: transparent; border: none;"
        )

        tagline = QLabel("GRBL MACHINE CONTROLLER", self)
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(
            f"color: {C_DIM}; font-size: 12px; font-weight: 600; "
            f"letter-spacing: 3px; background: transparent; border: none;"
        )

        inner = QVBoxLayout()
        inner.setSpacing(16)
        inner.setAlignment(Qt.AlignCenter)
        inner.addWidget(logo_box, 0, Qt.AlignCenter)
        inner.addWidget(wordmark)
        inner.addWidget(tagline)

        self._status_lbl = QLabel("Starting controller…", self)
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet(
            f"color: {C_TEXT}; font-size: 17px; font-weight: 600; "
            f"background: transparent; border: none;"
        )

        self._bar = QProgressBar(self)
        self._bar.setFixedWidth(440)
        self._bar.setFixedHeight(8)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)

        self._pct_lbl = QLabel("0%", self)
        self._pct_lbl.setAlignment(Qt.AlignCenter)
        self._pct_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )

        root.addLayout(inner)
        root.addSpacing(42)
        root.addWidget(self._status_lbl)
        root.addSpacing(16)
        root.addWidget(self._bar, 0, Qt.AlignCenter)
        root.addSpacing(11)
        root.addWidget(self._pct_lbl)

    def set_progress(self, pct: int, message: str = "") -> None:
        self._bar.setValue(max(0, min(100, pct)))
        self._pct_lbl.setText(f"Loading interface · {pct}%")
        if message:
            self._status_lbl.setText(message)
