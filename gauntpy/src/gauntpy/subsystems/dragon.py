"""The dragon -- WP-9.

Reference: ``doc/04_game_subsystems.md`` §8;
``doc/generated/dragon_thief_exit_contracts.csv``;
``book/12_dragon_thief_mugger.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_handle_dragon(state: GameState) -> None:
    """0x54454 -- dragon state machine, movement, attacks, and path following.

    The dragon occupies a 2-cell stride at decode time (gex's ``expand`` steps
    by 2 for ``MONST_DRAGON``). Its path system is fully decoded; see §8.3.
    """
