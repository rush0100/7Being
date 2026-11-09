"""BCI control outputs (channels) — registry + hub fan-out."""

from __future__ import annotations

from sevenbeing.brain.bci.channels import (
    CHANNELS,
    OUTPUTS,
    Channel,
    build_default_hub,
    channel_by_name,
    control_payload,
)
from sevenbeing.brain.bci.mental.control import ControlOutput


def test_channel_registry() -> None:
    assert len(CHANNELS) == 6
    assert OUTPUTS is CHANNELS
    assert [c.name for c in CHANNELS] == [
        "game",
        "mqtt",
        "serialport",
        "tcpudp",
        "grpc",
        "custom",
    ]
    assert channel_by_name("games") is not None
    assert channel_by_name("games").name == "game"
    assert channel_by_name("iot").name == "mqtt"
    assert channel_by_name("tcp/udp").name == "tcpudp"
    assert channel_by_name("serial").name == "serialport"
    assert Channel.GAME.value == "game"
    assert all(c.status == "shipping" for c in CHANNELS)


def test_hub_dispatch() -> None:
    hub = build_default_hub()
    assert hub.is_enabled("game")
    assert not hub.is_enabled("mqtt")

    seen: list[str] = []
    hub.sinks["game"].on(lambda ev: seen.append(ev.name))  # type: ignore[attr-defined]
    mqtt_msgs: list[tuple[str, bytes]] = []
    hub.sinks["mqtt"].set_publisher(lambda topic, body: mqtt_msgs.append((topic, body)))  # type: ignore[attr-defined]
    hub.enable("mqtt")

    out = ControlOutput("Push", "w", "mental", 0.9)
    hit = hub.dispatch(out)
    assert "game" in hit and "mqtt" in hit
    assert seen == ["Push"]
    assert mqtt_msgs and mqtt_msgs[0][0] == "7being/bci/control"
    assert control_payload(out)["name"] == "Push"

    # Edge: identical fingerprint is skipped
    assert hub.dispatch(out) == []
    assert seen == ["Push"]

    custom_hit: list[str] = []
    hub.sinks["custom"].on(lambda o, p: custom_hit.append(p["key"]))  # type: ignore[attr-defined]
    hub.enable("custom")
    hub.dispatch(ControlOutput("Pull", "s", "mental", 0.8))
    assert custom_hit == ["s"]
    assert seen == ["Push", "Pull"]

    # force re-emits same fingerprint
    hub.dispatch(ControlOutput("Pull", "s", "mental", 0.8), force=True)
    assert custom_hit == ["s", "s"]

    serial_lines: list[bytes] = []
    hub.configure("serialport", port="/dev/null", baudrate=9600)
    hub.sinks["serialport"].set_writer(serial_lines.append)  # type: ignore[attr-defined]
    hub.enable("serialport")
    hub.dispatch(ControlOutput("Lift", "q", "face", 1.0))
    assert serial_lines and b'"name":"Lift"' in serial_lines[0]

    udp: list[tuple] = []
    hub.configure("tcpudp", transport="udp", host="127.0.0.1", port=7700)
    hub.sinks["tcpudp"].set_sender(lambda *a: udp.append(a))  # type: ignore[attr-defined]
    hub.enable("tcpudp")
    hub.dispatch(ControlOutput("Drop", "e", "mental", 0.7))
    assert udp and udp[0][0] == "udp" and udp[0][2] == 7700

    grpc_payloads: list[dict] = []
    hub.sinks["grpc"].set_publisher(grpc_payloads.append)  # type: ignore[attr-defined]
    hub.enable("grpc")
    hub.dispatch(ControlOutput("Left", "a", "mental", 0.6))
    assert grpc_payloads and grpc_payloads[0]["key"] == "a"

    state = hub.public_state()
    assert "game" in state["enabled"] and "mqtt" in state["enabled"]
    assert "outputs" in state and len(state["outputs"]) == 6
    hub.close()


def test_core_outputs_alias() -> None:
    from sevenbeing.brain.bci import CORE

    assert CORE.outputs is CORE.channels
    assert "outputs" in CORE.public_state()


if __name__ == "__main__":
    test_channel_registry()
    test_hub_dispatch()
    test_core_outputs_alias()
    print("ok")
