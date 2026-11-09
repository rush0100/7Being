"""Live 0–1 affect scores from the 14 EEG channels.

The detectors in the library turn band power into Excitement, Engagement,
Relaxation, Stress, Interest, and Focus. Band edges are the live θ/α/β set.
(theta 4–8, alpha 8–12, beta 12–25 via low+high, gamma 25–45).

FFT work lives in BandPowerEngine so mental features can reuse the same hop.
"""

from __future__ import annotations

import math

import numpy as np

from .band_engine import BANDS, N_CH, BandPowerEngine

RATE = 128
# Re-export for callers / tests that imported BANDS from affect.
__all__ = ("AffectMeter", "BANDS", "NAMES", "RATE")

# AF3 F7 F3 FC5 T7 P7 O1 O2 P8 T8 FC6 F4 F8 AF4
FRONTAL = np.asarray((0, 2, 3, 10, 11, 13), dtype=np.intp)
POSTERIOR = np.asarray((5, 6, 7, 8), dtype=np.intp)
AF3 = 0
AF4 = 13

NAMES = (
    "Excitement",
    "Engagement",
    "Relaxation",
    "Stress",
    "Interest",
    "Focus",
)


def _sigmoid(value: float, center: float, width: float) -> float:
    z = (math.log(max(value, 1e-9)) - math.log(center)) / width
    z = max(-8.0, min(8.0, z))
    return 1.0 / (1.0 + math.exp(-z))


class AffectMeter:
    def __init__(
        self,
        rate: int = RATE,
        engine: BandPowerEngine | None = None,
        *,
        n_ch: int = N_CH,
    ) -> None:
        n = max(1, int(n_ch))
        if engine is None:
            self._engine = BandPowerEngine(rate, n_ch=n)
            self._engine.set_rate(rate)
        else:
            self._engine = engine
            if engine.n_ch != n:
                engine.set_n_ch(n)
            engine.set_rate(rate)
        self._smooth: list[float] | None = None
        self.closed: tuple[int, ...] = ()
        self.bands: list[float] | None = None
        self.channel_bands: list[list[float]] | None = None
        self.band_gen = 0
        self.last_power: np.ndarray | None = None

    @property
    def engine(self) -> BandPowerEngine:
        return self._engine

    def push(self, values: list[float]) -> list[float] | None:
        power = self._engine.push(values)
        if power is None:
            return self._smooth
        self.last_power = power
        raw = self._scores_from_power(power)
        if self._smooth is None:
            self._smooth = raw
        else:
            old = self._smooth
            self._smooth = [0.75 * old[i] + 0.25 * raw[i] for i in range(len(raw))]
        return self._smooth

    def _scores_from_power(self, stacked: np.ndarray) -> list[float]:
        # stacked: bands × channels (absolute power)
        theta, alpha, low_beta, high_beta = stacked[0], stacked[1], stacked[2], stacked[3]
        beta = low_beta + high_beta
        total = stacked.sum(axis=0)
        share = stacked / np.maximum(total, 1e-12)
        n = int(stacked.shape[1])
        off = {int(i) for i in self.closed if 0 <= int(i) < n}
        open_idx = np.asarray([i for i in range(n) if i not in off], dtype=np.intp)
        if open_idx.size == 0:
            open_idx = np.arange(n)
        self.bands = [round(float(share[b, open_idx].mean()), 3) for b in range(len(BANDS))]
        channel_bands: list[list[float]] = []
        for ch in range(n):
            if ch in off:
                channel_bands.append([0.0, 0.0, 0.0, 0.0])
                continue
            t = float(share[0, ch])
            a = float(share[1, ch])
            b = float(share[2, ch] + share[3, ch])
            g = float(share[4, ch])
            s = t + a + b + g
            if s <= 1e-12:
                channel_bands.append([0.25, 0.25, 0.25, 0.25])
            else:
                channel_bands.append(
                    [round(t / s, 3), round(a / s, 3), round(b / s, 3), round(g / s, 3)]
                )
        self.channel_bands = channel_bands
        self.band_gen = self._engine.gen

        # 14-channel EPOC keeps the frontal / posterior / AF3–AF4 split.
        # Closed channels drop out of those averages. One channel (H1 Fpz)
        # uses that spectrum for every score. Interest stays 0.5 when there
        # is no open left/right pair.
        def _keep(idx: np.ndarray) -> np.ndarray:
            kept = [int(i) for i in idx if int(i) < n and int(i) not in off]
            if not kept:
                return open_idx
            return np.asarray(kept, dtype=np.intp)

        if n > AF4:
            front = _keep(FRONTAL)
            back = _keep(POSTERIOR)
            if AF3 in off or AF4 in off:
                interest = 0.5
            else:
                asymmetry = math.log(float(alpha[AF4]) + 1e-12) - math.log(
                    float(alpha[AF3]) + 1e-12
                )
                interest = 0.5 + 0.5 * math.tanh(asymmetry)
        else:
            front = _keep(FRONTAL)
            back = _keep(POSTERIOR)
            if n == 1 or back.size == 0:
                back = front
            interest = 0.5
        front_theta = float(theta[front].mean())
        front_alpha = float(alpha[front].mean())
        front_beta = float(beta[front].mean())
        front_low = float(low_beta[front].mean())
        front_high = float(high_beta[front].mean())
        back_alpha = float(alpha[back].mean())
        back_beta = float(beta[back].mean())
        excitement = _sigmoid(front_beta / (front_alpha + 1e-12), 1.0, 0.55)
        engagement = _sigmoid(front_beta / (front_alpha + front_theta + 1e-12), 0.7, 0.55)
        relaxation = back_alpha / (back_alpha + back_beta + 1e-12)
        stress = _sigmoid(front_high / (front_alpha + 1e-12), 0.8, 0.55)
        focus = _sigmoid(front_low / (front_theta + front_high + 1e-12), 0.45, 0.55)
        return [excitement, engagement, relaxation, stress, interest, focus]
