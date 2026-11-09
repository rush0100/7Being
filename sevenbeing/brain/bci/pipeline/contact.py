"""Contact quality when the headset does not send a CQ byte.

Score is 0–1 per channel. A sample near the PGA rail is a bad contact.
Large sample-to-sample steps (a loose electrode) pull the score down.
A quiet in-range trace stays high.
"""

from __future__ import annotations


class ContactProxy:
    def __init__(self, n_ch: int, rate: int, full_scale_uv: float) -> None:
        self.n = max(1, int(n_ch))
        self.rate = max(1, int(rate))
        self.full_scale_uv = max(1.0, float(full_scale_uv))
        self._prev = [0.0] * self.n
        self._rail = [0.0] * self.n
        self._hf = [0.0] * self.n

    def push(self, row: list[float]) -> list[float]:
        rail_at = 0.85 * self.full_scale_uv
        hf_full = 0.15 * self.full_scale_uv
        out: list[float] = []
        for i in range(self.n):
            x = float(row[i]) if i < len(row) else 0.0
            rail = 1.0 if abs(x) >= rail_at else 0.0
            step = abs(x - self._prev[i])
            self._prev[i] = x
            self._rail[i] = 0.92 * self._rail[i] + 0.08 * rail
            self._hf[i] = 0.9 * self._hf[i] + 0.1 * step
            hf_bad = self._hf[i] / hf_full
            if hf_bad > 1.0:
                hf_bad = 1.0
            score = (1.0 - self._rail[i]) * (1.0 - 0.85 * hf_bad)
            if score < 0.0:
                score = 0.0
            elif score > 1.0:
                score = 1.0
            out.append(score)
        return out
