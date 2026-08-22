"""WP-10: thief and mugger scheduling, targeting, and state machine.

Acceptance criteria come from PLAN.md §6 WP-10 and doc §9.
"""

from __future__ import annotations

import pytest

from gauntpy.constants import PlayerStatus
from gauntpy.coords import hpos_x, vpos_y
from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot
from gauntpy.constants import MazeObjIds
from gauntpy.state import GameState
from gauntpy.subsystems.thief import (
    THIEF_DEAD,
    THIEF_DODGE,
    THIEF_ENTER_OK,
    THIEF_ESCAPE,
    THIEF_IS_MUGGER,
    THIEF_JUMPJUMP,
    THIEF_PURSUE,
    main_start_thief,
    main_thief_anim,
    thief_begin_dodge,
    thief_end_dodge,
    thief_exit,
    thief_find_aligned_shooter,
    thief_handle_tile_collision,
    thief_move_engine,
    thief_setup,
    thief_steal_from_player,
    thief_remove_and_drop_loot,
    thief_compute_path,
    thief_track_victim_move,
    thief_target_calc,
    thief_timer_set,
    calc_direction,
    path_grid_get_direction,
    path_grid_set_high_direction_if_empty,
    path_grid_set_low_direction,
    _SPEED_MUGGER,
    _SPEED_THIEF,
    _THIEF_COLLISION_REMOVE_FLAGS,
    _THIEF_DIRECTION_STEP_FLAGS,
)

# Same skip condition test_assets.py uses: the ROM byte-match below needs the
# real code ROMs, everything else in this module does not.
from gex.roms import _rom_dir, TILE_ROMS  # noqa: E402

_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not (_ROM_PATH.is_dir() and (_ROM_PATH / TILE_ROMS[0][0]).is_file()),
    reason=f"ROM files not available at {_ROM_PATH}",
)


class _FixedRNG:
    def __init__(self, *values: int, default: int = 0) -> None:
        self._queue = list(values)
        self._default = default

    def getrandom(self, bound: int) -> int:  # noqa: ARG002
        return self._queue.pop(0) if self._queue else self._default

    random_word = getrandom


class _RecordingRNG:
    def __init__(self, *values: int) -> None:
        self._queue = list(values)
        self.bounds: list[int] = []

    def getrandom(self, bound: int) -> int:
        self.bounds.append(bound)
        return self._queue.pop(0) if self._queue else 0


def _active(state: GameState, index: int, slot: int) -> None:
    p = state.players[index]
    p.status = PlayerStatus.ALIVE_HERE
    p.health = max(p.health, 1000)
    p.mob_slot = slot
    row, col = slot >> 5, slot & 0x1F
    state.mobs.hpos[slot] = encode_hpos(col * 16)
    state.mobs.vpos[slot] = encode_vpos_at_y(row * 16)


class TestScheduling:
    def test_no_thief_below_level_6(self):
        state = GameState()
        state.game_mode = 0
        state.mazenum_current = 10
        state.levelnum_current = 5
        _active(state, 0, pack_slot(5, 5))
        thief_setup(state)
        assert state.thief_enter_time < 0, "must not schedule below level 6"

    def test_no_thief_in_secret_maze(self):
        state = GameState()
        state.game_mode = 0
        state.mazenum_current = 0x73     # 115 -> secret room, excluded
        state.levelnum_current = 20
        _active(state, 0, pack_slot(5, 5))
        thief_setup(state)
        assert state.thief_enter_time < 0

    def test_setup_clears_a_stale_victim_when_its_gate_fails(self):
        state = GameState()
        state.game_mode = -1
        state.thief_victim = 3

        thief_setup(state)

        assert state.thief_victim == -1

    def test_schedules_when_roll_succeeds(self):
        state = GameState()
        state.rng = _FixedRNG(0, 0, 5)   # setup roll 0, timer_set mugger roll, delay
        state.game_mode = 0
        state.mazenum_current = 10
        state.levelnum_current = 16      # level>>3 = 2 > getrandom(8)=0
        _active(state, 0, pack_slot(5, 5))
        thief_setup(state)
        assert state.thief_enter_time > 0, "should have scheduled a delay"

    def test_roll_fails_when_random_too_high(self):
        state = GameState()
        state.rng = _FixedRNG(7)         # level>>3 (2) <= 7 -> no schedule
        state.game_mode = 0
        state.mazenum_current = 10
        state.levelnum_current = 16
        _active(state, 0, pack_slot(5, 5))
        thief_setup(state)
        assert state.thief_enter_time < 0

    def test_scheduling_records_the_target_current_cell(self):
        state = GameState()
        state.rng = _FixedRNG(0, 20, 5)
        state.game_mode = 0
        state.mazenum_current = 10
        state.levelnum_current = 16
        # The victim's record names the cell it stands in.
        _active(state, 0, pack_slot(8, 9))
        player_slot = state.players[0].mob_slot
        state.mobs.hpos[player_slot] = encode_hpos(9 * 16 + 7)
        state.mobs.vpos[player_slot] = encode_vpos_at_y(8 * 16 + 3)

        thief_setup(state)

        assert state.thief_start_location == pack_slot(8, 9)
        assert state.thief_victim_pos == pack_slot(8, 9)


class TestMuggerSelection:
    def test_low_roll_selects_mugger(self):
        state = GameState()
        state.rng = _FixedRNG(0, 5)      # 0 < 16 -> mugger, then delay span draw
        state.levelnum_current = 16
        state.mazenum_current = 10
        _active(state, 0, pack_slot(5, 5))
        state.thief_victim = 0
        thief_timer_set(state)
        assert state.thief_mode & THIEF_IS_MUGGER
        assert state.thief_speed == _SPEED_MUGGER

    def test_high_roll_selects_thief(self):
        state = GameState()
        state.rng = _FixedRNG(20, 5)     # 20 >= 16, bit4 clear -> ordinary thief
        state.levelnum_current = 16
        state.mazenum_current = 10
        _active(state, 0, pack_slot(5, 5))
        state.thief_victim = 0
        thief_timer_set(state)
        assert not (state.thief_mode & THIEF_IS_MUGGER)
        assert state.thief_speed == _SPEED_THIEF


class TestTargeting:
    def test_wealthiest_player_selected(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        _active(state, 1, pack_slot(6, 6))
        state.players[0].keysnum = 1
        state.players[1].keysnum = 5     # player 1 is wealthier
        thief_target_calc(state)
        assert state.thief_victim == 1

    def test_ignores_inactive_players(self):
        state = GameState()
        _active(state, 2, pack_slot(7, 7))
        state.players[2].potionsnum = 3
        thief_target_calc(state)
        assert state.thief_victim == 2

    def test_ignores_active_but_dead_players(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        _active(state, 1, pack_slot(6, 6))
        state.players[0].powers = 0x3F
        state.players[0].health = 0
        state.players[1].keysnum = 1

        thief_target_calc(state)

        assert state.thief_victim == 1

    def test_shot_power_bit_outweighs_a_key(self):
        """A player holding the shot-power upgrade (bit 4) is the richer target.

        Regression for the power-bit layout: shot power is worth 0x3E8, far more
        than a key (0x2), so a shot-power player must be picked over a key
        holder.  This fails if _POWER_SHOT reads the wrong bit.
        """
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        _active(state, 1, pack_slot(6, 6))
        state.players[0].keysnum = 5              # 5 × 0x2 = 0x0A
        state.players[1].powers = 0x0010          # POWER_SHOTPOWER_BIT (bit 4)
        thief_target_calc(state)
        assert state.thief_victim == 1, "shot-power player must be the target"


class TestDeployAndSteal:
    def test_timer_countdown_then_deploy(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.thief_mode = THIEF_PURSUE
        state.thief_victim = 0
        state.thief_start_location = pack_slot(6, 6)
        state.thief_speed = _SPEED_THIEF
        state.thief_enter_time = 1
        main_start_thief(state)          # 1 -> 0
        assert state.thief_enter_time == 0
        main_start_thief(state)          # 0 -> deploy
        assert state.thief_mode & THIEF_PURSUE
        assert state.thief_current_pos == pack_slot(6, 6)
        assert state.thief_enter_time == 0x3C
        assert state.mobs.picture[pack_slot(6, 6)] == 0x0DEA
        assert state.mobs.obj_type(pack_slot(6, 6)) == int(MazeObjIds.PLAYERSTART)

    def test_steal_takes_key_first(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.players[0].keysnum = 2
        state.players[0].potionsnum = 1
        thief_steal_from_player(state, 0)
        assert state.players[0].keysnum == 1
        assert state.players[0].potionsnum == 1

    def test_mugger_takes_health_when_empty(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.players[0].health = 500
        state.thief_mode = THIEF_IS_MUGGER
        thief_steal_from_player(state, 0)
        assert state.players[0].health == 400
        assert state.mugger_item_carried == int(MazeObjIds.FOOD_INVULN)

    def test_pursue_to_overlap_steals_and_escapes(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.players[0].keysnum = 1
        # Thief sitting on the victim's cell.
        slot = pack_slot(5, 5)
        state.thief_mob_slot = slot
        state.thief_current_pos = slot
        state.thief_next_pos = slot
        state.thief_victim = 0
        state.thief_mode = THIEF_PURSUE
        state.thief_speed = _SPEED_THIEF
        main_thief_anim(state)
        assert state.players[0].keysnum == 0, "thief should have stolen the key"
        assert state.thief_mode & THIEF_ESCAPE
        assert state.thief_mode & THIEF_JUMPJUMP


class TestNotDeployed:
    def test_anim_noop_when_dead(self):
        state = GameState()
        state.thief_mode = THIEF_DEAD
        main_thief_anim(state)           # must not raise
        assert state.thief_mode == THIEF_DEAD


class TestRouteGrid:
    def test_low_nibble_replaces_and_uses_44_column_stride(self):
        state = GameState()
        path_grid_set_high_direction_if_empty(state, 0, 6)
        path_grid_set_low_direction(state, 0, 2)
        path_grid_set_low_direction(state, 0, 4)
        path_grid_set_low_direction(state, 44, 1)

        assert state.path_direction_grid[0] == 0x75
        assert state.path_direction_grid[0x80] == 0x02
        assert path_grid_get_direction(state, 0) == 4
        assert path_grid_get_direction(state, 44) == 1

    def test_high_nibble_is_write_once_and_disabled_during_escape(self):
        state = GameState()
        path_grid_set_high_direction_if_empty(state, 75, 3)
        path_grid_set_high_direction_if_empty(state, 75, 5)
        state.thief_mode = THIEF_ESCAPE
        path_grid_set_high_direction_if_empty(state, 75, 1)
        path_grid_set_high_direction_if_empty(state, 76, 1)
        path_grid_set_low_direction(state, 75, 1)

        assert state.path_direction_grid[0x80 + 31] == 0x42
        assert state.path_direction_grid[0x80 + 32] == 0
        assert path_grid_get_direction(state, 75) == 3

    def test_unset_and_invalid_nibbles_return_direction_eight(self):
        state = GameState()
        assert path_grid_get_direction(state, 100) == 8
        state.path_direction_grid[0x80 + 12] = 0x09
        assert path_grid_get_direction(state, 56) == 8


class TestVictimRouteTracking:
    def test_target_move_records_low_nibble_and_updates_prior_position(self):
        state = GameState()
        old_pos = pack_slot(10, 10)
        new_pos = pack_slot(10, 11)
        state.thief_victim = 2
        state.thief_victim_pos = old_pos

        thief_track_victim_move(state, new_pos, 2)

        assert path_grid_get_direction(state, old_pos) == 2
        assert state.thief_victim_pos == new_pos

    def test_nonvictim_or_same_position_does_not_change_route(self):
        state = GameState()
        pos = pack_slot(8, 8)
        state.thief_victim = 1
        state.thief_victim_pos = pos

        thief_track_victim_move(state, pack_slot(8, 9), 0)
        thief_track_victim_move(state, pos, 1)

        assert path_grid_get_direction(state, pos) == 8
        assert state.thief_victim_pos == pos

    def test_calc_direction_honors_wrap_flags(self):
        state = GameState()
        assert calc_direction(state, pack_slot(5, 31), pack_slot(5, 0)) == 6
        state.wrap_h = True
        assert calc_direction(state, pack_slot(5, 31), pack_slot(5, 0)) == 2


class TestThiefComputePath:
    @staticmethod
    def _state_at(slot: int) -> GameState:
        state = GameState()
        state.thief_current_pos = slot
        state.thief_next_pos = slot
        return state

    def test_selects_route_direction_and_preserves_prior_next_cell(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        state.thief_next_pos = pack_slot(10, 9)
        state.thief_path_direction = 6
        path_grid_set_low_direction(state, current, 2)

        thief_compute_path(state)

        assert state.thief_path_direction == 2
        assert state.thief_previous_pos == pack_slot(10, 9)
        assert state.thief_next_pos == pack_slot(10, 11)

    def test_unset_route_restores_saved_direction(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        state.thief_path_direction = 2

        thief_compute_path(state)

        assert state.thief_path_direction == 2
        assert state.thief_next_pos == pack_slot(10, 11)

    def test_escape_mode_reads_high_nibble_and_recovers_even_corner(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        right = pack_slot(10, 11)
        diagonal = pack_slot(11, 11)
        path_grid_set_high_direction_if_empty(state, current, 2)
        path_grid_set_high_direction_if_empty(state, right, 4)
        path_grid_set_high_direction_if_empty(state, diagonal, 2)
        path_grid_set_high_direction_if_empty(state, pack_slot(11, 12), 0)
        state.thief_mode = THIEF_ESCAPE

        thief_compute_path(state)

        assert state.thief_path_direction == 3
        assert state.thief_next_pos == diagonal

    def test_odd_direction_skips_corner_recovery(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        diagonal = pack_slot(11, 11)
        path_grid_set_low_direction(state, current, 3)
        path_grid_set_low_direction(state, diagonal, 1)

        thief_compute_path(state)

        assert state.thief_path_direction == 3
        assert state.thief_next_pos == diagonal

    def test_recovers_diagonal_at_a_traversable_route_corner(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        right = pack_slot(10, 11)
        diagonal = pack_slot(11, 11)
        path_grid_set_low_direction(state, current, 2)
        path_grid_set_low_direction(state, right, 4)
        path_grid_set_low_direction(state, diagonal, 2)
        path_grid_set_low_direction(state, pack_slot(11, 12), 0)

        thief_compute_path(state)

        assert state.thief_path_direction == 3
        assert state.thief_next_pos == diagonal

    def test_corner_recovery_requires_traversable_side_cells(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        right = pack_slot(10, 11)
        diagonal = pack_slot(11, 11)
        path_grid_set_low_direction(state, current, 2)
        path_grid_set_low_direction(state, right, 4)
        path_grid_set_low_direction(state, diagonal, 2)
        path_grid_set_low_direction(state, pack_slot(11, 12), 0)
        state.mobs.set_obj_type(right, MazeObjIds.TILE_STUN)

        thief_compute_path(state)

        assert state.thief_path_direction == 2
        assert state.thief_next_pos == right

    def test_corner_recovery_requires_a_valid_route_beyond_diagonal(self):
        current = pack_slot(10, 10)
        state = self._state_at(current)
        right = pack_slot(10, 11)
        diagonal = pack_slot(11, 11)
        path_grid_set_low_direction(state, current, 2)
        path_grid_set_low_direction(state, right, 4)
        path_grid_set_low_direction(state, diagonal, 2)

        thief_compute_path(state)

        assert state.thief_path_direction == 2
        assert state.thief_next_pos == right


class TestRouteGridMovement:
    def test_pursuit_moves_using_the_computed_grid_direction(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        victim_slot = pack_slot(12, 10)
        _active(state, 0, victim_slot)
        state.thief_mob_slot = thief_slot
        state.thief_current_pos = thief_slot
        state.thief_next_pos = thief_slot
        state.thief_victim = 0
        state.thief_mode = THIEF_PURSUE
        state.thief_speed = _SPEED_THIEF
        state.mobs.hpos[thief_slot] = encode_hpos(10 * 16)
        state.mobs.vpos[thief_slot] = encode_vpos_at_y(10 * 16)
        path_grid_set_low_direction(state, thief_slot, 2)

        main_thief_anim(state)

        assert state.thief_path_direction == 2
        assert state.thief_next_pos == pack_slot(10, 11)
        assert hpos_x(state.mobs.hpos[thief_slot]) == 10 * 16 + 4

    def test_crossing_a_route_cell_records_reverse_escape_direction(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        victim_slot = pack_slot(12, 10)
        _active(state, 0, victim_slot)
        state.thief_mob_slot = thief_slot
        state.thief_current_pos = thief_slot
        state.thief_next_pos = thief_slot
        state.thief_victim = 0
        state.thief_mode = THIEF_PURSUE
        state.thief_speed = _SPEED_THIEF
        state.mobs.hpos[thief_slot] = encode_hpos(10 * 16)
        state.mobs.vpos[thief_slot] = encode_vpos_at_y(10 * 16)
        path_grid_set_low_direction(state, thief_slot, 2)

        for _ in range(4):
            main_thief_anim(state)

        destination = pack_slot(10, 11)
        assert state.thief_mob_slot == destination
        state.thief_mode = THIEF_ESCAPE
        assert path_grid_get_direction(state, destination) == 6


def _thief_at(state: GameState, slot: int, direction: int = 8) -> None:
    row, col = slot >> 5, slot & 0x1F
    state.thief_mob_slot = slot
    state.thief_current_pos = slot
    state.thief_previous_pos = slot
    state.thief_next_pos = slot
    state.thief_direction = direction
    state.thief_enter_time = -1
    state.mobs.hpos[slot] = encode_hpos(col * 16)
    state.mobs.vpos[slot] = encode_vpos_at_y(row * 16)
    state.mobs.picture[slot] = 1


class TestTimerAndTheftDetails:
    def test_both_spent_latches_prevent_another_schedule(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.thief_victim = 0
        state.thief_mode = 0x30
        state.thief_enter_time = 99

        thief_timer_set(state)

        assert state.thief_enter_time == -1
        assert state.thief_mode == 0x30

    def test_delay_uses_the_target_players_score_and_coin_count(self):
        state = GameState()
        state.rng = _FixedRNG(20, 0)
        state.levelnum_current = 6
        _active(state, 0, pack_slot(5, 5))
        _active(state, 1, pack_slot(6, 6))
        state.players[0].score = 0
        state.players[0].coin_count = 1
        state.players[1].score = 15 << 13
        state.players[1].coin_count = 1
        state.thief_victim = 0

        thief_timer_set(state)

        assert state.thief_enter_time == 20 * 60

    def test_treasure_room_delay_uses_the_shorter_plus_five_span(self):
        state = GameState()
        state.rng = _RecordingRNG(20, 0)
        state.mazenum_current = 0x68
        state.levelnum_current = 6
        _active(state, 0, pack_slot(5, 5))
        state.players[0].score = 5 << 13
        state.players[0].coin_count = 1
        state.thief_victim = 0

        thief_timer_set(state)

        assert state.rng.bounds == [32, 13]
        assert state.thief_enter_time == 5 * 60

    def test_permanent_powers_are_stolen_in_rom_priority_order(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        _thief_at(state, pack_slot(6, 6))
        state.players[0].powers = 0x3F

        assert thief_steal_from_player(state, 0) == 1

        assert state.players[0].powers == 0x2F
        assert state.thief_item_carried == int(MazeObjIds.POT_INVULN)
        assert state.thief_mode & THIEF_ESCAPE
        assert state.thief_mode & THIEF_JUMPJUMP
        assert state.thief_mode & 0x10

    def test_multiplier_is_stolen_when_it_is_the_most_valuable_resource(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.players[0].potionsnum = 1
        state.players[0].keysnum = 1
        state.players[0].bonusmult = 4

        thief_steal_from_player(state, 0)

        assert state.players[0].bonusmult == 1
        assert state.thief_item_carried == (4 * 500 << 6) | int(MazeObjIds.TREASURE_BAG)

    def test_escape_mode_suppresses_repeat_theft(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        state.players[0].keysnum = 2
        state.thief_mode = THIEF_ESCAPE

        assert thief_steal_from_player(state, 0) == 0
        assert state.players[0].keysnum == 2


class TestRemoveAndDropLoot:
    def test_killed_thief_awards_bounty_dissolves_and_recreates_carried_key(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        _active(state, 0, pack_slot(5, 5))
        state.players[0].bonusmult = 3
        _thief_at(state, thief_slot)
        state.thief_mode = THIEF_PURSUE
        state.thief_victim = -1
        state.thief_item_carried = int(MazeObjIds.KEY)

        thief_remove_and_drop_loot(state, 0, thief_slot)

        assert state.players[0].score == 1500
        assert state.score_dirty[0] == 1
        assert state.thief_current_pos == 0
        assert state.thief_mob_slot == 0
        assert state.mobs.obj_type(thief_slot) == int(MazeObjIds.KEY)
        assert state.mobs.picture[thief_slot] == 0x8AFC
        assert state.thief_item_carried == 0x7D30
        assert state.special_bonus_score == 0
        assert 0x0924 in state.mobs.picture[13:17]

    def test_multiplier_bag_keeps_its_encoded_value_as_special_bonus(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        _active(state, 0, pack_slot(5, 5))
        _active(state, 1, pack_slot(6, 6))
        _thief_at(state, thief_slot)
        state.thief_mode = THIEF_PURSUE
        state.thief_victim = 1
        state.thief_item_carried = (4 * 500 << 6) | int(MazeObjIds.TREASURE_BAG)
        state.rng = _FixedRNG(20, 0)

        thief_remove_and_drop_loot(state, -1, 0)

        assert state.players[0].score == 0
        assert state.special_bonus_score == 2000
        assert state.mobs.obj_type(thief_slot) == int(MazeObjIds.TREASURE_BAG)
        assert state.thief_item_carried == 0x7D30

    def test_killed_mugger_drops_food_and_preserves_normal_thief_score_field(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        _active(state, 0, pack_slot(5, 5))
        state.players[0].bonusmult = 2
        _thief_at(state, thief_slot)
        state.thief_mode = THIEF_PURSUE | THIEF_IS_MUGGER
        state.thief_victim = -1
        state.thief_item_carried = 0x1234
        state.mugger_item_carried = int(MazeObjIds.FOOD_INVULN)
        state.special_bonus_score = 777

        thief_remove_and_drop_loot(state, 0, 0)

        assert state.players[0].score == 1000
        assert state.mugger_item_carried == 0
        assert state.thief_item_carried == 0x1234
        assert state.special_bonus_score == 777
        assert state.mobs.obj_type(thief_slot) == int(MazeObjIds.FOOD_INVULN)
        assert state.mobs.picture[thief_slot] == 0x096C

    def test_replacement_slot_receives_the_effect_and_the_new_pickup(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        replacement = pack_slot(12, 12)
        _thief_at(state, thief_slot)
        state.thief_mode = THIEF_PURSUE
        state.thief_victim = -1
        state.thief_item_carried = int(MazeObjIds.KEY)
        state.thief_tport_timer = 0
        state.thief_tport_dest = replacement
        state.mobs.create(
            replacement,
            1,
            encode_hpos(12 * 16),
            encode_vpos_at_y(12 * 16),
            MazeObjIds.TREASURE,
        )

        thief_remove_and_drop_loot(state, -1, replacement)

        assert state.mobs.picture[thief_slot] == 0
        assert state.mobs.obj_type(replacement) == int(MazeObjIds.KEY)
        assert state.mobs.picture[replacement] == 0x8AFC
        assert state.thief_tport_timer == -1
        assert 0x0924 in state.mobs.picture[13:17]

    def test_empty_mugger_carry_removes_the_mob_without_creating_a_pickup(self):
        state = GameState()
        thief_slot = pack_slot(10, 10)
        _thief_at(state, thief_slot)
        state.thief_mode = THIEF_PURSUE | THIEF_IS_MUGGER
        state.thief_victim = -1
        state.mugger_item_carried = 0

        thief_remove_and_drop_loot(state, -1, 0)

        assert state.thief_current_pos == 0
        assert state.mobs.picture[thief_slot] == 0


class TestDeployAndEscapeGraph:
    def test_deploy_retries_when_the_start_cell_is_occupied(self):
        state = GameState()
        _active(state, 0, pack_slot(5, 5))
        start = pack_slot(6, 6)
        state.mobs.picture[start] = 1
        state.thief_mode = THIEF_PURSUE
        state.thief_victim = 0
        state.thief_start_location = start
        state.thief_enter_time = 0

        main_start_thief(state)

        assert state.thief_current_pos == 0
        assert state.thief_enter_time == 0x12C

    def test_exit_changes_to_escape_and_reverses_the_pending_cell(self):
        state = GameState()
        current = pack_slot(10, 10)
        previous = pack_slot(10, 9)
        _thief_at(state, current)
        state.thief_mode = THIEF_PURSUE
        state.thief_previous_pos = previous
        state.thief_next_pos = pack_slot(10, 11)

        thief_exit(state)

        assert state.thief_current_pos == current
        assert state.thief_mode & THIEF_ESCAPE
        assert not state.thief_mode & THIEF_PURSUE
        assert state.thief_next_pos == previous

    def test_escape_finishes_when_the_route_returns_to_start(self):
        state = GameState()
        start = pack_slot(10, 10)
        _active(state, 0, pack_slot(5, 5))
        _thief_at(state, start)
        state.thief_mode = THIEF_ESCAPE | THIEF_ENTER_OK
        state.thief_victim = 0
        state.thief_start_location = start
        state.thief_previous_pos = pack_slot(10, 9)
        state.thief_item_carried = int(MazeObjIds.KEY)
        state.rng = _FixedRNG(0, 0)

        main_thief_anim(state)

        assert state.thief_current_pos == 0
        assert state.thief_mob_slot == 0
        assert state.thief_item_nextlevel == int(MazeObjIds.KEY)

    def test_post_theft_pause_uses_escape_animation_then_pitch_pair(self):
        state = GameState()
        slot = pack_slot(10, 10)
        _thief_at(state, slot)
        state.rng = _FixedRNG(0)
        state.thief_mode = THIEF_ESCAPE | THIEF_JUMPJUMP
        state.thief_stolen_item = 0x3B
        state.thief_start_location = pack_slot(9, 9)

        main_thief_anim(state)

        assert not state.thief_mode & THIEF_JUMPJUMP
        assert state.thief_stolen_item == 0x3C
        assert state.sound_log[-2:] == [0x62, 0x63]


class TestShotDodge:
    @staticmethod
    def _aligned_state() -> GameState:
        state = GameState()
        _thief_at(state, pack_slot(10, 10), direction=6)
        state.thief_mode = THIEF_PURSUE
        state.thief_speed = _SPEED_THIEF
        state.thief_previous_pos = pack_slot(10, 9)
        state.mobs.picture[1] = 1
        state.mobs.hpos[1] = encode_hpos(8 * 16)
        state.mobs.vpos[1] = encode_vpos_at_y(10 * 16)
        state.shot_direction[0] = 2
        return state

    def test_finds_first_cardinal_aligned_player_shot(self):
        state = self._aligned_state()
        state.mobs.picture[2] = 1
        state.mobs.hpos[2] = encode_hpos(7 * 16)
        state.mobs.vpos[2] = encode_vpos_at_y(10 * 16)
        state.shot_direction[1] = 2

        assert thief_find_aligned_shooter(state) == 0

    def test_finds_diagonal_alignment_and_honors_wrap(self):
        diagonal = GameState()
        _thief_at(diagonal, pack_slot(10, 10), direction=5)
        diagonal.mobs.picture[1] = 1
        diagonal.mobs.hpos[1] = encode_hpos(9 * 16)
        diagonal.mobs.vpos[1] = encode_vpos_at_y(11 * 16)
        diagonal.shot_direction[0] = 1
        assert thief_find_aligned_shooter(diagonal) == 0

        wrapped = self._aligned_state()
        _thief_at(wrapped, pack_slot(10, 0), direction=6)
        wrapped.mobs.hpos[1] = encode_hpos(31 * 16)
        assert thief_find_aligned_shooter(wrapped) == -1
        wrapped.wrap_h = True
        assert thief_find_aligned_shooter(wrapped) == 0

    def test_rejects_inactive_or_wrong_direction_shots(self):
        state = self._aligned_state()
        state.mobs.picture[1] = 0
        assert thief_find_aligned_shooter(state) == -1
        state.mobs.picture[1] = 1
        state.shot_direction[0] = 6
        assert thief_find_aligned_shooter(state) == -1

    def test_uses_live_shot_velocity_when_direction_word_is_unset(self):
        state = self._aligned_state()
        state.shot_direction[0] = 8
        state.shot_dx[1] = 6
        state.shot_dy[1] = 0

        assert thief_find_aligned_shooter(state) == 0

    def test_begin_end_dodge_flip_route_polarity_and_repair_next_cell(self):
        state = GameState()
        current = pack_slot(10, 10)
        previous = pack_slot(10, 9)
        _thief_at(state, current)
        state.thief_mode = THIEF_PURSUE
        state.thief_previous_pos = previous
        state.thief_next_pos = pack_slot(10, 11)

        thief_begin_dodge(state)
        assert state.thief_mode & THIEF_DODGE
        assert state.thief_mode & THIEF_ESCAPE
        assert state.thief_next_pos == previous

        thief_end_dodge(state)
        assert not state.thief_mode & THIEF_DODGE
        assert state.thief_mode & THIEF_PURSUE
        assert state.thief_next_pos == previous

    def test_main_latches_shot_then_ends_dodge_when_its_direction_changes(self):
        state = self._aligned_state()

        main_thief_anim(state)

        assert state.thief_mode & THIEF_DODGE
        assert state.thief_mode & THIEF_ESCAPE
        assert state.thief_pursuit_player == 0
        assert state.thief_pursuit_shot_direction == 2
        assert state.thief_pursuit_direction >= 0

        state.shot_direction[0] = 3
        main_thief_anim(state)

        assert not state.thief_mode & THIEF_DODGE
        assert state.thief_mode & THIEF_PURSUE

    def test_mugger_does_not_enter_shot_dodge(self):
        state = self._aligned_state()
        state.thief_mode |= THIEF_IS_MUGGER

        main_thief_anim(state)

        assert not state.thief_mode & THIEF_DODGE


class TestMoveEngineCollisionAndAnimation:
    def test_diagonal_engine_moves_both_axes_and_relocates(self):
        state = GameState()
        start = pack_slot(10, 10)
        _thief_at(state, start)
        state.thief_mode = THIEF_PURSUE

        for _ in range(4):
            thief_move_engine(
                state, _THIEF_DIRECTION_STEP_FLAGS[3],
                _SPEED_THIEF, _SPEED_THIEF,
            )

        destination = pack_slot(11, 11)
        assert state.thief_mob_slot == destination
        assert hpos_x(state.mobs.hpos[destination]) == 11 * 16
        assert vpos_y(state.mobs.vpos[destination]) == 11 * 16

    def test_engine_blocks_solid_tile_without_crossing_the_cell(self):
        state = GameState()
        start = pack_slot(10, 10)
        destination = pack_slot(10, 11)
        _thief_at(state, start)
        state.thief_mode = THIEF_PURSUE
        state.mobs.hpos[start] = encode_hpos(10 * 16 + 12)
        state.mobs.picture[destination] = 0x8000
        state.mobs.set_obj_type(destination, MazeObjIds.WALL_REGULAR)

        result = thief_move_engine(state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF)

        assert result == 1
        assert state.thief_mob_slot == start
        assert hpos_x(state.mobs.hpos[start]) == 10 * 16 + 12

    def test_collision_removes_eligible_pickup_before_retrying_the_move(self):
        state = GameState()
        start = pack_slot(10, 10)
        destination = pack_slot(10, 11)
        _thief_at(state, start)
        state.thief_mode = THIEF_PURSUE
        state.mobs.hpos[start] = encode_hpos(10 * 16 + 12)
        state.mobs.create(destination, 1, encode_hpos(11 * 16), encode_vpos_at_y(10 * 16), MazeObjIds.TREASURE)

        assert thief_move_engine(state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF) == 1
        assert state.mobs.picture[destination] == 0
        assert thief_move_engine(state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF) == 0
        assert state.thief_mob_slot == destination

    def test_nonblocking_occupied_cell_keeps_the_thiefs_slot_but_moves_pixels(self):
        state = GameState()
        start = pack_slot(10, 10)
        destination = pack_slot(10, 11)
        _thief_at(state, start)
        state.thief_mode = THIEF_PURSUE
        state.mobs.hpos[start] = encode_hpos(10 * 16 + 12)
        state.mobs.create(destination, 1, encode_hpos(11 * 16), encode_vpos_at_y(10 * 16), MazeObjIds.TILE_STUN)

        assert thief_move_engine(state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF) == 0
        assert state.thief_mob_slot == start
        assert hpos_x(state.mobs.hpos[start]) == 11 * 16

    def test_engine_contacts_the_cell_the_player_record_occupies(self):
        state = GameState()
        thief_slot = pack_slot(10, 9)
        player_slot = pack_slot(10, 10)
        _active(state, 0, player_slot)
        state.players[0].keysnum = 2
        state.mobs.create(
            player_slot, 1, encode_hpos(10 * 16),
            encode_vpos_at_y(10 * 16), MazeObjIds.PLAYERSTART,
        )
        _thief_at(state, thief_slot)
        state.mobs.hpos[thief_slot] = encode_hpos(10 * 16 - 1)
        state.thief_mode = THIEF_PURSUE

        thief_move_engine(
            state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF,
        )

        assert state.players[0].keysnum == 1
        assert state.thief_mode & THIEF_ESCAPE

    def test_escape_contact_damage_uses_the_collision_latch(self):
        state = GameState()
        player_slot = pack_slot(5, 5)
        _active(state, 0, player_slot)
        state.players[0].health = 100
        state.thief_mode = THIEF_ESCAPE
        state.thief_stolen_item = 0x10
        state.thief_collision_direction_code = 1

        assert thief_handle_tile_collision(state, player_slot) == 0
        assert state.players[0].health == 94
        assert state.players[0].hurt_cooldown == 0x12
        assert state.thief_collision_direction_code == 0

    def test_first_escape_contact_only_sets_the_latch_once(self):
        state = GameState()
        thief_slot = pack_slot(10, 9)
        player_slot = pack_slot(10, 10)
        _active(state, 0, player_slot)
        state.players[0].health = 100
        state.mobs.create(
            player_slot, 1, encode_hpos(10 * 16),
            encode_vpos_at_y(10 * 16), MazeObjIds.PLAYERSTART,
        )
        _thief_at(state, thief_slot, direction=2)
        state.mobs.hpos[thief_slot] = encode_hpos(10 * 16 - 1)
        state.thief_mode = THIEF_ESCAPE
        state.thief_stolen_item = 0x10

        thief_move_engine(
            state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF,
        )

        assert state.players[0].health == 100
        assert state.thief_collision_direction_code == 3
        assert state.thief_stolen_item == 0

    def test_blocked_motion_selects_the_compact_animation_bank(self):
        state = GameState()
        start = pack_slot(10, 10)
        destination = pack_slot(10, 11)
        _thief_at(state, start)
        state.thief_mode = THIEF_PURSUE
        state.thief_speed = _SPEED_THIEF
        state.thief_next_pos = destination
        state.thief_previous_pos = pack_slot(10, 9)
        state.mobs.hpos[start] = encode_hpos(10 * 16 + 12)
        state.mobs.picture[destination] = 0x8000
        state.mobs.set_obj_type(destination, MazeObjIds.WALL_REGULAR)

        main_thief_anim(state)

        assert state.mobs.picture[start] == 0x0E63


# ---------------------------------------------------------------------------
# thief_collision_remove_flags (0x5B6AE), read at 0x4F8EC
# ---------------------------------------------------------------------------

#: ROM 0x5B6AE, all 64 bytes.  ``thief_handle_tile_collision`` indexes it with
#: the candidate cell's object type, which comes out of ``mob_link`` bits 15-10
#: and therefore covers the whole 0-63 range -- the table is not optional at
#: either end.
_ROM_THIEF_COLLISION_REMOVE_FLAGS = (
    1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0,
)


class TestCollisionRemoveTable:
    def test_the_table_is_exactly_sixty_four_bytes(self):
        assert len(_THIEF_COLLISION_REMOVE_FLAGS) == 64

    def test_the_table_matches_the_transcribed_rom_bytes(self):
        assert _THIEF_COLLISION_REMOVE_FLAGS == _ROM_THIEF_COLLISION_REMOVE_FLAGS

    @requires_roms
    def test_the_table_matches_the_rom_itself(self):
        """Byte for byte against 0x5B6AE in the real code ROMs."""
        from gex.roms import coderom_get_bytes

        assert tuple(coderom_get_bytes(0x5B6AE, 64)) == \
            _THIEF_COLLISION_REMOVE_FLAGS

    def test_every_pickup_including_supershot_and_hiddenpot_is_removable(self):
        for obj_type in (
            MazeObjIds.TREASURE, MazeObjIds.TREASURE_LOCKED,
            MazeObjIds.TREASURE_BAG, MazeObjIds.FOOD_DESTRUCTABLE,
            MazeObjIds.FOOD_INVULN, MazeObjIds.POT_DESTRUCTABLE,
            MazeObjIds.POT_INVULN, MazeObjIds.KEY,
            MazeObjIds.POWER_INVIS, MazeObjIds.POWER_REPULSE,
            MazeObjIds.POWER_REFLECT, MazeObjIds.POWER_TRANSPORT,
            MazeObjIds.POWER_SUPERSHOT, MazeObjIds.POWER_INVULN,
            MazeObjIds.HIDDENPOT,
        ):
            assert _THIEF_COLLISION_REMOVE_FLAGS[int(obj_type)] == 1, obj_type

    def test_the_dragon_transporter_and_hub_are_not_removable(self):
        for obj_type in (MazeObjIds.MONST_DRAGON, MazeObjIds.TRANSPORTER,
                         MazeObjIds.FORCEFIELDHUB):
            assert _THIEF_COLLISION_REMOVE_FLAGS[int(obj_type)] == 0, obj_type


class TestCollisionAgainstHighObjectTypes:
    """The four types a 62-entry transcription got wrong or could not index."""

    @staticmethod
    def _thief_stepping_right(state: GameState) -> tuple[int, int]:
        start, destination = pack_slot(10, 10), pack_slot(10, 11)
        _thief_at(state, start)
        state.thief_mode = THIEF_PURSUE
        state.mobs.hpos[start] = encode_hpos(10 * 16 + 12)
        return start, destination

    def _step(self, state: GameState) -> int:
        return thief_move_engine(
            state, _THIEF_DIRECTION_STEP_FLAGS[2], _SPEED_THIEF, _SPEED_THIEF
        )

    def test_supershot_is_eaten_then_walked_into(self):
        state = GameState()
        start, destination = self._thief_stepping_right(state)
        state.mobs.create(destination, 1, encode_hpos(11 * 16),
                          encode_vpos_at_y(10 * 16), MazeObjIds.POWER_SUPERSHOT)

        assert self._step(state) == 1, "the removal costs the thief this frame"
        assert state.mobs.picture[destination] == 0
        assert state.mobs.obj_type(destination) == 0
        assert state.thief_mob_slot == start

        assert self._step(state) == 0
        assert state.thief_mob_slot == destination

    def test_hidden_potion_is_eaten_then_walked_into(self):
        state = GameState()
        start, destination = self._thief_stepping_right(state)
        state.mobs.create(destination, 1, encode_hpos(11 * 16),
                          encode_vpos_at_y(10 * 16), MazeObjIds.HIDDENPOT)

        assert self._step(state) == 1
        assert state.mobs.obj_type(destination) == 0
        assert state.thief_mob_slot == start

        assert self._step(state) == 0
        assert state.thief_mob_slot == destination

    def test_a_transporter_is_walked_over_not_eaten(self):
        """Flag 0 and a 0x8001 marker picture: the cell neither blocks nor dies."""
        state = GameState()
        start, destination = self._thief_stepping_right(state)
        state.mobs.create(destination, 0x8001, encode_hpos(11 * 16),
                          encode_vpos_at_y(10 * 16), MazeObjIds.TRANSPORTER)

        assert self._step(state) == 0, "not blocked"
        assert state.mobs.obj_type(destination) == int(MazeObjIds.TRANSPORTER)
        assert state.mobs.picture[destination] == 0x8001
        assert state.thief_mob_slot == start, "an occupied cell keeps the slot"
        assert hpos_x(state.mobs.hpos[start]) == 11 * 16, "but the pixels move"

    def test_a_forcefield_hub_blocks_and_survives(self):
        """Flag 0 and the 0x8000 wall marker: solid, and still there after."""
        state = GameState()
        start, destination = self._thief_stepping_right(state)
        state.mobs.create(destination, 0x8000, encode_hpos(11 * 16),
                          encode_vpos_at_y(10 * 16), MazeObjIds.FORCEFIELDHUB)

        assert self._step(state) == 1, "blocked"
        assert state.mobs.obj_type(destination) == int(MazeObjIds.FORCEFIELDHUB)
        assert state.mobs.picture[destination] == 0x8000
        assert state.thief_mob_slot == start
        assert hpos_x(state.mobs.hpos[start]) == 10 * 16 + 12, "no pixels moved"

    def test_the_lookup_covers_every_object_type(self):
        """0x4F8EC indexes with a six-bit field, so all 64 have to resolve."""
        state = GameState()
        slot = pack_slot(10, 11)
        for obj_type in range(64):
            state.mobs.unlink_and_clear(slot)
            state.mobs.create(slot, 1, encode_hpos(11 * 16),
                              encode_vpos_at_y(10 * 16), obj_type)
            assert thief_handle_tile_collision(state, slot) in (0, -1)
