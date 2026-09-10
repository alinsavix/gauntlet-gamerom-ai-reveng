"""Projectile collision candidates, viewport gates, and reflection routines."""

from __future__ import annotations

from ..constants import MazeObjIds
from ..coords import POS_FIELD_MASK, position_field
from ..state import GameState
from .shot_data import (
    CONSUMED as CONSUMED,
)

# shot_collision_width (0x40B98) and its companion span table (0x40BB0),
# twelve words each, in native position units.  Player shots index by
# character, other channels by channel.
_SHOT_HITBOX_WIDTH = [
    0x0580, 0x0400, 0x0480, 0x0400, 0x0480, 0x0480,
    0x0480, 0x0480, 0x0480, 0x0480, 0x0480, 0x0480,
]
_SHOT_HITBOX_SPAN = [
    0x0800, 0x0600, 0x0700, 0x0600, 0x0600, 0x0600,
    0x0600, 0x0600, 0x0600, 0x0600, 0x0600, 0x0600,
]
# dragon_shot_collision_width (0x40BC8) plus its span half (0x40BD0).
_DRAGON_HITBOX_WIDTH = [0x0300, 0x0200, 0x0280, 0x0200]
_DRAGON_HITBOX_SPAN = [0x0500, 0x0300, 0x0400, 0x0300]
# A max-tier monster shot swaps in a fixed, much larger box (0x4094C).
_MAXTIER_HITBOX_WIDTH = 0x0880
_MAXTIER_HITBOX_SPAN = 0x0E80
_MAXTIER_H_BIAS = 0x0200          # 0x40990: nudge before masking

# shot_collision_probe_offsets -- ROM 0x40BD8, eight direction records of five
# (horizontal, vertical) signed word pairs.  The values are *word* indices
# into the MOB arrays: 2 per cell horizontally, 0x40 per maze row.  Each probe
# takes the previous probe's index, adds the horizontal delta, keeps only the
# column (``& 0x3E``), adds the vertical delta and re-adds the shot's own row.
_PROBE_OFFSETS = [
    [(-64, -64), (62, 0), (4, 0), (-68, -64), (4, -64)],
    [(-62, -64), (-2, -64), (66, 0), (62, 64), (-66, 0)],
    [(2, 0), (-66, -64), (128, 64), (-126, -64), (128, 64)],
    [(66, 64), (-64, 0), (62, 64), (-66, 0), (-62, -64)],
    [(64, 64), (-66, 0), (4, 0), (64, 64), (-4, 64)],
    [(62, 64), (-64, 0), (66, 64), (-128, -64), (66, 0)],
    [(-2, 0), (-62, -64), (128, 64), (-2, 64), (-128, -64)],
    [(-66, -64), (64, 0), (-62, -64), (66, 0), (62, 64)],
]

# 0x40B58, 64 bytes: 0 = a max-tier shot collides with this object type,
# 0xFF = it passes straight through.
_MAXTIER_PASS_TBL = [
    0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00,
    0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0xFF, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF,
    0xFF, 0x00, 0xFF, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF,
]
_SOUND_REFLECT = 0x2C


def shot_onscreen_check(state: GameState, target: int,
                        h_limit: int, v_limit: int) -> int:
    """0x4AEA0 -- does the door at ``target`` face the shot that just hit it?

    Reads the separations ``shot_collision_candidate_core`` recorded for the
    accepted candidate and compares them against the door's own open-direction
    bits in ``mob_state_link``.  -1 = react, 0 = ignore.
    """
    from .shots import (
        _s16 as _s16,
    )

    door = state.mobs.state_link[target]

    if v_limit > state.collision_dist_V:
        if (door & 0x2000) and _s16(state.shothit_dist_H) > -h_limit:
            return CONSUMED
        if (door & 0x0800) and h_limit > _s16(state.shothit_dist_H):
            return CONSUMED
    if h_limit > state.collision_dist_H:
        if (door & 0x1000) and _s16(state.shothit_dist_V) > -v_limit:
            return CONSUMED
        if (door & 0x0400) and v_limit > _s16(state.shothit_dist_V):
            return CONSUMED
    return 0


# =============================================================================
# shot_mob_collision (0x40906) and its candidate core (0x40A78)
# =============================================================================

def shot_collision_candidate_core(state: GameState, index: int, shooter_id: int,
                    width: int, span: int, shot_h: int, shot_v: int,
                    self_index: int, maxtier: bool) -> int | None:
    """0x40A78 -- accept or reject one probed cell.

    ``index`` is the ROM's word index (``slot * 2``).  Returns the accepted
    MOB slot, or ``None``.  Also publishes the signed and folded separations
    the door check reads back.
    """
    from .shots import (
        _shot_slot as _shot_slot,
        _u16 as _u16,
    )

    mobs = state.mobs

    if index >= 0x800:
        # 0x40A84: the probe left the maze.  As a u16 this covers both a probe
        # that ran off the top (the index went negative) and one that ran off
        # the bottom.  The ROM wraps by a whole 0x800-word maze and returns the
        # cell as an immediate hit, without any separation test.  It only does
        # so for a non-max-tier shot (0x40A90 tests the sign bit set on the
        # biased hpos) whose own V word is negative and no greater than
        # 0xF3FF -- see ``_wrap_allowed``.  ``_test_probe_wrap`` proves the
        # bottom case cannot occur, so the wrap always lands on row 31.
        if maxtier or not _wrap_allowed(state, shooter_id):
            return None
        index = _u16(index + 0x800)
        assert 0x40 <= index < 0x800, "probe wrapped outside the maze"
        return index >> 1

    if index < 0x40:
        # 0x40A9A-0x40AA0: row 0 shares the reserved MOB band, so an upward
        # shot in the top half of that row returns a 0x400-tagged playfield
        # target instead of reading a MOB record. resolve_shot_hit routes that
        # tag through the ordinary wall/reflect path.
        shot_v = state.mobs.vpos[_shot_slot(shooter_id)] & 0xFFFF
        if maxtier or shot_v <= 0xF3FF:
            return None
        return (index + 0x800) >> 1

    slot = index >> 1
    if mobs.picture[slot] == 0 or index == self_index:
        # 0x40AA6/0x40AAE: an empty cell, or the shooter's own record, is not a
        # candidate. A live hero *is* one -- its record migrates into the cell
        # it stands in, so the probe finds it here like any other occupant.
        return None

    picture = mobs.picture[slot]
    if picture & 0x8000:
        # 0x40B02: a static playfield tile is snapped to its cell first.
        sep_h = _u16(((mobs.hpos[slot] + 0x280) & 0xF800) - shot_h)
        sep_v = _u16(((mobs.vpos[slot] + 0x100) & 0xF800) - shot_v)
    else:
        sep_h = _u16(
            position_field(mobs.hpos[slot]) - shot_h + 0x200
        )
        sep_v = _u16(
            position_field(mobs.vpos[slot]) - shot_v
        )

    state.shothit_dist_H = sep_h
    folded_h = sep_h ^ POS_FIELD_MASK if sep_h & 0x8000 else sep_h
    if folded_h >= width:
        return None
    state.collision_dist_H = folded_h

    state.shothit_dist_V = sep_v
    folded_v = sep_v ^ POS_FIELD_MASK if sep_v & 0x8000 else sep_v
    if folded_v >= width:
        return None
    state.collision_dist_V = folded_v

    if span < _u16(folded_v + folded_h):
        return None

    if maxtier and _MAXTIER_PASS_TBL[mobs.obj_type(slot)] != 0:
        return None      # 0x40B3A: this type ignores a max-tier shot
    return slot


def _wrap_allowed(state: GameState, shooter_id: int) -> bool:
    """The vertical window at 0x40A88/0x40A8A gates the probe's maze wrap.

    Straight off the ROM now that the V word is the hardware's own: "negative
    and no greater than 0xF3FF", i.e. the shot has to be level with the bottom
    half of row 0 (9 <= screen y <= 240) before a probe may wrap to row 31.

    The companion window at 0x40A9A, ``V > 0xF3FF``, guards the row-0 case
    ``shot_collision_candidate_core`` refuses outright.
    """
    from .shots import (
        _shot_slot as _shot_slot,
    )

    vpos = state.mobs.vpos[_shot_slot(shooter_id)] & 0xFFFF
    return 0x8000 <= vpos <= 0xF3FF


def shot_mob_collision(state: GameState, cell: int, shooter_id: int) -> int:
    """0x40906 -- the first MOB this shot overlaps, or -1.

    ``cell`` is the shot's own packed maze cell (the ROM passes
    ``mob_depth_key[shot]``).  The shot's own cell is probed first, then the
    five direction-dependent offsets from ``shot_collision_probe_offsets``.
    """
    from .shots import (
        _is_maxtier as _is_maxtier,
        _live_direction as _live_direction,
        _shot_slot as _shot_slot,
        _u16 as _u16,
    )

    mobs = state.mobs
    slot = _shot_slot(shooter_id)
    maxtier = _is_maxtier(state, shooter_id)

    if shooter_id >= 4:
        if maxtier:
            width, span = _MAXTIER_HITBOX_WIDTH, _MAXTIER_HITBOX_SPAN
        else:
            width = _SHOT_HITBOX_WIDTH[shooter_id]
            span = _SHOT_HITBOX_SPAN[shooter_id]
    else:
        character = state.players[shooter_id].character & 0x03
        width = _SHOT_HITBOX_WIDTH[character]
        span = _SHOT_HITBOX_SPAN[character]

    shot_h = mobs.hpos[slot]
    shot_v = mobs.vpos[slot]
    if maxtier:
        shot_h = _u16(shot_h + _MAXTIER_H_BIAS)
    shot_h = position_field(shot_h)
    shot_v = position_field(shot_v)

    self_index = _u16(_shot_owner(state, shooter_id) * 2)
    if shooter_id < 4 and state.reflect_count[shooter_id] != 4:
        self_index |= 0x8000    # 0x409BA: a reflected shot may hit its owner

    index = _u16(cell * 2)
    hit = shot_collision_candidate_core(
        state, index, shooter_id, width, span, shot_h, shot_v,
        self_index, maxtier,
    )
    if hit is not None:
        return _dragon_hitbox_retry(state, hit, shooter_id, shot_h, shot_v,
                                    self_index, maxtier)

    row_base = index & 0x7C0
    for h_delta, v_delta in _PROBE_OFFSETS[_live_direction(state, shooter_id) & 7]:
        index = _u16(_u16(index + h_delta) & 0x3E)
        index = _u16(index + v_delta + row_base)
        hit = shot_collision_candidate_core(
            state, index, shooter_id, width, span, shot_h, shot_v,
            self_index, maxtier,
        )
        if hit is not None:
            return _dragon_hitbox_retry(state, hit, shooter_id, shot_h,
                                        shot_v, self_index, maxtier)
    return -1


def _dragon_hitbox_retry(state: GameState, slot: int, shooter_id: int,
                         shot_h: int, shot_v: int, self_index: int,
                         maxtier: bool) -> int:
    """0x40A3E -- the dragon gets a second, tighter pass over the same cell."""
    from .shots import (
        _s16 as _s16,
        _u16 as _u16,
    )

    if slot >= 0x400:
        return slot
    if state.mobs.obj_type(slot) != int(MazeObjIds.MONST_DRAGON):
        return slot
    character = (
        state.players[shooter_id].character & 0x03 if shooter_id < 4 else 0
    )
    facing = state.dragon_facing & 0x06
    # dragon_head_hitbox_offsets, ROM 0x54BD6. Facing indexes these as byte
    # offsets: V reads table[facing/2], H reads the following word.
    offsets = (0x0400, 0, 0x0400, 0, 0x0400)
    hsep = _u16(state.dragon_head_hpos - shot_h)
    if hsep & 0x8000:
        hsep ^= POS_FIELD_MASK
    hsep = _s16(hsep - offsets[(facing >> 1) + 1])
    width = _DRAGON_HITBOX_WIDTH[character]
    if hsep >= width:
        return slot

    vsep = _u16(state.dragon_head_vpos - shot_v)
    if vsep & 0x8000:
        vsep ^= POS_FIELD_MASK
    vsep = _s16(vsep - offsets[facing >> 1])
    if vsep >= width or hsep + vsep >= _DRAGON_HITBOX_SPAN[character]:
        return slot

    # The ROM adds 0x1000 to the doubled MOB index and then shifts right once,
    # so the public packed-cell result carries 0x0800 on a moving-head hit.
    return slot | 0x0800


def _shot_owner(state: GameState, shooter_id: int) -> int:
    """``active_mob_ids[shooter]`` (0x9048C8) -- the MOB that fired."""
    if shooter_id < 4:
        return state.players[shooter_id].mob_slot
    owner = state.shot_owner_mob[shooter_id]
    return owner if owner >= 0 else 0


# =============================================================================
# shot_reflect_calc (0x53818)
# =============================================================================

_REFLECT_NONE = 0        # 0x53CAE: unchanged, and no counter/cell update
_REFLECT_KEEP = 1        # 0x53CB4: finish with the direction as computed
_REFLECT_XOR2 = 2        # 0x53CB6
_REFLECT_XOR6 = 3        # 0x53CB0

# 0x538FE / 0x53924 / 0x53948 / 0x5396A / 0x53992: the five signed-delta
# bands, each five entries wide, that pick the corner handler.
_REFLECT_BANDS = {
    -2: "A_", -1: "A_", 0: None, 1: "B_", 2: "B_",
    -66: "UL", -65: "UL", -64: None, -63: "UR", -62: "UR",
    -34: "UL", -33: "UL", -32: "U_", -31: "UR", -30: "UR",
    30: "DL", 31: "DL", 32: "D_", 33: "DR", 34: "DR",
    62: "DL", 63: "DL", 64: None, 65: "DR", 66: "DR",
}


def shot_reflect_calc(state: GameState, target: int, shooter_id: int) -> int:
    """0x53818 -- the direction a reflected shot leaves the wall with.

    Cardinal shots simply reverse.  A diagonal picks its bounce from the
    signed cell delta between this wall and the last one, then confirms it
    against the two neighbouring wall pictures, exactly as 0x5399C-0x53C98 do.
    """
    from .shots import (
        _live_direction as _live_direction,
        _s16 as _s16,
        _shot_slot as _shot_slot,
    )

    mobs = state.mobs
    direction = state.shot_direction[shooter_id] & 0xFFFF
    if 0 <= direction <= 7 and not direction & 1:
        return _reflect_finish(state, target, shooter_id, direction ^ 4,
                               _REFLECT_KEEP)
    if not 0 <= direction <= 7:
        direction = _live_direction(state, shooter_id)
        if not direction & 1:
            return _reflect_finish(state, target, shooter_id, direction ^ 4,
                                   _REFLECT_KEEP)

    if target >= 0x400:
        # 0x53850: with no MOB to inspect, the shot's own vertical position
        # decides.  The ROM's ``vpos > 0xF7FF`` is "within 8 pixels of the top
        # of the maze" in the hardware's upward V word.
        near_top = (mobs.vpos[_shot_slot(shooter_id)] & 0xFFFF) > 0xF7FF
        if direction in (1, 7):
            outcome = _REFLECT_NONE if near_top else _REFLECT_XOR2
        else:
            outcome = _REFLECT_XOR2 if near_top else _REFLECT_NONE
        return _reflect_finish(state, target, shooter_id, direction, outcome)

    delta = _s16(target - state.player_shot_last_wall_pos[shooter_id])
    if delta > 0x200:
        delta -= 0x400
    if (state.player_shot_last_wall_pos[shooter_id] & 0x3E0) == (target & 0x3E0):
        if delta > 2:
            delta -= 0x20
        elif delta < -2:
            delta += 0x20

    band = _REFLECT_BANDS.get(delta)
    if band is None:
        return _reflect_finish(state, target, shooter_id, direction,
                               _REFLECT_NONE)

    direction, outcome = _reflect_corner(state, target, shooter_id,
                                         direction, band)
    return _reflect_finish(state, target, shooter_id, direction, outcome)


# Each corner handler owns one diagonal; anything else snaps to its partner.
# (expected direction, fallback direction, column step, row step, negate H)
_REFLECT_CORNERS = {
    "UL": (7, 3, +1, +1, True),    # 0x5399C
    "UR": (1, 5, -1, +1, False),   # 0x53A50
    "DL": (5, 1, +1, -1, False),   # 0x53AFC
    "DR": (3, 7, -1, -1, True),    # 0x53BA6
}


def _reflect_corner(state: GameState, target: int, shooter_id: int,
                    direction: int, band: str) -> tuple[int, int]:
    """0x5399C / 0x53A50 / 0x53AFC / 0x53BA6 and their three dispatchers."""
    from .shots import (
        _s16 as _s16,
        _shot_slot as _shot_slot,
    )

    if band == "A_":       # 0x53C84, same row, wall to the left
        if direction == 5:
            band = "DL"
        elif direction == 7:
            band = "UL"
        else:
            return direction, _REFLECT_NONE
    elif band == "B_":     # 0x53C98, same row, wall to the right
        if direction == 1:
            band = "UR"
        elif direction == 3:
            band = "DR"
        else:
            return direction, _REFLECT_NONE
    elif band == "U_":     # 0x53C58, one row up
        if direction == 1:
            band = "UR"
        elif direction == 7:
            band = "UL"
        else:
            return direction, _REFLECT_NONE
    elif band == "D_":     # 0x53C6E, one row down
        if direction == 3:
            band = "DR"
        elif direction == 5:
            band = "DL"
        else:
            return direction, _REFLECT_NONE

    expected, fallback, col_step, row_step, negate_h = _REFLECT_CORNERS[band]
    if direction != expected:
        return fallback, _REFLECT_KEEP

    mobs = state.mobs
    side = (target & 0xFFE0) | ((target + col_step) & 0x1F)
    if mobs.picture[side] == 0x8000:
        direction ^= 2
    above = target + (row_step << 5)
    if not 0 <= above < 0x400 or mobs.picture[above] == 0x8000:
        direction ^= 6

    if direction != state.shot_direction[shooter_id]:
        return direction, _REFLECT_KEEP

    shot = _shot_slot(shooter_id)
    sep_h = mobs.hpos[target] - mobs.hpos[shot]
    if negate_h:
        sep_h = -sep_h
    sep_v = _s16(mobs.vpos[target] - mobs.vpos[shot])
    nearer = _s16(sep_h) < sep_v
    if band in ("UL", "UR"):
        return direction, _REFLECT_XOR2 if nearer else _REFLECT_XOR6
    return direction, _REFLECT_XOR6 if nearer else _REFLECT_XOR2


def _reflect_finish(state: GameState, target: int, shooter_id: int,
                    direction: int, outcome: int) -> int:
    """0x53CB0-0x53D02 -- apply the outcome, spend a bounce, remember the wall."""
    from .shots import (
        _shot_slot as _shot_slot,
        _sound as _sound,
        _u16 as _u16,
    )

    if outcome == _REFLECT_NONE:
        return direction
    if outcome == _REFLECT_XOR2:
        direction ^= 2
    elif outcome == _REFLECT_XOR6:
        direction ^= 6

    state.reflect_count[shooter_id] = _u16(state.reflect_count[shooter_id] - 1)
    if state.reflect_count[shooter_id] != 0:
        _sound(state, _SOUND_REFLECT)

    if target >= 0x190:
        slot = _shot_slot(shooter_id)
        key = state.mobs.depth_key[slot] if slot < len(state.mobs.depth_key) else 0
        state.player_shot_last_wall_pos[shooter_id] = key
    else:
        state.player_shot_last_wall_pos[shooter_id] = target
    return direction & 7
