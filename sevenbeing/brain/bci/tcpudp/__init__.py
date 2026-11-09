"""BCI channel · TCP/UDP — raw sockets."""

from __future__ import annotations

from .sink import TcpUdpSink

CODE = "04"
NAME = "tcpudp"
TITLE = "TCP/UDP"
BLURB = "Raw TCP and UDP control sockets"
STATUS = "shipping"

__all__ = [
    "BLURB",
    "CODE",
    "NAME",
    "STATUS",
    "TITLE",
    "TcpUdpSink",
]
