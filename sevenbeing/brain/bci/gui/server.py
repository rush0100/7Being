#!/usr/bin/env python3
"""7Being BCI HTTP API + SSE (UI is 7Being Studio on :3000).

Serves REST/SSE on http://127.0.0.1:8765. Product UI: Next.js Studio
(``7being-studio``). GET / redirects there.
"""

from __future__ import annotations

import ctypes
import json
import mimetypes
import re
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..pipeline.affect import BANDS, NAMES as AFFECT_NAMES
from ..pipeline.affect import AffectMeter
from ..core import CORE
from ..devices.base import DeviceCallbacks, DeviceKind
from ..devices.montage import EPOCX_MONTAGE
from ..mental.control import ControlOutput
from ..pipeline.contact import ContactProxy
from ..pipeline.face import NAMES as FACE_NAMES
from ..pipeline.face import FaceMeter
from ..store.profile import (
    ACTIONS,
    create_profile,
    delete_profile,
    list_profiles,
    save_profile,
    to_public,
)
from ..pipeline.signal import SignalMeter

# Default plot labels until a live device publishes its montage.
CHANNELS = EPOCX_MONTAGE.channels
MOTION_AXES = ("GYROX", "GYROY", "GYROZ", "ACCX", "ACCY", "ACCZ", "MAGX", "MAGY", "MAGZ")
MOTION_STREAM_AXES = (
    "Q0",
    "Q1",
    "Q2",
    "Q3",
    "ACCX",
    "ACCY",
    "ACCZ",
    "MAGX",
    "MAGY",
    "MAGZ",
)
_structure_motion = None
try:
    from sevenbeing_epocx.ble import (
        CHANNELS as _EMOTIV_CH,
        MOTION_AXES as _EMOTIV_MOT,
        MOTION_STREAM_AXES as _EMOTIV_MOT_STREAM,
        structure_motion as _structure_motion_fn,
    )

    CHANNELS = _EMOTIV_CH
    MOTION_AXES = _EMOTIV_MOT
    MOTION_STREAM_AXES = _EMOTIV_MOT_STREAM
    _structure_motion = _structure_motion_fn
except ImportError:
    pass

HOST = "127.0.0.1"
PORT = 8765
STUDIO_URL = "http://127.0.0.1:3000"
WINDOW = 384
# Batch EEG SSE: ~32–64 Hz UI updates is enough for traces (saves json.dumps).
SAMPLE_FLUSH_S = 0.016
SAMPLE_FLUSH_N = 4
SSE_IDLE_S = 0.008
SSE_BUSY_S = 0.0
STATIC_DIR = Path(__file__).resolve().parent / "static"

_booted = False
_calib_watch: threading.Thread | None = None
_calib_watch_stop = threading.Event()


def _calib_watch_loop() -> None:
    """Publish calib progress on wall clock; finish even if BLE stalls at ~99%."""
    while not _calib_watch_stop.wait(0.25):
        if not CORE.calibrator.active:
            # One last publish after completion, then exit.
            with state_lock:
                payload = CORE.public_state()
                state["app"] = payload
            publish("app", payload)
            break
        finished = CORE.tick_calibration()
        with state_lock:
            payload = CORE.public_state()
            state["app"] = payload
        publish("app", payload)
        if finished:
            break


def _start_calib_watch() -> None:
    global _calib_watch
    _calib_watch_stop.set()
    if _calib_watch is not None and _calib_watch.is_alive():
        _calib_watch.join(timeout=0.5)
    _calib_watch_stop.clear()
    _calib_watch = threading.Thread(
        target=_calib_watch_loop, name="calib-watch", daemon=True
    )
    _calib_watch.start()


def ensure_boot() -> None:
    """Load active profile once — call from main/run, not at import time."""
    global _booted
    if _booted:
        return
    CORE.boot()
    game = CORE.channels.sinks.get("game")
    if game is not None and hasattr(game, "set_injector"):
        game.set_injector(post_key)
        game.inject_enabled = True
    _booted = True


state_lock = threading.Lock()
state = {
    "status": "ยังไม่เชื่อมต่อ",
    "banner": "7Being · profile → calibrate → train → live control",
    "banner_warn": False,
    "pkt_s": 0.0,
    "sample_s": 0.0,
    "samples": deque(maxlen=WINDOW),
    "motion": deque(maxlen=WINDOW),
    "motion_last": None,
    "cq": [None] * len(CHANNELS),
    "affect": [None] * len(AFFECT_NAMES),
    "bands": None,
    "channel_bands": None,
    "signal": None,
    "face": [0.0] * len(FACE_NAMES),
    "command": "Neutral",
    "key": "",
    "keys_enabled": False,
    "brain": None,
    "app": CORE.public_state(),
}


def command_of(face: list[float]) -> tuple[str, str]:
    """Face-only fallback used by tests; live path uses ControlRouter."""
    for name, value in zip(FACE_NAMES, face):
        if value is not None and value > 0:
            key = CORE.control.keymap.get(name, "")
            return name, key
    return "Neutral", ""


def _allowed_inject_keys() -> set[str]:
    keys = {str(v) for v in (CORE.control.keymap or {}).values() if v}
    # Face / mental defaults only — never free-form injection.
    keys.update({"w", "a", "s", "d", "q", "e", "b"})
    return {k for k in keys if len(k) == 1}


def post_key(char: str) -> None:
    if len(char) != 1 or char not in _allowed_inject_keys():
        return
    with state_lock:
        if not state.get("keys_enabled"):
            return
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    cg.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    cg.CGEventKeyboardSetUnicodeString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_uint16),
    ]
    cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    units = (ctypes.c_uint16 * 1)(ord(char))
    for down in (True, False):
        event = cg.CGEventCreateKeyboardEvent(None, 0, down)
        if not event:
            return
        cg.CGEventKeyboardSetUnicodeString(event, 1, units)
        cg.CGEventPost(0, event)
        cf.CFRelease(event)
clients: list[deque] = []
clients_lock = threading.Lock()
stop_event = threading.Event()
worker: threading.Thread | None = None


def publish(kind: str, payload: dict) -> None:
    message = f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    with clients_lock:
        for inbox in clients:
            # Prefer latest samples over a growing backlog (keeps Live realtime).
            if kind == "sample" and len(inbox) > 24:
                keep = [item for item in inbox if not item.startswith("event: sample\n")]
                inbox.clear()
                inbox.extend(keep[-16:])
            # Never drop the newest app/state — calib finish was getting pruned at 99%.
            elif kind == "app" and len(inbox) > 40:
                keep = [item for item in inbox if not item.startswith("event: app\n")]
                inbox.clear()
                inbox.extend(keep[-48:])
            elif len(inbox) > 120:
                while len(inbox) > 60:
                    inbox.popleft()
            inbox.append(message)


class BleWorker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._rate_t = time.monotonic()
        self._rate_packets = 0
        self._rate_rows = 0
        self._rate_motion = 0
        self._motion_rows = 0
        self._announced = False
        self._sample_rows = 0
        self._sample_rate = 128
        self._n_ch = 14
        self._kind = ""
        self._full_scale_uv = 208_000.0
        self._contact: ContactProxy | None = None
        self._cq_pub_t = 0.0
        self._affect = AffectMeter(self._sample_rate, n_ch=self._n_ch)
        self._band_seen = 0
        self._signal = SignalMeter(self._sample_rate)
        self._signal_shown: float | None = None
        self._face = FaceMeter(self._sample_rate, self._n_ch)
        self._face_shown: list[float | None] | None = None
        self._command_shown = "Neutral"
        self._live = None
        self._device_id: str | None = None
        self._sample_batch: list[list[float]] = []
        self._sample_flush_t = time.monotonic()
        self._affect_shown: list[float] | None = None
        self._app_pub_t = 0.0

    def _apply_rate(self, rate: int, n_ch: int | None = None) -> None:
        rate = int(rate) if rate and rate > 0 else 128
        n = self._n_ch if n_ch is None else max(1, int(n_ch))
        if rate == self._sample_rate and n == self._n_ch:
            return
        self._flush_samples(force=True)
        rate_changed = rate != self._sample_rate
        self._sample_rate = rate
        self._n_ch = n
        if rate_changed:
            CORE.set_rate(rate)
        self._affect = AffectMeter(rate, n_ch=n)
        self._band_seen = 0
        self._signal = SignalMeter(rate)
        self._signal_shown = None
        self._face = FaceMeter(rate, n)
        self._face_shown = None
        self._affect_shown = None
        self._command_shown = "Neutral"
        self._arm_contact()
        blank_affect = [None] * len(AFFECT_NAMES)
        with state_lock:
            state["bands"] = None
            state["channel_bands"] = None
            state["affect"] = blank_affect
        publish("bands", {"values": None, "channels": None})
        publish("affect", {"values": blank_affect})
        with state_lock:
            resized = len(state["cq"]) != n
            if resized:
                state["cq"] = [None] * n
                cq = list(state["cq"])
            else:
                cq = None
        if cq is not None:
            publish("cq", {"values": cq})

    def _arm_contact(self) -> None:
        """Derive CQ only for headsets that do not send a contact byte."""
        if self._kind in ("", "epocx"):
            self._contact = None
            return
        self._contact = ContactProxy(self._n_ch, self._sample_rate, self._full_scale_uv)
        self._cq_pub_t = 0.0

    @staticmethod
    def _scale_uv(pub: dict) -> float:
        detail = str(pub.get("detail") or "")
        match = re.search(r"±\s*(\d+(?:\.\d+)?)\s*(mV|V)\b", detail)
        if match:
            value = float(match.group(1))
            return value * (1000.0 if match.group(2) == "mV" else 1_000_000.0)
        if str(pub.get("kind") or "") == "h1":
            return 208_000.0
        return 208_000.0

    def _publish_signal(self, value: float) -> None:
        shown = round(max(0.0, min(1.0, float(value))), 2)
        if shown == self._signal_shown:
            return
        self._signal_shown = shown
        with state_lock:
            state["signal"] = shown
        publish("signal", {"value": shown})

    def _clear_motion(self) -> None:
        with state_lock:
            state["motion"].clear()
            state["motion_last"] = None
            state["motion_s"] = 0.0
        publish("motion", {"available": False})

    def _link_ready(self, state: dict) -> bool:
        """EPOC X is ready once the session key locks. Other devices have no lock."""
        if state.get("locked"):
            return True
        kind = str(state.get("kind") or "")
        return bool(state.get("connected")) and kind not in ("", "epocx")

    def _sync_rate(self) -> None:
        live = self._live
        if live is None or not live.connected:
            return
        state = live.public_state()
        if not self._link_ready(state):
            return
        self._apply_rate(int(state.get("sample_rate") or self._sample_rate))

    def stop(self, *, disconnect: bool = False) -> None:
        self._stop.set()
        # Keep BLE session by default so "หยุด/เริ่มสตรีม" can resume quickly.
        if disconnect and self._device_id:
            try:
                CORE.devices.disconnect(self._device_id)
            except Exception:
                pass

    def run(self) -> None:
        try:
            self._run_devices()
        except Exception as exc:
            text = str(exc)
            if "NO_BLUETOOTH" in text or "unsupported" in text.lower():
                text = "ยังไม่เห็นตัวรับ Bluetooth บนเครื่องนี้"
            self._status(f"BLE: {text}")

    def _batt_text(self) -> str:
        value = getattr(self, "_battery", None)
        return f" · แบต {value}%" if value is not None else ""

    def _status(self, text: str, warn: bool = False) -> None:
        with state_lock:
            state["status"] = text
            state["banner_warn"] = warn
            state["banner"] = text
        publish("status", {"text": text, "warn": warn, "banner": text})

    def _brain(self, brain: dict) -> None:
        with state_lock:
            state["brain"] = brain
        publish("brain", brain)

    def _flush_samples(self, force: bool = False) -> None:
        batch = self._sample_batch
        if not batch:
            return
        now = time.monotonic()
        if (
            not force
            and len(batch) < SAMPLE_FLUSH_N
            and now - self._sample_flush_t < SAMPLE_FLUSH_S
        ):
            return
        rows = batch
        self._sample_batch = []
        self._sample_flush_t = now
        publish("sample", {"rows": rows} if len(rows) > 1 else {"values": rows[0]})

    def _publish_app(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._app_pub_t < 0.2:
            return
        self._app_pub_t = now
        payload = CORE.public_state()
        with state_lock:
            state["app"] = payload
        publish("app", payload)

    def _sample(self, values: list[float]) -> None:
        self._sample_rows += 1
        self._sync_rate()
        row = [round(float(v), 3) for v in values]
        with state_lock:
            state["samples"].append(row)
        self._sample_batch.append(row)
        self._flush_samples()
        if len(row) >= 14 or not self._face.lateral:
            face_vals = self._face.push(row)
            face = [
                None if v is None else (1.0 if v > 0 else 0.0) for v in face_vals
            ]
            if face != self._face_shown:
                self._face_shown = face
                with state_lock:
                    state["face"] = face
                publish("face", {"values": face})
        else:
            face = self._face_shown or [0.0] * len(FACE_NAMES)
        if self._contact is not None and len(row) >= 1:
            cq_now = time.monotonic()
            if cq_now - self._cq_pub_t >= 0.25:
                self._cq_pub_t = cq_now
                shown_cq = [round(v, 2) for v in self._contact.push(row)]
                with state_lock:
                    state["cq"] = shown_cq
                publish("cq", {"values": shown_cq})
            else:
                self._contact.push(row)
        closed = tuple(int(i) for i in (CORE.montage.closed or ()))
        if closed != self._affect.closed:
            self._affect.closed = closed
        scores = self._affect.push(row)
        # One rfft hop from AffectMeter's BandPowerEngine — mental/calib reuse it.
        band_power = self._affect.last_power if self._affect.band_gen != self._band_seen else None
        if scores is not None:
            shown = [round(v, 3) for v in scores]
            if shown != self._affect_shown:
                self._affect_shown = shown
                with state_lock:
                    state["affect"] = shown
                publish("affect", {"values": shown})
        if self._affect.bands is not None and self._affect.band_gen != self._band_seen:
            self._band_seen = self._affect.band_gen
            bands = self._affect.bands
            channels = self._affect.channel_bands
            with state_lock:
                state["bands"] = bands
                state["channel_bands"] = channels
            publish("bands", {"values": bands, "channels": channels})
        was_calib = CORE.calibrator.active
        prev_train_phase = CORE.mental.train.phase
        out = CORE.on_sample(
            row, face, self._affect_shown, band_power=band_power, shared_bands=True
        )
        self._apply_control(out)
        calib_just_finished = was_calib and not CORE.calibrator.active
        train_just_finished = (
            prev_train_phase in ("cue", "rest")
            and CORE.mental.train.phase == "idle"
            and CORE.mental.last_completed is not None
        )
        if (
            calib_just_finished
            or train_just_finished
            or CORE.calibrator.active
            or CORE.mental.train.phase not in ("idle",)
            or CORE.mental.live_enabled
        ):
            # Force publish on calib/train completion so Studio doesn't stick.
            self._publish_app(force=calib_just_finished or train_just_finished)

    def _apply_control(self, out: ControlOutput) -> None:
        if out.name == self._command_shown and out.key == getattr(self, "_key_shown", ""):
            return
        self._command_shown = out.name
        self._key_shown = out.key
        with state_lock:
            state["command"] = out.name
            state["key"] = out.key
        publish(
            "command",
            {
                "name": out.name,
                "key": out.key,
                "source": out.source,
                "confidence": round(out.confidence, 3),
            },
        )
        # Key inject runs via GameSink (ChannelHub) when keys_enabled.

    def _command(self, face: list[float]) -> None:
        out = CORE.control.resolve(None, face)
        CORE.last_control = out
        CORE.channels.dispatch(out)
        self._apply_control(out)

    def _counter(self, counter: int) -> None:
        # H1 reports the sample index once per frame, so the gap meter
        # reads a healthy stream as packet loss. Those devices use rate fit.
        if self._kind and self._kind != "epocx":
            return
        self._sync_rate()
        self._publish_signal(self._signal.push(counter))

    def _motion(self, values: list[float]) -> None:
        # Emotiv-style: quat + accel + mag (gyro kept for fusion/debug).
        if _structure_motion is not None and len(values) >= 9:
            payload = _structure_motion([float(v) for v in values])
        else:
            row = [round(float(v), 4) for v in values]
            payload = {
                "values": row,
                "quat": row[:4] if len(row) >= 4 else [1.0, 0.0, 0.0, 0.0],
                "accel": row[4:7] if len(row) >= 7 else [0.0, 0.0, 0.0],
                "mag": row[7:10] if len(row) >= 10 else [0.0, 0.0, 0.0],
                "gyro": row[:3] if len(row) >= 3 else [0.0, 0.0, 0.0],
                "axes": list(MOTION_STREAM_AXES),
            }
        self._motion_rows += 1
        with state_lock:
            state["motion"].append(payload.get("values") or [])
            state["motion_last"] = payload
        # When AHRS is frozen, skip flooding SSE (UI already holds last pose).
        if payload.get("still") and getattr(self, "_motion_still_pub", False):
            return
        self._motion_still_pub = bool(payload.get("still"))
        publish("motion", payload)

    def _cq(self, index: int, value: float) -> None:
        # A real contact byte owns the panel; stop the amplitude proxy.
        self._contact = None
        with state_lock:
            cq = state["cq"]
            if not 0 <= index < len(cq):
                return
            shown = round(float(value), 2)
            cq[index] = shown
            current = list(cq)
        publish("cq", {"values": current})

    def _gui_callbacks(self) -> DeviceCallbacks:
        return DeviceCallbacks(
            on_sample=lambda _did, values: self._sample(values),
            on_motion=lambda _did, values: self._motion(values),
            on_brain=lambda _did, brain: self._brain(brain),
            on_cq=lambda _did, index, value: self._cq(index, value),
            on_counter=lambda _did, counter: self._counter(counter),
            on_status=lambda _did, text, warn: self._status(text, warn),
        )

    def _run_devices(self) -> None:
        """Attach to DeviceManager primary (any kind) or auto-connect first Emotiv."""
        callbacks = self._gui_callbacks()
        live = CORE.devices.primary()
        if live is not None:
            self._status(f"กำลังต่อ {live.info.name}…")
            try:
                live = CORE.devices.connect(live.info, callbacks, make_primary=True)
            except Exception as exc:
                self._status(f"ต่อ primary ไม่ติด: {exc}", warn=True)
                live = None
        if live is None:
            self._status("กำลังสแกน…")
            chosen = None
            while not self._stop.is_set() and chosen is None:
                if not CORE.devices.kinds():
                    self._status(
                        "ยังไม่มี device plugin — pip install 7being-emotiv-epocx "
                        "(หรือ 7being-h1 / ads1299)",
                        warn=True,
                    )
                    self._stop.wait(2.0)
                    continue
                found = CORE.devices.scan(timeout=5.0)
                for info in found:
                    if info.kind == DeviceKind.EPOCX:
                        chosen = info
                        break
                if chosen is None and found:
                    chosen = found[0]
                if chosen is None and not self._stop.is_set():
                    self._status("ยังไม่เห็นอุปกรณ์ เปิดเครื่องไว้ กำลังสแกนต่อ…")
                    self._stop.wait(1.0)
            if chosen is None or self._stop.is_set():
                return
            live = CORE.devices.connect(chosen, callbacks, make_primary=True)

        self._live = live
        self._device_id = live.info.id
        self._headset_name = live.info.name

        # BLE handshake is async — wait for link before entering the live loop.
        deadline = time.monotonic() + 45.0
        while not self._stop.is_set() and not live.connected and time.monotonic() < deadline:
            detail = ""
            try:
                detail = str((live.public_state() or {}).get("detail") or "")
            except Exception:
                detail = ""
            msg = f"กำลังจับคู่ {self._headset_name}…"
            if detail:
                msg = f"{msg} {detail}"
            self._status(msg)
            self._stop.wait(0.3)
        if self._stop.is_set():
            return
        if not live.connected:
            self._status(
                f"เชื่อมต่อ {self._headset_name} ไม่สำเร็จ — กดเริ่มสตรีมใหม่",
                warn=True,
            )
            return

        while not self._stop.is_set() and live.connected:
            # Follow primary if user switched devices mid-session.
            primary = CORE.devices.primary()
            if primary is not None and primary.info.id != live.info.id:
                live = CORE.devices.connect(primary.info, callbacks, make_primary=True)
                self._live = live
                self._device_id = live.info.id
                self._headset_name = live.info.name
                self._announced = False
            time.sleep(0.1)
            self._publish_live_stats(live)
        if not self._stop.is_set():
            self._status(f"หลุดจาก {self._headset_name} — กดเริ่มสตรีมเพื่อต่อใหม่", warn=True)

    def _publish_live_stats(self, live) -> None:
        pub = live.public_state()
        name = pub.get("name") or getattr(self, "_headset_name", None) or "device"
        now = time.monotonic()
        dt = now - self._rate_t
        session = getattr(live, "_session", None)
        if dt >= 0.8 and session is not None:
            pkt_s = (session.packets - self._rate_packets) / dt
            sample_s = (session.rows - self._rate_rows) / dt
            motion_s = (self._motion_rows - self._rate_motion) / dt
            self._rate_t = now
            self._rate_packets = session.packets
            self._rate_rows = session.rows
            self._rate_motion = self._motion_rows
            with state_lock:
                state["pkt_s"] = pkt_s
                state["sample_s"] = sample_s
                state["motion_s"] = motion_s
        elif dt >= 0.8:
            sample_s = (self._sample_rows - self._rate_rows) / dt
            self._rate_t = now
            self._rate_rows = self._sample_rows
            self._rate_motion = self._motion_rows
            with state_lock:
                state["pkt_s"] = sample_s
                state["sample_s"] = sample_s
                state["motion_s"] = 0.0
            kind = str(pub.get("kind") or "")
            if kind and kind != "epocx":
                target = float(pub.get("sample_rate") or self._sample_rate or 0)
                self._publish_signal(sample_s / target if target else 0.0)
        reported = pub.get("battery")
        if reported is not None and reported != getattr(self, "_battery", None):
            self._battery = reported
            detail = f" · {pub.get('detail')}" if pub.get("detail") else ""
            self._status(f"ต่อแล้ว {name}{self._batt_text()}{detail}")
        if self._link_ready(pub) and not self._announced:
            self._announced = True
            self._kind = str(pub.get("kind") or "")
            self._full_scale_uv = self._scale_uv(pub)
            n_live = int(pub.get("n_channels") or len(pub.get("channels") or ()) or 14)
            try:
                CORE.sync_primary_montage()
            except Exception:
                pass
            self._apply_rate(int(pub.get("sample_rate") or 128), n_live)
            self._publish_app(force=True)
            if self._kind != "epocx":
                self._clear_motion()
                if not self._face.lateral:
                    blank = [0.0, None, None, None, None]
                    self._face_shown = blank
                    with state_lock:
                        state["face"] = blank
                    publish("face", {"values": blank})
            detail = pub.get("detail") or ""
            n_ch = pub.get("n_channels") or len(pub.get("channels") or ()) or "?"
            self._status(
                f"ต่อแล้ว {name} · {n_ch} ch{self._batt_text()}"
                + (f" · {detail}" if detail else "")
            )
        self._flush_samples(force=True)
        with state_lock:
            pkt_s = state.get("pkt_s", 0.0)
            sample_s = state.get("sample_s", 0.0)
            motion_s = state.get("motion_s", 0.0)
        publish(
            "stats",
            {
                "pkt_s": round(pkt_s, 1),
                "sample_s": round(sample_s, 1),
                "motion_s": round(motion_s, 1),
                "battery": getattr(self, "_battery", None),
            },
        )



def start_worker() -> None:
    global worker
    if worker is not None and worker.is_alive() and not worker._stop.is_set():
        # Already streaming — re-bind callbacks onto primary if needed.
        primary = CORE.devices.primary()
        if primary is not None:
            try:
                CORE.devices.connect(primary.info, worker._gui_callbacks(), make_primary=True)
            except Exception:
                pass
        return
    if worker is not None:
        try:
            worker.stop(disconnect=False)
            worker.join(timeout=2.0)
        except Exception:
            pass
    worker = BleWorker()
    worker.start()


def stop_worker() -> None:
    global worker
    if worker is not None:
        flush = getattr(worker, "_flush_samples", None)
        if callable(flush):
            flush(force=True)
        worker.stop(disconnect=False)
    with state_lock:
        state["status"] = "หยุดแล้ว"
        state["banner"] = "หยุดแล้ว"
        state["banner_warn"] = False
    publish("status", {"text": "หยุดแล้ว", "warn": False, "banner": "หยุดแล้ว"})


PAGE = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={STUDIO_URL}">
<title>7Being API</title>
<style>
  body{{font:15px/1.45 system-ui,sans-serif;background:#0c0e0b;color:#e8ebe4;
       display:grid;place-items:center;min-height:100vh;margin:0}}
  a{{color:#c4a35a}}
  main{{max-width:32rem;padding:2rem;border:1px solid #2a2e28;border-radius:12px;
       background:#141714}}
  .meta{{color:#8b9286;font-size:0.85rem;line-height:1.45}}
</style>
</head>
<body>
<main>
  <h1>7Being BCI API</h1>
  <p class="meta"><strong>7Being</strong> Powered by <strong>RUSH0100</strong> × <strong>BURNLab KMITL</strong>
  (Thailand Biomedical Engineering Lab).<br>
  Founder &amp; PhD Biomedical Engineering Student
  <a href="https://www.linkedin.com/in/ratchaphon/">Mr. Ratchaphon Khaemphukhiao</a>.</p>
  <p>The product UI is <strong>7Being Studio</strong> (Next.js).</p>
  <p><a href="{STUDIO_URL}">Open Studio → {STUDIO_URL}</a></p>
  <p>REST + SSE remain on this port (<code>/app</code>, <code>/events</code>, …).</p>
</main>
</body>
</html>
"""

_PAGE_BYTES = PAGE.encode()



class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _cors(self) -> None:
        origin = self.headers.get("Origin") or ""
        if origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type",
            )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            # Primary UI is Next.js Studio; keep a tiny HTML fallback + 302.
            self.send_response(302)
            self.send_header("Location", STUDIO_URL)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(_PAGE_BYTES)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(_PAGE_BYTES)
            return
        if path.startswith("/static/"):
            name = path[len("/static/") :]
            if not name or "/" in name or name.startswith(".") or ".." in name:
                self.send_error(404)
                return
            file_path = STATIC_DIR / name
            if not file_path.is_file():
                self.send_error(404)
                return
            body = file_path.read_bytes()
            mime, _enc = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/app":
            self._json(200, CORE.public_state())
            return
        if path == "/profiles":
            self._json(200, {"profiles": [to_public(p) for p in list_profiles()]})
            return
        if path == "/devices":
            from ..devices.scan_hints import build_scan_hint

            scan_errors: list[str] = []
            scanned_infos = CORE.devices.scan(timeout=8.0, errors_out=scan_errors)
            scanned = [d.to_public() for d in scanned_infos]
            payload = CORE.devices.public_state()
            payload["scanned"] = scanned
            payload["hint"] = build_scan_hint(
                scanned=len(scanned),
                kinds=CORE.devices.kinds(),
                errors=scan_errors,
            )
            self._json(200, payload)
            return
        if path == "/plugins":
            from ..devices.catalog import list_plugins

            self._json(
                200,
                {
                    "plugins": list_plugins(CORE.devices.kinds()),
                    "loaded": CORE.devices.kinds(),
                },
            )
            return
        if path in ("/channels", "/outputs"):
            self._json(200, CORE.channels.public_state())
            return
        if path == "/montage":
            self._json(200, CORE.montage.to_public())
            return
        if path == "/events":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            inbox: deque[str] = deque()
            with state_lock:
                inbox.append(
                    "event: status\ndata: "
                    + json.dumps(
                        {"text": state["status"], "warn": state["banner_warn"], "banner": state["banner"]},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                app_state = CORE.public_state()
                state["app"] = app_state
                inbox.append(
                    "event: history\ndata: "
                    + json.dumps(
                        {
                            "samples": list(state["samples"]),
                            "motion": list(state["motion"]),
                            "motion_last": state.get("motion_last"),
                            "cq": list(state["cq"]),
                            "affect": list(state["affect"]),
                            "bands": state["bands"],
                            "channel_bands": state["channel_bands"],
                            "signal": state["signal"],
                            "face": list(state["face"]),
                            "command": state["command"],
                            "key": state["key"],
                            "keys_enabled": state["keys_enabled"],
                            "brain": state["brain"],
                            "battery": getattr(worker, "_battery", None) if worker else None,
                            "app": app_state,
                        }
                    )
                    + "\n\n"
                )
                inbox.append(
                    "event: app\ndata: " + json.dumps(app_state, ensure_ascii=False) + "\n\n"
                )
            with clients_lock:
                clients.append(inbox)
            try:
                while not stop_event.is_set():
                    wrote = False
                    while inbox:
                        self.wfile.write(inbox.popleft().encode())
                        wrote = True
                    if wrote:
                        self.wfile.flush()
                        if SSE_BUSY_S > 0:
                            time.sleep(SSE_BUSY_S)
                    else:
                        time.sleep(SSE_IDLE_S)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with clients_lock:
                    if inbox in clients:
                        clients.remove(inbox)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/connect":
            start_worker()
            self._empty(204)
            return
        if path == "/stop":
            stop_worker()
            self._empty(204)
            return
        if path == "/plugins/install":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                self._json(403, {"error": "loopback only"})
                return
            body = self._read_json()
            try:
                from ..devices.catalog import install_plugin, list_plugins

                result = install_plugin(str(body.get("id") or ""))
                CORE.devices.reload_plugins()
                result["plugins"] = list_plugins(CORE.devices.kinds())
                result["loaded"] = CORE.devices.kinds()
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, result)
            return
        if path == "/plugins/attach":
            body = self._read_json()
            try:
                from ..devices.catalog import list_plugins, plugin_by_id

                plugin_id = str(body.get("id") or "")
                spec = plugin_by_id(plugin_id)
                endpoint = str(body.get("endpoint") or "").strip()
                if not endpoint and spec is not None:
                    endpoint = f"127.0.0.1:{spec.default_port}"
                if not endpoint:
                    raise ValueError("endpoint required")
                CORE.devices.attach_grpc(endpoint)
                CORE.devices.reload_plugins()
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(
                200,
                {
                    "ok": True,
                    "endpoint": endpoint,
                    "plugins": list_plugins(CORE.devices.kinds()),
                    "loaded": CORE.devices.kinds(),
                    "devices": CORE.devices.public_state(),
                },
            )
            return
        if path == "/plugins/reload":
            loaded = CORE.devices.reload_plugins()
            from ..devices.catalog import list_plugins

            publish("app", CORE.public_state())
            self._json(
                200,
                {
                    "ok": True,
                    "loaded": loaded or CORE.devices.kinds(),
                    "plugins": list_plugins(CORE.devices.kinds()),
                },
            )
            return
        if path == "/devices/connect":
            body = self._read_json()
            device_id = str(body.get("id") or body.get("address") or "")
            frontend = body.get("frontend")
            if frontend is not None and not isinstance(frontend, dict):
                self._json(400, {"error": "frontend must be an object"})
                return
            try:
                scanned = CORE.devices.scan(timeout=8.0)
                live = CORE.devices.connect_id(
                    device_id,
                    scanned=scanned,
                    frontend=frontend if isinstance(frontend, dict) else None,
                )
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            start_worker()  # keep GUI meters attached to primary stream
            self._json(200, {"ok": True, "device": live.public_state(), "devices": CORE.devices.public_state()})
            return
        if path == "/devices/configure":
            body = self._read_json()
            device_id = str(body.get("id") or "")
            frontend = body.get("frontend")
            if not isinstance(frontend, dict):
                self._json(400, {"error": "frontend must be an object"})
                return
            try:
                detail = CORE.devices.configure(device_id, frontend)
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ok": True, "detail": detail, "devices": CORE.devices.public_state()})
            return
        if path == "/devices/primary":
            body = self._read_json()
            try:
                CORE.devices.set_primary(str(body.get("id") or ""))
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, CORE.devices.public_state())
            return
        if path == "/devices/disconnect":
            body = self._read_json()
            device_id = body.get("id")
            CORE.devices.disconnect(None if not device_id else str(device_id))
            if not CORE.devices.connected():
                stop_worker()
            self._json(200, CORE.devices.public_state())
            return
        if path == "/keys":
            # Loopback-only toggle; actual key injection also checks keys_enabled + whitelist.
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                self._json(403, {"error": "loopback only"})
                return
            body = self._read_json()
            enabled = bool(body.get("enabled"))
            with state_lock:
                state["keys_enabled"] = enabled
                payload = {
                    "name": state["command"],
                    "key": state["key"],
                    "keys_enabled": enabled,
                }
            publish("command", payload)
            self._empty(204)
            return
        if path in ("/channels/enable", "/outputs/enable"):
            body = self._read_json()
            try:
                CORE.channels.enable(str(body.get("name") or ""))
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, CORE.channels.public_state())
            return
        if path in ("/channels/disable", "/outputs/disable"):
            body = self._read_json()
            CORE.channels.disable(str(body.get("name") or ""))
            publish("app", CORE.public_state())
            self._json(200, CORE.channels.public_state())
            return
        if path in ("/channels/configure", "/outputs/configure"):
            body = self._read_json()
            name = str(body.get("name") or "")
            opts = {k: v for k, v in body.items() if k != "name"}
            try:
                CORE.channels.configure(name, **opts)
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, CORE.channels.public_state())
            return
        if path == "/profile/select":
            body = self._read_json()
            try:
                from ..store.profile import safe_profile_id

                CORE.load_profile(safe_profile_id(str(body.get("id") or "")))
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, CORE.public_state())
            return
        if path == "/profile/create":
            body = self._read_json()
            name = str(body.get("name") or "User")
            actions = body.get("actions") or ["Neutral", "Push", "Pull", "Left", "Right"]
            from ..store.profile import MAX_ACTIONS

            actions = [a for a in actions if a in ACTIONS][:MAX_ACTIONS]
            profile = create_profile(name, actions)
            CORE.load_profile(profile.id)
            publish("app", CORE.public_state())
            self._json(200, CORE.public_state())
            return
        if path == "/profile/delete":
            body = self._read_json()
            try:
                from ..store.profile import safe_profile_id

                pid = safe_profile_id(str(body.get("id") or ""))
                profiles = list_profiles()
                if len(profiles) <= 1:
                    raise ValueError("ต้องเหลืออย่างน้อย 1 โปรไฟล์")
                if CORE.profile is not None and CORE.profile.id == pid:
                    # Switch away before deleting the active profile.
                    other = next((p for p in profiles if p.id != pid), None)
                    if other is None:
                        raise ValueError("ไม่มีโปรไฟล์อื่นให้สลับ")
                    CORE.load_profile(other.id)
                if not delete_profile(pid):
                    raise ValueError("ไม่พบโปรไฟล์")
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, CORE.public_state())
            return
        if path == "/calibrate/start":
            with CORE.lock:
                CORE.calibrator.set_n_ch(CORE.montage.n_channels)
                CORE.calibrator.set_rate(CORE.sample_rate)
                CORE.calibrator.start()
            _start_calib_watch()
            publish("app", CORE.public_state())
            self._empty(204)
            return
        if path == "/calibrate/stop":
            _calib_watch_stop.set()
            with CORE.lock:
                result = CORE.calibrator.stop()
                CORE._commit_calibration(result)
            publish("app", CORE.public_state())
            self._empty(204)
            return
        if path == "/train/start":
            body = self._read_json()
            action = str(body.get("action") or "Push")
            try:
                with CORE.lock:
                    CORE.mental.set_rate(CORE.sample_rate)
                    CORE.train_state = CORE.mental.start_action_block(action)
                    # Keep profile action list in sync when training a new command.
                    if CORE.profile is not None:
                        wanted = list(CORE.mental.actions)
                        if wanted != CORE.profile.actions:
                            CORE.profile.actions = wanted
                            save_profile(CORE.profile)
                    if CORE.recorder.active:
                        CORE.recorder.mark("train_start", {"action": action})
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._empty(204)
            return
        if path == "/train/stop":
            with CORE.lock:
                CORE.train_state = CORE.mental.stop_training()
                if CORE.recorder.active:
                    CORE.recorder.mark("train_stop", {})
            publish("app", CORE.public_state())
            self._empty(204)
            return
        if path == "/train/fit":
            try:
                with CORE.lock:
                    result = CORE.mental.fit()
                    if CORE.profile is not None:
                        CORE.mental.save(CORE.profile.model_path())
                        CORE.profile.has_model = True
                        CORE.profile.last_cv_accuracy = result["cv_accuracy"]
                        save_profile(CORE.profile)
                        CORE.mental.live_enabled = True
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, result)
            return
        if path == "/mental/live":
            body = self._read_json()
            enabled = bool(body.get("enabled"))
            with CORE.lock:
                if enabled and CORE.mental.model is None:
                    self._json(400, {"error": "ยังไม่มีโมเดล — Fit LDA ก่อน"})
                    return
                CORE.mental.live_enabled = enabled
            publish("app", CORE.public_state())
            self._empty(204)
            return
        if path == "/session/start":
            with CORE.lock:
                if CORE.profile is None:
                    self._json(400, {"error": "ไม่มีโปรไฟล์"})
                    return
                path = CORE.recorder.start(CORE.profile.id)
            publish("app", CORE.public_state())
            self._json(200, {"path": str(path)})
            return
        if path == "/session/stop":
            with CORE.lock:
                path = CORE.recorder.stop()
            publish("app", CORE.public_state())
            self._json(200, {"path": None if path is None else str(path)})
            return
        if path == "/control":
            body = self._read_json()
            with CORE.lock:
                if CORE.profile is not None:
                    if "keymap" in body and isinstance(body["keymap"], dict):
                        CORE.profile.keymap.update(
                            {str(k): str(v) for k, v in body["keymap"].items()}
                        )
                    if "mental_threshold" in body:
                        CORE.profile.mental_threshold = float(body["mental_threshold"])
                    if "debounce_ms" in body:
                        CORE.profile.debounce_ms = int(body["debounce_ms"])
                    save_profile(CORE.profile)
                    CORE.control.configure(
                        keymap=CORE.profile.keymap,
                        mental_threshold=CORE.profile.mental_threshold,
                        debounce_ms=CORE.profile.debounce_ms,
                    )
            publish("app", CORE.public_state())
            self._json(200, CORE.public_state())
            return
        if path == "/montage":
            body = self._read_json()
            action = str(body.get("action") or "set").strip().lower()
            try:
                if action == "reset":
                    CORE.reset_electrode_map()
                elif action == "random":
                    raise ValueError("random electrode map is disabled")
                else:
                    assignments = body.get("assignments") or body.get("channels")
                    if assignments is not None and not isinstance(assignments, list):
                        raise ValueError("assignments must be a list")
                    ref = body.get("reference")
                    closed = body["closed"] if "closed" in body else None
                    CORE.apply_electrode_map(
                        None if assignments is None else list(assignments),
                        reference=None if ref is None else str(ref),
                        closed=closed,
                        reset_model=False,
                    )
            except (TypeError, ValueError) as exc:
                self._json(400, {"error": str(exc)})
                return
            publish("app", CORE.public_state())
            self._json(200, CORE.montage.to_public())
            return
        self.send_error(404)

    def _empty(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    ensure_boot()
    server = None
    port = PORT
    for candidate in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer((HOST, candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"no free port in {PORT}-{PORT + 19}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"BCI API  http://{HOST}:{port}", flush=True)
    print(f"Studio   {STUDIO_URL}", flush=True)
    start_worker()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()
        stop_worker()
        server.shutdown()


run = main


if __name__ == "__main__":
    main()
