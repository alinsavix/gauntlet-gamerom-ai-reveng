"""EEPROM persistence and operator configuration -- WP-19.

The options word (0x904A24) matters even though the operator menus do not:
bits 5-7 are the operator-facing "Game Difficulty", whose principal gameplay
effect is generator spawn probability, and bits 8-9 are coins to start.

Reference: ``doc/04_game_subsystems.md`` §20; ``doc/02_os_rom.md`` (EEPROM
codec and redundant-block format); ``nvram/`` for the real layout.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def eeprom_periodic_write(state: GameState) -> None:
    """0x431EE -- periodic write timer for the EEPROM shadow."""
