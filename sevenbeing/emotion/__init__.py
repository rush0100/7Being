"""04 Emotion — affective state.

Today: re-exports live affect meters from Brain→BCI EEG pipeline.
"""

from __future__ import annotations

CODE = "04"
NAME = "emotion"
TITLE = "Emotion"
BLURB = "Affective state"
STATUS = "partial"  # driven by Brain EEG affect for now

try:
    from sevenbeing.brain.bci.pipeline.affect import AffectMeter, BANDS, NAMES
except ImportError:  # pragma: no cover
    AffectMeter = None  # type: ignore[misc, assignment]
    BANDS = ()
    NAMES = ()

__all__ = ["CODE", "NAME", "TITLE", "BLURB", "STATUS", "AffectMeter", "BANDS", "NAMES"]
