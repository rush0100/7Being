"""Features, calibration, LDA mental commands, and control routing."""

from .calibrate import CalibrationResult, Calibrator
from .control import ControlOutput, ControlRouter
from .engine import MentalEngine, MentalPrediction
from .features import FEAT_DIM, FeatureExtractor, normalize_features

__all__ = [
    "FEAT_DIM",
    "CalibrationResult",
    "Calibrator",
    "ControlOutput",
    "ControlRouter",
    "FeatureExtractor",
    "MentalEngine",
    "MentalPrediction",
    "normalize_features",
]
