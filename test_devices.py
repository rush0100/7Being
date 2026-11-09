#!/usr/bin/env python3
"""DeviceManager + montage + plugin loader checks (BLE optional)."""

from __future__ import annotations

from sevenbeing.devices.base import DeviceCallbacks, DeviceInfo, DeviceKind
from sevenbeing.devices.manager import DeviceManager
from sevenbeing.devices.montage import COMMON_CHANNEL_COUNTS, Montage, labels_for
from sevenbeing.devices.plugins import ENTRY_POINT_GROUP, discover_drivers
from sevenbeing.mental.features import FeatureExtractor, feat_dim


def test_kinds_and_public() -> None:
    mgr = DeviceManager(autoload=True)
    state = mgr.public_state()
    assert "kinds" in state and "connected" in state
    assert state["primary_id"] is None
    assert 1 in state["channel_counts"] and 14 in state["channel_counts"]
    assert ENTRY_POINT_GROUP == "sevenbeing.devices"
    # Plugins appear only if the matching pip package is installed.
    for kind in mgr.kinds():
        assert isinstance(kind, str)


def test_montages_multi_ch() -> None:
    assert COMMON_CHANNEL_COUNTS[0] == 1
    for n in (1, 2, 4, 6, 8, 14, 16):
        m = Montage.for_count(n)
        assert m.n_channels == n
        assert len(labels_for(n)) == n
        fx = FeatureExtractor(rate=128, n_ch=n)
        assert fx.feat_dim == feat_dim(n)
        row = [0.0] * n
        got = None
        for i in range(400):
            out = fx.push([v + i * 0.01 for v in row])
            if out is not None:
                got = out
        assert got is not None and got.shape == (feat_dim(n),)


def test_device_kind_ids() -> None:
    assert DeviceKind.EPOCX.value == "epocx"
    assert DeviceKind.H1.value == "h1"
    assert DeviceKind.ADS1299.value == "ads1299"
    info = DeviceInfo(
        id="generic:usb-8",
        kind=DeviceKind.GENERIC,
        name="DIY-8",
        n_channels=8,
    )
    assert info.n_channels == 8


def test_rebind_callbacks_on_open_device() -> None:
    """A second connect must install GUI handlers on an already-open device."""

    class Live:
        def __init__(self) -> None:
            self.info = DeviceInfo(
                id="h1:test",
                kind=DeviceKind.H1,
                name="H1",
                n_channels=1,
                channels=("Fpz",),
                sample_rate_hz=250,
            )
            self.callbacks = None
            self._connected = True

        @property
        def connected(self) -> bool:
            return self._connected

        def set_callbacks(self, callbacks: DeviceCallbacks) -> None:
            self.callbacks = callbacks

        def public_state(self) -> dict:
            return {}

        def stop(self) -> None:
            self._connected = False

    holder: dict[str, Live] = {}

    class Driver:
        kind = DeviceKind.H1

        def scan(self, timeout: float = 5.0) -> list[DeviceInfo]:
            _ = timeout
            return []

        def connect(self, info: DeviceInfo, callbacks: DeviceCallbacks) -> Live:
            _ = info
            live = Live()
            live.set_callbacks(callbacks)
            holder["live"] = live
            return live

    mgr = DeviceManager(autoload=False)
    mgr.register(Driver())
    info = DeviceInfo(
        id="h1:test",
        kind=DeviceKind.H1,
        name="H1",
        n_channels=1,
        channels=("Fpz",),
        sample_rate_hz=250,
    )
    mgr.connect(info)
    seen: list[list[float]] = []
    again = mgr.connect(info, DeviceCallbacks(on_sample=lambda _i, values: seen.append(values)))
    assert again is holder["live"]
    assert holder["live"].callbacks is not None
    holder["live"].callbacks.on_sample("h1:test", [1.5])
    assert seen == [[1.5]]


def test_discover_drivers_callable() -> None:
    drivers = discover_drivers()
    assert isinstance(drivers, list)


if __name__ == "__main__":
    test_kinds_and_public()
    test_montages_multi_ch()
    test_device_kind_ids()
    test_rebind_callbacks_on_open_device()
    test_discover_drivers_callable()
    print("device tests passed")
