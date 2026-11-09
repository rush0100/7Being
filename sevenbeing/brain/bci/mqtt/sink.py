"""MQTT IoT channel — publish control (and later EEG) over MQTT."""

from __future__ import annotations

import json
from typing import Any, Callable

from ..channels import control_payload
from ..mental.control import ControlOutput

NAME = "mqtt"


class MqttSink:
    """Scaffold sink. Wire a real client via ``configure`` / ``set_publisher``."""

    name = NAME

    def __init__(self) -> None:
        self.broker = "mqtt://127.0.0.1:1883"
        self.topic = "7being/bci/control"
        self._publisher: Callable[[str, bytes], None] | None = None
        self._last: dict[str, Any] | None = None
        self._connected = False

    def configure(self, *, broker: str | None = None, topic: str | None = None) -> None:
        if broker is not None:
            self.broker = broker
        if topic is not None:
            self.topic = topic

    def set_publisher(self, fn: Callable[[str, bytes], None] | None) -> None:
        self._publisher = fn
        self._connected = fn is not None

    def emit(self, out: ControlOutput) -> None:
        payload = control_payload(out)
        self._last = payload
        if self._publisher is None:
            return
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._publisher(self.topic, body)

    def close(self) -> None:
        self._publisher = None
        self._connected = False

    @property
    def last(self) -> dict[str, Any] | None:
        return self._last

    @property
    def connected(self) -> bool:
        return self._connected
