"""JSONL session recorder for EEG + control events."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .profile import SESSIONS, ensure_dirs


class SessionRecorder:
    def __init__(self) -> None:
        self.path: Path | None = None
        self._fh = None
        self.active = False
        self.rows = 0

    def start(self, profile_id: str) -> Path:
        self.stop()
        ensure_dirs()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in profile_id)[:40]
        path = SESSIONS / f"{safe}_{stamp}.jsonl"
        self.path = path
        self._fh = path.open("a", encoding="utf-8")
        self.active = True
        self.rows = 0
        self.mark("session_start", {"profile": profile_id})
        return path

    def stop(self) -> Path | None:
        path = self.path
        if self._fh is not None:
            try:
                self.mark("session_stop", {"rows": self.rows})
            except Exception:
                pass
            self._fh.close()
        self._fh = None
        self.active = False
        self.path = None
        return path

    def mark(self, marker: str, extra: dict | None = None) -> None:
        if not self.active or self._fh is None:
            return
        payload = {"t": time.time(), "marker": marker}
        if extra:
            payload.update(extra)
        self._fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fh.flush()
        self.rows += 1

    def write_sample(
        self,
        eeg: list[float],
        *,
        mental: str | None = None,
        conf: float | None = None,
        face: list[float] | None = None,
        affect: list[float] | None = None,
        command: str | None = None,
        source: str | None = None,
        marker: str | None = None,
    ) -> None:
        if not self.active or self._fh is None:
            return
        payload: dict = {"t": time.time(), "eeg": [round(float(v), 3) for v in eeg]}
        if mental is not None:
            payload["mental"] = mental
        if conf is not None:
            payload["conf"] = round(float(conf), 4)
        if face is not None:
            payload["face"] = face
        if affect is not None:
            payload["affect"] = affect
        if command is not None:
            payload["command"] = command
        if source is not None:
            payload["source"] = source
        if marker is not None:
            payload["marker"] = marker
        self._fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.rows += 1
        if self.rows % 32 == 0:
            self._fh.flush()
