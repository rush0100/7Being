"""BCI channel · MQTT — IoT publish / subscribe."""

from __future__ import annotations

from .sink import MqttSink

CODE = "02"
NAME = "mqtt"
TITLE = "MQTT"
BLURB = "Publish control over MQTT (IoT)"
STATUS = "shipping"

__all__ = [
    "BLURB",
    "CODE",
    "MqttSink",
    "NAME",
    "STATUS",
    "TITLE",
]
