"""gRPC client that presents a remote DeviceService as a local DeviceDriver."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from ..devices.base import DeviceCallbacks, DeviceInfo, DeviceKind, LiveDevice
from .codec import SERVICE_NAME, dumps, loads
from .server import info_to_msg, msg_to_info

try:
    import grpc
except ImportError as exc:  # pragma: no cover
    grpc = None  # type: ignore[assignment]
    _GRPC_ERR = exc
else:
    _GRPC_ERR = None


def _require_grpc() -> Any:
    if grpc is None:
        raise ImportError(
            "grpcio is required for device gRPC. Install with: pip install grpcio"
        ) from _GRPC_ERR
    return grpc


def _stub_call(channel: Any, method: str, request: dict, timeout: float | None = None) -> dict:
    grpc = _require_grpc()
    path = f"/{SERVICE_NAME}/{method}"
    fn = channel.unary_unary(
        path,
        request_serializer=dumps,
        response_deserializer=loads,
    )
    return fn(request, timeout=timeout)


def _stub_stream(channel: Any, method: str, request: dict):
    path = f"/{SERVICE_NAME}/{method}"
    fn = channel.unary_stream(
        path,
        request_serializer=dumps,
        response_deserializer=loads,
    )
    return fn(request)


class GrpcLiveDevice:
    def __init__(self, info: DeviceInfo, client: "GrpcDeviceDriver") -> None:
        self.info = info
        self._client = client
        self._connected = True
        self._sample_rate = int(info.sample_rate_hz or 128)
        self._detail = ""
        self._battery: int | None = None
        self._locked = False
        self._state_at = 0.0

    def set_callbacks(self, callbacks: DeviceCallbacks) -> None:
        """Replace handlers after the device is already open."""
        self._client._callbacks[self.info.id] = callbacks

    @property
    def connected(self) -> bool:
        return self._connected and self._client._open_ids.get(self.info.id) is self

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def n_channels(self) -> int:
        return self.info.n_channels

    def stop(self) -> None:
        self._client._close_remote(self.info.id)
        self._connected = False

    def public_state(self) -> dict:
        now = time.monotonic()
        if now - self._state_at >= 0.4:
            self._state_at = now
            try:
                state = _stub_call(
                    self._client._channel,
                    "GetState",
                    {"device_id": self.info.id},
                    timeout=0.8,
                )
                self._apply_state(state)
            except Exception:
                pass
        return {
            **self.info.to_public(),
            "connected": self.connected,
            "sample_rate": self._sample_rate,
            "n_channels": self.n_channels,
            "channels": list(self.info.channels),
            "detail": self._detail,
            "battery": self._battery,
            "locked": self._locked,
            "transport": "grpc",
            "endpoint": self._client.endpoint,
        }

    def _apply_state(self, state: dict) -> None:
        # A device can report connected=false for a moment while the link
        # comes up. Only a closed session should drop the local flag.
        if str(state.get("detail") or "") == "not open":
            self._connected = False
        elif state.get("connected"):
            self._connected = True
        self._sample_rate = int(state.get("sample_rate") or self._sample_rate)
        self._detail = str(state.get("detail") or "")
        batt = state.get("battery")
        self._battery = None if batt is None else int(batt)
        self._locked = bool(state.get("locked"))


class GrpcDeviceDriver:
    """DeviceDriver facade over a remote ``DeviceService`` daemon."""

    def __init__(self, endpoint: str, *, kind: DeviceKind | str | None = None) -> None:
        _require_grpc()
        self.endpoint = endpoint
        self._channel = grpc.insecure_channel(endpoint)
        self._kind: DeviceKind | str = kind or DeviceKind.GENERIC
        self._kind_ready = kind is not None
        self._open_ids: dict[str, GrpcLiveDevice] = {}
        self._callbacks: dict[str, DeviceCallbacks] = {}
        self._sub_stop = threading.Event()
        self._sub_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._ensure_kind()
        self._ensure_subscribe()

    @property
    def kind(self) -> DeviceKind | str:
        self._ensure_kind()
        return self._kind

    def _ensure_kind(self) -> None:
        if self._kind_ready:
            return
        try:
            resp = _stub_call(self._channel, "GetKind", {}, timeout=3.0)
            value = str(resp.get("kind") or "generic")
            try:
                self._kind = DeviceKind(value)
            except ValueError:
                self._kind = value
            self._kind_ready = True
        except Exception:
            self._kind = DeviceKind.GENERIC

    def _ensure_subscribe(self) -> None:
        if self._sub_thread and self._sub_thread.is_alive():
            return
        self._sub_stop.clear()
        self._sub_thread = threading.Thread(
            target=self._subscribe_loop, daemon=True, name=f"grpc-sub-{self.endpoint}"
        )
        self._sub_thread.start()

    def _subscribe_loop(self) -> None:
        while not self._sub_stop.is_set():
            try:
                stream = _stub_stream(self._channel, "Subscribe", {"device_id": ""})
                for event in stream:
                    if self._sub_stop.is_set():
                        break
                    self._dispatch(event)
            except Exception:
                time.sleep(0.5)

    def _dispatch(self, event: dict) -> None:
        if "sample" in event:
            msg = event["sample"]
            cb = self._callbacks.get(msg.get("device_id", ""))
            if cb and cb.on_sample:
                cb.on_sample(msg["device_id"], list(msg.get("values") or []))
            return
        if "motion" in event:
            msg = event["motion"]
            cb = self._callbacks.get(msg.get("device_id", ""))
            if cb and cb.on_motion:
                cb.on_motion(msg["device_id"], list(msg.get("values") or []))
            return
        if "cq" in event:
            msg = event["cq"]
            cb = self._callbacks.get(msg.get("device_id", ""))
            if cb and cb.on_cq:
                cb.on_cq(msg["device_id"], int(msg["index"]), float(msg["value"]))
            return
        if "counter" in event:
            msg = event["counter"]
            cb = self._callbacks.get(msg.get("device_id", ""))
            if cb and cb.on_counter:
                cb.on_counter(msg["device_id"], int(msg["counter"]))
            return
        if "status" in event:
            msg = event["status"]
            cb = self._callbacks.get(msg.get("device_id", ""))
            if cb and cb.on_status:
                cb.on_status(msg["device_id"], str(msg.get("text") or ""), bool(msg.get("warn")))
            return
        if "brain" in event:
            msg = event["brain"]
            cb = self._callbacks.get(msg.get("device_id", ""))
            if cb and cb.on_brain:
                try:
                    brain = json.loads(msg.get("json") or "{}")
                except Exception:
                    brain = {}
                cb.on_brain(msg["device_id"], brain)
            return
        if "state" in event:
            state = event["state"]
            info = state.get("info") or {}
            did = info.get("id")
            live = self._open_ids.get(did) if did else None
            if live is not None:
                live._apply_state(state)

    def scan(self, timeout: float = 5.0) -> list[DeviceInfo]:
        resp = _stub_call(
            self._channel, "Scan", {"timeout_s": float(timeout)}, timeout=timeout + 5.0
        )
        return [msg_to_info(d) for d in (resp.get("devices") or [])]

    def connect(self, info: DeviceInfo, callbacks: DeviceCallbacks) -> LiveDevice:
        resp = _stub_call(
            self._channel,
            "Open",
            {"device": info_to_msg(info)},
            timeout=30.0,
        )
        if not resp.get("ok", True) and resp.get("error"):
            raise RuntimeError(resp["error"])
        remote = msg_to_info(resp.get("device") or info_to_msg(info))
        live = GrpcLiveDevice(remote, self)
        with self._lock:
            self._open_ids[remote.id] = live
            self._callbacks[remote.id] = callbacks
        self._ensure_subscribe()
        return live

    def configure(self, device_id: str, payload: dict) -> str:
        resp = _stub_call(
            self._channel,
            "Configure",
            {"device_id": device_id, "json": json.dumps(payload)},
            timeout=8.0,
        )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error") or "configure failed"))
        return str(resp.get("detail") or "")

    def _close_remote(self, device_id: str) -> None:
        try:
            _stub_call(self._channel, "Close", {"device_id": device_id}, timeout=5.0)
        except Exception:
            pass
        with self._lock:
            self._open_ids.pop(device_id, None)
            self._callbacks.pop(device_id, None)

    def close(self) -> None:
        self._sub_stop.set()
        for did in list(self._open_ids):
            self._close_remote(did)
        try:
            self._channel.close()
        except Exception:
            pass


def attach_endpoints(endpoints: list[str]) -> list[GrpcDeviceDriver]:
    return [GrpcDeviceDriver(ep.strip()) for ep in endpoints if ep.strip()]
