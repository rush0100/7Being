"""Compatibility shim — Emotiv EegPipeline lives in ``7being-emotiv-epocx``."""

from __future__ import annotations

try:
    from sevenbeing_epocx.pipeline.eeg import (  # noqa: F401
        BRAIN_BANDS,
        BRAIN_LOBES,
        BRAIN_WINDOW,
        LOCK_PACKETS,
        EegPipeline,
        EegSample,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Emotiv EEG pipeline moved to package 7being-emotiv-epocx. "
        "Install with: pip install 7being-emotiv-epocx"
    ) from exc

__all__ = [
    "BRAIN_BANDS",
    "BRAIN_LOBES",
    "BRAIN_WINDOW",
    "LOCK_PACKETS",
    "EegPipeline",
    "EegSample",
]
