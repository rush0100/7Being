"""Single rolling rfft hop shared by AffectMeter and mental FeatureExtractor.

Window / hop match AffectMeter (~2 s / 0.25 s). Absolute band power is
(bands × channels); callers derive affect scores or log-features from it.
"""

from __future__ import annotations

import numpy as np

RATE = 128
WINDOW_S = 2.0
HOP_S = 0.25
N_CH = 14

BANDS = (
    ("theta", 4.0, 8.0),
    ("alpha", 8.0, 12.0),
    ("lowBeta", 12.0, 16.0),
    ("highBeta", 16.0, 25.0),
    ("gamma", 25.0, 45.0),
)
N_BANDS = len(BANDS)


class BandPowerEngine:
    """One ring buffer + one rfft per hop for the live montage."""

    def __init__(self, rate: int = RATE, n_ch: int = N_CH) -> None:
        self.n_ch = max(1, int(n_ch))
        self.set_rate(rate)

    def set_rate(self, rate: int) -> None:
        self.rate = int(rate) if rate > 0 else RATE
        self.window = max(8, int(round(WINDOW_S * self.rate)))
        self.hop = max(1, int(round(HOP_S * self.rate)))
        self._buf = np.zeros((self.window, self.n_ch), dtype=np.float64)
        self._scratch = np.empty((self.window, self.n_ch), dtype=np.float64)
        self._pos = 0
        self._count = 0
        self._since = 0
        self._freqs = np.fft.rfftfreq(self.window, 1.0 / self.rate)
        self._hann = np.hanning(self.window).astype(np.float64)
        self._masks = tuple(
            (self._freqs >= lo) & (self._freqs < hi) for _name, lo, hi in BANDS
        )
        self.last_power: np.ndarray | None = None  # (n_bands, n_ch)
        self.gen = 0

    def set_n_ch(self, n_ch: int) -> None:
        n = max(1, int(n_ch))
        if n == self.n_ch:
            return
        self.n_ch = n
        self.set_rate(self.rate)

    def push(self, values: list[float] | np.ndarray) -> np.ndarray | None:
        if len(values) < self.n_ch:
            return None
        self._buf[self._pos] = np.asarray(values[: self.n_ch], dtype=np.float64)
        self._pos += 1
        if self._pos >= self.window:
            self._pos = 0
        if self._count < self.window:
            self._count += 1
        self._since += 1
        if self._count < self.window or self._since < self.hop:
            return None
        self._since = 0
        power = self._band_power(self._ordered())
        self.last_power = power
        self.gen += 1
        return power

    def _ordered(self) -> np.ndarray:
        out = self._scratch
        n = self.window
        p = self._pos
        if p == 0:
            np.copyto(out, self._buf)
        else:
            out[: n - p] = self._buf[p:]
            out[n - p :] = self._buf[:p]
        return out

    def _band_power(self, window: np.ndarray) -> np.ndarray:
        centered = window - window.mean(axis=0)
        spec = np.fft.rfft(centered * self._hann[:, None], axis=0)
        power = (spec.real * spec.real + spec.imag * spec.imag) * (1.0 / self.window)
        parts = []
        zeros = None
        for mask in self._masks:
            if mask.any():
                parts.append(power[mask].sum(axis=0))
            else:
                if zeros is None:
                    zeros = np.zeros(self.n_ch, dtype=np.float64)
                parts.append(zeros)
        return np.stack(parts, axis=0)
