"""Push ControlOutput toward games / local key injectors."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from ..mental.control import ControlOutput

NAME = "game"


@dataclass(frozen=True)
class GameEvent:
    name: str
    key: str
    source: str
    confidence: float
    t: float = field(default_factory=time.time)

    @classmethod
    def from_control(cls, out: ControlOutput) -> GameEvent:
        return cls(
            name=out.name,
            key=out.key,
            source=out.source,
            confidence=float(out.confidence),
        )


class GameSink:
    """Fan-out of control events (keymap → game / OS inject)."""

    name = NAME

    def __init__(self) -> None:
        self._listeners: list[Callable[[GameEvent], None]] = []
        self._last: GameEvent | None = None
        self._injector: Callable[[str], None] | None = None
        self.inject_enabled = True

    def on(self, fn: Callable[[GameEvent], None]) -> None:
        self._listeners.append(fn)

    def set_injector(self, fn: Callable[[str], None] | None) -> None:
        self._injector = fn

    def emit(self, out: ControlOutput | GameEvent) -> GameEvent:
        event = out if isinstance(out, GameEvent) else GameEvent.from_control(out)
        self._last = event
        for fn in list(self._listeners):
            fn(event)
        if (
            self.inject_enabled
            and self._injector is not None
            and event.key
            and event.name != "Neutral"
        ):
            self._injector(event.key)
        return event

    def close(self) -> None:
        self._listeners.clear()
        self._injector = None

    @property
    def last(self) -> GameEvent | None:
        return self._last
