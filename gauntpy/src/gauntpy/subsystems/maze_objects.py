"""The living maze: doors, walls, transporters, and forcefields -- WP-11.

Reference: ``doc/04_game_subsystems.md`` §§7, 18, and 19; the corresponding
generated contracts; and ROM routines 0x40528, 0x45C00, 0x52F26, 0x53346,
0x53398, 0x5E41A, 0x5E62A, 0x5025C, and 0x509E4.
"""

from __future__ import annotations

from ..constants import FIRST_PLAYABLE_SLOT, GameMode, MazeObjIds, NUM_MOB_SLOTS
from ..coords import encode_hpos, encode_vpos_at_y, slot_to_pixels
from ..playfield_vram import (
    SPECIAL_COLOR_INDEX_1,
    SPECIAL_COLOR_INDEX_2,
    TRANSPORTER_COLOR_CYCLE,
    write_playfield_color,
    write_playfield_colors,
)
from ..state import GameState
from .sound import sound_play as _sound_play

_SOUND_DOORS_OPEN = 0x12
_SOUND_CYCLIC_WALLS = 0x2B

# ROM 0x571DA, four eight-byte profiles selected by level & 3.
_FORCEFIELD_DELAY_PROFILES = (
    (0x10, 0x20, 0x10, 0x20, 0x10, 0x20, 0x20, 0x40),
    (0x10, 0x20, 0x08, 0x10, 0x10, 0x20, 0x08, 0x40),
    (0x08, 0x08, 0x08, 0x20, 0x10, 0x20, 0x08, 0x40),
    (0x10, 0x10, 0x20, 0x20, 0x40, 0x40, 0x08, 0x40),
)

_DOOR_JUNCTION_MIN = 0x9D18
_DOOR_JUNCTION_MAX = 0x9D38
_DOOR_HORIZONTAL_MIN = 0x9D3C
_DOOR_HORIZONTAL_MAX = 0x9D6E
_DOOR_VERTICAL_MIN = 0x9D7C
_DOOR_VERTICAL_MAX = 0x9DAC

# Door picture/position tables, ROM 0x5F9CE and 0x5FACA-0x5FC11.
_DOOR_GFX_BY_NEIGHBORS = (
    0x9D28, 0x9D24, 0x9D1C, 0x9D34,
    0x9D20, 0x9D28, 0x9D2C, 0x9D1C,
    0x9D18, 0x9D38, 0x9D28, 0x9D24,
    0x9D30, 0x9D18, 0x9D20, 0x9D28,
)
_DOOR_GFX_TYPE2 = (
    0x9D5A, 0x9D60, 0x9D3C, 0x9D68, 0x9D6E,
    0x9D42, 0x9D4C, 0x9D52, 0x9D48,
)
_DOOR_HPOS_SUB2 = (
    0x0200, 0x0200, 0x0200, 0x0280, 0x0280,
    0x0280, 0x0200, 0x0200, 0x0000,
)
_DOOR_VPOS_ADD2 = (
    0x0011, 0x0019, 0x0011, 0x0011, 0x0019,
    0x0011, 0x0011, 0x0019, 0x0009,
)
_DOOR_GFX_TYPE3 = (
    0x9D98, 0x9D9E, 0x9D7C, 0x9DA4, 0x9DAC,
    0x9D8C, 0x9D82, 0x9D86, 0x9D94,
)
_DOOR_VPOS_SUB3 = (
    0x0000, 0x0100, 0x0000, 0x0000, 0x0000,
    0x0100, 0x0000, 0x0000, 0x0100,
)
_DOOR_VPOS_ADD3 = (
    0x000A, 0x000A, 0x000A, 0x000B, 0x000B,
    0x000B, 0x0009, 0x000A, 0x0009,
)

_FORCEFIELD_BLOCKERS = frozenset((
    int(MazeObjIds.WALL_REGULAR),
    int(MazeObjIds.WALL_SECRET),
    int(MazeObjIds.WALL_DESTRUCTABLE),
    int(MazeObjIds.WALL_RANDOM),
    int(MazeObjIds.WALL_TRAPCYC1),
    int(MazeObjIds.WALL_TRAPCYC2),
    int(MazeObjIds.WALL_TRAPCYC3),
))

_POWER_TRANSPORT = 0x0800


def _slot_is_linked(state: GameState, slot: int) -> bool:
    return state.mobs.is_linked(slot)


def _clear_slot(state: GameState, slot: int) -> None:
    """Clear a dynamic MOB without corrupting synthetic, unlinked test tiles."""
    from ..maze import clear_cell_descriptor

    was_door = _is_door(state, slot)
    clear_cell_descriptor(state, slot)
    if _slot_is_linked(state, slot):
        state.mobs.unlink_and_clear(slot)
    else:
        state.mobs.picture[slot] = 0
        state.mobs.hpos[slot] = 0
        state.mobs.vpos[slot] = 0
        state.mobs.link[slot] = 0
        state.mobs.state_link[slot] = 0
    if was_door:
        setup_door_graphics(state)


def _remove_door_slot(state: GameState, slot: int) -> None:
    """Remove one door MOB without touching its existing floor descriptor."""
    if _slot_is_linked(state, slot):
        state.mobs.unlink_and_clear(slot)
    else:
        state.mobs.picture[slot] = 0
        state.mobs.hpos[slot] = 0
        state.mobs.vpos[slot] = 0
        state.mobs.link[slot] = 0
        state.mobs.state_link[slot] = 0
    data = getattr(state.maze, "data", None)
    if data is not None:
        row, col = divmod(slot, 32)
        data[(col, row)] = int(MazeObjIds.TILE_FLOOR)


def select_forcefield_delay_profile(state: GameState) -> None:
    """Install the exact ROM delay row selected by ``levelnum_current & 3``."""
    state.forcefield_step_durations = list(
        _FORCEFIELD_DELAY_PROFILES[state.levelnum_current & 3]
    )
    state.forcefield_segments.clear()
    state.forcefield_segments_ready = False
    state.cyclic_wall_setup_ready = False
    state.cyclic_wall_assign = [0] * len(state.cyclic_wall_assign)
    state.cyclic_wall_phase = 0
    state.cyclic_wall_timer = 0
    state.random_wall_setup_ready = False
    state.tport_secret_pad_masks = [0] * len(state.tport_secret_pad_masks)
    state.tport_secret_event_keys = [-1] * len(state.tport_secret_event_keys)


def _update_forcefield_color(state: GameState) -> None:
    if state.forcefield_step & 1:
        state.forcefield_color = 0
    else:
        color_index = (state.frame_counter & 0x0C) >> 2
        state.forcefield_color = state.forcefield_colors_table[color_index]


def _palette_color_indices(state: GameState) -> tuple[int, int, int]:
    floorpattern = int(getattr(state.maze, "floorpattern", 0) or 0)
    floorpattern %= len(SPECIAL_COLOR_INDEX_1)
    return (
        0,
        SPECIAL_COLOR_INDEX_1[floorpattern],
        SPECIAL_COLOR_INDEX_2[floorpattern],
    )


def _write_live_color(
    state: GameState, palette: int, word: int,
) -> None:
    for index in _palette_color_indices(state):
        write_playfield_color(state, palette * 16 + index, word)


def _write_transporter_colors_vblank(state: GameState) -> None:
    """game_vblank 0x40456-0x40476: palette 4 entries 8-13."""
    write_playfield_colors(
        state, 4 * 16 + 8,
        TRANSPORTER_COLOR_CYCLE[state.tport_cycle_pos % 6],
    )


def _door_neighbor(slot: int, dx: int, dy: int) -> int:
    row, col = slot >> 5, slot & 0x1F
    return (((row + dy) & 0x1F) << 5) | ((col + dx) & 0x1F)


def _is_door(state: GameState, slot: int) -> bool:
    if state.maze is not None:
        row, col = slot >> 5, slot & 0x1F
        data = getattr(state.maze, "data", None)
        if data is not None and (col, row) in data:
            return int(data[(col, row)]) in (
                int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT),
            )
    return state.mobs.obj_type(slot) in (
        int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT),
    )


def _is_blank_floor(state: GameState, slot: int) -> bool:
    """Exact pf_isblankfloor marker/type predicate at 0x5EA2E."""
    if (slot >> 5) == 0:
        return True
    return (
        state.mobs.picture[slot] == 0x8000
        and state.mobs.obj_type(slot) != int(MazeObjIds.FORCEFIELDHUB)
    )


def _door_orientation_index(
    state: GameState, slot: int, *, vertical: bool,
) -> int:
    """The 3x3 negative/neither/positive blank-floor selector at 0x5F9EE."""
    nx, ny = ((1, 0) if vertical else (0, 1))
    px, py = (-nx, -ny)
    sx, sy = ((0, 1) if vertical else (1, 0))

    if not _is_blank_floor(state, _door_neighbor(slot, px, py)):
        negative = 6
    elif (
        _is_blank_floor(state, _door_neighbor(slot, 2 * px, 2 * py))
        and not _is_blank_floor(state, _door_neighbor(slot, px + sx, py + sy))
        and not _is_blank_floor(state, _door_neighbor(slot, px - sx, py - sy))
    ):
        negative = 3
    else:
        negative = 0

    if _is_blank_floor(state, _door_neighbor(slot, nx, ny)):
        positive = 2
    elif (
        _is_blank_floor(state, _door_neighbor(slot, 2 * nx, 2 * ny))
        and not _is_blank_floor(state, _door_neighbor(slot, nx + sx, ny + sy))
        and not _is_blank_floor(state, _door_neighbor(slot, nx - sx, ny - sy))
    ):
        positive = 1
    else:
        positive = 0
    return negative + positive


def _draw_door_graphic(state: GameState, slot: int) -> None:
    """pf_door_draw_xy 0x5F876 for one already-classified door."""
    row, col = slot >> 5, slot & 0x1F
    obj_type = state.mobs.obj_type(slot)
    picture = state.mobs.picture[slot]
    if _DOOR_JUNCTION_MIN <= picture <= _DOOR_JUNCTION_MAX:
        door_class = 1
    elif _DOOR_HORIZONTAL_MIN <= picture <= _DOOR_HORIZONTAL_MAX:
        door_class = 2
    elif _DOOR_VERTICAL_MIN <= picture <= _DOOR_VERTICAL_MAX:
        door_class = 3
    else:
        door_class = (
            2 if obj_type == int(MazeObjIds.DOOR_HORIZ) else 3
        )
    horizontal = door_class == 2
    connected = (
        _is_door(state, _door_neighbor(slot, 0, -1))
        or _is_door(state, _door_neighbor(slot, 0, 1))
    ) if door_class == 2 else (
        _is_door(state, _door_neighbor(slot, -1, 0))
        or _is_door(state, _door_neighbor(slot, 1, 0))
    )
    if door_class == 1:
        connected = any(
            _is_door(state, _door_neighbor(slot, dx, dy))
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
        )

    if connected:
        neighbors = (
            int(_is_door(state, _door_neighbor(slot, 0, -1)))
            | (int(_is_door(state, _door_neighbor(slot, 1, 0))) << 1)
            | (int(_is_door(state, _door_neighbor(slot, 0, 1))) << 2)
            | (int(_is_door(state, _door_neighbor(slot, -1, 0))) << 3)
        )
        state.mobs.picture[slot] = _DOOR_GFX_BY_NEIGHBORS[neighbors]
        state.mobs.hpos[slot] = (col << 11) & 0xFFFF
        state.mobs.vpos[slot] = (((row << 11) ^ 0xF800) + 0x09) & 0xFFFF
        state.mobs.set_state(slot, neighbors)
        return

    horizontal = (
        door_class == 2
        or (
            door_class == 1
            and obj_type == int(MazeObjIds.DOOR_HORIZ)
        )
    )
    index = _door_orientation_index(state, slot, vertical=not horizontal)
    if horizontal:
        state.mobs.picture[slot] = _DOOR_GFX_TYPE2[index]
        state.mobs.hpos[slot] = (
            (col << 11) - _DOOR_HPOS_SUB2[index]
        ) & 0xFFFF
        state.mobs.vpos[slot] = (
            ((row << 11) ^ 0xF800) + _DOOR_VPOS_ADD2[index]
        ) & 0xFFFF
        state.mobs.set_state(slot, 10)
    else:
        state.mobs.picture[slot] = _DOOR_GFX_TYPE3[index]
        state.mobs.hpos[slot] = (col << 11) & 0xFFFF
        state.mobs.vpos[slot] = (
            ((row << 11) ^ 0xF800)
            - _DOOR_VPOS_SUB3[index]
            + _DOOR_VPOS_ADD3[index]
        ) & 0xFFFF
        state.mobs.set_state(slot, 5)


def refresh_surrounding_door_graphics(state: GameState, slot: int) -> None:
    """pf_door_update_surrounding_xy 0x5F7F0, including ROM visit order."""
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbour = _door_neighbor(slot, dx, dy)
        if _is_door(state, neighbour):
            _draw_door_graphic(state, neighbour)


def setup_door_graphics(state: GameState) -> None:
    """maze_doors_setup 0x5F7C0 -- draw the initial complete door set."""
    for slot in range(FIRST_PLAYABLE_SLOT, NUM_MOB_SLOTS):
        if _is_door(state, slot):
            _draw_door_graphic(state, slot)


def _transporter_id(state: GameState, slot: int) -> int:
    """0x4E7C0's one-based transporter ID, or zero when ``slot`` is absent."""
    transporter_id = 1
    for candidate in range(FIRST_PLAYABLE_SLOT, NUM_MOB_SLOTS):
        if state.mobs.obj_type(candidate) != int(MazeObjIds.TRANSPORTER):
            continue
        if candidate == slot:
            return transporter_id
        transporter_id += 1
    return 0


def record_transporter_secret_progress(
    state: GameState,
    player_index: int,
    source_slot: int,
    destination_pad: int,
    landing_slot: int,
    *,
    powers_gate: bool = False,
) -> None:
    """Apply the transporter-only secret hooks at 0x5025C and 0x509E4.

    Task 0x56 records the one-based source and destination transporter IDs as
    bits in the player's progress byte. Ordinary tricks 1-4 are completed by
    their exact movement consumers, which write the winner without touching
    the progress bytes.
    """
    if not 0 <= player_index < len(state.players) or powers_gate:
        return

    from .exits import (
        secret_trick_set,
    )

    # 0x5025C / 0x509E4: task 0x56 ORs 1 << tport_find_id(pad), where the
    # ROM ID is one-based.  The setter preserves its active-objective gate.
    if state.secret_trick_id == 0x56:
        mask = state.tport_secret_pad_masks[player_index]
        for pad in (source_slot, destination_pad):
            pad_id = _transporter_id(state, pad)
            if pad_id:
                mask |= 1 << pad_id
        state.tport_secret_pad_masks[player_index] = mask
        secret_trick_set(state, player_index, 0x56, mask)

def _record_inflight_transporter_secret_progress(state: GameState) -> None:
    """Bridge the player-owned transition producer to WP-11's ROM hooks."""
    for player_index, phase in enumerate(state.player_tport_phase):
        if phase < 0:
            state.tport_secret_event_keys[player_index] = -1
            continue

        source = state.player_tport_route_state[player_index] & 0x3FF
        destination = state.player_tport_type[player_index] & 0x3FF
        landing = state.player_tile_pos[player_index] & 0x3FF
        event_key = (source << 20) | (destination << 10) | landing
        if state.tport_secret_event_keys[player_index] == event_key:
            continue
        state.tport_secret_event_keys[player_index] = event_key
        record_transporter_secret_progress(
            state,
            player_index,
            source,
            destination,
            landing,
            powers_gate=bool(state.players[player_index].powers & _POWER_TRANSPORT),
        )


def main_cycle_tport_and_ffield(state: GameState) -> None:
    """0x40528 -- advance the transporter and forcefield palette cycles.

    The transporter counter is a six-position bounce.  The forcefield timer is
    an unsigned *byte* predecremented before its zero test, and its lit colour
    is refreshed every frame from frame-counter bits 2--3.
    """
    if not state.forcefield_segments_ready:
        forcefield_segments_setup(state)
    _record_inflight_transporter_secret_progress(state)

    state.tport_cycle_divider = (state.tport_cycle_divider + 1) & 3
    if state.tport_cycle_divider == 0:
        state.tport_cycle_pos += state.tport_cycle_dir
        if state.tport_cycle_pos == 0:
            state.tport_cycle_dir = 1
        elif state.tport_cycle_pos >= 5:
            state.tport_cycle_dir = -1

    state.forcefield_step_timer = (state.forcefield_step_timer - 1) & 0xFF
    if state.forcefield_step_timer == 0:
        state.forcefield_step = (state.forcefield_step + 1) & 7
        duration = state.forcefield_step_durations[state.forcefield_step]
        state.forcefield_step_timer = (duration + state.getrandom(8)) & 0xFF

    _update_forcefield_color(state)


def playfield_palette_vblank(state: GameState) -> None:
    """0x40392-0x40476 -- perform all live playfield color-RAM writes."""
    if int(state.game_mode) == int(GameMode.TITLE):
        return

    _write_live_color(state, 3, state.forcefield_color)
    if not state.frame_counter & 1:
        stun = state.playfield_color_ram[2 * 16]
        if state.palette_pulse_dir_a < 0:
            stun -= 0x1110
            if stun <= 0x2220:
                stun = 0x2220
                state.palette_pulse_dir_a = 0
        else:
            stun += 0x1110
            if stun >= 0xEEE0:
                stun = 0xEEE0
                state.palette_pulse_dir_a = -1
        _write_live_color(state, 2, stun)

        trap = state.playfield_color_ram[1 * 16]
        if state.palette_pulse_dir_b < 0:
            trap -= 0x1011
            if trap <= 0x4044:
                trap = 0x4044
                state.palette_pulse_dir_b = 0
        else:
            trap += 0x1011
            if trap >= 0xA0AA:
                trap = 0xA0AA
                state.palette_pulse_dir_b = -1
        _write_live_color(state, 1, trap)

    _write_transporter_colors_vblank(state)


# ---------------------------------------------------------------------------
# Door opening
# ---------------------------------------------------------------------------

def _door_picture_matches(picture: int, direction: int) -> tuple[bool, int | None]:
    """Return whether a front consumes ``picture`` and its optional turn."""
    if direction in (0, 2):
        if _DOOR_VERTICAL_MIN <= picture <= _DOOR_VERTICAL_MAX:
            return True, None
        if _DOOR_JUNCTION_MIN <= picture <= _DOOR_JUNCTION_MAX:
            return True, 3 if direction == 0 else 1
    else:
        if _DOOR_HORIZONTAL_MIN <= picture <= _DOOR_HORIZONTAL_MAX:
            return True, None
        if _DOOR_JUNCTION_MIN <= picture <= _DOOR_JUNCTION_MAX:
            return True, 0 if direction == 1 else 2
    return False, None


def _next_door_slot(slot: int, direction: int) -> int | None:
    if direction == 0:
        return slot - 0x20 if slot >= 0x20 else None
    if direction == 1:
        return (slot & 0x3E0) | ((slot + 1) & 0x1F)
    if direction == 2:
        candidate = slot + 0x20
        return candidate if candidate < NUM_MOB_SLOTS else None
    if direction == 3:
        return (slot & 0x3E0) | ((slot - 1) & 0x1F)
    return None


def main_open_doors(state: GameState) -> None:
    """0x45C00 -- advance up to eight door-opening fronts by one cell.

    Idle timing is owned by ``main_move_players`` at 0x4ACDA.  This routine is
    the independent animation consumer of the endpoint records that traversal
    has already installed at 0x904A76/0x904A86.
    """
    for channel, position in enumerate(state.door_endpoint_pos):
        direction = state.door_endpoint_dir[channel]
        if position == 0 or not 0 <= direction <= 3:
            continue

        candidate = _next_door_slot(position, direction)
        if candidate is None:
            state.door_endpoint_pos[channel] = 0
            continue

        state.door_endpoint_pos[channel] = candidate
        matches, turn = _door_picture_matches(state.mobs.picture[candidate], direction)
        if not matches:
            state.door_endpoint_pos[channel] = 0
            continue

        _remove_door_slot(state, candidate)
        if turn is not None:
            state.door_endpoint_dir[channel] = turn


def open_timed_doors(state: GameState) -> None:
    """0x47FAC -- remove every door and queue ``Doors Open`` once if any exist."""
    removed_any = False
    door_types = (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT))
    for slot in range(NUM_MOB_SLOTS):
        if state.mobs.obj_type(slot) not in door_types:
            continue
        _remove_door_slot(state, slot)
        removed_any = True
    if removed_any:
        _sound_play(state, _SOUND_DOORS_OPEN)


# ---------------------------------------------------------------------------
# Cyclic walls and their shared color-spare setup
# ---------------------------------------------------------------------------

def consume_forcefield_code(state: GameState, marker_slot: int) -> int:
    """0x52FBE -- consume a type-7/8/9 marker and return its 1/2/3 code."""
    object_type = state.mobs.obj_type(marker_slot)
    if not int(MazeObjIds.WALL_TRAPCYC1) <= object_type <= int(MazeObjIds.WALL_TRAPCYC3):
        return 0
    if _slot_is_linked(state, marker_slot):
        state.mobs.unlink_and_clear(marker_slot)
    else:
        state.mobs.picture[marker_slot] = 0
        state.mobs.hpos[marker_slot] = 0
        state.mobs.vpos[marker_slot] = 0
        state.mobs.link[marker_slot] = 0
        state.mobs.state_link[marker_slot] = 0
    data = getattr(state.maze, "data", None)
    if data is not None:
        row, col = divmod(marker_slot, 32)
        data[(col, row)] = int(MazeObjIds.TILE_FLOOR)
    return object_type - int(MazeObjIds.WALL_TRAPCYC1) + 1


def maze_forcefield_setup(state: GameState) -> None:
    """0x52F26 -- pack type-7/8/9 cycle codes into color-spare storage."""
    assignments = [0] * 256
    has_cycle_marker = False
    for first in range(FIRST_PLAYABLE_SLOT, NUM_MOB_SLOTS, 4):
        packed = 0
        for offset in range(4):
            code = consume_forcefield_code(state, first + offset)
            packed |= code << (offset * 2)
        assignments[first >> 2] = packed
        has_cycle_marker |= packed != 0

    state.cyclic_wall_assign = assignments
    state.cyclic_wall_setup_ready = True
    state.cyclic_wall_phase = 0
    state.cyclic_wall_timer = 0
    if not has_cycle_marker:
        state.level_flags_3 &= ~0x08


def main_walls_cyclic_move(state: GameState) -> None:
    """0x5E62A -- remove the old cycle phase and place the next one."""
    if not (state.level_flags_3 & 0x08):
        return
    if not state.cyclic_wall_setup_ready:
        if any(state.cyclic_wall_assign):
            state.cyclic_wall_setup_ready = True
        else:
            maze_forcefield_setup(state)
    if not any(player.mob_slot for player in state.players):
        return

    previous_timer = state.cyclic_wall_timer & 0xFFFF
    state.cyclic_wall_timer = (previous_timer - 1) & 0xFFFF
    if previous_timer != 0:
        return

    state.cyclic_wall_timer = 0x78
    old_phase = state.cyclic_wall_phase
    new_phase = old_phase + 1
    if new_phase > 3:
        new_phase = 1
    state.cyclic_wall_phase = new_phase

    if state.mazenum_current < 0x73:
        _sound_play(state, _SOUND_CYCLIC_WALLS)

    removed: list[int] = []
    placed: list[tuple[int, int]] = []
    for tile in range(FIRST_PLAYABLE_SLOT, NUM_MOB_SLOTS):
        if tile & 0x3F == 0:
            state.vblank_flag = 0

        assignment = (
            state.cyclic_wall_assign[tile >> 2] >> ((tile & 3) << 1)
        ) & 3
        if assignment == 0:
            continue

        if assignment == old_phase and state.mobs.picture[tile] == 0x8000:
            state.mobs.picture[tile] = 0
            state.mobs.hpos[tile] = 0
            state.mobs.vpos[tile] = 0
            state.mobs.link[tile] = 0
            state.mobs.state_link[tile] = 0
            data = getattr(state.maze, "data", None)
            if data is not None:
                row, col = divmod(tile, 32)
                data[(col, row)] = int(MazeObjIds.TILE_FLOOR)
            removed.append(tile)
        elif (
            assignment == new_phase
            and tile != state.thief_current_pos
            and state.mobs.picture[tile] == 0
        ):
            x, y = slot_to_pixels(tile)
            state.mobs.picture[tile] = 0x8000
            state.mobs.hpos[tile] = encode_hpos(x)
            state.mobs.vpos[tile] = encode_vpos_at_y(y, 2, 2)
            state.mobs.link[tile] = (6 + new_phase) << 10
            state.mobs.state_link[tile] = 0
            placed.append((tile, 6 + new_phase))

    from ..maze import write_cyclic_wall_descriptor, write_floor_descriptor

    for tile in removed:
        write_floor_descriptor(state, tile)
    for tile, object_type in placed:
        write_cyclic_wall_descriptor(state, tile, object_type)


# ---------------------------------------------------------------------------
# Random walls
# ---------------------------------------------------------------------------

def setup_random_walls(state: GameState) -> None:
    """Initialize the 0x9048A0--A6 cursor state from type-6 maze objects."""
    slots = [
        slot
        for slot in range(FIRST_PLAYABLE_SLOT, NUM_MOB_SLOTS)
        if state.mobs.obj_type(slot) == int(MazeObjIds.WALL_RANDOM)
    ]
    if not slots:
        state.random_wall_timer = -1
        state.random_wall_low_mark = 0
        state.random_wall_target = 0
        state.random_wall_current = 0
        state.random_wall_setup_ready = True
        return

    state.random_wall_low_mark = slots[0]
    state.random_wall_target = slots[-1]
    state.random_wall_current = slots[0] - 1
    state.random_wall_timer = 0
    state.random_wall_setup_ready = True


def _restart_random_wall_cycle(state: GameState) -> None:
    state.random_wall_timer = (
        0x3C if state.game_mode < 0 else 0x78
    )
    state.random_wall_current = state.random_wall_low_mark - 1


def main_walls_random_move(state: GameState) -> None:
    """0x5E41A -- process one random-wall marker per frame.

    The ROM uses the low-water/current/target cursor triplet rather than a
    whole-table sweep: the scan can span many frames while its cycle timer runs.
    """
    if not state.random_wall_setup_ready:
        setup_random_walls(state)
    if state.game_mode not in (GameMode.NORMAL, GameMode.DEMO):
        return
    if state.random_wall_timer < 0:
        return

    if state.random_wall_timer > 0:
        state.random_wall_timer -= 1
        if (
            state.random_wall_timer == 0
            and state.random_wall_current == state.random_wall_target
        ):
            _restart_random_wall_cycle(state)
            return

    if state.random_wall_current == state.random_wall_target:
        return

    start = state.random_wall_current + 1
    target = state.random_wall_target
    candidate = next(
        (
            slot
            for slot in range(start, target + 1)
            if state.mobs.obj_type(slot) == int(MazeObjIds.WALL_RANDOM)
        ),
        None,
    )
    if candidate is None:
        state.random_wall_current = target
        if state.random_wall_timer == 0:
            _restart_random_wall_cycle(state)
        return

    if state.getrandom(32) > 15:
        state.mobs.picture[candidate] ^= 0x8000
        if state.mobs.picture[candidate]:
            from ..maze import set_cell_descriptor

            set_cell_descriptor(
                state, candidate, int(MazeObjIds.WALL_RANDOM),
            )
        else:
            from ..maze import clear_cell_descriptor

            clear_cell_descriptor(state, candidate)

    if candidate == target:
        state.random_wall_current = target
        if state.random_wall_timer == 0:
            _restart_random_wall_cycle(state)
    else:
        state.random_wall_current = candidate


# ---------------------------------------------------------------------------
# Forcefield segment table
# ---------------------------------------------------------------------------

def _forcefield_candidate(
    hub: int, distance: int, horizontal: bool, wraps: bool
) -> tuple[int, bool] | None:
    row, col = hub >> 5, hub & 0x1F
    if horizontal:
        next_col = col + distance
        wrapped = next_col >= 32
        if wrapped:
            if not wraps:
                return None
            next_col &= 0x1F
        return (row << 5) | next_col, wrapped

    next_row = row + distance
    wrapped = next_row >= 32
    if wrapped:
        if not wraps:
            return None
        next_row &= 0x1F
    return (next_row << 5) | col, wrapped


def forcefield_segments_setup(state: GameState) -> None:
    """0x53398 -- build the packed, zero-terminated forcefield segment view."""
    hubs = {
        slot
        for slot in range(FIRST_PLAYABLE_SLOT, NUM_MOB_SLOTS)
        if state.mobs.obj_type(slot) == int(MazeObjIds.FORCEFIELDHUB)
    }
    segments: list[int] = []
    for hub in sorted(hubs):
        for horizontal, wraps in ((True, state.wrap_h), (False, state.wrap_v)):
            for distance in range(1, 16):
                candidate_data = _forcefield_candidate(hub, distance, horizontal, wraps)
                if candidate_data is None:
                    break
                candidate, wrapped = candidate_data
                if candidate in hubs:
                    if distance > 1:
                        segments.append(
                            (0x8000 if horizontal else 0)
                            | (0x4000 if wrapped else 0)
                            | ((distance - 1) << 10)
                            | hub
                        )
                    break
                object_type = state.mobs.obj_type(candidate)
                if (
                    object_type in _FORCEFIELD_BLOCKERS
                    or state.mobs.picture[candidate] in (0x8000, 0x8001)
                ):
                    break
    state.forcefield_segments = segments
    state.forcefield_segments_ready = True
    from ..playfield_vram import write_tile_descriptor

    for segment in segments:
        hub = segment & 0x3FF
        row, col = hub >> 5, hub & 0x1F
        length = ((segment >> 10) & 0x0F) + 1
        horizontal = bool(segment & 0x8000)
        for distance in range(1, length):
            cell = (
                (row << 5) | ((col + distance) & 0x1F)
                if horizontal
                else (((row + distance) & 0x1F) << 5) | col
            )
            state.playfield_forcefield_cells.add(cell)
            descriptor = state.playfield_floor_descriptors[cell]
            write_tile_descriptor(
                state, cell,
                tuple((word & 0x8FFF) | 0x3000 for word in descriptor),
            )


def check_forcefield_collision(state: GameState, packed_maze_pos: int) -> bool:
    """0x53346/0x5FC5E -- test a packed cell against forcefield beam segments."""
    query = packed_maze_pos & 0x3FF
    query_row, query_col = query >> 5, query & 0x1F
    for segment in state.forcefield_segments:
        hub = segment & 0x3FF
        hub_row, hub_col = hub >> 5, hub & 0x1F
        length = ((segment >> 10) & 0x0F) + 1
        horizontal = bool(segment & 0x8000)
        wraps = bool(segment & 0x4000)

        if horizontal:
            if query_row != hub_row:
                continue
            delta = query_col - hub_col
        else:
            if query_col != hub_col:
                continue
            delta = query_row - hub_row

        if wraps and delta <= 0:
            delta += 32
        if 0 < delta < length:
            return True
    return False
