# 7Being

English · [中文](#中文)

## English

Core of **7Being Studio** — **RUSH0100** × **BURNLab KMITL** (Thailand Biomedical Engineering Lab).

Founder & PhD Biomedical Engineering Student [Mr. Ratchaphon Khaemphukhiao](https://www.linkedin.com/in/ratchaphon/).

Python package: **`sevenbeing`**.

### Map

| Part | Where |
|------|--------|
| Core (this repo) | Seven pillars · Brain → BCI |
| Studio | [7being-studio](https://github.com/rush0100/7being-studio) |
| ADS1299 | [7being-ads1299](https://github.com/rush0100/7being-ads1299) |
| H1 | Private · not in the public set |
| EPOC X | LSL adapter `7being-emotiv-epocx` · see below |

| # | Pillar | Focus | Status |
|---|--------|--------|--------|
| 01 | **Brain** | EEG and neural activity | **BCI shipping** |
| 02 | **Body** | Heart rate and HRV | scaffold |
| 03 | **Breath** | Respiration and rhythm | scaffold |
| 04 | **Emotion** | Affective state | partial (from EEG affect) |
| 05 | **Attention** | Focus and cognition | scaffold |
| 06 | **Environment** | Context and surroundings | scaffold |
| 07 | **Being** | Personalized wellbeing | scaffold |

### EPOC X

Buy [EmotivPRO](https://www.emotiv.com/emotivpro), then contact hello@rush0100.com for the LSL adapter.

Brain’s first subsystem is **BCI** (`sevenbeing.brain.bci`): multi-device EEG inputs, mental commands, **outputs** (game / MQTT / serial / TCP-UDP / gRPC / custom), local GUI, and gRPC device plugins. See [`OUTPUTS.md`](OUTPUTS.md).

MIT licensed (`LICENSE`). Pillars 02–07 are scaffolds. Brain → BCI is usable. See [`SECURITY.md`](SECURITY.md).

### Layout

```
sevenbeing/
  pillars.py           # 01–07 registry
  brain/
    bci/               # devices, mental, pipeline, store, gui
  body/ breath/ emotion/ attention/ environment/ being/
```

Public device plugin: `7being-ads1299`. `7being-h1` and EPOC X stay private.

### Install

```bash
cd 7Being
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install -e ../7being-ads1299  # ADS1299 USBStyx, public
# private, not part of the public set:
# .venv/bin/pip install -e ../7being-h1
```

### Run Brain → BCI (Studio)

The primary UI is **7Being Studio** (Next.js no-code flow builder). Python serves the API on `:8765`.

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

### Tests

```bash
.venv/bin/python test_devices.py
.venv/bin/python test_mental.py
.venv/bin/python test_channels.py
.venv/bin/python test_grpc_device.py
```

### BCI outputs (control)

```python
from sevenbeing.brain.bci import CORE, OUTPUTS

CORE.outputs.enable("mqtt")
CORE.outputs.configure("mqtt", topic="7being/bci/control")
CORE.outputs.get("custom").on(lambda out, payload: print(payload))
```

## 中文

**7Being Studio** 的核心 — **RUSH0100** × **BURNLab KMITL**（泰国生物医学工程实验室）。

创始人、生物医学工程博士生 [Mr. Ratchaphon Khaemphukhiao](https://www.linkedin.com/in/ratchaphon/)。

Python 包名：**`sevenbeing`**。

### 地图

| 部分 | 位置 |
|------|------|
| 核心（本仓库） | 七个支柱 · Brain → BCI |
| Studio | [7being-studio](https://github.com/rush0100/7being-studio) |
| ADS1299 | [7being-ads1299](https://github.com/rush0100/7being-ads1299) |
| H1 | 私有 · 不在公开套件中 |
| EPOC X | LSL adapter `7being-emotiv-epocx` · 见下文 |

| # | 支柱 | 焦点 | 状态 |
|---|------|------|------|
| 01 | **Brain** | 脑电与神经活动 | **BCI 已可用** |
| 02 | **Body** | 心率与 HRV | 脚手架 |
| 03 | **Breath** | 呼吸与节律 | 脚手架 |
| 04 | **Emotion** | 情绪状态 | 部分（来自 EEG affect） |
| 05 | **Attention** | 专注与认知 | 脚手架 |
| 06 | **Environment** | 情境与环境 | 脚手架 |
| 07 | **Being** | 个性化健康 | 脚手架 |

### EPOC X

请先购买 [EmotivPRO](https://www.emotiv.com/emotivpro)，然后联系 hello@rush0100.com 获取 LSL adapter。

Brain 的第一个子系统是 **BCI**（`sevenbeing.brain.bci`）：多设备 EEG 输入、mental commands、**输出**（game / MQTT / serial / TCP-UDP / gRPC / custom）、本地 GUI，以及 gRPC 设备插件。见 [`OUTPUTS.md`](OUTPUTS.md)。

MIT 许可（`LICENSE`）。支柱 02–07 仍为脚手架。Brain → BCI 已可用。见 [`SECURITY.md`](SECURITY.md)。

### 目录

```
sevenbeing/
  pillars.py           # 01–07 注册表
  brain/
    bci/               # devices, mental, pipeline, store, gui
  body/ breath/ emotion/ attention/ environment/ being/
```

公开设备插件：`7being-ads1299`。`7being-h1` 与 EPOC X 保持私有。

### 安装

```bash
cd 7Being
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install -e ../7being-ads1299  # ADS1299 USBStyx，公开
# 私有，不属于公开套件：
# .venv/bin/pip install -e ../7being-h1
```

### 运行 Brain → BCI（Studio）

主界面是 **7Being Studio**（Next.js 无代码流程构建器）。Python 在 `:8765` 提供 API。

```bash
# 1) 设备插件（公开示例：ADS1299）
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
run_gui()  # API + SSE；界面请打开 Studio
```

另见 [`../7being-studio/README.md`](../7being-studio/README.md) 与 [`OUTPUTS.md`](OUTPUTS.md)。

### 测试

```bash
.venv/bin/python test_devices.py
.venv/bin/python test_mental.py
.venv/bin/python test_channels.py
.venv/bin/python test_grpc_device.py
```

### BCI 输出（控制）

```python
from sevenbeing.brain.bci import CORE, OUTPUTS

CORE.outputs.enable("mqtt")
CORE.outputs.configure("mqtt", topic="7being/bci/control")
CORE.outputs.get("custom").on(lambda out, payload: print(payload))
```
