"""Monsters and generators -- WP-8.

Reference: ``doc/04_game_subsystems.md`` §3 (all of it);
``doc/generated/monster_combat_contracts.csv``; ``book/11_monsters.md``.

Key facts for whoever implements this, all of which are easy to get backwards:

- ``monsters_everything`` walks the chain from ``monster_iter_ptr`` (0x904A60),
  which rotates the entry point each frame so no creature is permanently first.
  The walk runs to completion; it never leaves monsters unprocessed.
- There is **no jump table**. One shared handler (0x4119A) with branches.
- ``D6`` in the original is ``monster_index * 4``, **not** an object type.
- ``monster_slowmo_timer`` skips the entire pass on even frames -- it is a
  global effect on monsters, not a player debuff.
- Generators are throttled by ``frame_overflow``, which zeroes their spawn
  probability; it does not cap how many monsters are processed.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_move_monsters(state: GameState) -> None:
    """0x49034 -- advance every monster and generator by one frame.

    Calls ``monsters_everything`` (0x40E6A), which builds the seven-longword
    per-family speed configuration, applies the slow-motion gate, and walks the
    depth chain dispatching each object.
    """
