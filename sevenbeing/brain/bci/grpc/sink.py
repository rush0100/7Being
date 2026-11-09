"""gRPC control fan-out — companion to DeviceService device plugins."""

from __future__ import annotations

from typing import Any, Callable

from ..channels import control_payload
from ..mental.control import ControlOutput

NAME = "grpc"


class GrpcControlSink:
    """Publish control events to a gRPC stream / callback (scaffold hook).

    Device I/O already ships via ``GrpcDeviceDriver`` / DeviceService.
    This sink is the *control* direction: mental/face → remote consumers.
    """

    name = NAME

    def __init__(self) -> None:
        self._publisher: Callable[[dict[str, Any]], None] | None = None
        self._last: dict[str, Any] | None = None

    def set_publisher(self, fn: Callable[[dict[str, Any]], None] | None) -> None:
        self._publisher = fn

    def emit(self, out: ControlOutput) -> None:
        payload = control_payload(out)
        self._last = payload
        if self._publisher is not None:
            self._publisher(payload)

    def close(self) -> None:
        self._publisher = None

    @property
    def last(self) -> dict[str, Any] | None:
        return self._last
