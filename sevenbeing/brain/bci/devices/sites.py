"""10–20 scalp sites for electrode mapping UI (top-down head view).

Coordinates are normalized 0–1: x = left→right (subject), y = nose→occiput.
"""

from __future__ import annotations

from typing import Iterable

# (name, x, y) — top-down schematic, nose at top (small y).
_SITE_ROWS: tuple[tuple[str, float, float], ...] = (
    ("Fp1", 0.35, 0.10),
    ("Fpz", 0.50, 0.06),
    ("Fp2", 0.65, 0.10),
    ("AF3", 0.32, 0.18),
    ("AF4", 0.68, 0.18),
    ("F7", 0.16, 0.28),
    ("F3", 0.34, 0.28),
    ("Fz", 0.50, 0.26),
    ("F4", 0.66, 0.28),
    ("F8", 0.84, 0.28),
    ("FC5", 0.22, 0.38),
    ("FC6", 0.78, 0.38),
    ("T7", 0.08, 0.50),
    ("C3", 0.32, 0.50),
    ("Cz", 0.50, 0.50),
    ("C4", 0.68, 0.50),
    ("T8", 0.92, 0.50),
    ("CP5", 0.22, 0.60),
    ("CP6", 0.78, 0.60),
    ("P7", 0.18, 0.70),
    ("P3", 0.34, 0.70),
    ("Pz", 0.50, 0.68),
    ("P4", 0.66, 0.70),
    ("P8", 0.82, 0.70),
    ("O1", 0.38, 0.88),
    ("Oz", 0.50, 0.92),
    ("O2", 0.62, 0.88),
    # Emotiv hardware references (not signal channels).
    ("CMS", 0.42, 0.58),
    ("DRL", 0.58, 0.58),
)

SITE_NAMES: tuple[str, ...] = tuple(n for n, _x, _y in _SITE_ROWS)
SITE_XY: dict[str, tuple[float, float]] = {n: (x, y) for n, x, y in _SITE_ROWS}
REF_CANDIDATES: tuple[str, ...] = ("CMS", "DRL", "A1", "A2", "Tp9", "Tp10", "Cz")

def sites_public() -> list[dict]:
    return [{"name": n, "x": x, "y": y, "ref": n in ("CMS", "DRL")} for n, x, y in _SITE_ROWS]


def default_reference(kind: str | None = None) -> str:
    if (kind or "").lower() in ("epocx", "epoc", "emotiv", "emotiv_insight"):
        return "CMS"
    return "CMS"


def coerce_assignments(
    n: int,
    labels: Iterable[str | None] | None,
    *,
    fill: bool = True,
) -> list[str]:
    """Normalize to length ``n``; unknown kept as-is; empty → Ch{i+1} if fill."""
    src = list(labels) if labels is not None else []
    out: list[str] = []
    for i in range(n):
        raw = src[i] if i < len(src) else None
        name = (str(raw).strip() if raw is not None else "") or ""
        if not name and fill:
            name = f"Ch{i + 1}"
        out.append(name)
    return out
