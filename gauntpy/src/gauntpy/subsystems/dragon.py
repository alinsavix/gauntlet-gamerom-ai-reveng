"""Dragon runtime state, pose selection, and fire control -- WP-9.

The data and state transitions here are transcribed from 0x53D10--0x549E8,
including the dragon-kill secret hook at 0x54420.
The renderer consumes the resulting segment pictures and head position; this
module keeps the ROM's state-machine and projectile decisions independent of it.

The dragon owns no projectile channel of its own: ``dragon_find_free_shot_slot``
(0x540E8) hands its fire one of the four *monster* shot channels, MOB slots 5-8,
so everything after ``_dragon_fire_setup`` -- animation, motion, collision box,
damage row -- is ``shots.py``'s demon path acting on the H word written here.
"""

from __future__ import annotations

from ..constants import MazeObjIds
from ..coords import (
    POS_SHIFT,
    hpos_x,
    pack_slot,
    position_field,
    vpos_v,
    vpos_y,
)
from ..state import GameState
from .sound import sound_play as _sound_play

_SOUND_DRAGON_HIT = 0x3A
_FIRE_COOLDOWN = 8
_DRAGON_MAX_HITS = 9

# dragon_state (0x904890).  Bit 0 is the sleeping/wake transition, not the
# active pursuit state; the old private _ST_AWAKE name is retained for callers
# that used the previous module.
_ST_WAKING = 0x01
_ST_AWAKE = _ST_WAKING
_ST_STUNNED = 0x02
_ST_TURNING = 0x04
_ST_LOCKED = 0x08

_DRAGON_PATH_PROGRAMS = (
    (0, 1, 0, 2, 4, 6, 7, 6, 4, 2, 3, 2, 4, 5, 4, 2),
    (0, 2, 4, 6, 7, 5, 3, 1, 0, 2, 4, 6, 7, 5, 3, 1),
    (0, 1, 3, 2, 4, 6, 7, 5, 4, 2, 3, 5, 4, 2, 3, 1),
    (0, 2, 4, 7, 5, 3, 4, 7, 4, 2, 1, 0, 2, 4, 5, 2),
    (0, 3, 4, 7, 6, 5, 2, 1, 2, 4, 7, 5, 4, 2, 3, 1),
)

# ROM 0x5D438 / 0x5D478, in whole world pixels (the raw words are all
# multiples of 0x80, one native position unit per pixel) and in the hardware's
# own axes, so a positive V delta walks the head *up* the screen.  These are
# **32-entry** tables indexed by
# ``raw path byte + facing * 4`` (0x54616-0x54626) -- not the 16-entry
# ``pose + facing*2`` index the fire/segment tables use.  Each (pose, facing)
# therefore owns *two* adjacent entries, selected by the path byte's fire bit:
# the head lengthens along the facing when the mouth opens.
_HEAD_HDELTA = (
    20, 20, 12, 12, 4, 4, -4, -4,       # facing 0 (up): pose ramp
    9, 19, 9, 19, 9, 19, 9, 19,         # facing 2 (right): mouth extends right
    20, 20, 12, 12, 4, 4, -4, -4,       # facing 4 (down): pose ramp
    4, -6, 4, -6, 4, -6, 4, -6,         # facing 6 (left): mouth extends left
)
_HEAD_VDELTA = (
    8, 18, 8, 18, 8, 18, 8, 18,         # facing 0: mouth extends up
    20, 20, 12, 12, 4, 4, -4, -4,       # facing 2: pose ramp
    4, -6, 4, -6, 4, -6, 4, -6,         # facing 4: mouth extends down
    20, 20, 12, 12, 4, 4, -4, -4,       # facing 6: pose ramp
)
# The dragon's own fire tables, all transcribed from ``row76.bin``.
# ``dragon_fire_segment_tbl`` (0x5D4B8) picks which of the four 2x2 segment
# MOBs owns the shot; the two pose tables (0x5D4C8/0x5D4E8) and the two facing
# tables (0x5D428/0x5D430) are the muzzle offset.  Every entry is a multiple of
# 0x80 -- a whole pixel -- so the tables are stated in pixels here and shifted
# back by ``POS_SHIFT`` on use, the same way ``_HEAD_HDELTA`` above is.
# Both axes keep the hardware's sense, so a positive V entry walks *up*.
_DRAGON_FIRE_SEGMENT_TBL = (
    3, 3, 1, 1, 3, 3, 2, 2,
    2, 2, 0, 0, 1, 1, 0, 0,
)
_FIRE_H_BY_FACING = (-4, 6, -4, -13)        # 0x5D428, index = facing >> 1
_FIRE_V_BY_FACING = (5, -4, -11, -4)        # 0x5D430
_FIRE_H_BY_POSE = (                          # 0x5D4C8, index = pose + facing*2
    20, 12, 4, -4,
    24, 24, 24, 24,
    20, 12, 4, -4,
    -8, -8, -8, -8,
)
_FIRE_V_BY_POSE = (                          # 0x5D4E8
    24, 24, 24, 24,
    20, 12, 4, -4,
    -8, -8, -8, -8,
    20, 12, 4, -4,
)

# The low bits each branch adds on top of the masked position word.  These are
# not offsets: the ROM has already cleared bits 0-6 of the segment's own word,
# so ``+0x30 +8`` (0x54866/0x5486A) and ``+0x20 +0xE`` (0x548E8/0x548EC) *are*
# the new H word's flags-and-palette byte, and ``+0x12`` (0x5488C) / ``+9``
# (0x54900) are the V word's packed sprite size.  gauntpy numbers both fields
# exactly as the ROM does (palette 0x0F, software flags 0x30, width bits 5-3,
# height bits 2-0), so the constants carry over unchanged.
_BREATH_HPOS_LOW = 0x30 + 0x08      # tier bits 0x30 (max tier), palette 8
_BREATH_VPOS_LOW = 0x12             # 3x3 tiles
_FIREBALL_HPOS_LOW = 0x20 + 0x0E    # tier bits 0x20, palette 0xE
_FIREBALL_VPOS_LOW = 0x09           # 2x2 tiles
# 0x54814: the breath's animation/lifetime counter, the top of its 20-entry
# block in ``special_projectile_picture_table``.
_BREATH_COUNTER = 0x13
# 0x578C2 ``shot_counter_reload`` for the demon channels the dragon fires into.
_FIREBALL_COUNTER = 0x01
# 0x546DC/0x546E2 and 0x54710: the dragon breathes when the nearest hero is
# within three cells of its firing line.  ``dragon_move_state``'s high byte is
# that cross-axis distance in cells (0x5406A builds it as ``dist << 4``).
_BREATH_RANGE_CELLS = 3
_DRAGON_TARGET_LIMIT = 16 * 15
_DRAGON_PROBE_OFFSETS_A = (0, -0x40, 2, -0x20, 1, 0x20, -1, 0)
_DRAGON_PROBE_OFFSETS_B = (1, -0x40, 2, 0, 0, 0x20, -1, -0x20)
_DRAGON_HEAD_PICS = (
    # dragon_head_picture_tbl (0x5D528), 32 words on the same
    # ``raw byte + facing*4`` index as the two head delta tables.
    0xA2E0, 0xA2F0, 0xA2C0, 0xA2D0, 0xA2A0, 0xA2B0, 0xA280, 0xA290,
    0xA180, 0xA190, 0xA1A0, 0xA1B0, 0xA1C0, 0xA1D0, 0xA1E0, 0xA1F0,
    0xA260, 0xA270, 0xA240, 0xA250, 0xA220, 0xA230, 0xA200, 0xA210,
    0xA100, 0xA110, 0xA120, 0xA130, 0xA140, 0xA150, 0xA160, 0xA170,
)

# The special-shot family at ROM 0x58EDE is the *monster* projectile table;
# the dragon's own artwork comes from ``special_projectile_picture_table``
# (0x58E3E) for the breath and ``projectile_picture_table`` (0x58B8A) for the
# long-range fireball, both picked by ``shots.shot_picture``.


def setup_dragon_segments(state: GameState, primary_slot: int) -> None:
    """0x5496E -- initialize the four-slot 2×2 dragon footprint."""
    row = primary_slot & 0x3E0
    right = row | ((primary_slot + 1) & 0x1F)
    state.dragon_seg_mob_ids = [
        primary_slot,
        (primary_slot - 0x20) & 0x3FF,
        right,
        (right - 0x20) & 0x3FF,
    ]
    state.dragon_mob_slot = primary_slot
    state.dragon_state = _ST_WAKING
    state.dragon_anim_ctr = 0
    state.dragon_facing = 4
    state.dragon_move_state = 0x1044
    state.dragon_hits = 0
    _update_dragon_pose(state, primary_slot)


def _segments(state: GameState) -> list[int]:
    """Return the ROM segment array, deriving it for legacy level setup."""
    segments = state.dragon_seg_mob_ids
    if segments[0] == 0 and state.dragon_mob_slot:
        primary = state.dragon_mob_slot
        row = primary & 0x3E0
        right = row | ((primary + 1) & 0x1F)
        state.dragon_seg_mob_ids = [
            primary,
            (primary - 0x20) & 0x3FF,
            right,
            (right - 0x20) & 0x3FF,
        ]
        segments = state.dragon_seg_mob_ids
    elif segments[0]:
        state.dragon_mob_slot = segments[0]
    return segments


def _dragon_slot(state: GameState) -> int | None:
    if (
        state.dragon_seg_mob_ids[0] == 0
        and state.dragon_mob_slot
        and state.mobs.obj_type(state.dragon_mob_slot) == int(MazeObjIds.MONST_DRAGON)
    ):
        setup_dragon_segments(state, state.dragon_mob_slot)
    segments = _segments(state)
    slot = segments[0] if segments else 0
    if slot and state.mobs.obj_type(slot) == int(MazeObjIds.MONST_DRAGON):
        return slot
    if state.dragon_mob_slot and state.mobs.obj_type(state.dragon_mob_slot) == int(MazeObjIds.MONST_DRAGON):
        if not state.dragon_seg_mob_ids[0]:
            setup_dragon_segments(state, state.dragon_mob_slot)
        return state.dragon_mob_slot
    for slot in state.mobs.iter_chain():
        if state.mobs.obj_type(slot) == int(MazeObjIds.MONST_DRAGON):
            setup_dragon_segments(state, slot)
            return slot
    return None


def _current_path_byte(state: GameState) -> int:
    program = _DRAGON_PATH_PROGRAMS[state.dragon_path_num % len(_DRAGON_PATH_PROGRAMS)]
    return program[(state.dragon_anim_ctr & 0x7F) >> 3]


def _pose_index(state: GameState) -> int:
    """0x53D5C-0x53D70 / 0x54790-0x5479E -- ``(byte >> 1) + facing * 2``.

    The 16-entry index the *fire* tables use: ``dragon_fire_segment_tbl``
    (0x5D4B8) and the two muzzle-offset tables (0x5D4C8/0x5D4E8).  It throws
    the path byte's fire bit away, because a shot is only ever set up on a
    frame where that bit is already known to be set.
    """
    pose = _current_path_byte(state) >> 1
    return pose + ((state.dragon_facing & 0x06) << 1)


def _head_index(state: GameState) -> int:
    """0x54616-0x54626 -- ``raw path byte + facing * 4``.

    The 32-entry index the *head* tables use: ``dragon_head_picture_tbl``
    (0x5D528) and the two head delta tables (0x5D438/0x5D478).  It keeps the
    fire bit, so each (pose, facing) has a mouth-closed and a mouth-open
    entry -- which is exactly the pair the delta tables differ on.  This is
    twice ``_pose_index`` plus the fire bit, never the same number.
    """
    return _current_path_byte(state) + (state.dragon_facing & 0x06) * 4


def _update_dragon_pose(state: GameState, head_slot: int) -> None:
    """0x545FA--0x546A4 -- publish the current head picture and hitbox origin.

    The ROM rebuilds both head words as ``(delta + segment word) & 0xFF80``,
    so they carry a position field and nothing else -- no palette, no sprite
    size.  Its vertical axis grows upward, and so does the stored V word, so a
    positive V delta simply adds.
    """
    index = _head_index(state)
    state.mobs.picture[head_slot] = _DRAGON_HEAD_PICS[index]
    state.dragon_head_hpos = (
        state.mobs.hpos[head_slot] + (_HEAD_HDELTA[index] << POS_SHIFT)
    )
    state.dragon_head_hpos = position_field(state.dragon_head_hpos)
    state.dragon_head_vpos = (
        state.mobs.vpos[head_slot] + (_HEAD_VDELTA[index] << POS_SHIFT)
    )
    state.dragon_head_vpos = position_field(state.dragon_head_vpos)


def _player_cell(state: GameState, player_index: int) -> tuple[int, int]:
    player = state.players[player_index]
    x = hpos_x(state.mobs.hpos[player.mob_slot])
    y = vpos_y(state.mobs.vpos[player.mob_slot])
    return y >> 4, x >> 4


def _nearby_player(state: GameState, head_slot: int) -> bool:
    """The proximity envelope behind ``dragon_player_proximity`` (0x549EA)."""
    head_row, head_col = head_slot >> 5, head_slot & 0x1F
    for player in state.players:
        if not player.active or player.mob_slot == 0:
            continue
        row, col = _player_cell(state, player.index)
        dx = abs(col - head_col)
        dy = abs(row - head_row)
        if state.wrap_h:
            dx = min(dx, 32 - dx)
        if state.wrap_v:
            dy = min(dy, 32 - dy)
        if dx <= 9 and dy <= 5:
            return True
    return False


def _tile_near_screen(state: GameState, slot: int) -> bool:
    """tile_near_screen_test 0x5E5D8, including its unsigned edge tests."""
    h_delta = (
        (((slot & 0x1F) << 4) << POS_SHIFT)
        + 0x0780
        - (state.scroll_x << POS_SHIFT)
    ) & 0xFFFF
    if h_delta >= 0x7B80:
        return False

    native_v = ((((slot & 0x3E0) ^ 0x3E0) >> 1) << POS_SHIFT) & 0xFFFF
    v_origin = ((0x108 - state.scroll_y) << POS_SHIFT) & 0xFFFF
    return ((native_v - v_origin + 0x0380) & 0xFFFF) < 0x7F80


def dragon_any_segment_near_screen(state: GameState) -> bool:
    """0x54AF8 -- test all four packed dragon segment cells."""
    segments = state.dragon_seg_mob_ids
    if not segments[0]:
        return False
    return any(_tile_near_screen(state, slot) for slot in segments)


def _select_new_path(state: GameState) -> None:
    state.dragon_path_num = state.getrandom(len(_DRAGON_PATH_PROGRAMS))


def _advance_wake_or_turn(state: GameState, head_slot: int) -> bool:
    """Run a transition frame and return whether normal path execution is blocked."""
    if state.dragon_state & _ST_WAKING:
        if state.dragon_anim_ctr == 0:
            if _nearby_player(state, head_slot):
                state.dragon_anim_ctr = 0x31
            return True
        was_positive = state.dragon_anim_ctr > 0
        state.dragon_anim_ctr += -1 if was_positive else 1
        if state.dragon_anim_ctr == 0 and was_positive:
            state.dragon_state &= ~_ST_WAKING
            _select_new_path(state)
        return True

    if state.dragon_state & _ST_TURNING:
        state.dragon_anim_ctr += -1 if state.dragon_anim_ctr > 0 else 1
        if state.dragon_anim_ctr == 0:
            state.dragon_state &= ~_ST_TURNING
            _select_new_path(state)
        return True

    return False


def _dragon_probe_open(state: GameState, head_slot: int, direction: int) -> bool:
    """Test the two leading footprint cells used by 0x53E4A."""
    slots = []
    for offsets in (_DRAGON_PROBE_OFFSETS_A, _DRAGON_PROBE_OFFSETS_B):
        col = (head_slot + offsets[direction]) & 0x1F
        row = ((head_slot & 0x3E0) + offsets[direction + 1]) & 0x7FF
        slots.append((row + col) & 0x7FF)
    if slots[0] < 0x20:
        return False
    return all(
        slot < len(state.mobs.picture)
        and state.mobs.picture[slot] != 0x8000
        for slot in slots
    )


def _choose_move_direction(state: GameState, head_slot: int) -> None:
    """Pack the closest legal player, facing, and distance exactly as 0x53E4A."""
    dragon_x = hpos_x(state.mobs.hpos[head_slot]) + 16
    dragon_y = vpos_y(state.mobs.vpos[head_slot])
    chosen_player = 4
    chosen_direction = state.dragon_facing & 0x06
    chosen_distance = _DRAGON_TARGET_LIMIT

    for player in reversed(state.players):
        if not player.active or player.mob_slot == 0 or player.health <= 0:
            continue
        player_x = hpos_x(state.mobs.hpos[player.mob_slot]) + 12
        player_y = vpos_y(state.mobs.vpos[player.mob_slot]) + 8
        dx = player_x - dragon_x
        dy = player_y - dragon_y
        if dx > 0x100:
            dx -= 0x200
        elif dx < -0x100:
            dx += 0x200
        abs_x, abs_y = abs(dx), abs(dy)

        if abs_x < abs_y:
            direction = 4 if dy > 0 else 0
            distance = abs_y
        elif abs_y < abs_x:
            direction = 2 if dx > 0 else 6
            distance = abs_x
        else:
            direction = state.dragon_facing & 0x06
            distance = abs_y if direction in (0, 4) else abs_x

        if (
            distance < chosen_distance
            and _dragon_probe_open(state, head_slot, direction)
        ):
            chosen_player = player.index
            chosen_direction = direction
            chosen_distance = distance

    if chosen_player == 4:
        packed = 4 | ((state.dragon_facing & 0x06) << 4) | 0x1000
    else:
        packed = (
            chosen_player
            | (chosen_direction << 4)
            | ((chosen_distance << 4) & 0xFF00)
        )
    if packed == state.dragon_move_state:
        return
    state.dragon_move_state = packed

    old_direction = state.dragon_facing & 0x06
    if chosen_player == 4 or chosen_direction == old_direction:
        return
    turn = old_direction - chosen_direction
    if turn == -6:
        turn = 2
    elif turn == 6:
        turn = -2
    state.dragon_anim_ctr = turn << 3
    state.dragon_anim_ctr += 1 if state.dragon_anim_ctr > 0 else -1
    state.dragon_facing = chosen_direction
    state.dragon_state |= _ST_TURNING


def _update_fire_lock(state: GameState, head_slot: int) -> None:
    """Hold a close firing pose while its selected player stays on the line."""
    player_index = state.dragon_move_state & 0x0F
    facing = state.dragon_facing & 0x06
    if (
        player_index >= len(state.players)
        or (state.dragon_move_state >> 8) > _BREATH_RANGE_CELLS
        or ((state.dragon_move_state >> 4) & 0x0F) != facing
    ):
        state.dragon_state &= ~_ST_LOCKED
        return

    pose = _pose_index(state)
    muzzle_x = (
        hpos_x(state.mobs.hpos[head_slot])
        + _FIRE_H_BY_POSE[pose]
        + _FIRE_H_BY_FACING[facing >> 1]
    )
    muzzle_v = (
        vpos_v(state.mobs.vpos[head_slot])
        + _FIRE_V_BY_POSE[pose]
        + _FIRE_V_BY_FACING[facing >> 1]
    )
    player = state.players[player_index]
    player_x = hpos_x(state.mobs.hpos[player.mob_slot])
    player_v = vpos_v(state.mobs.vpos[player.mob_slot])
    delta_x = muzzle_x - player_x
    if delta_x > 0x100:
        delta_x -= 0x200
    elif delta_x < -0x100:
        delta_x += 0x200
    aligned = (
        -17 < delta_x < 18
        if facing in (0, 4)
        else -17 < (muzzle_v - player_v) < 17
    )
    if aligned:
        state.dragon_state |= _ST_LOCKED
    else:
        state.dragon_state &= ~_ST_LOCKED


def _dragon_find_free_shot_slot(state: GameState) -> int | None:
    """0x540E8 -- scan the demon projectile channels, MOB slot 8 down to 5.

    The dragon does not own channels of its own: it borrows the four ordinary
    monster-shot channels, which is why its fire is animated, moved and scored
    by the *demon* half of ``shots.py`` and not the lobber half.
    """
    for slot in range(8, 4, -1):
        if state.mobs.picture[slot] == 0:
            return slot
    return None


def _breathing(state: GameState) -> bool:
    """0x546D6-0x546E2 -- close-range breath, or the long-range fireball?

    ``dragon_move_state``'s high byte is the winning candidate's cross-axis
    distance in cells (0x5406A stores ``dist << 4`` into the word), read back
    with ``asr.w #8`` -- signed.  Three cells or less and the dragon breathes.
    """
    high = ((state.dragon_move_state & 0xFFFF) ^ 0x8000) - 0x8000
    return (high >> 8) <= _BREATH_RANGE_CELLS


def _dragon_fire_setup(state: GameState, shot_slot: int) -> None:
    """0x54748 -- arm one demon channel with the dragon's projectile.

    Everything is written for the channel, ``shot_slot - 1``, never for the
    MOB slot: ``active_mob_ids`` (0x547CA), ``shot_direction`` (0x547D8) and
    ``shot_anim_lifetime_counter`` (0x54816/0x548AE) are all indexed that way.
    Indexing them by the MOB slot instead silently rearms a *different* live
    channel -- slot 8 lands on lobber channel 8's words, slots 6 and 7 on the
    demon channels either side.

    The two branches differ in more than artwork.  The close-range breath
    (0x5480A) is a max-tier shot: its H word carries the 0x30 strength bits,
    which is what makes ``shots.py`` give it the large fixed hitbox, the
    0x50 velocity block, its every-other-frame cadence, the
    ``special_projectile_picture_table`` animation and the tier-3 row of
    ``monstshot_damage_tbl`` -- the row that also raises the "shoot the
    dragon's head" dialog and spends the *Don't Get Hit* objective.  The
    long-range fireball (0x54894) is an ordinary tier-2 shot.

    Position is taken from ``dragon_seg_mob_ids[0]`` (0x547DC/0x547EE), even
    though the *owner* recorded for the shot is the pose-selected segment.
    """
    from .shots import shot_cell, shot_picture, shot_velocity

    channel = shot_slot - 1
    segments = _segments(state)
    pose = _pose_index(state)
    segment_index = _DRAGON_FIRE_SEGMENT_TBL[pose]
    source_slot = segments[segment_index] if segment_index < len(segments) else 0
    if source_slot == 0:
        source_slot = segments[0]
    head_slot = segments[0] or source_slot

    facing = state.dragon_facing & 0x06
    rom_dir = facing

    state.dragon_fire_cooldown = _FIRE_COOLDOWN         # 0x54764
    state.shot_owner_mob[channel] = source_slot         # 0x547CA
    state.shot_direction[channel] = rom_dir             # 0x547D8

    if _breathing(state):
        counter = _BREATH_COUNTER
        off_h = _FIRE_H_BY_FACING[facing >> 1] + _FIRE_H_BY_POSE[pose]
        off_v = _FIRE_V_BY_FACING[facing >> 1] + _FIRE_V_BY_POSE[pose]
        hpos_low, vpos_low = _BREATH_HPOS_LOW, _BREATH_VPOS_LOW
    else:
        from .shots import _SHOT_COUNTER_RELOAD

        counter = _SHOT_COUNTER_RELOAD[channel]
        off_h = _FIRE_H_BY_POSE[pose]
        off_v = _FIRE_V_BY_POSE[pose]
        hpos_low, vpos_low = _FIREBALL_HPOS_LOW, _FIREBALL_VPOS_LOW

    state.shot_anim_lifetime_counter[channel] = counter
    # The H word must carry its strength bits before anything reads the tier,
    # so write the MOB words first and pick the picture from them.
    state.mobs.hpos[shot_slot] = (
        position_field(state.mobs.hpos[head_slot])
        + (off_h << POS_SHIFT) + hpos_low
    ) & 0xFFFF
    # Both the ROM's muzzle offsets and the stored V word grow upward, so the
    # offset simply adds.
    state.mobs.vpos[shot_slot] = (
        position_field(state.mobs.vpos[head_slot])
        + (off_v << POS_SHIFT) + vpos_low
    ) & 0xFFFF
    state.mobs.picture[shot_slot] = shot_picture(state, channel, counter)

    # 0x54952: the ROM depth-places the new channel from the words it has just
    # written.  Without it the channel keeps a zero depth key and the next
    # ``main_handle_shots`` probes for collisions from the maze's top-left.
    state.mobs.unlink(shot_slot)
    state.mobs.insert(shot_slot, depth_key=shot_cell(state, shot_slot))

    dx, dy = shot_velocity(state, channel, rom_dir)
    state.shot_dx[shot_slot] = dx >> POS_SHIFT
    state.shot_dy[shot_slot] = dy >> POS_SHIFT
    state.shot_lifetime[shot_slot] = 0      # port-side frame count, no ROM word


def _run_active_path(state: GameState, head_slot: int) -> None:
    path_byte = _current_path_byte(state)
    held_fire_phase = (
        bool(state.dragon_state & _ST_LOCKED)
        and (state.dragon_anim_ctr & 7) == 0
        and bool(path_byte & 1)
    )
    if not held_fire_phase:
        state.dragon_anim_ctr = (state.dragon_anim_ctr + 1) & 0x7F
        state.dragon_fire_cooldown = 0

    if state.dragon_anim_ctr & 7:
        _update_fire_lock(state, head_slot)
        return

    _update_dragon_pose(state, head_slot)
    if (
        _current_path_byte(state) & 1
        and state.dragon_fire_cooldown == 0
        and (state.dragon_move_state & 0x0F) < 4
    ):
        shot_slot = _dragon_find_free_shot_slot(state)
        if shot_slot is not None:
            _dragon_fire_setup(state, shot_slot)
    _choose_move_direction(state, head_slot)
    _update_fire_lock(state, head_slot)


def main_handle_dragon(state: GameState) -> None:
    """0x54454 -- advance the dragon's transition, path pose, and fire gates."""
    head_slot = _dragon_slot(state)
    if head_slot is None:
        return

    if state.dragon_fire_cooldown > 0:
        state.dragon_fire_cooldown -= 1

    if _advance_wake_or_turn(state, head_slot):
        return
    if state.dragon_state & _ST_STUNNED:
        return
    _run_active_path(state, head_slot)


def _switch_path_matching_byte(state: GameState, old_byte: int) -> None:
    """0x5419A--0x541E8 -- randomize then fast-forward to the same path byte."""
    _select_new_path(state)
    state.dragon_anim_ctr = 0
    for _ in range(len(_DRAGON_PATH_PROGRAMS) * 16):
        if _current_path_byte(state) == old_byte:
            return
        state.dragon_anim_ctr += 8
        if state.dragon_anim_ctr <= 0x7F:
            continue
        state.dragon_anim_ctr = 0
        state.dragon_path_num = (state.dragon_path_num + 1) % len(_DRAGON_PATH_PROGRAMS)


def _dragon_die(state: GameState, shooter_id: int) -> None:
    primary = _segments(state)[0]
    dragon_x = hpos_x(state.mobs.hpos[primary])
    dragon_y = vpos_y(state.mobs.vpos[primary])
    facing_index = (state.dragon_facing & 0x06) >> 1
    loot_a_h = (0, 16, 0, 0)
    loot_a_v = (-16, 0, 0, 0)
    loot_b_h = (0, -16, 0, 16)
    loot_b_v = (16, 0, -16, 0)

    from .shots import tport_cycle_start

    original_hpos = state.mobs.hpos[primary]
    original_vpos = state.mobs.vpos[primary]
    state.mobs.hpos[primary] = (
        position_field(original_hpos) + (8 << POS_SHIFT)
    ) & 0xFFFF
    state.mobs.vpos[primary] = (
        position_field(original_vpos) + (8 << POS_SHIFT)
    ) & 0xFFFF
    tport_cycle_start(state, primary, shooter_id)
    state.mobs.hpos[primary] = original_hpos
    state.mobs.vpos[primary] = original_vpos
    for slot in _segments(state):
        if slot:
            state.mobs.unlink_and_clear(slot)
    state.dragon_seg_mob_ids = [0] * 4
    state.dragon_mob_slot = 0
    state.dragon_state = 0
    state.dragon_head_hpos = 0
    state.dragon_head_vpos = 0

    from ..maze import placement_base_picture, placement_geometry

    def spawn_loot(obj_type: MazeObjIds, x: int, y: int, picture: int) -> None:
        slot = pack_slot(((y + 8) >> 4) & 0x1F, ((x + 8) >> 4) & 0x1F)
        hpos, vpos = placement_geometry(int(obj_type), slot)
        state.mobs.create(slot, picture, hpos, vpos, int(obj_type), 0)

    spawn_loot(
        MazeObjIds.TREASURE_BAG,
        dragon_x + loot_a_h[facing_index],
        dragon_y + loot_a_v[facing_index],
        placement_base_picture(int(MazeObjIds.TREASURE_BAG)),
    )
    spawn_loot(
        MazeObjIds.HIDDENPOT,
        dragon_x + loot_a_h[facing_index] + loot_b_h[facing_index],
        dragon_y + loot_a_v[facing_index] + loot_b_v[facing_index],
        0xA728 + (state.getrandom(6) << 2),
    )
    state.secret_need_hint = 1
    state.special_bonus_score = 2000

    # 0x54420: finishing the dragon completes the "Don't Get Hit" objective
    # unless this shooter was already disqualified (flag value 1).
    if not 0 <= shooter_id < len(state.secret_tricks_flags):
        return
    if state.secret_tricks_flags[shooter_id] == 1:
        return
    from .exits import TRICK_NOGETHIT, secret_trick_set

    secret_trick_set(state, shooter_id, TRICK_NOGETHIT, 2)


def dragon_shot_hit(state: GameState, target_slot: int, shooter_id: int) -> None:
    """0x54112 -- apply a player shot only to an exposed, active dragon head."""
    if target_slot < 0x400:
        return
    if state.dragon_state & (_ST_WAKING | _ST_TURNING):
        return
    old_byte = _current_path_byte(state)
    if not (old_byte & 1):
        return

    _sound_play(state, _SOUND_DRAGON_HIT)
    state.dragon_hits += 1
    if state.dragon_hits >= _DRAGON_MAX_HITS:
        _dragon_die(state, shooter_id)
        return
    _switch_path_matching_byte(state, old_byte)
    primary = state.dragon_seg_mob_ids[0]
    if primary:
        # 0x541E8-0x5422A: hits 1-2/3-5/6-8 select palettes 8/7/6.
        palette = 5 + (11 - state.dragon_hits) // 3
        state.mobs.hpos[primary] = (
            state.mobs.hpos[primary] & 0xFFF0
        ) | palette
