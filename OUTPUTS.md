# BCI outputs

Input **devices** bring EEG in. **Outputs** push mental / face control out.

| # | Output | Role |
|---|--------|------|
| 01 | `game` | Keymap → game / OS key inject (default on) |
| 02 | `mqtt` | MQTT IoT publish |
| 03 | `serialport` | UART / USB-serial JSON lines |
| 04 | `tcpudp` | Raw TCP or UDP frames |
| 05 | `grpc` | Control stream to gRPC consumers |
| 06 | `custom` | User handlers |

Payload (all sinks share this shape):

```json
{"name":"Push","key":"w","source":"mental","confidence":0.91}
```

Fan-out is **edge-triggered** on `(name, key, source)` so sample-rate EEG does not flood IoT / serial.

## Python

```python
from sevenbeing.brain.bci import CORE

# enable outputs
CORE.outputs.enable("mqtt")
CORE.outputs.configure("mqtt", broker="mqtt://127.0.0.1:1883", topic="7being/bci/control")
CORE.outputs.get("mqtt").set_publisher(lambda topic, body: …)

CORE.outputs.enable("serialport")
CORE.outputs.configure("serialport", port="/dev/tty.usbserial", baudrate=115200)
CORE.outputs.get("serialport").set_writer(lambda line: …)

CORE.outputs.enable("tcpudp")
CORE.outputs.configure("tcpudp", transport="udp", host="127.0.0.1", port=7700)
CORE.outputs.get("tcpudp").set_sender(lambda transport, host, port, body: …)

CORE.outputs.enable("grpc")
CORE.outputs.get("grpc").set_publisher(lambda payload: …)

CORE.outputs.enable("custom")
CORE.outputs.get("custom").on(lambda out, payload: print(payload))

# game key inject (GUI wires CoreGraphics when keys_enabled)
CORE.outputs.get("game").set_injector(lambda key: …)
```

`CORE.channels` and `CORE.outputs` are the same hub.

## No-code (Studio)

Use **7Being Studio** (`../7being-studio`): draw `Mental → mqtt` (etc.), then **Apply**. Studio calls these HTTP routes via `/api/bci/*`.

## HTTP (Python API)

```
GET  /outputs
POST /outputs/enable     {"name":"mqtt"}
POST /outputs/disable    {"name":"mqtt"}
POST /outputs/configure  {"name":"mqtt","topic":"home/bci"}
```

Aliases: `/channels`, `/channels/enable`, …

## Layout

```
sevenbeing/brain/bci/
  channels.py / outputs.py   # hub + registry
  game/ mqtt/ serialport/ tcpudp/ grpc/ custom/
```
