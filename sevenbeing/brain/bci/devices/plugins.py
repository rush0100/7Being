"""Load device drivers from pip packages via entry points.

Install core, then add hardware packages as needed::

    pip install 7being
    pip install 7being-emotiv-epocx      # Emotiv EPOC / EPOC+ / EPOC X
    pip install 7being-h1         # H1
    pip install 7being-ads1299    # ADS1299EEGFE-PDK

Each device package registers under the group ``sevenbeing.devices``.
"""

from __future__ import annotations

from typing import Iterable

from .base import DeviceDriver

ENTRY_POINT_GROUP = "sevenbeing.devices"


def iter_entry_point_drivers() -> Iterable[DeviceDriver]:
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return

    try:
        selected = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # Python < 3.10 style
        selected = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]

    for ep in selected:
        try:
            obj = ep.load()
        except Exception:
            continue
        try:
            driver = obj() if isinstance(obj, type) else obj
        except Exception:
            continue
        if driver is None:
            continue
        yield driver


def discover_drivers() -> list[DeviceDriver]:
    return list(iter_entry_point_drivers())
