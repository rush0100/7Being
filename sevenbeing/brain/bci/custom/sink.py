"""Custom channel — user-defined adapters and hooks."""

from __future__ import annotations

from typing import Any, Callable

from ..channels import control_payload
from ..mental.control import ControlOutput

NAME = "custom"
Handler = Callable[[ControlOutput, dict[str, Any]], None]


class CustomSink:
    """Call arbitrary handlers with ControlOutput + stable payload dict."""

    name = NAME

    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._last: dict[str, Any] | None = None

    def on(self, fn: Handler) -> None:
        self._handlers.append(fn)

    def emit(self, out: ControlOutput) -> None:
        payload = control_payload(out)
        self._last = payload
        for fn in list(self._handlers):
            fn(out, payload)

    def close(self) -> None:
        self._handlers.clear()

    @property
    def last(self) -> dict[str, Any] | None:
        return self._last
