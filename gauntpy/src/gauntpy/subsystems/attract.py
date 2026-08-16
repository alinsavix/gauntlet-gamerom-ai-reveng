"""Attract mode, demo playback, and logo colour cycling -- WP-17.

Demo playback is the engine running on recorded inputs: the same
``main_move_players`` path, fed from per-player streams of ``[timer, joystick]``
pairs, with ``0xFF`` = speech and ``0xFE`` = player switch / end of sequence.
Demo joystick bytes are active low, like the hardware.

Reference: ``doc/04_game_subsystems.md`` §6 (all), §14.3;
``doc/generated/startup_attract_contracts.csv``; ``book/15_attract_and_demo.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_logo_updcolors(state: GameState) -> None:
    """0x4DCBA -- palette-driven colour animation, title logo effects included."""


@stub
def main_attract(state: GameState) -> None:
    """0x44562 -- the attract state machine.

    Four screens (SCORES -1, TITLE -2, DEMO -3, LEGEND -4) with their timers,
    and five input-test blocks that restart an *attract screen* rather than
    starting a session. The one-second input lockout (thresholds are exactly 60
    frames below each loaded timer) gates **screen switching only**.
    """
