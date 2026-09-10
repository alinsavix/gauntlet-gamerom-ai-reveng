"""Demon/lobber targeting, projectile-channel allocation, and shot creation."""

from __future__ import annotations

from ..constants import SLOT_DEMON_SHOTS, SLOT_LOBBER_SHOTS, MazeObjIds, PlayerPower
from ..coords import POS_SHIFT, position_field
from ..state import GameState
from .sound import sound_play as _sound_play
from .monster_data import (
    _DIR_DELTAS as _DIR_DELTAS,
    _HPOS_FLAG_ATTACK as _HPOS_FLAG_ATTACK,
)

# Lobber-throw sound (§3.5).
_SOUND_LOBBER_THROW = 0x49

# Player power bits monster_find_and_shoot reads out of ``player_powers``
# (0x9048E0).  The ROM tests the *high byte* bits 0 and 1 -- word bits 8 and 9
# -- which ``powerup_bit_masks`` (0x59B64) assigns to Invisibility and
# Repulsiveness; ``PlayerPower`` is the ROM-authoritative transcription.
_POWER_INVIS = PlayerPower.INVIS        # not targeted at all (0x4176C/0x417C0)
_POWER_REPULSE = PlayerPower.REPULSE    # fled from instead (0x4185C)

# monster_shoot_axis_thresholds (0x40D8A) -- ten rows of two words, indexed by
# monster index.  Word 0 feeds the 0x80 odd-angle picker (0x418F2), word 1 the
# default cardinal/diagonal picker (0x41822).  Both are in 2-pixel units.
_MONSTER_SHOOT_AXIS_THRESHOLDS = (
    (8, 1),   # 0 ghost
    (4, 2),   # 1 grunt
    (4, 4),   # 2 demon
    (4, 4),   # 3 lobber
    (4, 2),   # 4 sorcerer
    (4, 2),   # 5 aux grunt
    (4, 1),   # 6 Death
    (0, 0),   # 7 acid
    (4, 2),   # 8 super sorcerer
    (4, 1),   # 9 IT
)

# Shooter range gates, in the 2-pixel units monster_find_and_shoot works in.
_LOBBER_MIN_RANGE = 0x14        # closer than this on both axes: back away (0x41946)
_LOBBER_MAX_RANGE = 0x2C        # further than this on either axis: no throw
_DEMON_MIN_RANGE = 0x10         # 0x41AB6/0x41AD0/0x41AE8
_DEMON_DIAG_SKEW = 0x08         # diagonal shots need |dx|-|dy| under this
# Cells a demon shot may be launched *into* (0x41A72-0x41AAE); anything else
# blocks the shot.  An empty cell always passes.
_DEMON_SHOT_PASSABLE = frozenset({
    int(MazeObjIds.TILE_STUN), int(MazeObjIds.TILE_TRAP1),
    int(MazeObjIds.TILE_TRAP2), int(MazeObjIds.TILE_TRAP3),
    int(MazeObjIds.EXIT), int(MazeObjIds.MONST_ACID),
    int(MazeObjIds.KEY), int(MazeObjIds.POWER_INVIS),
    int(MazeObjIds.POWER_REPULSE), int(MazeObjIds.POWER_REFLECT),
    int(MazeObjIds.POWER_TRANSPORT), int(MazeObjIds.TRANSPORTER),
})


# =============================================================================
# Find and shoot (0x41750)
# =============================================================================

def monster_find_and_shoot(state: GameState, slot: int, obj_type: int) -> None:
    """0x41750 -- face a player and, for shooter classes, launch a shot.

    The IT player (``player_it``) is evaluated first, biasing selection toward
    the cursed hero; otherwise the nearest player by summed absolute axis delta
    wins (§3.5).  Invisible players are invisible to this too (0x4176C/0x417C0).

    Which direction "facing" means is the family's business: an ODDANGLE level
    flag swaps in a diagonal-only picker (``_aim_direction``).  A *repulsive*
    target is fled from instead -- the direction is flipped 180 degrees
    (``eori #4`` at 0x41876/0x41AE2) -- except that demons and lobbers still
    take their shot first.
    """
    from .monsters import (
        _aim_direction as _aim_direction,
        _delta_units as _delta_units,
        _monster_index as _monster_index,
        _oddangle_override as _oddangle_override,
        _set_direction as _set_direction,
    )

    index = _monster_index(obj_type)
    target = _find_target_player(state, slot)
    if target < 0:
        return
    p = state.players[target]
    dx = _delta_units(state.mobs.hpos[p.mob_slot], state.mobs.hpos[slot])
    dv = _delta_units(state.mobs.vpos[p.mob_slot], state.mobs.vpos[slot])

    override = _oddangle_override(state, obj_type)
    thresholds = _MONSTER_SHOOT_AXIS_THRESHOLDS[index]
    threshold = thresholds[0] if override == 0x80 else thresholds[1]
    direction = _aim_direction(dx, dv, override, threshold)
    repulsive = bool(p.powers & _POWER_REPULSE)

    if obj_type == int(MazeObjIds.MONST_LOBBER):
        direction = _lobber_throw(state, slot, direction, dx, dv, target)
    elif obj_type == int(MazeObjIds.MONST_DEMON):
        if not _demon_shoot(state, slot, direction, dx, dv) and repulsive:
            direction ^= 4
    elif repulsive:
        direction ^= 4

    _set_direction(state, slot, direction)


def _lobber_throw(state: GameState, slot: int, direction: int,
                  dx: int, dv: int, target: int) -> int:
    """0x41946 -- range-gated rock throw; returns the direction to face.

    Inside 0x14 units (40 px) on *both* axes the lobber backs away instead of
    throwing; past 0x2C (88 px) on either axis, and from outside the shooter
    box, it just stands and faces.  A thrown rock is given the lead arc of
    0x419E4, not a straight direction step.
    """
    from .monsters import (
        monster_shooter_in_view as monster_shooter_in_view,
    )

    adx, adv = abs(dx), abs(dv)
    if adx < _LOBBER_MIN_RANGE and adv < _LOBBER_MIN_RANGE:
        return direction ^ 4            # too close: turn away (0x41876)
    if adx >= _LOBBER_MAX_RANGE or adv >= _LOBBER_MAX_RANGE:
        return direction
    if not monster_shooter_in_view(state, slot):
        return direction
    shot_slot = find_unused_shot(state, SLOT_LOBBER_SHOTS)
    if shot_slot is None:
        return direction
    lead = _lobber_lead(state, slot, direction, target, dx, dv)
    monster_create_shot(state, slot, direction, shot_slot, lead=lead)
    _sound_play(state, _SOUND_LOBBER_THROW)
    return direction


def _demon_shoot(state: GameState, slot: int, direction: int,
                 dx: int, dv: int) -> bool:
    """0x41A2E -- fireball if in view, in range, and the muzzle cell is clear.

    The axis gate depends on the facing: a diagonal shot also needs the two
    deltas within ``_DEMON_DIAG_SKEW`` of each other, so the demon only fires
    down a real 45-degree line.
    """
    from .monsters import (
        monster_shooter_in_view as monster_shooter_in_view,
    )

    if not monster_shooter_in_view(state, slot):
        return False
    shot_slot = find_unused_shot(state, SLOT_DEMON_SHOTS)
    if shot_slot is None:
        return False
    if not _demon_muzzle_clear(state, slot, direction):
        return False

    adx, adv = abs(dx), abs(dv)
    if direction & 1:                                   # diagonal
        if adx < _DEMON_MIN_RANGE or abs(adx - adv) >= _DEMON_DIAG_SKEW:
            return False
    elif direction in (0, 4):                           # left/right
        if adx < _DEMON_MIN_RANGE:
            return False
    elif adv < _DEMON_MIN_RANGE:                        # up/down
        return False

    monster_create_shot(state, slot, direction, shot_slot)
    return True


def _neighbor_slot(slot: int, direction: int, wrap: bool = False) -> int | None:
    """The neighbouring cell one step along ``direction``.

    ``wrap`` reproduces the masked arithmetic of 0x41A5A (``andi #0x1F`` on the
    column and ``andi #0x3E0`` on the row), which the demon shot path uses;
    everywhere else an off-grid step is simply rejected.
    """
    row, col = slot >> 5, slot & 0x1F
    step_x, step_y = _DIR_DELTAS[direction]
    nr, nc = row + step_y, col + step_x
    if wrap:
        return ((nr & 0x1F) << 5) | (nc & 0x1F)
    if not (0 <= nr < 32 and 0 <= nc < 32):
        return None
    return (nr << 5) | nc


def _demon_muzzle_clear(state: GameState, slot: int, direction: int) -> bool:
    """0x41A42-0x41AAE -- the cell the shot is launched into must be passable."""
    dest = _neighbor_slot(slot, direction, wrap=True)
    if dest is None or dest < 0x20:
        return False
    if state.mobs.picture[dest] == 0:
        return True
    return state.mobs.obj_type(dest) in _DEMON_SHOT_PASSABLE


def _find_target_player(state: GameState, slot: int) -> int:
    """Nearest active player by |dH| + |dV|, IT evaluated first.

    Distances are the byte deltas of 0x417C8-0x417EA, so they wrap the shorter
    way round the maze.  An invisible player is skipped entirely, IT included.
    The ROM walks the four slots *backwards* (D3 = 6, 4, 2, 0) and only takes a
    strictly closer one, so an exact tie is won by the **higher** player index;
    scanning forwards with ``<=`` is the same rule.
    """
    from .monsters import (
        _delta_units as _delta_units,
    )

    it = state.player_it
    if (it != 0xFFFF and 0 <= it < len(state.players)
            and state.players[it].active
            and not (state.players[it].powers & _POWER_INVIS)):
        return it

    best = -1
    best_dist = None
    for p in state.players:
        if not p.active or (p.powers & _POWER_INVIS):
            continue
        dx = _delta_units(state.mobs.hpos[p.mob_slot], state.mobs.hpos[slot])
        dv = _delta_units(state.mobs.vpos[p.mob_slot], state.mobs.vpos[slot])
        dist = abs(dx) + abs(dv)
        if best_dist is None or dist <= best_dist:
            best_dist = dist
            best = p.index
    return best


def find_unused_shot(state: GameState, shot_slots: range) -> int | None:
    """``find_unused_shot`` (0x41B16) -- a channel is free when its picture is
    clear *and* the word beside it reads zero.

    That second word is **not** the channel's own cadence timer.  The ROM
    indexes it from 0x904926 with ``slot*2``, three words below
    ``shot_timer_next``'s own base, so channel *n* is gated by the timer
    ``monster_create_shot`` wrote for channel *n+3*, and the top three lobber
    channels index past the end of that array into ``score_display_timer``
    (0x90493A) -- a floating score popup really does hold a lobber channel
    shut.  Reproduced as-is; ``_shot_gate_word`` is where the aliasing lives.
    """
    for s in shot_slots:
        if state.mobs.picture[s] == 0 and _shot_gate_word(state, s) == 0:
            return s
    return None


def _shot_gate_word(state: GameState, slot: int) -> int:
    """The 0x904926-based word ``find_unused_shot`` tests for ``slot``."""
    index = slot - 2                    # (0x904926 + slot*2 - 0x90492A) // 2
    timers = state.shot_timer_next
    if index < len(timers):
        return timers[index]
    popups = state.score_display_timer
    index -= len(timers)
    return popups[index] if index < len(popups) else 0


# Per-direction muzzle offsets, raw ROM position words indexed by the ROM
# compass.  ``monster_shot_spawn_h_offset`` (0x57B98) / ``..._v_offset``
# (0x57BA8) are the demon pair, ``lobber_shot_spawn_h/v_offset`` (0x57BB8/
# 0x57BC8) the lobber pair.  Every entry is a multiple of 0x100 -- a whole
# pixel is 0x80 -- so none of them can disturb the low field of the word they
# are added to, and they are added exactly as the ROM writes them.
_MONSTER_SHOT_SPAWN_H = (0x200, 0x500, 0x600, 0x200, 0x200, 0x000, -0x200, -0x100)
_MONSTER_SHOT_SPAWN_V = (0x500, 0x400, 0x000, 0x000, -0x200, -0x100, 0x000, 0x400)
_LOBBER_SHOT_SPAWN_H = (0x500, 0x300, 0x200, 0x000, 0x000, 0x000, 0x200, 0x300)
_LOBBER_SHOT_SPAWN_V = (0x100, 0x000, 0x000, 0x000, 0x000, 0x300, 0x200, 0x200)

# The constants the ROM adds *underneath* the position field.  0x49192/0x491A2
# mask the shooter's own words with 0xFF80 first, so these are not offsets at
# all -- they are the new projectile's low field.  A demon shot collects
# ``+0xD`` (0x491BA) and then the shared ``+1`` (0x49258), giving H low byte
# 0xE: palette 0xE with no strength bits.  A lobber gets only the ``+1``,
# palette 1.  Both get ``+9`` vertically (0x4926E), which is the packed sprite
# size -- width-1 = height-1 = 1, a 2x2-tile 16x16 px projectile.  gauntpy
# numbers both fields exactly as the ROM does, so the values carry over.
_DEMON_SHOT_HPOS_LOW = 0x0D + 0x01
_LOBBER_SHOT_HPOS_LOW = 0x01
_SHOT_VPOS_LOW = 0x09

#: ``shot_counter_reload`` (0x578C2), one word per shot channel 0-11.
_SHOT_COUNTER_RELOAD = (
    0x000F, 0x0001, 0x0001, 0x0000,      # player channels
    0x0001, 0x0001, 0x0001, 0x0001,      # demon channels
    0x0020, 0x0020, 0x0020, 0x0020,      # lobber channels
)
#: 0x49104 -- frames before that channel may fire again.
_SHOT_COOLDOWN = 0x3C
#: The lobber's flight is a lead: the target's own velocity plus four times the
#: separation.  ``player_speed_normal`` (0x580C8) and the per-direction
#: components at 0x580D8/0x580EA build the first term.
_LEAD_PLAYER_SPEED = (0x60, 0x70, 0x60, 0x80, 0x80, 0x80, 0x80, 0xA0)
_LEAD_COS = (0, 2, 2, 2, 0, -2, -2, -2, 0)  # 0x580D8, index 8 = still
_LEAD_SIN = (2, 2, 0, -2, -2, -2, 0, 2, 0)  # 0x580EA, index 8 = still
# ``joystick_nibble_to_direction`` (0x580FC), indexed by the achieved-movement
# word at 0x9048F0. A neutral 0xF nibble selects 8, the zero-padded table row.
_JOYSTICK_NIBBLE_TO_DIRECTION = (
    8, 8, 8, 8, 8, 7, 1, 0, 8, 5, 3, 4, 8, 6, 2, 8,
)
_LEAD_DELTA_SCALE = 4                        # 0x419BC/0x419C6
_LEAD_SPAWN_SCALE = 4                        # 0x419F4/0x41A0C


def monster_create_shot(state: GameState, slot: int, direction: int,
                        shot_slot: int, lead: tuple[int, int] | None = None) -> None:
    """0x490DC -- arm a projectile in one of the fixed monster channels.

    Seeds everything WP-7's mover reads: the channel cadence timer, the
    animation/lifetime counter, the owner cell, the ROM-compass direction, the
    spawn position with its per-direction muzzle offset, the projectile's
    opening frame and its place in the depth chain.  ``lead`` carries the
    lobber's computed arc vector (0x419E4-0x41A10); without it the projectile
    flies straight down its direction, which is what every other family does.

    The spawn position is rebuilt in whole ROM words rather than decoded and
    re-encoded, because the ROM's ``+0xD``/``+1``/``+9`` tails land in the low
    field, not the position field: they are the projectile's palette and its
    packed sprite size, not a pixel offset.  The muzzle offsets are position
    words in the hardware's own axes, so they simply add.
    """
    from .shots import lobber_accumulator_seed, shot_velocity

    channel = shot_slot - 1                    # shooter id, ROM's shot slot - 1
    rom_dir = (direction + 2) & 0x07

    state.shot_timer_next[shot_slot - 5] = _SHOT_COOLDOWN
    state.mobs.hpos[slot] |= _HPOS_FLAG_ATTACK          # 0x4910E
    state.shot_anim_lifetime_counter[channel] = _SHOT_COUNTER_RELOAD[channel]
    state.shot_lifetime[shot_slot] = _SHOT_COUNTER_RELOAD[channel]
    # 0x4915C stores the direction WP-7 reads back out of ``shot_direction``,
    # and everything that module indexes with it -- ``shot_velocity_x/y``
    # (0x576E2/0x57792), the projectile picture tables and ``_direction_of``'s
    # own recovery -- is on the ROM compass, not gauntpy's.
    state.shot_direction[channel] = rom_dir
    state.shot_owner_mob[channel] = slot                # active_mob_ids[shot-1]

    # 0x49192/0x491A2: the projectile inherits only the shooter's *position*
    # field -- the shooter's palette (its health nibble) and its 3x3 sprite
    # size are masked off, and the class constants below replace them.
    base_h = position_field(state.mobs.hpos[slot])
    base_v = position_field(state.mobs.vpos[slot])
    if lead is None:
        off_h = _MONSTER_SHOT_SPAWN_H[rom_dir]
        off_v = _MONSTER_SHOT_SPAWN_V[rom_dir]
        hpos_low = _DEMON_SHOT_HPOS_LOW
    else:
        off_h = _LOBBER_SHOT_SPAWN_H[rom_dir]
        off_v = _LOBBER_SHOT_SPAWN_V[rom_dir]
        hpos_low = _LOBBER_SHOT_HPOS_LOW
    state.mobs.hpos[shot_slot] = (base_h + off_h + hpos_low) & 0xFFFF
    state.mobs.vpos[shot_slot] = (base_v + off_v + _SHOT_VPOS_LOW) & 0xFFFF
    state.mobs.picture[shot_slot] = _spawn_shot_picture(state, channel)
    _depth_place_shot(state, shot_slot)

    if lead is None:
        vec_h, vec_v = shot_velocity(state, channel, rom_dir)
        state.shot_dx[shot_slot] = vec_h >> POS_SHIFT
        state.shot_dy[shot_slot] = vec_v >> POS_SHIFT
    else:
        vec_h, vec_v = lead
        state.lobber_shot_vec_h[shot_slot - 9] = vec_h
        state.lobber_shot_vec_v[shot_slot - 9] = vec_v
        # 0x49216/0x4922A -- WP-7 owns the accumulator/MOB-word relationship.
        lobber_accumulator_seed(state, channel)
        # WP-7 moves shots by whole pixels, so round rather than truncate: a
        # lob that leads by 1.5 px/frame otherwise degenerates to 1.
        state.shot_dx[shot_slot] = _round_div(vec_h, 128)
        state.shot_dy[shot_slot] = _round_div(vec_v, 128)


def _depth_place_shot(state: GameState, shot_slot: int) -> None:
    """0x49274-0x492B6 -- key the new channel into the depth chain at its cell.

    The ROM derives the cell from the H/V words it has just written, with the
    same +12/+8 px sprite biases the per-frame re-key uses, and hands both to
    ``insert_mob_depth_sorted``.  Without it the channel's ``mob_depth_key``
    stays zero, and the very next ``main_handle_shots`` probes for collisions
    from cell 0 -- the top-left corner of the maze -- and destroys the shot on
    the frame after it was fired.
    """
    from .shots import shot_cell     # WP-7 owns the shot cell geometry

    state.mobs.unlink(shot_slot)
    state.mobs.insert(shot_slot, depth_key=shot_cell(state, shot_slot))


def _spawn_shot_picture(state: GameState, channel: int) -> int:
    """The frame 0x491D2 (demon) / 0x49238 (lobber) arms a channel with.

    Both are the ordinary projectile animation evaluated at the counter the
    channel was just seeded with, so the projectile is drawn as real artwork
    for the rest of the frame it is created in.  That matters because
    ``main_handle_shots`` (0x474F6) has already run by the time
    ``main_move_monsters`` (0x49034) fires: the picture written here is the one
    the renderer shows until the *next* frame's animation tick.

    The two creation sites read their tables at different counters -- 0x491D8
    hardcodes index 0 for a demon shot (which is where the reload of 1
    pre-decrements to on that next tick), while 0x49240 uses the lobber's
    freshly stored reload -- and neither consults the shot's strength tier,
    which the H word written just above has in any case cleared.
    """
    from .shots import shot_picture   # WP-7 owns the three ROM picture tables

    counter = (_SHOT_COUNTER_RELOAD[channel]
               if channel + 1 in SLOT_LOBBER_SHOTS else 0)
    return shot_picture(state, channel, counter)


def _round_div(value: int, divisor: int) -> int:
    return -((-value + divisor // 2) // divisor) if value < 0 else (value + divisor // 2) // divisor


def _lobber_lead(state: GameState, slot: int, direction: int, target: int,
                 dx: int, dv: int) -> tuple[int, int]:
    """0x41978-0x41A10 -- where the rock is thrown, not where the player is.

    The arc vector is the target's *current* walking velocity plus four times
    the separation, less the muzzle offset -- so a lobber leads a running hero
    and drops the rock where they are heading.
    """
    from .monster_movement import (
        _s16 as _s16,
    )

    p = state.players[target]
    speed_row = ((p.character & 0x03)
                 + (4 if p.powers & PlayerPower.SPEED else 0))
    speed = _LEAD_PLAYER_SPEED[speed_row]
    move_nibble = (state.player_joystick[target] >> 4) & 0x0F
    rom_move = _JOYSTICK_NIBBLE_TO_DIRECTION[move_nibble]
    vec_h = speed * _LEAD_COS[rom_move]
    vec_v = speed * _LEAD_SIN[rom_move]

    # The separation terms: the ROM adds 2 to the horizontal delta first
    # (0x419BA); both deltas are already in its own axes.
    vec_h += (dx + 2) * _LEAD_DELTA_SCALE
    vec_v += dv * _LEAD_DELTA_SCALE

    rom_dir = (direction + 2) & 0x07
    vec_h -= (_LOBBER_SHOT_SPAWN_H[rom_dir] >> 8) * _LEAD_SPAWN_SCALE
    vec_v -= (_LOBBER_SHOT_SPAWN_V[rom_dir] >> 8) * _LEAD_SPAWN_SCALE
    return _s16(vec_h), _s16(vec_v)
