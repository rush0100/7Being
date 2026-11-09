"""BCI outputs (control channels) — route mental/face commands outward.

Outputs
-------
01 game        — keymap / game / OS key inject
02 mqtt        — MQTT IoT publish
03 serialport  — UART / USB-serial
04 tcpudp      — raw TCP and UDP sockets
05 grpc        — control fan-out over gRPC
06 custom      — user-defined adapters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol

from .mental.control import ControlOutput


@dataclass(frozen=True)
class ChannelInfo:
    code: str
    name: str
    title: str
    blurb: str
    status: str  # shipping | scaffold


class Channel(str, Enum):
    GAME = "game"
    MQTT = "mqtt"
    SERIALPORT = "serialport"
    TCPUDP = "tcpudp"
    GRPC = "grpc"
    CUSTOM = "custom"


# Public alias — "outputs" matches product language; Channel remains the enum.
Output = Channel
OutputInfo = ChannelInfo

CHANNELS: tuple[ChannelInfo, ...] = (
    ChannelInfo("01", "game", "Game", "Mental-command keymap / game control out", "shipping"),
    ChannelInfo("02", "mqtt", "MQTT", "Publish control over MQTT (IoT)", "shipping"),
    ChannelInfo("03", "serialport", "Serialport", "UART / USB-serial control frames", "shipping"),
    ChannelInfo("04", "tcpudp", "TCP/UDP", "Raw TCP and UDP control sockets", "shipping"),
    ChannelInfo("05", "grpc", "gRPC", "Control stream to gRPC consumers", "shipping"),
    ChannelInfo("06", "custom", "Custom", "User-defined adapters and hooks", "shipping"),
)

OUTPUTS = CHANNELS


def channel_by_name(name: str) -> ChannelInfo | None:
    raw = name.strip().lower()
    key = raw.replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "tcpudp": "tcpudp",
        "tcp": "tcpudp",
        "udp": "tcpudp",
        "serial": "serialport",
        "serialport": "serialport",
        "grpc": "grpc",
        "game": "game",
        "games": "game",
        "mqtt": "mqtt",
        "iot": "mqtt",
        "custom": "custom",
    }
    resolved = aliases.get(key, key)
    for item in CHANNELS:
        if item.name == resolved or item.code == raw or item.title.lower().replace("/", "") == key:
            return item
    return None


def control_payload(out: ControlOutput) -> dict:
    """Stable JSON-shaped payload shared by MQTT / TCP / serial / custom."""
    return {
        "name": out.name,
        "key": out.key,
        "source": out.source,
        "confidence": float(out.confidence),
    }


class ControlSink(Protocol):
    name: str

    def emit(self, out: ControlOutput) -> None: ...

    def close(self) -> None: ...


def _resolve_name(name: str) -> str:
    info = channel_by_name(name)
    return info.name if info else name.strip().lower()


def _fingerprint(out: ControlOutput) -> tuple[str, str, str]:
    return (out.name, out.key, out.source)


@dataclass
class ChannelHub:
    """Fan-out ControlOutput to every enabled output sink.

    Dispatches are edge-triggered: identical ``(name, key, source)`` is skipped
    unless ``force=True`` — keeps MQTT / serial / TCP from flooding each sample.
    """

    sinks: dict[str, ControlSink] = field(default_factory=dict)
    enabled: set[str] = field(default_factory=lambda: {Channel.GAME.value})
    _last: tuple[str, str, str] | None = field(default=None, repr=False)

    def register(self, sink: ControlSink) -> ControlSink:
        self.sinks[sink.name] = sink
        return sink

    def get(self, name: str) -> ControlSink | None:
        return self.sinks.get(_resolve_name(name))

    def enable(self, name: str) -> None:
        key = _resolve_name(name)
        if key not in self.sinks:
            raise KeyError(f"unknown output sink: {name}")
        self.enabled.add(key)

    def disable(self, name: str) -> None:
        self.enabled.discard(_resolve_name(name))

    def is_enabled(self, name: str) -> bool:
        return _resolve_name(name) in self.enabled

    def configure(self, name: str, **opts: Any) -> ControlSink:
        """Pass kwargs to ``sink.configure`` when the driver supports it."""
        key = _resolve_name(name)
        sink = self.sinks.get(key)
        if sink is None:
            raise KeyError(f"unknown output sink: {name}")
        configure = getattr(sink, "configure", None)
        if configure is None:
            raise TypeError(f"output {key!r} has no configure()")
        configure(**opts)
        return sink

    def dispatch(self, out: ControlOutput, *, force: bool = False) -> list[str]:
        fp = _fingerprint(out)
        if not force and fp == self._last:
            return []
        self._last = fp
        hit: list[str] = []
        for name in list(self.enabled):
            sink = self.sinks.get(name)
            if sink is None:
                continue
            sink.emit(out)
            hit.append(name)
        return hit

    def close(self) -> None:
        for sink in list(self.sinks.values()):
            sink.close()
        self._last = None

    def public_state(self) -> dict:
        channels = [
            {
                "code": c.code,
                "name": c.name,
                "title": c.title,
                "blurb": c.blurb,
                "status": c.status,
                "enabled": c.name in self.enabled,
                "registered": c.name in self.sinks,
            }
            for c in CHANNELS
        ]
        return {
            "enabled": sorted(self.enabled),
            "last": None
            if self._last is None
            else {"name": self._last[0], "key": self._last[1], "source": self._last[2]},
            "channels": channels,
            "outputs": channels,
        }


# Alias used in docs / public API.
OutputHub = ChannelHub


def build_default_hub() -> ChannelHub:
    """Register all channel sinks; only ``game`` enabled by default."""
    from .custom import CustomSink
    from .game import GameSink
    from .grpc.sink import GrpcControlSink
    from .mqtt import MqttSink
    from .serialport import SerialportSink
    from .tcpudp import TcpUdpSink

    hub = ChannelHub()
    for sink in (
        GameSink(),
        MqttSink(),
        SerialportSink(),
        TcpUdpSink(),
        GrpcControlSink(),
        CustomSink(),
    ):
        hub.register(sink)
    return hub


def iter_channels() -> Iterable[ChannelInfo]:
    return CHANNELS
