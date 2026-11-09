"""Resting baseline collection for feature normalization."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .features import N_BANDS, FeatureExtractor

MIN_FRAMES = 1


@dataclass
class CalibrationResult:
    mean: np.ndarray
    std: np.ndarray
    n_frames: int
    duration_s: float


class Calibrator:
    """Collect feature frames during eyes-open rest."""

    def __init__(self, rate: int = 128, duration_s: float = 30.0, n_ch: int = 14) -> None:
        self.duration_s = float(duration_s)
        self.extractor = FeatureExtractor(rate, n_ch=n_ch)
        self._rows: list[np.ndarray] = []
        self._t0: float | None = None
        self._active = False
        self.result: CalibrationResult | None = None

    def set_rate(self, rate: int) -> None:
        self.extractor.set_rate(rate)

    def set_n_ch(self, n_ch: int) -> None:
        self.extractor.set_n_ch(n_ch)

    def start(self) -> None:
        self._rows = []
        self._t0 = time.monotonic()
        self._active = True
        self.result = None
        # Fresh ring so warm-up starts now (don't inherit stale mental buffer).
        self.extractor.set_rate(self.extractor.rate)

    def stop(self) -> CalibrationResult | None:
        self._active = False
        if len(self._rows) < MIN_FRAMES:
            return None
        stacked = np.stack(self._rows, axis=0)
        mean = stacked.mean(axis=0)
        std = stacked.std(axis=0)
        std = np.maximum(std, 1e-3)
        elapsed = 0.0 if self._t0 is None else time.monotonic() - self._t0
        self.result = CalibrationResult(
            mean=mean, std=std, n_frames=len(self._rows), duration_s=elapsed
        )
        return self.result

    @property
    def active(self) -> bool:
        return self._active

    def progress(self) -> float:
        if not self._active or self._t0 is None:
            return 0.0 if self.result is None else 1.0
        # Snap to 1.0 once wall time is up so the bar never sits on 99 while finishing.
        elapsed = time.monotonic() - self._t0
        if elapsed >= self.duration_s:
            return 1.0
        return min(1.0, elapsed / max(self.duration_s, 1e-6))

    def _maybe_finish(self) -> CalibrationResult | None:
        if not self._active or self._t0 is None:
            return None
        elapsed = time.monotonic() - self._t0
        n = len(self._rows)
        # Soft/normal finish: duration elapsed + at least one feature frame.
        if elapsed >= self.duration_s and n >= MIN_FRAMES:
            return self.stop()
        # Hard timeout: BLE/FFT stalled — end so UI unblocks (may return None).
        if elapsed >= self.duration_s + 3.0:
            return self.stop()
        return None

    def tick(self) -> CalibrationResult | None:
        """Wall-clock poll while active (works even if BLE samples pause)."""
        return self._maybe_finish()

    def push(
        self,
        values: list[float],
        band_power: object | None = None,
        *,
        shared_bands: bool = False,
    ) -> CalibrationResult | None:
        if not self._active:
            return None
        # Prefer shared hop when present; otherwise keep a private FFT rolling
        # so calibration never starves if AffectMeter hops are skipped.
        # Always feed the private ring so we still produce frames if shared hops pause.
        feat = None
        if band_power is not None:
            feat = self.extractor.from_powers(band_power)  # type: ignore[arg-type]
        private = self.extractor.push(values)
        if feat is None:
            feat = private
        if feat is not None:
            self._rows.append(feat.copy())
        return self._maybe_finish()

    def save(self, path) -> None:
        if self.result is None:
            raise RuntimeError("no calibration result")
        np.savez(
            path,
            mean=self.result.mean,
            std=self.result.std,
            n_frames=self.result.n_frames,
            duration_s=self.result.duration_s,
        )

    @staticmethod
    def load(path) -> CalibrationResult:
        from pathlib import Path

        from ..store.profile import PROFILES

        resolved = Path(path).resolve()
        root = PROFILES.resolve()
        if root not in resolved.parents:
            raise ValueError("calibration path outside profile store")
        if resolved.suffix != ".npz" or resolved.name != "calibration.npz":
            raise ValueError("refusing to load unexpected calibration file")
        data = np.load(resolved)
        mean = np.asarray(data["mean"], dtype=np.float64)
        std = np.asarray(data["std"], dtype=np.float64)
        if mean.ndim != 1 or std.shape != mean.shape or mean.size % N_BANDS != 0:
            raise ValueError("calibration shape mismatch")
        return CalibrationResult(
            mean=mean,
            std=np.maximum(std, 1e-3),
            n_frames=int(data["n_frames"]),
            duration_s=float(data["duration_s"]),
        )
