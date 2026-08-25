"""The thief and mugger -- WP-10.

Reference: ``doc/04_game_subsystems.md`` §9, ``doc/05_data_reference.md``,
and the checked ``row76.bin`` routines at 0x4DEB8-0x4FEB0.
"""

from __future__ import annotations

from ..constants import FIRST_PLAYABLE_SLOT, MazeObjIds
from ..coords import (
    decode_hpos,
    decode_vpos,
    encode_hpos,
    encode_vpos_at_y,
    hpos_x,
    mob_cell_of,
    vpos_y,
)
from ..state import GameState
from .sound import sound_play as _sound_play

_WORLD_PIXELS = 512


# ram.thief_mode, 0x904BA0.
THIEF_DEAD = 0
THIEF_PURSUE = 1
THIEF_ESCAPE = 2
THIEF_JUMPJUMP = 4
THIEF_DODGE = 8
THIEF_ENTER_OK = 16
THIEF_ENTER_OK_MUGGER = 32
THIEF_IS_MUGGER = 128

# thief_speed / mugger_speed, ROM 3*0x80 and 4*0x80 native position words.
_SPEED_MUGGER = 0x180
_SPEED_THIEF = 0x200
_THIEF_MAZE_LIMIT = 0x73
_THIEF_MIN_LEVEL = 6
_THIEF_CARRIED_EMPTY = 0x7D30
_TAUNT_THRESHOLD = 0x3B
_TAUNT_PAIRS = ((0x62, 0x63), (0x64, 0x65))

# 0x5B62E and 0x5B63A.
_STEALABLE_POWER_MASKS = (0x10, 0x01, 0x08, 0x20, 0x02, 0x04)
_THIEF_CONTACT_DAMAGE = (6, 5, 10, 8, 4, 4, 7, 5)

# 0x5B70A.  The bits select the horizontal/vertical legs in
# thief_move_engine; the value is not a scalar speed.
_THIEF_DIRECTION_STEP_FLAGS = (0x70, 0x60, 0xE0, 0xA0, 0xB0, 0x90, 0xD0, 0x50, 0xF0)

# Packed-route direction 0=N, 2=E, 4=S, 6=W.
_ROUTE_COLUMN_DELTAS = (0, 1, 1, 1, 0, -1, -1, -1, 0)
_ROUTE_ROW_DELTAS = (-0x20, -0x20, 0, 0x20, 0x20, 0x20, 0, -0x20, 0)
_PATH_GRID_COLUMNS = 44
_PATH_GRID_ROW_STRIDE = 0x80
_PATH_GRID_MAX_CELL = 0x3FF

#: 0x5B66E, read by ``_route_cell_is_traversable`` (0x4FA50/0x4FA70).
_MAZE_OBJECT_TRAVERSABILITY_FLAGS = (
    1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0,
    0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0,
)
#: 0x5B6AE, indexed by the candidate cell's object type with ``tst.b (a0,d0.w)``
#: at 0x4F8EC.  The type comes out of ``mob_link`` bits 15-10, so every one of
#: the 64 values is reachable and the table has to be exactly 64 bytes long:
#: a short transcription silently raised IndexError on the two highest types.
#: Indices 46-59 -- TREASURE through POWER_INVULN, i.e. every pickup including
#: POWER_SUPERSHOT -- are 1, and so is 61 (HIDDENPOT); MONST_DRAGON (60),
#: TRANSPORTER (62) and FORCEFIELDHUB (63) are 0, so the thief walks over a
#: transporter or hub instead of eating it.
_THIEF_COLLISION_REMOVE_FLAGS = (
    1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0,
)
_THIEF_SOLID_OBJECTS = frozenset((
    int(MazeObjIds.WALL_REGULAR),
    int(MazeObjIds.WALL_MOVABLE),
    int(MazeObjIds.WALL_SECRET),
    int(MazeObjIds.WALL_DESTRUCTABLE),
    int(MazeObjIds.WALL_RANDOM),
    int(MazeObjIds.WALL_TRAPCYC1),
    int(MazeObjIds.WALL_TRAPCYC2),
    int(MazeObjIds.WALL_TRAPCYC3),
    int(MazeObjIds.DOOR_HORIZ),
    int(MazeObjIds.DOOR_VERT),
    int(MazeObjIds.MONST_DRAGON),
))

# row76.bin animation tables: 0x58C8A-0x58E3D.
_THIEF_ESCAPE_ANIM = (0x0FAB, 0x0FAB, 0x0FAB, 0x0FB4, 0x0FB4, 0x0FBD, 0x0FBD, 0x0DF3)
_THIEF_WALK_ANIM = (
    0x0F09, 0x0F12, 0x0F1B, 0x0F1B, 0x0F1B, 0x0F1B, 0x0F12, 0x0F09,
    0x0F90, 0x0F99, 0x0FA2, 0x0FA2, 0x0FA2, 0x0FA2, 0x0F99, 0x0F90,
    0x0F24, 0x0F2D, 0x0F36, 0x0F36, 0x0F36, 0x0F36, 0x0F2D, 0x0F24,
    0x0F5A, 0x0F63, 0x0F6C, 0x0F6C, 0x0F6C, 0x0F6C, 0x0F63, 0x0F5A,
    0x0ECF, 0x0ED8, 0x0EE1, 0x0EE1, 0x0EE1, 0x0EE1, 0x0ED8, 0x0ECF,
    0x0F3F, 0x0F48, 0x0F51, 0x0F51, 0x0F51, 0x0F51, 0x0F48, 0x0F3F,
    0x0EEA, 0x0EF3, 0x0F00, 0x0F00, 0x0F00, 0x0F00, 0x0EF3, 0x0EEA,
    0x0F75, 0x0F7E, 0x0F87, 0x0F87, 0x0F87, 0x0F87, 0x0F7E, 0x0F75,
)
_THIEF_IDLE_ANIM = (0x0E12, 0x0EA2, 0x0E6C, 0x0E48, 0x0DF3, 0x0E2D, 0x0E87, 0x0EBD, 0x0DF3)
_THIEF_COMPACT_ANIM = (
    0x0E09, 0x0E12, 0x0E1B, 0x0E12, 0x0E99, 0x0EA2, 0x0EAB, 0x0EA2,
    0x0E63, 0x0E6C, 0x0E75, 0x0E6C, 0x0E3F, 0x0E48, 0x0E51, 0x0E48,
    0x0DEA, 0x0DF3, 0x0E00, 0x0DF3, 0x0E24, 0x0E2D, 0x0E36, 0x0E2D,
    0x0E7E, 0x0E87, 0x0E90, 0x0E87, 0x0EB4, 0x0EBD, 0x0EC6, 0x0EBD,
)
_MUGGER_WALK_ANIM = (
    0x0FE1, 0x0FEA, 0x0FF3, 0x0FF3, 0x0FF3, 0x0FF3, 0x0FEA, 0x0FE1,
    0x26E1, 0x26EA, 0x26F3, 0x26F3, 0x26F3, 0x26F3, 0x26EA, 0x26E1,
    0x2760, 0x2769, 0x2772, 0x2772, 0x2772, 0x2772, 0x2769, 0x2760,
    0x26AB, 0x26B4, 0x26BD, 0x26BD, 0x26BD, 0x26BD, 0x26B4, 0x26AB,
    0x24E1, 0x24EA, 0x24F3, 0x24F3, 0x24F3, 0x24F3, 0x24EA, 0x24E1,
    0x2690, 0x2699, 0x26A2, 0x26A2, 0x26A2, 0x26A2, 0x2699, 0x2690,
    0x0FC6, 0x0FCF, 0x0FD8, 0x0FD8, 0x0FD8, 0x0FD8, 0x0FCF, 0x0FC6,
    0x26C6, 0x26CF, 0x26D8, 0x26D8, 0x26D8, 0x26D8, 0x26CF, 0x26C6,
)
_MUGGER_IDLE_ANIM = (0x2424, 0x24B4, 0x247E, 0x245A, 0x2409, 0x243F, 0x2499, 0x24CF, 0x2409)
_MUGGER_COMPACT_ANIM = (
    0x241B, 0x2424, 0x242D, 0x2424, 0x24AB, 0x24B4, 0x24BD, 0x24B4,
    0x2475, 0x247E, 0x2487, 0x247E, 0x2451, 0x245A, 0x2463, 0x245A,
    0x2400, 0x2409, 0x2412, 0x2409, 0x2436, 0x243F, 0x2448, 0x243F,
    0x2490, 0x2499, 0x24A2, 0x2499, 0x24C6, 0x24CF, 0x24D8, 0x24CF,
)


def _path_grid_offset(grid_index: int) -> int:
    if not 0 <= grid_index <= _PATH_GRID_MAX_CELL:
        raise ValueError(f"path-grid cell out of range: {grid_index:#x}")
    return (grid_index // _PATH_GRID_COLUMNS) * _PATH_GRID_ROW_STRIDE + grid_index % _PATH_GRID_COLUMNS


def path_grid_get_direction(state: GameState, grid_index: int) -> int:
    """0x5103E -- return the selected nibble, or eight when it is unset."""
    packed = state.path_direction_grid[_path_grid_offset(grid_index)]
    if state.thief_mode & THIEF_ESCAPE:
        packed >>= 4
    direction = (packed & 0x0F) - 1
    return direction if 0 <= direction <= 7 else 8


def path_grid_set_low_direction(state: GameState, grid_index: int, direction: int) -> None:
    """0x50FD2 -- replace the pursuit (low-nibble) route direction."""
    offset = _path_grid_offset(grid_index)
    state.path_direction_grid[offset] = (state.path_direction_grid[offset] & 0xF0) | ((direction + 1) & 0x0F)


def path_grid_set_high_direction_if_empty(state: GameState, grid_index: int, direction: int) -> None:
    """0x51000 -- write a reverse escape route only once, outside escape mode."""
    if state.thief_mode & THIEF_ESCAPE:
        return
    offset = _path_grid_offset(grid_index)
    if not state.path_direction_grid[offset] & 0xF0:
        state.path_direction_grid[offset] |= ((direction + 1) & 0x0F) << 4


def calc_direction(state: GameState, from_slot: int, to_slot: int) -> int:
    """0x510FC -- direction between packed cells, including level wrapping."""
    from_col, to_col = from_slot & 0x1F, to_slot & 0x1F
    if state.wrap_h:
        if from_col - to_col > 0x10:
            to_col += 0x20
        elif to_col - from_col > 0x10:
            from_col += 0x20
    col_delta = to_col - from_col

    from_row, to_row = (from_slot >> 5) & 0x1F, (to_slot >> 5) & 0x1F
    if state.wrap_v:
        if from_row - to_row > 0x10:
            to_row += 0x20
        elif to_row - from_row > 0x10:
            from_row += 0x20
    row_delta = to_row - from_row

    direction = 1
    if col_delta == 0:
        direction = 0
    if row_delta == 0:
        direction = 2
    if col_delta < 0:
        direction = (8 - direction) & 7
    if row_delta > 0:
        direction = (12 - direction) & 7
    return 8 if col_delta == 0 and row_delta == 0 else direction


def _tport_positions(state: GameState) -> list[int]:
    return [
        slot for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link))
        if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)
    ]


def tport_find_id(state: GameState, packed_pos: int) -> int:
    """0x4E7C0 -- return a transporter's one-based ID, or count+1."""
    pads = _tport_positions(state)
    try:
        return pads.index(packed_pos) + 1
    except ValueError:
        return len(pads) + 1


def tport_route_connect(
    state: GameState, source_pos: int, destination_pos: int, landing_pos: int,
) -> None:
    """0x4E684 -- connect both directional route-table records."""
    source_id = tport_find_id(state, source_pos)
    destination_id = tport_find_id(state, destination_pos)
    if not 1 <= source_id < len(state.tport_route_forward):
        return
    if not 1 <= destination_id < len(state.tport_route_reverse):
        return

    forward = (
        (destination_id << 8)
        | (state.tport_route_forward[source_id] & 0x0F)
    )
    reverse = state.tport_route_reverse[destination_id] & 0xFF00
    if reverse == 0:
        reverse = source_id << 8
    reverse |= (calc_direction(state, destination_pos, landing_pos) + 1) & 0x0F
    state.tport_route_forward[source_id] = forward
    state.tport_route_reverse[destination_id] = reverse


def tport_route_connect_if_empty(
    state: GameState, source_pos: int, destination_pos: int, approach_pos: int,
) -> None:
    """0x4E73A -- fill the source's approach direction once."""
    source_id = tport_find_id(state, source_pos)
    destination_id = tport_find_id(state, destination_pos)
    if not 1 <= source_id < len(state.tport_route_forward):
        return
    if not 1 <= destination_id < len(state.tport_route_reverse):
        return
    if state.tport_route_forward[source_id] & 0x0F:
        return
    state.tport_route_forward[source_id] |= (
        calc_direction(state, source_pos, approach_pos) + 1
    ) & 0x0F


def _advance_route_cell(packed_pos: int, direction: int) -> int:
    return (
        ((packed_pos & 0x3E0) + _ROUTE_ROW_DELTAS[direction])
        + ((packed_pos + _ROUTE_COLUMN_DELTAS[direction]) & 0x1F)
    ) & 0xFFFF


def _route_cell_is_traversable(state: GameState, packed_pos: int) -> bool:
    return bool(_MAZE_OBJECT_TRAVERSABILITY_FLAGS[state.mobs.obj_type(packed_pos)])


def thief_track_victim_move(state: GameState, new_packed_pos: int, player_index: int) -> None:
    """0x4E630 -- write the target's departure direction to the low route nibble."""
    new_packed_pos &= 0xFFFF
    if player_index != state.thief_victim or new_packed_pos == state.thief_victim_pos:
        return
    path_grid_set_low_direction(
        state,
        state.thief_victim_pos,
        calc_direction(state, state.thief_victim_pos, new_packed_pos),
    )
    state.thief_victim_pos = new_packed_pos


def thief_compute_path(state: GameState) -> None:
    """0x4F912 -- choose the following route cell and recover diagonal corners."""
    old_direction = state.thief_path_direction & 0xFF
    direction = path_grid_get_direction(state, state.thief_current_pos)
    state.thief_path_direction = old_direction if direction == 8 else direction
    state.thief_previous_pos = state.thief_next_pos
    state.thief_next_pos = _advance_route_cell(state.thief_current_pos, state.thief_path_direction)

    if state.thief_path_direction & 1:
        return
    next_direction = path_grid_get_direction(state, state.thief_next_pos)
    if next_direction == 8 or ((state.thief_path_direction ^ next_direction) & 3) != 2:
        return

    diagonal_sum = state.thief_path_direction + next_direction
    if next_direction == 0 and state.thief_path_direction == 6:
        diagonal_sum += 8
    elif next_direction == 6 and state.thief_path_direction == 0:
        diagonal_sum += 8
    diagonal_direction = diagonal_sum >> 1
    diagonal_pos = _advance_route_cell(state.thief_current_pos, diagonal_direction)
    column_side_pos = (state.thief_current_pos & 0x3E0) | (
        (state.thief_current_pos + _ROUTE_COLUMN_DELTAS[diagonal_direction]) & 0x1F
    )
    row_side_pos = (
        ((state.thief_current_pos & 0x3E0) + _ROUTE_ROW_DELTAS[diagonal_direction])
        | (state.thief_current_pos & 0x1F)
    ) & 0xFFFF
    if not _route_cell_is_traversable(state, column_side_pos):
        return
    if not _route_cell_is_traversable(state, row_side_pos):
        return
    diagonal_next_direction = path_grid_get_direction(state, diagonal_pos)
    if diagonal_next_direction == 8:
        return
    if path_grid_get_direction(state, _advance_route_cell(diagonal_pos, diagonal_next_direction)) == 8:
        return
    state.thief_path_direction = diagonal_direction
    state.thief_next_pos = diagonal_pos


def _player_packed_cell(state: GameState, player_index: int) -> int:
    """The cell a hero occupies -- its migrating record names it directly."""
    return state.players[player_index].mob_slot


def _player_is_targetable(state: GameState, player_index: int) -> bool:
    player = state.players[player_index]
    return bool(player.active and player.health > 0 and player.mob_slot)


def _player_wealth(player: object) -> int:
    powers = player.powers
    return (
        (0x3E8 if powers & 0x10 else 0)
        + (0x2BC if powers & 0x01 else 0)
        + (0x1F4 if powers & 0x08 else 0)
        + (0x12C if powers & 0x20 else 0)
        + (0x0C8 if powers & 0x02 else 0)
        + (0x064 if powers & 0x04 else 0)
        + player.potionsnum * 3
        + player.bonusmult
        + player.keysnum * 2
    )


def thief_target_calc(state: GameState) -> None:
    """0x4DFF6 -- select the richest active, living player."""
    state.thief_victim = -1
    best_wealth = 0
    for index in range(len(state.players)):
        if not _player_is_targetable(state, index):
            continue
        wealth = _player_wealth(state.players[index])
        if state.thief_victim < 0 or wealth > best_wealth:
            state.thief_victim = index
            best_wealth = wealth


def thief_setup(state: GameState) -> None:
    """0x4E432 -- reset this level's thief state and roll its appearance."""
    state.thief_level_setup_done = True
    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    state.thief_enter_time = -1
    state.thief_victim = -1
    state.thief_item_carried = _THIEF_CARRIED_EMPTY
    state.mugger_item_carried = 0
    state.thief_mode = THIEF_DEAD
    state.thief_collision_direction_code = 0
    state.thief_pursuit_direction = -1
    state.thief_tport_timer = -1
    state.thief_tport_dest = 0

    if state.game_mode < 0 or state.mazenum_current >= _THIEF_MAZE_LIMIT:
        return
    if state.levelnum_current < _THIEF_MIN_LEVEL:
        return
    if (state.levelnum_current >> 3) <= state.getrandom(8):
        return
    thief_target_calc(state)
    if state.thief_victim < 0:
        return
    victim_pos = _player_packed_cell(state, state.thief_victim)
    state.thief_start_location = victim_pos
    state.thief_victim_pos = victim_pos
    thief_timer_set(state)


def _thief_delay_frames(state: GameState) -> int:
    """The target-score delay arithmetic at 0x4E568-0x4E620."""
    player = state.players[state.thief_victim]
    wealth = (player.score >> 13) // max(1, player.coin_count)
    level_delta = min(max(0, state.levelnum_current - 6), 100)
    if state.mazenum_current >= 0x68:
        wealth = min(wealth, 5)
        decrement = 3 - (level_delta >> 5)
        span = wealth + 5 + decrement
        base = 10
    else:
        wealth = min(wealth, 15)
        decrement = 50 - (level_delta >> 1)
        span = wealth + 10 + decrement
        base = 20
    return ((base - wealth) + state.getrandom(max(1, span))) * 60


def thief_timer_set(state: GameState) -> None:
    """0x4E4D8 -- choose the variant and schedule the next arrival."""
    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    state.thief_enter_time = -1
    if state.thief_victim < 0 or not _player_is_targetable(state, state.thief_victim):
        return
    if state.thief_mode & (THIEF_ENTER_OK | THIEF_ENTER_OK_MUGGER) == (
        THIEF_ENTER_OK | THIEF_ENTER_OK_MUGGER
    ):
        return

    state.thief_mode = (state.thief_mode & (THIEF_ENTER_OK | THIEF_ENTER_OK_MUGGER)) | THIEF_PURSUE
    is_mugger = False
    if not state.thief_mode & THIEF_ENTER_OK_MUGGER:
        is_mugger = state.getrandom(32) < 16 or bool(state.thief_mode & THIEF_ENTER_OK)
    if is_mugger:
        state.thief_mode |= THIEF_IS_MUGGER
        state.thief_speed = _SPEED_MUGGER
    else:
        state.thief_speed = _SPEED_THIEF
    state.thief_enter_time = _thief_delay_frames(state)


def _spawn_picture(state: GameState) -> int:
    return 0x2400 if state.thief_mode & THIEF_IS_MUGGER else 0x0DEA


def _thief_deploy(state: GameState) -> None:
    """0x4DEDC-0x4DFDE -- create the thief after its arrival timer expires."""
    if state.thief_victim < 0 or not _player_is_targetable(state, state.thief_victim):
        thief_target_calc(state)
        if state.thief_victim < 0:
            state.thief_enter_time = -1
            return
        state.thief_start_location = _player_packed_cell(state, state.thief_victim)
        state.thief_victim_pos = state.thief_start_location

    slot = state.thief_start_location
    if state.mobs.picture[slot] != 0 or not _route_cell_is_traversable(state, slot):
        state.thief_enter_time = 0x12C
        return

    row, col = slot >> 5, slot & 0x1F
    palette = 1 if state.thief_mode & THIEF_IS_MUGGER else 0
    state.mobs.create(
        slot,
        _spawn_picture(state),
        encode_hpos(col * 16, palette=palette),
        encode_vpos_at_y(row * 16, width=3, height=3),
        MazeObjIds.PLAYERSTART,
    )
    state.thief_mob_slot = slot
    state.thief_current_pos = slot
    state.thief_previous_pos = slot
    state.thief_next_pos = slot
    state.thief_direction = 8
    state.thief_enter_time = 0x3C
    state.thief_collision_direction_code = 0
    state.thief_tport_active = 0
    path_grid_set_high_direction_if_empty(state, slot, 8)
    thief_compute_path(state)
    _sound_play(state, 0x2D if state.thief_mode & THIEF_IS_MUGGER else 0x29)


def main_start_thief(state: GameState) -> None:
    """0x4DEB8 -- schedule/deploy bookkeeping and the arrival pause."""
    if state.thief_enter_time < 0:
        # Direct dev/test level loads do not run main_start_game's 0x4835E tail.
        # Let them perform that setup once without repeating its RNG draw.
        if not state.thief_level_setup_done:
            thief_setup(state)
        return
    if state.thief_enter_time > 0:
        state.thief_enter_time -= 1
        return
    if state.thief_current_pos:
        state.thief_enter_time = -1
        return
    _thief_deploy(state)


def _repair_route_after_mode_toggle(state: GameState) -> None:
    if state.thief_previous_pos == state.thief_current_pos:
        thief_compute_path(state)
    else:
        state.thief_next_pos = state.thief_previous_pos


def thief_exit(state: GameState) -> None:
    """0x4E122 -- change an active thief from pursuit to route-retracing escape."""
    if not state.thief_current_pos:
        state.thief_enter_time = -1
        return
    if state.thief_mode & THIEF_ESCAPE:
        return
    state.thief_mode = (state.thief_mode & ~0x09) | THIEF_ESCAPE
    _repair_route_after_mode_toggle(state)


def thief_begin_dodge(state: GameState) -> None:
    """0x4E1B8 -- flip pursuit/escape while setting the dodge bit."""
    if not state.thief_current_pos or state.thief_mode & THIEF_DODGE:
        return
    state.thief_mode |= THIEF_DODGE
    state.thief_mode ^= THIEF_PURSUE | THIEF_ESCAPE
    _repair_route_after_mode_toggle(state)


def thief_end_dodge(state: GameState) -> None:
    """0x4E172 -- clear the dodge bit and restore the previous route polarity."""
    if not state.thief_current_pos or not state.thief_mode & THIEF_DODGE:
        return
    state.thief_mode &= ~THIEF_DODGE
    state.thief_mode ^= THIEF_PURSUE | THIEF_ESCAPE
    _repair_route_after_mode_toggle(state)


def _resource_to_steal(player: object) -> int:
    potions = player.potionsnum * 3
    multiplier = player.bonusmult
    keys = player.keysnum * 2
    if potions > keys and potions > multiplier:
        return int(MazeObjIds.POT_INVULN)
    if multiplier > potions and multiplier > keys:
        return int(MazeObjIds.TREASURE_BAG)
    if keys > multiplier and keys > potions:
        return int(MazeObjIds.KEY)
    if potions:
        return int(MazeObjIds.POT_INVULN)
    if multiplier:
        return int(MazeObjIds.TREASURE_BAG)
    if keys:
        return int(MazeObjIds.KEY)
    return int(MazeObjIds.TREASURE_BAG)


def thief_steal_from_player(state: GameState, player_index: int) -> int:
    """0x4E1FE -- steal the ROM-selected item, or mug 100 health."""
    if state.thief_mode & THIEF_ESCAPE:
        return 0
    thief_exit(state)
    player = state.players[player_index]

    if state.thief_mode & THIEF_IS_MUGGER:
        player.health = max(0, player.health - 100)
        state.mugger_item_carried = int(MazeObjIds.FOOD_INVULN)
        state.thief_mode |= THIEF_ENTER_OK_MUGGER
        if hasattr(state, "health_dirty"):
            state.health_dirty[player_index] = 1
        _sound_play(state, 0x26)
        return 1

    state.thief_mode |= THIEF_JUMPJUMP
    state.thief_stolen_item = 0
    if player.powers & 0x00FF:
        state.thief_item_carried = int(MazeObjIds.POT_INVULN)
        for mask in _STEALABLE_POWER_MASKS:
            if player.powers & mask:
                player.powers &= ~mask
                break
    else:
        stolen_type = _resource_to_steal(player)
        if stolen_type == int(MazeObjIds.POT_INVULN):
            state.thief_item_carried = stolen_type
            player.potionsnum = max(0, player.potionsnum - 1)
        elif stolen_type == int(MazeObjIds.KEY):
            state.thief_item_carried = stolen_type
            player.keysnum = max(0, player.keysnum - 1)
        else:
            state.thief_item_carried = (player.bonusmult * 500 << 6) | int(MazeObjIds.TREASURE_BAG)
            player.bonusmult = 1

    from .players import setup_infopanel

    setup_infopanel(state, player_index)                         # 0x4E3F8
    state.thief_mode |= THIEF_ENTER_OK
    if hasattr(state, "score_dirty"):
        state.score_dirty[player_index] = 1
    _sound_play(state, 0x26)
    return 1


def thief_remove_and_drop_loot(
    state: GameState,
    score_player_or_minus1: int,
    replacement_mob_slot: int,
) -> None:
    """0x4F5C8 -- dissolve a killed thief/mugger and recreate its carried item.

    ``score_player_or_minus1`` is a signed player index.  A nonnegative value
    earns that player the ROM's 500-point bounty through their multiplier;
    ``-1`` suppresses the bounty and uses the thief's victim as the dissolve
    channel.  A nonzero ``replacement_mob_slot`` receives both the dissolve
    effect and recreated pickup; zero uses the thief's current MOB slot.
    """
    current_slot = state.thief_current_pos or state.thief_mob_slot
    score_player = (
        -1 if (score_player_or_minus1 & 0xFFFF) == 0xFFFF
        else score_player_or_minus1
    )
    effect_player = state.thief_victim if score_player == -1 else score_player

    if 0 <= score_player < len(state.players):
        player = state.players[score_player]
        player.score = (player.score + 0x1F4 * player.bonusmult) & 0xFFFF_FFFF
        if hasattr(state, "score_dirty"):
            state.score_dirty[score_player] = 1

    if state.thief_mode & THIEF_IS_MUGGER:
        item_type = state.mugger_item_carried & 0xFFFF
        state.mugger_item_carried = 0
    else:
        carried = state.thief_item_carried
        item_type = (carried & 0xFFFF) & 0x3F
        # The arcade writes this even for an ordinary low-valued item, whose
        # packed score component is zero.
        state.special_bonus_score = (carried >> 6) & 0xFFFF
        state.thief_item_carried = _THIEF_CARRIED_EMPTY

    drop_slot = replacement_mob_slot & 0xFFFF or current_slot
    if current_slot:
        # The transporter animation itself is owned by WP-7, but its start is
        # part of this ROM routine's observable thief-removal transaction.
        from .shots import tport_cycle_start

        tport_cycle_start(state, drop_slot, effect_player)
        state.mobs.unlink_and_clear(current_slot)

    # 0x4F662-0x4F6A6 tears down an in-flight thief transporter transition
    # before creating the replacement pickup.
    if getattr(state, "thief_tport_timer", -1) >= 0:
        transition_slot = getattr(state, "thief_tport_dest", 0)
        if transition_slot and transition_slot != current_slot:
            state.mobs.unlink_and_clear(transition_slot)
        state.thief_tport_timer = -1

    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    if item_type and drop_slot:
        if drop_slot != current_slot and state.mobs.is_occupied(drop_slot):
            state.mobs.unlink_and_clear(drop_slot)
        # This exact path indexes the base-picture table directly, rather than
        # using maze placement's randomized invulnerable-food picture variant.
        from ..maze import placement_base_picture, placement_geometry

        hpos, vpos = placement_geometry(item_type, drop_slot)
        state.mobs.create(
            drop_slot,
            placement_base_picture(item_type),
            hpos,
            vpos,
            item_type,
        )

    # The ROM schedules the remaining variant (if any) after the old thief and
    # optional loot have been removed.
    thief_timer_set(state)


def _slot_for_thief(state: GameState) -> int:
    return state.thief_mob_slot or state.thief_current_pos


def _clamp_or_wrap(value: int, wraps: bool) -> int:
    return value % _WORLD_PIXELS if wraps else max(0, min(_WORLD_PIXELS - 1, value))


def _player_at_cell(state: GameState, cell: int) -> int:
    for index in range(len(state.players)):
        if _player_is_targetable(state, index) and _player_packed_cell(state, index) == cell:
            return index
    return -1


def _fixed_player_at_slot(state: GameState, slot: int) -> int:
    for index in range(len(state.players)):
        if state.players[index].active and state.players[index].mob_slot == slot:
            return index
    return -1


def _damage_player_from_escape_contact(state: GameState, player_index: int) -> None:
    player = state.players[player_index]
    protected = 4 if player.powers & 0x02 else 0
    damage = _THIEF_CONTACT_DAMAGE[(player.character & 3) + protected]
    player.health = max(0, player.health - damage)
    player.hurt_cooldown = 0x12
    if hasattr(state, "health_dirty"):
        state.health_dirty[player_index] = 1
    if state.getrandom(8) == 1:
        _sound_play(state, (0x66, 0x67, 0x68)[state.getrandom(3)])
    else:
        _sound_play(state, 0x1E)


def _handle_escape_player_contact(state: GameState, player_index: int) -> None:
    if not state.thief_collision_direction_code:
        state.thief_collision_direction_code = state.thief_direction + 1
        state.thief_stolen_item = 0
        return
    if state.thief_stolen_item > 0x0F:
        _damage_player_from_escape_contact(state, player_index)
        state.thief_collision_direction_code = 0


def thief_handle_tile_collision(state: GameState, candidate_mob_slot: int) -> int:
    """0x4F742 -- handle a prospective cell; -1 means this frame is blocked."""
    if not 0 <= candidate_mob_slot <= _PATH_GRID_MAX_CELL:
        return -1
    player_index = _fixed_player_at_slot(state, candidate_mob_slot)
    if player_index >= 0:
        if state.thief_mode & THIEF_ESCAPE:
            _handle_escape_player_contact(state, player_index)
        return 0

    obj_type = state.mobs.obj_type(candidate_mob_slot)
    if (
        candidate_mob_slot == state.thief_next_pos
        and obj_type == int(MazeObjIds.TRANSPORTER)
    ):
        return thief_enter_tport(state, candidate_mob_slot)
    if _THIEF_COLLISION_REMOVE_FLAGS[obj_type]:
        state.mobs.unlink_and_clear(candidate_mob_slot)
        return -1
    if state.mobs.picture[candidate_mob_slot] == 0x8000 or obj_type in _THIEF_SOLID_OBJECTS:
        return -1
    return 0


def thief_start_tport_anim(state: GameState, destination_pos: int) -> None:
    """0x4FBFC -- arm the shared transition and destination placeholder."""
    from .players import handle_tport

    state.thief_tport_active = 1
    handle_tport(state, state.thief_current_pos, 4)
    state.thief_tport_timer = 0
    state.thief_tport_dest = destination_pos
    state.thief_next_pos = destination_pos
    if state.mobs.is_occupied(destination_pos):
        state.mobs.unlink_and_clear(destination_pos)
    row, col = destination_pos >> 5, destination_pos & 0x1F
    palette = 1 if state.thief_mode & THIEF_IS_MUGGER else 0
    state.mobs.create(
        destination_pos,
        0x1709,
        encode_hpos(col * 16 - 4, palette=palette),
        encode_vpos_at_y(row * 16, width=3, height=3),
        MazeObjIds.PLAYERSTART,
    )
    if state.thief_previous_pos != state.thief_current_pos:
        path_grid_set_high_direction_if_empty(
            state,
            destination_pos,
            calc_direction(
                state, destination_pos, state.thief_previous_pos,
            ),
        )
    _sound_play(state, 0x28)


def thief_enter_tport(state: GameState, transporter_pos: int) -> int:
    """0x4FAD4 -- follow a learned transporter route, or return clear."""
    route_id = tport_find_id(state, transporter_pos)
    if not 1 <= route_id < len(state.tport_route_forward):
        return 0
    route = (
        state.tport_route_forward[route_id]
        if state.thief_mode & THIEF_PURSUE
        else state.tport_route_reverse[route_id]
    )
    destination_id = (route >> 8) & 0xFF
    pads = _tport_positions(state)
    if not 1 <= destination_id <= len(pads):
        return 0
    direction_route = (
        state.tport_route_reverse[destination_id]
        if state.thief_mode & THIEF_PURSUE
        else state.tport_route_forward[destination_id]
    )
    direction = (direction_route & 0x0F) - 1
    if not 0 <= direction <= 7:
        return 0
    destination_pad = pads[destination_id - 1]
    landing = _advance_route_cell(destination_pad, direction) & 0x3FF
    if (state.mobs.hpos[landing] & 0x0F) >= 0x0C:
        return 0
    from .players import nearby_mob_clearance_test

    if not nearby_mob_clearance_test(state, landing, 4):
        return 0
    tport_route_connect_if_empty(
        state, transporter_pos, destination_pad, state.thief_previous_pos,
    )
    thief_start_tport_anim(state, landing)
    state.thief_previous_pos = destination_pad
    return -1


def _direction_from_move_flags(move_flags: int) -> int:
    try:
        return _THIEF_DIRECTION_STEP_FLAGS.index(move_flags & 0xFF)
    except ValueError:
        return 8


def _axis_delta(move_flags: int, horizontal_speed: int, vertical_speed: int) -> tuple[int, int]:
    dx = 0 if (move_flags & 0x30) == 0x30 else (
        -horizontal_speed if move_flags & 0x10 else horizontal_speed
    )
    if move_flags & 0x40:
        dy = 0 if move_flags & 0x80 else -vertical_speed
    else:
        dy = vertical_speed if move_flags & 0x80 else 0
    return dx, dy


def _move_thief_axis(state: GameState, dx: int, dy: int) -> tuple[bool, bool]:
    """Apply one ROM-probed axis. Returns (moved, blocked)."""
    if not dx and not dy:
        return False, False
    slot = _slot_for_thief(state)
    if not slot:
        return False, True
    x, flags, palette = decode_hpos(state.mobs.hpos[slot])
    _, width, height = decode_vpos(state.mobs.vpos[slot])
    y = vpos_y(state.mobs.vpos[slot])
    new_x = _clamp_or_wrap(x + dx, state.wrap_h)
    new_y = _clamp_or_wrap(y + dy, state.wrap_v)

    from .players import (
        mob_probe_down,
        mob_probe_left,
        mob_probe_right,
        mob_probe_up,
    )

    proposed_h = encode_hpos(new_x, palette, flags)
    proposed_v = encode_vpos_at_y(new_y, width, height)
    if dx:
        probe = mob_probe_right if dx > 0 else mob_probe_left
    else:
        probe = mob_probe_down if dy > 0 else mob_probe_up
    candidate = probe(
        state,
        slot,
        hpos=proposed_h,
        vpos=proposed_v,
        self_slot=slot,
        defer_interactions=False,
    )
    if candidate >= 0:
        player_index = _fixed_player_at_slot(state, candidate)
        if (
            player_index >= 0
            and _player_is_targetable(state, player_index)
            and not state.thief_mode & THIEF_ESCAPE
            and thief_steal_from_player(state, player_index)
        ):
            return False, True
        if candidate > _PATH_GRID_MAX_CELL or thief_handle_tile_collision(
            state, candidate,
        ):
            return False, True
        return False, False

    state.mobs.hpos[slot] = proposed_h
    state.mobs.vpos[slot] = proposed_v
    new_cell = mob_cell_of(proposed_h, proposed_v)
    if new_cell != slot and not state.mobs.is_occupied(new_cell):
        state.mobs.move_slot(slot, new_cell)
        slot = new_cell
        state.thief_mob_slot = slot
        state.thief_current_pos = slot
        if state.thief_current_pos == state.thief_next_pos:
            path_grid_set_high_direction_if_empty(
                state, slot, (state.thief_path_direction + 4) & 7
            )
    return True, False


def thief_move_engine(
    state: GameState,
    move_flags: int,
    horizontal_delta_bias: int,
    vertical_delta_bias: int,
) -> int:
    """0x4EE7A -- ROM-order horizontal/vertical thief movement and collision."""
    slot = _slot_for_thief(state)
    if not slot:
        return -1
    state.thief_current_pos = slot
    player_index = _player_at_cell(state, state.thief_current_pos)
    contacted_current_player = player_index >= 0
    if player_index >= 0:
        if state.thief_mode & THIEF_ESCAPE:
            _handle_escape_player_contact(state, player_index)
        elif thief_steal_from_player(state, player_index):
            return state.thief_collision_direction_code + 1
    direction = _direction_from_move_flags(move_flags)
    if direction != 8:
        state.thief_direction = direction
    horizontal_speed = max(0, horizontal_delta_bias >> 7)
    vertical_speed = max(0, vertical_delta_bias >> 7)
    dx, dy = _axis_delta(move_flags, horizontal_speed, vertical_speed)

    blocked = False
    moved_h, blocked_h = _move_thief_axis(state, dx, 0)
    blocked |= blocked_h
    moved_v, blocked_v = _move_thief_axis(state, 0, dy)
    blocked |= blocked_v
    if not moved_h and not moved_v and not blocked and not contacted_current_player:
        player_index = _player_at_cell(state, state.thief_current_pos)
        if player_index >= 0 and not state.thief_mode & THIEF_ESCAPE:
            blocked = bool(thief_steal_from_player(state, player_index))

    return state.thief_collision_direction_code + int(blocked)


def _shot_direction(state: GameState, player_index: int) -> int:
    direction = state.shot_direction[player_index]
    if 0 <= direction <= 7:
        return direction
    slot = player_index + 1
    dx = state.shot_dx[slot] if slot < len(state.shot_dx) else 0
    dy = state.shot_dy[slot] if slot < len(state.shot_dy) else 0
    if dx == 0:
        return 0 if dy < 0 else 4 if dy > 0 else 8
    if dy == 0:
        return 2 if dx > 0 else 6
    if dx > 0:
        return 1 if dy < 0 else 3
    return 7 if dy < 0 else 5


def _wrapped_axis_delta(value: int, wraps: bool) -> int:
    if wraps:
        if value > _WORLD_PIXELS // 2:
            value -= _WORLD_PIXELS
        elif value < -_WORLD_PIXELS // 2:
            value += _WORLD_PIXELS
    return value


def _trunc_div(value: int, divisor: int) -> int:
    return value // divisor if value >= 0 else -((-value) // divisor)


def _shot_ray_matches(direction: int, dx: int, dy: int) -> bool:
    if direction == 0:
        return dx == 0 and dy < 0
    if direction == 1:
        return dx > 0 and dx == -dy
    if direction == 2:
        return dx > 0 and dy == 0
    if direction == 3:
        return dx > 0 and dx == dy
    if direction == 4:
        return dx == 0 and dy > 0
    if direction == 5:
        return dx < 0 and dx == -dy
    if direction == 6:
        return dx < 0 and dy == 0
    return direction == 7 and dx < 0 and dx == dy


def thief_find_aligned_shooter(state: GameState) -> int:
    """0x4FCF0 -- return the first player shot that is exactly on the thief's ray."""
    slot = _slot_for_thief(state)
    if not slot:
        return -1
    thief_x = hpos_x(state.mobs.hpos[slot])
    thief_y = vpos_y(state.mobs.vpos[slot])
    for player_index in range(4):
        shot_slot = player_index + 1
        if not state.mobs.picture[shot_slot]:
            continue
        direction = _shot_direction(state, player_index)
        if not 0 <= direction <= 7 or (direction ^ state.thief_direction) != 4:
            continue
        shot_x = hpos_x(state.mobs.hpos[shot_slot])
        shot_y = vpos_y(state.mobs.vpos[shot_slot])
        dx = _trunc_div(_wrapped_axis_delta(thief_x - shot_x, state.wrap_h), 16)
        dy = _trunc_div(_wrapped_axis_delta(thief_y - shot_y, state.wrap_v), 16)
        if _shot_ray_matches(direction, dx, dy):
            return player_index
    return -1


def _escape_animation(state: GameState) -> bool:
    """Advance the post-theft pause at 0x4E90C-0x4E99C."""
    if not state.thief_mode & THIEF_JUMPJUMP:
        return False
    counter = state.thief_stolen_item
    slot = _slot_for_thief(state)
    if counter >= 0x1C and slot:
        state.mobs.picture[slot] = _THIEF_ESCAPE_ANIM[((counter - 0x1C) >> 2) & 7]
    state.thief_stolen_item = counter + 1
    if state.thief_stolen_item > _TAUNT_THRESHOLD:
        state.thief_mode &= ~THIEF_JUMPJUMP
        laugh, speech = _TAUNT_PAIRS[state.getrandom(2)]
        _sound_play(state, laugh)
        _sound_play(state, speech)
    return True


def _finish_escape_at_start(state: GameState) -> bool:
    if not state.thief_mode & THIEF_ESCAPE:
        return False
    if state.thief_current_pos != state.thief_start_location:
        return False
    if state.thief_previous_pos == state.thief_start_location:
        return False
    slot = _slot_for_thief(state)
    if state.thief_mode & THIEF_IS_MUGGER:
        state.mugger_item_nextlevel = state.mugger_item_carried
    else:
        state.thief_item_nextlevel = state.thief_item_carried
    if slot:
        state.mobs.unlink_and_clear(slot)
    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    thief_timer_set(state)
    return True


def _update_dodge(state: GameState) -> None:
    if state.thief_mode & THIEF_IS_MUGGER:
        return
    if state.thief_mode & THIEF_DODGE:
        player_index = state.thief_pursuit_player
        shot_slot = player_index + 1
        if not 0 <= player_index < 4 or not state.mobs.picture[shot_slot]:
            thief_end_dodge(state)
            return
        if state.thief_pursuit_direction >= 0 and _shot_direction(state, player_index) != state.thief_pursuit_shot_direction:
            thief_end_dodge(state)
        return
    player_index = thief_find_aligned_shooter(state)
    if player_index < 0:
        return
    thief_begin_dodge(state)
    state.thief_pursuit_direction = -1
    state.thief_pursuit_player = player_index
    state.thief_pursuit_shot_direction = _shot_direction(state, player_index)
    state.thief_direction_change_pos = 0


def _set_thief_animation(state: GameState, movement_result: int) -> None:
    slot = _slot_for_thief(state)
    if not slot:
        return
    direction = state.thief_direction
    if state.thief_collision_direction_code:
        if not 0 <= direction < 8:
            return
        table = _MUGGER_WALK_ANIM if state.thief_mode & THIEF_IS_MUGGER else _THIEF_WALK_ANIM
        state.mobs.picture[slot] = table[direction * 8 + ((state.thief_stolen_item >> 2) & 7)]
    elif movement_result and 0 <= direction < 8:
        table = _MUGGER_COMPACT_ANIM if state.thief_mode & THIEF_IS_MUGGER else _THIEF_COMPACT_ANIM
        state.mobs.picture[slot] = table[direction * 4 + ((state.thief_stolen_item >> 2) & 3)]
    else:
        table = _MUGGER_IDLE_ANIM if state.thief_mode & THIEF_IS_MUGGER else _THIEF_IDLE_ANIM
        state.mobs.picture[slot] = table[min(direction, 8)]


def main_thief_anim(state: GameState) -> None:
    """0x4E8DC -- thief state graph, dodge latches, movement and animation."""
    if not state.thief_current_pos or state.thief_enter_time >= 0:
        return
    if state.thief_tport_timer >= 0:                 # 0x4E900-0x4E908
        return
    if _escape_animation(state):
        return
    if _finish_escape_at_start(state):
        return

    _update_dodge(state)
    if (
        state.thief_mode & THIEF_DODGE
        and state.thief_pursuit_direction >= 0
        and state.thief_current_pos == state.thief_next_pos
        and state.thief_direction_change_pos
        and state.thief_direction_change_pos != state.thief_current_pos
    ):
        return

    if state.thief_current_pos == state.thief_next_pos:
        thief_compute_path(state)
    direction = calc_direction(state, state.thief_current_pos, state.thief_next_pos)
    if state.thief_mode & THIEF_DODGE:
        if state.thief_pursuit_direction < 0:
            state.thief_pursuit_direction = direction
        elif direction != state.thief_direction:
            state.thief_direction_change_pos = state.thief_current_pos
    state.thief_direction = direction
    if not 0 <= direction <= 8:
        return

    state.thief_tport_active = 0
    movement_result = thief_move_engine(
        state,
        _THIEF_DIRECTION_STEP_FLAGS[direction],
        state.thief_speed,
        state.thief_speed,
    )
    if movement_result < 0:
        return
    _set_thief_animation(state, movement_result)
