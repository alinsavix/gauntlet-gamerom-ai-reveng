"""Boot and one-time initialization -- WP-20.

Reference: ``doc/03_game_rom_structure.md`` §5, §2.2; ``book/05_boot_and_os.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def one_time_init(state: GameState) -> None:
    """0x4327A -- runs once, before the first frame ever starts.

    RAM initialization (default characters ``{0,1,2,3}``), timers, display
    setup, and palette init. Reached from ``game_start`` (0x4014C), which sets
    the initial colour pointers and tail-jumps into the loop.
    """
