"""Door geometry and opening contracts checked against M68000 ROM execution."""

import pytest

from gauntpy.game.constants import MazeObjIds
from gauntpy.game.coords import pack_slot
from gauntpy.game.state import GameState
from gauntpy.game.subsystems.maze_objects import (
    main_open_doors,
    maze_doors_setup,
    pf_door_draw_xy,
    pf_isdoor,
)
from gauntpy.game.subsystems.player_items import door_open_start


def _door(state, row, col, *, vertical=False, picture=None):
    slot = pack_slot(row, col)
    state.mobs.create(
        slot, tile=picture or (0x9D7C if vertical else 0x9D3C),
        hpos=0, vpos=0,
        obj_type=MazeObjIds.DOOR_VERT if vertical else MazeObjIds.DOOR_HORIZ,
    )
    return slot


@pytest.mark.parametrize("vertical", [False, True])
@pytest.mark.parametrize("negative", range(3))
@pytest.mark.parametrize("positive", range(3))
def test_isolated_orientation_uses_walls_along_the_door_axis(
    vertical, negative, positive,
):
    state = GameState()
    slot = _door(state, 8, 8, vertical=vertical)
    for sign, digit in ((-1, negative), (1, positive)):
        if digit == 2:
            continue
        for distance in range(1, 3 if digit == 1 else 2):
            row = 8 + (sign * distance if vertical else 0)
            col = 8 + (0 if vertical else sign * distance)
            neighbor = pack_slot(row, col)
            state.mobs.picture[neighbor] = 0x8000
            state.mobs.set_obj_type(neighbor, MazeObjIds.WALL_REGULAR)

    pf_door_draw_xy(state, slot)

    # ROM 0x5F9EE / 0x5FB00, all nine selectors executed independently.
    index = negative * 3 + positive
    if vertical:
        pictures = (0x9D98, 0x9D9E, 0x9D7C, 0x9DA4, 0x9DAC,
                    0x9D8C, 0x9D82, 0x9D86, 0x9D94)
        vsub = (0, 0x100, 0, 0, 0x100, 0, 0, 0x100, 0)
        vadd = (10, 10, 10, 11, 11, 11, 9, 10, 9)
        expected_h = 0x4000
        expected_v = 0xB800 - vsub[index] + vadd[index]
    else:
        pictures = (0x9D5A, 0x9D60, 0x9D3C, 0x9D68, 0x9D6E,
                    0x9D42, 0x9D4C, 0x9D52, 0x9D48)
        hsub = (0x200, 0x200, 0x200, 0x280, 0x280,
                0x280, 0x200, 0x200, 0)
        vadd = (17, 25, 17, 17, 25, 17, 17, 25, 9)
        expected_h = 0x4000 - hsub[index]
        expected_v = 0xB800 + vadd[index]
    assert state.mobs.picture[slot] == pictures[index]
    assert state.mobs.hpos[slot] == expected_h
    assert state.mobs.vpos[slot] == expected_v
    assert state.mobs.state(slot) == (5 if vertical else 10)


@pytest.mark.parametrize("direction,delta,turn", [
    (0, -32, 3), (1, 1, 0), (2, 32, 1), (3, -1, 2),
])
def test_junction_front_turn_is_always_left_not_connectivity_search(
    direction, delta, turn,
):
    state = GameState()
    origin = pack_slot(8, 8)
    junction = origin + delta
    _door(state, junction >> 5, junction & 31, picture=0x9D28)
    state.door_endpoint_pos[0] = origin
    state.door_endpoint_dir[0] = direction
    main_open_doors(state)
    assert state.door_endpoint_pos[0] == junction
    assert state.door_endpoint_dir[0] == turn
    assert state.mobs.picture[junction] == 0
    main_open_doors(state)
    assert state.door_endpoint_pos[0] == 0


def test_upward_front_does_not_consume_reserved_row_zero():
    state = GameState()
    _door(state, 0, 8, vertical=True)
    state.door_endpoint_pos[0] = pack_slot(1, 8)
    state.door_endpoint_dir[0] = 0
    main_open_doors(state)
    assert state.mobs.picture[8] == 0x9D7C
    assert state.door_endpoint_pos[0] == 0


def test_redrawing_straightened_junction_uses_axis_picture():
    state = GameState()
    center = _door(state, 8, 8, picture=0x9D38)
    _door(state, 8, 7)
    _door(state, 8, 9)
    maze_doors_setup(state)
    assert state.mobs.picture[center] == 0x9D48
    assert state.mobs.state(center) == 10


@pytest.mark.parametrize("door_class", [1, 2, 3])
@pytest.mark.parametrize("mask", range(16))
def test_all_door_neighbor_masks_match_rom(door_class, mask):
    state = GameState()
    slot = _door(state, 8, 8, picture={1: 0x9D28, 2: 0x9D3C, 3: 0x9D7C}[door_class])
    for bit, (row, col) in enumerate(((7, 8), (8, 9), (9, 8), (8, 7))):
        if mask & (1 << bit):
            _door(state, row, col)
    pf_door_draw_xy(state, slot)
    # Results of pf_door_draw 0x5F880 for each input class and neighbor mask.
    expected = {
        1: (0x9D28, 0x9D94, 0x9D48, 0x9D34, 0x9D94, 0x9D94, 0x9D2C, 0x9D1C,
            0x9D48, 0x9D38, 0x9D48, 0x9D24, 0x9D30, 0x9D18, 0x9D20, 0x9D28),
        2: (0x9D48, 0x9D24, 0x9D48, 0x9D34, 0x9D20, 0x9D28, 0x9D2C, 0x9D1C,
            0x9D48, 0x9D38, 0x9D48, 0x9D24, 0x9D30, 0x9D18, 0x9D20, 0x9D28),
        3: (0x9D94, 0x9D94, 0x9D1C, 0x9D34, 0x9D94, 0x9D94, 0x9D2C, 0x9D1C,
            0x9D18, 0x9D38, 0x9D28, 0x9D24, 0x9D30, 0x9D18, 0x9D20, 0x9D28),
    }[door_class][mask]
    assert state.mobs.picture[slot] == expected
    assert state.mobs.hpos[slot] == 0x4000
    assert state.mobs.vpos[slot] == 0xB809
    assert state.mobs.state(slot) == {0x9D48: 10, 0x9D94: 5}.get(expected, mask)


@pytest.mark.parametrize("picture,door_class", [
    (0x9D17, 0), (0x9D18, 1), (0x9D3B, 1), (0x9D3C, 2),
    (0x9D6F, 2), (0x9D7B, 2), (0x9D7C, 3), (0x9DAC, 3),
    (0x9DAD, 0), (0x8000, 0), (0, 0),
])
def test_door_classification_uses_live_picture_not_object_type(picture, door_class):
    state = GameState()
    slot = pack_slot(8, 8)
    state.mobs.picture[slot] = picture
    state.mobs.set_obj_type(slot, MazeObjIds.TILE_FLOOR)
    assert pf_isdoor(state, slot) == door_class
    state.mobs.set_obj_type(slot, MazeObjIds.DOOR_HORIZ)
    assert pf_isdoor(state, slot) == door_class
    state.mobs.picture[8] = picture
    assert pf_isdoor(state, 8) == 0


def test_junction_scan_preserves_an_unwritten_front_channel():
    state = GameState()
    slot = _door(state, 8, 8, picture=0x9D38)
    _door(state, 8, 7)
    previous = _door(state, 12, 12)
    next_slot = _door(state, 12, 13)
    state.door_endpoint_pos[1] = previous
    state.door_endpoint_dir[1] = 1
    door_open_start(state, slot, 0)
    assert state.door_endpoint_pos[:2] == [slot - 1, next_slot]
    assert state.door_endpoint_dir[:2] == [3, 1]
    assert state.mobs.picture[next_slot] == 0


def test_junction_scanner_uses_picture_and_wraps_the_vertical_axis():
    state = GameState()
    slot = _door(state, 31, 8, picture=0x9D38)
    # A stale door type with no door picture is not a branch.
    _door(state, 31, 7)
    state.mobs.picture[slot - 1] = 0x8000
    # The wrapped row zero is rejected by pf_isdoor even with a door picture.
    _door(state, 0, 8, vertical=True)
    door_open_start(state, slot, 0)
    assert state.door_endpoint_dir[:2] == [0, 0]
    assert state.door_endpoint_pos[:2] == [0, 0]


@pytest.mark.parametrize("seed,mirror,remaining", [
    (0, 0x0C, 100), (1, 0x00, 115), (2, 0x04, 136), (4, 0x08, 155),
])
def test_maze39_downward_contact_matches_rom_partial_spiral(seed, mirror, remaining):
    from gex.roms import SLAPSTIC_ROMS, _rom_dir
    if not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file():
        pytest.skip("Local maze ROMs unavailable")
    from gauntpy.host.startup import build_state
    from gauntpy.game.mainloop import tick
    from gauntpy.game.subsystems.input import JOY_DOWN

    state = build_state(40, 3, maze_number=39, keys=1, rng_seed=seed)
    state.game_settings |= 0x0400
    doors = {slot for slot in range(32, 1024)
             if state.mobs.obj_type(slot) in (13, 14)}
    assert len(doors) == 167
    assert state.level_flags & 0x0C == mirror
    floor = state.playfield_ram.copy()
    state.player_input_raw[0] = 0xFFFF ^ JOY_DOWN
    for _ in range(60):
        tick(state)
        if state.players[0].keysnum == 0:
            break
    assert state.players[0].keysnum == 0
    state.player_input_raw[0] = 0xFFFF
    for _ in range(90):
        tick(state)
    assert not any(state.door_endpoint_pos)
    assert sum(state.mobs.obj_type(slot) in (13, 14) for slot in doors) == remaining
    for slot in doors:
        if state.mobs.picture[slot] == 0:
            assert state.maze.data[(slot & 31, slot >> 5)] == MazeObjIds.TILE_FLOOR
    assert state.playfield_ram == floor
