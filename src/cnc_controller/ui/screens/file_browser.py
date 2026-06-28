"""File browser screen."""
from __future__ import annotations

import os
from pathlib import Path

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_BLUE, C_AMBER, C_BTN_2ND,
    C_GREEN_BG, C_BLUE_BG, C_AMBER_BG,
    CARD_RADIUS, BTN_RADIUS,
)
from ...grbl_worker import GrblStatus


EXT_COLORS = {
    ".nc": (C_GREEN_BG, "#0c7a45", "NC"),
    ".gcode": (C_GREEN_BG, "#0c7a45", "GC"),
    ".gc": (C_GREEN_BG, "#0c7a45", "GC"),
    ".tap": (C_GREEN_BG, "#0c7a45", "TAP"),
    ".svg": (C_BLUE_BG, "#0f5fb0", "SVG"),
    ".dxf": (C_BLUE_BG, "#0f5fb0", "DXF"),
    ".gbr": (C_AMBER_BG, "#8a5a06", "GBR"),
}


def _badge(ext: str) -> tuple[str, str, str]:
    key = ext.lower()
    return EXT_COLORS.get(key, ("#f6f8f9", "#5c636b", ext.lstrip(".").upper()[:3]))


class FileRow(QFrame):
    def __init__(self, path: Path, on_select, parent: QWidget | None = None):
        super().__init__(parent)
        self._path = path
        self._on_select = on_select
        self._selected = False
        self._update_style()

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(14, 13, 14, 13)
        lyt.setSpacing(12)

        bg, fg, label = _badge(path.suffix)
        badge = QLabel(label, self)
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 7px; "
            f"font-size: 11px; font-weight: 700; border: none;"
        )
        lyt.addWidget(badge)

        info = QWidget(self)
        info.setStyleSheet("background: transparent; border: none;")
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(1)
        name = QLabel(path.name, info)
        name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 600; background: transparent; border: none;"
        )
        size_str = self._fmt_size(path)
        meta = QLabel(size_str, info)
        meta.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;")
        il.addWidget(name)
        il.addWidget(meta)
        lyt.addWidget(info, 1)

    def _update_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"QFrame {{ background: #f3f8fe; border-bottom: 1px solid {C_CARD_BORDER}; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {C_CARD}; border-bottom: 1px solid {C_DIVIDER}; }}"
            )

    def _fmt_size(self, path: Path) -> str:
        try:
            sz = path.stat().st_size
            if sz < 1024:
                return f"{sz} B"
            elif sz < 1024 ** 2:
                return f"{sz//1024} KB"
            else:
                return f"{sz//1024**2} MB"
        except OSError:
            return "—"

    def select(self, selected: bool) -> None:
        self._selected = selected
        self._update_style()

    def mousePressEvent(self, event):
        self._on_select(self._path)


class FileBrowserScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._selected: Path | None = None
        self._rows: list[FileRow] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(11)

        # Source tabs + search
        top = QHBoxLayout()
        top.setSpacing(9)
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self._src_btns: list[QPushButton] = []
        for label in ("USB", "SD Card", "Internal"):
            btn = QPushButton(label, self)
            btn.setFixedHeight(42)
            btn.setObjectName("btnSecondary")
            tabs.addWidget(btn)
            self._src_btns.append(btn)
        self._src_btns[0].setStyleSheet(
            f"QPushButton {{ background: {C_TEXT}; color: white; border: none; "
            f"border-radius: {BTN_RADIUS}px; font-size: 14px; font-weight: 700; padding: 0 16px; }}"
        )
        top.addLayout(tabs)

        search = QFrame(self)
        search.setStyleSheet(
            f"QFrame {{ background: {C_CARD}; border: 1px solid {C_CARD_BORDER}; border-radius: {BTN_RADIUS}px; }}"
        )
        sl = QHBoxLayout(search)
        sl.setContentsMargins(13, 0, 13, 0)
        sl.addWidget(QLabel("⌕", search))
        placeholder = QLabel("Search files…", search)
        placeholder.setStyleSheet(f"color: {C_DIM}; font-size: 14px; background: transparent; border: none;")
        sl.addWidget(placeholder, 1)
        search.setFixedHeight(42)
        top.addWidget(search, 1)
        root.addLayout(top)

        # Main area
        content = QHBoxLayout()
        content.setSpacing(11)

        # File list
        self._list_frame = QFrame(self)
        self._list_frame.setObjectName("card")
        self._list_frame.setStyleSheet(
            f"QFrame#card {{ border-radius: {CARD_RADIUS}px; background: {C_CARD}; "
            f"border: 1px solid {C_CARD_BORDER}; }}"
        )
        self._list_lyt = QVBoxLayout(self._list_frame)
        self._list_lyt.setContentsMargins(0, 0, 0, 0)
        self._list_lyt.setSpacing(0)
        content.addWidget(self._list_frame, 1)

        # Preview sidebar
        preview = QWidget(self)
        preview.setFixedWidth(248)
        pl = QVBoxLayout(preview)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)

        prev_card = QFrame(preview)
        prev_card.setObjectName("card")
        pcl = QVBoxLayout(prev_card)
        pcl.setContentsMargins(12, 12, 12, 12)
        pcl.setSpacing(8)

        ps = QLabel("PREVIEW", prev_card)
        ps.setObjectName("labelSection")
        pcl.addWidget(ps)

        thumb = QFrame(prev_card)
        thumb.setStyleSheet(
            f"QFrame {{ background: {C_BTN_2ND}; border: 1px dashed {C_CARD_BORDER}; border-radius: 8px; }}"
        )
        thumb.setFixedHeight(100)
        tl = QVBoxLayout(thumb)
        tl.setAlignment(Qt.AlignCenter)
        tl.addWidget(QLabel("thumb", thumb))
        pcl.addWidget(thumb)

        self._prev_name = QLabel("—", prev_card)
        self._prev_name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
        )
        self._prev_meta = QLabel("", prev_card)
        self._prev_meta.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;")
        pcl.addWidget(self._prev_name)
        pcl.addWidget(self._prev_meta)
        pcl.addStretch()
        pl.addWidget(prev_card, 1)

        self._open_btn = QPushButton("Open", preview)
        self._open_btn.setObjectName("btnPrimary")
        self._open_btn.setFixedHeight(60)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_file)
        pl.addWidget(self._open_btn)
        content.addWidget(preview)
        root.addLayout(content, 1)

        # Load from home directory
        self._load_directory(Path.home())

    def _load_directory(self, path: Path) -> None:
        # Clear current list
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

        try:
            exts = set(EXT_COLORS.keys())
            files = sorted(
                [p for p in path.iterdir() if p.is_file() and p.suffix.lower() in exts],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except PermissionError:
            files = []

        for fp in files[:20]:
            row = FileRow(fp, self._on_select, self._list_frame)
            self._list_lyt.addWidget(row)
            self._rows.append(row)

        self._list_lyt.addStretch()

    def _on_select(self, path: Path) -> None:
        self._selected = path
        for row in self._rows:
            row.select(row._path == path)
        self._prev_name.setText(path.name)
        ext = path.suffix.lower()
        mode = "CNC" if ext in (".nc", ".gcode", ".gc", ".tap") else "Laser"
        self._prev_meta.setText(f"{mode} · {path.suffix.upper()}")
        self._open_btn.setEnabled(True)

    def _open_file(self) -> None:
        if self._selected:
            self._ctrl.set_job_file(self._selected)
            self._ctrl.navigate_back()

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("SCROLL", "file list")
        self._ctrl.rail.set_enc2("SOURCE", "USB")
