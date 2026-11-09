"""The thief and mugger -- WP-10.

Reference: ``doc/04_game_subsystems.md`` §9, ``doc/05_data_reference.md``,
and the checked ``row76.bin`` routines at 0x4DEB8-0x4FEB0.
"""

from __future__ import annotations

from ..alpha_memory import write_path_grid_byte as _write_path_grid_byte

from ..constants import FIRST_PLAYABLE_SLOT, MazeObjIds
from ..coords import (
    POS_SHIFT,
    encode_hpos,
    encode_vpos_at_y,
    hpos_x,
    position_field,
    vpos_y,
)
from ..state import GameState
from .player_transport import tport_find_id as tport_find_id
from .score import player_add_score_with_mult
from .sound import sound_play as _sound_play
from .sound import sound_speech_play as _sound_speech_play

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

#: ``dialog_first_encounter`` masks pushed at 0x4E3FE, 0x4EBFA and 0x4E268.
_DIALOG_KILL_THIEF = 0x00100000
_DIALOG_FIND_STOLEN_ITEM = 0x00200000
_DIALOG_KILL_MUGGER = 0x20000000
_THIEF_TPORT_ANIM_SLOT = 0x1D
_TAUNT_THRESHOLD = 0x3B
_TAUNT_PAIRS = ((0x62, 0x63), (0x64, 0x65))

# 0x5B62E and 0x5B63A.
_THIEF_STEALABLE_POWER_MASKS = (0x10, 0x01, 0x08, 0x20, 0x02, 0x04)
_THIEF_CONTACT_DAMAGE = (6, 5, 10, 8, 4, 4, 7, 5)

# 0x5B70A.  The bits select the horizontal/vertical legs in
# thief_move_engine; the value is not a scalar speed.
_THIEF_DIRECTION_STEP_SIZE = (0x70, 0x60, 0xE0, 0xA0, 0xB0, 0x90, 0xD0, 0x50, 0xF0)

# Packed-route direction 0=N, 2=E, 4=S, 6=W.
_ROUTE_COLUMN_DELTAS = (0, 1, 1, 1, 0, -1, -1, -1, 0)
_ROUTE_ROW_DELTAS = (-0x20, -0x20, 0, 0x20, 0x20, 0x20, 0, -0x20, 0)
_PATH_GRID_COLUMNS = 44
_PATH_GRID_ROW_STRIDE = 0x80
# The thief can head off the bottom row, and 0x5103E reads what lies past it: row 23 of
# the grid has room for these 32 cells.
_PATH_GRID_MAX_CELL = 0x41F

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
# ROM: part game:0x50FD2,game:0x51000,game:0x5103E | Extracts the shared 44-column, 128-byte-row path-grid address calculation with a Python bounds guard.
def _path_grid_offset(grid_index: int) -> int:
    if not 0 <= grid_index <= _PATH_GRID_MAX_CELL:
        raise ValueError(f"path-grid cell out of range: {grid_index:#x}")
    return (grid_index // _PATH_GRID_COLUMNS) * _PATH_GRID_ROW_STRIDE + grid_index % _PATH_GRID_COLUMNS


# ROM: direct game:0x5103E | Reads pursuit or escape route nibble and returns direction 8 for an unset route.
def path_grid_get_direction(state: GameState, grid_index: int) -> int:
    """0x5103E -- return the selected nibble, or eight when it is unset."""
    packed = state.path_direction_grid[_path_grid_offset(grid_index)]
    if state.thief_mode & THIEF_ESCAPE:
        packed >>= 4
    direction = (packed & 0x0F) - 1
    return direction if 0 <= direction <= 7 else 8


# ROM: direct game:0x50FD2 | Writes direction-plus-one to the pursuit route nibble.
def path_grid_set_low_direction(state: GameState, grid_index: int, direction: int) -> None:
    """0x50FD2 -- replace the pursuit (low-nibble) route direction."""
    offset = _path_grid_offset(grid_index)
    _write_path_grid_byte(
        state, offset,
        (state.path_direction_grid[offset] & 0xF0) | ((direction + 1) & 0x0F),
    )


# ROM: direct game:0x51000 | Writes the reverse route nibble once, outside escape mode.
def path_grid_set_high_direction_if_empty(state: GameState, grid_index: int, direction: int) -> None:
    """0x51000 -- write a reverse escape route only once, outside escape mode."""
    if state.thief_mode & THIEF_ESCAPE:
        return
    offset = _path_grid_offset(grid_index)
    if not state.path_direction_grid[offset] & 0xF0:
        _write_path_grid_byte(
            state, offset,
            state.path_direction_grid[offset] | (((direction + 1) & 0x0F) << 4),
        )


# ROM: direct game:0x510FC | Direction between packed cells with per-axis level-wrap flags.
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


# ROM: helper | Reconstructs the Python ordered transporter positions from current MOB types.
def _tport_positions(state: GameState) -> list[int]:
    return [
        slot for slot in range(FIRST_PLAYABLE_SLOT, len(state.mobs.link))
        if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)
    ]


# ROM: direct game:0x4E684 | Route construction entry using flattened Python forward/reverse arrays.
# ROM: part game:0x510BC,game:0x5107A | Inlines paired route-word reads and writes; padded addressing and packed-return ABI are not standalone Python bodies.
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


# ROM: direct game:0x4E73A | Conditional source approach-direction update.
# ROM: part game:0x510BC,game:0x5107A | Inlines the used forward-half read/write while leaving reverse state unchanged; not a direct read-pair implementation.
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


# ROM: part game:0x4F912 | Extracts next-route-cell calculation using the row/column direction tables.
def _advance_route_cell(packed_pos: int, direction: int) -> int:
    return (
        ((packed_pos & 0x3E0) + _ROUTE_ROW_DELTAS[direction])
        + ((packed_pos + _ROUTE_COLUMN_DELTAS[direction]) & 0x1F)
    ) & 0xFFFF


# ROM: helper | Python object-type traversability-table accessor reused by routing and deployment.
def _route_cell_is_traversable(state: GameState, packed_pos: int) -> bool:
    # A hero's record has type 0 on the ROM's side, and 0x0F only here.
    if any(player.mob_slot == packed_pos for player in state.players):
        return bool(_MAZE_OBJECT_TRAVERSABILITY_FLAGS[0])
    return bool(_MAZE_OBJECT_TRAVERSABILITY_FLAGS[state.mobs.obj_type(packed_pos)])


# ROM: direct game:0x4E630 | Records the selected victim's departure direction and updates its packed position.
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


# ROM: direct game:0x4F912 | Computes the next recorded-route cell and diagonal corner shortcuts.
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
    # 0x4FA80: no test of this direction, so an unset 8 steps on through entry 8.
    diagonal_next_direction = path_grid_get_direction(state, diagonal_pos)
    if path_grid_get_direction(state, _advance_route_cell(diagonal_pos, diagonal_next_direction)) == 8:
        return
    state.thief_path_direction = diagonal_direction
    state.thief_next_pos = diagonal_pos


# ROM: helper | Python authoritative player MOB-slot accessor.
def _player_packed_cell(state: GameState, player_index: int) -> int:
    """The cell a hero occupies -- its migrating record names it directly."""
    return state.players[player_index].mob_slot


# ROM: helper | Reusable Python active/living/placed player-state predicate.
def _player_is_targetable(state: GameState, player_index: int) -> bool:
    player = state.players[player_index]
    return bool(player.active and player.health > 0 and player.mob_slot)


# ROM: part game:0x4DFF6 | Extracts the power, potion, multiplier and key weighted-value calculation used to select a victim.
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


# ROM: direct game:0x4DFF6 | Represents victim selection by weighted player possessions.
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


# ROM: direct game:0x4E432 | Level thief-state reset and appearance/victim setup, with additional Python setup bookkeeping.
def thief_setup(state: GameState) -> None:
    """0x4E432 -- reset this level's thief state and roll its appearance."""
    state.thief_level_setup_done = True
    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    state.thief_enter_time = -1
    state.thief_item_carried = _THIEF_CARRIED_EMPTY
    state.mugger_item_carried = 0
    state.thief_mode = THIEF_DEAD
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


# ROM: part game:0x4E4D8 | Extracts target score-per-coin, maze/level and random arrival-delay arithmetic at 0x4E568-0x4E620.
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


# ROM: direct game:0x4E4D8 | Selects the remaining thief/mugger variant and schedules its arrival.
def thief_timer_set(state: GameState) -> None:
    """0x4E4D8 -- choose the variant and schedule the next arrival."""
    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    state.thief_enter_time = -1
    # 0x4E4FA-0x4E510: a slot word is all it asks of the victim. One leaving by an exit
    # still has one, so the next arrival is scheduled all the same.
    if state.thief_victim < 0 or not state.players[state.thief_victim].mob_slot:
        return
    if state.thief_mode & (THIEF_ENTER_OK | THIEF_ENTER_OK_MUGGER) == (
        THIEF_ENTER_OK | THIEF_ENTER_OK_MUGGER
    ):
        return

    state.thief_mode = (state.thief_mode & 0xFF70) | THIEF_PURSUE     # 0x4E528-0x4E52C
    is_mugger = False
    if not state.thief_mode & THIEF_ENTER_OK_MUGGER:
        is_mugger = state.getrandom(32) < 16 or bool(state.thief_mode & THIEF_ENTER_OK)
    if is_mugger:
        state.thief_mode |= THIEF_IS_MUGGER
        state.thief_speed = _SPEED_MUGGER
    else:
        state.thief_speed = _SPEED_THIEF
    state.thief_enter_time = _thief_delay_frames(state)


# ROM: part game:0x4DEB8 | Extracts the deployment branch's thief-versus-mugger initial picture selection.
def _spawn_picture(state: GameState) -> int:
    return 0x2400 if state.thief_mode & THIEF_IS_MUGGER else 0x0DEA


# ROM: part game:0x4DEB8 | Extracted arrival deployment transaction at 0x4DEDC-0x4DFDE.
def _thief_deploy(state: GameState) -> None:
    """0x4DEDC-0x4DFDE -- create the thief after its arrival timer expires."""
    from .monster_spawning import tile_occupancy_test
    from .shot_effects import tport_cycle_start

    slot = state.thief_start_location
    if state.mobs.picture[slot] != 0 or not tile_occupancy_test(state, slot):
        state.thief_enter_time = 0x12C              # 0x4DFE0
        return

    row, col = slot >> 5, slot & 0x1F
    palette = 1 if state.thief_mode & THIEF_IS_MUGGER else 0
    state.mobs.create(
        slot,
        _spawn_picture(state),
        encode_hpos(col * 16 - 4, palette=palette),
        encode_vpos_at_y(row * 16, width=3, height=3),
        MazeObjIds.PLAYERSTART,
    )
    tport_cycle_start(state, slot, state.thief_victim)  # 0x4DF84
    state.thief_mob_slot = slot
    state.thief_current_pos = slot
    state.thief_previous_pos = slot
    state.thief_next_pos = slot
    state.thief_direction = 8
    state.thief_enter_time = 0x3C
    state.thief_collision_direction_code = 0        # 0x4DF9C
    state.thief_tport_timer = -1                    # 0x4DFA2
    path_grid_set_high_direction_if_empty(state, slot, 8)
    thief_compute_path(state)
    _sound_play(state, 0x2D if state.thief_mode & THIEF_IS_MUGGER else 0x29)


# ROM: direct game:0x4DEB8 | Thief arrival timer and deployment entry; includes a development-load setup fallback.
def main_start_thief(state: GameState) -> None:
    """0x4DEB8 -- schedule/deploy bookkeeping and the arrival pause."""
    if state.thief_enter_time < 0:
        # Direct dev/test level loads do not run main_start_game's 0x4835E tail.
        # Let them perform that setup once without repeating its RNG draw. A level
        # behind its splash, or a new game with nobody placed, is only waiting for
        # that tail to run.
        if (
            not state.thief_level_setup_done and not state.level_start_pending
            and state.level_players_active
        ):
            thief_setup(state)
        return
    if state.thief_enter_time > 0:
        state.thief_enter_time -= 1
        return
    if state.thief_current_pos:
        state.thief_enter_time = -1
        return
    _thief_deploy(state)


# ROM: part game:0x4E122,game:0x4E172,game:0x4E1B8 | Factors the shared route-repair tail after exit, dodge-end and dodge-begin mode changes.
def _repair_route_after_mode_toggle(state: GameState) -> None:
    if state.thief_previous_pos == state.thief_current_pos:
        thief_compute_path(state)
    else:
        state.thief_next_pos = state.thief_previous_pos


# ROM: part game:0x4A53A | Thief loot carry-over at 0x4A6F0-0x4A742, run when the last hero has left.
def carry_thief_loot_over(state: GameState) -> None:
    """0x4A6F0-0x4A742 -- what an escaping thief takes with it to the next level."""
    if state.thief_mode & THIEF_ESCAPE and state.thief_current_pos:
        if state.thief_mode & THIEF_IS_MUGGER:
            state.mugger_item_nextlevel = state.mugger_item_carried
        else:
            state.thief_item_nextlevel = state.thief_item_carried
        return
    if state.thief_item_carried == _THIEF_CARRIED_EMPTY:
        state.thief_item_nextlevel = _THIEF_CARRIED_EMPTY
    if not state.mugger_item_carried:
        state.mugger_item_nextlevel = 0


# ROM: direct game:0x4E122 | Changes pursuit to retraced-route escape.
def thief_exit(state: GameState) -> None:
    """0x4E122 -- change an active thief from pursuit to route-retracing escape."""
    if not state.thief_current_pos or state.thief_mode & THIEF_ESCAPE:   # 0x4E12C-0x4E13A
        state.thief_enter_time = -1                                     # 0x4E166
        return
    state.thief_mode = (state.thief_mode & ~0x09) | THIEF_ESCAPE
    _repair_route_after_mode_toggle(state)


# ROM: direct game:0x4E1B8 | Sets dodge, toggles pursuit/escape and repairs the route.
def thief_begin_dodge(state: GameState) -> None:
    """0x4E1B8 -- flip pursuit/escape while setting the dodge bit."""
    if not state.thief_current_pos or state.thief_mode & THIEF_DODGE:
        return
    state.thief_mode |= THIEF_DODGE
    state.thief_mode ^= THIEF_PURSUE | THIEF_ESCAPE
    _repair_route_after_mode_toggle(state)


# ROM: direct game:0x4E172 | Clears dodge, restores route polarity and repairs the route.
def thief_end_dodge(state: GameState) -> None:
    """0x4E172 -- clear the dodge bit and restore the previous route polarity."""
    if not state.thief_current_pos or not state.thief_mode & THIEF_DODGE:
        return
    state.thief_mode &= ~THIEF_DODGE
    state.thief_mode ^= THIEF_PURSUE | THIEF_ESCAPE
    _repair_route_after_mode_toggle(state)


# ROM: part game:0x4E1FE | Extracts weighted potion/multiplier/key theft selection and tie fallbacks.
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


# ROM: direct game:0x4E1FE | Theft/mugging transaction with item selection extracted.
def thief_steal_from_player(state: GameState, player_index: int) -> int:
    """0x4E1FE -- steal the ROM-selected item, or mug 100 health."""
    if state.thief_mode & THIEF_ESCAPE:
        return 0
    from .score import dialog_first_encounter

    thief_exit(state)
    player = state.players[player_index]

    if state.thief_mode & THIEF_IS_MUGGER:
        player.health = max(0, player.health - 100)
        state.mugger_item_carried = int(MazeObjIds.FOOD_INVULN)
        dialog_first_encounter(state, player_index, _DIALOG_KILL_MUGGER)  # 0x4E274
        state.thief_mode |= THIEF_ENTER_OK_MUGGER
        if hasattr(state, "health_dirty"):
            state.health_dirty[player_index] = 1
        _sound_play(state, 0x26)
        return 1

    state.thief_mode |= THIEF_JUMPJUMP
    state.thief_stolen_item = 0
    if player.powers & 0x00FF:
        state.thief_item_carried = int(MazeObjIds.POT_INVULN)
        for mask in _THIEF_STEALABLE_POWER_MASKS:
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

    from .player_lifecycle import setup_infopanel

    setup_infopanel(state, player_index)                         # 0x4E3F8
    dialog_first_encounter(state, player_index, _DIALOG_KILL_THIEF)  # 0x4E40A
    state.thief_mode |= THIEF_ENTER_OK
    _sound_play(state, 0x26)
    return 1


# ROM: direct game:0x4F5C8 | Thief removal, bounty, transporter cleanup, carried-item recreation and rescheduling entry.
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
        player_add_score_with_mult(state, score_player, 0x1F4)

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
        from .shot_effects import tport_cycle_start

        tport_cycle_start(state, drop_slot, effect_player)
        state.mobs.unlink_and_clear(current_slot)

    # 0x4F662-0x4F6A6 tears down an in-flight thief transporter transition
    # before creating the replacement pickup.
    if getattr(state, "thief_tport_timer", -1) >= 0:
        transition_slot = getattr(state, "thief_tport_dest", 0)
        if transition_slot and transition_slot != current_slot:
            state.mobs.unlink_and_clear(transition_slot)
        if state.mobs.picture[_THIEF_TPORT_ANIM_SLOT]:
            state.mobs.depth_remove(_THIEF_TPORT_ANIM_SLOT - 1)
            state.mobs.picture[_THIEF_TPORT_ANIM_SLOT] = 0
        state.thief_tport_timer = -1
        state.thief_tport_active = 0

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


# ROM: helper | Resolves duplicate Python thief slot/current-position fields.
def _slot_for_thief(state: GameState) -> int:
    return state.thief_mob_slot or state.thief_current_pos


# ROM: helper | Python helper: a record is a hero by its palette nibble, 0xC plus the player (0x4F77C, 0x4EFF6).
def _is_hero_record(state: GameState, slot: int) -> bool:
    return (state.mobs.hpos[slot] & 0x0F) >= 0x0C


# ROM: part game:0x4F742 | Extracts the escape-contact damage table, redraw, hurt timer and sound branch.
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


# ROM: direct game:0x4F742 | Prospective-cell interaction: -1 lets the thief's move stand, 0 blocks it.
def thief_handle_tile_collision(state: GameState, candidate_mob_slot: int) -> int:
    """0x4F742 -- what the record a probe found does to the thief's move.

    It returns -1 when the move may stand: a transporter route took it, or the
    record was a monster beaten after the fight dwell, or an object the thief
    removes. Everything else, walls and heroes included, returns 0 and blocks.
    A hero is recognized by palette nibble, and is only fought while escaping.
    """
    slot = candidate_mob_slot
    if _is_hero_record(state, slot):                                  # 0x4F77C-0x4F784
        if state.thief_mode & THIEF_ESCAPE:                           # 0x4F788
            if not state.thief_collision_direction_code:              # 0x4F794
                state.thief_collision_direction_code = state.thief_direction + 1
                state.thief_stolen_item = 0                           # 0x4F86A-0x4F876
            elif state.thief_stolen_item > 0x0F:                      # 0x4F79A
                _damage_player_from_escape_contact(
                    state, state.mobs.state(slot),                    # 0x4F7AE-0x4F7BC
                )
                state.thief_collision_direction_code = 0              # 0x4F866
        return 0

    obj_type = state.mobs.obj_type(slot)
    if thief_test_move_tile(state, slot, obj_type):                   # 0x4F88A
        return -1
    if int(MazeObjIds.MONST_GHOST) <= obj_type <= int(MazeObjIds.GEN_AUX_GRUNT3):  # 0x4F89A
        if not state.thief_collision_direction_code:                  # 0x4F8A6
            state.thief_collision_direction_code = state.thief_direction + 1
            state.thief_stolen_item = 0
            return 0
        if state.thief_stolen_item <= 0x0F:                           # 0x4F8AA
            return 0
        from .shot_effects import shot_impact_spawn

        shot_impact_spawn(state, slot, state.thief_victim)            # 0x4F8C0
        state.mobs.unlink_and_clear(slot)                             # 0x4F8CC
        state.thief_collision_direction_code = 0
        return -1
    if _THIEF_COLLISION_REMOVE_FLAGS[obj_type]:                       # 0x4F8EA-0x4F8FE
        state.mobs.unlink_and_clear(slot)
        return -1
    return 0


# ROM: direct game:0x4E7FC | Transporter-route and corner-recovery test for a proposed cell.
def thief_test_move_tile(
    state: GameState, candidate_pos: int, object_type: int,
) -> int:
    """0x4E7FC -- resolve route transport and diagonal corner recovery."""
    if (
        candidate_pos == state.thief_next_pos
        and object_type == int(MazeObjIds.TRANSPORTER)
    ):
        return thief_enter_tport(state, candidate_pos)

    if path_grid_get_direction(state, state.thief_next_pos) != 8:
        return 0

    # A direction of 8 (previous and next the same cell, as after a dodge
    # begins) is not a stop: it steps nowhere, and 0x4E8AC then squeezes the
    # thief through if that cell is where the victim stands.
    direction = calc_direction(
        state, state.thief_previous_pos, state.thief_next_pos,
    )                                                                 # 0x4E854
    corner_target = _advance_route_cell(state.thief_next_pos, direction) & 0x3FF
    corner_direction = path_grid_get_direction(state, corner_target)  # 0x4E88E
    if (
        corner_direction == 8
        or (direction ^ corner_direction) == 4
    ) and corner_target != state.thief_victim_pos:                    # 0x4E8AC
        return 0
    # corner_squeeze_geometry's thief arm first tests the probed record (0x4FFB6-0x4FFF4).
    if (state.mobs.hpos[candidate_pos] & 0x0F) >= 0x0C:
        return 0
    if (
        int(MazeObjIds.MONST_GHOST)
        <= object_type
        <= int(MazeObjIds.MONST_IT)
    ) or object_type == int(MazeObjIds.MONST_DRAGON):
        return 0

    return _thief_corner_squeeze_geometry(state, direction)


# ROM: part game:0x4FEB2 | Extracts corner_squeeze_geometry's player-index-4 thief arm at 0x4FFB6-0x50218.
def _thief_corner_squeeze_geometry(
    state: GameState, direction: int,
) -> int:
    """corner_squeeze_geometry's player-index-4 arm, 0x4FFB6-0x50218."""
    target = _advance_route_cell(state.thief_previous_pos, direction) & 0x3FF
    if target < FIRST_PLAYABLE_SLOT or state.mobs.picture[target]:
        target = _advance_route_cell(target, direction) & 0x3FF
        if target < FIRST_PLAYABLE_SLOT:
            return 0
    if (state.mobs.hpos[target] & 0x0F) > 0x0C:
        return 0

    for player_index in range(len(state.players)):
        if (
            state.player_tile_or_tport_dest[player_index] == target
            and state.player_tport_phase[player_index] >= 0
        ):
            return 0

    path_grid_set_high_direction_if_empty(
        state, target, (direction + 4) & 0x07,
    )
    thief_start_tport_anim(state, target)
    state.thief_previous_pos = target
    return -2


# ROM: direct game:0x4FBFC | Starts shared transporter animation and creates the thief destination placeholder.
def thief_start_tport_anim(state: GameState, destination_pos: int) -> None:
    """0x4FBFC -- arm the shared transition and destination placeholder."""
    from .player_transport import handle_tport

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


# ROM: direct game:0x4FAD4 | Follows learned transporter routes, checks the landing and starts transition.
# ROM: part game:0x510BC | Inlines the selected forward/reverse route-word reads through flattened Python arrays.
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
    from .player_transport import nearby_mob_clearance_test

    if not nearby_mob_clearance_test(state, landing, 4):
        return 0
    tport_route_connect_if_empty(
        state, transporter_pos, destination_pad, state.thief_previous_pos,
    )
    thief_start_tport_anim(state, landing)
    state.thief_previous_pos = destination_pad
    return -1


# ROM: direct game:0x4EE0A | One probe of the movement engine: a blocking record undoes ``delta`` of the step.
def thief_probe_axis(state: GameState, probe, positions, delta: int) -> int:
    """0x4EE0A -- the blocking slot, or -1 when the step stands.

    The undo also clears bits 6 and 7 of the position word (``andi #$FF3F``),
    so a blocked thief lands on an even pixel.
    """
    current = state.thief_current_pos
    hit = probe(state, current)                       # 0x4EE2A
    if hit < 0:
        return -1
    hit &= 0x3FF                                      # 0x4EE30
    if thief_handle_tile_collision(state, hit):       # 0x4EE3A
        return -1
    positions[current] = ((positions[current] + delta) & 0xFFFF) & 0xFF3F  # 0x4EE44-0x4EE66
    return hit


# ROM: direct game:0x4EE7A | Thief movement: right or left, then down or up, each probed, with wall-corner nudges, hero contact and cell migration.
def thief_move_engine(
    state: GameState,
    move_flags: int,
    horizontal_speed: int,
    vertical_speed: int,
) -> int:
    """0x4EE7A -- move the thief one frame; returns the fight latch plus one if it got anywhere.

    ``move_flags`` is active low: bit 4 clear moves right, bit 5 left, bit 6 down
    and bit 7 up. A blocked right or up step is undone only by the speed beyond
    one pixel, while a blocked left or down step is undone completely. A wall
    met with more than 0x200 of overlap on the other axis nudges the thief a
    pixel round its corner instead of moving on the other axis. Touching a hero
    who is not transporting counts as getting somewhere, and tries the theft.
    """
    from .mob_probes import mob_probe_down, mob_probe_left, mob_probe_right, mob_probe_up

    current = state.thief_current_pos
    hpos, vpos = state.mobs.hpos, state.mobs.vpos
    saved_h, saved_v = hpos[current], vpos[current]                       # 0x4EEA2-0x4EEB0
    h_excess = horizontal_speed - 0x80 if horizontal_speed >= 0x80 else 0  # 0x4EEBC
    v_excess = vertical_speed - 0x80 if vertical_speed >= 0x80 else 0      # 0x4EEC8
    got_somewhere = 0

    # ROM: helper | Neighbour arithmetic the four arms repeat inline (0x4EF3E-0x4EF62 and kin).
    def cell(column_delta: int, row_delta: int) -> int:
        return ((current + column_delta) & 0x1F) + ((current + row_delta) & 0x3E0)

    # ROM: helper | The 0x8000/0x8001 picture test each arm repeats inline (0x4EF0A-0x4EF2E and kin).
    def wall(hit: int) -> bool:
        return state.mobs.picture[hit] in (0x8000, 0x8001)

    # ROM: helper | The position-word add each arm repeats inline (0x4EEE6 and kin).
    def step(positions, amount: int) -> None:
        positions[current] = (positions[current] + amount) & 0xFFFF

    # ROM: helper | A wall-corner nudge and its probe, repeated inline in each arm (0x4EF6E-0x4EF90 and kin).
    def nudge(positions, amount: int, probe) -> None:
        nonlocal got_somewhere
        step(positions, amount)
        if thief_probe_axis(state, probe, positions, -amount) < 0:
            got_somewhere = 1

    # ROM: helper | Hero-contact arm repeated inline after each probe (0x4EFE8-0x4F048 and kin).
    def hero(hit: int) -> bool:
        """0x4EFE8-0x4F048: a hero who is not transporting is reached; the theft is tried."""
        nonlocal got_somewhere
        nibble = hpos[hit] & 0x0F
        if nibble < 0x0C or state.player_tport_phase[nibble - 0x0C] != -1:
            return False
        got_somewhere = 1
        return bool(thief_steal_from_player(state, state.mobs.state(hit)))

    corner = False
    if not move_flags & 0x10:                                     # right, 0x4EED8
        step(hpos, horizontal_speed)
        hit = thief_probe_axis(state, mob_probe_right, hpos, -h_excess)
        if hit < 0:
            got_somewhere = 1
        elif wall(hit):
            if state.collision_dist_V > 0x200:                    # 0x4EF32
                if hit == cell(1, 0x20) and move_flags & 0x40:
                    nudge(vpos, 0x80, mob_probe_up)
                    corner = True
                elif hit == cell(1, -0x20) and move_flags & 0x80:
                    nudge(vpos, -0x80, mob_probe_down)
                    corner = True
        elif hero(hit):
            hpos[current] = saved_h                               # 0x4F048
    elif not move_flags & 0x20:                                   # left, 0x4F052
        step(hpos, -horizontal_speed)
        hit = thief_probe_axis(state, mob_probe_left, hpos, horizontal_speed)
        if hit < 0:
            got_somewhere = 1
        elif wall(hit):
            if state.collision_dist_V > 0x200:                    # 0x4F0A8
                if hit == cell(-1, 0x20) and move_flags & 0x40:
                    nudge(vpos, 0x80, mob_probe_up)
                    corner = True
                elif hit == cell(-1, -0x20) and move_flags & 0x80:
                    nudge(vpos, -0x80, mob_probe_down)
                    corner = True
        elif hero(hit):
            hpos[current] = saved_h                               # 0x4F1BE

    if not corner:
        if not move_flags & 0x40:                                 # down, 0x4F1C4
            step(vpos, -vertical_speed)
            hit = thief_probe_axis(state, mob_probe_down, vpos, vertical_speed)
            if hit < 0:
                got_somewhere = 1
            elif wall(hit):
                if state.collision_dist_H > 0x200:                # 0x4F21C
                    if hit == cell(-1, 0x20) and move_flags & 0x20:
                        nudge(hpos, 0x80, mob_probe_right)
                    elif hit == cell(1, 0x20) and move_flags & 0x10:
                        nudge(hpos, -0x80, mob_probe_left)
            elif hero(hit):
                vpos[current] = saved_v                           # 0x4F32A
        elif not move_flags & 0x80:                               # up, 0x4F334
            step(vpos, vertical_speed)
            hit = thief_probe_axis(state, mob_probe_up, vpos, -v_excess)
            if hit < 0:
                got_somewhere = 1
            elif wall(hit):
                if state.collision_dist_H > 0x200:                # 0x4F390
                    if hit == cell(-1, -0x20) and move_flags & 0x20:
                        nudge(hpos, 0x80, mob_probe_right)
                    elif hit == cell(1, -0x20) and move_flags & 0x10:
                        nudge(hpos, -0x80, mob_probe_left)
            elif hero(hit):
                vpos[current] = saved_v                           # 0x4F49C

    # 0x4F4A2-0x4F4DA: the cell the body is now in.
    x = _s16(_s16(hpos[current]) >> POS_SHIFT & 0xFFFF)
    y = _s16(_s16(vpos[current]) >> POS_SHIFT & 0xFFFF)
    new_cell = ((x + 12) >> 4 & 0x1F) + ((((y + 8) & 0x1F0) ^ 0x1F0) << 1)
    # 0x4F4DC-0x4F546: a step of more than two pixels on either axis ends a fight.
    dh = _s16(position_field(saved_h) - position_field(hpos[current]))
    dv = _s16(position_field(saved_v) - position_field(vpos[current]))
    if not (-0x100 <= dh <= 0x100 and -0x100 <= dv <= 0x100):
        state.thief_collision_direction_code = 0
    if (not state.thief_tport_active and new_cell != current         # 0x4F54C-0x4F568
            and not state.mobs.picture[new_cell]):
        state.mobs.move_slot(current, new_cell)                      # 0x4F576
        state.thief_current_pos = state.thief_mob_slot = new_cell
        if state.thief_next_pos == new_cell:                         # 0x4F582
            path_grid_set_high_direction_if_empty(
                state, new_cell, (state.thief_path_direction + 4) & 7,
            )
    return state.thief_collision_direction_code + got_somewhere


# ROM: helper | Python signed-16-bit view of a word.
def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


# ROM: helper | Reads a player shot's direction word at 0x9049C4, as 0x4FD44 and 0x4E9F2 do.
def _shot_direction(state: GameState, player_index: int) -> int:
    return state.shot_direction[player_index]


# ROM: helper | Generic Python shortest wrapped-axis delta utility.
def _wrapped_axis_delta(value: int, wraps: bool) -> int:
    if wraps:
        if value > _WORLD_PIXELS // 2:
            value -= _WORLD_PIXELS
        elif value < -_WORLD_PIXELS // 2:
            value += _WORLD_PIXELS
    return value


# ROM: helper | Python division primitive truncating signed values toward zero.
def _trunc_div(value: int, divisor: int) -> int:
    return value // divisor if value >= 0 else -((-value) // divisor)


# ROM: part game:0x4FCF0 | Extracts the eight exact axis/diagonal shot-ray predicates used by the dodge scan.
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


# ROM: direct game:0x4FCF0 | Represents the opposing-direction player-shot ray scan; helper arithmetic is not independently callable in ROM.
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


# ROM: part game:0x4E8DC | Extracts the post-theft pause, jump animation and taunt at 0x4E90C-0x4E99C.
def _escape_animation(state: GameState) -> bool:
    """Advance the post-theft jump at 0x4E90C-0x4E99C; True when it holds the thief still.

    For its first 0x1C frames the thief keeps running and only counts (0x4E916,
    0x4E99C). After that it stands and plays the jump, then taunts.
    """
    if not state.thief_mode & THIEF_JUMPJUMP:
        return False
    counter = state.thief_stolen_item
    if counter < 0x1C:
        state.thief_stolen_item = counter + 1
        return False
    slot = _slot_for_thief(state)
    if slot:
        state.mobs.picture[slot] = _THIEF_ESCAPE_ANIM[((counter - 0x1C) >> 2) & 7]
    state.thief_stolen_item = counter + 1
    if state.thief_stolen_item > _TAUNT_THRESHOLD:
        state.thief_mode &= ~THIEF_JUMPJUMP
        laugh, speech = _TAUNT_PAIRS[state.getrandom(2)]
        _sound_play(state, laugh)
        _sound_speech_play(state, speech)
    return True


# ROM: part game:0x4E8DC | Extracts return-to-start escape completion, next-level carried-item handoff and rescheduling.
def _finish_escape_at_start(state: GameState) -> bool:
    if not state.thief_mode & THIEF_ESCAPE:
        return False
    if state.thief_current_pos != state.thief_start_location:
        return False
    if state.thief_previous_pos == state.thief_start_location:
        return False
    from .score import dialog_first_encounter

    # 0x4EBC0-0x4EC0A: "find stolen item on next level", when there is an item.
    victim = state.thief_victim
    if state.thief_mode & THIEF_IS_MUGGER:
        tell = (
            0 <= victim < len(state.players)
            and state.players[victim].mob_slot and state.mugger_item_carried
        )
    else:
        tell = state.thief_item_carried != _THIEF_CARRIED_EMPTY
    if tell:
        dialog_first_encounter(state, victim, _DIALOG_FIND_STOLEN_ITEM)

    slot = _slot_for_thief(state)
    if state.thief_mode & THIEF_IS_MUGGER:
        state.mugger_item_nextlevel = state.mugger_item_carried
    else:
        state.thief_item_nextlevel = state.thief_item_carried
    if slot:
        from .shot_effects import tport_cycle_start

        tport_cycle_start(state, slot, state.thief_victim)
        state.mobs.unlink_and_clear(slot)
    state.thief_current_pos = 0
    state.thief_mob_slot = 0
    thief_timer_set(state)
    return True


# ROM: part game:0x4E8DC | Extracts dodge acquisition and tracked-shot disappearance/direction-change handling.
def _update_dodge(state: GameState) -> None:
    """0x4E9A2-0x4EA30. Nothing changes while the dodge has begun but not yet moved (0x4E9AC)."""
    if state.thief_mode & THIEF_IS_MUGGER:
        return
    if state.thief_pursuit_direction < 0:
        return
    if state.thief_mode & THIEF_DODGE:
        player_index = state.thief_pursuit_player
        shot_slot = player_index + 1
        if not 0 <= player_index < 4 or not state.mobs.picture[shot_slot]:
            thief_end_dodge(state)                                   # 0x4E9D6
            return
        if _shot_direction(state, player_index) != state.thief_pursuit_shot_direction:
            thief_end_dodge(state)                                   # 0x4E9F2-0x4E9F8
        return
    player_index = thief_find_aligned_shooter(state)
    if player_index < 0:
        return
    thief_begin_dodge(state)
    state.thief_pursuit_direction = -1
    state.thief_pursuit_player = player_index
    state.thief_pursuit_shot_direction = _shot_direction(state, player_index) & 0xFF  # 0x4EA28, low byte
    state.thief_direction_change_pos = 0


# ROM: part game:0x4E8DC | Extracts fight, compact movement and idle animation selection from the frame-service tail.
def _set_thief_animation(state: GameState, movement_result: int) -> None:
    slot = _slot_for_thief(state)
    if not slot:
        return
    direction = state.thief_direction
    if state.thief_collision_direction_code:
        if not 0 <= direction < 8:
            return
        counter = state.thief_stolen_item
        state.thief_stolen_item = (counter + 1) & 0xFFFF
        table = _MUGGER_WALK_ANIM if state.thief_mode & THIEF_IS_MUGGER else _THIEF_WALK_ANIM
        state.mobs.picture[slot] = table[direction * 8 + ((counter >> 2) & 7)]
    elif movement_result and 0 <= direction < 8:
        counter = state.thief_stolen_item
        state.thief_stolen_item = (counter + 1) & 0xFFFF
        table = _MUGGER_COMPACT_ANIM if state.thief_mode & THIEF_IS_MUGGER else _THIEF_COMPACT_ANIM
        state.mobs.picture[slot] = table[direction * 4 + ((counter >> 2) & 3)]
    else:
        table = _MUGGER_IDLE_ANIM if state.thief_mode & THIEF_IS_MUGGER else _THIEF_IDLE_ANIM
        state.mobs.picture[slot] = table[min(direction, 8)]


# ROM: direct game:0x4E8DC | Thief frame-service entry with escape, dodge and animation branches extracted.
def main_thief_anim(state: GameState) -> None:
    """0x4E8DC -- thief state graph, dodge latches, movement and animation.

    On reaching its next route cell the thief first walks to the cell's centre,
    each axis at most its speed and at most the distance left (0x4EA4A-0x4EB66).
    Only once centred does it wait on a dodge, finish an escape, or take the
    next route step (0x4EB68-0x4EC78).
    """
    if not state.thief_current_pos or state.thief_enter_time >= 0:
        return
    if state.thief_tport_timer >= 0:                 # 0x4E900-0x4E908
        return
    if _escape_animation(state):
        return

    _update_dodge(state)                             # 0x4E9A2-0x4EA30
    horizontal_speed = vertical_speed = state.thief_speed   # 0x4EA36-0x4EA3C
    current = state.thief_current_pos
    if current == state.thief_next_pos:              # 0x4EA3E
        direction, horizontal_speed, vertical_speed = _centring_step(
            state, horizontal_speed,
        )
        if not horizontal_speed and not vertical_speed:
            if (                                     # 0x4EB74-0x4EB96
                state.thief_mode & THIEF_DODGE
                and state.thief_pursuit_direction >= 0
                and state.thief_direction_change_pos
                and state.thief_direction_change_pos != current
            ):
                return
            if _finish_escape_at_start(state):       # 0x4EB9A-0x4EC56
                return
            thief_compute_path(state)                # 0x4EC5A
            horizontal_speed = vertical_speed = state.thief_speed
            direction = calc_direction(state, current, state.thief_next_pos)
    else:
        direction = calc_direction(state, current, state.thief_next_pos)  # 0x4EC92

    if state.thief_mode & THIEF_DODGE:               # 0x4EC9A-0x4ECC2
        if state.thief_pursuit_direction < 0:
            state.thief_pursuit_direction = direction
        elif direction != state.thief_direction:
            state.thief_direction_change_pos = current
    state.thief_direction = direction
    if not 0 <= direction <= 8:
        return

    state.thief_tport_active = 0                     # 0x4ECDC
    movement_result = thief_move_engine(
        state,
        _THIEF_DIRECTION_STEP_SIZE[direction],
        horizontal_speed,
        vertical_speed,
    )
    if movement_result < 0:
        return
    _set_thief_animation(state, movement_result)


# ROM: part game:0x4E8DC | The centring step at 0x4EA4A-0x4EB66: direction to the next cell's anchor, and speeds clamped to the distance left.
def _centring_step(state: GameState, speed: int) -> tuple[int, int, int]:
    """``(direction, horizontal speed, vertical speed)`` toward the anchor of ``thief_next_pos``.

    Distances are in position units and wrap at half the maze. An axis within
    0x80 of the anchor gives way to the other in the direction; both speeds
    are zero once the thief stands exactly on the anchor.
    """
    current, target = state.thief_current_pos, state.thief_next_pos
    dh = ((target & 0x1F) << 11) - 0x200 - position_field(state.mobs.hpos[current])
    dv = ((((target & 0x3E0) ^ 0x3E0) << 6)) - position_field(state.mobs.vpos[current])
    if dh > 0x1000:                                  # 0x4EAA6-0x4EAC0
        dh -= 0x10000
    elif dh < -0x1000:
        dh += 0x10000
    if dv > 0x1000:
        dv -= 0x10000
    elif dv < -0x1000:
        dv += 0x10000
    direction = 1                                    # 0x4EAE2-0x4EB26
    if -0x80 < dh < 0x80:
        direction = 0
    if -0x80 < dv < 0x80:
        direction = 2
    if dh <= -0x80:
        direction = (8 - direction) & 7
    if dv <= -0x80:
        direction = (12 - direction) & 7
    horizontal = min(speed, abs(dh))                 # 0x4EB28-0x4EB46
    vertical = min(speed, abs(dv))                   # 0x4EB48-0x4EB66
    return direction, horizontal, vertical
