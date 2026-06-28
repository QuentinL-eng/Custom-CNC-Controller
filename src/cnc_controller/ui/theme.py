"""Design tokens and Qt stylesheet for the CNC Controller UI.

All colors, dimensions, and typography match the Claude Design mockup exactly.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

C_BG = "#e9ecef"           # screen background
C_CARD = "#ffffff"         # card background
C_RAIL = "#f3f5f7"         # right action rail
C_STATUS_BAR = "#ffffff"   # top status bar

C_GREEN = "#109a5b"        # primary / ready / confirm
C_BLUE = "#1577d4"         # running / info / axes
C_AMBER = "#d98a0a"        # hold / warning
C_RED = "#d23b2f"          # alarm / stop / abort

C_TEXT = "#15191d"         # primary text
C_MUTED = "#5c636b"        # secondary text
C_DIM = "#97a0a8"          # labels, captions
C_BORDER = "#dce0e4"       # hairline borders
C_CARD_BORDER = "#d4d9de"  # card border
C_DIVIDER = "#eef1f3"      # in-card dividers

# Accent badges
C_GREEN_BG = "#e6f4ec"
C_GREEN_BORDER = "#bfe3cf"
C_GREEN_TEXT = "#0c7a45"

C_BLUE_BG = "#e6f0fb"
C_BLUE_BORDER = "#bcd6f2"
C_BLUE_TEXT = "#0f5fb0"

C_AMBER_BG = "#fdf3e2"
C_AMBER_BORDER = "#f1d59a"
C_AMBER_TEXT = "#8a5a06"

C_RED_BG = "#fdecec"
C_RED_BORDER = "#f0c0bc"

# Secondary button background
C_BTN_2ND = "#f6f8f9"

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

STATUS_BAR_H = 46
ACTION_RAIL_W = 104
CARD_RADIUS = 12
BTN_RADIUS = 10
TOUCH_MIN = 46      # min touch target height
TOUCH_PRIMARY = 60  # primary action height

# ---------------------------------------------------------------------------
# Main QSS stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
/* ---- Base ---- */
QWidget {{
    background-color: {C_BG};
    color: {C_TEXT};
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 14px;
}}

QMainWindow {{
    background-color: {C_BG};
}}

/* ---- Cards ---- */
QFrame#card {{
    background-color: {C_CARD};
    border: 1px solid {C_CARD_BORDER};
    border-radius: {CARD_RADIUS}px;
}}

/* ---- Status bar ---- */
QFrame#statusBar {{
    background-color: {C_STATUS_BAR};
    border-bottom: 1px solid {C_BORDER};
    border-radius: 0;
}}

/* ---- Action rail ---- */
QFrame#actionRail {{
    background-color: {C_RAIL};
    border-left: 1px solid {C_BORDER};
    border-radius: 0;
}}

/* ---- Buttons ---- */

/* Primary (green) */
QPushButton#btnPrimary {{
    background-color: {C_GREEN};
    color: white;
    border: none;
    border-radius: {BTN_RADIUS}px;
    font-size: 16px;
    font-weight: 700;
    padding: 0 18px;
}}
QPushButton#btnPrimary:pressed {{
    background-color: #0d7a47;
}}
QPushButton#btnPrimary:disabled {{
    background-color: {C_CARD_BORDER};
    color: {C_DIM};
}}

/* Secondary (gray) */
QPushButton#btnSecondary {{
    background-color: {C_BTN_2ND};
    color: {C_TEXT};
    border: 1px solid {C_CARD_BORDER};
    border-radius: {BTN_RADIUS}px;
    font-size: 14px;
    font-weight: 700;
    padding: 0 14px;
}}
QPushButton#btnSecondary:pressed {{
    background-color: #e3e7ea;
}}

/* Danger (red) */
QPushButton#btnDanger {{
    background-color: {C_RED};
    color: white;
    border: none;
    border-radius: {BTN_RADIUS}px;
    font-size: 16px;
    font-weight: 700;
    padding: 0 14px;
}}
QPushButton#btnDanger:pressed {{
    background-color: #aa2e25;
}}

/* Warning (amber) */
QPushButton#btnWarning {{
    background-color: {C_AMBER};
    color: white;
    border: none;
    border-radius: {BTN_RADIUS}px;
    font-size: 16px;
    font-weight: 700;
    padding: 0 14px;
}}
QPushButton#btnWarning:pressed {{
    background-color: #b37008;
}}

/* Rail buttons */
QPushButton#btnRail {{
    background-color: {C_CARD};
    color: {C_TEXT};
    border: 1px solid {C_CARD_BORDER};
    border-radius: {BTN_RADIUS}px;
    font-size: 13px;
    font-weight: 600;
    padding: 0;
}}
QPushButton#btnRail:pressed {{
    background-color: {C_BTN_2ND};
}}

/* Jog step buttons */
QPushButton#btnStep {{
    background-color: {C_BTN_2ND};
    color: {C_MUTED};
    border: 1px solid {C_CARD_BORDER};
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#btnStep:pressed, QPushButton#btnStep[active="true"] {{
    background-color: {C_GREEN};
    color: white;
    border-color: {C_GREEN};
}}

/* Jog direction buttons */
QPushButton#btnJog {{
    background-color: {C_BTN_2ND};
    color: {C_TEXT};
    border: 1px solid {C_CARD_BORDER};
    border-radius: {BTN_RADIUS}px;
    font-size: 22px;
}}
QPushButton#btnJog:pressed {{
    background-color: #dbe6f5;
    border-color: {C_BLUE};
}}

/* Tile buttons (home screen) */
QPushButton#btnTile {{
    background-color: {C_CARD};
    color: {C_TEXT};
    border: 1px solid {C_CARD_BORDER};
    border-radius: {CARD_RADIUS}px;
    text-align: left;
    padding: 14px;
    font-weight: 700;
    font-size: 17px;
}}
QPushButton#btnTile:pressed {{
    background-color: #f0f2f4;
}}

/* ---- Labels ---- */
QLabel#labelSection {{
    color: {C_DIM};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
    border: none;
}}

QLabel#labelDRO {{
    color: {C_TEXT};
    font-size: 33px;
    font-weight: 700;
    background: transparent;
    border: none;
    font-variant-numeric: tabular-nums;
}}

QLabel#labelMPos {{
    color: {C_DIM};
    font-size: 12px;
    background: transparent;
    border: none;
}}

QLabel#labelAxis {{
    color: {C_BLUE};
    font-size: 22px;
    font-weight: 700;
    background: transparent;
    border: none;
}}

QLabel#labelMuted {{
    color: {C_MUTED};
    font-size: 13px;
    background: transparent;
    border: none;
}}

QLabel#labelTitle {{
    color: {C_TEXT};
    font-size: 17px;
    font-weight: 700;
    background: transparent;
    border: none;
}}

/* ---- Progress bar ---- */
QProgressBar {{
    background-color: #e3e7ea;
    border: none;
    border-radius: 4px;
    height: 9px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {C_BLUE};
    border-radius: 4px;
}}

/* ---- Scroll areas ---- */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    width: 6px;
    background: {C_BG};
}}
QScrollBar::handle:vertical {{
    background: {C_CARD_BORDER};
    border-radius: 3px;
}}

/* ---- Mode badge labels ---- */
QLabel#badgeCNC {{
    color: {C_GREEN_TEXT};
    background-color: {C_GREEN_BG};
    border: 1px solid {C_GREEN_BORDER};
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 5px 10px;
}}
QLabel#badgeLASER {{
    color: {C_BLUE_TEXT};
    background-color: {C_BLUE_BG};
    border: 1px solid {C_BLUE_BORDER};
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 5px 10px;
}}
"""


def make_card(parent=None):
    """Return a QFrame styled as a white card."""
    from .qt_compat import QFrame
    f = QFrame(parent)
    f.setObjectName("card")
    return f


def section_label(text: str, parent=None):
    """Return a section-caps QLabel."""
    from .qt_compat import QLabel
    lbl = QLabel(text.upper(), parent)
    lbl.setObjectName("labelSection")
    return lbl
