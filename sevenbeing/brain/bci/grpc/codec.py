"""JSON codecs for the device.v1 gRPC contract (see protos/.../device.proto).

Payloads follow proto field names so other languages can generate real protobuf
stubs later; the Python path uses gRPC with JSON serializers to avoid a
grpcio-tools build step on every machine.
"""

from __future__ import annotations

import json
from typing import Any


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def loads(raw: bytes) -> Any:
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


SERVICE_NAME = "sevenbeing.device.v1.DeviceService"
