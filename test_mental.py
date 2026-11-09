#!/usr/bin/env python3
"""Unit checks for mental / calibrate / control / session pieces."""

from __future__ import annotations

import math
import tempfile
import time
from pathlib import Path

import numpy as np

from sevenbeing.mental.calibrate import Calibrator
from sevenbeing.mental.control import ControlRouter
from sevenbeing.mental.engine import MentalEngine, MentalPrediction
from sevenbeing.mental.features import FEAT_DIM, FeatureExtractor
from sevenbeing.store import profile as profile_mod
from sevenbeing.store import session as session_mod
from sevenbeing.store.profile import create_profile, load_profile, save_profile, safe_profile_id
from sevenbeing.store.session import SessionRecorder


def _frame(t: float = 0.0, bias: float = 0.0) -> list[float]:
    return [math.sin(t + i * 0.3) * 20.0 + bias for i in range(14)]


def test_features_and_calibrate() -> None:
    fx = FeatureExtractor(rate=128)
    got = None
    for i in range(400):
        out = fx.push(_frame(i / 128))
        if out is not None:
            got = out
    assert got is not None
    assert got.shape == (FEAT_DIM,)

    cal = Calibrator(rate=128, duration_s=0.15)
    cal.start()
    # Monkey-patch clock so duration completes without long sleeps.
    t0 = time.monotonic()
    cal._t0 = t0 - 1.0
    for i in range(800):
        cal.push(_frame(i / 128))
        if cal.result is not None:
            break
    assert cal.result is not None
    assert cal.result.mean.shape == (FEAT_DIM,)


def test_mental_fit_predict() -> None:
    engine = MentalEngine(actions=["Neutral", "Push"], rate=128)
    engine.set_baseline(np.zeros(FEAT_DIM), np.ones(FEAT_DIM))
    # Inject labeled feature rows directly (skip long cue wall-clock).
    rng = np.random.default_rng(0)
    for label, offset in (("Neutral", 0.0), ("Push", 3.0)):
        for _ in range(24):
            row = rng.normal(size=FEAT_DIM) + offset
            engine._X.append(row.astype(np.float64))
            engine._y.append(label)
    info = engine.fit()
    assert info["n_samples"] >= 8
    assert engine.model is not None
    pred = engine.predict(np.ones(FEAT_DIM) * 3.0)
    assert isinstance(pred, MentalPrediction)
    assert pred.label in ("Neutral", "Push")


def test_control_router() -> None:
    router = ControlRouter(mental_threshold=0.2, debounce_ms=0)
    out = router.resolve(MentalPrediction("Push", 0.9, {"Push": 0.9}), [0] * 5)
    assert out.name == "Push"
    assert out.source == "mental"
    weak = router.resolve(MentalPrediction("Push", 0.05, {"Push": 0.05}), [1, 0, 0, 0, 0])
    assert weak.source in ("face", "neutral", "mental")


def test_profile_and_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        profile_mod.ROOT = root
        profile_mod.PROFILES = root / "profiles"
        profile_mod.SESSIONS = root / "sessions"
        session_mod.SESSIONS = root / "sessions"
        profile_mod.ensure_dirs()

        p = create_profile("Unit", ["Neutral", "Push"])
        loaded = load_profile(p.id)
        assert loaded.name == "Unit"
        loaded.actions.append("Left")
        save_profile(loaded)
        assert "Left" in load_profile(p.id).actions

        rec = SessionRecorder()
        path = rec.start(p.id)
        rec.mark("ping", {"n": 1})
        rec.stop()
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()

        for bad in ("../etc", "..", "a/b", "a\\b", "", "../../tmp"):
            try:
                safe_profile_id(bad)
            except ValueError:
                continue
            raise AssertionError(f"expected reject {bad!r}")
        assert safe_profile_id(p.id) == p.id


if __name__ == "__main__":
    test_features_and_calibrate()
    test_mental_fit_predict()
    test_control_router()
    test_profile_and_session()
    print("mental/mvp tests passed")
