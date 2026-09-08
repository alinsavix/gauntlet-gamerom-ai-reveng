"""Shared game-side playfield replacement, not host rendering.

pf_replace (0x5F31E) couples logical maze, MOB, and native playfield writes.
Projectile collisions and player transporter landings call this same owner.
"""

from __future__ import annotations

from .constants import MazeObjIds
from .state import GameState


def pf_replace(state: GameState, slot: int, obj_type: int) -> None:
    """``pf_replace`` (0x5F31E) -- retile a maze cell in place.

    Replacing with floor takes the ROM's three-way branch at 0x5F352: a static
    tile marker (picture 0x8000/0x8001) only loses its picture and type, so the
    cell keeps the H/V words a following ``shot_impact_spawn`` reads back; a
    real MOB goes through ``mob_free``; an empty cell is left alone.  Stamping
    a new type uses ``maze._place_one``, the port's single reviewed copy of the
    ROM's tile write, which unlinks the previous occupant exactly as
    ``mob_place_tile`` (0x5F310) does.
    """
    if obj_type != int(MazeObjIds.TILE_FLOOR):
        from .maze import _place_one, set_cell_descriptor

        _place_one(state, slot, obj_type)
        set_cell_descriptor(state, slot, obj_type)
        return

    from .maze import clear_cell_descriptor

    clear_cell_descriptor(state, slot)
    picture = state.mobs.picture[slot]
    if picture in (0x8000, 0x8001):
        hpos = state.mobs.hpos[slot]
        vpos = state.mobs.vpos[slot]
        state.mobs.unlink_and_clear(slot)
        state.mobs.hpos[slot] = hpos
        state.mobs.vpos[slot] = vpos
    elif picture:
        state.mobs.unlink_and_clear(slot)
