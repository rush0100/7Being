"""EEG channel montages — any count the drivers advertise (1, 2, 4, 6, 8, 14, …)."""

from __future__ import annotations

from dataclasses import dataclass

# Counts the library is built to host. Drivers may use any of these (or others).
COMMON_CHANNEL_COUNTS: tuple[int, ...] = (1, 2, 4, 5, 6, 8, 14, 16, 32)

# Named layouts for common headsets / DIY boards. Unknown N → Ch1…ChN.
_PRESETS: dict[int, tuple[str, ...]] = {
    1: ("Fpz",),
    2: ("Fp1", "Fp2"),
    4: ("TP9", "AF7", "AF8", "TP10"),  # Muse-style
    5: ("AF3", "AF4", "T7", "T8", "Pz"),  # Insight-style
    6: ("Fp1", "Fp2", "C3", "C4", "O1", "O2"),
    8: ("Fp1", "Fp2", "C3", "C4", "T7", "T8", "O1", "O2"),
    # Emotiv EPOC order (same as sevenbeing.ble.raw.CHANNELS)
    14: (
        "AF3",
        "F7",
        "F3",
        "FC5",
        "T7",
        "P7",
        "O1",
        "O2",
        "P8",
        "T8",
        "FC6",
        "F4",
        "F8",
        "AF4",
    ),
    16: (
        "Fp1",
        "Fp2",
        "F3",
        "F4",
        "C3",
        "C4",
        "P3",
        "P4",
        "O1",
        "O2",
        "F7",
        "F8",
        "T7",
        "T8",
        "P7",
        "P8",
    ),
    32: tuple(f"Ch{i + 1}" for i in range(32)),
}


@dataclass(frozen=True)
class Montage:
    """Electrode layout for one live device / profile."""

    channels: tuple[str, ...]
    sample_rate_hz: int = 128
    units: str = "uV"
    reference: str = "CMS"
    # Channel indexes the user turned off. At least one channel stays open.
    closed: tuple[int, ...] = ()

    @property
    def n_channels(self) -> int:
        return len(self.channels)

    def to_public(self) -> dict:
        from .sites import REF_CANDIDATES, sites_public

        return {
            "n_channels": self.n_channels,
            "channels": list(self.channels),
            "sample_rate_hz": self.sample_rate_hz,
            "units": self.units,
            "reference": self.reference,
            "sites": sites_public(),
            "ref_candidates": list(REF_CANDIDATES),
            # Channel index → site label (same as channels; kept explicit for UI).
            "assignments": list(self.channels),
            "closed": list(self.closed),
        }

    @classmethod
    def for_count(
        cls,
        n: int,
        *,
        labels: tuple[str, ...] | list[str] | None = None,
        sample_rate_hz: int = 128,
        units: str = "uV",
        reference: str = "CMS",
    ) -> "Montage":
        n = int(n)
        if n < 1:
            raise ValueError("n_channels must be >= 1")
        if labels is not None:
            names = tuple(str(x) for x in labels)
            if len(names) != n:
                raise ValueError(f"labels length {len(names)} != n_channels {n}")
        elif n in _PRESETS:
            names = _PRESETS[n]
        else:
            names = tuple(f"Ch{i + 1}" for i in range(n))
        return cls(
            channels=names,
            sample_rate_hz=int(sample_rate_hz),
            units=units,
            reference=reference,
        )


def labels_for(n: int) -> tuple[str, ...]:
    return Montage.for_count(n).channels


def closed_indices(n: int, raw: object) -> tuple[int, ...]:
    """Channel indexes to drop from live views. Rejects closing every channel."""
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise ValueError("closed must be a list of channel indexes")
    seen: list[int] = []
    for item in raw:
        index = int(item)
        if 0 <= index < n and index not in seen:
            seen.append(index)
    if n > 0 and len(seen) >= n:
        raise ValueError("ต้องเปิดอย่างน้อย 1 แชนแนล")
    return tuple(seen)


EPOCX_MONTAGE = Montage.for_count(14, sample_rate_hz=128)
