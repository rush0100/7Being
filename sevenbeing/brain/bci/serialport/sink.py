"""Serialport channel — UART / USB-serial control frames."""

from __future__ import annotations

import json
from typing import Any, Callable

from ..channels import control_payload
from ..mental.control import ControlOutput

NAME = "serialport"


class SerialportSink:
    """Scaffold sink. Inject a writer that accepts newline-delimited JSON."""

    name = NAME

    def __init__(self) -> None:
        self.port = ""
        self.baudrate = 115200
        self._writer: Callable[[bytes], None] | None = None
        self._last: dict[str, Any] | None = None

    def configure(self, *, port: str | None = None, baudrate: int | None = None) -> None:
        if port is not None:
            self.port = port
        if baudrate is not None:
            self.baudrate = int(baudrate)

    def set_writer(self, fn: Callable[[bytes], None] | None) -> None:
        self._writer = fn

    def emit(self, out: ControlOutput) -> None:
        payload = control_payload(out)
        self._last = payload
        if self._writer is None:
            return
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        self._writer(line)

    def close(self) -> None:
        self._writer = None

    @property
    def last(self) -> dict[str, Any] | None:
        return self._last
