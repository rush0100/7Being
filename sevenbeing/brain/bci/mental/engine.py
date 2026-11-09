"""Cue-based mental-command training and live LDA classification."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import joblib
import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import RidgeClassifier
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import FeatureExtractor, normalize_features

TRIAL_CUE_S = 2.5
TRIAL_REST_S = 1.0
TRIALS_PER_ACTION = 8
MIN_CV = 0.55

# Keep in sync with store.profile.ACTIONS (avoid circular import at module load).
TRAIN_ACTIONS = ("Neutral", "Push", "Pull", "Lift", "Drop", "Left", "Right")
MAX_ACTIONS = 7  # Neutral + up to 6 motion commands


@dataclass
class MentalPrediction:
    label: str
    confidence: float
    scores: dict[str, float]


@dataclass
class TrainState:
    action: str = ""
    phase: str = "idle"  # idle | cue | rest | done
    trial: int = 0
    trials_total: int = TRIALS_PER_ACTION
    progress: float = 0.0
    message: str = ""


@dataclass
class MentalEngine:
    actions: list[str] = field(default_factory=lambda: ["Neutral", "Push", "Left"])
    rate: int = 128
    n_ch: int = 14
    mean: np.ndarray | None = None
    std: np.ndarray | None = None

    def __post_init__(self) -> None:
        self.extractor = FeatureExtractor(self.rate, n_ch=self.n_ch)
        self.model: object | None = None
        self.classes_: list[str] = list(self.actions)
        self._X: list[np.ndarray] = []
        self._y: list[str] = []
        self._blocks_done: dict[str, int] = {}
        self.last_completed: str | None = None
        self.train = TrainState()
        self._phase_t0 = 0.0
        self._collecting = False
        self.last_cv: float | None = None
        self.live_enabled = False

    def set_rate(self, rate: int) -> None:
        self.rate = int(rate) if rate > 0 else 128
        self.extractor.set_rate(self.rate)

    def set_n_ch(self, n_ch: int, *, reset: bool = True) -> None:
        n = max(1, int(n_ch))
        if n == self.n_ch:
            return
        self.n_ch = n
        self.extractor.set_n_ch(n)
        if not reset:
            return
        # Model/baseline belong to the previous montage — clear on switch.
        self.model = None
        self.mean = None
        self.std = None
        self.live_enabled = False
        self.clear_trials()

    def set_baseline(self, mean: np.ndarray, std: np.ndarray) -> None:
        self.mean = np.asarray(mean, dtype=np.float64)
        self.std = np.maximum(np.asarray(std, dtype=np.float64), 1e-3)

    def set_actions(self, actions: list[str]) -> None:
        cleaned = [a for a in actions if a in TRAIN_ACTIONS]
        if "Neutral" not in cleaned:
            cleaned = ["Neutral", *cleaned]
        self.actions = cleaned[:MAX_ACTIONS]
        self.classes_ = list(self.actions)

    def ensure_action(self, action: str) -> None:
        """Allow training any catalog action; grow profile set up to MAX_ACTIONS."""
        if action not in TRAIN_ACTIONS:
            raise ValueError(f"unknown action {action}")
        if action in self.actions:
            return
        if len(self.actions) >= MAX_ACTIONS:
            # Replace last non-Neutral slot so training can proceed.
            rest = [a for a in self.actions if a != "Neutral"]
            if not rest:
                self.set_actions(["Neutral", action])
                return
            rest[-1] = action
            self.set_actions(["Neutral", *rest])
            return
        self.set_actions([*self.actions, action])

    def clear_trials(self) -> None:
        self._X = []
        self._y = []
        self._blocks_done = {}
        self.last_completed = None
        self.train = TrainState()
        self._collecting = False

    def train_bank(self) -> list[dict]:
        """Classes already collected this session (for Studio 'เก็บแล้ว' list)."""
        from collections import Counter

        counts = Counter(self._y)
        ordered = [
            a
            for a in ("Neutral", "Push", "Pull", "Lift", "Drop", "Left", "Right")
            if counts.get(a, 0) > 0 or self._blocks_done.get(a, 0) > 0
        ]
        return [
            {
                "action": a,
                "samples": int(counts.get(a, 0)),
                "blocks": int(self._blocks_done.get(a, 0)),
            }
            for a in ordered
        ]

    def start_action_block(self, action: str) -> TrainState:
        self.ensure_action(action)
        self.last_completed = None
        self.train = TrainState(
            action=action,
            phase="cue",
            trial=1,
            trials_total=TRIALS_PER_ACTION,
            progress=0.0,
            message=f"คิดตาม · {action}",
        )
        self._phase_t0 = time.monotonic()
        self._collecting = True
        return self.train

    def stop_training(self) -> TrainState:
        self._collecting = False
        self.train.phase = "idle"
        self.train.message = "หยุดฝึก"
        return self.train

    def _advance_train(self) -> None:
        if not self._collecting or self.train.phase in ("idle", "done"):
            return
        elapsed = time.monotonic() - self._phase_t0
        if self.train.phase == "cue":
            self.train.progress = min(1.0, elapsed / TRIAL_CUE_S)
            self.train.message = (
                f"คิดตาม {self.train.action} · รอบ {self.train.trial}/{self.train.trials_total}"
            )
            if elapsed >= TRIAL_CUE_S:
                self.train.phase = "rest"
                self.train.progress = 0.0
                self._phase_t0 = time.monotonic()
                self.train.message = "พัก — ว่างใจ"
        elif self.train.phase == "rest":
            self.train.progress = min(1.0, elapsed / TRIAL_REST_S)
            if elapsed >= TRIAL_REST_S:
                if self.train.trial >= self.train.trials_total:
                    done_action = self.train.action
                    self._blocks_done[done_action] = self._blocks_done.get(done_action, 0) + 1
                    self.last_completed = done_action
                    self._collecting = False
                    # Drop the cue panel — class moves into train_bank list.
                    self.train = TrainState(
                        action=done_action,
                        phase="idle",
                        trial=TRIALS_PER_ACTION,
                        trials_total=TRIALS_PER_ACTION,
                        progress=1.0,
                        message=f"ครบ {done_action} — เลือกคำสั่งถัดไปได้",
                    )
                else:
                    self.train.trial += 1
                    self.train.phase = "cue"
                    self.train.progress = 0.0
                    self._phase_t0 = time.monotonic()
                    self.train.message = f"คิดตาม {self.train.action}"

    def push_sample(
        self,
        values: list[float],
        band_power: object | None = None,
        *,
        shared_bands: bool = False,
    ) -> MentalPrediction | None:
        # shared_bands: GUI already ran BandPowerEngine — only take hops.
        if shared_bands:
            feat = None if band_power is None else self.extractor.from_powers(band_power)  # type: ignore[arg-type]
        elif band_power is not None:
            feat = self.extractor.from_powers(band_power)  # type: ignore[arg-type]
        else:
            feat = self.extractor.push(values)
        self._advance_train()
        if feat is None:
            return None
        normed = normalize_features(feat, self.mean, self.std)
        if self._collecting and self.train.phase == "cue":
            self._X.append(normed.copy())
            self._y.append(self.train.action)
        if self.live_enabled and self.model is not None:
            return self.predict(normed)
        return None

    def fit(self) -> dict:
        if len(self._X) < 8:
            raise RuntimeError("ข้อมูลฝึกไม่พอ — เก็บอย่างน้อยหนึ่ง action แบบเต็มบล็อก")
        labels = sorted(set(self._y))
        if len(labels) < 2:
            raise RuntimeError("ต้องมีอย่างน้อย 2 คลาส")
        X = np.stack(self._X, axis=0)
        y = np.asarray(self._y)
        counts = {lab: int(np.sum(y == lab)) for lab in labels}
        if min(counts.values()) < 2:
            raise RuntimeError(f"แต่ละคลาสต้องมีอย่างน้อย 2 เฟรม: {counts}")

        # Prefer LDA; fall back to Ridge if class count / singularity issues.
        try:
            pipe: object = Pipeline(
                [
                    ("scaler", StandardScaler()),
                    ("clf", LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
                ]
            )
            n_splits = min(5, min(counts.values()))
            if n_splits >= 2:
                scores = cross_val_score(pipe, X, y, cv=n_splits)
                cv_acc = float(scores.mean())
            else:
                cv_acc = 0.0
            pipe.fit(X, y)
        except Exception:
            pipe = Pipeline(
                [
                    ("scaler", StandardScaler()),
                    ("clf", RidgeClassifier(alpha=1.0)),
                ]
            )
            n_splits = min(5, min(counts.values()))
            scores = cross_val_score(pipe, X, y, cv=max(2, n_splits))
            cv_acc = float(scores.mean())
            pipe.fit(X, y)

        self.model = pipe
        self.classes_ = list(getattr(pipe.named_steps["clf"], "classes_", labels))
        self.last_cv = cv_acc
        return {
            "cv_accuracy": cv_acc,
            "n_samples": int(len(y)),
            "counts": counts,
            "classes": list(self.classes_),
            "ready": cv_acc >= MIN_CV,
            "warn": cv_acc < MIN_CV,
        }

    def predict(self, feat: np.ndarray) -> MentalPrediction:
        if self.model is None:
            return MentalPrediction("Neutral", 0.0, {})
        clf = self.model
        proba = None
        if hasattr(clf, "predict_proba"):
            proba = clf.predict_proba(feat.reshape(1, -1))[0]
            classes = list(clf.classes_)
        else:
            # Pipeline with RidgeClassifier: use decision_function
            step = clf.named_steps["clf"] if hasattr(clf, "named_steps") else clf
            classes = list(getattr(step, "classes_", self.classes_))
            if hasattr(clf, "decision_function"):
                raw = np.asarray(clf.decision_function(feat.reshape(1, -1)), dtype=np.float64)
                if raw.ndim == 1:
                    # binary: map to two-class softmax-ish
                    if len(classes) == 2:
                        s = 1.0 / (1.0 + np.exp(-raw[0]))
                        proba = np.asarray([1.0 - s, s], dtype=np.float64)
                    else:
                        proba = np.ones(len(classes)) / len(classes)
                else:
                    ex = np.exp(raw[0] - raw[0].max())
                    proba = ex / ex.sum()
            else:
                label = str(clf.predict(feat.reshape(1, -1))[0])
                scores = {c: 0.0 for c in classes}
                scores[label] = 1.0
                return MentalPrediction(label, 1.0, scores)

        scores = {str(c): float(p) for c, p in zip(classes, proba)}
        best_i = int(np.argmax(proba))
        return MentalPrediction(str(classes[best_i]), float(proba[best_i]), scores)

    def save(self, path) -> None:
        if self.model is None:
            raise RuntimeError("no model")
        joblib.dump(
            {
                "model": self.model,
                "classes": self.classes_,
                "actions": self.actions,
                "mean": self.mean,
                "std": self.std,
                "cv": self.last_cv,
                "feat_dim": self.extractor.feat_dim,
                "n_ch": self.n_ch,
            },
            path,
        )

    def load(self, path) -> None:
        from pathlib import Path

        from ..store.profile import PROFILES

        resolved = Path(path).resolve()
        root = PROFILES.resolve()
        if root not in resolved.parents:
            raise ValueError("model path outside profile store")
        if resolved.suffix != ".joblib" or resolved.name != "mental.joblib":
            raise ValueError("refusing to load unexpected model file")
        blob = joblib.load(resolved)
        n_ch = int(blob.get("n_ch") or self.n_ch)
        self.set_n_ch(n_ch, reset=False)
        self.model = blob["model"]
        self.classes_ = list(blob.get("classes") or [])
        self.actions = list(blob.get("actions") or self.classes_)
        mean = blob.get("mean")
        std = blob.get("std")
        self.mean = None if mean is None else np.asarray(mean, dtype=np.float64)
        self.std = None if std is None else np.asarray(std, dtype=np.float64)
        self.last_cv = blob.get("cv")
        self.live_enabled = self.model is not None
