"""BCI channel · gRPC — DeviceService device plugins + control sink."""

from __future__ import annotations

from .client import GrpcDeviceDriver
from .codec import SERVICE_NAME, dumps, loads
from .server import info_to_msg, main_for_driver, msg_to_info, serve
from .sink import GrpcControlSink

CODE = "05"
NAME = "grpc"
TITLE = "gRPC"
BLURB = "DeviceService plugins + control stream"
STATUS = "shipping"

__all__ = [
    "BLURB",
    "CODE",
    "GrpcControlSink",
    "GrpcDeviceDriver",
    "NAME",
    "SERVICE_NAME",
    "STATUS",
    "TITLE",
    "dumps",
    "info_to_msg",
    "loads",
    "main_for_driver",
    "msg_to_info",
    "serve",
]
