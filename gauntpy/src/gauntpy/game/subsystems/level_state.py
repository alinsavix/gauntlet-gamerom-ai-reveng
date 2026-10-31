"""Shared level-state predicates and the ROM active-party count."""

from __future__ import annotations

from ..constants import PlayerStatus
from ..state import GameState
from .level_data import _SECRET_MAZE_FIRST, _TREASURE_MAZE_FIRST


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# ROM: direct game:0x4D900 | Counts exactly statuses 1, 2, 8 and 0x10, unlike GameState's ALIVE_HERE-only convenience properties.
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


# ROM: part game:0x4D29E,game:0x4A53A,game:0x52B40 | Parameterized shared inline maze>=104 predicate at the documented timer, mover and exit-sequence sites; no separate ROM callable.
def in_bonus_room(state: GameState) -> bool:
    """True in any bonus room -- treasure (104-114) or secret (115/116).

    This is the ROM's own test, ``cmpi.w #0x68,mazenum_current`` followed by a
    carry-clear branch, used at 0x4D2D0, 0x4A756, 0x52DBA and 0x52E56.
    """
    return state.mazenum_current >= _TREASURE_MAZE_FIRST


# ROM: part game:0x4800C,game:0x438AE,game:0x4D476 | Parameterized shared inline maze>=115 predicate from startup, setup and bonus branches; not an entry at any cited comparison instruction.
def in_secret_room(state: GameState) -> bool:
    """True in a secret room (maze 115 or 116) -- ``cmpi.w #0x73`` at 0x48232,
    0x43916, 0x4D496, 0x4D544 and 0x4D8CA."""
    return state.mazenum_current >= _SECRET_MAZE_FIRST
