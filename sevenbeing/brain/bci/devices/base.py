"""Device abstractions for multi-hardware 7Being (any channel count)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

from .montage import Montage, labels_for


class DeviceKind(str, Enum):
    """Hardware families the library can host.

    Drivers register on DeviceManager; ``n_channels`` lives on each DeviceInfo
    (1 / 2 / 4 / 6 / 8 / 14 / …) — kinds are vendors, not fixed montages.
    """

    EPOCX = "epocx"  # pip: 7being-emotiv-epocx (EPOC / + / X)
    H1 = "h1"  # pip: 7being-h1
    ADS1299 = "ads1299"  # pip: 7being-ads1299 (ADS1299EEGFE-PDK)
    EMOTIV_INSIGHT = "emotiv_insight"  # reserved
    MUSE = "muse"  # reserved
    OPENBCI = "openbci"  # reserved
    NEUROSKY = "neurosky"  # reserved
    GENERIC = "generic"  # DIY / serial / LSL adapters of any N


@dataclass(frozen=True)
class DeviceInfo:
    """Discovered or connected device identity + montage."""

    id: str  # stable within process, e.g. "epocx:AA:BB:…"
    kind: DeviceKind | str
    name: str
    address: str | None = None
    n_channels: int = 14
    channels: tuple[str, ...] = ()
    sample_rate_hz: int | None = None
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = int(self.n_channels) if self.n_channels else 0
        names = tuple(self.channels) if self.channels else ()
        if names and n and len(names) != n:
            raise ValueError(f"channels length {len(names)} != n_channels {n}")
        if not names:
            n = n or 14
            names = labels_for(n)
            object.__setattr__(self, "channels", names)
            object.__setattr__(self, "n_channels", n)
        else:
            object.__setattr__(self, "n_channels", len(names))

    @property
    def montage(self) -> Montage:
        rate = self.sample_rate_hz or 128
        return Montage(channels=self.channels, sample_rate_hz=rate)

    def to_public(self) -> dict:
        kind = self.kind.value if isinstance(self.kind, DeviceKind) else str(self.kind)
        return {
            "id": self.id,
            "kind": kind,
            "name": self.name,
            "address": self.address,
            "n_channels": self.n_channels,
            "channels": list(self.channels),
            "sample_rate_hz": self.sample_rate_hz,
            "meta": dict(self.meta),
        }


SampleHandler = Callable[[str, list[float]], None]  # device_id, channel values
MotionHandler = Callable[[str, list[float]], None]
BrainHandler = Callable[[str, dict], None]
StatusHandler = Callable[[str, str, bool], None]  # device_id, text, warn


@dataclass
class DeviceCallbacks:
    on_sample: SampleHandler | None = None
    on_motion: MotionHandler | None = None
    on_brain: BrainHandler | None = None
    on_cq: Callable[[str, int, float], None] | None = None
    on_counter: Callable[[str, int], None] | None = None
    on_status: StatusHandler | None = None


class DeviceDriver(Protocol):
    """One hardware family. Drivers are registered on DeviceManager."""

    kind: DeviceKind | str

    def scan(self, timeout: float = 5.0) -> list[DeviceInfo]:
        """Blocking BLE/USB scan; return discoverable devices of this kind."""
        ...

    def connect(self, info: DeviceInfo, callbacks: DeviceCallbacks) -> "LiveDevice":
        """Start streaming; returns a live handle (may spawn a worker thread)."""
        ...


class LiveDevice(Protocol):
    info: DeviceInfo

    @property
    def connected(self) -> bool: ...

    @property
    def sample_rate(self) -> int: ...

    @property
    def n_channels(self) -> int: ...

    def stop(self) -> None: ...

    def public_state(self) -> dict: ...
