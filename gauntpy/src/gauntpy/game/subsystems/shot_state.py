"""Shared projectile channel geometry, state, and picture/velocity tables."""

from __future__ import annotations

from ..coords import hpos_x, position_field, vpos_y
from ..state import GameState

# shot_counter_reload -- ROM 0x578C2, 12 words.  Player channels index it by
# character; channels 4-11 index it by channel.
_SHOT_COUNTER_RELOAD = [
    0x0F, 0x01, 0x01, 0x00, 0x01, 0x01,
    0x01, 0x01, 0x20, 0x20, 0x20, 0x20,
]

# shot_velocity_x / shot_velocity_y -- ROM 0x576E2 / 0x57792, 88 signed words
# each, 11 rows of 8 directions.  Rows 0-3 are the four characters, row 4 the
# ordinary monster shot (+0x20), rows 5-8 the shot-speed set (+0x28), row 9
# the tier-2 monster shot (+0x48) and row 10 the max-tier shot (+0x50).
#
# The ROM stores positions and velocities in native ``<< 7`` words, and so do
# we, so both tables are the literal ROM data.  The V axis grows up the screen
# in both, so ``shot_velocity`` returns entry Y unchanged.
_SHOT_VELOCITY_X = [
    0, 256, 384, 256, 0, -256, -384, -256,
    0, 384, 512, 384, 0, -384, -512, -384,
    0, 384, 512, 384, 0, -384, -512, -384,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 256, 384, 256, 0, -256, -384, -256,
    0, 384, 512, 384, 0, -384, -512, -384,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 640, 896, 640, 0, -640, -896, -640,
    0, 512, 640, 512, 0, -512, -640, -512,
    0, 128, 256, 128, 0, -128, -256, -128,
]
_SHOT_VELOCITY_Y = [
    384, 256, 0, -256, -384, -256, 0, 256,
    512, 384, 0, -384, -512, -384, 0, 384,
    512, 384, 0, -384, -512, -384, 0, 384,
    640, 512, 0, -512, -640, -512, 0, 512,
    384, 256, 0, -256, -384, -256, 0, 256,
    512, 384, 0, -384, -512, -384, 0, 384,
    640, 512, 0, -512, -640, -512, 0, 512,
    640, 512, 0, -512, -640, -512, 0, 512,
    896, 640, 0, -640, -896, -640, 0, 640,
    640, 512, 0, -512, -640, -512, 0, 512,
    256, 128, 0, -128, -256, -128, 0, 128,
]
_VEL_MONSTER_BASE = 0x20     # ordinary monster shot rows
_VEL_SHOTSPEED = 0x28        # player shot-speed rows
_VEL_MONSTER_TIER2 = 0x48    # monster shot with hpos bit 5
_VEL_MONSTER_MAXTIER = 0x50  # monster shot with hpos bits 4+5

# projectile_picture_table (0x58B8A, 64 words), special_projectile_picture_table
# (0x58E3E, 80 words) and monster_projectile_picture_table (0x58EDE, 33 words).
_PROJECTILE_PICTURE_TBL = [
    0x1C9F, 0x1CA3, 0x1CA7, 0x1CAB, 0x1CAF, 0x1CB3, 0x1CB7, 0x1CBB,
    0x1CBF, 0x1CC3, 0x1CC7, 0x1CCB, 0x1CCF, 0x1CD3, 0x1C97, 0x1C9B,
    0x17FC, 0x17FC, 0x18FC, 0x18FC, 0x19FC, 0x19FC, 0x1AFC, 0x1AFC,
    0x1BC3, 0x1BC3, 0x1C68, 0x1C68, 0x1C6C, 0x1C6C, 0x1C70, 0x1C70,
    0x1CD7, 0x1CDB, 0x1CDF, 0x1CE3, 0x1CE7, 0x1CEB, 0x1CEF, 0x1CF3,
    0x1CF7, 0x1CFB, 0x1D00, 0x1D04, 0x1D08, 0x1D0C, 0x1D10, 0x1D14,
    0x1C74, 0x1C74, 0x1C78, 0x1C78, 0x1C7C, 0x1C7C, 0x1C80, 0x1C80,
    0x1C84, 0x1C84, 0x1C8B, 0x1C8B, 0x1C8F, 0x1C8F, 0x1C93, 0x1C93,
]
_SPECIAL_PROJECTILE_PICTURE_TBL = [
    0x27B0, 0x27B0, 0x27B0, 0x27A7, 0x27A7, 0x279E, 0x279E, 0x2795,
    0x2795, 0x278C, 0x278C, 0x07BC, 0x07BC, 0x07BC, 0x07B3, 0x07B3,
    0x07B3, 0x27EF, 0x27EF, 0x27EF, 0x27B0, 0x27B0, 0x27B0, 0x27A7,
    0x27A7, 0x279E, 0x279E, 0x2795, 0x2795, 0x278C, 0x278C, 0x27E6,
    0x27E6, 0x27E6, 0x27DD, 0x27DD, 0x27DD, 0x27D4, 0x27D4, 0x27D4,
    0x27B0, 0x27B0, 0x27B0, 0x27A7, 0x27A7, 0x279E, 0x279E, 0x2795,
    0x2795, 0x278C, 0x278C, 0x07D7, 0x07D7, 0x07D7, 0x07CE, 0x07CE,
    0x07CE, 0x07C5, 0x07C5, 0x07C5, 0x27B0, 0x27B0, 0x27B0, 0x27A7,
    0x27A7, 0x279E, 0x279E, 0x2795, 0x2795, 0x278C, 0x278C, 0x27CB,
    0x27CB, 0x27CB, 0x27C2, 0x27C2, 0x27C2, 0x27B9, 0x27B9, 0x27B9,
]
_MONSTER_PROJECTILE_PICTURE_TBL = [
    0x1C48, 0x1C48, 0x1C48, 0x1C48, 0x1C4C, 0x1C4C, 0x1C4C, 0x1C4C,
    0x1C50, 0x1C50, 0x1C50, 0x1C54, 0x1C54, 0x1C54, 0x1C58, 0x1C58,
    0x1C58, 0x1C58, 0x1C54, 0x1C54, 0x1C54, 0x1C50, 0x1C50, 0x1C50,
    0x1C4C, 0x1C4C, 0x1C4C, 0x1C4C, 0x1C48, 0x1C48, 0x1C48, 0x1C48,
    0x1C48,
]
# Shot strength/tier lives in hpos bits 4-5 of the *shot's* MOB word.
_SHOT_TIER_MASK = 0x30

# =============================================================================
# Small shared helpers
# =============================================================================

def _u16(value: int) -> int:
    return value & 0xFFFF


def _maze_position(value: int) -> int:
    """Unsigned position arithmetic: one 512 px maze is exactly one 16-bit word."""
    return value & 0xFFFF


def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def _shot_slot(shooter_id: int) -> int:
    """The MOB slot a shooter id owns.  The ROM writes ``shooter + 1``."""
    return shooter_id + 1


def _shot_tier(state: GameState, shooter_id: int) -> int:
    """hpos bits 4-5 of the shot MOB: its strength band."""
    return state.mobs.hpos[_shot_slot(shooter_id)] & _SHOT_TIER_MASK


def _is_maxtier(state: GameState, shooter_id: int) -> bool:
    return _shot_tier(state, shooter_id) == _SHOT_TIER_MASK


def _cell_of(px: int, py: int) -> int:
    """Packed maze cell of a world pixel position (0x47A5A-0x47A7C).

    The ROM rounds each axis to the nearest cell centre (``+8``) before
    truncating; ``py`` arrives already un-inverted into downward screen pixels
    by ``coords.vpos_y``, which is that routine's vertical half.
    """
    col = ((px + 8) >> 4) & 0x1F
    row = ((py + 8) >> 4) & 0x1F
    return (row << 5) | col


def shot_cell(state: GameState, slot: int) -> int:
    """The maze cell a projectile MOB's pixel position belongs to.

    ``monster_create_shot`` (0x49280-0x492A2) and ``shots``' per-frame re-key use
    the same +12/+8 px sprite biases, so a channel is depth-placed at creation
    exactly where the next frame would re-key it.
    """
    mobs = state.mobs
    return _cell_of(hpos_x(mobs.hpos[slot]), vpos_y(mobs.vpos[slot]))


def _shot_cell(state: GameState, slot: int) -> int:
    return shot_cell(state, slot)


def _direction_of(dx: int, dv: int) -> int:
    """Shot direction code from a per-frame pixel delta.

    ``dv`` is a native V delta -- positive walks up the screen -- matching the
    hardware axes ``state.shot_dy`` is stored in.  Matches ``thief.py``'s
    identical derivation: 0 is up, then clockwise.
    """
    if dx == 0:
        return 0 if dv > 0 else 4 if dv < 0 else 8
    if dv == 0:
        return 2 if dx > 0 else 6
    if dx > 0:
        return 1 if dv > 0 else 3
    return 7 if dv > 0 else 5


def _live_direction(state: GameState, shooter_id: int) -> int:
    """``shot_direction[shooter]`` (0x9049C4), recovered when unset.

    The player, monster and dragon creators seed direction directly. A channel
    armed by hand can retain sentinel 8; only an unset/invalid direction falls
    back to ``shot_dx/dy`` here.
    """
    direction = state.shot_direction[shooter_id]
    if 0 <= direction <= 7:
        return direction
    slot = _shot_slot(shooter_id)
    direction = _direction_of(state.shot_dx[slot], state.shot_dy[slot])
    if direction > 7:
        direction = 0
    state.shot_direction[shooter_id] = direction
    return direction


def _u32(value: int) -> int:
    return value & 0xFFFF_FFFF


def shot_picture(state: GameState, shooter_id: int, counter: int) -> int:
    """The projectile picture channel ``shooter_id`` shows at ``counter``.

    The three ROM tables and the index arithmetic of 0x47622-0x47716, factored
    out so ``shots``' per-frame animation and the monster/dragon creators share
    their frame selection. ``monster_shooting.monster_create_shot`` (0x490DC)
    arms a channel with the very frame the next animation tick would land on.

    * player channels 0-3 index ``projectile_picture_table`` by
      ``(direction*2 + counter) & 0x0F`` inside the character's 16-word block;
    * demon channels 4-7 by ``direction*2 + counter + 0x20``, unless the shot
      is max tier, which swaps in ``special_projectile_picture_table``;
    * lobber channels 8-11 ignore direction entirely -- the rock's spin is the
      counter alone, in ``monster_projectile_picture_table``.
    """
    direction = _live_direction(state, shooter_id) & 7

    if shooter_id < 4:
        index = (direction * 2 + counter) & 0x0F
        index += (state.players[shooter_id].character & 0x03) << 4
        return _PROJECTILE_PICTURE_TBL[index & 0x3F]
    if shooter_id < 8:
        if _is_maxtier(state, shooter_id):
            index = (direction & 6) * 10 + counter
            table = _SPECIAL_PROJECTILE_PICTURE_TBL
        else:
            index = direction * 2 + counter + 0x20
            table = _PROJECTILE_PICTURE_TBL
        return table[index % len(table)]
    table = _MONSTER_PROJECTILE_PICTURE_TBL
    return table[counter % len(table)]


def _velocity_row(state: GameState, shooter_id: int, direction: int) -> int:
    """0x47846 / 0x478B8 -- which velocity row this channel uses.

    Only channels 0-7 reach here: the lobbed-rock channels 8-11 branch
    away at 0x478B4 before any table is read (see ``shots._advance_lobber``).
    """
    if shooter_id < 4:
        row = ((state.players[shooter_id].character & 0x03) << 3) + direction
        if state.players[shooter_id].powers & 0x08:      # shot-speed upgrade
            row += _VEL_SHOTSPEED
        return row
    tier = _shot_tier(state, shooter_id)
    if tier == _SHOT_TIER_MASK:
        return direction + _VEL_MONSTER_MAXTIER
    if tier & 0x20:
        return direction + _VEL_MONSTER_TIER2
    return direction + _VEL_MONSTER_BASE


def shot_velocity(state: GameState, shooter_id: int,
                  direction: int) -> tuple[int, int]:
    """This frame's signed H/V word delta for a straight channel (0-7).

    Public so a shot creator can seed ``shot_dx/dy`` with the very step its
    channel will take, instead of guessing one.  Both components are in the
    hardware's own axes, so the V delta is positive up the screen.
    """
    row = _velocity_row(state, shooter_id, direction)
    return _SHOT_VELOCITY_X[row], _SHOT_VELOCITY_Y[row]


def lobber_accumulator_seed(state: GameState, shooter_id: int) -> None:
    """0x49216/0x4922A -- point a lobber channel's accumulators at its MOB.

    ``monster_create_shot`` seeds the pair from the masked spawn position, one
    instruction before it writes the same value plus the palette (0x4925A) and
    the sprite size (0x49270) into the MOB words -- so the accumulator's low
    bits start at zero and the first ``_advance_lobber`` reproduces the spawn
    position exactly, plus one vector step.  Exposed so the creators and
    ``main_handle_shots``' go-live latch agree by construction.
    """
    lobber = shooter_id - 8
    slot = _shot_slot(shooter_id)
    state.lobber_shot_h_accum[lobber] = position_field(state.mobs.hpos[slot])
    state.lobber_shot_v_accum[lobber] = position_field(state.mobs.vpos[slot])


# =============================================================================
# Channel retirement shared by hit resolution and off-screen disposal
# =============================================================================

def _channel_clear(state: GameState, shooter_id: int) -> None:
    """``mob_depth_remove(shooter)`` + ``mob_picture[shooter+1] = 0``.

    The ROM leaves H/V alone here; only the off-screen path clears them.
    """
    slot = _shot_slot(shooter_id)
    state.mobs.depth_remove(shooter_id)
    state.mobs.picture[slot] = 0
    state.shot_dx[slot] = 0
    state.shot_dy[slot] = 0
    state.shot_direction[shooter_id] = 8
    state.shot_owner_mob[shooter_id] = -1
