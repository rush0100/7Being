"""BCI outputs — public re-export of control channels.

Input devices feed EEG in; outputs push mental/face control out:

  game | mqtt (IoT) | serialport | tcp/udp | grpc | custom
"""

from __future__ import annotations

from .channels import (
    CHANNELS,
    OUTPUTS,
    Channel,
    ChannelHub,
    ChannelInfo,
    ControlSink,
    Output,
    OutputHub,
    OutputInfo,
    build_default_hub,
    channel_by_name,
    control_payload,
    iter_channels,
)

__all__ = [
    "CHANNELS",
    "OUTPUTS",
    "Channel",
    "ChannelHub",
    "ChannelInfo",
    "ControlSink",
    "Output",
    "OutputHub",
    "OutputInfo",
    "build_default_hub",
    "channel_by_name",
    "control_payload",
    "iter_channels",
    "iter_outputs",
]


def iter_outputs():
    return iter_channels()
