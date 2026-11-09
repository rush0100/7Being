"""Brain → BCI — multi-device EEG, mental commands, local GUI."""

from __future__ import annotations

from .channels import CHANNELS, OUTPUTS, Channel, ChannelHub, Output, build_default_hub
from .core import CORE, AppCore
from .devices import (
    COMMON_CHANNEL_COUNTS,
    DeviceCallbacks,
    DeviceInfo,
    DeviceKind,
    DeviceManager,
    EPOCX_MONTAGE,
    Montage,
    discover_drivers,
    labels_for,
)

__all__ = [
    "AppCore",
    "CHANNELS",
    "COMMON_CHANNEL_COUNTS",
    "CORE",
    "Channel",
    "ChannelHub",
    "DeviceCallbacks",
    "DeviceInfo",
    "DeviceKind",
    "DeviceManager",
    "EPOCX_MONTAGE",
    "Montage",
    "OUTPUTS",
    "Output",
    "build_default_hub",
    "discover_drivers",
    "labels_for",
    "run_gui",
]


def run_gui(host: str | None = None, port: int | None = None) -> None:
    from .gui import server as gui

    if host is not None:
        gui.HOST = host
    if port is not None:
        gui.PORT = port
    gui.main()
