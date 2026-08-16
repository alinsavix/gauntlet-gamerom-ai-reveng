"""The camera -- WP-13.

Reference: ``doc/04_game_subsystems.md`` §17; ``book/08_world_in_memory.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_scroll_playfield(state: GameState) -> None:
    """0x46CAA -- move the shared camera toward the party.

    Bounding extent of the active players (honouring wraparound), the +/-0xC8
    rubber band so one adventurous player cannot yank the camera away from
    three cooperating ones, a target at the midpoint offset so the maze
    viewport centres rather than the full screen, 2 px per axis per frame with
    a snap when close, then ``scroll_set_position`` clamps.
    """
