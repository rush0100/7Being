# 7Being

แกนของ **7Being Studio** — **RUSH0100** × **BURNLab KMITL** (Thailand Biomedical Engineering Lab).

Founder & PhD Biomedical Engineering Student [Mr. Ratchaphon Khaemphukhiao](https://www.linkedin.com/in/ratchaphon/).

Python package: **`sevenbeing`**.

## แผนที่

| ส่วน | ที่อยู่ |
|------|---------|
| แกน (repo นี้) | เจ็ดเสา · Brain → BCI |
| Studio | [7being-studio](https://github.com/rush0100/7being-studio) |
| ADS1299 | [7being-ads1299](https://github.com/rush0100/7being-ads1299) |
| H1 | ส่วนตัว · ไม่อยู่ในชุดสาธารณะ |
| EPOC X | LSL adapter `7being-emotiv-epocx` · ดูสามภาษาด้านล่าง |

| # | Pillar | Focus | Status |
|---|--------|--------|--------|
| 01 | **Brain** | EEG and neural activity | **BCI shipping** |
| 02 | **Body** | Heart rate and HRV | scaffold |
| 03 | **Breath** | Respiration and rhythm | scaffold |
| 04 | **Emotion** | Affective state | partial (from EEG affect) |
| 05 | **Attention** | Focus and cognition | scaffold |
| 06 | **Environment** | Context and surroundings | scaffold |
| 07 | **Being** | Personalized wellbeing | scaffold |

## EPOC X

- **ไทย:** ซื้อ [EmotivPRO](https://www.emotiv.com/emotivpro) จากนั้นติดต่อ hello@rush0100.com เพื่อขอ LSL adapter
- **中文:** 请先购买 [EmotivPRO](https://www.emotiv.com/emotivpro)，然后联系 hello@rush0100.com 获取 LSL adapter
- **English:** Buy [EmotivPRO](https://www.emotiv.com/emotivpro), then contact hello@rush0100.com for the LSL adapter

Brain’s first subsystem is **BCI** (`sevenbeing.brain.bci`): multi-device EEG inputs, mental commands, **outputs** (game / MQTT / serial / TCP-UDP / gRPC / custom), local GUI, gRPC device plugins. See [`OUTPUTS.md`](OUTPUTS.md).

MIT licensed (`LICENSE`). เสา 02–07 ยังเป็น scaffold มี Brain → BCI ที่ใช้งานได้ ดู [`SECURITY.md`](SECURITY.md).

## Layout

```
sevenbeing/
  pillars.py           # 01–07 registry
  brain/
    bci/               # devices, mental, pipeline, store, gui
  body/ breath/ emotion/ attention/ environment/ being/
```

Public device plugin: `7being-ads1299`. `7being-h1` and EPOC X stay private.

## Install

```bash
cd 7Being
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install -e ../7being-ads1299  # ADS1299 USBStyx, public
# private, not part of the public set:
# .venv/bin/pip install -e ../7being-h1
```

## Run Brain → BCI (Studio)

Primary UI is **7Being Studio** (Next.js no-code flow builder). Python serves the API on `:8765`.

```bash
# 1) device plugin (public example: ADS1299)
7being-ads1299-serve --port 51053
export SEVENBEING_DEVICE_GRPC=127.0.0.1:51053

# 2) BCI API
./run.sh

# 3) Studio
cd ../7being-studio && npm install && npm run dev
# → http://127.0.0.1:3000
```

```python
from sevenbeing import PILLARS, CORE, run_gui
from sevenbeing import brain

print([(p.code, p.title, p.blurb) for p in PILLARS])
CORE.devices.attach_grpc("127.0.0.1:51053")
run_gui()  # API + SSE; open Studio for the UI
```

See [`../7being-studio/README.md`](../7being-studio/README.md) and [`OUTPUTS.md`](OUTPUTS.md).

## Tests

```bash
.venv/bin/python test_devices.py
.venv/bin/python test_mental.py
.venv/bin/python test_channels.py
.venv/bin/python test_grpc_device.py
```

## BCI outputs (control)

```python
from sevenbeing.brain.bci import CORE, OUTPUTS

CORE.outputs.enable("mqtt")
CORE.outputs.configure("mqtt", topic="7being/bci/control")
CORE.outputs.get("custom").on(lambda out, payload: print(payload))
```
