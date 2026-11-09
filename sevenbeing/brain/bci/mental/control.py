"""Merge mental-command and face into a single control output."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..pipeline.face import NAMES as FACE_NAMES
from .engine import MentalPrediction
from ..store.profile import DEFAULT_KEYMAP


@dataclass
class ControlOutput:
    name: str
    key: str
    source: str  # mental | face | neutral
    confidence: float


class ControlRouter:
    def __init__(
        self,
        keymap: dict[str, str] | None = None,
        mental_threshold: float = 0.55,
        debounce_ms: int = 400,
    ) -> None:
        self.keymap = dict(DEFAULT_KEYMAP)
        if keymap:
            self.keymap.update(keymap)
        self.mental_threshold = float(mental_threshold)
        self.debounce_s = max(0.0, debounce_ms / 1000.0)
        self._last_name = "Neutral"
        self._last_fire_t = 0.0
        self._shown = ControlOutput("Neutral", "", "neutral", 0.0)

    def configure(
        self,
        keymap: dict[str, str] | None = None,
        mental_threshold: float | None = None,
        debounce_ms: int | None = None,
    ) -> None:
        if keymap is not None:
            self.keymap = dict(DEFAULT_KEYMAP)
            self.keymap.update(keymap)
        if mental_threshold is not None:
            self.mental_threshold = float(mental_threshold)
        if debounce_ms is not None:
            self.debounce_s = max(0.0, debounce_ms / 1000.0)

    def resolve(
        self,
        mental: MentalPrediction | None,
        face: list[float] | None,
    ) -> ControlOutput:
        now = time.monotonic()
        candidate: ControlOutput | None = None

        if (
            mental is not None
            and mental.label
            and mental.label != "Neutral"
            and mental.confidence >= self.mental_threshold
        ):
            candidate = ControlOutput(
                mental.label,
                self.keymap.get(mental.label, ""),
                "mental",
                mental.confidence,
            )
        else:
            face_name = self._face_command(face)
            if face_name:
                candidate = ControlOutput(
                    face_name,
                    self.keymap.get(face_name, ""),
                    "face",
                    1.0,
                )

        if candidate is None:
            out = ControlOutput("Neutral", "", "neutral", 0.0 if mental is None else mental.confidence)
            self._shown = out
            return out

        # Debounce label switches (except immediate mental→face fallback).
        if candidate.name != self._last_name and self.debounce_s > 0:
            falling_back = self._shown.source == "mental" and candidate.source == "face"
            if (
                not falling_back
                and now - self._last_fire_t < self.debounce_s
                and self._last_name != "Neutral"
            ):
                return self._shown
            self._last_name = candidate.name
            self._last_fire_t = now
        elif candidate.name != self._last_name:
            self._last_name = candidate.name
            self._last_fire_t = now
        self._shown = candidate
        return candidate

    def _face_command(self, face: list[float] | None) -> str:
        if not face:
            return ""
        for name, value in zip(FACE_NAMES, face):
            if value is not None and value > 0:
                return name
        return ""
