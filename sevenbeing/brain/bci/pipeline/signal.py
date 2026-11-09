"""Packet-loss signal strength from DataInterpolation::processSignalStrength.

Over the last second, strength is 1 minus lost counter steps divided by the
locked sample rate. A gap is lost steps only when the counter advances by
1..65, which is the range interpolate() keeps. Counter modulus matches the
sample rate (128 or 256).
"""

from __future__ import annotations

import time

RATE = 128
MOD = 128
WINDOW_S = 1.0
MAX_GAP = 65


class SignalMeter:
    def __init__(self, rate: int = RATE) -> None:
        self._rate = int(rate) if rate > 0 else RATE
        self._mod = self._rate
        self._prev: int | None = None
        self._events: list[tuple[float, int]] = []

    def push(self, counter: int, now: float | None = None) -> float:
        moment = time.monotonic() if now is None else now
        lost = 0
        if self._prev is not None:
            delta = (int(counter) - self._prev) % self._mod
            if 1 <= delta <= MAX_GAP:
                lost = delta - 1
        self._prev = int(counter) % self._mod
        if lost:
            self._events.append((moment, lost))
        cutoff = moment - WINDOW_S
        events = self._events
        while events and events[0][0] < cutoff:
            events.pop(0)
        lost_sum = 0
        for _t, count in events:
            lost_sum += count
        value = 1.0 - lost_sum / self._rate
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value
