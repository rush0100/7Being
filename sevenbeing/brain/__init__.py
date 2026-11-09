"""01 Brain — EEG and neural activity.

Subsystems:
- ``bci`` — brain–computer interface (mental commands, device plugins, live EEG GUI)
"""

from __future__ import annotations

from . import bci

CODE = "01"
NAME = "brain"
TITLE = "Brain"
BLURB = "EEG and neural activity"

__all__ = ["CODE", "NAME", "TITLE", "BLURB", "bci"]
