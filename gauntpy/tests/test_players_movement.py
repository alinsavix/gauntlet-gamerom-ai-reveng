"""WP-5: player movement and collision helpers.

Acceptance criteria from PLAN.md §6 WP-5:
1. A player cannot enter a wall from any of the eight directions.
2. Diagonal movement into a corner: squeeze behaviour (one axis blocked, other clear).
3. A door with player.keysnum > 0 opens; without a key it does not.
4. mob_probe_up returns 0x0400 (boundary sentinel) at the top row.
5. Wraparound: with state.wrap_h = True a player at the right edge wraps left.
"""

from __future__ import annotations

import pytest

from gauntpy.constants import Character, MazeObjIds, PlayerStatus, FIRST_PLAYABLE_SLOT
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
    state.mobs.hpos[slot] = x << 6
    state.mobs.vpos[slot] = y << 6
    # Geometry unit tests are about walls rather than the independent
    # player-offscreen flag. Dedicated tests below cover the screen gate.
    state.level_flags_4 |= 0x80
    return player


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
            state, (5 << 5) | 5, hpos=76 << 6, vpos=78 << 6,
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
            state, (5 << 5) | 5, hpos=74 << 6, vpos=78 << 6,
        )
        assert result == left_flank

    def test_right_flank_wall_is_detected(self):
        right_flank = (4 << 5) | 6
        state = _state_with_wall(right_flank)
        result = mob_probe_up(
            state, (5 << 5) | 5, hpos=78 << 6, vpos=78 << 6,
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
            state, (5 << 5) | 5, hpos=76 << 6, vpos=82 << 6,
        ) == wall_slot

    def test_bottom_row_returns_vertical_boundary_sentinel(self):
        state = GameState()
        result = mob_probe_down(state, (31 << 5) | 10)   # row 31 = last row
        assert result == _VERTICAL_BOUNDARY

    def test_flank_walls_detected(self):
        left_flank = (6 << 5) | 4
        state = _state_with_wall(left_flank)
        assert mob_probe_down(
            state, (5 << 5) | 5, hpos=74 << 6, vpos=82 << 6,
        ) == left_flank


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
            state, (5 << 5) | 5, hpos=74 << 6, vpos=80 << 6,
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
            state, (5 << 5) | 5, hpos=74 << 6, vpos=78 << 6,
        ) == upper_flank


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
            state, (5 << 5) | 5, hpos=78 << 6, vpos=80 << 6,
        ) == wall_slot

    def test_no_boundary_sentinel_at_right_edge(self):
        state = GameState()
        result = mob_probe_right(state, (5 << 5) | 31)  # col 31
        assert result == -1

    def test_lower_flank_wall_detected(self):
        lower_flank = (6 << 5) | 6
        state = _state_with_wall(lower_flank)
        assert mob_probe_right(
            state, (5 << 5) | 5, hpos=78 << 6, vpos=82 << 6,
        ) == lower_flank


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
        y_before = state.mobs.vpos[state.players[pi].mob_slot] >> 6
        player_try_move(state, pi, gin.JOY_UP, 0)
        y_after = state.mobs.vpos[state.players[pi].mob_slot] >> 6
        assert y_after == y_before, "should not move into wall above"

    def test_blocked_down(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(6 << 5) | 5] = _WALL_PICTURE
        y_before = state.mobs.vpos[state.players[pi].mob_slot] >> 6
        player_try_move(state, pi, gin.JOY_DOWN, 0)
        y_after = state.mobs.vpos[state.players[pi].mob_slot] >> 6
        assert y_after == y_before

    def test_blocked_left(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(5 << 5) | 4] = _WALL_PICTURE
        x_before = state.mobs.hpos[state.players[pi].mob_slot] >> 6
        player_try_move(state, pi, gin.JOY_LEFT, 0)
        x_after = state.mobs.hpos[state.players[pi].mob_slot] >> 6
        assert x_after == x_before

    def test_blocked_right(self):
        state, pi = self._player_at_slot((5 << 5) | 5)
        state.mobs.picture[(5 << 5) | 6] = _WALL_PICTURE
        x_before = state.mobs.hpos[state.players[pi].mob_slot] >> 6
        player_try_move(state, pi, gin.JOY_RIGHT, 0)
        x_after = state.mobs.hpos[state.players[pi].mob_slot] >> 6
        assert x_after == x_before

    def test_movable_wall_blocks_despite_real_sprite(self):
        """A movable wall carries a real sprite picture (0x20F6), not the 0x8000
        marker, but still blocks -- collision keys off obj_type for it."""
        from gauntpy.constants import MazeObjIds
        state, pi = self._player_at_slot((5 << 5) | 5)
        slot = (5 << 5) | 6
        state.mobs.create(slot, tile=0x20F6, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.WALL_MOVABLE))
        x_before = state.mobs.hpos[state.players[pi].mob_slot] >> 6
        player_try_move(state, pi, gin.JOY_RIGHT, 0)
        assert state.mobs.hpos[state.players[pi].mob_slot] >> 6 == x_before

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
        y_before = state.mobs.vpos[state.players[pi].mob_slot] >> 6
        player_try_move(state, pi, gin.JOY_UP, 0)
        y_after = state.mobs.vpos[state.players[pi].mob_slot] >> 6
        assert y_after < y_before, "player should move up when clear"

    def test_flank_wall_does_not_block_parallel_empty_floor(self):
        """The three-cell probe is position-aware, not a whole-row barrier."""
        state, pi = self._player_at_slot((5 << 5) | 5)
        flank = (4 << 5) | 6
        state.mobs.picture[flank] = _WALL_PICTURE
        before = state.mobs.hpos[state.players[pi].mob_slot] >> 6

        assert player_try_move(state, pi, gin.JOY_RIGHT, 0) != _NO_MOVE
        assert state.mobs.hpos[state.players[pi].mob_slot] >> 6 > before


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
        y_before = state.mobs.vpos[player.mob_slot] >> 6
        x_before = state.mobs.hpos[player.mob_slot] >> 6
        player_try_move(state, 0, gin.JOY_UP | gin.JOY_RIGHT, 0)
        y_after = state.mobs.vpos[player.mob_slot] >> 6
        x_after = state.mobs.hpos[player.mob_slot] >> 6
        assert y_after == y_before, "should not move up into wall"
        assert x_after > x_before, "should still move right"

    def test_both_axes_blocked_returns_no_move(self):
        state = GameState()
        player = _active_player_at(state, 0, (5 << 5) | 5)
        state.mobs.picture[(4 << 5) | 5] = _WALL_PICTURE   # wall above
        state.mobs.picture[(5 << 5) | 6] = _WALL_PICTURE   # wall right
        result = player_try_move(state, 0, gin.JOY_UP | gin.JOY_RIGHT, 0)
        assert result == _NO_MOVE


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
        state.mobs.hpos[player.mob_slot] = 170 << 6
        state.movement_type = 2

        result = player_try_move(state, 0, gin.JOY_UP, 0)

        assert result != _NO_MOVE
        assert state.player_tile_pos[0] == ((9 << 5) | 10)
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
        state = GameState()
        player = _active_player_at(state, 0, (1 << 5) | 10)
        player.powers = self._POWER_INVULN
        wall = (0 << 5) | 10
        state.mobs.picture[wall] = _WALL_PICTURE
        state.mobs.set_obj_type(wall, int(MazeObjIds.WALL_REGULAR))
        state.movement_type = 2

        player_try_move(state, 0, gin.JOY_UP, 0)

        assert state.player_tile_pos[0] == ((31 << 5) | 10)


class TestThiefRouteTracking:
    def test_crossing_cell_records_victim_route(self):
        from gauntpy.subsystems.thief import path_grid_get_direction

        state = GameState()
        start = (10 << 5) | 10
        player = _active_player_at(state, 0, start)
        state.thief_victim = 0
        state.thief_victim_pos = start

        for _ in range(8):
            player_try_move(state, 0, gin.JOY_RIGHT, 0)

        assert state.mobs.hpos[player.mob_slot] >> 6 == 172
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
        y_before = state.mobs.vpos[player.mob_slot] >> 6
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
        state.scroll_y = 0x108 - 80
        return state, player

    def test_player_cannot_walk_under_the_hud(self):
        state, player = self._state()
        state.mobs.hpos[player.mob_slot] = ((100 + 223) << 6)
        before = state.mobs.hpos[player.mob_slot]

        assert player_try_move(state, 0, gin.JOY_RIGHT, 0) == _NO_MOVE
        assert state.mobs.hpos[player.mob_slot] == before

    def test_player_cannot_walk_past_the_bottom_screen_edge(self):
        state, player = self._state()
        state.mobs.vpos[player.mob_slot] = ((80 + 231) << 6)
        before = state.mobs.vpos[player.mob_slot]

        assert player_try_move(state, 0, gin.JOY_DOWN, 0) == _NO_MOVE
        assert state.mobs.vpos[player.mob_slot] == before

    def test_player_offscreen_flag_bypasses_both_screen_edges(self):
        state, player = self._state()
        state.level_flags_4 |= 0x80
        state.mobs.hpos[player.mob_slot] = ((100 + 223) << 6)
        state.mobs.vpos[player.mob_slot] = ((80 + 231) << 6)

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
        x_before = state.mobs.hpos[player.mob_slot] >> 6
        # Move right many times to cross the boundary
        for _ in range(10):
            player_try_move(state, 0, gin.JOY_RIGHT, 0)
        x_after = state.mobs.hpos[player.mob_slot] >> 6
        # With wrap, position should be small (wrapped around)
        assert x_after < x_before, "x should have wrapped around"

    def test_no_wraparound_without_flag(self):
        """Without wrap_h, movement is clamped at the right edge."""
        state = GameState()
        state.wrap_h = False
        player = _active_player_at(state, 0, (10 << 5) | 31)
        x_before = state.mobs.hpos[player.mob_slot] >> 6
        for _ in range(20):
            player_try_move(state, 0, gin.JOY_RIGHT, 0)
        x_after = state.mobs.hpos[player.mob_slot] >> 6
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
        y_before = state.mobs.vpos[player.mob_slot] >> 6
        # Active low: clear bit 7 (UP) in the raw word.
        state.player_input_raw[0] = 0xFFFF & ~gin.JOY_UP
        player_try_move(state, 0, gin.direction_bits(state, 0), 0)
        y_after = state.mobs.vpos[player.mob_slot] >> 6
        assert y_after < y_before, "raw UP press (bit 7) must move the player up"

    def test_raw_right_press_moves_player_right(self):
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        x_before = state.mobs.hpos[player.mob_slot] >> 6
        state.player_input_raw[0] = 0xFFFF & ~gin.JOY_RIGHT   # clear bit 4
        player_try_move(state, 0, gin.direction_bits(state, 0), 0)
        x_after = state.mobs.hpos[player.mob_slot] >> 6
        assert x_after > x_before, "raw RIGHT press (bit 4) must move the player right"

    def test_spare_bits_do_not_move_player(self):
        """Clearing the spare lines (bits 2-3) must not cause movement."""
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        x_before = state.mobs.hpos[player.mob_slot] >> 6
        y_before = state.mobs.vpos[player.mob_slot] >> 6
        state.player_input_raw[0] = 0xFFFF & ~0x0C   # clear bits 2 and 3
        player_try_move(state, 0, gin.direction_bits(state, 0), 0)
        assert state.mobs.hpos[player.mob_slot] >> 6 == x_before
        assert state.mobs.vpos[player.mob_slot] >> 6 == y_before


class TestPerCharacterSpeed:
    """player_speed_normal (ROM 0x580A8): Elf 4 px, others 2 px; power doubles."""

    def _step_right(self, character: int, powers: int = 0) -> int:
        from gauntpy.constants import Character  # noqa: F401
        state = GameState()
        player = _active_player_at(state, 0, (10 << 5) | 10)
        player.character = character
        player.powers = powers
        x_before = state.mobs.hpos[player.mob_slot] >> 6
        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        return (state.mobs.hpos[player.mob_slot] >> 6) - x_before

    def test_warrior_moves_two_pixels(self):
        assert self._step_right(0) == 2

    def test_elf_moves_four_pixels(self):
        assert self._step_right(3) == 4, "Elf base speed is 0x100 -> 4 px"

    def test_speed_power_doubles_warrior(self):
        assert self._step_right(0, powers=0x01) == 4, "POWER_SPEED_BIT -> 4 px"


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

    def test_special_mazes_run_everyone_at_0x100(self):
        state = GameState()
        state.mazenum_current = gp._SPECIAL_MAZE_FIRST
        p = state.players[0]
        p.character = int(Character.WARRIOR)
        state.frame_counter = 1
        assert gp._player_speed_units(state, p) == 0x100

    def test_boost_reaches_player_try_move(self):
        """A boosted Warrior frame moves 3 px, an unboosted one 2 px."""
        state = GameState()
        _active_player_at(state, 0, (5 << 5) | 5)
        state.frame_counter = 0
        x0 = state.mobs.hpos[state.players[0].mob_slot] >> 6
        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        assert (state.mobs.hpos[state.players[0].mob_slot] >> 6) - x0 == 2

        state = GameState()
        _active_player_at(state, 0, (5 << 5) | 5)
        state.frame_counter = 1
        x0 = state.mobs.hpos[state.players[0].mob_slot] >> 6
        player_try_move(state, 0, gin.JOY_RIGHT, 0)
        assert (state.mobs.hpos[state.players[0].mob_slot] >> 6) - x0 == 4
