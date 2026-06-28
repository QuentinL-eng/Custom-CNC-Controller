"""Tool library screen — touch-friendly list + editor for cutting tools."""
from __future__ import annotations

from pathlib import Path

from ..qt_compat import (
    Qt, QEvent, QTimer, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QLineEdit,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_RED, C_BTN_2ND,
    CARD_RADIUS, BTN_RADIUS,
)
from ..widgets.touch_keyboard import TouchKeyboard
from ...tools import (
    ToolRecord, TOOL_TYPES, DEFAULT_TOOLS_PATH,
    load_tools, save_tools,
)


def _field_style() -> str:
    return (
        f"QLineEdit {{ background: {C_CARD}; color: {C_TEXT}; "
        f"border: 1px solid {C_CARD_BORDER}; border-radius: {BTN_RADIUS}px; "
        f"padding: 0 12px; font-size: 15px; }}"
        f"QLineEdit:focus {{ border: 1px solid {C_GREEN}; }}"
    )


class ToolRow(QFrame):
    def __init__(self, index: int, tool: ToolRecord, on_select,
                 selected: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self._index = index
        self._on_select = on_select
        self._selected = selected
        self._update_style()

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(14, 12, 14, 12)
        lyt.setSpacing(12)

        info = QWidget(self)
        info.setStyleSheet("background: transparent; border: none;")
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(1)
        name = QLabel(tool.name or "(unnamed tool)", info)
        name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        meta = QLabel(
            f"{tool.tool_type.replace('_', ' ')} · ⌀{tool.diameter_mm:g} mm · "
            f"{tool.flutes}fl · {tool.rec_feed_mm_min:g} mm/min · {tool.rec_rpm} rpm",
            info,
        )
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


class ToolsScreen(QWidget):
    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = controller
        self._path = Path(DEFAULT_TOOLS_PATH)
        self._tools: list[ToolRecord] = load_tools(self._path)
        self._selected = 0 if self._tools else -1
        self._rows: list[ToolRow] = []
        self._fields: dict[str, QLineEdit] = {}
        self._build_ui()
        self._refresh_list()
        self._load_selected_into_form()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self._root_layout = QHBoxLayout(self)
        self._root_layout.setContentsMargins(14, 14, 14, 14)
        self._root_layout.setSpacing(12)

        # Left: tool list
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        header = QHBoxLayout()
        sec = QLabel("TOOL LIBRARY", left)
        sec.setObjectName("labelSection")
        header.addWidget(sec)
        header.addStretch()
        add_btn = QPushButton("+ Add", left)
        add_btn.setObjectName("btnSecondary")
        add_btn.setFixedHeight(42)
        add_btn.clicked.connect(self._add_tool)
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

        # Right: editor form
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

        sec2 = QLabel("TOOL DETAILS", edit_card)
        sec2.setObjectName("labelSection")
        ecl.addWidget(sec2)

        self._add_field(ecl, edit_card, "name", "Name", "Tool name")
        ecl.addWidget(self._type_row(edit_card))
        self._add_field(ecl, edit_card, "diameter_mm", "Diameter (mm)", "Diameter", numeric=True)
        self._add_field(ecl, edit_card, "flutes", "Flutes", "Flutes", numeric=True)
        self._add_field(ecl, edit_card, "rec_feed_mm_min", "Feed (mm/min)", "Feed", numeric=True)
        self._add_field(ecl, edit_card, "rec_rpm", "RPM", "RPM", numeric=True)
        self._add_field(ecl, edit_card, "notes", "Notes", "Notes")
        ecl.addStretch()
        rl.addWidget(edit_card, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._delete_btn = QPushButton("Delete", right)
        self._delete_btn.setObjectName("btnDanger")
        self._delete_btn.setFixedHeight(60)
        self._delete_btn.clicked.connect(self._delete_tool)
        btns.addWidget(self._delete_btn)
        self._save_btn = QPushButton("Save", right)
        self._save_btn.setObjectName("btnPrimary")
        self._save_btn.setFixedHeight(60)
        self._save_btn.clicked.connect(self._save_current)
        btns.addWidget(self._save_btn, 1)
        rl.addLayout(btns)
        self._root_layout.addWidget(right)

        # Touch keyboard overlay
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

    def _type_row(self, parent) -> QWidget:
        host = QWidget(parent)
        host.setStyleSheet("background: transparent; border: none;")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        lbl = QLabel("Type", host)
        lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        v.addWidget(lbl)
        self._type_btn = QPushButton(TOOL_TYPES[0], host)
        self._type_btn.setObjectName("btnSecondary")
        self._type_btn.setFixedHeight(44)
        self._type_btn.clicked.connect(self._cycle_type)
        v.addWidget(self._type_btn)
        return host

    # -------------------------------------------------------------- helpers
    def _cycle_type(self) -> None:
        cur = self._type_btn.text()
        try:
            idx = TOOL_TYPES.index(cur)
        except ValueError:
            idx = -1
        self._type_btn.setText(TOOL_TYPES[(idx + 1) % len(TOOL_TYPES)])

    def _refresh_list(self) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()
        # remove stretch if present
        while self._list_lyt.count():
            item = self._list_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._tools:
            empty = QLabel("No tools yet. Tap + Add to create one.", self._list_host)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {C_DIM}; font-size: 14px; background: transparent; "
                "border: none; padding: 30px;"
            )
            self._list_lyt.addWidget(empty)
            self._list_lyt.addStretch()
            return

        for i, tool in enumerate(self._tools):
            row = ToolRow(i, tool, self._on_select, i == self._selected, self._list_host)
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
        has = 0 <= self._selected < len(self._tools)
        self._save_btn.setEnabled(True)
        self._delete_btn.setEnabled(has)
        if not has:
            for edit in self._fields.values():
                edit.clear()
            self._type_btn.setText(TOOL_TYPES[0])
            return
        t = self._tools[self._selected]
        self._fields["name"].setText(t.name)
        self._type_btn.setText(t.tool_type)
        self._fields["diameter_mm"].setText(f"{t.diameter_mm:g}")
        self._fields["flutes"].setText(str(t.flutes))
        self._fields["rec_feed_mm_min"].setText(f"{t.rec_feed_mm_min:g}")
        self._fields["rec_rpm"].setText(str(t.rec_rpm))
        self._fields["notes"].setText(t.notes)

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

    def _form_to_record(self) -> ToolRecord:
        return ToolRecord(
            name=self._fields["name"].text().strip(),
            tool_type=self._type_btn.text(),
            diameter_mm=self._to_float(self._fields["diameter_mm"].text()),
            flutes=self._to_int(self._fields["flutes"].text()),
            rec_feed_mm_min=self._to_float(self._fields["rec_feed_mm_min"].text()),
            rec_rpm=self._to_int(self._fields["rec_rpm"].text()),
            notes=self._fields["notes"].text().strip(),
        )

    # --------------------------------------------------------------- actions
    def _add_tool(self) -> None:
        self._tools.append(ToolRecord("New Tool"))
        self._selected = len(self._tools) - 1
        self._refresh_list()
        self._load_selected_into_form()
        self._fields["name"].selectAll()

    def _save_current(self) -> None:
        record = self._form_to_record()
        if 0 <= self._selected < len(self._tools):
            self._tools[self._selected] = record
        else:
            self._tools.append(record)
            self._selected = len(self._tools) - 1
        save_tools(self._path, self._tools)
        self._refresh_list()

    def _delete_tool(self) -> None:
        if 0 <= self._selected < len(self._tools):
            del self._tools[self._selected]
            self._selected = min(self._selected, len(self._tools) - 1)
            save_tools(self._path, self._tools)
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
            self._ctrl.rail.set_enc1("SCROLL", "tool list")
            self._ctrl.rail.set_enc2("SELECT", "tool")
