"""BCI channel · Custom — user-defined adapters."""

from __future__ import annotations

from .sink import CustomSink

CODE = "06"
NAME = "custom"
TITLE = "Custom"
BLURB = "User-defined adapters and hooks"
STATUS = "shipping"

__all__ = [
    "BLURB",
    "CODE",
    "CustomSink",
    "NAME",
    "STATUS",
    "TITLE",
]
