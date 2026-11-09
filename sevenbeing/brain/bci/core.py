"""Shared runtime for profiles, calibration, mental training, and sessions."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .channels import ChannelHub, OutputHub, build_default_hub
from .devices.manager import DeviceManager
from .devices.montage import EPOCX_MONTAGE, Montage, closed_indices
from .devices.sites import coerce_assignments, default_reference
from .mental.calibrate import CalibrationResult, Calibrator
from .mental.control import ControlOutput, ControlRouter
from .mental.engine import MentalEngine, MentalPrediction, TrainState
from .store.profile import (
    Profile,
    create_profile,
    get_active_profile,
    list_profiles,
    load_profile,
    save_profile,
    set_active_id,
    to_public,
)
from .store.session import SessionRecorder


@dataclass
class AppCore:
    lock: threading.Lock = field(default_factory=threading.Lock)
    profile: Profile | None = None
    calibrator: Calibrator = field(default_factory=Calibrator)
    mental: MentalEngine = field(default_factory=MentalEngine)
    control: ControlRouter = field(default_factory=ControlRouter)
    channels: ChannelHub = field(default_factory=build_default_hub)
    recorder: SessionRecorder = field(default_factory=SessionRecorder)
    devices: DeviceManager = field(default_factory=DeviceManager)
    sample_rate: int = 128
    montage: Montage = field(default_factory=lambda: EPOCX_MONTAGE)
    last_mental: MentalPrediction | None = None
    last_control: ControlOutput = field(
        default_factory=lambda: ControlOutput("Neutral", "", "neutral", 0.0)
    )
    train_state: TrainState = field(default_factory=TrainState)

    @property
    def outputs(self) -> OutputHub:
        """Alias for ``channels`` — BCI control outputs (game / mqtt / …)."""
        return self.channels

    def boot(self) -> None:
        profile = get_active_profile()
        if profile is None:
            profiles = list_profiles()
            if profiles:
                profile = profiles[0]
                set_active_id(profile.id)
            else:
                profile = create_profile("Default", ["Neutral", "Push", "Left"])
                set_active_id(profile.id)
        self.load_profile(profile.id)

    def load_profile(self, profile_id: str) -> Profile:
        profile = load_profile(profile_id)
        set_active_id(profile.id)
        with self.lock:
            self.profile = profile
            self.mental = MentalEngine(
                actions=list(profile.actions),
                rate=self.sample_rate,
                n_ch=self.montage.n_channels,
            )
            self.calibrator = Calibrator(rate=self.sample_rate, n_ch=self.montage.n_channels)
            self.control = ControlRouter(
                keymap=profile.keymap,
                mental_threshold=profile.mental_threshold,
                debounce_ms=profile.debounce_ms,
            )
            if profile.has_calibration and profile.calib_path().exists():
                cal = Calibrator.load(profile.calib_path())
                self.mental.set_baseline(cal.mean, cal.std)
            if profile.has_model and profile.model_path().exists():
                self.mental.load(profile.model_path())
                self.mental.live_enabled = True
            self.train_state = TrainState()
            self.last_mental = None
        return profile

    def set_rate(self, rate: int) -> None:
        with self.lock:
            if rate == self.sample_rate:
                return
            self.sample_rate = rate
            self.montage = Montage(
                channels=self.montage.channels,
                sample_rate_hz=rate,
                units=self.montage.units,
            )
            self.calibrator.set_rate(rate)
            self.mental.set_rate(rate)

    def set_montage(self, montage: Montage, *, reset_model: bool = True) -> None:
        """Align mental / calibrate buffers to the live device channel count."""
        with self.lock:
            if (
                montage.n_channels == self.montage.n_channels
                and montage.channels == self.montage.channels
                and montage.sample_rate_hz == self.sample_rate
                and montage.reference == self.montage.reference
                and montage.closed == self.montage.closed
            ):
                return
            if (
                montage.n_channels == self.montage.n_channels
                and montage.channels == self.montage.channels
                and montage.sample_rate_hz == self.sample_rate
                and montage.reference == self.montage.reference
            ):
                self.montage = montage
                return
            self.montage = montage
            self.sample_rate = montage.sample_rate_hz
            self.calibrator.set_n_ch(montage.n_channels)
            self.calibrator.set_rate(montage.sample_rate_hz)
            self.mental.set_n_ch(montage.n_channels, reset=reset_model)
            self.mental.set_rate(montage.sample_rate_hz)

    def apply_electrode_map(
        self,
        assignments: list[str | None] | None = None,
        *,
        reference: str | None = None,
        closed: object = None,
        reset_model: bool = False,
    ) -> Montage:
        """Set per-channel site labels, reference, and which channels are off."""
        with self.lock:
            n = self.montage.n_channels
            labels = coerce_assignments(n, assignments, fill=True)
            ref = (reference or self.montage.reference or "CMS").strip() or "CMS"
            kept = self.montage.closed if closed is None else closed_indices(n, closed)
            montage = Montage(
                channels=tuple(labels),
                sample_rate_hz=self.montage.sample_rate_hz,
                units=self.montage.units,
                reference=ref,
                closed=kept,
            )
        self.set_montage(montage, reset_model=reset_model)
        return self.montage

    def reset_electrode_map(self) -> Montage:
        """Restore labels from the live device (Emotiv defaults) or count preset."""
        live = self.devices.primary()
        kind = None if live is None else getattr(live.info, "kind", None)
        if live is not None and live.connected:
            info = live.info
            rate = int(
                getattr(live, "sample_rate", None) or info.sample_rate_hz or self.sample_rate
            )
            self.set_montage(
                Montage(
                    channels=tuple(info.channels),
                    sample_rate_hz=rate,
                    units="uV",
                    reference=default_reference(str(kind) if kind else None),
                ),
                reset_model=False,
            )
            return self.montage
        n = self.montage.n_channels
        preset = Montage.for_count(n, sample_rate_hz=self.sample_rate)
        return self.apply_electrode_map(
            list(preset.channels),
            reference=default_reference(str(kind) if kind else None),
            reset_model=False,
        )

    def sync_primary_montage(self) -> bool:
        """Pull montage from DeviceManager primary; returns True if applied."""
        live = self.devices.primary()
        if live is None or not live.connected:
            return False
        info = live.info
        rate = int(getattr(live, "sample_rate", None) or info.sample_rate_hz or self.sample_rate)
        kind = getattr(info, "kind", None)
        n = len(tuple(info.channels))
        kept = self.montage.closed if self.montage.n_channels == n else ()
        self.set_montage(
            Montage(
                channels=info.channels,
                sample_rate_hz=rate,
                units="uV",
                reference=default_reference(str(kind) if kind else None),
                closed=tuple(i for i in kept if i < n),
            ),
            reset_model=True,
        )
        return True

    def public_state(self) -> dict:
        with self.lock:
            profile = None if self.profile is None else to_public(self.profile)
            mental = None
            if self.last_mental is not None:
                mental = {
                    "label": self.last_mental.label,
                    "confidence": round(self.last_mental.confidence, 3),
                    "scores": {k: round(v, 3) for k, v in self.last_mental.scores.items()},
                }
            ctrl = self.last_control
            train = {
                "action": self.train_state.action,
                "phase": self.train_state.phase,
                "trial": self.train_state.trial,
                "trials_total": self.train_state.trials_total,
                "progress": round(self.train_state.progress, 3),
                "message": self.train_state.message,
            }
            return {
                "profile": profile,
                "profiles": [to_public(p) for p in list_profiles()],
                "calib": {
                    "active": self.calibrator.active,
                    "progress": round(self.calibrator.progress(), 3),
                },
                "train": train,
                "train_bank": self.mental.train_bank(),
                "train_last_completed": self.mental.last_completed,
                "mental": mental,
                "mental_live": self.mental.live_enabled,
                "cv_accuracy": self.mental.last_cv,
                "control": {
                    "name": ctrl.name,
                    "key": ctrl.key,
                    "source": ctrl.source,
                    "confidence": round(ctrl.confidence, 3),
                },
                "channels": self.channels.public_state(),
                "outputs": self.channels.public_state(),
                "session": {
                    "active": self.recorder.active,
                    "path": None if self.recorder.path is None else str(self.recorder.path),
                    "rows": self.recorder.rows,
                },
                "montage": self.montage.to_public(),
                "devices": self.devices.public_state(),
                "train_actions": [
                    a
                    for a in (
                        "Neutral",
                        "Push",
                        "Pull",
                        "Lift",
                        "Drop",
                        "Left",
                        "Right",
                    )
                ],
            }

    def _commit_calibration(self, finished: CalibrationResult | None) -> bool:
        """Persist baseline when calib finishes. Caller must hold ``self.lock``."""
        if finished is None or self.profile is None:
            return False
        self.mental.set_baseline(finished.mean, finished.std)
        self.calibrator.save(self.profile.calib_path())
        self.profile.has_calibration = True
        save_profile(self.profile)
        return True

    def tick_calibration(self) -> bool:
        """Wall-clock calib poll — unblocks UI if BLE samples stall near 100%."""
        with self.lock:
            finished = self.calibrator.tick()
            return self._commit_calibration(finished)

    def on_sample(
        self,
        values: list[float],
        face: list[float],
        affect: list[float] | None,
        band_power: object | None = None,
        *,
        shared_bands: bool = False,
    ) -> ControlOutput:
        with self.lock:
            finished = self.calibrator.push(
                values, band_power=band_power, shared_bands=shared_bands
            )
            self._commit_calibration(finished)

            pred = self.mental.push_sample(
                values, band_power=band_power, shared_bands=shared_bands
            )
            # Always sync — block completion resets phase to idle and must publish.
            self.train_state = self.mental.train
            if pred is not None:
                self.last_mental = pred
            out = self.control.resolve(self.last_mental if self.mental.live_enabled else None, face)
            self.last_control = out
            self.channels.dispatch(out)
            if self.recorder.active:
                self.recorder.write_sample(
                    values,
                    mental=None if self.last_mental is None else self.last_mental.label,
                    conf=None if self.last_mental is None else self.last_mental.confidence,
                    face=face,
                    affect=affect,
                    command=out.name,
                    source=out.source,
                )
            return out


CORE = AppCore()
