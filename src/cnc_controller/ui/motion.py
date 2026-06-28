"""Low-cost motion and touch feedback tuned for a Raspberry Pi 3B."""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from .qt_compat import (
    Qt,
    QEvent,
    QObject,
    QPoint,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QPropertyAnimation,
    QEasingCurve,
    QScroller,
    QScrollerProperties,
    Signal,
)


MOTION_CONFIG_PATH = (
    Path.home() / ".config" / "cnc-controller" / "motion.json"
)


class MotionMode(str, Enum):
    STANDARD = "standard"
    REDUCED = "reduced"
    OFF = "off"


def _load_mode(path: Path) -> MotionMode:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("mode")
        return MotionMode(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return MotionMode.STANDARD


def _save_mode(path: Path, mode: MotionMode) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"mode": mode.value}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class MotionController(QObject):
    """Coordinates motion so the UI never runs competing animation styles."""

    mode_changed = Signal(str)

    STANDARD_DURATION = 180
    REDUCED_DURATION = 90
    BUTTON_RELEASE_DURATION = 100

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        config_path: Path = MOTION_CONFIG_PATH,
    ):
        super().__init__(parent)
        self._config_path = config_path
        self._mode = _load_mode(config_path)
        self._button_animations: dict[QPushButton, QPropertyAnimation] = {}
        self._property_animations: dict[tuple[int, bytes], QPropertyAnimation] = {}
        self._pulse_animations: dict[object, QPropertyAnimation] = {}
        self._screen_animation: QPropertyAnimation | None = None
        self._screen_overlay: QLabel | None = None
        self._screen_page = None
        self._installed = False

    @property
    def mode(self) -> MotionMode:
        return self._mode

    @property
    def duration(self) -> int:
        if self._mode is MotionMode.OFF:
            return 0
        if self._mode is MotionMode.REDUCED:
            return self.REDUCED_DURATION
        return self.STANDARD_DURATION

    def set_mode(self, mode: MotionMode | str) -> None:
        selected = MotionMode(mode)
        if selected is self._mode:
            return
        self._mode = selected
        _save_mode(self._config_path, selected)
        self.mode_changed.emit(selected.value)

    def install(self, application: QObject) -> None:
        if self._installed:
            return
        application.installEventFilter(self)
        self._installed = True

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if isinstance(watched, QPushButton) and watched.isEnabled():
            if event_type == QEvent.MouseButtonPress:
                self._press_button(watched)
            elif event_type in (QEvent.MouseButtonRelease, QEvent.Leave):
                self._release_button(watched)
        elif isinstance(watched, QScrollArea) and event_type == QEvent.Show:
            enable_kinetic_scrolling(watched)
        return False

    def _press_button(self, button: QPushButton) -> None:
        if self._mode is MotionMode.OFF:
            return
        current = self._button_animations.pop(button, None)
        if current:
            current.stop()
            current.deleteLater()
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(button)
            button.setGraphicsEffect(effect)
        effect.setOpacity(0.78)

    def _release_button(self, button: QPushButton) -> None:
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            return
        if self._mode is MotionMode.OFF:
            button.setGraphicsEffect(None)
            return
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setStartValue(effect.opacity())
        animation.setEndValue(1.0)
        animation.setDuration(
            60
            if self._mode is MotionMode.REDUCED
            else self.BUTTON_RELEASE_DURATION
        )
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(
            lambda target=button, active=animation: self._finish_button(
                target, active
            )
        )
        self._button_animations[button] = animation
        animation.start()

    def animate_value(self, target, value: int) -> None:
        """Smooth an integer Qt property without queuing stale updates."""
        if self.duration == 0:
            target.setValue(value)
            return
        key = (id(target), b"value")
        current = self._property_animations.pop(key, None)
        if current is not None:
            current.stop()
            current.deleteLater()
        animation = QPropertyAnimation(target, b"value", self)
        animation.setStartValue(target.value())
        animation.setEndValue(value)
        animation.setDuration(self.duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(
            lambda active=animation, animation_key=key: self._finish_property(
                animation_key, active
            )
        )
        self._property_animations[key] = animation
        animation.start()

    def _finish_property(
        self,
        key: tuple[int, bytes],
        animation: QPropertyAnimation,
    ) -> None:
        if self._property_animations.get(key) is animation:
            self._property_animations.pop(key, None)
        animation.deleteLater()

    def pulse(self, target) -> None:
        """Briefly acknowledge an important state change."""
        if self.duration == 0:
            return
        current = self._pulse_animations.pop(target, None)
        if current is not None:
            current.stop()
            current.deleteLater()
        effect = target.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(effect)
        effect.setOpacity(0.55)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setStartValue(0.55)
        animation.setEndValue(1.0)
        animation.setDuration(self.duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(
            lambda item=target, active=animation: self._finish_pulse(
                item, active
            )
        )
        self._pulse_animations[target] = animation
        animation.start()

    def _finish_pulse(self, target, animation: QPropertyAnimation) -> None:
        if self._pulse_animations.get(target) is not animation:
            return
        self._pulse_animations.pop(target, None)
        target.setGraphicsEffect(None)
        animation.deleteLater()

    def _finish_button(
        self,
        button: QPushButton,
        animation: QPropertyAnimation,
    ) -> None:
        if self._button_animations.get(button) is not animation:
            return
        self._button_animations.pop(button, None)
        button.setGraphicsEffect(None)
        animation.deleteLater()

    def show_page(
        self,
        stack: QStackedWidget,
        page,
        *,
        direction: int = 1,
        animate: bool = True,
    ) -> None:
        current = stack.currentWidget()
        if current is page:
            return
        if (
            not animate
            or self.duration == 0
            or current is None
            or not stack.isVisible()
            or stack.width() <= 0
        ):
            stack.setCurrentWidget(page)
            return

        self._finish_screen_transition()
        snapshot = current.grab()
        overlay = QLabel(stack)
        overlay.setPixmap(snapshot)
        overlay.setGeometry(stack.rect())
        overlay.show()

        stack.setCurrentWidget(page)
        distance = stack.width() if direction >= 0 else -stack.width()
        page.move(distance, 0)
        page.raise_()

        animation = QPropertyAnimation(page, b"pos", self)
        animation.setStartValue(QPoint(distance, 0))
        animation.setEndValue(QPoint(0, 0))
        animation.setDuration(self.duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(self._finish_screen_transition)
        self._screen_overlay = overlay
        self._screen_page = page
        self._screen_animation = animation
        animation.start()

    def _finish_screen_transition(self) -> None:
        animation = self._screen_animation
        self._screen_animation = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        page = self._screen_page
        self._screen_page = None
        if page is not None:
            page.move(0, 0)
        overlay = self._screen_overlay
        self._screen_overlay = None
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()


def enable_kinetic_scrolling(area: QScrollArea) -> None:
    """Enable native touch momentum once per scroll area."""
    viewport = area.viewport()
    if viewport.property("kineticScrolling"):
        return
    viewport.setProperty("kineticScrolling", True)
    viewport.setAttribute(Qt.WA_AcceptTouchEvents, True)
    try:
        gesture = QScroller.ScrollerGestureType.TouchGesture
    except AttributeError:  # PyQt5
        gesture = QScroller.TouchGesture
    QScroller.grabGesture(viewport, gesture)

    scroller = QScroller.scroller(viewport)
    properties = scroller.scrollerProperties()
    try:
        metric = QScrollerProperties.ScrollMetric
    except AttributeError:  # PyQt5
        metric = QScrollerProperties
    properties.setScrollMetric(metric.DecelerationFactor, 0.12)
    properties.setScrollMetric(metric.MaximumVelocity, 0.55)
    properties.setScrollMetric(metric.OvershootDragResistanceFactor, 0.35)
    properties.setScrollMetric(metric.OvershootScrollDistanceFactor, 0.12)
    scroller.setScrollerProperties(properties)
