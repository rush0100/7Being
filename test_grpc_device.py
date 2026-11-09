#!/usr/bin/env python3
"""gRPC device transport smoke test (needs grpcio)."""

from __future__ import annotations

import threading
import time

try:
    import grpc  # noqa: F401
except ImportError:
    print("skip: grpcio not installed")
    raise SystemExit(0)

from sevenbeing.devices.base import DeviceCallbacks, DeviceInfo, DeviceKind
from sevenbeing.devices.grpc_client import GrpcDeviceDriver
from sevenbeing.devices.grpc_server import serve
from sevenbeing.devices.manager import DeviceManager
from sevenbeing.devices.montage import Montage


class FakeDriver:
    kind = DeviceKind.GENERIC

    def scan(self, timeout: float = 5.0) -> list[DeviceInfo]:
        _ = timeout
        return [
            DeviceInfo(
                id="generic:fake",
                kind=DeviceKind.GENERIC,
                name="Fake",
                n_channels=4,
                channels=Montage.for_count(4).channels,
                sample_rate_hz=128,
            )
        ]

    def connect(self, info: DeviceInfo, callbacks: DeviceCallbacks):
        live = _FakeLive(info, callbacks)
        live.start()
        return live


class _FakeLive:
    def __init__(self, info: DeviceInfo, callbacks: DeviceCallbacks) -> None:
        self.info = info
        self.callbacks = callbacks
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and not self._stop.is_set()

    @property
    def sample_rate(self) -> int:
        return 128

    @property
    def n_channels(self) -> int:
        return self.info.n_channels

    def start(self) -> None:
        self._stop.clear()
        self._connected = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._connected = False

    def public_state(self) -> dict:
        return {
            **self.info.to_public(),
            "connected": self.connected,
            "sample_rate": 128,
            "detail": "fake",
            "battery": None,
            "locked": True,
        }

    def _run(self) -> None:
        if self.callbacks.on_status:
            self.callbacks.on_status(self.info.id, "fake online", False)
        n = 0
        while not self._stop.is_set():
            if self.callbacks.on_sample:
                self.callbacks.on_sample(self.info.id, [float(n)] * self.info.n_channels)
            n += 1
            time.sleep(0.02)


def main() -> None:
    server = serve(
        FakeDriver(),
        host="127.0.0.1",
        port=51111,
        package="test-fake",
        wait=False,
    )
    time.sleep(0.2)
    try:
        mgr = DeviceManager(autoload=False)
        mgr.attach_grpc("127.0.0.1:51111")
        assert "generic" in mgr.kinds()
        found = mgr.scan(timeout=0.5)
        assert found and found[0].id == "generic:fake"
        got: list[list[float]] = []

        def on_sample(_did: str, values: list[float]) -> None:
            got.append(values)

        live = mgr.connect(found[0], DeviceCallbacks(on_sample=on_sample))
        deadline = time.time() + 2.0
        while time.time() < deadline and len(got) < 3:
            time.sleep(0.05)
        assert len(got) >= 3, got
        live.stop()
        print("grpc device tests passed")
    finally:
        server.stop(0)


if __name__ == "__main__":
    main()
