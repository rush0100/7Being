"""BCI channel · Game — mental-command keymap / game control out."""

from __future__ import annotations

from .sink import GameEvent, GameSink

CODE = "01"
NAME = "game"
TITLE = "Game"
BLURB = "Mental-command keymap / game control out"
STATUS = "shipping"

__all__ = [
    "BLURB",
    "CODE",
    "GameEvent",
    "GameSink",
    "NAME",
    "STATUS",
    "TITLE",
]
