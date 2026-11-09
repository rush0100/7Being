"""7Being pillars — product map (01–07)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PillarInfo:
    code: str
    name: str
    title: str
    blurb: str


class Pillar(str, Enum):
    BRAIN = "brain"
    BODY = "body"
    BREATH = "breath"
    EMOTION = "emotion"
    ATTENTION = "attention"
    ENVIRONMENT = "environment"
    BEING = "being"


PILLARS: tuple[PillarInfo, ...] = (
    PillarInfo("01", "brain", "Brain", "EEG and neural activity"),
    PillarInfo("02", "body", "Body", "Heart rate and HRV"),
    PillarInfo("03", "breath", "Breath", "Respiration and rhythm"),
    PillarInfo("04", "emotion", "Emotion", "Affective state"),
    PillarInfo("05", "attention", "Attention", "Focus and cognition"),
    PillarInfo("06", "environment", "Environment", "Context and surroundings"),
    PillarInfo("07", "being", "Being", "Personalized wellbeing"),
)


def pillar_by_name(name: str) -> PillarInfo | None:
    key = name.strip().lower()
    for item in PILLARS:
        if item.name == key or item.code == key or item.title.lower() == key:
            return item
    return None
