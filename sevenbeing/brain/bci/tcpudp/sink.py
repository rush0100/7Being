"""TCP/UDP channel — raw socket control frames."""

from __future__ import annotations

import json
from typing import Any, Callable, Literal

from ..channels import control_payload
from ..mental.control import ControlOutput

NAME = "tcpudp"
Transport = Literal["tcp", "udp"]


class TcpUdpSink:
    """Scaffold sink. Inject a sender ``(transport, host, port, bytes)``."""

    name = NAME

    def __init__(self) -> None:
        self.transport: Transport = "udp"
        self.host = "127.0.0.1"
        self.port = 7700
        self._sender: Callable[[Transport, str, int, bytes], None] | None = None
        self._last: dict[str, Any] | None = None

    def configure(
        self,
        *,
        transport: Transport | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        if transport is not None:
            self.transport = transport
        if host is not None:
            self.host = host
        if port is not None:
            self.port = int(port)

    def set_sender(self, fn: Callable[[Transport, str, int, bytes], None] | None) -> None:
        self._sender = fn

    def emit(self, out: ControlOutput) -> None:
        payload = control_payload(out)
        self._last = payload
        if self._sender is None:
            return
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._sender(self.transport, self.host, self.port, body)

    def close(self) -> None:
        self._sender = None

    @property
    def last(self) -> dict[str, Any] | None:
        return self._last
