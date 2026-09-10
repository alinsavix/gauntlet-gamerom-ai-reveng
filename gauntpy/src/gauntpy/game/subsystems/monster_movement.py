"""Monster ray marches, native-word movement, and MOB record handoff."""

from __future__ import annotations

from ..constants import MazeObjIds
from ..coords import POS_SHIFT, mob_cell_of
from ..state import GameState
from .monster_data import (
    _BLANK_PICTURE as _BLANK_PICTURE,
    _HPOS_FLAG_ATTACK as _HPOS_FLAG_ATTACK,
    _HPOS_FLAG_MOVING as _HPOS_FLAG_MOVING,
    _MONSTER_ODDANGLE_TABLE as _MONSTER_ODDANGLE_TABLE,
    _OVERLAP as _OVERLAP,
    _SOFTWARE_MOB_BIAS as _SOFTWARE_MOB_BIAS,
)

#: 0x41484 -- extra counter bump applied when entering the blink state.
_BLINK_ANIM_BUMP = 0x60
#: 0x5E112 / 0x5E1DE -- the vertical edge guards, on the V word itself: a march
#: towards row 0 stops unless the word is at or below 0xF080, and a march
#: towards row 31 stops once the word has gone negative through the floor.
_EDGE_TOP_LIMIT = 0xF080

# Probe descriptors: (row step, column step) of the cell straight ahead, and
# the axis the two flanking cells are taken along.
_PROBE_UP = (-1, 0)
_PROBE_DOWN = (1, 0)
_PROBE_LEFT = (0, -1)
_PROBE_RIGHT = (0, 1)


def _cell_at(row: int, col: int) -> int:
    """Slot of a maze cell; the column wraps inside its row (``andi #0x3E``)."""
    return ((row & 0x1F) << 5) | (col & 0x1F)


def _march_cell_blocks(state: GameState, cell: int, h: int, v: int) -> bool:
    """One cell of a ray march: does its occupant overlap the probe position?

    ``tst.w (a2,d1.w)`` empty -> no; picture bit 15 (a software MOB) shifts the
    stored H by 0x200 first; otherwise both axis separations have to be inside
    ``_OVERLAP`` for the cell to block.

    The separations are taken *modulo the maze*: the position words span
    exactly one maze in 16 bits, so the subtraction wraps at the seam on its
    own and a creature on column 31 sees column 0 as its neighbour.

    A hero needs no special case: its record migrates into the cell it stands
    in, so a walking player is simply that cell's occupant.
    """
    picture = state.mobs.picture[cell]
    if picture == 0:
        return False
    cell_h = state.mobs.hpos[cell]
    if picture & 0x8000:
        cell_h = (cell_h - _SOFTWARE_MOB_BIAS) & 0xFFFF
    if abs(_s16(cell_h - h)) >= _OVERLAP:
        return False
    return abs(_s16(v - state.mobs.vpos[cell])) < _OVERLAP


def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _ray_march(state: GameState, slot: int, probe: tuple[int, int],
               h: int, v: int) -> int | None:
    """The four ray marches -- returns the blocking cell, or None when clear.

    Each march looks at the cell straight ahead and the two cells flanking it
    on the perpendicular axis, because a 16-pixel creature clips its
    neighbours.  The ROM signals "clear" by returning with N set and a -1 cell,
    and records it by setting bit 31 of D2; here that is simply ``None``.
    """
    row, col = slot >> 5, slot & 0x1F
    d_row, d_col = probe

    if d_row:                                   # vertical march
        if d_row < 0:                           # 0x5E10C: towards row 0
            if row < 2:                         # cmpi.w #0x80,d2
                return None if (v & 0xFFFF) <= _EDGE_TOP_LIMIT else slot
        elif row >= 31:                         # 0x5E1D8: cmpi.w #0x7C0,d2
            return None if _s16(v) >= 0 else slot
        ahead_row = row + d_row
        cells = (_cell_at(ahead_row, col),
                 _cell_at(ahead_row, col - 1),
                 _cell_at(ahead_row, col + 1))
    else:                                       # horizontal march
        ahead_col = col + d_col
        cells = [_cell_at(row, ahead_col)]
        if row >= 2:                            # 0x5E2DE: skip near the top
            cells.append(_cell_at(row - 1, ahead_col))
        if row < 31:                            # 0x5E308: skip on the last row
            cells.append(_cell_at(row + 1, ahead_col))

    for cell in cells:
        if cell != slot and _march_cell_blocks(state, cell, h, v):
            return cell
    return None


def _probe_phase(state: GameState, slot: int, step: int,
                 ) -> tuple[int, int, int, bool, int | None]:
    """0x41272-0x41336 -- the four axis probes.

    Returns ``(hpos, vpos, d6, any_clear, blocking_cell)``.  ``d6`` is the
    ROM's rotating direction counter *after* the final ``+0x400`` and mask, so
    it is the heading to store; ``blocking_cell`` is set only when a probe ran
    into something the caller has to resolve as contact.
    """
    from .monsters import (
        _get_direction as _get_direction,
    )

    h = state.mobs.hpos[slot]
    v = state.mobs.vpos[slot]
    rom_dir = (_get_direction(state, slot) + 2) & 0x07
    d6 = ((rom_dir << 10) + 0x400) & 0x1C00
    clear = False

    # --- probe 1 (0x41288): the "up the screen" component -------------------
    if d6 < 0xC00:
        v = (v + step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_UP, h, v)
        if blocker is None:
            clear = True
        else:
            v = (v - step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 - 0x1000) & 0xFFFF

    # --- probe 2 (0x412B4): the "down the screen" component -----------------
    if d6 < 0xC00:
        v = (v - step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_DOWN, h, v)
        if blocker is None:
            clear = True
        else:
            v = (v + step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 - 0x800) & 0x1C00

    # --- probe 3 (0x412E4): the leftward component --------------------------
    if d6 < 0xC00:
        h = (h - step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_LEFT, h, v)
        if blocker is None:
            clear = True
        else:
            h = (h + step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 + 0x1000) & 0x1C00

    # --- probe 4 (0x41314): the rightward component -------------------------
    if d6 < 0xC00:
        h = (h + step) & 0xFFFF
        blocker = _ray_march(state, slot, _PROBE_RIGHT, h, v)
        if blocker is None:
            clear = True
        else:
            h = (h - step) & 0xFFFF
            d6 = (2 * d6 - 0x400) & 0xFFFF
            if _is_player_cell(state, blocker):
                return h, v, d6, clear, blocker
    d6 = (d6 + 0x400) & 0x1C00
    return h, v, d6, clear, None


def _is_player_cell(state: GameState, cell: int) -> bool:
    """0x4129E -- the palette nibble the ROM reads a hero sprite by."""
    return _cell_player_index(state, cell) is not None


def _monster_move_engine(state: GameState, slot: int, obj_type: int, index: int,
                         frame_word: int, acted: bool = False) -> None:
    """0x4126A -- probe, slide, relocate, and animate.

    ``D6`` walks a rotating direction counter: it starts one step clockwise of
    the creature's heading and each probe block moves it on, so a run with
    nothing blocked lands back exactly where it started.  A probe that *is*
    blocked doubles it first (``add.w d6,d6; subi #0x400``), which is how the
    creature turns away from what it hit.
    """
    from .monsters import (
        _monster_speed as _monster_speed,
    )

    speed = _monster_speed(state, obj_type, frame_word)
    h, v, d6, clear, blocker = _probe_phase(state, slot, speed << POS_SHIFT)
    if blocker is not None:
        _march_hit_player(state, slot, blocker)
        return
    _commit_move(state, slot, index, d6, h, v, clear, frame_word, acted)


def _march_hit_player(state: GameState, slot: int, blocker: int) -> None:
    """0x4129A/0x413B0 -- a blocked probe that ran into a player is contact.

    The ROM branches out of the probe loop *before* it commits the heading or
    drops the moving flag (0x41348), so the creature neither moves nor leaves
    its attack state: this is the frame it lands a blow.  Afterwards it turns
    to face what it hit (0x413CC), unless the contact removed it -- a ghost
    exploding on the player.
    """
    from .monsters import (
        _iter_ptr_forget as _iter_ptr_forget,
        monster_playerhit as monster_playerhit,
    )

    victim = _cell_player_index(state, blocker)
    if victim is None:
        return
    monster_playerhit(state, victim, slot)
    if state.mobs.picture[slot] == 0:
        _iter_ptr_forget(state, slot)          # 0x413C4: it removed itself
        return
    apply_direction_from_delta(state, slot, blocker)  # 0x413CC


def _cell_player_index(state: GameState, cell: int) -> int | None:
    """Which player, if any, the given cell counts as.

    The ROM tests the cell's palette nibble (>= 0xC, the four hero palettes)
    and then charges the hit to that player.  This port asks the authoritative
    question instead -- which live record *is* this cell -- because
    ``active_mob_ids`` is the identity and a nibble is only its colour
    (``FIDELITY.md`` rule 6).  Both answers are the same cell now that a hero's
    record migrates with it.
    """
    for p in state.players:
        if p.active and p.mob_slot == cell:
            return p.index
    return None


def apply_direction_from_delta(state: GameState, slot: int, victim_cell: int) -> None:
    """``apply_direction_from_delta`` (0x41B7E) -- turn towards what was hit.

    Same picker as the idle aim with the fixed 0x400-position-unit threshold,
    which is 8 pixels, i.e. 4 of the 2-pixel units the picker counts in.
    """
    from .monsters import (
        _aim_direction as _aim_direction,
        _delta_units as _delta_units,
        _set_direction as _set_direction,
    )

    victim = _cell_player_index(state, victim_cell)
    target_slot = (
        state.players[victim].mob_slot if victim is not None else victim_cell
    )
    dx = _delta_units(state.mobs.hpos[target_slot], state.mobs.hpos[slot])
    dv = _delta_units(state.mobs.vpos[target_slot], state.mobs.vpos[slot])
    _set_direction(state, slot, _aim_direction(dx, dv, 0, 4))


def _write_direction(state: GameState, slot: int, d6: int) -> None:
    """0x4133E -- store the ROM-compass direction field back into the state."""
    from .monsters import (
        _set_direction as _set_direction,
    )

    _set_direction(state, slot, ((d6 >> 10) - 2) & 0x07)


def _destination_cell(h: int, v: int) -> int:
    """0x41358-0x41374 -- which cell a position belongs to, sprite bias and all.

    The ROM adds 0x400 to V and 0x600 to H before slicing out the row and
    column, and its rows run the other way -- which is exactly what the stored
    words do too, so this is the ROM's own arithmetic. ``coords.mob_cell_of``
    owns it, because ``player_try_move_core`` (0x424CA) applies the identical
    sequence to relocate a hero's record.
    """
    return mob_cell_of(h, v)


def _commit_move(state: GameState, slot: int, index: int, d6: int, h: int,
                 v: int, clear: bool, frame_word: int, acted: bool) -> None:
    """0x4133E-0x413AE -- store the heading, then relocate if a probe was clear."""
    from .monsters import (
        _iter_ptr_forget as _iter_ptr_forget,
        monster_playerhit as monster_playerhit,
        monster_update_anim_tile as monster_update_anim_tile,
    )

    _write_direction(state, slot, d6)
    h &= ~_HPOS_FLAG_MOVING                    # 0x41348: bclr #5
    state.mobs.hpos[slot] = h

    if not clear:
        _move_tail(state, slot, index, frame_word, moved=False, acted=acted)
        return

    dest = _destination_cell(h, v)
    if dest == slot:                            # 0x4144C: same cell
        state.mobs.vpos[slot] = v
        _move_tail(state, slot, index, frame_word, moved=True, acted=acted)
        return

    if state.mobs.picture[dest] == 0:           # 0x41380: the cell is free
        if state.monster_iter_ptr == slot:
            state.monster_iter_ptr = dest
        state.mobs.hpos[slot] = h
        state.mobs.vpos[slot] = v
        state.mobs.move_slot(slot, dest)
        _move_tail(state, dest, index, frame_word, moved=True, acted=acted)
        monster_update_anim_tile(
            state, dest, int(MazeObjIds.MONST_GHOST) + index,
        )
        return

    victim = _cell_player_index(state, dest)    # 0x413A2
    if victim is None:
        _move_tail(state, slot, index, frame_word, moved=False, acted=acted)
        return
    monster_playerhit(state, victim, slot)
    if state.mobs.picture[slot] == 0:
        _iter_ptr_forget(state, slot)
        return
    apply_direction_from_delta(state, slot, dest)
    if not (state.mobs.hpos[slot] & _HPOS_FLAG_MOVING):
        _move_tail(state, slot, index, frame_word, moved=False, acted=acted)


def _move_tail(state: GameState, slot: int, index: int, frame_word: int,
               moved: bool, acted: bool) -> None:
    """0x41454 (moved) and 0x4142E (refused) -- the shared animation tail.

    The frame mask comes from ``monster_oddangle_table``: byte 1 after a step,
    byte 0 when the step was refused.  A zero mask on the refused path means
    "do nothing at all"; a negative one (the two sorcerers) drops the attack
    flag instead.  When the counter wraps, byte 2 either bumps it further or --
    with bit 0 set -- flips the creature into its blink state.
    """
    from .monsters import (
        _anim_add_high as _anim_add_high,
        _anim_advance as _anim_advance,
    )

    row = _MONSTER_ODDANGLE_TABLE[index]
    if moved:
        mask = row[1]
    else:
        if acted:                               # 0x41430: btst #30
            return
        mask = row[0]
        if mask == 0:
            return
        if mask & 0x80:                         # 0x41442: bmi
            if state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
                state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK
            return

    if mask & (frame_word & 0xFF):              # 0x41460
        return
    if not _anim_advance(state, slot):          # 0x41466
        return

    delta = row[2]
    if delta & 0x01:                            # 0x41472: the blink families
        if state.mobs.hpos[slot] & _HPOS_FLAG_ATTACK:
            state.mobs.hpos[slot] &= ~_HPOS_FLAG_ATTACK
            return
        state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK
        _anim_add_high(state, slot, _BLINK_ANIM_BUMP)
        state.mobs.picture[slot] = _BLANK_PICTURE
        return
    _anim_add_high(state, slot, delta)
