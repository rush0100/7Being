"""Multi-device layer — gRPC device daemons (+ optional in-process plugins)."""

from .base import DeviceCallbacks, DeviceInfo, DeviceKind
from .manager import DeviceManager
from .montage import (
    COMMON_CHANNEL_COUNTS,
    EPOCX_MONTAGE,
    Montage,
    labels_for,
)
from .catalog import CATALOG, install_plugin, list_plugins, plugin_by_id
from .plugins import ENTRY_POINT_GROUP, discover_drivers

__all__ = [
    "CATALOG",
    "COMMON_CHANNEL_COUNTS",
    "DeviceCallbacks",
    "DeviceInfo",
    "DeviceKind",
    "DeviceManager",
    "EPOCX_MONTAGE",
    "ENTRY_POINT_GROUP",
    "Montage",
    "discover_drivers",
    "install_plugin",
    "labels_for",
    "list_plugins",
    "plugin_by_id",
]
