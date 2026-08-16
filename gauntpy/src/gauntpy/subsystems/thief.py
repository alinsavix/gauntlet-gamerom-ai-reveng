"""The thief and mugger -- WP-10.

Reference: ``doc/04_game_subsystems.md`` §9, §23.4;
``doc/generated/thief_secret_contracts.csv``;
``book/12_dragon_thief_mugger.md``.

Open question: the thief-mode enum names are unverified -- no thief appeared in
the bounded level-1 attract corpus. Implement from disassembly and flag any
guess in a comment rather than inventing a confident name.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_thief_anim(state: GameState) -> None:
    """0x4E8DC -- thief state machine and animation.

    The thief uses the **high nibble** of the direction grid (0x905054) for its
    private pathing; ordinary movement uses the low nibble.
    """


@stub
def main_start_thief(state: GameState) -> None:
    """0x4DEB8 -- per-frame check on whether the thief should enter.

    Scheduling (``thief_setup``, 0x4E432) gates on: ``game_mode`` non-negative,
    maze below 0x73, level at least 6, and ``getrandom(8) < level >> 3``.
    Targeting (``thief_target_calc``, 0x4DFF6) picks the wealthiest player by
    the weighted formula in §4.7.
    """
