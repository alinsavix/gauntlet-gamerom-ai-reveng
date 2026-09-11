"""Shared level-state predicates and the ROM active-party count."""

from __future__ import annotations

from ..constants import PlayerStatus
from ..state import GameState
from .level_data import _SECRET_MAZE_FIRST, _TREASURE_MAZE_FIRST


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def player_activecount(state: GameState) -> int:
    """0x4D900 ``player_activecount`` -- players with status 1, 2, 8 or 0x10.

    Reference: doc/04_game_subsystems.md §16; PlayerStatus values 1/2/8/0x10
    = ALIVE_HERE / ALIVE_NEXT / RESPAWN_WAIT / SELECTING.
    """
    active_statuses = (
        int(PlayerStatus.ALIVE_HERE),
        int(PlayerStatus.ALIVE_NEXT),
        int(PlayerStatus.RESPAWN_WAIT),
        int(PlayerStatus.SELECTING),
    )
    return sum(1 for p in state.players if p.status in active_statuses)


def in_bonus_room(state: GameState) -> bool:
    """True in any bonus room -- treasure (104-114) or secret (115/116).

    This is the ROM's own test, ``cmpi.w #0x68,mazenum_current`` followed by a
    carry-clear branch, used at 0x4D2D0, 0x4A756, 0x52DBA and 0x52E56.
    """
    return state.mazenum_current >= _TREASURE_MAZE_FIRST


def in_secret_room(state: GameState) -> bool:
    """True in a secret room (maze 115 or 116) -- ``cmpi.w #0x73`` at 0x48232,
    0x43916, 0x4D496, 0x4D544 and 0x4D8CA."""
    return state.mazenum_current >= _SECRET_MAZE_FIRST
