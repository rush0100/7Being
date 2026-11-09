"""Band-power feature vectors for mental-command training and live classify.

Feature width follows the live montage: ``n_ch × 5 bands`` (works for 1–N channels).
"""

from __future__ import annotations

import math

import numpy as np

RATE = 128
# Match AffectMeter / BandPowerEngine (~2 s) so live can share one rfft hop.
WINDOW_S = 2.0
HOP_S = 0.25
N_CH = 14  # Emotiv default; FeatureExtractor accepts any n_ch

BANDS = (
    ("theta", 4.0, 8.0),
    ("alpha", 8.0, 12.0),
    ("lowBeta", 12.0, 16.0),
    ("highBeta", 16.0, 25.0),
    ("gamma", 25.0, 45.0),
)
N_BANDS = len(BANDS)
FEAT_DIM = N_CH * N_BANDS  # default 14-ch width; prefer extractor.feat_dim


def feat_dim(n_ch: int) -> int:
    return int(n_ch) * N_BANDS


def features_from_power(stacked: np.ndarray) -> np.ndarray:
    """bands×ch absolute power → flat log1p feature vector (ch-major)."""
    logged = np.log1p(np.maximum(stacked, 0.0))
    return logged.T.reshape(-1).astype(np.float64)


class FeatureExtractor:
    """Rolling log-band-power features (n_ch × 5 bands)."""

    def __init__(self, rate: int = RATE, n_ch: int = N_CH) -> None:
        self.n_ch = max(1, int(n_ch))
        self.set_rate(rate)

    @property
    def feat_dim(self) -> int:
        return feat_dim(self.n_ch)

    def set_n_ch(self, n_ch: int) -> None:
        n = max(1, int(n_ch))
        if n == self.n_ch:
            return
        self.n_ch = n
        self.set_rate(self.rate)

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
        self.latest: np.ndarray | None = None

    def from_powers(self, stacked: np.ndarray) -> np.ndarray:
        """Use a shared BandPowerEngine hop (bands × ch)."""
        feat = features_from_power(np.asarray(stacked, dtype=np.float64))
        self.latest = feat
        return feat

    def push(self, values: list[float] | np.ndarray) -> np.ndarray | None:
        if len(values) < self.n_ch:
            return None
        self._buf[self._pos, :] = np.asarray(values[: self.n_ch], dtype=np.float64)
        self._pos += 1
        if self._pos >= self.window:
            self._pos = 0
        if self._count < self.window:
            self._count += 1
        self._since += 1
        if self._count < self.window or self._since < self.hop:
            return None
        self._since = 0
        feat = self._compute(self._ordered())
        self.latest = feat
        return feat

    def _ordered(self) -> np.ndarray:
        out = self._scratch
        p = self._pos
        n = self.window
        if p == 0:
            np.copyto(out, self._buf)
        else:
            out[: n - p] = self._buf[p:]
            out[n - p :] = self._buf[:p]
        return out

    def _compute(self, window: np.ndarray) -> np.ndarray:
        centered = window - window.mean(axis=0)
        spec = np.fft.rfft(centered * self._hann[:, None], axis=0)
        power = (spec.real * spec.real + spec.imag * spec.imag) * (1.0 / self.window)
        parts = []
        for mask in self._masks:
            if mask.any():
                parts.append(power[mask].sum(axis=0))
            else:
                parts.append(np.zeros(self.n_ch, dtype=np.float64))
        stacked = np.stack(parts, axis=0)  # bands × ch
        return features_from_power(stacked)


def normalize_features(
    feat: np.ndarray,
    mean: np.ndarray | None,
    std: np.ndarray | None,
) -> np.ndarray:
    if mean is None or std is None:
        return feat
    scale = np.maximum(std, 1e-6)
    return (feat - mean) / scale


def feature_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(math.sqrt(float(np.sum((a - b) ** 2))))
