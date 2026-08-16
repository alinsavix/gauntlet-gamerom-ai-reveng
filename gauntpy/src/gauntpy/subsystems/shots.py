"""Projectiles and hit resolution -- WP-7.

Twelve fixed channels: player shots in slots 1-4, demon 5-8, lobber 9-12. Fixed
slots mean no allocation and no search -- that is the design, not an
optimization to add later.

Reference: ``doc/04_game_subsystems.md`` §26, §3.6;
``doc/generated/monster_combat_contracts.csv``; ``book/11_monsters.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_handle_shots(state: GameState) -> None:
    """0x474F6 -- advance the 12 projectile slots.

    Class-specific motion, animation and lifetime, collision, and removal.
    Collisions resolve through ``resolve_shot_hit`` (0x4AF50), whose 62-entry
    computed dispatch is naturally a dict keyed by object type.

    Monster health is the target's own **hpos low nibble**: subtract damage
    from it, and if the nibble leaves ``[base - 2, base]`` from
    ``mazeobj_hsize_tier_tbl`` (0x5864C) the monster dies; otherwise it
    survives as a weaker tier.
    """
