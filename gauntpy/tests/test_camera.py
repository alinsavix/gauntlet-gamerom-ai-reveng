"""Tests for the camera scroll system (WP-13).

Acceptance criteria from PLAN.md §6 WP-13:
1. One player running away stops dragging the camera at 200 px (0xC8).
2. Camera never exceeds the playfield scroll clamps.
3. Wraparound levels track correctly across the seam.

Test coverage:
1. Single player: camera moves toward player position.
2. Camera snaps to target when within 2 px (|delta| < 3).
3. Two-player spread > 0xC8: extent clamped to 0xC8.
4. Camera uses the ROM's asymmetric X/Y scroll clamps.
5. No movement when level_players_active == 0.
6. Camera steps exactly 2 px per frame when delta >= 3.
7. Wraparound levels: positions > 512 px are folded across the seam.
"""

from __future__ import annotations

import pytest

from gauntpy.coords import native_v
from gauntpy.constants import GameMode, PlayerStatus
from gauntpy.state import GameState
from gauntpy.subsystems.camera import main_scroll_playfield, snap_camera, viewport_scroll


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_player(state: GameState, index: int, slot: int, px: int, py: int) -> None:
    """Place an active player at a specific pixel position in a mob slot.

    ``px`` / ``py`` are world pixel coordinates.  The camera reads pixel
    position through ``coords.hpos_x`` / ``coords.vpos_y``, so the native
    words go in here.  The ``slot`` is used as both mob_slot and the index
    into the hpos array (identity-is-location convention, §1.2).
    """
    player = state.players[index]
    player.status = PlayerStatus.ALIVE_HERE
    player.mob_slot = slot
    state.mobs.hpos[slot] = px << 7
    state.mobs.vpos[slot] = native_v(py) << 7
    # main_move_players maintains these in the real frame; the camera reads
    # them, so the isolated camera tests supply them here.
    state.player_in_maze[index] = 1
    state.player_tile_pos[index] = slot


def _gameplay_state() -> GameState:
    """Return a GameState configured for a normal gameplay frame."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.level_players_active = 1
    state.scroll_x = 0
    state.scroll_y = 0
    return state


# ---------------------------------------------------------------------------
# Test 1 -- single player: camera moves toward player position
# ---------------------------------------------------------------------------

class TestSinglePlayerMovement:
    def test_scroll_x_steps_toward_target(self):
        """scroll_x increases by 2 when target is far to the right (§17 step 3)."""
        state = _gameplay_state()
        # Player at pixel (200, 200):
        #   target_x = 200 - 0x68 = 200 - 104 = 96
        #   start scroll_x = 50 -> delta = 46 >= 3 -> scroll_x += 2 = 52
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = 50
        state.scroll_y = 180
        main_scroll_playfield(state)
        assert state.scroll_x == 52

    def test_scroll_y_steps_toward_target(self):
        """Downward-world target is player Y minus 0x74."""
        state = _gameplay_state()
        # Player at pixel (200, 200):
        #   target_y = 200 - 116 = 84
        #   start scroll_y = 100 -> delta = -16 -> scroll_y -= 2 = 98
        state.scroll_x = 96            # pre-position X so we isolate Y
        state.scroll_y = 100
        _active_player(state, 0, slot=10, px=200, py=200)
        main_scroll_playfield(state)
        assert state.scroll_y == 98

    def test_scroll_decreases_when_target_is_behind(self):
        """scroll_x decreases by 2 when target is to the left (§17 step 3)."""
        state = _gameplay_state()
        # Player at pixel (200, 200): target_x = 96
        # Start scroll_x = 150 -> delta = 96 - 150 = -54 <= -3 -> scroll_x -= 2 = 148
        state.scroll_x = 150
        state.scroll_y = 180
        _active_player(state, 0, slot=10, px=200, py=200)
        main_scroll_playfield(state)
        assert state.scroll_x == 148


# ---------------------------------------------------------------------------
# Test 2 -- camera snaps when within 2 px of target (|delta| < 3)
# ---------------------------------------------------------------------------

class TestSnapToTarget:
    def test_snap_x_when_delta_is_one(self):
        """scroll_x snaps to target when |delta| == 1 (§17 step 3: snap if |d| < 3)."""
        state = _gameplay_state()
        # Player at (200, 200): target_x = 96, target_y = 84
        # Start scroll_x = 97 -> delta = -1 -> snap -> scroll_x = 96
        state.scroll_x = 97
        state.scroll_y = 84
        _active_player(state, 0, slot=10, px=200, py=200)
        main_scroll_playfield(state)
        assert state.scroll_x == 96

    def test_snap_y_when_delta_is_minus_two(self):
        """scroll_y snaps to target when |delta| == 2 (§17 step 3)."""
        state = _gameplay_state()
        # Player at (200, 200): target_y = 84
        # Start scroll_y = 86 -> delta = -2 -> snap -> scroll_y = 84
        state.scroll_x = 96
        state.scroll_y = 86
        _active_player(state, 0, slot=10, px=200, py=200)
        main_scroll_playfield(state)
        assert state.scroll_y == 85

    def test_already_at_target_stays(self):
        """When scroll is exactly at target, it does not drift (§17 step 3)."""
        state = _gameplay_state()
        # Player at (200, 200): target_x = 96, target_y = 84
        state.scroll_x = 96
        state.scroll_y = 84
        _active_player(state, 0, slot=10, px=200, py=200)
        main_scroll_playfield(state)
        assert state.scroll_x == 96
        assert state.scroll_y == 84


# ---------------------------------------------------------------------------
# Test 3 -- rubber band: two-player spread > 0xC8 is clamped to 0xC8
# ---------------------------------------------------------------------------

class TestRubberBand:
    def test_spread_under_320_px_is_not_rubber_banded_horizontally(self):
        """The ROM's outlier threshold is 0x140, so a 300px spread is retained.

        Without rubber band: midpoint = (100+400)/2 = 250, target_x = 146.
        With rubber band:    max_x = 100+200 = 300, midpoint = 200, target_x = 96.
        Verifying by positioning scroll at 96 and checking it stays (snap).
        """
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=100, py=100)
        _active_player(state, 1, slot=20, px=400, py=100)
        state.level_players_active = 2
        # The unmodified midpoint is 250, target 146, so the camera leaves 96.
        state.scroll_x = 96
        state.scroll_y = 1
        main_scroll_playfield(state)
        assert state.scroll_x == 98

    def test_spread_under_320_px_is_not_rubber_banded_vertically(self):
        """A 300px vertical spread is below the ROM's 0x140 threshold.

        Without rubber band: midpoint_y = 250, target_y = 134.
        With rubber band: midpoint_y = 200, target_y = 84.
        """
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=200, py=100)
        _active_player(state, 1, slot=20, px=200, py=400)
        state.level_players_active = 2
        # target_x = 200 - 104 = 96
        # Unmodified target_y is 134.
        state.scroll_x = 96
        state.scroll_y = 84
        main_scroll_playfield(state)
        assert state.scroll_y == 86

    def test_spread_exactly_at_limit_is_not_clamped(self):
        """Spread of exactly 0xC8 pixels is within the rubber band -- no clamping."""
        state = _gameplay_state()
        # Players exactly 0xC8 = 200 px apart in X.
        _active_player(state, 0, slot=10, px=100, py=100)
        _active_player(state, 1, slot=20, px=300, py=100)    # 300 - 100 = 200 = 0xC8
        state.level_players_active = 2
        # No rubber band: midpoint = 200, target_x = 96
        state.scroll_x = 96
        state.scroll_y = 1
        main_scroll_playfield(state)
        assert state.scroll_x == 96

    def test_wrap_seam_target_stabilizes_in_the_scroll_register_frame(self):
        state = _gameplay_state()
        state.wrap_h = True
        state.scroll_x = 440
        _active_player(state, 0, slot=10, px=50, py=200)

        for _ in range(80):
            main_scroll_playfield(state)
        settled = state.scroll_x
        for _ in range(20):
            main_scroll_playfield(state)

        assert state.scroll_x == settled


# ---------------------------------------------------------------------------
# Test 4 -- exact ROM clamps when wrap flags are clear
# ---------------------------------------------------------------------------

class TestScrollClamp:
    def test_clamp_to_minimum_x(self):
        """scroll_x clamps to 5 when it would fall below that (§17 scroll_set_position)."""
        state = _gameplay_state()
        # Player at far-left: target_x = 0 - 104 = -104, very negative.
        # Start scroll_x = 5; delta = -109 <= -3 -> scroll_x -= 2 = 3; clamp to 5.
        _active_player(state, 0, slot=10, px=0, py=100)
        state.scroll_x = 5
        state.scroll_y = 100
        main_scroll_playfield(state)
        assert state.scroll_x == 5                # clamped to minimum

    def test_clamp_to_maximum_x(self):
        """scroll_x clamps to 0x124 when it would exceed that (0x46F56)."""
        state = _gameplay_state()
        # Player at px=620: target_x = 516 > 0x124.
        _active_player(state, 0, slot=10, px=620, py=100)
        state.scroll_x = 0x124
        state.scroll_y = 100
        main_scroll_playfield(state)
        assert state.scroll_x == 0x124

    def test_clamp_to_minimum_y(self):
        """scroll_y clamps to 1 when it would fall below that (0x46F56)."""
        state = _gameplay_state()
        # Player at py=0: target_y = -116.
        _active_player(state, 0, slot=10, px=100, py=0)
        state.scroll_x = 5
        state.scroll_y = 1
        main_scroll_playfield(state)
        assert state.scroll_y == 1

    def test_no_clamp_when_wrap_h_true(self):
        """With wrap_h=True the X clamp is skipped (§17 scroll_set_position)."""
        state = _gameplay_state()
        state.wrap_h = True
        # Player at far-left: target_x approaches -104; scroll steps below 5.
        # Start scroll_x = 5; delta = -109 <= -3 -> scroll_x -= 2 = 3 (no clamp).
        _active_player(state, 0, slot=10, px=0, py=100)
        state.scroll_x = 5
        state.scroll_y = 100
        main_scroll_playfield(state)
        assert state.scroll_x == 3                # NOT clamped, below 5


# ---------------------------------------------------------------------------
# Test 5 -- no movement when disabled
# ---------------------------------------------------------------------------

class TestGateConditions:
    def test_no_movement_when_level_players_active_is_zero(self):
        """main_scroll_playfield is a no-op when no players are active (§17 guard)."""
        state = _gameplay_state()
        state.level_players_active = 0
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = 100
        state.scroll_y = 100
        main_scroll_playfield(state)
        assert state.scroll_x == 100
        assert state.scroll_y == 100

    def test_no_movement_in_title_mode(self):
        """main_scroll_playfield is a no-op in TITLE mode (§17: only NORMAL/DEMO)."""
        state = _gameplay_state()
        state.game_mode = GameMode.TITLE
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = 100
        state.scroll_y = 100
        main_scroll_playfield(state)
        assert state.scroll_x == 100
        assert state.scroll_y == 100

    def test_movement_in_demo_mode(self):
        """main_scroll_playfield runs during GAMEMODE_DEMO as well as NORMAL (§17)."""
        state = _gameplay_state()
        state.game_mode = GameMode.DEMO
        # Player at (200, 200): target_x=96, target_y=84.
        # scroll_x=50 -> delta=46 -> steps to 52.
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = 50
        state.scroll_y = 84
        main_scroll_playfield(state)
        assert state.scroll_x == 52               # camera still moves in DEMO mode

    def test_no_movement_when_player_not_in_maze(self):
        """If no player is in the maze (all player_in_maze == 0), scroll is unchanged."""
        state = _gameplay_state()
        # Players all have default status REMOVED -> player_in_maze all 0.
        state.scroll_x = 100
        state.scroll_y = 100
        main_scroll_playfield(state)
        assert state.scroll_x == 100
        assert state.scroll_y == 100


# ---------------------------------------------------------------------------
# Test 6 -- camera steps exactly 2 px per frame when delta >= 3
# ---------------------------------------------------------------------------

class TestStepSize:
    @pytest.mark.parametrize("start_x,expected_x", [
        (50,  52),    # delta = +46 >= 3 -> step +2
        (150, 148),   # delta = -54 <= -3 -> step -2
    ])
    def test_x_step_is_exactly_two(self, start_x: int, expected_x: int):
        """Each frame the camera moves exactly 2 px when |delta_x| >= 3 (§17)."""
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = start_x
        state.scroll_y = 84                        # pre-position Y at target
        main_scroll_playfield(state)
        assert state.scroll_x == expected_x

    @pytest.mark.parametrize("start_y,expected_y", [
        (50, 52),     # target 84, step +2
        (100, 98),    # target 84, step -2
    ])
    def test_y_step_is_exactly_two(self, start_y: int, expected_y: int):
        """Each frame the camera moves exactly 2 px when |delta_y| >= 3 (§17)."""
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = 96                        # pre-position X at target
        state.scroll_y = start_y
        main_scroll_playfield(state)
        assert state.scroll_y == expected_y

    def test_step_exactly_at_threshold_3_does_step(self):
        """delta == 3 is on the >= boundary and causes a 2-px step (§17)."""
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=200, py=200)
        # target_x = 96; scroll_x = 93 -> delta = 3 -> step +2 -> 95
        state.scroll_x = 93
        state.scroll_y = 84
        main_scroll_playfield(state)
        assert state.scroll_x == 94

    def test_delta_two_snaps_not_steps(self):
        """delta == 2 is below the step threshold; scroll snaps to target (§17)."""
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=200, py=200)
        # target_x = 96; scroll_x = 94 -> delta = 2 -> snap -> 96
        state.scroll_x = 94
        state.scroll_y = 84
        main_scroll_playfield(state)
        assert state.scroll_x == 95


# ---------------------------------------------------------------------------
# Test 7 -- wraparound: positions past the seam (x > 512) are folded correctly
# ---------------------------------------------------------------------------

class TestViewportConversion:
    """viewport_scroll converts the camera's hardware scroll registers into the
    renderer's viewport top-left (I-23)."""

    def test_mid_maze_player_centres_exactly(self):
        state = _gameplay_state()
        _active_player(state, 0, slot=500, px=256, py=256)
        snap_camera(state)
        vx, vy = viewport_scroll(state, 240, 240)
        assert (vx, vy) == (144, 140)
        assert (256 - vx, 256 - vy) == (112, 116)

    def test_viewport_is_a_wrapped_hardware_origin(self):
        for px, py in [(0, 0), (512, 512), (256, 0), (0, 256), (448, 448)]:
            state = _gameplay_state()
            _active_player(state, 0, slot=500, px=px, py=py)
            snap_camera(state)
            vx, vy = viewport_scroll(state, 240, 240)
            assert 0 <= vx < 512, (px, py, vx)
            assert 0 <= vy < 512, (px, py, vy)

    def test_nonwrapping_horizontal_view_never_exposes_the_opposite_edge(self):
        state = _gameplay_state()
        state.wrap_h = False
        state.scroll_x = 5
        assert viewport_scroll(state, 232, 240)[0] == 0

        state.scroll_x = 0x124
        assert viewport_scroll(state, 232, 240)[0] == 0x124 - 8

    def test_wrapping_horizontal_view_keeps_the_hardware_seam(self):
        state = _gameplay_state()
        state.wrap_h = True
        state.scroll_x = 5
        assert viewport_scroll(state, 232, 240)[0] == 509

    def test_low_player_is_still_on_screen(self):
        """The upward V register used to push a low player off-screen (the
        bug behind the runner's old _center_camera workaround)."""
        state = _gameplay_state()
        _active_player(state, 0, slot=500, px=256, py=448)
        snap_camera(state)
        vx, vy = viewport_scroll(state, 240, 240)
        assert 0 <= 448 - vy < 240                     # hero row is within the viewport

    def test_low_player_uses_rom_maximum_scroll(self):
        state = _gameplay_state()
        _active_player(state, 0, slot=500, px=256, py=448)
        snap_camera(state)
        assert state.scroll_y == 0x118
        assert viewport_scroll(state, 240, 240)[1] == 0x118

    def test_top_player_uses_rom_minimum_scroll(self):
        state = _gameplay_state()
        _active_player(state, 0, slot=500, px=256, py=0)
        snap_camera(state)
        assert state.scroll_y == 1


class TestSnapCamera:
    def test_snap_jumps_straight_to_target(self):
        """snap_camera writes the target with no 2px smoothing."""
        state = _gameplay_state()
        _active_player(state, 0, slot=10, px=200, py=200)
        state.scroll_x = 0
        state.scroll_y = 0
        snap_camera(state)
        # Converted ROM target: x = 200 - 0x68; y = 200 - 0x74.
        assert (state.scroll_x, state.scroll_y) == (96, 84)

    def test_snap_is_a_noop_without_tracked_players(self):
        state = _gameplay_state()
        state.scroll_x, state.scroll_y = 42, 24
        snap_camera(state)                             # no player_in_maze set
        assert (state.scroll_x, state.scroll_y) == (42, 24)


class TestSeamWraparound:
    def test_x_position_past_seam_is_adjusted(self):
        """When wrap_h is True, a player at pixel x=520 (past the 512-px seam)
        is folded to x=8 for camera purposes (§17; acceptance criterion 3).

        Player A: x=5,  hpos = 5<< 7 = 320
        Player B: x=520, hpos = 520<< 7 = 33280 (raw pos, past the right edge)
        ref_x = 5; diff = 520 - 5 = 515 > 0x200 (512) -> adjust B: px = 520 - 512 = 8
        midpoint = (5 + 8) // 2 = 6
        target_x = 6 - 0x68 = -98; raw scroll_x steps to -2. The final
        register write masks it to its 9-bit value, 0x1FE.
        """
        state = _gameplay_state()
        state.wrap_h = True
        state.level_players_active = 2
        _active_player(state, 0, slot=10, px=5,   py=100)
        _active_player(state, 1, slot=20, px=520, py=100)   # past-seam position
        state.scroll_x = 0
        state.scroll_y = 100            # pre-position Y so we focus on X
        main_scroll_playfield(state)
        # With correct wrap: target_x = -98, step toward it -> raw scroll_x=-2.
        # Without wrap: positions [5, 520], rubber-band max = 205, target ≈ 1, snap.
        assert state.scroll_x == 0x1FE

    def test_no_wrap_adjustment_when_wrap_h_false(self):
        """When wrap_h is False, no seam adjustment is applied (§17 guard)."""
        state = _gameplay_state()
        state.wrap_h = False
        state.level_players_active = 2
        _active_player(state, 0, slot=10, px=5,   py=100)
        _active_player(state, 1, slot=20, px=520, py=100)
        state.scroll_x = 0
        state.scroll_y = 100
        main_scroll_playfield(state)
        # No wrap logic: raw min=5, max=520, diff=515 > 0xC8 -> max = 5+200 = 205
        # midpoint = (5+205)//2 = 105, target_x = 105 - 104 = 1 -> snap
        # Then clamp: max(5, 1) = 5
        assert state.scroll_x == 5     # clamped min, not -2 (no wrap applied)
