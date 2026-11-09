"""7Being — seven pillars for wellbeing sensing & BCI.

Install::

    pip install sevenbeing

Pillars: Brain · Body · Breath · Emotion · Attention · Environment · Being

Brain → BCI is the first shipping subsystem (EEG devices over gRPC)::

    pip install 7being-emotiv-epocx
    7being-emotiv-epocx-serve --port 51051
    export SEVENBEING_DEVICE_GRPC=127.0.0.1:51051
"""

from __future__ import annotations

__version__ = "0.1.0"

from .pillars import PILLARS, Pillar, PillarInfo, pillar_by_name

# Brain → BCI (primary shipping surface)
from .brain.bci import (
    COMMON_CHANNEL_COUNTS,
    CORE,
    AppCore,
    DeviceCallbacks,
    DeviceInfo,
    DeviceKind,
    DeviceManager,
    EPOCX_MONTAGE,
    Montage,
    discover_drivers,
    labels_for,
    run_gui,
)
from .brain.bci.mental.calibrate import CalibrationResult, Calibrator
from .brain.bci.mental.control import ControlOutput, ControlRouter
from .brain.bci.mental.engine import MentalEngine, MentalPrediction
from .brain.bci.mental.features import FEAT_DIM, FeatureExtractor, feat_dim, normalize_features
from .brain.bci.pipeline.affect import AffectMeter
from .brain.bci.pipeline.face import FaceMeter
from .brain.bci.pipeline.signal import SignalMeter
from .brain.bci.store.profile import ACTIONS, create_profile, list_profiles, load_profile, save_profile
from .brain.bci.store.session import SessionRecorder

CHANNELS = EPOCX_MONTAGE.channels

__all__ = [
    "ACTIONS",
    "AffectMeter",
    "AppCore",
    "CHANNELS",
    "COMMON_CHANNEL_COUNTS",
    "CORE",
    "CalibrationResult",
    "Calibrator",
    "ControlOutput",
    "ControlRouter",
    "DeviceCallbacks",
    "DeviceInfo",
    "DeviceKind",
    "DeviceManager",
    "EPOCX_MONTAGE",
    "FEAT_DIM",
    "FaceMeter",
    "FeatureExtractor",
    "MentalEngine",
    "MentalPrediction",
    "Montage",
    "PILLARS",
    "Pillar",
    "PillarInfo",
    "SessionRecorder",
    "SignalMeter",
    "__version__",
    "create_profile",
    "discover_drivers",
    "feat_dim",
    "labels_for",
    "list_profiles",
    "load_profile",
    "normalize_features",
    "pillar_by_name",
    "run_gui",
    "save_profile",
]
