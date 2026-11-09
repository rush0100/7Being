"""Multi-device registry: scan / connect / primary — gRPC device daemons + local plugins."""

from __future__ import annotations

import json
import os
import threading
from typing import Iterable

from .base import (
    DeviceCallbacks,
    DeviceDriver,
    DeviceInfo,
    DeviceKind,
    LiveDevice,
    SampleHandler,
)
from .plugins import discover_drivers


class DeviceManager:
    """Holds many live devices; mental/GUI usually consume ``primary``.

    Preferred transport: **gRPC** to per-device daemons
    (``7being-emotiv-epocx-serve``, etc.). Attach with ``attach_grpc("host:port")``
    or env ``SEVENBEING_DEVICE_GRPC=127.0.0.1:51051,127.0.0.1:51052``.

    Optional in-process drivers still load from entry points ``sevenbeing.devices``
    (useful for tests). Production path is gRPC process isolation.
    """

    def __init__(self, *, autoload: bool = True) -> None:
        self._lock = threading.RLock()
        self._drivers: dict[DeviceKind | str, DeviceDriver] = {}
        self._local_drivers: dict[DeviceKind | str, DeviceDriver] = {}
        self._grpc_endpoints: dict[str, DeviceDriver] = {}
        self._live: dict[str, LiveDevice] = {}
        self._primary_id: str | None = None
        self._sample_handlers: list[SampleHandler] = []
        if autoload:
            self.reload_plugins()
            self.attach_grpc_from_env()

    def reload_plugins(self) -> list[str]:
        """(Re)load optional in-process drivers from entry points."""
        loaded: list[str] = []
        for driver in discover_drivers():
            self.register(driver, source="plugin")
            kind = getattr(driver, "kind", None)
            loaded.append(kind.value if isinstance(kind, DeviceKind) else str(kind))
        return loaded

    def attach_grpc(self, endpoint: str) -> DeviceDriver:
        """Connect to a device package's DeviceService and register its kind."""
        from ..grpc.client import GrpcDeviceDriver

        endpoint = endpoint.strip()
        if not endpoint:
            raise ValueError("empty gRPC endpoint")
        with self._lock:
            existing = self._grpc_endpoints.get(endpoint)
            if existing is not None:
                return existing
        driver = GrpcDeviceDriver(endpoint)
        # Probe once so dead endpoints do not silently replace local BLE.
        try:
            _ = driver.kind
            if getattr(driver, "_kind_ready", False) is False:
                raise RuntimeError(f"gRPC device offline: {endpoint}")
            # GetKind failure leaves kind as GENERIC — reject that for attach.
            kind = driver.kind
            kind_s = kind.value if isinstance(kind, DeviceKind) else str(kind)
            if kind_s in ("", "generic"):
                # Retry probe explicitly
                driver._kind_ready = False
                driver._ensure_kind()
                kind = driver.kind
                kind_s = kind.value if isinstance(kind, DeviceKind) else str(kind)
                if kind_s in ("", "generic"):
                    raise RuntimeError(f"gRPC device offline: {endpoint}")
        except Exception:
            try:
                driver.close()
            except Exception:
                pass
            raise
        with self._lock:
            self._grpc_endpoints[endpoint] = driver
        self.register(driver, source="grpc")
        return driver

    def attach_grpc_from_env(self, env_var: str = "SEVENBEING_DEVICE_GRPC") -> list[str]:
        raw = os.environ.get(env_var, "")
        attached: list[str] = []
        for part in raw.split(","):
            ep = part.strip()
            if not ep:
                continue
            try:
                self.attach_grpc(ep)
                attached.append(ep)
            except Exception:
                continue
        return attached

    def register(self, driver: DeviceDriver, *, source: str = "plugin") -> None:
        with self._lock:
            kind = driver.kind
            if source != "grpc":
                self._local_drivers[kind] = driver
                # Keep an active gRPC driver if already attached for this kind.
                current = self._drivers.get(kind)
                if current is not None and current is not driver:
                    if type(current).__name__ == "GrpcDeviceDriver":
                        return
            self._drivers[kind] = driver

    def kinds(self) -> list[str]:
        with self._lock:
            out: list[str] = []
            for k in self._drivers:
                out.append(k.value if isinstance(k, DeviceKind) else str(k))
            return out

    def scan(
        self,
        kinds: Iterable[DeviceKind | str] | None = None,
        timeout: float = 5.0,
        *,
        errors_out: list[str] | None = None,
    ) -> list[DeviceInfo]:
        with self._lock:
            drivers = list(self._drivers.items())
            local = dict(getattr(self, "_local_drivers", {}))
        if not drivers:
            return []
        wanted: set[str] | None = None
        if kinds is not None:
            wanted = set()
            for item in kinds:
                wanted.add(item.value if isinstance(item, DeviceKind) else str(item))
        found: list[DeviceInfo] = []
        for kind, driver in drivers:
            key = kind.value if isinstance(kind, DeviceKind) else str(kind)
            if wanted is not None and key not in wanted:
                continue
            try:
                found.extend(driver.scan(timeout=timeout))
            except Exception as exc:
                if errors_out is not None:
                    errors_out.append(f"{key}: {exc}")
                fallback = local.get(kind)
                if fallback is not None and fallback is not driver:
                    try:
                        found.extend(fallback.scan(timeout=timeout))
                    except Exception as exc2:
                        if errors_out is not None:
                            errors_out.append(f"{key}/local: {exc2}")
                continue
        return found

    def connect(
        self,
        info: DeviceInfo,
        callbacks: DeviceCallbacks | None = None,
        *,
        make_primary: bool = True,
    ) -> LiveDevice:
        with self._lock:
            driver = self._drivers.get(info.kind)
            if driver is None:
                raise KeyError(
                    f"no driver for kind {info.kind!r} — install the matching "
                    f"device package (loaded: {self.kinds()})"
                )
            user = callbacks or DeviceCallbacks()
            merged = self._merge_callbacks(user)

            existing = self._live.get(info.id)
            if existing is not None:
                thread = getattr(existing, "_thread", None)
                starting = bool(thread and thread.is_alive() and not getattr(existing, "_stop", threading.Event()).is_set())
                if existing.connected or starting:
                    # gRPC live handles have no `.callbacks`; the daemon client
                    # keeps them. Rebind or the GUI never sees samples.
                    self._bind_callbacks(existing, merged)
                    if make_primary:
                        self._primary_id = info.id
                    return existing
                try:
                    existing.stop()
                except Exception:
                    pass
                self._live.pop(info.id, None)

            live = driver.connect(info, merged)
            self._live[info.id] = live
            if make_primary or self._primary_id is None:
                self._primary_id = info.id
            return live

    def _bind_callbacks(self, live: LiveDevice, callbacks: DeviceCallbacks) -> None:
        setter = getattr(live, "set_callbacks", None)
        if callable(setter):
            setter(callbacks)
            return
        if hasattr(live, "callbacks"):
            live.callbacks = callbacks  # type: ignore[attr-defined]

    def _merge_callbacks(self, user: DeviceCallbacks) -> DeviceCallbacks:
        def on_sample(device_id: str, values: list[float]) -> None:
            self._fanout_sample(device_id, values)
            if user.on_sample:
                user.on_sample(device_id, values)

        return DeviceCallbacks(
            on_sample=on_sample,
            on_motion=user.on_motion,
            on_brain=user.on_brain,
            on_cq=user.on_cq,
            on_counter=user.on_counter,
            on_status=user.on_status,
        )

    def connect_id(
        self,
        device_id: str,
        *,
        scanned: list[DeviceInfo] | None = None,
        frontend: dict | None = None,
    ) -> LiveDevice:
        with self._lock:
            existing = self._live.get(device_id)
            if existing is None:
                for live in self._live.values():
                    addr = (live.info.address or "").upper()
                    if addr and addr in device_id.upper():
                        existing = live
                        break
            if existing is not None:
                info = existing.info
            else:
                info = None
        if info is None:
            pool = scanned or self.scan()
            for cand in pool:
                if cand.id == device_id or (cand.address and cand.address.upper() in device_id.upper()):
                    info = cand
                    break
        if info is None:
            raise KeyError(f"device not found: {device_id}")
        already_open = existing is not None and bool(getattr(existing, "connected", False))
        if frontend is not None and isinstance(info.meta, dict):
            info.meta["frontend"] = json.dumps(frontend)
        live = self.connect(info)
        # A new Open carries frontend in meta. An already-open device does not
        # reopen, so push the write over Configure.
        if frontend is not None and already_open:
            self.configure(info.id, frontend)
        return live

    def configure(self, device_id: str, payload: dict) -> str:
        """Push an analog front-end config to an open device daemon."""
        with self._lock:
            live = self._live.get(device_id)
            if live is None:
                raise KeyError(f"device not open: {device_id}")
            driver = self._drivers.get(live.info.kind)
            if isinstance(live.info.meta, dict):
                live.info.meta["frontend"] = json.dumps(payload)
        # In-process sessions own the USB handle. gRPC sessions only queue
        # the write on the daemon, so prefer that when the local object can't.
        fn = getattr(live, "configure", None)
        if callable(fn) and type(live).__name__ != "GrpcLiveDevice":
            return str(fn(payload))
        if driver is not None and callable(getattr(driver, "configure", None)):
            return str(driver.configure(device_id, payload))
        raise RuntimeError("device has no front-end config")

    def disconnect(self, device_id: str | None = None) -> None:
        with self._lock:
            if device_id is None:
                ids = list(self._live)
            else:
                ids = [device_id]
            for did in ids:
                live = self._live.pop(did, None)
                if live is not None:
                    live.stop()
            if self._primary_id not in self._live:
                self._primary_id = next(iter(self._live), None)

    def set_primary(self, device_id: str) -> None:
        with self._lock:
            if device_id not in self._live:
                raise KeyError(device_id)
            self._primary_id = device_id

    @property
    def primary_id(self) -> str | None:
        with self._lock:
            return self._primary_id

    def primary(self) -> LiveDevice | None:
        with self._lock:
            if self._primary_id is None:
                return None
            return self._live.get(self._primary_id)

    def get(self, device_id: str) -> LiveDevice | None:
        with self._lock:
            return self._live.get(device_id)

    def connected(self) -> list[LiveDevice]:
        with self._lock:
            return [d for d in self._live.values() if d.connected]

    def on_sample(self, handler: SampleHandler) -> None:
        """Subscribe to samples from every connected device (device_id, channels)."""
        with self._lock:
            self._sample_handlers.append(handler)

    def _fanout_sample(self, device_id: str, values: list[float]) -> None:
        with self._lock:
            handlers = list(self._sample_handlers)
        for handler in handlers:
            try:
                handler(device_id, values)
            except Exception:
                continue

    def public_state(self) -> dict:
        from .montage import COMMON_CHANNEL_COUNTS

        with self._lock:
            return {
                "kinds": self.kinds(),
                "kinds_known": [k.value for k in DeviceKind],
                "plugins": self.kinds(),
                "grpc_endpoints": list(self._grpc_endpoints),
                "channel_counts": list(COMMON_CHANNEL_COUNTS),
                "primary_id": self._primary_id,
                "connected": [d.public_state() for d in self._live.values()],
            }
