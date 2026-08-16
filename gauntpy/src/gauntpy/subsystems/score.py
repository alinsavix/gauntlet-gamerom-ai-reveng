"""Scoring, HUD, and dialogs -- WP-14.

Reference: ``doc/04_game_subsystems.md`` §10, §14, §25;
``doc/generated/score_coin_dialog_contracts.csv``;
``book/14_score_and_economics.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_msgbox_countdown(state: GameState) -> None:
    """0x4CCBC -- decrement ``dialog_timer`` and erase the box at zero.

    This is the call that releases the gate in ``game_frame``. A value of 1 is
    also used to force immediate cleanup during screen transitions.
    """


@stub
def main_score_update(state: GameState) -> None:
    """0x4715E -- three indexed loops plus the thief/effect transition pass.

    Popup timers, per-player transition MOBs, and the four
    ``mob_effect_anim_counter`` bytes. Projectile movement is **not** here; it
    is ``main_handle_shots``, an independent top-level call.
    """


@stub
def main_score_display(state: GameState) -> None:
    """0x457C0 -- render scores and the info panel. See §14."""
