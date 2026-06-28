"""PySide6 / PyQt5 compatibility shim.

Import Qt classes from here rather than directly from PySide6 or PyQt5 so
the rest of the codebase is insulated from the backend difference.
"""
from __future__ import annotations

try:
    from PySide6.QtCore import (
        Qt, QTimer, QThread, QObject, QSize, QPoint, QRect,
        Signal, Slot, QEvent, QUrl, QPropertyAnimation,
        QEasingCurve, QAbstractAnimation,
    )
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QFrame, QLabel,
        QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
        QStackedWidget, QSizePolicy, QScrollArea, QProgressBar,
        QFileDialog, QMessageBox, QSplitter, QSpacerItem,
        QButtonGroup, QAbstractButton, QScrollBar,
        QLineEdit, QPlainTextEdit,
    )
    from PySide6.QtGui import (
        QFont, QColor, QPalette, QPixmap, QPainter, QPen,
        QBrush, QFontMetrics, QKeyEvent, QResizeEvent, QIcon,
        QFontDatabase, QCursor,
    )
    PYSIDE6 = True
except ImportError:
    from PyQt5.QtCore import (  # type: ignore[no-redef]
        Qt, QTimer, QThread, QObject, QSize, QPoint, QRect,
        pyqtSignal as Signal, pyqtSlot as Slot, QEvent, QUrl,
        QPropertyAnimation, QEasingCurve, QAbstractAnimation,
    )
    from PyQt5.QtWidgets import (  # type: ignore[no-redef]
        QApplication, QMainWindow, QWidget, QFrame, QLabel,
        QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
        QStackedWidget, QSizePolicy, QScrollArea, QProgressBar,
        QFileDialog, QMessageBox, QSplitter, QSpacerItem,
        QButtonGroup, QAbstractButton, QScrollBar,
        QLineEdit, QPlainTextEdit,
    )
    from PyQt5.QtGui import (  # type: ignore[no-redef]
        QFont, QColor, QPalette, QPixmap, QPainter, QPen,
        QBrush, QFontMetrics, QKeyEvent, QResizeEvent, QIcon,
        QFontDatabase, QCursor,
    )
    PYSIDE6 = False

__all__ = [
    "Qt", "QTimer", "QThread", "QObject", "QSize", "QPoint", "QRect",
    "Signal", "Slot", "QEvent", "QUrl", "QPropertyAnimation",
    "QEasingCurve", "QAbstractAnimation", "QApplication", "QMainWindow",
    "QWidget", "QFrame", "QLabel", "QPushButton", "QVBoxLayout",
    "QHBoxLayout", "QGridLayout", "QStackedWidget", "QSizePolicy",
    "QScrollArea", "QProgressBar", "QFileDialog", "QMessageBox",
    "QSplitter", "QSpacerItem", "QButtonGroup", "QAbstractButton",
    "QScrollBar", "QFont", "QColor", "QPalette", "QPixmap", "QPainter",
    "QLineEdit", "QPlainTextEdit",
    "QPen", "QBrush", "QFontMetrics", "QKeyEvent", "QResizeEvent",
    "QIcon", "QFontDatabase", "QCursor", "PYSIDE6",
]
