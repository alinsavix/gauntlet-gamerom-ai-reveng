"""Level-transition orchestration, positioned spawn, and player firing (WP-20).

Covers the pieces that were blocked on "WP-20 orchestration / maze spawn":

  * maze_checknum (0x52ECA) and compute_next_level (the player_exit_sequence
    tail, 0x52DB2) -- the next level/maze arithmetic (doc/06 §3.2/§3.4);
  * player_exit_sequence (0x52B40) -- exit state machine and the "advance when
    all players have exited" gate;
  * show_level_end_bonus_screen (0x4D476) -- actually loads the next maze and
    re-places survivors (I-12), exercised with real ROMs;
  * player_start_inner (0x48BEC) -- the positioned player spawn (I-08);
  * player_create_shot (0x53666) -- player firing (N-02).

The pure arithmetic/state-machine tests need no ROMs; the full maze-reload test
skips cleanly when the Slapstic ROMs are absent, mirroring test_maze.py.
"""

from __future__ import annotations

import pytest

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus, SLOT_PLAYER_SHOTS
from gauntpy.coords import encode_hpos, encode_vpos_at_y, pack_slot
from gauntpy.mainloop import tick
from gauntpy.state import GameState
from gauntpy.subsystems import exits as ex
from gauntpy.subsystems import players as gp
from gauntpy.subsystems import session as sess
from gauntpy.subsystems.input import JOY_MAGIC_BIT, JOY_RIGHT

from gex.roms import SLAPSTIC_ROMS, _rom_dir

_ROM_PATH = _rom_dir()
_ROMS_EXIST = _ROM_PATH.is_dir() and (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file()
requires_roms = pytest.mark.skipif(
    not _ROMS_EXIST, reason=f"Slapstic ROM files ({_ROM_PATH}) not available"
)


# ---------------------------------------------------------------------------
# maze_checknum (0x52ECA)
# ---------------------------------------------------------------------------

class TestMazeChecknum:
    def test_candidate_5_is_replaced_by_resume(self):
        """The hinge (doc/06 §3.2): candidate maze 5 -> the resume position."""
        state = GameState()
        state.mazerand_num = 42
        state.maze_next = 5
        ex.maze_checknum(state)
        assert state.maze_next == 42

    def test_candidate_above_101_wraps_to_5_and_forces_eeprom_save(self):
        state = GameState()
        state.mazerand_num = 5
        state.maze_next = 150
        ex.maze_checknum(state)
        assert state.maze_next == 5
        assert state.timer_eepromwrite == 1   # forced save next tick

    def test_in_range_candidate_is_left_alone(self):
        state = GameState()
        state.maze_next = 60
        ex.maze_checknum(state)
        assert state.maze_next == 60


# ---------------------------------------------------------------------------
# compute_next_level -- the player_exit_sequence tail (doc/06 §3.2/§3.4)
# ---------------------------------------------------------------------------

class TestComputeNextLevel:
    def test_fresh_cabinet_maze4_to_level6_lands_on_resume_and_bumps_stride(self):
        """Factory-fresh: exiting maze 4 (level 5) -> level 6 = maze 5 (resume),
        and landing on 5 raises the stride to 1 (doc/06 §3.2)."""
        state = GameState()
        state.levelnum_current = 5
        state.mazenum_current = 4
        state.mazerand_num = 5
        state.mazerand_adder = 0
        ex.compute_next_level(state, int(MazeObjIds.EXIT))
        assert state.level_next == 6
        assert state.maze_next == 5
        assert state.mazerand_adder == 1

    def test_opening_act_maze0_to_maze1(self):
        """Levels 1-5 step one maze at a time (stride not yet in play)."""
        state = GameState()
        state.levelnum_current = 1
        state.mazenum_current = 0
        ex.compute_next_level(state, int(MazeObjIds.EXIT))
        assert state.level_next == 2
        assert state.maze_next == 1

    def test_level_wraps_at_1000_back_to_6(self):
        state = GameState()
        state.levelnum_current = 999
        state.mazenum_current = 50
        ex.compute_next_level(state, int(MazeObjIds.EXIT))
        assert state.level_next == 6           # 1000 - 994

    def test_exitto6_jumps_to_level6_at_resume(self):
        """EXITTO6 shortcut (doc/06 §3.4): straight to level 6 / resume, and it
        does not bump the stride."""
        state = GameState()
        state.levelnum_current = 1
        state.mazenum_current = 0
        state.mazerand_num = 37
        state.mazerand_adder = 3
        ex.compute_next_level(state, int(MazeObjIds.EXITTO6))
        assert state.level_next == 6
        assert state.maze_next == 37
        assert state.mazerand_adder == 3          # unchanged


# ---------------------------------------------------------------------------
# player_exit_sequence (0x52B40)
# ---------------------------------------------------------------------------

def _active_player_with_mob(state: GameState, index: int, slot: int,
                            health: int = 500) -> None:
    """Make player *index* ALIVE_HERE with a real hero MOB at *slot*.

    ``level_players_active`` is bumped the way ``player_start_inner`` (0x48BEC)
    does, because the exit tail at 0x4A6E6 is what ends the level and it counts
    that word down.  The health matters as soon as a test runs frames: a hero
    on zero health dies on the next ``main_move_players``.
    """
    px, py = slot % 32 * 16, slot // 32 * 16
    state.mobs.create(slot, tile=0x1e0d, hpos=encode_hpos(px), vpos=encode_vpos_at_y(py),
                      obj_type=int(MazeObjIds.PLAYERSTART))
    p = state.players[index]
    p.status = int(PlayerStatus.ALIVE_HERE)
    p.mob_slot = slot
    p.health = health
    state.player_in_maze[index] = 1
    state.level_players_active += 1


def _run_exit_animation(state: GameState, frames: int = 96) -> None:
    """Play out the status-8 exit dissolve (main_move_players 0x4A646-0x4A6E6).

    ``player_exit_sequence`` (0x52B40) only *starts* it: the ROM parks the hero
    in status 8 for the ~32-frame animation and the level ends when the last one
    finishes (``level_players_active`` hitting zero at 0x4A6E6).  The mode is
    forced out of attract because the whole player loop is gated on it.
    """
    if state.game_mode < 0:
        state.game_mode = int(GameMode.NORMAL)
    for _ in range(frames):
        if not any(p.exit_pending for p in state.players):
            return
        gp.main_move_players(state)
    raise AssertionError("the exit animation never finished")


class TestPlayerExitSequence:
    def test_exit_marks_player_exiting_plays_sound_and_removes_sprite(self):
        state = GameState()
        _active_player_with_mob(state, 0, pack_slot(10, 10))
        # A second player still in the maze so the transition does NOT fire yet.
        _active_player_with_mob(state, 1, pack_slot(12, 12))
        slot0 = state.players[0].mob_slot

        ex.player_exit_sequence(state, 0, slot0, int(MazeObjIds.EXIT))

        # 0x52C66: status 8 for the dissolve, not straight to 2.
        assert state.players[0].status == int(PlayerStatus.EXITING)
        assert state.players[0].exit_pending == 1
        assert state.player_in_maze[0] == 0
        assert state.mobs.picture[slot0] == 0          # sprite lifted out
        assert (0x0E + 0) in state.sound_log         # per-player exit sound
        # Player 1 is still ALIVE_HERE, so no level advance happened.
        assert state.levelnum_current == 0

        _run_exit_animation(state)
        assert state.players[0].status == int(PlayerStatus.ALIVE_NEXT)
        assert state.levelnum_current == 0, "player 1 is still on the level"

    def test_the_exit_animation_holds_the_level_open(self):
        """0x4A646-0x4A6E6: the dissolve is 4 spin steps plus 0x20 counter
        frames before the level can end."""
        state = GameState()
        state.levelnum_current = 1
        _active_player_with_mob(state, 0, pack_slot(10, 10))
        p = state.players[0]
        p.direction = 4                      # ROM facing 6 -> two spin steps

        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        state.game_mode = int(GameMode.NORMAL)

        anim_slot = 21                       # SLOT_EXIT_ANIMS[0]
        assert p.mob_slot == anim_slot
        for _ in range(8):                   # two spin steps at four frames each
            gp.main_move_players(state)
        assert state.player_death_anim_frame[0] == 4
        assert p.status == int(PlayerStatus.EXITING)

        # 0x4A796: the dissolve table drives the picture while the counter runs.
        gp.main_move_players(state)
        gp.main_move_players(state)
        gp.main_move_players(state)
        gp.main_move_players(state)
        assert state.mobs.picture[anim_slot] == gp._PLAYER_EXIT_PICTURE[
            (p.character & 3) * 8 + (p.anim_counter >> 2)
        ]
        assert p.status == int(PlayerStatus.EXITING)
        assert state.level_players_active == 1

        _run_exit_animation(state)
        assert p.status == int(PlayerStatus.ALIVE_NEXT)
        assert state.level_players_active == 0
        if state.level_start_pending:
            assert state.mobs.picture[anim_slot] == 0x8000, "the next maze boundary is loaded"
        else:
            assert state.mobs.picture[anim_slot] == 0, "ROM-free fallback releases the animation"

    def test_last_player_to_exit_advances_the_level(self):
        """Solo player: stepping on the exit ends the level -- once the exit
        animation has played out -- and the next level/maze are computed and
        committed. (Whether the survivor is then re-placed as ALIVE_HERE depends
        on the maze actually loading, which needs ROMs; the level-advance itself
        does not, so that is what this asserts.)"""
        state = GameState()
        state.levelnum_current = 1
        state.mazenum_current = 0
        _active_player_with_mob(state, 0, pack_slot(10, 10))

        ex.player_exit_sequence(state, 0, state.players[0].mob_slot,
                                int(MazeObjIds.EXIT))

        assert state.level_next == 2
        assert state.levelnum_current == 1, "not committed until the animation ends"

        _run_exit_animation(state)
        assert state.levelnum_current == 2             # committed by bonus screen
        assert state.mazenum_current == 1


# ---------------------------------------------------------------------------
# show_level_end_bonus_screen (0x4D476) -- the real maze reload (I-12)
# ---------------------------------------------------------------------------

@requires_roms
class TestShowLevelEndBonusScreenLoadsNextMaze:
    def test_level_splash_timer_advances_while_a_dialog_gates_the_world(self, monkeypatch):
        spawned = []
        monkeypatch.setattr(
            ex, "_spawn_level_players",
            lambda state, survivors: spawned.append((state, survivors)),
        )
        state = GameState(
            game_mode=GameMode.NORMAL,
            global_ui_delay_timer=2,
            dialog_timer=30,
            level_start_pending=True,
        )
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)

        sess.main_start_game(state)
        sess.main_start_game(state)

        assert state.global_ui_delay_timer == 0
        assert not state.level_start_pending
        assert spawned and spawned[0][1] == [0]

    def test_solo_exit_loads_next_level_and_respawns_survivor(self):
        from gauntpy import maze

        state = GameState()
        maze.load_level(state, 1)                       # level 1 = maze 0
        # Drop a hero in via the real spawn path.
        assert gp.player_start_inner(state, 0) == -1
        state.players[0].health = 500
        old_slot = state.players[0].mob_slot

        # Take the exit: the hero dissolves for ~32 frames, then the ordinary
        # level splash appears. The treasure tally is reserved for bonus rooms
        # and scheduled bonus-room entries.
        ex.player_exit_sequence(state, 0, old_slot, int(MazeObjIds.EXIT))
        assert state.players[0].status == int(PlayerStatus.EXITING)
        assert state.game_mode != int(GameMode.TREAS_EXIT)
        _run_exit_animation(state)

        assert state.game_mode == int(GameMode.NORMAL)
        assert state.global_ui_delay_timer > 0
        assert state.level_start_pending
        assert state.levelnum_current == 2 and state.mazenum_current == 1  # committed
        assert state.players[0].status == int(PlayerStatus.ALIVE_NEXT)

        # Hold the level splash out; when the timer expires the hero is placed.
        while state.global_ui_delay_timer > 0:
            sess.main_start_game(state)

        assert state.game_mode == int(GameMode.NORMAL)
        assert not state.level_start_pending
        assert state.maze is not None
        assert all(
            state.alpha_ram[row * 64 + column] == 0
            for row in range(30)
            for column in range(29)
        )
        assert all(
            state.alpha_ram[row * 64 + column] & 0x8000
            for row in range(30)
            for column in range(29, 42)
        )
        p = state.players[0]
        assert p.status == int(PlayerStatus.ALIVE_HERE)                    # respawned
        assert state.mobs.obj_type(p.mob_slot) == int(MazeObjIds.PLAYERSTART)
        assert state.level_players_active == 1


class TestLevelEndBonus:
    """The level-end bonus tally (100 x players x coins x treasures) and its
    brief display phase (show_level_end_bonus_screen, §16)."""

    def test_treasure_pickup_bumps_the_level_count(self):
        state = GameState()
        p = state.players[0]
        p.status = int(PlayerStatus.ALIVE_HERE)
        p.mob_slot = 40
        state.mobs.create(40, tile=0, hpos=0, vpos=0, obj_type=int(MazeObjIds.TREASURE))
        gp.player_tile_interact(state, 40, 0)
        assert state.level_treasures == 1

    def test_bonus_tally_and_phase(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.levelnum_current, state.mazenum_current = 1, 0
        state.level_treasures = 5
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.players[0].coin_count = 1
        ex.compute_next_level(state, int(MazeObjIds.EXIT))
        ex.show_level_end_bonus_screen(state)
        assert state.bonus_amount == 100 * 1 * 1 * 5      # players*coins*treasures
        assert state.players[0].score == 500              # awarded to the exiter
        assert state.game_mode == int(GameMode.TREAS_EXIT)
        assert state.global_ui_delay_timer == 0x12C                 # 0x4D50E

    def test_no_treasures_is_no_bonus(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.level_treasures = 0
        ex.show_level_end_bonus_screen(state)
        assert state.bonus_amount == 0


# ---------------------------------------------------------------------------
# Treasure-room interleave (doc/06 §3.5) -- the full round trip
# ---------------------------------------------------------------------------

@requires_roms
class TestTreasureRoomRoundTrip:
    """A treasure room borrows a level number and hands it straight back.

    Level N ends -> ``show_level_start_screen`` swaps the rotation maze for
    ``treas_mazerand_num`` -> the countdown expires -> the post-room tally holds
    -> the saved ``maze_next`` is played, still as level N (§3.5).
    """

    def _level_12_with_a_hero(self) -> GameState:
        from gauntpy import maze

        state = GameState()
        state.game_mode = GameMode.NORMAL
        maze.load_level(state, 12, maze_number=40)
        ex.exit_scan_level(state)
        state.level_next_treasure = 1          # this transition schedules the room
        state.treas_mazerand_num = 104
        state.treas_mazerand_adder = 0
        assert gp.player_start_inner(state, 0) == -1
        state.players[0].health = 500
        return state

    def _run_out_the_hold(self, state: GameState) -> None:
        """Sit out the current level-start or bonus display hold."""
        _run_exit_animation(state)
        while state.global_ui_delay_timer > 0:
            sess.main_start_game(state)

    def test_exit_lands_in_a_treasure_room_then_returns_to_the_rotation(self):
        state = self._level_12_with_a_hero()

        ex.player_exit_sequence(state, 0, state.players[0].mob_slot,
                                int(MazeObjIds.EXIT))
        assert (state.level_next, state.maze_next) == (13, 41)
        _run_exit_animation(state)
        assert state.game_mode == int(GameMode.NORMAL)
        assert state.mazenum_current == 104

        self._run_out_the_hold(state)
        # The treasure room replaced the rotation maze but kept its level number.
        assert state.levelnum_current == 13
        assert state.mazenum_current == 104
        assert state.maze_next == 41, "the displaced rotation maze is remembered"
        assert state.treasure_timer == 1200 + 1     # solo duration + 1
        assert state.treas_mazerand_num == 105      # rotation advanced by adder+1
        assert 3 <= state.level_next_treasure <= 5
        assert state.idle_timer == 0
        assert state.players[0].status == int(PlayerStatus.ALIVE_HERE)
        assert state.game_mode == int(GameMode.NORMAL)

        # Sit out the whole treasure room; the timeout ends the level.
        while state.treasure_timer > 0:
            ex.main_treasure_timer(state)
        assert state.game_mode == int(GameMode.TREAS_EXIT)

        self._run_out_the_hold(state)
        assert (state.levelnum_current, state.mazenum_current) == (13, 41)
        assert state.game_mode == int(GameMode.NORMAL)
        assert state.players[0].status == int(PlayerStatus.ALIVE_HERE)
        assert state.level_players_active == 1

    def test_walking_the_treasure_room_exit_returns_the_same_way(self):
        state = self._level_12_with_a_hero()
        ex.player_exit_sequence(state, 0, state.players[0].mob_slot,
                                int(MazeObjIds.EXIT))
        self._run_out_the_hold(state)
        assert state.mazenum_current == 104

        ex.player_exit_sequence(state, 0, state.players[0].mob_slot,
                                int(MazeObjIds.EXIT))
        assert state.treasure_timer == 0             # 0x52E88
        self._run_out_the_hold(state)
        assert (state.levelnum_current, state.mazenum_current) == (13, 41)

    def test_a_treasure_room_does_not_consume_a_level_number(self):
        state = self._level_12_with_a_hero()
        ex.player_exit_sequence(state, 0, state.players[0].mob_slot,
                                int(MazeObjIds.EXIT))
        self._run_out_the_hold(state)
        level_in_treasure_room = state.levelnum_current

        ex.player_exit_sequence(state, 0, state.players[0].mob_slot,
                                int(MazeObjIds.EXIT))
        self._run_out_the_hold(state)
        assert state.levelnum_current == level_in_treasure_room


# ---------------------------------------------------------------------------
# player_start_inner (0x48BEC) -- positioned spawn (I-08)
# ---------------------------------------------------------------------------

class TestPlayerStartInner:
    def test_no_maze_returns_zero(self):
        state = GameState()
        assert state.maze is None
        assert gp.player_start_inner(state, 0) == 0

    def test_spawns_at_playerstart_and_sets_camera_arrays(self):
        state = GameState()
        state.maze = object()                           # dummy: just not None
        slot = pack_slot(8, 8)
        state.maze_player_start_slot = slot

        assert gp.player_start_inner(state, 0) == -1
        p = state.players[0]
        assert p.mob_slot == slot
        assert p.direction == 2                         # facing down
        assert state.player_in_maze[0] == 1
        assert state.player_tile_or_tport_dest[0] == slot
        assert state.level_players_active == 1

    def test_second_player_takes_a_distinct_start(self):
        state = GameState()
        state.maze = object()
        slot_a = pack_slot(5, 5)
        expected = pack_slot(5, 4)
        # Player 0 already spawned and active at slot_a.
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
        state.players[0].mob_slot = slot_a
        state.level_players_active = 1

        assert gp.player_start_inner(state, 1) == -1
        assert state.players[1].mob_slot == expected

    @requires_roms
    def test_post_death_continue_reuses_saved_start_and_snaps_camera(self):
        from gauntpy import maze
        from gauntpy.coords import slot_to_pixels
        from gauntpy.subsystems.camera import viewport_scroll

        state = GameState(game_mode=GameMode.NORMAL)
        maze.load_level(state, 2)
        start = state.maze_player_start_slot
        assert start
        assert gp.player_start_inner(state, 0) == -1
        state.mobs.unlink_and_clear(state.players[0].mob_slot)
        gp.player_resetcounters(state, 0)
        state.level_players_active = 0
        state.scroll_x = 300
        state.scroll_y = 300

        sess.player_coindrop(state, 0)
        state.debounce_shift_magic[0] = 0x1C
        sess.main_start_game(state)

        player = state.players[0]
        assert player.status == int(PlayerStatus.ALIVE_HERE)
        assert player.mob_slot == start
        assert state.mobs.picture[start] != 0
        assert state.player_in_maze[0] == 1
        scroll_x, scroll_y = viewport_scroll(state, 232, 240)
        player_x, player_y = slot_to_pixels(start)
        assert (player_x - scroll_x) % 512 < 232
        assert (player_y - scroll_y) % 512 < 240


# ---------------------------------------------------------------------------
# player_create_shot (0x53666) -- firing (N-02)
# ---------------------------------------------------------------------------

def _firing_player(state: GameState, index: int, direction: int) -> int:
    slot = pack_slot(9, 9)
    state.mobs.create(slot, tile=0x1e0d, hpos=encode_hpos(9 * 16),
                      vpos=encode_vpos_at_y(9 * 16), obj_type=int(MazeObjIds.PLAYERSTART))
    p = state.players[index]
    p.status = int(PlayerStatus.ALIVE_HERE)
    p.mob_slot = slot
    p.direction = direction
    return slot


class TestFrontEndFlow:
    """attract -> coin -> character select -> Magic start -> spawned in level 1,
    driven entirely through the real per-frame loop (`tick`)."""

    def test_start_attract_to_game_loads_level_1(self):
        """The attract->game transition sets NORMAL and (with ROMs) loads
        level 1 = maze 0; without ROMs it still makes the mode transition."""
        state = GameState()
        assert state.game_mode == GameMode.TITLE
        sess.start_attract_to_game(state)
        assert state.game_mode == GameMode.NORMAL
        if _ROMS_EXIST:
            assert state.levelnum_current == 1
            assert state.mazenum_current == 0
            assert state.maze is not None

    @requires_roms
    def test_coin_select_start_spawns_hero_in_level_1(self):
        state = GameState()                       # boots into TITLE attract
        assert state.game_mode == GameMode.TITLE

        # 1. Insert a coin: leaves attract, loads level 1, player 0 -> SELECTING.
        state.coin_counters = 1
        tick(state)
        assert state.game_mode == GameMode.NORMAL
        assert (state.levelnum_current, state.mazenum_current) == (1, 0)
        assert state.maze is not None
        assert state.players[0].status == int(PlayerStatus.SELECTING)

        # 2. Character select: hold RIGHT (active low) to choose the Elf.
        state.player_input_raw[0] = 0xFFFF & ~JOY_RIGHT
        tick(state)
        assert state.players[0].character == int(Character.ELF)

        # 3. Build a settled Magic press edge: >=3 released frames, then 2 held.
        state.player_input_raw[0] = 0xFFFF        # release everything
        tick(state)
        tick(state)
        state.player_input_raw[0] = 0xFFFF & ~JOY_MAGIC_BIT   # Magic held
        tick(state)                               # first held frame (pattern 0x1E)
        tick(state)                               # second held frame -> 0x1C edge -> commit

        # Committed and spawned into the loaded maze (I-08).
        p = state.players[0]
        assert p.status == int(PlayerStatus.ALIVE_HERE)
        assert p.character == int(Character.ELF)
        assert p.health == 100
        assert state.mobs.obj_type(p.mob_slot) == int(MazeObjIds.PLAYERSTART)
        assert state.level_players_active == 1


class TestPlayerCreateShot:
    def test_fires_into_own_channel_with_velocity_from_facing(self):
        state = GameState()
        _firing_player(state, 0, direction=0)           # facing right
        gp.player_create_shot(state, 0)

        shot_slot = 0 + SLOT_PLAYER_SHOTS.start         # slot 1
        assert state.mobs.picture[shot_slot] != 0
        assert state.shot_dx[shot_slot] == 3            # ROM 0x180 is 3 px
        assert state.shot_dy[shot_slot] == 0

    def test_only_one_shot_per_channel_at_a_time(self):
        state = GameState()
        _firing_player(state, 0, direction=0)
        gp.player_create_shot(state, 0)
        state.shot_dx[1] = 999                            # tamper to detect a re-fire
        gp.player_create_shot(state, 0)                  # channel busy -> no-op
        assert state.shot_dx[1] == 999

    def test_channel_rearms_after_it_clears(self):
        state = GameState()
        _firing_player(state, 0, direction=6)            # facing up
        gp.player_create_shot(state, 0)
        state.mobs.picture[1] = 0                         # shot expired (WP-7)
        gp.player_create_shot(state, 0)
        assert state.shot_dy[1] == 3                      # up: native V grows up

    def test_shot_speed_power_makes_shots_faster(self):
        state = GameState()
        _firing_player(state, 0, direction=0)
        state.players[0].powers |= gp._POWER_SHOTSPEED
        gp.player_create_shot(state, 0)
        assert state.shot_dx[1] == 4                      # ROM 0x200 is 4 px

    def test_diagonal_shot_is_slower_per_axis_than_cardinal(self):
        """The ROM's 0x100 diagonal component is 2 px in the native words."""
        state = GameState()
        _firing_player(state, 0, direction=1)            # down-right
        gp.player_create_shot(state, 0)
        assert (state.shot_dx[1], state.shot_dy[1]) == (2, -2)

    def test_shot_plays_character_sound_and_consumes_supershot(self):
        state = GameState()
        _firing_player(state, 0, direction=0)
        state.players[0].character = Character.WIZARD
        state.players[0].supershot = 2

        gp.player_create_shot(state, 0)

        assert state.sound_log[-1] == 0x46
        assert state.players[0].supershot == 1

    def test_player2_uses_channel_3(self):
        state = GameState()
        _firing_player(state, 2, direction=2)            # facing down
        gp.player_create_shot(state, 2)
        assert state.mobs.picture[3] != 0                # slot player_index+1
        assert state.shot_dy[3] == -4                    # down: native V falls


# ---------------------------------------------------------------------------
# Secret rooms end to end (§10.6) -- win a trick, play the challenge, come back
# ---------------------------------------------------------------------------

@requires_roms
class TestSecretRoomRoundTrip:
    """A won trick borrows the level for a challenge room and hands it back.

    Level N ends with somebody who satisfied the maze's trick standing in the
    exit -> ``show_level_start_screen`` swaps in maze 115/116 with a random
    challenge task -> the winner plays it alone and empty-handed -> the exit (or
    the clock) pays out and returns to the rotation maze, still as level N.
    """

    #: Maze 19's header trick is 14 (0x0E), "Don't Be Greedy (no treasure)" --
    #: the code the ROM's treasure arm compares at 0x519C2 -- so it is won by
    #: not picking any up and lost by a single ``treasure_collected``.
    _GREEDY_MAZE = 19
    #: Maze 6's header trick is 13 (0x0D), the *food* code the ROM compares in
    #: player_tile_interact's food arms (0x51C0C/0x51CEE). Kept alongside so the
    #: two neighbouring codes cannot be swapped without a test noticing.
    _DIET_MAZE = 6
    #: Maze 11's header trick is 5, "Watch What You Shoot (foods)", won by two
    #: recorded hits.
    _SHOOT_MAZE = 11

    def _level_12(self, maze_number: int) -> GameState:
        from gauntpy import maze

        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.levelnum_current = 12
        state.secret_possible_counter = 0       # a trick is due this level
        state.level_next_treasure = 4           # but a treasure room is not
        maze.load_level(state, 12, maze_number=maze_number)
        ex.exit_scan_level(state)
        ex.secret_new_level_setup(state)
        assert gp.player_start_inner(state, 0) == -1
        state.secret_tricks_flags[0] = 0       # true next-level survivor path
        p = state.players[0]
        p.coin_count = 1
        p.health = 500
        p.keysnum, p.potionsnum, p.supershot = 3, 2, 5
        return state

    def _hold(self, state: GameState) -> None:
        """Finish the exit dissolve, then sit out the bonus display."""
        _run_exit_animation(state)
        while state.global_ui_delay_timer > 0:
            sess.main_start_game(state)

    @staticmethod
    def _secret_exit(state: GameState) -> int:
        return next(
            slot for slot in range(32, len(state.mobs.link))
            if state.mobs.obj_type(slot) == int(MazeObjIds.EXIT)
        )

    def test_no_treasure_trick_wins_and_opens_a_secret_room(self):
        state = self._level_12(self._GREEDY_MAZE)
        assert state.trick_tasknum == ex.TRICK_NO_TREASURE == 0x0E
        p = state.players[0]

        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == 0, "the trick was satisfied at the exit"
        _run_exit_animation(state)
        assert state.secret_possible_start == 35, "a win pushes the reload up"
        assert state.level_next == 13

        self._hold(state)
        assert state.mazenum_current in (115, 116)
        assert state.levelnum_current == 13
        assert ex.CHALLENGE_FIRST <= state.trick_tasknum <= 0x5D
        assert state.trick_last == ex.TRICK_NO_TREASURE
        assert state.treasure_timer > 0
        # Only the winner is inside, and their inventory is at the door.
        assert p.status == int(PlayerStatus.ALIVE_HERE)
        assert (p.keysnum, p.potionsnum, p.supershot) == (0, 0, 0)
        assert (state.secret_saved_keys, state.secret_saved_potions,
                state.secret_saved_supershot) == (3, 2, 5)
        assert state.level_players_active == 1

    def test_completing_the_challenge_pays_and_returns_to_the_rotation(self):
        state = self._level_12(self._GREEDY_MAZE)
        p = state.players[0]
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        rotation_maze = state.maze_next
        self._hold(state)

        state.trick_tasknum = 0x54            # an unconditional task
        ex.player_exit_sequence(
            state, 0, self._secret_exit(state), int(MazeObjIds.EXIT),
        )
        _run_exit_animation(state)
        assert state.bonus_amount == ex._SECRET_ROOM_BONUS
        assert p.score == ex._SECRET_ROOM_BONUS
        assert (p.keysnum, p.potionsnum, p.supershot) == (3, 2, 5), "stash returned"
        assert state.trick_player == -1

        self._hold(state)
        assert (state.levelnum_current, state.mazenum_current) == (13, rotation_maze)
        assert state.game_mode == int(GameMode.NORMAL)
        assert p.status == int(PlayerStatus.ALIVE_HERE)
        assert state.trick_tasknum == ex.TRICK_NONE, "the challenge is over"

    def test_running_the_challenge_clock_out_returns_with_no_bonus(self):
        state = self._level_12(self._GREEDY_MAZE)
        p = state.players[0]
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        rotation_maze = state.maze_next
        self._hold(state)

        while state.treasure_timer > 0:
            ex.main_treasure_timer(state)
        assert state.game_mode == int(GameMode.TREAS_EXIT)
        assert state.bonus_amount == 0, "never reached the exit"

        self._hold(state)
        assert (state.levelnum_current, state.mazenum_current) == (13, rotation_maze)
        assert (p.keysnum, p.potionsnum, p.supershot) == (3, 2, 5)

    def test_a_shooting_trick_wins_the_same_way(self):
        state = self._level_12(self._SHOOT_MAZE)
        assert state.trick_tasknum == ex.TRICK_WATCHSHOOT1
        p = state.players[0]

        ex.secret_trick_progress(state, 0, ex.TRICK_WATCHSHOOT1)
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == -1, "one shot is not enough"

        state = self._level_12(self._SHOOT_MAZE)
        p = state.players[0]
        for _ in range(2):
            ex.secret_trick_progress(state, 0, ex.TRICK_WATCHSHOOT1)
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == 0
        self._hold(state)
        assert state.mazenum_current in (115, 116)

    def test_a_lost_trick_leaves_the_rotation_alone_and_paces_down(self):
        state = self._level_12(self._GREEDY_MAZE)
        p = state.players[0]
        ex.treasure_collected(state, 0)         # greedy!
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == -1
        _run_exit_animation(state)
        assert state.secret_possible_start == 18, "a miss pulls the reload down"

        self._hold(state)
        assert state.levelnum_current == 13
        assert state.mazenum_current < 104, "no bonus room was opened"

    def test_treasure_and_food_objectives_do_not_cross_report(self):
        """The neighbouring codes 0x0D and 0x0E come from different ROM arms.

        Maze 6's trick is the food code, so a treasure pickup must not touch it;
        maze 19's is the treasure code, so eating must not touch that one.
        """
        state = self._level_12(self._DIET_MAZE)
        assert state.trick_tasknum == ex.TRICK_NO_FOOD == 0x0D
        p = state.players[0]
        ex.treasure_collected(state, 0)
        assert state.secret_tricks_flags[0] == 0
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == 0, "taking treasure is not eating"

        state = self._level_12(self._GREEDY_MAZE)
        p = state.players[0]
        ex.secret_trick_progress(state, 0, ex.TRICK_NO_FOOD)   # WP-6's food hook
        assert state.secret_tricks_flags[0] == 0
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == 0, "eating is not taking treasure"

    def test_a_food_trick_is_lost_by_eating(self):
        state = self._level_12(self._DIET_MAZE)
        p = state.players[0]
        ex.secret_trick_progress(state, 0, ex.TRICK_NO_FOOD)   # 0x51CEE
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        assert state.trick_player == -1

    def test_the_next_level_gets_a_fresh_objective(self):
        """secret_new_level_setup runs on the return maze, so the trick and the
        winner slot do not leak across levels."""
        state = self._level_12(self._GREEDY_MAZE)
        p = state.players[0]
        ex.player_exit_sequence(state, 0, p.mob_slot, int(MazeObjIds.EXIT))
        self._hold(state)                        # into the secret room
        state.trick_tasknum = 0x54
        ex.player_exit_sequence(
            state, 0, self._secret_exit(state), int(MazeObjIds.EXIT),
        )
        self._hold(state)                        # back to the rotation

        assert state.trick_player == -1
        assert state.trick_tasknum == ex.TRICK_NONE
        assert state.secret_tricks_flags[0] == 0
