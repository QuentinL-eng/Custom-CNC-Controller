"""File browser screen."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QSizePolicy, QLineEdit, QTimer, QEvent,
    QPixmap, QPainter, QPen, QColor,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_BLUE, C_AMBER, C_BTN_2ND, C_BG,
    C_GREEN_BG, C_BLUE_BG, C_AMBER_BG,
    CARD_RADIUS, BTN_RADIUS,
)
from ..widgets.touch_keyboard import TouchKeyboard
from ...grbl_worker import GrblStatus
from ...gcode import GcodeAnalysis, analyze_gcode_file


EXT_COLORS = {
    ".nc": (C_GREEN_BG, "#0c7a45", "NC"),
    ".gcode": (C_GREEN_BG, "#0c7a45", "GC"),
    ".gc": (C_GREEN_BG, "#0c7a45", "GC"),
    ".tap": (C_GREEN_BG, "#0c7a45", "TAP"),
    ".svg": (C_BLUE_BG, "#0f5fb0", "SVG"),
    ".dxf": (C_BLUE_BG, "#0f5fb0", "DXF"),
    ".gbr": (C_AMBER_BG, "#8a5a06", "GBR"),
}

GCODE_EXTS = {".nc", ".gcode", ".gc", ".tap"}

# Reasonable, still-performant cap on entries rendered per directory.
MAX_ENTRIES = 500
MAX_RECENT = 30


# ---------------------------------------------------------------------------
# Pure helpers (no Qt) — covered by tests in test_file_browser.py
# ---------------------------------------------------------------------------

def _badge(ext: str) -> tuple[str, str, str]:
    key = ext.lower()
    return EXT_COLORS.get(key, ("#f6f8f9", "#5c636b", ext.lstrip(".").upper()[:3]))


def matches_filter(name: str, query: str) -> bool:
    """Case-insensitive substring filter. Empty query matches everything."""
    q = query.strip().lower()
    if not q:
        return True
    return q in name.lower()


def list_directory(path: Path, exts: set[str] | None = None,
                   cap: int = MAX_ENTRIES) -> list[Path]:
    """Return directory entries: folders first (alpha), then matching files
    (newest first). Hidden entries are skipped. Robust to permission errors."""
    if exts is None:
        exts = set(EXT_COLORS.keys())
    try:
        entries = list(path.iterdir())
    except (PermissionError, OSError):
        return []

    dirs: list[Path] = []
    files: list[Path] = []
    for p in entries:
        if p.name.startswith("."):
            continue
        try:
            if p.is_dir():
                dirs.append(p)
            elif p.is_file() and p.suffix.lower() in exts:
                files.append(p)
        except OSError:
            continue

    dirs.sort(key=lambda p: p.name.lower())

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    files.sort(key=_mtime, reverse=True)
    return (dirs + files)[:cap]


def discover_removable_media(linux_roots: tuple[str, ...] = ("/media", "/run/media"),
                             drive_letters: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                             platform: str | None = None,
                             root: Path | None = None) -> list[Path]:
    """Discover mounted removable media.

    On Linux, scans /media/* and one level into /run/media/*/* for mount points.
    On Windows, enumerates existing drive letters (skipping the system C: drive).
    ``root`` lets tests supply a fake filesystem prefix; ``platform`` overrides
    sys.platform for testing. Never raises.
    """
    plat = platform if platform is not None else sys.platform
    found: list[Path] = []

    def _resolve(p: str) -> Path:
        if root is not None:
            return root / p.lstrip("/\\")
        return Path(p)

    if plat.startswith("win"):
        for letter in drive_letters:
            if root is None and letter == "C":
                continue
            # When ``root`` is supplied (tests), use the bare letter as a path
            # component — a colon is a reserved drive specifier on Windows and
            # cannot appear in a normal directory name.
            drive = (root / letter) if root is not None else Path(f"{letter}:\\")
            try:
                if drive.exists() and drive.is_dir():
                    found.append(drive)
            except OSError:
                continue
    else:
        for base in linux_roots:
            bpath = _resolve(base)
            try:
                if not bpath.is_dir():
                    continue
                for child in sorted(bpath.iterdir()):
                    try:
                        if not child.is_dir():
                            continue
                    except OSError:
                        continue
                    # /run/media has a per-user subdirectory level.
                    has_mountpoints = False
                    try:
                        for sub in sorted(child.iterdir()):
                            if sub.is_dir():
                                found.append(sub)
                                has_mountpoints = True
                    except OSError:
                        pass
                    if not has_mountpoints:
                        found.append(child)
            except OSError:
                continue
    return found


def favorites_path() -> Path:
    """Location of the favorites JSON, under a per-user config dir."""
    base = os.environ.get("CNC_CONFIG_DIR")
    if base:
        return Path(base) / "file_favorites.json"
    return Path.home() / ".config" / "cnc_controller" / "file_favorites.json"


def load_favorites(path: Path) -> list[str]:
    """Load favorite paths from JSON. Robust to a missing/corrupt file."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("favorites", [])
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str)]


def save_favorites(path: Path, favorites: list[str]) -> None:
    """Persist favorite paths to JSON. Swallows write errors."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"favorites": list(favorites)}, indent=2))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class FileRow(QFrame):
    def __init__(self, path: Path, on_select, is_dir: bool = False,
                 is_fav: bool = False, on_toggle_fav=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._path = path
        self._on_select = on_select
        self._is_dir = is_dir
        self._selected = False
        self._update_style()

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(14, 13, 14, 13)
        lyt.setSpacing(12)

        if is_dir:
            bg, fg, label = ("#eef2f6", C_MUTED, "DIR")
        else:
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
        name = QLabel(path.name + ("/" if is_dir else ""), info)
        name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 600; background: transparent; border: none;"
        )
        meta = QLabel("Folder" if is_dir else self._fmt_size(path), info)
        meta.setStyleSheet(f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;")
        il.addWidget(name)
        il.addWidget(meta)
        lyt.addWidget(info, 1)

        if not is_dir and on_toggle_fav is not None:
            self._fav_btn = QPushButton("★" if is_fav else "☆", self)
            self._fav_btn.setFixedSize(34, 34)
            self._fav_btn.setFocusPolicy(Qt.NoFocus)
            self._fav_btn.setCursor(Qt.PointingHandCursor)
            self._update_fav_style(is_fav)
            self._fav_btn.clicked.connect(lambda: on_toggle_fav(path))
            lyt.addWidget(self._fav_btn)

    def _update_fav_style(self, is_fav: bool) -> None:
        color = C_AMBER if is_fav else C_DIM
        self._fav_btn.setText("★" if is_fav else "☆")
        self._fav_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {color}; border: none; "
            f"font-size: 20px; }}"
        )

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
        self._on_select(self._path, self._is_dir)


class FileBrowserScreen(QWidget):
    def __init__(self, ctrl, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._selected: Path | None = None
        self._rows: list[FileRow] = []
        self._source = "internal"          # "internal" | "usb" | "sd"
        self._view = "browse"              # "browse" | "favorites" | "recent"
        self._cwd: Path = Path.home()
        self._media_roots: list[Path] = []
        self._fav_path = favorites_path()
        self._favorites: list[str] = load_favorites(self._fav_path)
        self._recent: list[str] = []
        self._filter = ""
        self._build_ui()

        motion = getattr(self._ctrl, "motion", None)
        self._keyboard = TouchKeyboard(self, motion)
        self._keyboard.opened.connect(self._keyboard_opened)
        self._keyboard.dismissed.connect(self._keyboard_dismissed)
        self._position_keyboard()

        self._set_source("internal")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(11)
        self._root_layout = root

        # Source tabs + search
        top = QHBoxLayout()
        top.setSpacing(9)
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self._src_btns: dict[str, QPushButton] = {}
        for label, key in (("USB", "usb"), ("SD Card", "sd"), ("Internal", "internal")):
            btn = QPushButton(label, self)
            btn.setFixedHeight(42)
            btn.setObjectName("btnSecondary")
            btn.clicked.connect(lambda _=False, k=key: self._set_source(k))
            tabs.addWidget(btn)
            self._src_btns[key] = btn
        top.addLayout(tabs)

        # Search field (real QLineEdit + on-screen keyboard)
        search = QFrame(self)
        search.setStyleSheet(
            f"QFrame {{ background: {C_CARD}; border: 1px solid {C_CARD_BORDER}; border-radius: {BTN_RADIUS}px; }}"
        )
        sl = QHBoxLayout(search)
        sl.setContentsMargins(13, 0, 13, 0)
        sl.setSpacing(8)
        glyph = QLabel("⌕", search)
        glyph.setStyleSheet(f"color: {C_DIM}; font-size: 16px; background: transparent; border: none;")
        sl.addWidget(glyph)
        self._search = QLineEdit(search)
        self._search.setPlaceholderText("Search files…")
        self._search.setStyleSheet(
            f"QLineEdit {{ color: {C_TEXT}; font-size: 14px; background: transparent; border: none; }}"
        )
        self._search.textChanged.connect(self._on_search)
        self._search.installEventFilter(self)
        sl.addWidget(self._search, 1)
        search.setFixedHeight(42)
        top.addWidget(search, 1)
        root.addLayout(top)

        # View tabs + breadcrumb / up
        nav = QHBoxLayout()
        nav.setSpacing(6)
        self._up_btn = QPushButton("↑ Up", self)
        self._up_btn.setObjectName("btnSecondary")
        self._up_btn.setFixedHeight(34)
        self._up_btn.clicked.connect(self._go_up)
        nav.addWidget(self._up_btn)

        self._crumb = QLabel("", self)
        self._crumb.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        nav.addWidget(self._crumb, 1)

        self._view_btns: dict[str, QPushButton] = {}
        for label, key in (("Browse", "browse"), ("Favorites", "favorites"), ("Recent", "recent")):
            b = QPushButton(label, self)
            b.setObjectName("btnSecondary")
            b.setFixedHeight(34)
            b.clicked.connect(lambda _=False, k=key: self._set_view(k))
            self._view_btns[key] = b
            nav.addWidget(b)
        root.addLayout(nav)

        # Main area
        content = QHBoxLayout()
        content.setSpacing(11)

        # File list (scrollable)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self._list_frame = QFrame(self._scroll)
        self._list_frame.setObjectName("card")
        self._list_frame.setStyleSheet(
            f"QFrame#card {{ border-radius: {CARD_RADIUS}px; background: {C_CARD}; "
            f"border: 1px solid {C_CARD_BORDER}; }}"
        )
        self._list_lyt = QVBoxLayout(self._list_frame)
        self._list_lyt.setContentsMargins(0, 0, 0, 0)
        self._list_lyt.setSpacing(0)
        self._scroll.setWidget(self._list_frame)
        content.addWidget(self._scroll, 1)

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

        self._thumb = QLabel(prev_card)
        self._thumb.setStyleSheet(
            f"QLabel {{ background: {C_BTN_2ND}; border: 1px dashed {C_CARD_BORDER}; border-radius: 8px; color: {C_DIM}; }}"
        )
        self._thumb.setFixedHeight(110)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setText("No file selected")
        pcl.addWidget(self._thumb)

        self._prev_name = QLabel("—", prev_card)
        self._prev_name.setWordWrap(True)
        self._prev_name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
        )
        self._prev_meta = QLabel("", prev_card)
        self._prev_meta.setWordWrap(True)
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

    # -- source / view selection --------------------------------------------

    def _refresh_tabs(self) -> None:
        for key, btn in self._src_btns.items():
            if key == self._source:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {C_TEXT}; color: white; border: none; "
                    f"border-radius: {BTN_RADIUS}px; font-size: 14px; font-weight: 700; padding: 0 16px; }}"
                )
            else:
                btn.setStyleSheet("")
                btn.setObjectName("btnSecondary")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        for key, btn in self._view_btns.items():
            active = key == self._view
            btn.setStyleSheet(
                (f"QPushButton {{ background: {C_BLUE}; color: white; border: none; "
                 f"border-radius: {BTN_RADIUS}px; font-size: 13px; font-weight: 700; padding: 0 12px; }}")
                if active else ""
            )

    def _set_source(self, key: str) -> None:
        self._source = key
        self._view = "browse"
        if key == "internal":
            self._media_roots = []
            self._cwd = self._internal_root()
            self._load_current()
        else:
            self._media_roots = discover_removable_media()
            if self._media_roots:
                self._cwd = self._media_roots[0]
                self._load_current()
            else:
                self._cwd = None  # type: ignore[assignment]
                self._show_empty(f"No {'USB' if key == 'usb' else 'SD card'} media found")
        self._refresh_tabs()

    def _set_view(self, key: str) -> None:
        self._view = key
        if key == "favorites":
            self._load_favorites_view()
        elif key == "recent":
            self._load_recent_view()
        else:
            self._load_current()
        self._refresh_tabs()

    def _internal_root(self) -> Path:
        base = os.environ.get("CNC_FILES_ROOT")
        return Path(base) if base else Path.home()

    # -- listing -------------------------------------------------------------

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()
        while self._list_lyt.count():
            item = self._list_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_empty(self, message: str) -> None:
        self._clear_rows()
        lbl = QLabel(message, self._list_frame)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"color: {C_DIM}; font-size: 14px; background: transparent; border: none; padding: 28px;"
        )
        self._list_lyt.addWidget(lbl)
        self._list_lyt.addStretch()
        self._crumb.setText(message)
        self._up_btn.setEnabled(False)

    def _load_current(self) -> None:
        if self._cwd is None:
            return
        entries = list_directory(self._cwd)
        self._render_entries(entries)
        self._crumb.setText(self._crumb_text(self._cwd))
        self._up_btn.setEnabled(self._can_go_up())

    def _load_favorites_view(self) -> None:
        paths = [Path(p) for p in self._favorites]
        existing = [p for p in paths if p.is_file()]
        self._render_entries(existing, show_dirs=False)
        self._crumb.setText("Favorites")
        self._up_btn.setEnabled(False)

    def _load_recent_view(self) -> None:
        paths = [Path(p) for p in self._recent]
        existing = [p for p in paths if p.is_file()]
        self._render_entries(existing, show_dirs=False)
        self._crumb.setText("Recent")
        self._up_btn.setEnabled(False)

    def _render_entries(self, entries: list[Path], show_dirs: bool = True) -> None:
        self._clear_rows()
        shown = 0
        for p in entries:
            try:
                is_dir = p.is_dir()
            except OSError:
                continue
            if is_dir and not show_dirs:
                continue
            if not matches_filter(p.name, self._filter):
                continue
            is_fav = (not is_dir) and (str(p) in self._favorites)
            row = FileRow(
                p, self._on_select, is_dir=is_dir, is_fav=is_fav,
                on_toggle_fav=None if is_dir else self._toggle_favorite,
                parent=self._list_frame,
            )
            self._list_lyt.addWidget(row)
            self._rows.append(row)
            shown += 1
        if shown == 0:
            empty = QLabel("No matching files", self._list_frame)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {C_DIM}; font-size: 14px; background: transparent; border: none; padding: 28px;"
            )
            self._list_lyt.addWidget(empty)
        self._list_lyt.addStretch()

    def _crumb_text(self, path: Path) -> str:
        return str(path)

    def _can_go_up(self) -> bool:
        if self._cwd is None:
            return False
        if self._media_roots:
            return self._cwd not in self._media_roots and self._cwd != self._cwd.parent
        return self._cwd != self._cwd.parent

    def _go_up(self) -> None:
        if self._cwd is None or not self._can_go_up():
            return
        self._cwd = self._cwd.parent
        self._selected = None
        self._open_btn.setEnabled(False)
        self._load_current()

    # -- search --------------------------------------------------------------

    def _on_search(self, text: str) -> None:
        self._filter = text
        if self._view == "favorites":
            self._load_favorites_view()
        elif self._view == "recent":
            self._load_recent_view()
        else:
            self._load_current()

    # -- favorites -----------------------------------------------------------

    def _toggle_favorite(self, path: Path) -> None:
        key = str(path)
        if key in self._favorites:
            self._favorites.remove(key)
        else:
            self._favorites.append(key)
        save_favorites(self._fav_path, self._favorites)
        # Refresh fav glyphs in current rows
        for row in self._rows:
            if hasattr(row, "_fav_btn") and row._path == path:
                row._update_fav_style(key in self._favorites)
        if self._view == "favorites":
            self._load_favorites_view()

    def _push_recent(self, path: Path) -> None:
        key = str(path)
        if key in self._recent:
            self._recent.remove(key)
        self._recent.insert(0, key)
        del self._recent[MAX_RECENT:]

    # -- selection / preview -------------------------------------------------

    def _on_select(self, path: Path, is_dir: bool) -> None:
        if is_dir:
            self._cwd = path
            self._selected = None
            self._open_btn.setEnabled(False)
            self._load_current()
            return
        self._selected = path
        for row in self._rows:
            row.select(getattr(row, "_path", None) == path)
        self._update_preview(path)
        self._open_btn.setEnabled(True)

    def _update_preview(self, path: Path) -> None:
        self._prev_name.setText(path.name)
        ext = path.suffix.lower()
        mode = "CNC" if ext in GCODE_EXTS else "Laser"
        if ext in GCODE_EXTS:
            try:
                analysis = analyze_gcode_file(path)
            except OSError:
                analysis = None
            if analysis is not None:
                self._show_analysis(mode, ext, analysis)
                return
        self._thumb.setPixmap(QPixmap())
        self._thumb.setText(ext.lstrip(".").upper() or "FILE")
        self._prev_meta.setText(f"{mode} · {path.suffix.upper()}")

    def _show_analysis(self, mode: str, ext: str, a: GcodeAnalysis) -> None:
        parts = [f"{mode} · {ext.upper()}", f"{a.line_count} lines"]
        if a.bounds_mm is not None:
            x0, y0, x1, y1 = a.bounds_mm
            w = x1 - x0
            h = y1 - y0
            parts.append(f"Bounds: {w:.1f} × {h:.1f} mm")
        if a.max_feed_mm_min is not None:
            parts.append(f"Max feed: {a.max_feed_mm_min:.0f} mm/min")
        if a.max_power_s is not None:
            parts.append(f"Max power: S{a.max_power_s}")
        self._prev_meta.setText("\n".join(parts))
        self._render_bounds_thumb(a.bounds_mm)

    def _render_bounds_thumb(self, bounds: tuple[float, float, float, float] | None) -> None:
        w = max(self._thumb.width(), 200)
        h = self._thumb.height() or 110
        pix = QPixmap(w, h)
        pix.fill(QColor(C_BTN_2ND))
        if bounds is not None:
            x0, y0, x1, y1 = bounds
            bw = max(x1 - x0, 1e-6)
            bh = max(y1 - y0, 1e-6)
            pad = 14
            avail_w = w - 2 * pad
            avail_h = h - 2 * pad
            scale = min(avail_w / bw, avail_h / bh)
            rw = bw * scale
            rh = bh * scale
            rx = (w - rw) / 2
            ry = (h - rh) / 2
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(C_BLUE))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QColor(C_BLUE_BG))
            painter.drawRect(int(rx), int(ry), int(rw), int(rh))
            painter.end()
        self._thumb.setText("")
        self._thumb.setPixmap(pix)

    def _open_file(self) -> None:
        if self._selected:
            self._push_recent(self._selected)
            self._ctrl.set_job_file(self._selected)
            self._ctrl.navigate_back()

    # -- keyboard ------------------------------------------------------------

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            if watched is getattr(self, "_search", None):
                self._keyboard.show_for(self._search, "Search files")
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_keyboard()

    def _position_keyboard(self) -> None:
        if hasattr(self, "_keyboard"):
            self._keyboard.setGeometry(
                0,
                max(0, self.height() - self._keyboard.HEIGHT),
                self.width(),
                self._keyboard.HEIGHT,
            )

    def _keyboard_opened(self, target: QLineEdit) -> None:
        self._root_layout.setContentsMargins(14, 14, 14, self._keyboard.HEIGHT + 14)

    def _keyboard_dismissed(self) -> None:
        self._root_layout.setContentsMargins(14, 14, 14, 14)

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("SCROLL", "file list")
        src_label = {"usb": "USB", "sd": "SD Card", "internal": "Internal"}.get(self._source, "USB")
        self._ctrl.rail.set_enc2("SOURCE", src_label)
