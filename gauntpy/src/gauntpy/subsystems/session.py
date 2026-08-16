"""Coins, credits, character select, and session start -- WP-16.

Reference: ``doc/04_game_subsystems.md`` §10.1, §22, §6.4;
``book/07_session_lifecycle.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def coincheck(state: GameState) -> None:
    """0x42B6A -- coin detection, credit accounting, and coin-for-health.

    Coins inserted for an already-active player add health from the table at
    0x57862 indexed by ``game_settings & 0x1F``. A coin arriving during attract
    can begin a session at any point -- it consults no lockout threshold.
    """


@stub
def character_select_input_update(state: GameState) -> None:
    """0x42DF4 -- character selection input. See §22."""


@stub
def main_start_game(state: GameState) -> None:
    """0x4800C -- turn a credited player into a hero in the maze.

    The start/join/character-commit press is on the **Magic** line, matching
    ``(debounce_shift_magic & 0x1F) == 0x1C`` at 0x48402-0x48416. It is not
    Fire; that was a documented correction. Use ``input.magic_press_edge``.
    """
