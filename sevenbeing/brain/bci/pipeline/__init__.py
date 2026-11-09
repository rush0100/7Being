"""Band maps, affect / face / signal meters. Emotiv EegPipeline is optional."""

from .affect import AffectMeter
from .band_engine import BandPowerEngine
from .face import FaceMeter
from .signal import SignalMeter

try:
    from .eeg import BRAIN_BANDS, BRAIN_LOBES, EegPipeline, EegSample
except ImportError:  # 7being-emotiv-epocx not installed
    BRAIN_BANDS = ()
    BRAIN_LOBES = ()
    EegPipeline = None  # type: ignore[misc, assignment]
    EegSample = None  # type: ignore[misc, assignment]

__all__ = [
    "BRAIN_BANDS",
    "BRAIN_LOBES",
    "AffectMeter",
    "BandPowerEngine",
    "EegPipeline",
    "EegSample",
    "FaceMeter",
    "SignalMeter",
]
