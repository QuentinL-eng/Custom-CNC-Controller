from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class HardwareAction(str, Enum):
    CYCLE_START = "cycle_start"
    FEED_HOLD = "feed_hold"
    RESET = "reset"
    PROBE_Z = "probe_z"
    MODE_CONTEXT = "mode_context"
    JOG_INCREMENT = "jog_increment"
    OVERRIDE_INCREMENT = "override_increment"


@dataclass(frozen=True)
class HardwareEvent:
    action: HardwareAction
    value: int | float | None = None


@dataclass
class HardwareInputRouter:
    """Routes physical or simulated button/encoder events to app callbacks."""

    handlers: dict[HardwareAction, list[Callable[[HardwareEvent], None]]] = field(default_factory=dict)

    def bind(self, action: HardwareAction, handler: Callable[[HardwareEvent], None]) -> None:
        self.handlers.setdefault(action, []).append(handler)

    def dispatch(self, event: HardwareEvent) -> None:
        for handler in self.handlers.get(event.action, []):
            handler(event)
