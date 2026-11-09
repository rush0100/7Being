"""gRPC DeviceService server — wraps an in-process DeviceDriver for a device package."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import defaultdict, deque
from typing import Any, Iterator

from ..devices.base import DeviceCallbacks, DeviceDriver, DeviceInfo, DeviceKind, LiveDevice
from .codec import SERVICE_NAME, dumps, loads

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


def _kind_value(kind: DeviceKind | str) -> str:
    return kind.value if isinstance(kind, DeviceKind) else str(kind)


def _parse_kind(value: str) -> DeviceKind | str:
    try:
        return DeviceKind(value)
    except ValueError:
        return value


def info_to_msg(info: DeviceInfo) -> dict:
    meta = {str(k): str(v) for k, v in (info.meta or {}).items()}
    return {
        "id": info.id,
        "kind": _kind_value(info.kind),
        "name": info.name,
        "address": info.address or "",
        "n_channels": int(info.n_channels),
        "channels": list(info.channels),
        "sample_rate_hz": int(info.sample_rate_hz or 0),
        "meta": meta,
    }


def msg_to_info(msg: dict) -> DeviceInfo:
    channels = tuple(msg.get("channels") or ())
    n = int(msg.get("n_channels") or (len(channels) if channels else 14))
    rate = int(msg.get("sample_rate_hz") or 0) or None
    return DeviceInfo(
        id=str(msg["id"]),
        kind=_parse_kind(str(msg.get("kind") or "generic")),
        name=str(msg.get("name") or msg["id"]),
        address=(str(msg["address"]) if msg.get("address") else None),
        n_channels=n,
        channels=channels,
        sample_rate_hz=rate,
        meta=dict(msg.get("meta") or {}),
    )


class DeviceServicer:
    """Implements sevenbeing.device.v1.DeviceService over JSON-gRPC."""

    def __init__(
        self,
        driver: DeviceDriver,
        *,
        package: str = "",
        version: str = "0.1.0",
    ) -> None:
        self.driver = driver
        self.package = package
        self.version = version
        self._lock = threading.RLock()
        self._live: dict[str, LiveDevice] = {}
        self._queues: dict[str, list[deque[dict]]] = defaultdict(list)
        self._queues_all: list[deque[dict]] = []

    def _emit(self, device_id: str, event: dict) -> None:
        with self._lock:
            targets = list(self._queues.get(device_id, []))
            targets.extend(self._queues_all)
        for q in targets:
            q.append(event)
            while len(q) > 4096:
                q.popleft()

    def _callbacks_for(self, device_id: str) -> DeviceCallbacks:
        def on_sample(did: str, values: list[float]) -> None:
            self._emit(
                did,
                {
                    "sample": {
                        "device_id": did,
                        "values": [float(v) for v in values],
                        "t_unix_ms": int(time.time() * 1000),
                    }
                },
            )

        def on_motion(did: str, values: list[float]) -> None:
            self._emit(did, {"motion": {"device_id": did, "values": [float(v) for v in values]}})

        def on_cq(did: str, index: int, value: float) -> None:
            self._emit(did, {"cq": {"device_id": did, "index": int(index), "value": float(value)}})

        def on_counter(did: str, counter: int) -> None:
            self._emit(did, {"counter": {"device_id": did, "counter": int(counter)}})

        def on_status(did: str, text: str, warn: bool) -> None:
            self._emit(did, {"status": {"device_id": did, "text": text, "warn": bool(warn)}})

        def on_brain(did: str, brain: dict) -> None:
            self._emit(did, {"brain": {"device_id": did, "json": json.dumps(brain, ensure_ascii=False)}})

        return DeviceCallbacks(
            on_sample=on_sample,
            on_motion=on_motion,
            on_cq=on_cq,
            on_counter=on_counter,
            on_status=on_status,
            on_brain=on_brain,
        )

    def GetKind(self, request: dict, context: Any) -> dict:
        return {
            "kind": _kind_value(self.driver.kind),
            "package": self.package,
            "version": self.version,
        }

    def Scan(self, request: dict, context: Any) -> dict:
        timeout = float(request.get("timeout_s") or 5.0)
        found = self.driver.scan(timeout=timeout)
        return {"devices": [info_to_msg(i) for i in found]}

    def Open(self, request: dict, context: Any) -> dict:
        try:
            info = msg_to_info(request.get("device") or {})
            live = self.driver.connect(info, self._callbacks_for(info.id))
            with self._lock:
                self._live[info.id] = live
            return {"device": info_to_msg(live.info), "ok": True, "error": ""}
        except Exception as exc:
            return {"device": request.get("device") or {}, "ok": False, "error": str(exc)}

    def Close(self, request: dict, context: Any) -> dict:
        device_id = str(request.get("device_id") or "")
        with self._lock:
            if not device_id:
                ids = list(self._live)
            else:
                ids = [device_id]
            for did in ids:
                live = self._live.pop(did, None)
                if live is not None:
                    live.stop()
        return {}

    def Configure(self, request: dict, context: Any) -> dict:
        device_id = str(request.get("device_id") or "")
        with self._lock:
            live = self._live.get(device_id)
        if live is None:
            return {"ok": False, "detail": "", "error": "not open"}
        fn = getattr(live, "configure", None)
        if not callable(fn):
            return {"ok": False, "detail": "", "error": "device has no front-end config"}
        try:
            detail = str(fn(request.get("json") or "{}") or "")
        except Exception as exc:
            return {"ok": False, "detail": "", "error": str(exc)}
        return {"ok": True, "detail": detail, "error": ""}

    def GetState(self, request: dict, context: Any) -> dict:
        device_id = str(request.get("device_id") or "")
        with self._lock:
            live = self._live.get(device_id)
        if live is None:
            return {
                "info": {"id": device_id, "kind": "", "name": "", "channels": []},
                "connected": False,
                "sample_rate": 0,
                "detail": "not open",
                "locked": False,
            }
        pub = live.public_state()
        return {
            "info": info_to_msg(live.info),
            "connected": bool(pub.get("connected")),
            "sample_rate": int(pub.get("sample_rate") or live.sample_rate),
            "detail": str(pub.get("detail") or ""),
            "battery": pub.get("battery"),
            "locked": bool(pub.get("locked")),
        }

    def Subscribe(self, request: dict, context: Any) -> Iterator[dict]:
        device_id = str(request.get("device_id") or "")
        q: deque[dict] = deque()
        with self._lock:
            if device_id:
                self._queues[device_id].append(q)
            else:
                self._queues_all.append(q)
        try:
            while True:
                if context is not None and getattr(context, "is_active", lambda: True)() is False:
                    break
                try:
                    event = q.popleft()
                except IndexError:
                    time.sleep(0.01)
                    continue
                yield event
        finally:
            with self._lock:
                if device_id:
                    lst = self._queues.get(device_id, [])
                    if q in lst:
                        lst.remove(q)
                elif q in self._queues_all:
                    self._queues_all.remove(q)


def _add_servicer_to_server(servicer: DeviceServicer, server: Any) -> None:
    grpc = _require_grpc()
    handlers = {
        "GetKind": grpc.unary_unary_rpc_method_handler(
            servicer.GetKind,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
        "Scan": grpc.unary_unary_rpc_method_handler(
            servicer.Scan,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
        "Open": grpc.unary_unary_rpc_method_handler(
            servicer.Open,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
        "Close": grpc.unary_unary_rpc_method_handler(
            servicer.Close,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
        "GetState": grpc.unary_unary_rpc_method_handler(
            servicer.GetState,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
        "Configure": grpc.unary_unary_rpc_method_handler(
            servicer.Configure,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
        "Subscribe": grpc.unary_stream_rpc_method_handler(
            servicer.Subscribe,
            request_deserializer=loads,
            response_serializer=dumps,
        ),
    }
    generic = grpc.method_handlers_generic_handler(SERVICE_NAME, handlers)
    server.add_generic_rpc_handlers((generic,))


def serve(
    driver: DeviceDriver,
    host: str = "127.0.0.1",
    port: int = 51051,
    *,
    package: str = "",
    version: str = "0.1.0",
    wait: bool = True,
) -> Any:
    """Start a DeviceService gRPC server for one driver. Returns the server."""
    grpc = _require_grpc()
    server = grpc.server(futures_thread_pool(max_workers=8))
    servicer = DeviceServicer(driver, package=package, version=version)
    _add_servicer_to_server(servicer, server)
    bound = server.add_insecure_port(f"{host}:{port}")
    if bound == 0:
        raise RuntimeError(f"could not bind gRPC port {host}:{port}")
    server.start()
    if wait:
        server.wait_for_termination()
    return server


def futures_thread_pool(max_workers: int = 8):
    from concurrent.futures import ThreadPoolExecutor

    return ThreadPoolExecutor(max_workers=max_workers)


def main_for_driver(
    driver_factory,
    *,
    default_port: int,
    package: str,
    version: str = "0.1.0",
) -> None:
    """CLI entry helper used by device packages."""
    import argparse

    parser = argparse.ArgumentParser(description=f"sevenbeing device gRPC ({package})")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()
    driver = driver_factory() if callable(driver_factory) else driver_factory
    print(f"{package} gRPC DeviceService on {args.host}:{args.port} kind={_kind_value(driver.kind)}")
    serve(driver, host=args.host, port=args.port, package=package, version=version, wait=True)
