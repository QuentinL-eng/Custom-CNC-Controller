"""Material presets screen — touch-friendly list + editor for cutting presets."""
from __future__ import annotations

from pathlib import Path

from ..qt_compat import (
    Qt, QEvent, QTimer, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QLineEdit,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_AMBER, C_BTN_2ND,
    CARD_RADIUS, BTN_RADIUS,
)
from ..widgets.touch_keyboard import TouchKeyboard
from ...materials import (
    MaterialPreset, DEFAULT_PRESETS_PATH,
    load_material_presets, save_material_presets,
)

MODES = ("cnc", "laser", "pcb")


def _field_style() -> str:
    return (
        f"QLineEdit {{ background: {C_CARD}; color: {C_TEXT}; "
        f"border: 1px solid {C_CARD_BORDER}; border-radius: {BTN_RADIUS}px; "
        f"padding: 0 12px; font-size: 15px; }}"
        f"QLineEdit:focus {{ border: 1px solid {C_GREEN}; }}"
    )


class PresetRow(QFrame):
    def __init__(self, index: int, preset: MaterialPreset, on_select,
                 selected: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self._index = index
        self._on_select = on_select
        self._selected = selected
        self._update_style()

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(14, 12, 14, 12)
        lyt.setSpacing(12)

        star = QLabel("★" if preset.favorite else "", self)
        star.setFixedWidth(16)
        star.setStyleSheet(
            f"color: {C_AMBER}; font-size: 16px; background: transparent; border: none;"
        )
        lyt.addWidget(star)

        info = QWidget(self)
        info.setStyleSheet("background: transparent; border: none;")
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(1)
        name = QLabel(preset.name or "(unnamed preset)", info)
        name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        if preset.mode == "laser":
            meta_txt = (
                f"laser · {preset.feed_mm_min:g} mm/min · "
                f"{preset.laser_power_pct}% · {preset.passes} pass"
            )
        else:
            meta_txt = (
                f"{preset.mode} · {preset.feed_mm_min:g} mm/min · "
                f"{preset.rpm} rpm · {preset.passes} pass"
            )
        meta = QLabel(meta_txt, info)
        meta.setStyleSheet(
            f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;"
        )
        il.addWidget(name)
        il.addWidget(meta)
        lyt.addWidget(info, 1)

    def _update_style(self) -> None:
        bg = "#f3f8fe" if self._selected else C_CARD
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border-bottom: 1px solid {C_DIVIDER}; }}"
        )

    def mousePressEvent(self, event):
        self._on_select(self._index)


class MaterialsScreen(QWidget):
    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = controller
        self._path = Path(DEFAULT_PRESETS_PATH)
        self._presets: list[MaterialPreset] = load_material_presets(self._path)
        self._selected = 0 if self._presets else -1
        self._rows: list[PresetRow] = []
        self._fields: dict[str, QLineEdit] = {}
        self._build_ui()
        self._refresh_list()
        self._load_selected_into_form()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self._root_layout = QHBoxLayout(self)
        self._root_layout.setContentsMargins(14, 14, 14, 14)
        self._root_layout.setSpacing(12)

        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        header = QHBoxLayout()
        sec = QLabel("MATERIAL PRESETS", left)
        sec.setObjectName("labelSection")
        header.addWidget(sec)
        header.addStretch()
        add_btn = QPushButton("+ Add", left)
        add_btn.setObjectName("btnSecondary")
        add_btn.setFixedHeight(42)
        add_btn.clicked.connect(self._add_preset)
        header.addWidget(add_btn)
        ll.addLayout(header)

        list_card = QFrame(left)
        list_card.setObjectName("card")
        lcl = QVBoxLayout(list_card)
        lcl.setContentsMargins(0, 0, 0, 0)
        lcl.setSpacing(0)
        scroll = QScrollArea(list_card)
        scroll.setWidgetResizable(True)
        self._list_host = QWidget(scroll)
        self._list_lyt = QVBoxLayout(self._list_host)
        self._list_lyt.setContentsMargins(0, 0, 0, 0)
        self._list_lyt.setSpacing(0)
        self._list_lyt.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._list_host)
        self._content_scroll = scroll
        lcl.addWidget(scroll)
        ll.addWidget(list_card, 1)
        self._root_layout.addWidget(left, 1)

        right = QWidget(self)
        right.setFixedWidth(340)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        edit_card = QFrame(right)
        edit_card.setObjectName("card")
        ecl = QVBoxLayout(edit_card)
        ecl.setContentsMargins(13, 13, 13, 13)
        ecl.setSpacing(9)

        sec2 = QLabel("PRESET DETAILS", edit_card)
        sec2.setObjectName("labelSection")
        ecl.addWidget(sec2)

        self._add_field(ecl, edit_card, "name", "Name", "Preset name")

        # Mode + favorite row
        mf_row = QHBoxLayout()
        mf_row.setSpacing(8)
        mode_host = QWidget(edit_card)
        mode_host.setStyleSheet("background: transparent; border: none;")
        mv = QVBoxLayout(mode_host)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(4)
        mode_lbl = QLabel("Mode", mode_host)
        mode_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        mv.addWidget(mode_lbl)
        self._mode_btn = QPushButton(MODES[0], mode_host)
        self._mode_btn.setObjectName("btnSecondary")
        self._mode_btn.setFixedHeight(44)
        self._mode_btn.clicked.connect(self._cycle_mode)
        mv.addWidget(self._mode_btn)
        mf_row.addWidget(mode_host, 1)

        fav_host = QWidget(edit_card)
        fav_host.setStyleSheet("background: transparent; border: none;")
        fv = QVBoxLayout(fav_host)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(4)
        fav_lbl = QLabel("Favorite", fav_host)
        fav_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        fv.addWidget(fav_lbl)
        self._fav = False
        self._fav_btn = QPushButton("☆ No", fav_host)
        self._fav_btn.setObjectName("btnSecondary")
        self._fav_btn.setFixedHeight(44)
        self._fav_btn.clicked.connect(self._toggle_favorite)
        fv.addWidget(self._fav_btn)
        mf_row.addWidget(fav_host, 1)
        ecl.addLayout(mf_row)

        self._add_field(ecl, edit_card, "feed_mm_min", "Feed (mm/min)", "Feed", numeric=True)
        self._add_field(ecl, edit_card, "plunge_mm_min", "Plunge (mm/min)", "Plunge", numeric=True)
        self._add_field(ecl, edit_card, "rpm", "RPM", "RPM", numeric=True)
        self._add_field(ecl, edit_card, "laser_power_pct", "Laser power (%)", "Laser power", numeric=True)
        self._add_field(ecl, edit_card, "passes", "Passes", "Passes", numeric=True)
        self._add_field(ecl, edit_card, "notes", "Notes", "Notes")
        ecl.addStretch()
        rl.addWidget(edit_card, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._delete_btn = QPushButton("Delete", right)
        self._delete_btn.setObjectName("btnDanger")
        self._delete_btn.setFixedHeight(60)
        self._delete_btn.clicked.connect(self._delete_preset)
        btns.addWidget(self._delete_btn)
        self._save_btn = QPushButton("Save", right)
        self._save_btn.setObjectName("btnPrimary")
        self._save_btn.setFixedHeight(60)
        self._save_btn.clicked.connect(self._save_current)
        btns.addWidget(self._save_btn, 1)
        rl.addLayout(btns)
        self._root_layout.addWidget(right)

        self._keyboard = TouchKeyboard(self, getattr(self._ctrl, "motion", None))
        self._keyboard.opened.connect(self._keyboard_opened)
        self._keyboard.dismissed.connect(self._keyboard_dismissed)
        self._position_keyboard()

    def _add_field(self, layout, parent, key: str, label: str,
                   title: str, numeric: bool = False) -> None:
        lbl = QLabel(label, parent)
        lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        edit = QLineEdit(parent)
        edit.setFixedHeight(44)
        edit.setStyleSheet(_field_style())
        edit.setProperty("kbTitle", title)
        edit.installEventFilter(self)
        layout.addWidget(lbl)
        layout.addWidget(edit)
        self._fields[key] = edit

    # -------------------------------------------------------------- helpers
    def _cycle_mode(self) -> None:
        cur = self._mode_btn.text()
        try:
            idx = MODES.index(cur)
        except ValueError:
            idx = -1
        self._mode_btn.setText(MODES[(idx + 1) % len(MODES)])

    def _toggle_favorite(self) -> None:
        self._fav = not self._fav
        self._fav_btn.setText("★ Yes" if self._fav else "☆ No")

    def _refresh_list(self) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()
        while self._list_lyt.count():
            item = self._list_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._presets:
            empty = QLabel("No presets yet. Tap + Add to create one.", self._list_host)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {C_DIM}; font-size: 14px; background: transparent; "
                "border: none; padding: 30px;"
            )
            self._list_lyt.addWidget(empty)
            self._list_lyt.addStretch()
            return

        for i, preset in enumerate(self._presets):
            row = PresetRow(i, preset, self._on_select, i == self._selected, self._list_host)
            self._list_lyt.addWidget(row)
            self._rows.append(row)
        self._list_lyt.addStretch()

    def _on_select(self, index: int) -> None:
        self._selected = index
        for i, row in enumerate(self._rows):
            row._selected = (i == index)
            row._update_style()
        self._load_selected_into_form()

    def _load_selected_into_form(self) -> None:
        has = 0 <= self._selected < len(self._presets)
        self._delete_btn.setEnabled(has)
        if not has:
            for edit in self._fields.values():
                edit.clear()
            self._mode_btn.setText(MODES[0])
            self._fav = False
            self._fav_btn.setText("☆ No")
            return
        p = self._presets[self._selected]
        self._fields["name"].setText(p.name)
        self._mode_btn.setText(p.mode)
        self._fav = bool(p.favorite)
        self._fav_btn.setText("★ Yes" if self._fav else "☆ No")
        self._fields["feed_mm_min"].setText(f"{p.feed_mm_min:g}")
        self._fields["plunge_mm_min"].setText(f"{p.plunge_mm_min:g}")
        self._fields["rpm"].setText(str(p.rpm))
        self._fields["laser_power_pct"].setText(str(p.laser_power_pct))
        self._fields["passes"].setText(str(p.passes))
        self._fields["notes"].setText(p.notes)

    @staticmethod
    def _to_float(text: str, default: float = 0.0) -> float:
        try:
            return float(text.strip())
        except (ValueError, AttributeError):
            return default

    @staticmethod
    def _to_int(text: str, default: int = 0) -> int:
        try:
            return int(float(text.strip()))
        except (ValueError, AttributeError):
            return default

    def _form_to_preset(self) -> MaterialPreset:
        return MaterialPreset(
            name=self._fields["name"].text().strip(),
            mode=self._mode_btn.text(),
            feed_mm_min=self._to_float(self._fields["feed_mm_min"].text()),
            plunge_mm_min=self._to_float(self._fields["plunge_mm_min"].text()),
            rpm=self._to_int(self._fields["rpm"].text()),
            laser_power_pct=self._to_int(self._fields["laser_power_pct"].text()),
            passes=max(1, self._to_int(self._fields["passes"].text(), 1)),
            favorite=self._fav,
            notes=self._fields["notes"].text().strip(),
        )

    # --------------------------------------------------------------- actions
    def _add_preset(self) -> None:
        self._presets.append(MaterialPreset("New Preset"))
        self._selected = len(self._presets) - 1
        self._refresh_list()
        self._load_selected_into_form()
        self._fields["name"].selectAll()

    def _save_current(self) -> None:
        preset = self._form_to_preset()
        if 0 <= self._selected < len(self._presets):
            self._presets[self._selected] = preset
        else:
            self._presets.append(preset)
            self._selected = len(self._presets) - 1
        save_material_presets(self._path, self._presets)
        self._refresh_list()

    def _delete_preset(self) -> None:
        if 0 <= self._selected < len(self._presets):
            del self._presets[self._selected]
            self._selected = min(self._selected, len(self._presets) - 1)
            save_material_presets(self._path, self._presets)
            self._refresh_list()
            self._load_selected_into_form()

    # --------------------------------------------------------------- keyboard
    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            if isinstance(watched, QLineEdit) and watched in self._fields.values():
                title = watched.property("kbTitle") or "Edit"
                self._keyboard.show_for(watched, str(title))
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
        QTimer.singleShot(0, lambda: self._content_scroll.ensureWidgetVisible(target, 20, 20))

    def _keyboard_dismissed(self) -> None:
        self._root_layout.setContentsMargins(14, 14, 14, 14)

    # ----------------------------------------------------------------- hooks
    def on_enter(self) -> None:
        if hasattr(self._ctrl, "rail") and self._ctrl.rail:
            self._ctrl.rail.set_enc1("SCROLL", "preset list")
            self._ctrl.rail.set_enc2("SELECT", "preset")
