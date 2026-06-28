"""Reusable iPad-style on-screen keyboard for touchscreen text input."""
from __future__ import annotations

from ..qt_compat import (
    Qt,
    Signal,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    QLabel,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ..theme import C_BLUE, C_BORDER, C_CARD, C_DIM, C_MUTED, C_RAIL, C_TEXT


ALPHA_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]

SYMBOL_ROWS = [
    list("!@#$%^&*()"),
    ["[", "]", "{", "}", "<", ">", "/", "\\", "|", "~"],
    ["+", "=", "-", "_", ":", ";", '"', "'", ",", "?"],
]


class TouchKeyboard(QFrame):
    HEIGHT = 294
    opened = Signal(object)
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None, motion=None):
        super().__init__(parent)
        self._motion = motion
        self._animation: QPropertyAnimation | None = None
        self._target: QLineEdit | None = None
        self._shift = False
        self._symbols = False
        self.setStyleSheet(
            f"QFrame{{background-color:{C_RAIL};border:none;"
            f"border-top:1px solid {C_BORDER};border-radius:0px}}"
        )
        self.hide()
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(5)

        header = QHBoxLayout()
        self._title = QLabel("Keyboard", self)
        self._title.setStyleSheet(
            f"color:{C_MUTED};font-size:12px;font-weight:700;"
            "background:transparent;border:none"
        )
        header.addWidget(self._title)
        header.addStretch()
        note = QLabel("Input stays on this controller", self)
        note.setStyleSheet(
            f"color:{C_DIM};font-size:11px;background:transparent;border:none"
        )
        header.addWidget(note)
        root.addLayout(header)

        self._key_rows = QVBoxLayout()
        self._key_rows.setSpacing(4)
        root.addLayout(self._key_rows, 1)
        self._rebuild_keys()

    def _rebuild_keys(self) -> None:
        while self._key_rows.count():
            item = self._key_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        rows = SYMBOL_ROWS if self._symbols else ALPHA_ROWS
        for row_index, characters in enumerate(rows):
            row = QHBoxLayout()
            row.setSpacing(4)
            if not self._symbols and row_index == 3:
                row.addWidget(self._special("Shift", self._toggle_shift), 2)
            for character in characters:
                label = (
                    character.upper()
                    if self._shift and not self._symbols
                    else character
                )
                row.addWidget(self._character_key(label), 1)
            if row_index == len(rows) - 1:
                row.addWidget(self._special("⌫", self._backspace), 2)
            self._key_rows.addLayout(row)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(
            self._special("ABC" if self._symbols else "?123", self._toggle_symbols),
            2,
        )
        for character in ("-", "_", "@"):
            actions.addWidget(self._character_key(character), 1)
        actions.addWidget(self._special("Space", lambda: self._insert(" ")), 5)
        actions.addWidget(self._character_key("."), 1)
        actions.addWidget(self._special("Hide", self.hide_keyboard), 2)
        done = self._special("Done", self.hide_keyboard)
        done.setStyleSheet(
            f"background:{C_BLUE};color:white;border:1px solid {C_BLUE};"
            "border-radius:7px;font-size:14px;font-weight:700"
        )
        actions.addWidget(done, 2)
        self._key_rows.addLayout(actions)

    def _character_key(self, character: str) -> QPushButton:
        return self._special(character, lambda: self._insert(character))

    def _special(self, label: str, callback) -> QPushButton:
        button = QPushButton(label, self)
        button.setFixedHeight(42)
        button.setFocusPolicy(Qt.NoFocus)
        button.setStyleSheet(
            f"background:{C_CARD};color:{C_TEXT};border:1px solid {C_BORDER};"
            "border-radius:7px;font-size:15px;font-weight:700"
        )
        button.clicked.connect(callback)
        return button

    def show_for(self, target: QLineEdit, title: str = "Keyboard") -> None:
        was_visible = self.isVisible()
        self._stop_animation()
        self._target = target
        self._title.setText(title)
        final_position = self.pos()
        if not was_visible and self._duration:
            self.move(final_position.x(), self.parentWidget().height())
        self.show()
        self.raise_()
        target.setFocus()
        self.opened.emit(target)
        if not was_visible and self._duration:
            self._animation = QPropertyAnimation(self, b"pos", self)
            self._animation.setStartValue(self.pos())
            self._animation.setEndValue(final_position)
            self._animation.setDuration(self._duration)
            self._animation.setEasingCurve(QEasingCurve.OutCubic)
            self._animation.start()

    def hide_keyboard(self, clear_target: bool = False) -> None:
        if not self.isVisible():
            if clear_target:
                self._target = None
            return
        self._stop_animation()
        if clear_target or not self._duration:
            self._complete_hide(clear_target)
            return
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(
            QPoint(self.x(), self.parentWidget().height())
        )
        self._animation.setDuration(self._duration)
        self._animation.setEasingCurve(QEasingCurve.InCubic)
        self._animation.finished.connect(
            lambda: self._complete_hide(clear_target)
        )
        self._animation.start()

    @property
    def _duration(self) -> int:
        return getattr(self._motion, "duration", 0)

    def _stop_animation(self) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None

    def _complete_hide(self, clear_target: bool) -> None:
        self._stop_animation()
        self.hide()
        if self._target and not clear_target:
            self._target.setFocus()
        if clear_target:
            self._target = None
        self.dismissed.emit()

    def _insert(self, value: str) -> None:
        if not self._target:
            return
        self._target.insert(value)
        if self._shift and not self._symbols:
            self._shift = False
            self._rebuild_keys()

    def _backspace(self) -> None:
        if self._target:
            self._target.backspace()

    def _toggle_shift(self) -> None:
        self._shift = not self._shift
        self._rebuild_keys()

    def _toggle_symbols(self) -> None:
        self._symbols = not self._symbols
        self._shift = False
        self._rebuild_keys()
