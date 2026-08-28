"""ROM-regression tests for the living-maze WP-11 routines."""

from __future__ import annotations

from types import SimpleNamespace

from gauntpy.constants import GameMode, MazeObjIds
from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot
from gauntpy.state import GameState
from gauntpy.subsystems.maze_objects import (
    pf_isblankfloor,
    check_forcefield_collision,
    forcefield_segments_setup,
    main_cycle_tport_and_ffield,
    main_open_doors,
    main_walls_cyclic_move,
    main_walls_random_move,
    maze_forcefield_setup,
    open_timed_doors,
    record_transporter_secret_progress,
    select_forcefield_delay_profile,
    maze_doors_setup,
    setup_random_walls,
)


class _FixedRNG:
    def __init__(self, *values: int) -> None:
        self.values = list(values)

    def getrandom(self, bound: int) -> int:  # noqa: ARG002
        return self.values.pop(0) if self.values else 0


def _place(state: GameState, slot: int, object_type: int, picture: int = 0x8000) -> None:
    state.mobs.create(
        slot,
        tile=picture,
        hpos=encode_hpos((slot & 0x1F) * 16),
        vpos=encode_vpos_at_y((slot >> 5) * 16),
        obj_type=object_type,
    )


class TestTransporterAndForcefieldCycle:
    def test_transporter_bounces_through_all_six_palette_positions(self):
        state = GameState()
        state.ff_cycle_timer = 0xFF
        positions = []
        for _ in range(10):
            for _ in range(4):
                main_cycle_tport_and_ffield(state)
            positions.append(state.tport_cycle_pos)
        assert positions == [1, 2, 3, 4, 5, 4, 3, 2, 1, 0]

    def test_transporter_and_forcefield_cycles_write_their_color_banks(self):
        state = GameState(frame_counter=8, game_mode=GameMode.NORMAL)
        state.ff_cycle_timer = 5
        state.tport_cycle_divider = 3
        before = list(state.playfield_color_ram)

        main_cycle_tport_and_ffield(state)

        assert state.playfield_color_ram == before
        assert state.forcefield_color == 0x9FFF
        assert state.tport_cycle_pos == 1
        from gauntpy.subsystems.maze_objects import playfield_palette_vblank
        playfield_palette_vblank(state)
        assert state.playfield_color_ram[3 * 16] == 0x9FFF
        assert state.playfield_color_ram[4 * 16 + 8:4 * 16 + 14] == [
            0x8F00, 0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD,
        ]

    def test_vblank_palette_colors_bounce_at_the_rom_bounds(self):
        from gauntpy.subsystems.maze_objects import playfield_palette_vblank

        state = GameState(frame_counter=2, game_mode=GameMode.NORMAL)
        state.maze = SimpleNamespace(floorpattern=5)
        state.playfield_color_ram[2 * 16] = 0xDDD0
        state.playfield_color_ram[1 * 16] = 0xA0AA

        playfield_palette_vblank(state)

        assert state.palette_pulse_dir_a == -1
        assert state.palette_pulse_dir_b == -1
        for index in (0, 1, 2):
            assert state.playfield_color_ram[1 * 16 + index] == 0xA0AA
            assert state.playfield_color_ram[2 * 16 + index] == 0xEEE0

    def test_title_vblank_skips_all_playfield_palette_writes(self):
        from gauntpy.subsystems.maze_objects import playfield_palette_vblank

        state = GameState(game_mode=GameMode.TITLE, frame_counter=2)
        state.forcefield_color = 0xFFFF
        state.tport_cycle_pos = 4
        state.playfield_color_ram[:] = list(range(128))
        before = list(state.playfield_color_ram)

        playfield_palette_vblank(state)

        assert state.playfield_color_ram == before

    def test_odd_vblank_still_writes_forcefield_and_transporter_only(self):
        from gauntpy.subsystems.maze_objects import playfield_palette_vblank

        state = GameState(game_mode=GameMode.NORMAL, frame_counter=3)
        state.maze = SimpleNamespace(floorpattern=0)
        state.forcefield_color = 0xF00F
        state.playfield_color_ram[16] = 0x5555
        state.playfield_color_ram[32] = 0x6666

        playfield_palette_vblank(state)

        for index in (0, 10, 12):
            assert state.playfield_color_ram[48 + index] == 0xF00F
        assert state.playfield_color_ram[16] == 0x5555
        assert state.playfield_color_ram[32] == 0x6666
        assert state.playfield_color_ram[72:78] == list(
            (0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD, 0xFFFF)
        )

    def test_forcefield_timer_is_an_unsigned_byte_predecrement(self):
        state = GameState()
        state.ff_cycle_index = 0
        state.ff_cycle_timer = 0

        main_cycle_tport_and_ffield(state)

        assert state.ff_cycle_timer == 0xFF
        assert state.ff_cycle_index == 0
        assert state.forcefield_color == 0xFF00

    def test_expiring_timer_advances_then_reloads_from_exact_profile(self):
        state = GameState()
        state.ff_cycle_index = 0
        state.ff_cycle_timer = 1
        state.rng = _FixedRNG(3)

        main_cycle_tport_and_ffield(state)

        assert state.ff_cycle_index == 1
        assert state.ff_cycle_timer == 0x23  # profile[1] 0x20 + random(8)
        assert state.forcefield_color == 0

    def test_lit_color_tracks_frame_phase_even_while_timer_is_running(self):
        state = GameState()
        state.ff_cycle_index = 0
        state.ff_cycle_timer = 5
        state.frame_counter = 8

        main_cycle_tport_and_ffield(state)

        assert state.ff_cycle_timer == 4
        assert state.forcefield_color == 0x9FFF

    def test_level_selected_delay_profiles_are_hex_rom_bytes(self):
        state = GameState(levelnum_current=3)
        state.cycle_phase_assignments[10] = 0x55
        state.wallcycle_type = 2
        state.wallcycle_time = 99
        select_forcefield_delay_profile(state)
        assert state.forcefield_step_durations == [0x10, 0x10, 0x20, 0x20, 0x40, 0x40, 0x08, 0x40]
        assert not any(state.cycle_phase_assignments)
        assert state.wallcycle_type == 0
        assert state.wallcycle_time == 0


class TestTransporterSecretProgress:
    def _transport_state(self) -> tuple[GameState, int, int, int]:
        state = GameState()
        source = pack_slot(3, 3)
        destination = pack_slot(3, 8)
        landing = pack_slot(5, 8)
        _place(state, source, MazeObjIds.TRANSPORTER, picture=1)
        _place(state, destination, MazeObjIds.TRANSPORTER, picture=1)
        state.player_tport_phase[0] = 0
        state.player_tport_route_state[0] = source
        state.player_tport_type[0] = destination
        state.player_tile_or_tport_dest[0] = landing
        return state, source, destination, landing

    def test_task_0x56_records_one_based_source_and_destination_pad_bits(self):
        state, source, destination, landing = self._transport_state()
        state.trick_tasknum = 0x56

        record_transporter_secret_progress(
            state, 0, source, destination, landing
        )

        assert state.secret_tricks_flags[0] == 0x06  # IDs 1 and 2, never bit 0

    def test_cycle_bridge_records_an_armed_transporter_once(self):
        state, _, _, _ = self._transport_state()
        state.trick_tasknum = 0x56
        # main_score_update advances the freshly armed phase 0 to 1 before the
        # next world-frame transporter cycle observes it.
        state.player_tport_phase[0] = 1

        main_cycle_tport_and_ffield(state)
        main_cycle_tport_and_ffield(state)

        assert state.secret_tricks_flags[0] == 0x06

    def test_transport_power_skips_the_secret_transporter_hooks(self):
        state, source, destination, landing = self._transport_state()
        state.trick_tasknum = 0x56
        state.players[0].powers = 0x0800

        record_transporter_secret_progress(
            state, 0, source, destination, landing, powers_gate=True
        )

        assert state.secret_tricks_flags[0] == 0

    def test_ordinary_transport_tricks_are_not_progress_counters(self):
        state, source, destination, landing = self._transport_state()
        state.trick_tasknum = 3
        state.mobs.set_obj_type(landing, MazeObjIds.EXIT)

        record_transporter_secret_progress(
            state, 0, source, destination, landing
        )

        assert state.secret_tricks_flags[0] == 0
        assert state.trick_player == -1


class TestForcefieldSetup:
    def test_marker_setup_packs_four_2bit_codes_and_clears_markers(self):
        state = GameState()
        slots = (32, 33, 34)
        for slot, object_type in zip(
            slots,
            (MazeObjIds.WALL_TRAPCYC1, MazeObjIds.WALL_TRAPCYC2, MazeObjIds.WALL_TRAPCYC3),
            strict=True,
        ):
            _place(state, slot, object_type)
        state.level_flags_3 = 0x08

        maze_forcefield_setup(state)

        assert state.cycle_phase_assignments[8] == 0b00_11_10_01
        assert all(state.mobs.obj_type(slot) == 0 for slot in slots)
        assert state.wallcycle_type == 0
        assert state.wallcycle_time == 0

    def test_marker_setup_disables_cyclic_flag_when_no_markers_exist(self):
        state = GameState()
        state.level_flags_3 = 0x08

        maze_forcefield_setup(state)

        assert not state.level_flags_3 & 0x08

    def test_segment_table_and_collision_cover_only_cells_between_hubs(self):
        state = GameState()
        left = pack_slot(5, 5)
        right = pack_slot(5, 9)
        _place(state, left, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)
        _place(state, right, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)

        forcefield_segments_setup(state)

        assert state.ff_segment_table == [0x8000 | (3 << 10) | left]
        assert check_forcefield_collision(state, pack_slot(5, 6))
        assert check_forcefield_collision(state, pack_slot(5, 8))
        assert not check_forcefield_collision(state, left)
        assert not check_forcefield_collision(state, right)
        assert not check_forcefield_collision(state, pack_slot(6, 6))

    def test_real_marker_hubs_build_the_same_repeating_beam(self):
        from gauntpy.maze import maze_place_object

        state = GameState()
        left = pack_slot(5, 5)
        right = pack_slot(5, 9)
        maze_place_object(state, left, MazeObjIds.FORCEFIELDHUB, 1)
        maze_place_object(state, right, MazeObjIds.FORCEFIELDHUB, 1)

        forcefield_segments_setup(state)

        assert state.mobs.picture[left] == 0x8000
        assert state.ff_segment_table == [0x8000 | (3 << 10) | left]
        assert check_forcefield_collision(state, pack_slot(5, 7))

    def test_wrapped_segment_crosses_the_maze_seam(self):
        state = GameState(wrap_h=True)
        first = pack_slot(8, 30)
        second = pack_slot(8, 2)
        _place(state, first, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)
        _place(state, second, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)

        forcefield_segments_setup(state)

        assert state.ff_segment_table == [0xC000 | (3 << 10) | first]
        assert check_forcefield_collision(state, pack_slot(8, 0))
        assert not check_forcefield_collision(state, pack_slot(8, 2))

    def test_vertical_segment_uses_row_distance_and_same_column(self):
        state = GameState()
        top = pack_slot(4, 12)
        bottom = pack_slot(8, 12)
        _place(state, top, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)
        _place(state, bottom, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)

        forcefield_segments_setup(state)

        assert state.ff_segment_table == [(3 << 10) | top]
        assert check_forcefield_collision(state, pack_slot(6, 12))
        assert not check_forcefield_collision(state, pack_slot(6, 11))

    def test_wall_blocks_segment_construction(self):
        state = GameState()
        left = pack_slot(5, 5)
        right = pack_slot(5, 9)
        _place(state, left, MazeObjIds.FORCEFIELDHUB)
        _place(state, pack_slot(5, 7), MazeObjIds.WALL_REGULAR)
        _place(state, right, MazeObjIds.FORCEFIELDHUB)

        forcefield_segments_setup(state)

        assert state.ff_segment_table == []

    def test_first_palette_cycle_lazily_builds_level_forcefield_state(self):
        state = GameState()
        left = pack_slot(5, 5)
        right = pack_slot(5, 8)
        _place(state, left, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)
        _place(state, right, MazeObjIds.FORCEFIELDHUB, picture=0x0C3F)

        main_cycle_tport_and_ffield(state)

        assert state.forcefield_segments_ready
        assert check_forcefield_collision(state, pack_slot(5, 6))


class TestDoorOpening:
    def test_blank_floor_predicate_keeps_the_rom_row_zero_shortcut(self):
        state = GameState()
        slot = pack_slot(0, 5)
        _place(state, slot, MazeObjIds.WALL_REGULAR, picture=0x8000)
        state.maze = SimpleNamespace(data={(5, 0): int(MazeObjIds.WALL_REGULAR)})

        assert pf_isblankfloor(state, slot)

    def test_connected_horizontal_door_uses_rom_neighbor_picture(self):
        state = GameState()
        center = pack_slot(5, 5)
        left = pack_slot(5, 4)
        above = pack_slot(4, 5)
        for slot in (center, left, above):
            _place(state, slot, MazeObjIds.DOOR_HORIZ, picture=0x9D3C)
        state.maze = SimpleNamespace(data={
            (5, 5): int(MazeObjIds.DOOR_HORIZ),
            (4, 5): int(MazeObjIds.DOOR_HORIZ),
            (5, 4): int(MazeObjIds.DOOR_HORIZ),
        })

        maze_doors_setup(state)

        assert state.mobs.picture[center] == 0x9D38
        assert state.mobs.hpos[center] == 5 << 11
        assert state.mobs.vpos[center] == (((5 << 11) ^ 0xF800) + 9) & 0xFFFF
        assert state.mobs.state(center) == 9

    def test_isolated_horizontal_door_uses_orientation_tables(self):
        state = GameState()
        slot = pack_slot(5, 5)
        _place(state, slot, MazeObjIds.DOOR_HORIZ, picture=0x9D3C)
        state.maze = SimpleNamespace(data={(5, 5): int(MazeObjIds.DOOR_HORIZ)})

        maze_doors_setup(state)

        assert state.mobs.picture[slot] == 0x9D4C
        assert state.mobs.hpos[slot] == ((5 << 11) - 0x0200) & 0xFFFF
        assert state.mobs.vpos[slot] == (((5 << 11) ^ 0xF800) + 0x11) & 0xFFFF
        assert state.mobs.state(slot) == 10

    def test_open_front_removes_cells_and_turns_at_a_junction(self):
        state = GameState()
        junction = pack_slot(5, 6)
        horizontal = pack_slot(5, 5)
        _place(state, junction, MazeObjIds.DOOR_VERT, picture=0x9D20)
        _place(state, horizontal, MazeObjIds.DOOR_HORIZ, picture=0x9D3C)
        state.door_endpoint_pos[0] = pack_slot(6, 6)
        state.door_endpoint_dir[0] = 0

        main_open_doors(state)
        assert state.mobs.obj_type(junction) == 0
        assert state.door_endpoint_pos[0] == junction
        assert state.door_endpoint_dir[0] == 3

        main_open_doors(state)
        assert state.mobs.obj_type(horizontal) == 0
        assert state.door_endpoint_pos[0] == horizontal
        assert state.door_endpoint_dir[0] == 3

    def test_front_stops_when_the_next_cell_is_not_a_door(self):
        state = GameState()
        state.door_endpoint_pos[0] = pack_slot(6, 6)
        state.door_endpoint_dir[0] = 0

        main_open_doors(state)

        assert state.door_endpoint_pos[0] == 0

    def test_door_animation_does_not_own_the_player_idle_timer(self):
        state = GameState()
        state.idle_timer = 42
        main_open_doors(state)
        assert state.idle_timer == 42

    def test_timed_opening_unlinks_all_doors_and_plays_one_sound(self):
        state = GameState()
        slots = (pack_slot(4, 4), pack_slot(6, 6))
        _place(state, slots[0], MazeObjIds.DOOR_HORIZ, picture=0x9D3C)
        _place(state, slots[1], MazeObjIds.DOOR_VERT, picture=0x9D7C)

        open_timed_doors(state)

        assert all(state.mobs.obj_type(slot) == 0 for slot in slots)
        assert state.sound_log == [0x12]

    def test_timed_opening_is_silent_without_doors(self):
        state = GameState()
        open_timed_doors(state)
        assert state.sound_log == []


class TestCyclicWalls:
    def _armed_state(self) -> GameState:
        state = GameState()
        state.level_flags_3 = 0x08
        state.players[0].mob_slot = 1
        state.cyclic_wall_setup_ready = True
        return state

    def test_noncyclic_trap_walls_are_not_consumed_during_setup(self):
        state = GameState()
        slot = pack_slot(5, 5)
        _place(state, slot, MazeObjIds.WALL_TRAPCYC1)
        state.maze = SimpleNamespace(data={
            (5, 5): int(MazeObjIds.WALL_TRAPCYC1),
        })

        main_walls_cyclic_move(state)

        assert state.mobs.picture[slot] == 0x8000
        assert state.mobs.obj_type(slot) == int(MazeObjIds.WALL_TRAPCYC1)
        assert state.maze.data[(5, 5)] == int(MazeObjIds.WALL_TRAPCYC1)

    def test_predecrement_delays_transition_until_the_following_frame(self):
        state = self._armed_state()
        state.wallcycle_time = 1

        main_walls_cyclic_move(state)
        assert state.wallcycle_time == 0
        assert state.wallcycle_type == 0

        main_walls_cyclic_move(state)
        assert state.wallcycle_time == 0x78
        assert state.wallcycle_type == 1

    def test_transition_removes_old_phase_and_places_new_phase(self):
        state = self._armed_state()
        old_slot = pack_slot(5, 5)
        new_slot = pack_slot(5, 6)
        state.wallcycle_type = 1
        state.wallcycle_time = 0
        state.cycle_phase_assignments[old_slot >> 2] |= 1 << ((old_slot & 3) * 2)
        state.cycle_phase_assignments[new_slot >> 2] |= 2 << ((new_slot & 3) * 2)
        _place(state, old_slot, MazeObjIds.WALL_TRAPCYC1)
        state.maze = SimpleNamespace(data={
            (5, 5): int(MazeObjIds.WALL_TRAPCYC1),
            (6, 5): int(MazeObjIds.TILE_FLOOR),
        })

        main_walls_cyclic_move(state)

        assert state.mobs.picture[old_slot] == 0
        assert state.mobs.picture[new_slot] == 0x8000
        assert state.mobs.obj_type(new_slot) == int(MazeObjIds.WALL_TRAPCYC2)
        assert state.maze.data[(5, 5)] == int(MazeObjIds.TILE_FLOOR)
        assert state.maze.data[(6, 5)] == int(MazeObjIds.WALL_TRAPCYC2)
        assert state.sound_log == [0x2B]

    def test_transition_never_places_on_the_thief_cell(self):
        state = self._armed_state()
        tile = pack_slot(5, 6)
        state.wallcycle_time = 0
        state.thief_current_pos = tile
        state.cycle_phase_assignments[tile >> 2] |= 1 << ((tile & 3) * 2)

        main_walls_cyclic_move(state)

        assert state.mobs.picture[tile] == 0

    def test_late_mazes_suppress_the_cyclic_wall_sound(self):
        state = self._armed_state()
        state.mazenum_current = 0x73
        state.wallcycle_time = 0

        main_walls_cyclic_move(state)

        assert state.sound_log == []


class TestRandomWalls:
    def _state_with_walls(self) -> tuple[GameState, tuple[int, int]]:
        state = GameState(game_mode=GameMode.NORMAL)
        slots = (pack_slot(3, 4), pack_slot(3, 8))
        for slot in slots:
            _place(state, slot, MazeObjIds.WALL_RANDOM)
        setup_random_walls(state)
        return state, slots

    def test_setup_records_exact_low_target_and_cursor(self):
        state, slots = self._state_with_walls()
        assert state.randwall_low_watermark == slots[0]
        assert state.randwall_target == slots[1]
        assert state.randwall_current == slots[0] - 1
        assert state.randwall_timer == 0

    def test_processes_one_wall_per_frame_then_reloads(self):
        state, slots = self._state_with_walls()
        state.maze = SimpleNamespace(data={
            (4, 3): int(MazeObjIds.WALL_RANDOM),
            (8, 3): int(MazeObjIds.WALL_RANDOM),
        })
        # Each actual floor restamp draws getrandom(4) from the shared stream.
        state.rng = _FixedRNG(16, 0, 15)

        main_walls_random_move(state)
        assert state.mobs.picture[slots[0]] == 0
        assert state.mobs.picture[slots[1]] == 0x8000
        assert state.maze.data[(4, 3)] == int(MazeObjIds.TILE_FLOOR)
        assert state.maze.data[(8, 3)] == int(MazeObjIds.WALL_RANDOM)
        assert state.randwall_current == slots[0]

        main_walls_random_move(state)
        assert state.mobs.picture[slots[1]] == 0x8000
        assert state.randwall_timer == 0x78
        assert state.randwall_current == slots[0] - 1

    def test_timer_counts_while_the_incremental_scan_runs(self):
        state, slots = self._state_with_walls()
        state.randwall_timer = 2
        state.rng = _FixedRNG(16, 0, 16, 0)

        main_walls_random_move(state)
        assert state.randwall_timer == 1
        assert state.mobs.picture[slots[0]] == 0

        main_walls_random_move(state)
        assert state.mobs.picture[slots[1]] == 0
        assert state.randwall_timer == 0x78

    def test_title_mode_does_not_advance_the_random_wall_cursor(self):
        state, slots = self._state_with_walls()
        state.game_mode = GameMode.TITLE
        state.rng = _FixedRNG(16)

        main_walls_random_move(state)

        assert state.mobs.picture[slots[0]] == 0x8000
        assert state.randwall_current == slots[0] - 1
