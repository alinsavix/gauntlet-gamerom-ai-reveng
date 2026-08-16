"""Exits, treasure rooms, and secret rooms -- WP-15.

Reference: ``doc/04_game_subsystems.md`` §12, §16, §10.6;
``doc/06_maze_catalog.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_treasure_timer(state: GameState) -> None:
    """0x4D29E -- treasure-room countdown, speech, timeout, bonus transition."""


@stub
def main_exit_move(state: GameState) -> None:
    """0x5287C -- the moving exit (LFLAG3 bit 14) and exit animation.

    Exit animations use the fixed MOB slots 21-24. The fake exit is LFLAG4
    bit 6; ``EXITTO6`` is a distinct object type from ``EXIT``.
    """
