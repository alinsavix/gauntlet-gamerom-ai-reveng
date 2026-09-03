"""Architecture guards for the game-owned playfield descriptor RAM path."""

from __future__ import annotations

import ast
import inspect
import time
from types import SimpleNamespace

from gauntpy.constants import MazeObjIds
from gauntpy.maze import initialize_playfield_ram, set_cell_descriptor
from gauntpy.playfield_vram import (
    EXIT_SETTLED_DESC,
    EXITTO6_SETTLED_DESC,
    TRANSPORTER_DESC,
    descriptor_indices,
    read_tile_descriptor,
    write_playfield_color,
    write_tile_descriptor,
)
from gauntpy.render.playfield import playfield_cache_for_state
from gauntpy.state import GameState


def test_playfield_ram_is_the_exact_column_first_hardware_table():
    state = GameState()
    assert len(state.playfield_ram) == 4096
    assert descriptor_indices((7 << 5) | 3) == (
        6 * 64 + 14,
        7 * 64 + 14,
        6 * 64 + 15,
        7 * 64 + 15,
    )
    write_tile_descriptor(state, (7 << 5) | 3, (1, 2, 3, 4), 0x1000)
    assert read_tile_descriptor(state, (7 << 5) | 3) == (
        0x1001, 0x1002, 0x1003, 0x1004,
    )


def test_lflag1_invisible_trap_walls_preserve_floor_descriptors():
    import gauntpy.maze as maze_module

    state = GameState(level_flags=0x80)
    slot = (5 << 5) | 5
    state.maze = SimpleNamespace(data={(5, 5): int(MazeObjIds.WALL_TRAPCYC1)})
    floor = (1, 2, 3, 4)
    write_tile_descriptor(state, slot, floor)
    state.playfield_wall_catalog[0] = (9, 9, 9, 9)

    set_cell_descriptor(state, slot, int(MazeObjIds.WALL_TRAPCYC1))

    assert not maze_module._wall_is_visible(
        state, int(MazeObjIds.WALL_TRAPCYC1),
    )
    assert maze_module._wall_is_visible(
        state, int(MazeObjIds.WALL_REGULAR),
    )
    assert read_tile_descriptor(state, slot) == floor


def test_lflag2_invisible_all_walls_preserves_floor_descriptors():
    import gauntpy.maze as maze_module

    state = GameState(level_flags_2=0x80)
    slot = (5 << 5) | 5
    state.maze = SimpleNamespace(data={(5, 5): int(MazeObjIds.WALL_REGULAR)})
    floor = (1, 2, 3, 4)
    write_tile_descriptor(state, slot, floor)
    state.playfield_wall_catalog[0] = (9, 9, 9, 9)

    set_cell_descriptor(state, slot, int(MazeObjIds.WALL_REGULAR))

    assert not maze_module._wall_is_visible(
        state, int(MazeObjIds.WALL_REGULAR),
    )
    assert read_tile_descriptor(state, slot) == floor


def test_level_9999_overrides_both_wall_invisibility_flags():
    import gauntpy.maze as maze_module

    state = GameState(
        levelnum_current=maze_module.LEVEL_SENTINEL,
        level_flags=0x80,
        level_flags_2=0x80,
    )

    assert maze_module._wall_is_visible(
        state, int(MazeObjIds.WALL_TRAPCYC1),
    )


def test_runtime_render_api_exposes_only_authoritative_vram_path():
    import gauntpy.render.playfield as playfield

    assert not {
        "build_playfield_image",
        "build_playfield_images",
        "playfield_cache_for",
        "draw_animated_floor_tiles",
        "draw_exit_animation",
        "draw_transporter_tiles",
        "draw_wall_crumble",
    } & set(playfield.__all__)
    runtime_source = inspect.getsource(playfield)
    tree = ast.parse(runtime_source)
    assert "maze.data" not in runtime_source
    assert "GAUNTLET_PALETTES" not in runtime_source
    assert not any(
        isinstance(node, ast.Attribute)
        and node.attr == "data"
        and isinstance(node.value, ast.Name)
        and node.value.id == "maze"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Name)
        and node.id == "GAUNTLET_PALETTES"
        and isinstance(node.ctx, ast.Load)
        for node in ast.walk(tree)
    )
    assert not any(name.startswith("_legacy_") for name in vars(playfield))
    assert "_legacy_" not in runtime_source


def _fake_tile_decode(monkeypatch):
    monkeypatch.setattr(
        "gex.render.get_parsed_tile",
        lambda number: [[number % 15 + 1] * 8 for _ in range(8)],
    )


def _renderable_state() -> GameState:
    state = GameState()
    state.maze = SimpleNamespace(data={(8, 8): int(MazeObjIds.TILE_FLOOR)})
    for index in range(16):
        write_playfield_color(state, index, 0xF000 | index * 0x111)
    return state


def test_renderer_changes_from_vram_with_unchanged_maze_data(monkeypatch):
    _fake_tile_decode(monkeypatch)
    state = _renderable_state()
    logical_before = dict(state.maze.data)
    first = playfield_cache_for_state(state, None)

    slot = (8 << 5) | 8
    old = read_tile_descriptor(state, slot)
    write_tile_descriptor(
        state, slot, tuple((word & 0xF000) | ((word + 1) & 0x0FFF) for word in old),
    )
    second = playfield_cache_for_state(state, first)

    assert state.maze.data == logical_before
    assert second is not first
    assert second.image.tobytes() != first.image.tobytes()


def test_live_renderer_cache_does_not_read_maze_data(monkeypatch):
    _fake_tile_decode(monkeypatch)
    state = _renderable_state()

    class UnreadableData(dict):
        def __getattribute__(self, name):
            if name not in {"__class__", "__getattribute__"}:
                raise AssertionError("renderer read maze.data")
            return super().__getattribute__(name)

    state.maze.data = UnreadableData()
    cache = playfield_cache_for_state(state, None)
    assert cache.vram_generation == state.playfield_generation


def test_color_ram_write_rebuilds_pixels_without_descriptor_change(monkeypatch):
    _fake_tile_decode(monkeypatch)
    state = _renderable_state()
    state.playfield_ram[0] = 15
    descriptor_before = tuple(state.playfield_ram)
    first = playfield_cache_for_state(state, None)

    write_playfield_color(state, 1, 0xFF00)
    second = playfield_cache_for_state(state, first)

    assert tuple(state.playfield_ram) == descriptor_before
    assert second is not first
    assert second.image.getpixel((0, 0)) != first.image.getpixel((0, 0))


def test_cache_replacement_with_matching_generations_reads_the_new_state(monkeypatch):
    _fake_tile_decode(monkeypatch)
    first_state = _renderable_state()
    first = playfield_cache_for_state(first_state, None)
    second_state = _renderable_state()
    second_state.playfield_ram[0] = 14

    second = playfield_cache_for_state(second_state, first)

    assert second is not first
    assert second.state is second_state
    assert second.image.getpixel((0, 0)) != first.image.getpixel((0, 0))


def test_palette_only_update_recolors_without_decode_or_index_rebuild(monkeypatch):
    decode_calls = []
    monkeypatch.setattr(
        "gex.render.get_parsed_tile",
        lambda number: (
            decode_calls.append(number),
            [[number % 15 + 1] * 8 for _ in range(8)],
        )[1],
    )
    state = _renderable_state()
    cache = playfield_cache_for_state(state, None)
    initial_decode_calls = len(decode_calls)
    indexed = cache.indexed_image

    def unexpected_rebuild(*_args, **_kwargs):
        raise AssertionError("palette-only update rebuilt descriptor indices")

    monkeypatch.setattr(
        "gauntpy.render.playfield._build_vram_indices", unexpected_rebuild,
    )
    start = time.perf_counter()
    for step in range(30):
        write_playfield_color(state, 1, 0xF100 + step)
        cache = playfield_cache_for_state(state, cache)
    elapsed = time.perf_counter() - start

    assert cache.indexed_image is indexed
    assert len(decode_calls) == initial_decode_calls
    assert elapsed / 30 < 1 / 60


def test_descriptor_change_restamps_only_changed_tiles(monkeypatch):
    decode_calls = []
    monkeypatch.setattr(
        "gex.render.get_parsed_tile",
        lambda number: (
            decode_calls.append(number),
            [[number % 15 + 1] * 8 for _ in range(8)],
        )[1],
    )
    state = _renderable_state()
    cache = playfield_cache_for_state(state, None)
    initial_decode_calls = len(decode_calls)
    slot = (8 << 5) | 8
    old = read_tile_descriptor(state, slot)
    write_tile_descriptor(
        state, slot, tuple((word + 1) & 0x0FFF for word in old),
    )
    fresh = playfield_cache_for_state(state, None)

    def unexpected_rebuild(*_args, **_kwargs):
        raise AssertionError("local descriptor update rebuilt the full raster")

    monkeypatch.setattr(
        "gauntpy.render.playfield._build_vram_indices", unexpected_rebuild,
    )
    updated = playfield_cache_for_state(state, cache)

    assert updated.indexed_image is not cache.indexed_image
    assert len(decode_calls) > initial_decode_calls
    assert updated.image.tobytes() != cache.image.tobytes()
    assert updated.indexed_image.tobytes() == fresh.indexed_image.tobytes()
    assert updated.image.tobytes() == fresh.image.tobytes()
    assert updated.shadow_image.tobytes() == fresh.shadow_image.tobytes()


def test_descriptor_palette_fields_match_the_hardware_banks():
    state = GameState()
    state.playfield_floor_descriptors[64] = (1, 2, 3, 4)
    state.playfield_forcefield_catalog[0] = (0x4005,) * 4

    set_cell_descriptor(state, 64, int(MazeObjIds.TILE_TRAP1))
    assert read_tile_descriptor(state, 64) == (0x1001, 0x1002, 0x1003, 0x1004)
    set_cell_descriptor(state, 64, int(MazeObjIds.TILE_STUN))
    assert read_tile_descriptor(state, 64) == (0x2001, 0x2002, 0x2003, 0x2004)
    set_cell_descriptor(state, 64, int(MazeObjIds.FORCEFIELDHUB))
    assert read_tile_descriptor(state, 64) == (0x4005,) * 4


def test_descriptor_stays_committed_until_a_real_restamp_then_rerolls():
    committed = (0x1121, 0x1122, 0x1123, 0x1124)
    damaged = (0x57A7, 0x57A8, 0x57A9, 0x57AA)
    state = GameState()
    state.maze = SimpleNamespace(data={
        (3, 3): int(MazeObjIds.TILE_TRAP2),
        (4, 3): int(MazeObjIds.WALL_DESTRUCTABLE),
        (3, 4): int(MazeObjIds.WALL_REGULAR),
    })
    for variation in range(4):
        state.playfield_floor_catalog[(0, variation)] = (
            0x20 + variation,
        ) * 4
    trap_slot = (3 << 5) | 3
    destruct_slot = (3 << 5) | 4
    state.destructible_wall_stage[destruct_slot] = 2
    write_tile_descriptor(state, trap_slot, committed)
    write_tile_descriptor(state, destruct_slot, damaged)

    assert read_tile_descriptor(state, trap_slot) == committed
    assert read_tile_descriptor(state, destruct_slot) == damaged

    set_cell_descriptor(
        state, (4 << 5) | 3, int(MazeObjIds.TILE_FLOOR),
    )

    assert read_tile_descriptor(state, trap_slot) != committed
    assert read_tile_descriptor(state, destruct_slot) == damaged


def test_live_random_wall_draw_uses_state_rng_at_the_write(monkeypatch):
    import gauntpy.maze as maze_module

    class RecordingRng:
        def __init__(self):
            self.bounds = []

        def getrandom(self, bound):
            self.bounds.append(bound)
            return 4

    class Stamp:
        numbers = (0x101, 0x102, 0x103, 0x104)

    state = GameState()
    state.rng = RecordingRng()
    state.maze = SimpleNamespace(
        data={(5, 5): int(MazeObjIds.WALL_RANDOM)},
        wallpattern=7,
        wallcolor=0,
    )
    monkeypatch.setattr(
        maze_module, "wall_get_stamp",
        lambda _pattern, _adjacency, _color, rand: (
            rand.intn(6),
            Stamp(),
        )[1],
    )
    slot = (5 << 5) | 5

    set_cell_descriptor(state, slot, int(MazeObjIds.WALL_RANDOM))

    assert state.rng.bounds.count(6) == 1
    assert read_tile_descriptor(state, slot) == (
        0x7101, 0x7102, 0x7103, 0x7104,
    )


def test_initial_floor_and_random_wall_writes_use_state_rng(monkeypatch):
    import gauntpy.maze as maze_module

    class RecordingRng:
        def __init__(self):
            self.bounds = []

        def getrandom(self, bound):
            self.bounds.append(bound)
            return 3 if bound == 6 else 0

    class Stamp:
        numbers = (0x101, 0x102, 0x103, 0x104)

    wall_slot = (5 << 5) | 5
    maze = SimpleNamespace(
        data={(5, 5): int(MazeObjIds.WALL_RANDOM)},
        floorpattern=0,
        floorcolor=0,
        wallpattern=7,
        wallcolor=0,
    )
    state = GameState()
    state.maze = maze
    state.rng = RecordingRng()
    monkeypatch.setattr(maze_module, "ff_make_map", lambda _maze: set())
    monkeypatch.setattr(
        maze_module, "whatis",
        lambda current, col, row: current.data.get(
            (col, row), int(MazeObjIds.TILE_FLOOR),
        ),
    )
    monkeypatch.setattr(
        maze_module, "floor_get_stamp",
        lambda *_args, **_kwargs: Stamp(),
    )
    monkeypatch.setattr(
        maze_module, "wall_get_stamp",
        lambda _pattern, _adjacency, _color, rand: (
            rand.intn(6),
            Stamp(),
        )[1],
    )
    monkeypatch.setattr(
        maze_module, "wall_get_destructable_stamp",
        lambda *_args, **_kwargs: Stamp(),
    )
    monkeypatch.setattr(
        maze_module, "ff_get_stamp",
        lambda *_args, **_kwargs: Stamp(),
    )

    initialize_playfield_ram(state, maze)

    assert state.rng.bounds == [4] * 1024 + [6]
    assert read_tile_descriptor(state, wall_slot) == (
        0x7101, 0x7102, 0x7103, 0x7104,
    )


def test_initial_descriptor_decision_is_object_aware_and_draws_once(monkeypatch):
    import gauntpy.maze as maze_module

    class RecordingRng:
        def __init__(self):
            self.bounds = []

        def getrandom(self, bound):
            self.bounds.append(bound)
            return 3 if bound == 6 else 0

    class Stamp:
        numbers = (0x101, 0x102, 0x103, 0x104)

    objects = {
        (1, 5): int(MazeObjIds.TILE_STUN),
        (2, 5): int(MazeObjIds.TILE_TRAP1),
        (3, 5): int(MazeObjIds.EXIT),
        (4, 5): int(MazeObjIds.EXITTO6),
        (5, 5): int(MazeObjIds.TRANSPORTER),
        (6, 5): int(MazeObjIds.FORCEFIELDHUB),
        (7, 5): int(MazeObjIds.PLAYERSTART),
        (8, 5): int(MazeObjIds.WALL_RANDOM),
    }
    maze = SimpleNamespace(
        data=objects, floorpattern=0, floorcolor=0, wallpattern=7, wallcolor=0,
    )
    state = GameState()
    state.maze = maze
    state.rng = RecordingRng()
    monkeypatch.setattr(maze_module, "ff_make_map", lambda _maze: set())
    monkeypatch.setattr(
        maze_module, "whatis",
        lambda current, col, row: current.data.get(
            (col, row), int(MazeObjIds.TILE_FLOOR),
        ),
    )
    monkeypatch.setattr(maze_module, "floor_get_stamp", lambda *_args: Stamp())
    monkeypatch.setattr(
        maze_module, "wall_get_stamp",
        lambda _pattern, _adjacency, _color, rand: (
            rand.intn(6), Stamp(),
        )[1],
    )
    monkeypatch.setattr(
        maze_module, "wall_get_destructable_stamp", lambda *_args: Stamp(),
    )
    monkeypatch.setattr(maze_module, "ff_get_stamp", lambda *_args: Stamp())

    initialize_playfield_ram(state, maze)

    assert state.rng.bounds == [4] * (1024 - 4) + [6]
    descriptor = lambda col: read_tile_descriptor(state, (5 << 5) | col)
    assert descriptor(1) == (0x2101, 0x2102, 0x2103, 0x2104)
    assert descriptor(2) == (0x1101, 0x1102, 0x1103, 0x1104)
    assert descriptor(3) == EXIT_SETTLED_DESC
    assert descriptor(4) == EXITTO6_SETTLED_DESC
    assert descriptor(5) == TRANSPORTER_DESC
    assert descriptor(6) == (0x4101, 0x4102, 0x4103, 0x4104)
    assert descriptor(7) == (0x0101, 0x0102, 0x0103, 0x0104)
    assert descriptor(8) == (0x7101, 0x7102, 0x7103, 0x7104)


def test_live_wall_refresh_updates_the_wrapped_adjacency_ring():
    state = GameState()
    wall = (5 << 5) | 31
    wrapped_floor = (5 << 5) | 0
    state.maze = SimpleNamespace(data={
        (31, 5): int(MazeObjIds.WALL_REGULAR),
        (0, 5): int(MazeObjIds.TILE_FLOOR),
    })
    for variation in range(4):
        state.playfield_floor_catalog[(4, variation)] = (1, 1, 1, 1)
        state.playfield_floor_catalog[(0, variation)] = (2, 2, 2, 2)
    write_tile_descriptor(state, wrapped_floor, (1, 1, 1, 1))

    set_cell_descriptor(state, wall, int(MazeObjIds.TILE_FLOOR))

    assert read_tile_descriptor(state, wrapped_floor) == (2, 2, 2, 2)


def test_reserved_boundary_row_connects_as_one_continuous_wall():
    import gauntpy.maze as maze_module

    state = GameState()
    state.maze = SimpleNamespace(data={})
    for slot in range(32):
        state.mobs.picture[slot] = 0x8000
        state.mobs.set_obj_type(slot, int(MazeObjIds.WALL_REGULAR))

    assert maze_module._wall_adjacency(state, 0) & (0x08 | 0x10) == 0x18
    assert maze_module._wall_adjacency(state, 15) & (0x08 | 0x10) == 0x18
    assert maze_module._wall_adjacency(state, 31) & (0x08 | 0x10) == 0x18


def test_all_floor_live_refresh_draws_center_then_exact_three_neighbors():
    class SequencedRng:
        def __init__(self):
            self.bounds = []

        def getrandom(self, bound):
            self.bounds.append(bound)
            return (len(self.bounds) - 1) & 3

    state = GameState()
    state.rng = SequencedRng()
    state.maze = SimpleNamespace(data={})
    for variation in range(4):
        state.playfield_floor_catalog[(0, variation)] = (
            variation + 1,
        ) * 4

    center = (5 << 5) | 5
    untouched_north_west = (4 << 5) | 4
    write_tile_descriptor(state, untouched_north_west, (99,) * 4)

    set_cell_descriptor(state, center, int(MazeObjIds.TILE_FLOOR))

    assert state.rng.bounds == [4, 4, 4, 4]
    assert [
        read_tile_descriptor(state, slot)[0]
        for slot in (
            center,
            (4 << 5) | 5,  # north
            (4 << 5) | 6,  # north-east
            (5 << 5) | 6,  # east
        )
    ] == [1, 2, 3, 4]
    assert read_tile_descriptor(state, untouched_north_west) == (99,) * 4


def test_live_refresh_visits_walls_and_door_routines_in_rom_order(monkeypatch):
    import gauntpy.maze as maze_module
    import gauntpy.subsystems.maze_objects as maze_objects

    center = (5 << 5) | 5
    neighbors = (
        (4 << 5) | 4, (4 << 5) | 5, (4 << 5) | 6,
        (5 << 5) | 4, (5 << 5) | 6,
        (6 << 5) | 4, (6 << 5) | 5, (6 << 5) | 6,
    )
    state = GameState()
    state.maze = SimpleNamespace(data={
        (slot & 0x1F, slot >> 5): int(MazeObjIds.WALL_REGULAR)
        for slot in neighbors
    })
    for adjacency in (0, 4, 8, 12, 16, 20, 24, 28):
        for variation in range(4):
            state.playfield_floor_catalog[(adjacency, variation)] = (
                adjacency + variation,
            ) * 4
    for adjacency in range(256):
        state.playfield_wall_catalog[adjacency] = (adjacency,) * 4
    writes = []
    door_refreshes = []
    monkeypatch.setattr(
        maze_module, "write_tile_descriptor",
        lambda _state, slot, _descriptor, *args: writes.append(slot),
    )
    monkeypatch.setattr(
        maze_objects, "pf_door_update_surrounding_xy",
        lambda _state, slot: door_refreshes.append(slot),
    )

    set_cell_descriptor(state, center, int(MazeObjIds.TILE_FLOOR))

    assert writes == [center, *neighbors]
    assert door_refreshes == [
        center,
        (4 << 5) | 5,  # north
        (5 << 5) | 4,  # west, because it is a wall
        (5 << 5) | 6,  # east
        (6 << 5) | 5,  # south, because it is a wall
    ]


def test_initial_floor_rng_mapping_is_column_outer_row_inner(monkeypatch):
    import gauntpy.maze as maze_module

    class SequencedRng:
        def __init__(self):
            self.calls = 0

        def getrandom(self, bound):
            assert bound == 4
            value = self.calls & 3
            self.calls += 1
            return value

    class Stamp:
        def __init__(self, value=0):
            self.numbers = (value,) * 4

    maze = SimpleNamespace(
        data={}, floorpattern=0, floorcolor=0, wallpattern=0, wallcolor=0,
    )
    state = GameState()
    state.maze = maze
    state.rng = SequencedRng()
    monkeypatch.setattr(maze_module, "ff_make_map", lambda _maze: set())
    monkeypatch.setattr(maze_module, "whatis", lambda *_args: int(MazeObjIds.TILE_FLOOR))
    monkeypatch.setattr(
        maze_module, "floor_get_stamp",
        lambda _pattern, variant, _color: Stamp(variant),
    )
    monkeypatch.setattr(maze_module, "wall_get_stamp", lambda *_args: Stamp())
    monkeypatch.setattr(
        maze_module, "wall_get_destructable_stamp", lambda *_args: Stamp(),
    )
    monkeypatch.setattr(maze_module, "ff_get_stamp", lambda *_args: Stamp())

    initialize_playfield_ram(state, maze)

    assert state.rng.calls == 1024
    for col, row in ((0, 0), (0, 1), (0, 2), (1, 0), (7, 3), (31, 30)):
        descriptor = read_tile_descriptor(state, (row << 5) | col)
        assert descriptor == (row & 3,) * 4
