"""WP-5: player movement and collision helpers.

Acceptance criteria from PLAN.md §6 WP-5:
1. A player cannot enter a wall from any of the eight directions.
2. Diagonal movement into a corner: squeeze behaviour (one axis blocked, other clear).
3. A door with player.keysnum > 0 opens; without a key it does not.
4. mob_probe_up returns 0x0400 (boundary sentinel) at the top row.
5. Wraparound: with state.wrap_h = True a player at the right edge wraps left.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gauntpy.constants import (
    FIRST_PLAYABLE_SLOT,
    Character,
    GameMode,
    MazeObjIds,
    PlayerPower,
    PlayerStatus,
)
from gauntpy.coords import encode_vpos_at_y, hpos_x, native_v, vpos_y
from gauntpy.state import GameState, Player
from gauntpy.subsystems import players as gp
from gauntpy.subsystems.players import (
    _NO_MOVE,
    _VERTICAL_BOUNDARY,
    _WALL_PICTURE,
    corner_squeeze_geometry,
    mob_probe_down,
    mob_probe_left,
    mob_probe_right,
    mob_probe_up,
    player_try_move,
)
from gauntpy.subsystems import input as gin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WALL_PICTURE = 0x8000   # noqa: F811 -- re-export for clarity in tests


def _state_with_wall(wall_slot: int) -> GameState:
    """GameState with a single solid wall at wall_slot."""
    state = GameState()
    state.mobs.picture[wall_slot] = _WALL_PICTURE
    return state


def _active_player_at(state: GameState, player_index: int, slot: int) -> Player:
    """Place an active player at the given maze slot."""
    player = state.players[player_index]
    player.status = PlayerStatus.ALIVE_HERE
    player.mob_slot = slot
    # Exact player_start_inner geometry: the 24px sprite begins 4px left of its
    # 16px cell; the V word names the cell row.
    row = slot >> 5
    col = slot & 0x1F
    x = col * 16 - 4
    y = row * 16
    state.mobs.hpos[slot] = x << 7
    state.mobs.vpos[slot] = native_v(y) << 7
    # Geometry unit tests are about walls rather than the independent
    # player-offscreen flag. Dedicated tests below cover the screen gate.
    state.level_flags_4 |= 0x80
    return player


def test_pushing_a_movable_wall_into_an_exit_wins_trick_ten():
    wall = (5 << 5) | 5
    exit_slot = wall + 1
    state = GameState()
    state.secret_trick_id = 10
    state.mobs.create(
        wall,
        tile=0x20F6,
        hpos=5 * 16 << 7,
        vpos=encode_vpos_at_y(5 * 16),
        obj_type=int(MazeObjIds.WALL_MOVABLE),
    )
    state.mobs.create(
        exit_slot,
        tile=0x8001,
        hpos=6 * 16 << 7,
        vpos=encode_vpos_at_y(5 * 16),
        obj_type=int(MazeObjIds.EXIT),
    )

    assert gp._push_movable_wall(
        state, 2, wall, gp._JOY_RIGHT, vertical=False,
    )
    assert state.secret_winner == 2
    assert state.mobs.picture[wall] == 0


def test_pushing_a_movable_wall_into_a_transporter_dissolves_it():
    wall = (5 << 5) | 5
    transporter = wall + 1
    state = GameState()
    state.mobs.create(
        wall,
        tile=0x20F6,
        hpos=5 * 16 << 7,
        vpos=encode_vpos_at_y(5 * 16),
        obj_type=int(MazeObjIds.WALL_MOVABLE),
    )
    state.mobs.create(
        transporter,
        tile=0x8001,
        hpos=6 * 16 << 7,
        vpos=encode_vpos_at_y(5 * 16),
        obj_type=int(MazeObjIds.TRANSPORTER),
    )

    assert gp._push_movable_wall(
        state, 0, wall, gp._JOY_RIGHT, vertical=False,
    )
    assert state.mobs.picture[wall] == 0
    assert state.secret_winner == -1


# ---------------------------------------------------------------------------
# mob_probe_up
# ---------------------------------------------------------------------------

class TestMobProbeUp:
    def test_clear_above_returns_minus_one(self):
        state = GameState()
        result = mob_probe_up(state, (5 << 5) | 5)   # row 5, col 5
        assert result == -1

    def test_wall_directly_above_is_blocking(self):
        wall_slot = (4 << 5) | 5   # row 4, col 5
        state = _state_with_wall(wall_slot)
        result = mob_probe_up(
            state, (5 << 5) | 5, hpos=76 << 7, vpos=native_v(78) << 7,
        )
        assert result == wall_slot

    def test_top_row_returns_vertical_boundary_sentinel(self):
        """At row 0 the probe returns 0x0400, not -1 and not a slot (§4.2)."""
        state = GameState()
        result = mob_probe_up(state, (0 << 5) | 10)  # row 0
        assert result == _VERTICAL_BOUNDARY
        assert result != -1

    def test_left_flank_wall_is_detected(self):
        """A wall at (row-1, col-1) blocks the probe (three-candidate check)."""
        left_flank = (4 << 5) | 4
        state = _state_with_wall(left_flank)
        result = mob_probe_up(
            state, (5 << 5) | 5, hpos=74 << 7, vpos=native_v(78) << 7,
        )
        assert result == left_flank

    def test_right_flank_wall_is_detected(self):
        right_flank = (4 << 5) | 6
        state = _state_with_wall(right_flank)
        result = mob_probe_up(
            state, (5 << 5) | 5, hpos=78 << 7, vpos=native_v(78) << 7,
        )
        assert result == right_flank


# ---------------------------------------------------------------------------
# mob_probe_down
# ---------------------------------------------------------------------------

class TestMobProbeDown:
    def test_clear_below_returns_minus_one(self):
        state = GameState()
        assert mob_probe_down(state, (5 << 5) | 5) == -1

    def test_wall_below_is_blocking(self):
        wall_slot = (6 << 5) | 5
        state = _state_with_wall(wall_slot)
        assert mob_probe_down(
            state, (5 << 5) | 5, hpos=76 << 7, vpos=native_v(82) << 7,
        ) == wall_slot

    def test_bottom_row_returns_vertical_boundary_sentinel(self):
        state = GameState()
        result = mob_probe_down(state, (31 << 5) | 10)   # row 31 = last row
        assert result == _VERTICAL_BOUNDARY

    def test_flank_walls_detected(self):
        left_flank = (6 << 5) | 4
        state = _state_with_wall(left_flank)
        assert mob_probe_down(
            state, (5 << 5) | 5, hpos=74 << 7, vpos=native_v(82) << 7,
        ) == left_flank

    def test_high_bit_sprite_uses_its_live_marker_rounding_anchor(self):
        state = GameState()
        mover = (22 << 5) | 31
        door = (23 << 5) | 31
        state.mobs.create(
            door, tile=0x9D4C, hpos=0xF600, vpos=0x3011,
            obj_type=int(MazeObjIds.DOOR_HORIZ),
        )

        assert mob_probe_down(
            state, mover, hpos=0xF600, vpos=0x4700,
        ) == -1


# ---------------------------------------------------------------------------
# mob_probe_left
# ---------------------------------------------------------------------------

class TestMobProbeLeft:
    def test_clear_left_returns_minus_one(self):
        state = GameState()
        assert mob_probe_left(state, (5 << 5) | 5) == -1

    def test_wall_left_is_blocking(self):
        wall_slot = (5 << 5) | 4
        state = _state_with_wall(wall_slot)
        assert mob_probe_left(
            state, (5 << 5) | 5, hpos=74 << 7, vpos=native_v(80) << 7,
        ) == wall_slot

    def test_no_boundary_sentinel_at_left_edge(self):
        """Left/right probes return -1 (not 0x0400) at the maze edge (§4.2)."""
        state = GameState()
        result = mob_probe_left(state, (5 << 5) | 0)   # col 0
        assert result == -1
        assert result != _VERTICAL_BOUNDARY

    def test_flank_wall_detected(self):
        upper_flank = (4 << 5) | 4
        state = _state_with_wall(upper_flank)
        assert mob_probe_left(
            state, (5 << 5) | 5, hpos=74 << 7, vpos=native_v(78) << 7,
        ) == upper_flank

    def test_row_one_does_not_probe_the_reserved_top_row_as_a_flank(self):
        state = _state_with_wall((0 << 5) | 16)

        assert mob_probe_left(
            state, (1 << 5) | 17,
            hpos=266 << 7, vpos=native_v(15) << 7,
        ) == -1


# ---------------------------------------------------------------------------
# mob_probe_right
# ---------------------------------------------------------------------------

class TestMobProbeRight:
    def test_clear_right_returns_minus_one(self):
        state = GameState()
        assert mob_probe_right(state, (5 << 5) | 5) == -1

    def test_wall_right_is_blocking(self):
        wall_slot = (5 << 5) | 6
        state = _state_with_wall(wall_slot)
        assert mob_probe_right(
            state, (5 << 5) | 5, hpos=78 << 7, vpos=native_v(80) << 7,
        ) == wall_slot

    def test_no_boundary_sentinel_at_right_edge(self):
        state = GameState()
        result = mob_probe_right(state, (5 << 5) | 31)  # col 31
        assert result == -1

    def test_lower_flank_wall_detected(self):
        lower_flank = (6 << 5) | 6
        state = _state_with_wall(lower_flank)
        assert mob_probe_right(
            state, (5 << 5) | 5, hpos=78 << 7, vpos=native_v(82) << 7,
        ) == lower_flank

    def test_row_one_does_not_probe_the_reserved_top_row_as_a_flank(self):
        state = _state_with_wall((0 << 5) | 18)

        assert mob_probe_right(
            state, (1 << 5) | 17,
            hpos=270 << 7, vpos=native_v(15) << 7,
        ) == -1


# ---------------------------------------------------------------------------
# player_try_move -- wall collision (acceptance criterion 1)
# ---------------------------------------------------------------------------

class TestPlayerTryMoveWallCollision:
    """A player cannot enter a wall from any of the 8 directions (§4.2)."""

    def _player_at_slot(self, slot: int) -> tuple[GameState, int]:
        state = GameState()
        player = _active_player_at(state, 0, slot)
        return state, 0

    def test_blocked_up(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(4 << 5) | 5] = _WALL_PICTURE   # wall above
        y_before = vpos_y(state.mobs.vpos[state.players[pi].mob_slot])
        player_try_move(state, pi, gin.JOY_UP, 0)
        y_after = vpos_y(state.mobs.vpos[state.players[pi].mob_slot])
        assert y_after == y_before, "should not move into wall above"

    def test_row_one_player_boundary_ignores_cleared_reserved_mob_slots(self):
        state, pi = self._player_at_slot((1 << 5) | 10)
        slot = state.players[pi].mob_slot
        for reserved in range(FIRST_PLAYABLE_SLOT):
            state.mobs.picture[reserved] = 0
        state.mobs.vpos[slot] = encode_vpos_at_y(16, 3, 3)

        player_try_move(state, pi, gin.JOY_UP, 0)

        assert vpos_y(state.mobs.vpos[state.players[pi].mob_slot]) == 16

    def test_blocked_down(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(6 << 5) | 5] = _WALL_PICTURE
        y_before = vpos_y(state.mobs.vpos[state.players[pi].mob_slot])
        player_try_move(state, pi, gin.JOY_DOWN, 0)
        y_after = vpos_y(state.mobs.vpos[state.players[pi].mob_slot])
        assert y_after == y_before

    def test_blocked_left(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(5 << 5) | 4] = _WALL_PICTURE
        x_before = hpos_x(state.mobs.hpos[state.players[pi].mob_slot])
        player_try_move(state, pi, gin.JOY_LEFT, 0)
        x_after = hpos_x(state.mobs.hpos[state.players[pi].mob_slot])
        assert x_after == x_before

    def test_blocked_right(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(5 << 5) | 6] = _WALL_PICTURE
        x_before = hpos_x(state.mobs.hpos[state.players[pi].mob_slot])
        player_try_move(state, pi, gin.JOY_RIGHT, 0)
        x_after = hpos_x(state.mobs.hpos[state.players[pi].mob_slot])
        assert x_after == x_before

    def test_return_word_records_only_axes_that_actually_moved(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        assert player_try_move(
            state, pi, gin.JOY_RIGHT, 0,
        ) == 0xE0

        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(5 << 5) | 6] = _WALL_PICTURE
        assert player_try_move(
            state, pi, gin.JOY_RIGHT, 0,
        ) == 0xF0

    def test_movable_wall_pushes_one_pixel_with_the_player(self):
        from gauntpy.constants import MazeObjIds
        state, pi = self._player_at_slot((5 << 5) | 5)
        slot = (5 << 5) | 6
        state.mobs.create(slot, tile=0x20F6, hpos=92 << 7,
                          vpos=native_v(80) << 7,
                          obj_type=int(MazeObjIds.WALL_MOVABLE))
        x_before = hpos_x(state.mobs.hpos[state.players[pi].mob_slot])
        wall_before = hpos_x(state.mobs.hpos[slot])
        player_try_move(state, pi, gin.JOY_RIGHT, 0)
        assert hpos_x(state.mobs.hpos[state.players[pi].mob_slot]) == x_before
        assert hpos_x(state.mobs.hpos[slot]) == wall_before + 1

    def test_movable_wall_push_keeps_the_rom_zero_two_pixel_cadence(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.players[pi].character = Character.ELF
        slot = (5 << 5) | 6
        state.mobs.create(
            slot, tile=0x20F6, hpos=92 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.WALL_MOVABLE),
        )
        player_x = []
        wall_x = []

        for frame in range(6):
            state.frame_counter = frame
            state.movement_type = 2
            player_try_move(state, pi, gin.JOY_RIGHT, 0)
            player_x.append(hpos_x(state.mobs.hpos[state.players[pi].mob_slot]))
            wall_slot = next(
                candidate for candidate in range(32, 1024)
                if state.mobs.obj_type(candidate) == int(MazeObjIds.WALL_MOVABLE)
            )
            wall_x.append(hpos_x(state.mobs.hpos[wall_slot]))

        assert [b - a for a, b in zip(player_x, player_x[1:])] == [0, 2, 0, 0, 2]
        assert [b - a for a, b in zip(wall_x, wall_x[1:])] == [1, 0, 1, 1, 0]

    def test_it_player_tags_another_live_player_on_contact(self):
        state = GameState()
        it_slot = (5 << 5) | 5
        target_slot = (5 << 5) | 6
        it_player = _active_player_at(state, 0, it_slot)
        target = _active_player_at(state, 1, target_slot)
        state.mobs.create(
            it_slot, tile=0x1000, hpos=76 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART), state=0,
        )
        state.mobs.create(
            target_slot, tile=0x1000, hpos=92 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART), state=1,
        )
        it_player.mob_slot = it_slot
        target.mob_slot = target_slot
        state.player_it = 0
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.player_it == 1
        assert target.stundelay == 0x40
        assert 0x35 in state.sound_log

    def test_recursive_player_collision_does_not_transfer_it(self):
        state = GameState()
        it_slot = (5 << 5) | 5
        target_slot = (5 << 5) | 6
        it_player = _active_player_at(state, 0, it_slot)
        target = _active_player_at(state, 1, target_slot)
        state.mobs.create(
            it_slot, tile=0x1000, hpos=76 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART), state=0,
        )
        state.mobs.create(
            target_slot, tile=0x1000, hpos=92 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.PLAYERSTART), state=1,
        )
        it_player.mob_slot = it_slot
        target.mob_slot = target_slot
        state.player_it = 0
        state.movement_type = 1

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.player_it == 0
        assert target.stundelay == 0

    def test_returns_0x00f0_when_blocked(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(4 << 5) | 5] = _WALL_PICTURE
        result = player_try_move(state, pi, gin.JOY_UP, 0)
        assert result == _NO_MOVE

    def test_returns_non_0x00f0_when_moved(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        result = player_try_move(state, pi, gin.JOY_UP, 0)
        assert result != _NO_MOVE

    def test_position_updates_when_clear(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        y_before = vpos_y(state.mobs.vpos[state.players[pi].mob_slot])
        player_try_move(state, pi, gin.JOY_UP, 0)
        y_after = vpos_y(state.mobs.vpos[state.players[pi].mob_slot])
        assert y_after < y_before, "player should move up when clear"

    def test_flank_wall_does_not_block_parallel_empty_floor(self):
        """The three-cell probe is position-aware, not a whole-row barrier."""
        state, pi = self._player_at_slot((5 << 5) | 5)
        flank = (4 << 5) | 6
        state.mobs.picture[flank] = _WALL_PICTURE
        before = hpos_x(state.mobs.hpos[state.players[pi].mob_slot])

        assert player_try_move(state, pi, gin.JOY_RIGHT, 0) != _NO_MOVE
        assert hpos_x(state.mobs.hpos[state.players[pi].mob_slot]) > before

    def test_maze16_narrow_wall_lane_has_the_rom_alignment_escape(self):
        """Regression for the frame-10310 live-state report at (41, 288)."""
        state = GameState(game_mode=GameMode.NORMAL)
        player = _active_player_at(state, 0, (18 << 5) | 3)
        player.character = Character.ELF
        player.powers = int(PlayerPower.SPEED | PlayerPower.REFLECT)
        state.frame_counter = 10310
        state.mobs.hpos[player.mob_slot] = (41 << 7) | 0x0C
        state.mobs.vpos[player.mob_slot] = encode_vpos_at_y(288, 3, 3)
        for slot in ((17 << 5) | 2, (17 << 5) | 4):
            state.mobs.create(
                slot,
                tile=_WALL_PICTURE,
                hpos=(slot & 0x1F) * 16 << 7,
                vpos=encode_vpos_at_y((slot >> 5) * 16),
                obj_type=int(MazeObjIds.WALL_REGULAR),
                link_into_chain=False,
            )

        state.movement_type = 2
        assert player_try_move(state, 0, gin.JOY_UP, 0) == _NO_MOVE

        for direction in (gin.JOY_RIGHT, gin.JOY_RIGHT, gin.JOY_LEFT):
            state.movement_type = 2
            assert player_try_move(state, 0, direction, 0) != _NO_MOVE
            state.frame_counter += 1

        assert hpos_x(state.mobs.hpos[player.mob_slot]) == 44
        state.movement_type = 2
        assert player_try_move(state, 0, gin.JOY_UP, 0) != _NO_MOVE
        assert vpos_y(state.mobs.vpos[player.mob_slot]) == 285


# ---------------------------------------------------------------------------
# Diagonal partial movement (acceptance criterion 2)
# ---------------------------------------------------------------------------

class TestDiagonalMovement:
    """When one diagonal axis is blocked, movement continues on the other."""

    def test_diagonal_up_right_with_wall_above(self):
        """Wall above: up blocked, right clear → player moves right but not up."""
        state = GameState()
        player = _active_player_at(state, 0, (5 << 5) | 5)
        state.mobs.picture[(4 << 5) | 5] = _WALL_PICTURE  # wall directly above
        y_before = vpos_y(state.mobs.vpos[player.mob_slot])
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        player_try_move(state, 0, gin.JOY_UP | gin.JOY_RIGHT, 0)
        y_after = vpos_y(state.mobs.vpos[player.mob_slot])
        x_after = hpos_x(state.mobs.hpos[player.mob_slot])
        assert y_after == y_before, "should not move up into wall"
        assert x_after > x_before, "should still move right"

    def test_both_axes_blocked_returns_no_move(self):
        state = GameState()
        player = _active_player_at(state, 0, (5 << 5) | 5)
        state.mobs.picture[(4 << 5) | 5] = _WALL_PICTURE   # wall above
        state.mobs.picture[(5 << 5) | 6] = _WALL_PICTURE   # wall right
        result = player_try_move(state, 0, gin.JOY_UP | gin.JOY_RIGHT, 0)
        assert result == _NO_MOVE


class TestHandToHandGenerators:
    def _state(self, character=Character.WARRIOR, generator=MazeObjIds.GEN_GHOST1):
        state = GameState()
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.character = character
        slot = (5 << 5) | 6
        state.mobs.create(
            slot, tile=0x09AB, hpos=92 << 7, vpos=native_v(80) << 7,
            obj_type=int(generator),
        )
        return state, player, slot

    def test_collision_starts_fighting_and_blocks_movement(self):
        state, player, _slot = self._state()
        before = state.mobs.hpos[player.mob_slot]
        state.movement_type = 2

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert state.mobs.hpos[player.mob_slot] == before
        assert state.player_fighting_dir[0] == player.direction + 1

    def test_warrior_can_destroy_tier_one_generator(self):
        state, player, slot = self._state()
        state.movement_type = 2
        player_try_move(state, 0, gin.JOY_RIGHT, 0)  # arm fight
        state.rng = type("ZeroRng", (), {
            "getrandom": staticmethod(lambda _bound: 0),
        })()
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.mobs.picture[slot] == 0
        assert player.score == 10

    def test_wizard_cannot_fight_generators(self):
        state, player, slot = self._state(character=Character.WIZARD)
        state.movement_type = 2
        before = state.mobs.hpos[player.mob_slot]

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert state.mobs.hpos[player.mob_slot] == before
        assert state.player_fighting_dir[0] == 0
        assert state.mobs.picture[slot] != 0


class TestCharacterFightTables:
    """mob_collision_test 0x521AE-0x52438 table selection."""

    def test_fight_tables_match_the_rom(self):
        assert gp._HAND_POWER == (2, 2, 1, 1, 3, 3, 2, 2)
        assert gp._HAND_RANDOM == (0, 0, 0, 2)
        assert gp._GENERATOR_FIGHT_POWER == (3, 2, 0, 0, 4, 3, 0, 1)

    def test_extra_fight_power_selects_the_second_character_row(self):
        for character, powered, expected_damage in (
            (Character.WARRIOR, False, 2),
            (Character.VALKYRIE, False, 2),
            (Character.WIZARD, False, 1),
            (Character.ELF, False, 1),
            (Character.WARRIOR, True, 3),
            (Character.VALKYRIE, True, 3),
            (Character.WIZARD, True, 2),
            (Character.ELF, True, 2),
        ):
            state = GameState()
            player = _active_player_at(state, 0, (10 << 5) | 10)
            player.character = character
            player.powers = int(PlayerPower.FIGHT) if powered else 0
            slot = (10 << 5) | 11
            state.mobs.create(
                slot, tile=0x2000, hpos=(176 << 7) | 0x0B,
                vpos=native_v(160) << 7, obj_type=int(MazeObjIds.MONST_LOBBER),
            )
            state.player_fighting_dir[0] = 1
            state.rng = type("ZeroRng", (), {
                "getrandom": staticmethod(lambda _bound: 0),
            })()

            gp._player_fight_collision(state, 0, slot)

            remaining = (0x0B - expected_damage) & 0x0F
            if remaining < 9:
                assert state.mobs.obj_type(slot) == 0
            else:
                assert state.mobs.hpos[slot] & 0x0F == remaining


class TestLockedTreasureCollision:
    @staticmethod
    def _state(keys: int = 1) -> tuple[GameState, Player, int]:
        state = GameState()
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.keysnum = keys
        state.level_players_active = 1
        slot = (5 << 5) | 6
        state.mobs.create(
            slot, tile=0x25E4, hpos=92 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.TREASURE_LOCKED),
        )
        return state, player, slot

    def test_a_key_opens_the_chest_and_stuns_the_player(self):
        state, player, slot = self._state()
        state.rng = type("FixedRng", (), {
            "getrandom": staticmethod(lambda _bound: 0),
        })()
        state.movement_type = 2

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert player.keysnum == 0
        assert player.stundelay == 30
        assert state.mobs.obj_type(slot) == int(MazeObjIds.KEY)
        assert state.sound_log[-1] == 0x2A

    @pytest.mark.parametrize(("roll", "reward"), (
        (1, MazeObjIds.MONST_DEATH),
        (3, MazeObjIds.TREASURE_BAG),
        (7, MazeObjIds.POT_DESTRUCTABLE),
        (8, MazeObjIds.FOOD_DESTRUCTABLE),
    ))
    def test_reward_table_matches_the_rom(self, roll, reward):
        state, _player, slot = self._state()
        state.rng = type("FixedRng", (), {
            "getrandom": staticmethod(lambda _bound: roll),
        })()
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.mobs.obj_type(slot) == int(reward)

    def test_demo_always_reveals_coins(self):
        state, _player, slot = self._state()
        state.game_mode = int(GameMode.DEMO)
        state.rng = type("FixedRng", (), {
            "getrandom": staticmethod(lambda _bound: 1),
        })()
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.mobs.obj_type(slot) == int(MazeObjIds.TREASURE_BAG)

    def test_without_a_key_the_chest_remains_and_shows_the_hint(self):
        state, player, slot = self._state(keys=0)
        state.movement_type = 2

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert player.keysnum == 0
        assert state.mobs.obj_type(slot) == int(MazeObjIds.TREASURE_LOCKED)
        assert state.dialog_first_encounter_flags & (1 << 27)


class TestFloorTriggers:
    def test_trap_drops_its_wall_group_without_stunning(self):
        state = GameState()
        player = _active_player_at(state, 0, (8 << 5) | 3)
        trigger = (8 << 5) | 4
        wall = (8 << 5) | 5
        other_trigger = (9 << 5) | 4
        for slot, kind, picture in (
            (trigger, MazeObjIds.TILE_TRAP1, 0x8001),
            (wall, MazeObjIds.WALL_TRAPCYC1, 0x8000),
            (other_trigger, MazeObjIds.TILE_TRAP1, 0x8001),
        ):
            state.mobs.create(
                slot, tile=picture, hpos=0, vpos=0,
                obj_type=int(kind), link_into_chain=False,
            )
        state.maze = SimpleNamespace(data={
            (4, 8): int(MazeObjIds.TILE_TRAP1),
            (5, 8): int(MazeObjIds.WALL_TRAPCYC1),
            (4, 9): int(MazeObjIds.TILE_TRAP1),
        })

        assert gp.player_tile_interact(state, trigger, 0) == -1

        assert player.stundelay == 0
        assert all(state.mobs.picture[slot] == 0 for slot in (
            trigger, wall, other_trigger,
        ))
        assert set(state.maze.data.values()) == {int(MazeObjIds.TILE_FLOOR)}
        assert 0x27 in state.sound_log
        assert state.dialog_first_encounter_flags & (1 << 23)

    @pytest.mark.parametrize(("character", "delay", "sound"), (
        (Character.WARRIOR, 120, 0x32),
        (Character.VALKYRIE, 45, 0x34),
        (Character.WIZARD, 120, 0x32),
        (Character.ELF, 60, 0x33),
    ))
    def test_stun_floor_uses_character_table(self, character, delay, sound):
        state = GameState()
        player = _active_player_at(state, 0, (8 << 5) | 3)
        player.character = int(character)
        tile = (8 << 5) | 4
        state.mobs.create(
            tile, tile=0x8001, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.TILE_STUN), link_into_chain=False,
        )

        assert gp.player_tile_interact(state, tile, 0) == -1

        assert player.stundelay == delay
        assert state.death_touch_timer[0] == -delay
        assert state.mobs.picture[tile] == 0
        assert sound in state.sound_log
        assert state.dialog_first_encounter_flags & (1 << 26)


class TestMobCollisionDispatch:
    def test_pass_through_marker_does_not_trigger_from_the_adjacent_cell(self):
        state = GameState()
        state.game_mode = int(GameMode.NORMAL)
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.health = 500
        state.mobs.hpos[player.mob_slot] = 156 << 7
        state.mobs.vpos[player.mob_slot] = native_v(160) << 7
        state.player_tile_pos[0] = (10 << 5) | 10
        marker = (10 << 5) | 11
        state.mobs.create(
            marker, tile=0x8001, hpos=0, vpos=0,
            obj_type=int(MazeObjIds.TILE_STUN), link_into_chain=False,
        )
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert player.stundelay == 0
        assert state.mobs.picture[marker] == 0x8001

    def test_nonconsumed_pickup_fires_only_on_the_cell_entry_edge(self):
        state = GameState()
        state.game_mode = int(GameMode.NORMAL)
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.health = 500
        state.mobs.hpos[player.mob_slot] = 156 << 7
        state.mobs.vpos[player.mob_slot] = native_v(160) << 7
        state.player_tile_pos[0] = (10 << 5) | 10
        potion = (10 << 5) | 11
        state.mobs.create(
            potion, tile=0x89FC, hpos=176 << 7, vpos=native_v(160) << 7,
            obj_type=int(MazeObjIds.POT_INVULN),
        )
        state.player_input_raw[0] = 0xFFFF & ~gin.JOY_RIGHT

        for _ in range(40):
            gp.main_move_players(state)

        assert player.potionsnum == 1
        assert state.mobs.picture[potion] == 0

    def test_death_is_not_melee_killed(self):
        state = GameState()
        _active_player_at(state, 0, (10 << 5) | 10)
        slot = (10 << 5) | 11
        state.mobs.create(
            slot, tile=0x1A75, hpos=176 << 7,
            vpos=native_v(160) << 7, obj_type=int(MazeObjIds.MONST_DEATH),
        )
        state.player_fighting_dir[0] = 1

        assert gp._player_fight_collision(state, 0, slot) == 0
        assert state.mobs.picture[slot] != 0
        assert state.players[0].score == 0

    def test_fighting_super_sorcerer_stays_put_and_blocks(self):
        state = GameState()
        _active_player_at(state, 0, (10 << 5) | 10)
        slot = (10 << 5) | 11
        state.mobs.create(
            slot, tile=0x1A75, hpos=(176 << 7) | 0x2B,
            vpos=native_v(160) << 7, obj_type=int(MazeObjIds.MONST_SUPERSORC),
        )

        assert gp._player_fight_collision(state, 0, slot) == 0
        assert state.mobs.picture[slot] != 0
        assert state.mobs.hpos[slot] & 0x30 == 0x20

    def test_invisible_sorcerer_reveals_without_taking_melee_damage(self):
        state = GameState()
        _active_player_at(state, 0, (10 << 5) | 10)
        slot = (10 << 5) | 11
        state.mobs.create(
            slot, tile=0x1E13, hpos=(176 << 7) | 0x1B,
            vpos=native_v(160) << 7, obj_type=int(MazeObjIds.MONST_SORC),
        )
        state.player_fighting_dir[0] = 1

        assert gp._player_fight_collision(state, 0, slot) == 1
        assert state.mobs.hpos[slot] & 0x0F == 0x0B
        assert not state.mobs.hpos[slot] & 0x10
        assert state.players[0].score == 0

    def test_zero_random_hand_damage_still_advances_the_shared_rng(self):
        state = GameState()
        _active_player_at(state, 0, (10 << 5) | 10)
        slot = (10 << 5) | 11
        state.mobs.create(
            slot, tile=0x2000, hpos=(176 << 7) | 4,
            vpos=native_v(160) << 7, obj_type=int(MazeObjIds.MONST_GRUNT),
        )
        state.player_fighting_dir[0] = 1
        seed_before = state.rng.seed

        gp._player_fight_collision(state, 0, slot)

        assert state.rng.seed != seed_before

    def test_demo_actor_uses_normal_monster_melee(self):
        state = GameState(game_mode=GameMode.DEMO)
        _active_player_at(state, 0, (10 << 5) | 10)
        state.demo_active_player = 0
        state.movement_type = 1
        slot = (10 << 5) | 11
        state.mobs.create(
            slot, tile=0x2000, hpos=(176 << 7) | 4,
            vpos=native_v(160) << 7, obj_type=int(MazeObjIds.MONST_GRUNT),
        )

        assert gp._player_fight_collision(state, 0, slot) == 1
        assert state.player_fighting_dir[0] != 0

    def test_two_pixel_frame_latches_acid_only_once(self):
        state = GameState(game_mode=GameMode.NORMAL)
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.health = 1000
        state.mobs.hpos[player.mob_slot] = 81 << 7
        acid = (5 << 5) | 6
        state.mobs.create(
            acid, tile=0x2300, hpos=(92 << 7) | 1,
            vpos=native_v(80) << 7, obj_type=int(MazeObjIds.MONST_ACID),
        )
        state.frame_counter = 1  # Warrior's +1 px animation boost: 2 px total.
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert player.health == 1000
        assert player.stundelay == 0x20
        assert state.mobs.picture[acid] != 0
        assert player.mob_slot == (5 << 5) | 5
        assert gp._player_record_cell(state, 0) == player.mob_slot

    def test_diagonal_frame_keeps_one_contact_per_axis(self):
        state = GameState(game_mode=GameMode.NORMAL)
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.health = 1000
        state.mobs.hpos[player.mob_slot] = 80 << 7
        state.mobs.vpos[player.mob_slot] = native_v(81) << 7
        acid = (6 << 5) | 6
        state.mobs.create(
            acid, tile=0x2300, hpos=(92 << 7) | 1,
            vpos=native_v(96) << 7, obj_type=int(MazeObjIds.MONST_ACID),
        )
        state.frame_counter = 1
        state.movement_type = 2

        player_try_move(
            state, 0, gin.JOY_RIGHT | gin.JOY_DOWN, 0,
        )

        assert player.health < 1000
        assert state.mobs.picture[acid] == 0

    def test_fighting_thief_removes_it_and_pays_the_bounty(self):
        state = GameState()
        _active_player_at(state, 0, (10 << 5) | 10)
        slot = (10 << 5) | 11
        state.mobs.create(
            slot, tile=0x0F09, hpos=(176 << 7) | 1,
            vpos=native_v(160) << 7, obj_type=int(MazeObjIds.PLAYERSTART),
        )
        state.thief_mob_slot = slot
        state.thief_current_pos = slot
        state.player_fighting_dir[0] = 1

        assert gp._player_fight_collision(state, 0, slot) == -1
        assert state.mobs.obj_type(slot) != int(MazeObjIds.PLAYERSTART)
        assert state.thief_mob_slot == 0
        assert state.players[0].score == 500

    def test_pass_through_item_does_not_hide_a_flank_wall(self):
        state = GameState(game_mode=GameMode.NORMAL)
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.health = 500
        state.mobs.hpos[player.mob_slot] = 81 << 7
        state.mobs.vpos[player.mob_slot] = native_v(84) << 7
        key = (5 << 5) | 6
        wall = (6 << 5) | 6
        state.mobs.create(
            key, tile=0x8AFC, hpos=96 << 7, vpos=native_v(80) << 7,
            obj_type=int(MazeObjIds.KEY),
        )
        state.mobs.create(
            wall, tile=0x8000, hpos=96 << 7, vpos=native_v(96) << 7,
            obj_type=int(MazeObjIds.WALL_REGULAR), link_into_chain=False,
        )
        state.movement_type = 2

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert hpos_x(state.mobs.hpos[player.mob_slot]) == 81


# ---------------------------------------------------------------------------
# Invulnerable corner squeeze (I-02, ROM 0x42744 / 0x4FEB2)
# ---------------------------------------------------------------------------

class TestCornerSqueezeGeometry:
    _POWER_INVULN = 1 << 11

    def test_invulnerable_player_squeezes_past_flank_wall(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.powers = self._POWER_INVULN
        flank_wall = (9 << 5) | 11
        state.mobs.picture[flank_wall] = _WALL_PICTURE
        state.mobs.set_obj_type(flank_wall, int(MazeObjIds.WALL_REGULAR))
        # Near the upper-right corner, an upward probe overlaps the diagonal
        # wall even though the cell directly above is clear.
        state.mobs.hpos[player.mob_slot] = 170 << 7
        state.movement_type = 2

        result = player_try_move(state, 0, gin.JOY_UP, 0)

        assert result != _NO_MOVE
        assert state.player_tile_pos[0] == ((8 << 5) | 11)
        assert state.sound_log[-1] == 0x28

    def test_invulnerable_player_phases_through_one_cell_wall(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.powers = self._POWER_INVULN
        wall = (10 << 5) | 11
        state.mobs.picture[wall] = _WALL_PICTURE
        state.mobs.set_obj_type(wall, int(MazeObjIds.WALL_REGULAR))
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.player_tile_pos[0] == ((10 << 5) | 12)

    def test_transport_can_land_on_and_remove_the_second_wall(self):
        from types import SimpleNamespace

        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.powers = self._POWER_INVULN
        first = (10 << 5) | 11
        landing = (10 << 5) | 12
        state.maze = SimpleNamespace(data={
            (11, 10): int(MazeObjIds.WALL_REGULAR),
            (12, 10): int(MazeObjIds.WALL_REGULAR),
        })
        for slot in (first, landing):
            state.mobs.create(
                slot, tile=_WALL_PICTURE, hpos=(slot & 31) * 16 << 7,
                vpos=native_v((slot >> 5) * 16) << 7,
                obj_type=int(MazeObjIds.WALL_REGULAR), link_into_chain=False,
            )
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        assert state.player_tport_type[0] == 0
        assert state.player_tile_pos[0] == landing

        gp.tport_player_move(state, 0)

        assert player.mob_slot == landing
        assert state.mobs.picture[first] == _WALL_PICTURE
        assert state.maze.data[(12, 10)] == int(MazeObjIds.TILE_FLOOR)

    def test_transport_skips_an_item_instead_of_collecting_it(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.powers = self._POWER_INVULN
        key = (10 << 5) | 11
        state.mobs.create(
            key, tile=0x8AFC, hpos=11 * 16 << 7,
            vpos=native_v(10 * 16) << 7, obj_type=int(MazeObjIds.KEY),
        )
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.player_tile_pos[0] == ((10 << 5) | 12)
        assert state.mobs.obj_type(key) == int(MazeObjIds.KEY)
        assert player.keysnum == 0

    def test_transport_landing_on_an_item_collects_it(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.powers = self._POWER_INVULN
        wall = (10 << 5) | 11
        key = (10 << 5) | 12
        state.mobs.create(
            wall, tile=_WALL_PICTURE, hpos=11 * 16 << 7,
            vpos=native_v(10 * 16) << 7,
            obj_type=int(MazeObjIds.WALL_REGULAR), link_into_chain=False,
        )
        state.mobs.create(
            key, tile=0x8AFC, hpos=12 * 16 << 7,
            vpos=native_v(10 * 16) << 7, obj_type=int(MazeObjIds.KEY),
        )
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        gp.tport_player_move(state, 0)

        assert player.mob_slot == key
        assert player.keysnum == 1

    def test_squeeze_is_disabled_on_recursive_movement_pass(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.powers = self._POWER_INVULN
        wall = (10 << 5) | 11
        state.mobs.picture[wall] = _WALL_PICTURE
        state.mobs.set_obj_type(wall, int(MazeObjIds.WALL_REGULAR))
        state.movement_type = 1

        result = player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert result == _NO_MOVE
        assert state.player_tile_pos[0] == 0

    def test_transporter_destination_rejects_squeeze(self):
        state = GameState()
        _active_player_at(state, 0, (10 << 5) | 10)
        wall = (10 << 5) | 11
        transporter = (10 << 5) | 12
        state.mobs.picture[wall] = _WALL_PICTURE
        state.mobs.set_obj_type(wall, int(MazeObjIds.WALL_REGULAR))
        state.mobs.picture[transporter] = 1
        state.mobs.set_obj_type(transporter, int(MazeObjIds.TRANSPORTER))

        result = corner_squeeze_geometry(
            state, (10 << 5) | 10, 0, gin.JOY_RIGHT,
        )

        assert result == 0
        assert state.player_tile_pos[0] == 0

    def test_top_border_squeeze_advances_through_wrapped_row(self):
        state = GameState(wrap_v=True)
        player = _active_player_at(state, 0, (1 << 5) | 10)
        state.mobs.vpos[player.mob_slot] |= 0x12
        player.powers = self._POWER_INVULN
        wall = (0 << 5) | 10
        state.mobs.picture[wall] = _WALL_PICTURE
        state.mobs.set_obj_type(wall, int(MazeObjIds.WALL_REGULAR))
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_UP, 0)

        assert state.player_tile_pos[0] == ((31 << 5) | 10)

    def test_left_border_squeeze_cannot_cross_an_offscreen_seam(self):
        state = GameState(wrap_h=False, scroll_x=0, scroll_y=10 * 16)
        player = _active_player_at(state, 0, (10 << 5) | 0)
        state.level_flags_4 &= ~0x80
        player.powers = self._POWER_INVULN
        wall = (10 << 5) | 31
        state.mobs.picture[wall] = _WALL_PICTURE
        state.mobs.set_obj_type(wall, int(MazeObjIds.WALL_REGULAR))
        state.movement_type = 2

        result = corner_squeeze_geometry(
            state, player.mob_slot, 0, gin.JOY_LEFT,
        )

        assert result == 0
        assert state.player_tport_phase[0] < 0
        assert player.mob_slot == ((10 << 5) | 0)


class TestThiefRouteTracking:
    def test_crossing_cell_records_victim_route(self):
        from gauntpy.subsystems.thief import path_grid_get_direction

        state = GameState()
        start = (10 << 5) | 10
        player = _active_player_at(state, 0, start)
        state.thief_victim = 0
        state.thief_victim_pos = start

        for _ in range(16):
            player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert hpos_x(state.mobs.hpos[player.mob_slot]) == 172
        assert state.thief_victim_pos == ((10 << 5) | 11)
        assert path_grid_get_direction(state, start) == 2


# ---------------------------------------------------------------------------
# Door traversal (acceptance criterion 3)
# ---------------------------------------------------------------------------

class TestDoorTraversal:
    def _state_with_door(self, door_slot: int) -> GameState:
        state = GameState()
        state.mobs.link[door_slot] = (int(MazeObjIds.DOOR_HORIZ) << 10) | 0
        state.mobs.picture[door_slot] = 1   # non-zero, non-wall → door
        return state

    def test_door_opens_with_key(self):
        """Player with a key can traverse a door (key consumed, door cleared)."""
        door_slot = (4 << 5) | 5
        state = self._state_with_door(door_slot)
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.keysnum = 1
        y_before = vpos_y(state.mobs.vpos[player.mob_slot])
        result = player_try_move(state, 0, gin.JOY_UP, 0)
        assert result != _NO_MOVE, "should be able to move through opened door"
        assert state.players[0].keysnum == 0, "key should be consumed"

    def test_door_blocked_without_key(self):
        """Player without a key cannot traverse a door."""
        door_slot = (4 << 5) | 5
        state = self._state_with_door(door_slot)
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.keysnum = 0
        result = player_try_move(state, 0, gin.JOY_UP, 0)
        assert result == _NO_MOVE, "should not traverse door without key"
        assert state.players[0].keysnum == 0, "key count unchanged"

    def test_walking_through_a_door_starts_wp11s_opening_fronts(self):
        """Traversal and tile interaction share the same unlock (0x51E80).

        The key opens the whole door line, not just the cell walked into: the
        two front records at 0x904A76/0x904A86 are seeded for this player's
        channel pair and ``main_open_doors`` walks them from there.
        """
        door_slot = (4 << 5) | 5
        state = self._state_with_door(door_slot)
        for neighbour in (door_slot - 1, door_slot + 1):
            state.mobs.create(neighbour, tile=0x9D3C, hpos=0, vpos=0,
                              obj_type=int(MazeObjIds.DOOR_HORIZ))
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.keysnum = 1
        state.escape_timer = 4000

        player_try_move(state, 0, gin.JOY_UP, 0)

        assert state.door_endpoint_dir[0:2] == [3, 1]
        assert state.door_endpoint_pos[0:2] == [door_slot - 1, door_slot + 1]
        assert not state.mobs.is_occupied(door_slot - 1)
        assert not state.mobs.is_occupied(door_slot + 1)
        assert 0x12 in state.sound_log
        assert state.escape_timer == 0

    def test_opened_door_updates_the_rendered_maze_descriptor(self):
        from types import SimpleNamespace

        door_slot = (4 << 5) | 5
        state = self._state_with_door(door_slot)
        state.maze = SimpleNamespace(
            data={(5, 4): int(MazeObjIds.DOOR_HORIZ)}
        )
        player = _active_player_at(state, 0, (5 << 5) | 5)
        player.keysnum = 1

        player_try_move(state, 0, gin.JOY_UP, 0)

        assert state.maze.data[(5, 4)] == int(MazeObjIds.TILE_FLOOR)


class TestPlayerScreenWindow:
    def _state(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        state.level_flags_4 &= ~0x80
        # Put the ROM screen origins at x=100, y=80.
        state.scroll_x = 108
        state.scroll_y = 80
        return state, player

    def test_player_cannot_walk_under_the_hud(self):
        state, player = self._state()
        state.mobs.hpos[player.mob_slot] = ((100 + 207) << 7)
        before = state.mobs.hpos[player.mob_slot]

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert state.mobs.hpos[player.mob_slot] == before

    def test_player_cannot_walk_past_the_bottom_screen_edge(self):
        state, player = self._state()
        state.mobs.vpos[player.mob_slot] = (native_v(80 + 232) << 7)
        before = state.mobs.vpos[player.mob_slot]

        assert player_try_move(state, 0, gin.JOY_DOWN, 0) == _NO_MOVE
        assert state.mobs.vpos[player.mob_slot] == before

    def test_player_offscreen_flag_bypasses_both_screen_edges(self):
        state, player = self._state()
        state.level_flags_4 |= 0x80
        state.mobs.hpos[player.mob_slot] = ((100 + 207) << 7)
        state.mobs.vpos[player.mob_slot] = (native_v(80 + 231) << 7)

        assert player_try_move(
            state, 0, gin.JOY_RIGHT | gin.JOY_DOWN, 0
        ) != _NO_MOVE


# ---------------------------------------------------------------------------
# Vertical boundary sentinel (acceptance criterion 4)
# ---------------------------------------------------------------------------

class TestVerticalBoundarySentinel:
    def test_probe_up_at_top_row_returns_0x0400(self):
        """mob_probe_up at row 0 returns the boundary sentinel 0x0400 (§4.2)."""
        state = GameState()
        result = mob_probe_up(state, (0 << 5) | 15)
        assert result == _VERTICAL_BOUNDARY
        assert result != -1       # NOT the "clear" sentinel
        assert result >= 0        # not negative

    def test_probe_down_at_bottom_row_returns_0x0400(self):
        state = GameState()
        result = mob_probe_down(state, (31 << 5) | 15)
        assert result == _VERTICAL_BOUNDARY


# ---------------------------------------------------------------------------
# Wraparound (acceptance criterion 5)
# ---------------------------------------------------------------------------

class TestWraparound:
    def test_horizontal_wraparound_from_right_edge(self):
        """With wrap_h, moving right from col 31 lands at col 0 (§4.2)."""
        state = GameState()
        state.wrap_h = True
        player = _active_player_at(state, 0, (10 << 5) | 31)  # rightmost column
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        # Move right many times to cross the boundary
        for _ in range(24):
            player_try_move(state, 0, gin.JOY_RIGHT, 0)
        x_after = hpos_x(state.mobs.hpos[player.mob_slot])
        # With wrap, position should be small (wrapped around)
        assert x_after < x_before, "x should have wrapped around"

    def test_no_wraparound_without_flag(self):
        """Without wrap_h, movement is clamped at the right edge."""
        state = GameState()
        state.wrap_h = False
        player = _active_player_at(state, 0, (10 << 5) | 31)
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        for _ in range(20):
            player_try_move(state, 0, gin.JOY_RIGHT, 0)
        x_after = hpos_x(state.mobs.hpos[player.mob_slot])
        assert x_after >= x_before, "should not go negative when wrap disabled"


# ---------------------------------------------------------------------------
# Raw-input → direction_bits → player_try_move (regression for the §3.11 bug)
# ---------------------------------------------------------------------------

class TestRawInputBitLayout:
    """Directions live in raw-word bits 4-7 (05_data_reference.md §3.11).

    The other movement tests pass JOY_* straight to player_try_move and so
    never exercise the raw-word decode; these drive the real hardware path,
    where UP/DOWN at the wrong bits (spare lines 2-3) or LEFT/RIGHT swapped
    would silently fail.
    """

    def test_bit_layout_matches_data_reference(self):
        assert gin.JOY_RIGHT == 0x10   # bit 4
        assert gin.JOY_LEFT == 0x20    # bit 5
        assert gin.JOY_DOWN == 0x40    # bit 6
        assert gin.JOY_UP == 0x80      # bit 7

    def test_raw_up_press_moves_player_up(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        y_before = vpos_y(state.mobs.vpos[player.mob_slot])
        # Active low: clear bit 7 (UP) in the raw word.
        state.player_input_raw[0] = 0xFFFF & ~gin.JOY_UP
        player_try_move(state, 0, gin.direction_bits(state, 0), 0)
        y_after = vpos_y(state.mobs.vpos[player.mob_slot])
        assert y_after < y_before, "raw UP press (bit 7) must move the player up"

    def test_raw_right_press_moves_player_right(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        state.player_input_raw[0] = 0xFFFF & ~gin.JOY_RIGHT   # clear bit 4
        player_try_move(state, 0, gin.direction_bits(state, 0), 0)
        x_after = hpos_x(state.mobs.hpos[player.mob_slot])
        assert x_after > x_before, "raw RIGHT press (bit 4) must move the player right"

    def test_spare_bits_do_not_move_player(self):
        """Clearing the spare lines (bits 2-3) must not cause movement."""
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        y_before = vpos_y(state.mobs.vpos[player.mob_slot])
        state.player_input_raw[0] = 0xFFFF & ~0x0C   # clear bits 2 and 3
        player_try_move(state, 0, gin.direction_bits(state, 0), 0)
        assert hpos_x(state.mobs.hpos[player.mob_slot]) == x_before
        assert vpos_y(state.mobs.vpos[player.mob_slot]) == y_before


class TestPerCharacterSpeed:
    """ROM 0x80/0x100 are 1 and 2 px in the native position words."""

    def _step_right(self, character: int, powers: int = 0) -> int:
        from gauntpy.constants import Character  # noqa: F401
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.character = character
        player.powers = powers
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        return hpos_x(state.mobs.hpos[player.mob_slot]) - x_before

    def test_warrior_moves_one_pixel(self):
        assert self._step_right(0) == 1

    def test_elf_moves_two_pixels(self):
        assert self._step_right(3) == 2

    def test_speed_power_doubles_warrior(self):
        assert self._step_right(0, powers=0x01) == 2


# ---------------------------------------------------------------------------
# Speed: player_speed_normal (0x580A8) x player_anim_rate (0x580B8)
# ---------------------------------------------------------------------------

class TestPlayerSpeedTables:
    """main_move_players 0x4A920-0x4A962 builds D3 from two parallel tables."""

    def test_tables_match_the_rom_image(self):
        assert gp._PLAYER_SPEED_NORMAL == [
            0x80, 0x80, 0x80, 0x100, 0x100, 0x100, 0x100, 0x100,
        ]
        assert gp._PLAYER_ANIM_RATE == [1, 3, 1, 0, 0, 0, 0, 1]

    def test_warrior_boosts_on_odd_frames(self):
        """anim_rate 1 & frame_counter -> +0x80 on every odd frame."""
        state = GameState()
        p = state.players[0]
        p.character = int(Character.WARRIOR)
        state.frame_counter = 0
        assert gp._player_speed_units(state, p) == 0x80
        state.frame_counter = 1
        assert gp._player_speed_units(state, p) == 0x100

    def test_valkyrie_boosts_on_three_frames_in_four(self):
        state = GameState()
        p = state.players[0]
        p.character = int(Character.VALKYRIE)
        boosted = 0
        for frame in range(4):
            state.frame_counter = frame
            if gp._player_speed_units(state, p) == 0x100:
                boosted += 1
        assert boosted == 3          # anim_rate 3 masks frames 1, 2, 3

    def test_elf_never_boosts_at_base_speed(self):
        state = GameState()
        p = state.players[0]
        p.character = int(Character.ELF)
        for frame in range(8):
            state.frame_counter = frame
            assert gp._player_speed_units(state, p) == 0x100

    def test_speed_power_swaps_the_halves(self):
        """With POWER_SPEED only the Elf keeps a non-zero anim rate."""
        state = GameState()
        p = state.players[0]
        p.powers = gp._POWER_SPEED
        state.frame_counter = 1
        p.character = int(Character.WARRIOR)
        assert gp._player_speed_units(state, p) == 0x100
        p.character = int(Character.ELF)
        assert gp._player_speed_units(state, p) == 0x180

    def test_special_mazes_run_everyone_at_converted_0x100(self):
        state = GameState()
        state.mazenum_current = gp._SPECIAL_MAZE_FIRST
        p = state.players[0]
        p.character = int(Character.WARRIOR)
        state.frame_counter = 1
        assert gp._player_speed_units(state, p) == 0x100

    def test_two_pixel_step_cannot_stop_inside_a_wall_and_block_sliding(self):
        state = GameState(game_mode=GameMode.NORMAL)
        player = _active_player_at(state, 0, (4 << 5) | 4)
        player.character = int(Character.WARRIOR)
        state.mobs.hpos[player.mob_slot] = 60 << 7
        state.mobs.vpos[player.mob_slot] = native_v(65) << 7
        for col in range(1, 14):
            slot = (8 << 5) | col
            state.mobs.create(
                slot, tile=_WALL_PICTURE, hpos=0, vpos=0,
                obj_type=int(MazeObjIds.WALL_REGULAR),
                link_into_chain=False,
            )

        for _ in range(80):
            state.movement_type = 2
            player_try_move(state, 0, gin.JOY_DOWN, 0)
            state.frame_counter += 1

        assert vpos_y(state.mobs.vpos[player.mob_slot]) == 112
        x_before = hpos_x(state.mobs.hpos[player.mob_slot])
        for _ in range(8):
            state.movement_type = 2
            player_try_move(state, 0, gin.JOY_DOWN | gin.JOY_RIGHT, 0)
            state.frame_counter += 1
        assert hpos_x(state.mobs.hpos[player.mob_slot]) > x_before
        assert vpos_y(state.mobs.vpos[player.mob_slot]) == 112

    def test_boost_reaches_player_try_move(self):
        """A boosted Warrior frame moves 2 px, an unboosted one 1 px."""
        state = GameState()
        _active_player_at(state, 0, (5 << 5) | 5)
        state.frame_counter = 0
        x0 = hpos_x(state.mobs.hpos[state.players[0].mob_slot])
        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        assert (hpos_x(state.mobs.hpos[state.players[0].mob_slot])) - x0 == 1

        state = GameState()
        _active_player_at(state, 0, (5 << 5) | 5)
        state.frame_counter = 1
        x0 = hpos_x(state.mobs.hpos[state.players[0].mob_slot])
        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        assert (hpos_x(state.mobs.hpos[state.players[0].mob_slot])) - x0 == 2
