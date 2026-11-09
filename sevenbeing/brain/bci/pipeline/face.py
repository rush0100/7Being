"""Blink, wink, and horizontal gaze from the library's default profile.

The bandpass is BlinkWinkState's filter. Gaze uses HEDetector's peak test:
a peak beyond he-gradient_th (8.5), correlation below he-corr_th (-0.2),
and a hold of he-time_th seconds. Blink versus wink uses he-height_range_lo
(30) on the same filtered AF3/F7 and AF4/F8 pair.

IIR coefficients are designed for 128 Hz. At 256 Hz the meter decimates 2:1
before the filter so the frequency response stays valid.
"""

from __future__ import annotations

from collections import deque

NAMES = ("Blink", "Wink L", "Wink R", "Look L", "Look R")

# BlinkWinkState filter, order 3.
_B = (0.0115615007859192, -0.00347706824813574, -0.00347706824813575, 0.0115615007859192)
_A = (1.0, -2.57610703755538, 2.28676602998934, -0.694490127358385)

GRADIENT_TH = 8.5
CORR_TH = -0.2
HEIGHT_LO = 30.0
HOLD_S = 4.0
RATE = 128

# AF3 F7 ... F8 AF4
AF3, F7, F8, AF4 = 0, 1, 12, 13


class _IIR:
    __slots__ = ("x0", "x1", "x2", "x3", "y0", "y1", "y2")

    def __init__(self) -> None:
        self.x0 = self.x1 = self.x2 = self.x3 = 0.0
        self.y0 = self.y1 = self.y2 = 0.0

    def step(self, value: float) -> float:
        self.x3, self.x2, self.x1, self.x0 = self.x2, self.x1, self.x0, value
        out = (
            _B[0] * self.x0
            + _B[1] * self.x1
            + _B[2] * self.x2
            + _B[3] * self.x3
            - _A[1] * self.y0
            - _A[2] * self.y1
            - _A[3] * self.y2
        )
        self.y2, self.y1, self.y0 = self.y1, self.y0, out
        return out


def _corr(left: deque[float] | list[float], right: deque[float] | list[float]) -> float:
    n = len(left)
    if n < 8:
        return 0.0
    ml = sum(left) / n
    mr = sum(right) / n
    num = den_l = den_r = 0.0
    for a, b in zip(left, right):
        da = a - ml
        db = b - mr
        num += da * db
        den_l += da * da
        den_r += db * db
    den = (den_l * den_r) ** 0.5
    if den <= 1e-12:
        return 0.0
    return num / den


class _ForeheadBlink:
    """Blink from one forehead channel. Wink and gaze need a lateral pair."""

    def __init__(self, rate: int) -> None:
        self._rate = max(1, int(rate))
        self._buf: deque[float] = deque(maxlen=self._rate)
        self._sum = 0.0
        self._n = 0
        self._blink_until = 0
        self._hold = max(1, int(0.4 * self._rate))
        self._prev = 0.0

    def push(self, sample: list[float]) -> list[float | None]:
        self._n += 1
        x = float(sample[0]) if sample else 0.0
        buf = self._buf
        if len(buf) == buf.maxlen:
            self._sum -= buf[0]
        buf.append(x)
        self._sum += x
        base = self._sum / len(buf)
        dev = x - base
        blink = 1.0 if self._n < self._blink_until else 0.0
        # Rails and the startup swing are not blinks. Threshold rides above
        # the recent noise so a quiet Fpz trace does not sit on Blink.
        if len(buf) >= max(8, self._rate // 4) and abs(x) < 20_000.0:
            spread = sorted(abs(v - base) for v in buf)
            mad = spread[len(spread) // 2]
            th = max(180.0, mad * 8.0)
            if abs(dev) >= th and abs(dev) >= abs(self._prev):
                self._blink_until = self._n + self._hold
                blink = 1.0
        self._prev = dev
        return [blink, None, None, None, None]


class FaceMeter:
    def __init__(self, rate: int = RATE, n_ch: int = 14) -> None:
        self._input_rate = int(rate) if rate > 0 else RATE
        self.lateral = int(n_ch) >= 14
        self._forehead = None if self.lateral else _ForeheadBlink(self._input_rate)
        self.values: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0]
        if not self.lateral:
            return
        # Detector clock matches the 128 Hz IIR design rate.
        self._rate = RATE
        self._decimate = 2 if self._input_rate >= 256 else 1
        self._phase = 0
        self._filters = {name: _IIR() for name in (AF3, F7, F8, AF4)}
        self._filt = {name: deque(maxlen=self._rate) for name in (AF3, F7, F8, AF4)}
        self._filt_sum = {name: 0.0 for name in (AF3, F7, F8, AF4)}
        self._left: deque[float] = deque(maxlen=16)
        self._right: deque[float] = deque(maxlen=16)
        self._af3: deque[float] = deque(maxlen=64)
        self._af4: deque[float] = deque(maxlen=64)
        self._gaze = 0
        self._gaze_at = -10**9
        self._n = 0
        self._blink_until = 0
        self._wink_l_until = 0
        self._wink_r_until = 0
        self._hold = int(HOLD_S * self._rate)
        self._blink_hold = int(0.4 * self._rate)
    def push(self, sample: list[float]) -> list[float | None]:
        if self._forehead is not None:
            return self._forehead.push(sample)
        if len(sample) < 14:
            return self.values
        if self._decimate > 1:
            keep = self._phase == 0
            self._phase = (self._phase + 1) % self._decimate
            if not keep:
                return self.values
        return self._step(sample)

    def _step(self, sample: list[float]) -> list[float]:
        self._n += 1
        af3 = self._dev(AF3, self._filters[AF3].step(float(sample[AF3])))
        f7 = self._dev(F7, self._filters[F7].step(float(sample[F7])))
        f8 = self._dev(F8, self._filters[F8].step(float(sample[F8])))
        af4 = self._dev(AF4, self._filters[AF4].step(float(sample[AF4])))
        self._af3.append(af3)
        self._af4.append(af4)
        self._left.append(max(abs(af3), abs(f7)))
        self._right.append(max(abs(f8), abs(af4)))
        self._update_gaze()
        self._update_blink()
        look_l = 1.0 if self._gaze < 0 and self._n - self._gaze_at <= self._hold else 0.0
        look_r = 1.0 if self._gaze > 0 and self._n - self._gaze_at <= self._hold else 0.0
        if look_l == 0.0 and look_r == 0.0:
            self._gaze = 0
        vals = self.values
        vals[0] = 1.0 if self._n < self._blink_until else 0.0
        vals[1] = 1.0 if self._n < self._wink_l_until else 0.0
        vals[2] = 1.0 if self._n < self._wink_r_until else 0.0
        vals[3] = look_l
        vals[4] = look_r
        return vals

    def _dev(self, name: int, value: float) -> float:
        buf = self._filt[name]
        if len(buf) == buf.maxlen:
            self._filt_sum[name] -= buf[0]
        buf.append(value)
        self._filt_sum[name] += value
        baseline = self._filt_sum[name] / len(buf)
        return value - baseline

    def _update_gaze(self) -> None:
        if len(self._af3) < 64:
            return
        if _corr(self._af3, self._af4) >= CORR_TH:
            return
        code = _opposed_peak(self._af3, self._af4)
        if code == 0:
            return
        self._gaze = code
        self._gaze_at = self._n

    def _update_blink(self) -> None:
        if len(self._left) < 16:
            return
        left = max(self._left)
        right = max(self._right)
        both = min(left, right)
        af3 = self._af3
        af4 = self._af4
        n = len(af3)
        if both >= HEIGHT_LO and n >= 16 and _corr(
            [af3[i] for i in range(n - 16, n)],
            [af4[i] for i in range(n - 16, n)],
        ) > 0.5:
            self._blink_until = self._n + self._blink_hold
            return
        if left >= HEIGHT_LO and right < HEIGHT_LO * 0.5:
            self._wink_l_until = self._n + self._blink_hold
        elif right >= HEIGHT_LO and left < HEIGHT_LO * 0.5:
            self._wink_r_until = self._n + self._blink_hold


def _pair(a: float, b: float) -> bool:
    mag = min(abs(a), abs(b))
    return mag > HEIGHT_LO and max(abs(a), abs(b)) < 2.5 * mag and a * b < 0


def _opposed_peak(left: deque[float] | list[float], right: deque[float] | list[float]) -> int:
    a, b, c = left[-3], left[-2], left[-1]
    r = right[-2]
    if b > a and b > c and _pair(b, r):
        return -1 if b > 0 else 1
    a, b, c = right[-3], right[-2], right[-1]
    other = left[-2]
    if b > a and b > c and _pair(b, other):
        return 1 if b > 0 else -1
    return 0
