"""Scan hints for the device list.

EPOC X is reached through EmotivPRO and the private LSL adapter.
This module does not inspect or stop other headset software.
"""

from __future__ import annotations

from typing import Any


def build_scan_hint(*, scanned: int, kinds: list[str], errors: list[str] | None = None) -> dict[str, Any]:
    codes: list[str] = []
    if "epocx" not in kinds:
        codes.append("lsl-adapter")
    if scanned == 0:
        codes.append("none-found")
    level = "warn" if scanned == 0 or errors else "ok"
    return {
        "level": level,
        "summary": "",
        "codes": codes,
        "tips": list(errors or [])[:3],
        "cortex_running": False,
    }
