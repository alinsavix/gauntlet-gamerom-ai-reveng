"""gauntpy -- a Python reimplementation of the Gauntlet II arcade game.

Not an emulator. The 68010 code is reimplemented at the logic level, keeping
the original's structure: the same main-loop call order, the same object model,
the same tables and thresholds. Graphics data is read from the original ROMs
via ``gex``; sound-board commands are modelled through a deterministic host log.

Built from the reverse-engineering documentation in ``../doc`` and ``../book``.
Names come from those documents: if the docs call it ``main_move_monsters`` or
``mob_state_link``, so do we. Every non-obvious constant carries a citation to
the section or ROM address it came from.
"""

from __future__ import annotations

from .constants import Character, GameMode, MazeObjIds, PlayerStatus
from .mainloop import g2mainloop, game_frame, tick
from .mob import MobTable
from .rng import GameRandom
from .state import GameState, Player

__version__ = "0.0.1"

__all__ = [
    "Character",
    "GameMode",
    "GameRandom",
    "GameState",
    "MazeObjIds",
    "MobTable",
    "Player",
    "PlayerStatus",
    "g2mainloop",
    "game_frame",
    "tick",
]
