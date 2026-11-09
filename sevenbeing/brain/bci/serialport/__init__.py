"""BCI channel · Serialport — UART / USB-serial."""

from __future__ import annotations

from .sink import SerialportSink

CODE = "03"
NAME = "serialport"
TITLE = "Serialport"
BLURB = "UART / USB-serial control frames"
STATUS = "shipping"

__all__ = [
    "BLURB",
    "CODE",
    "NAME",
    "STATUS",
    "SerialportSink",
    "TITLE",
]
