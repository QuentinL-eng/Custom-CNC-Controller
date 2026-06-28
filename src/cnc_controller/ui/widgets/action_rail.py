"""Right 104 px action rail — always visible."""
from __future__ import annotations

from ..qt_compat import (
    Qt, QWidget, QFrame, QLabel, QVBoxLayout, QPushButton, QSizePolicy,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_MUTED, C_TEXT, C_GREEN, C_BLUE,
    C_RAIL, C_BORDER, ACTION_RAIL_W, BTN_RADIUS,
)


def _rail_btn(icon: str, label: str, parent: QWidget, color: str = C_TEXT) -> QPushButton:
    btn = QPushButton(parent)
    btn.setObjectName("btnRail")
    btn.setFixedSize(80, 60)
    btn.setStyleSheet(
        f"QPushButton {{ background: {C_CARD}; border: 1px solid {C_CARD_BORDER}; "
        f"border-radius: {BTN_RADIUS}px; }} "
        f"QPushButton:pressed {{ background: #eef1f3; }}"
    )
    inner = QWidget(btn)
    inner.setAttribute(Qt.WA_TransparentForMouseEvents)
    lyt = QVBoxLayout(inner)
    lyt.setContentsMargins(0, 6, 0, 6)
    lyt.setSpacing(2)
    lyt.setAlignment(Qt.AlignCenter)
    ico = QLabel(icon, inner)
    ico.setAlignment(Qt.AlignCenter)
    ico.setStyleSheet(f"color: {color}; font-size: 20px; background: transparent; border: none;")
    txt = QLabel(label, inner)
    txt.setAlignment(Qt.AlignCenter)
    txt.setStyleSheet(f"color: {C_MUTED}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
    lyt.addWidget(ico)
    lyt.addWidget(txt)
    inner.setGeometry(0, 0, 80, 60)
    return btn


def _enc_badge(enc_num: int, color: str, action: str, value: str, parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"QFrame {{ background: {C_CARD}; border: 1px solid {C_CARD_BORDER}; "
        f"border-radius: {BTN_RADIUS}px; }}"
    )
    lyt = QVBoxLayout(f)
    lyt.setContentsMargins(9, 8, 9, 8)
    lyt.setSpacing(2)

    header = QWidget(f)
    header.setStyleSheet("background: transparent; border: none;")
    hl = QVBoxLayout(header)
    hl.setContentsMargins(0, 0, 0, 4)
    dot_row = QWidget(header)
    dot_row.setStyleSheet("background: transparent; border: none;")
    drl = QVBoxLayout(dot_row)
    drl.setContentsMargins(0, 0, 0, 0)
    dot = QLabel(f"● ENC {enc_num}", dot_row)
    dot.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700; background: transparent; border: none;")
    drl.addWidget(dot)
    hl.addWidget(dot_row)
    lyt.addWidget(header)

    act_lbl = QLabel(action, f)
    act_lbl.setWordWrap(True)
    act_lbl.setStyleSheet(f"color: {C_TEXT}; font-size: 13px; font-weight: 700; background: transparent; border: none;")
    lyt.addWidget(act_lbl)

    val_lbl = QLabel(value, f)
    val_lbl.setStyleSheet(f"color: {C_MUTED}; font-size: 11px; background: transparent; border: none;")
    lyt.addWidget(val_lbl)

    f._action_label = act_lbl
    f._value_label = val_lbl
    return f


class ActionRail(QFrame):
    """104 px wide right action rail with Home, Back, context, and encoder badges."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("actionRail")
        self.setFixedWidth(ACTION_RAIL_W)
        self.setStyleSheet(
            f"QFrame#actionRail {{ background: {C_RAIL}; "
            f"border-left: 1px solid {C_BORDER}; border-radius: 0; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        self.home_btn = _rail_btn("⌂", "HOME", self)
        layout.addWidget(self.home_btn, 0, Qt.AlignHCenter)

        self.back_btn = _rail_btn("‹", "BACK", self)
        layout.addWidget(self.back_btn, 0, Qt.AlignHCenter)

        self.ctx_btn = _rail_btn("●", "CTX", self)
        self.ctx_btn.setVisible(False)
        layout.addWidget(self.ctx_btn, 0, Qt.AlignHCenter)

        layout.addStretch()

        self._enc1 = _enc_badge(1, C_GREEN, "NAVIGATE", "menu", self)
        layout.addWidget(self._enc1)

        self._enc2 = _enc_badge(2, C_BLUE, "—", "idle", self)
        layout.addWidget(self._enc2)

    def set_context(self, icon: str, label: str, visible: bool = True) -> None:
        """Update and show/hide the context button."""
        # Rebuild context button label
        for child in self.ctx_btn.children():
            if isinstance(child, QWidget):
                for c in child.children():
                    if isinstance(c, QLabel):
                        text = c.text()
                        if len(text) <= 3:
                            c.setText(icon)
                        else:
                            c.setText(label)
        self.ctx_btn.setVisible(visible)

    def set_enc1(self, action: str, value: str = "") -> None:
        self._enc1._action_label.setText(action)
        self._enc1._value_label.setText(value)

    def set_enc2(self, action: str, value: str = "") -> None:
        self._enc2._action_label.setText(action)
        self._enc2._value_label.setText(value)
