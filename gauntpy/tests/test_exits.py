"""WP-15 tests: exits, treasure rooms, and the treasure rotation.

Acceptance criteria (PLAN §6, WP-15 brief):
  1. main_treasure_timer: timer decrements by 1 each frame.
  2. main_treasure_timer: timer reaching 0 -> level-end bonus transition fires
     (game_mode changes to TREAS_EXIT when at least one player is present).
  3. main_treasure_timer: countdown logic fires at correct 60-frame intervals.
  4. main_treasure_timer: timer == 0 at entry -> no-op (already expired /
     not in a treasure room).
  5. main_exit_move: level_flags_3 ExitMoves bit clear -> timer not decremented,
     no sound emitted.
  6. main_exit_move: ExitMoves bit set, timer expires -> sound 0x31 emitted
     (§11.1 sends it straight to the board, so it lands in sound_log).
  7. main_exit_move: timer reloads to 0x12C after firing.

Plus the ROM behaviour the first pass reduced or got backwards:

  * the countdown speech table at 0x5AB64 is indexed *directly by the seconds
    remaining* (ZERO, ONE, ... TEN), not in reverse;
  * the fake countdown / six-second warning / timeout announcements
    (0x5AB90/0x5AC08/0x5ABF8) and their delay counter;
  * main_treasure_timer's four entry gates (0x4D2B2-0x4D2D8);
  * treasure-room scheduling: show_level_start_screen's 0x44E92-0x44F32 block,
    the treas_mazerand_* rotation, and the return to the displaced rotation maze
    (doc/06 §3.5);
  * main_exit_move walking the level's exit list rather than a no-op
    "relocate to a random cell" stub.

Reference: doc/04_game_subsystems.md §12, §16; doc/06_maze_catalog.md §3.5;
doc/05_data_reference.md §5.5.
"""

from __future__ import annotations

from gauntpy.constants import GameMode, MazeObjIds, PlayerStatus
from gauntpy.coords import encode_hpos, encode_vpos_at_y
from gauntpy.playfield_vram import (
    EXIT_SETTLED_DESC,
    exit_descriptor,
    read_tile_descriptor,
    write_tile_descriptor,
)
from gauntpy.rng import GameRandom
from gauntpy.state import GameState
from gauntpy.subsystems.exits import (
    _EXIT_ANIM_SETTLE,
    _EXIT_FAKE_MARK,
    _EXIT_MOVE_TIMER_RELOAD,
    _LFLAG3_EXIT_CHOOSEONE,
    _LFLAG3_EXIT_MOVES,
    _LFLAG4_EXIT_FAKE,
    _SECRET_ROOM_BONUS,
    _SECRET_START_MAX,
    _SECRET_START_MIN,
    _TREASURE_FAKE_COUNTDOWN,
    _TREASURE_ROOM_DURATION,
    _TREASURE_SECONDS_SPEECH,
    _TREASURE_TIMEOUT_SPEECH,
    _TREASURE_WARNING_SPEECH,
    CHALLENGE_COUNT,
    CHALLENGE_FIRST,
    TRICK_BEPUSHY,
    TRICK_DIET,
    TRICK_IT,
    TRICK_NOGETHIT,
    TRICK_NOGREEDY1,
    TRICK_NOGREEDY2,
    TRICK_NOHURTFRIENDS,
    TRICK_NONE,
    TRICK_NOUSEINVUL,
    TRICK_NO_FOOD,
    TRICK_NO_TREASURE,
    TRICK_SAVESUPERSHOTS,
    TRICK_TRANSPORT1,
    TRICK_WATCHSHOOT1,
    TRICK_WATCHSHOOT2,
    advance_level_countdowns,
    exit_get_id,
    exit_scan_level,
    main_exit_move,
    main_treasure_timer,
    maze_pick_one_exit,
    player_exit_sequence,
    secret_check,
    secret_check_winner,
    secret_new_level_setup,
    secret_trick_check,
    secret_trick_progress,
    secret_trick_set,
    show_level_end_bonus_screen,
    show_level_start_screen,
    treasure_collected,
)

_TREASURE_MAZE = 104


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_exit_animation(state: GameState, frames: int = 96) -> None:
    """Play out the status-8 exit dissolve (main_move_players 0x4A646-0x4A6E6).

    ``player_exit_sequence`` (0x52B40) only *starts* it: the hero sits in status
    8 for the ~32-frame animation and the level ends when the last one
    completes.  Tests that care about what happens after the exit therefore
    have to run those frames.  The mode is forced out of attract because the
    player loop is gated on it (0x4A53A).
    """
    from gauntpy.subsystems.players import main_move_players

    if state.game_mode < 0:
        state.game_mode = int(GameMode.NORMAL)
    for _ in range(frames):
        if not any(p.exit_pending for p in state.players):
            return
        main_move_players(state)
    raise AssertionError("the exit animation never finished")


def _treasure_state(timer: int, *, player_alive: bool = True) -> GameState:
    """GameState inside a treasure room with treasure_timer set.

    main_treasure_timer only runs in NORMAL, in a maze >= 104 (0x4D2C6/0x4D2D0),
    so the fixture has to put the state there.
    """
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.mazenum_current = _TREASURE_MAZE
    state.treasure_timer = timer
    if player_alive:
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
    return state


def _exit_at(state: GameState, slot: int) -> None:
    px, py = (slot % 32) * 16, (slot // 32) * 16
    state.mobs.create(slot, tile=0x8001, hpos=encode_hpos(px), vpos=encode_vpos_at_y(py),
                      obj_type=int(MazeObjIds.EXIT))


def _exit_moves_state(*, timer: int = _EXIT_MOVE_TIMER_RELOAD,
                      exits: tuple[int, ...] = (100, 200)) -> GameState:
    """GameState with the ExitMoves flag set and a scanned exit list.

    ``maze_pick_one_exit`` picks the real exit with ``getrandom(count)`` and
    removes the losers, so the fixture seeds the RNG to pick index 0 and sets the
    FakeExit flag, which keeps the other exit tiles in the maze (0x43EAC) for the
    relocation tests to land on.
    """
    state = GameState()
    state.level_flags_3 = _LFLAG3_EXIT_MOVES
    state.level_flags_4 = _LFLAG4_EXIT_FAKE
    state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(max(1, len(exits))))
    for slot in exits:
        _exit_at(state, slot)
    exit_scan_level(state)
    state.level_players_active = 1
    state.exit_move_timer = timer
    return state


# ---------------------------------------------------------------------------
# main_treasure_timer -- gates
# ---------------------------------------------------------------------------

class TestTreasureTimerGates:
    """0x4D2B2-0x4D2D8: four things must be true before the countdown runs."""

    def test_bonus_hold_freezes_the_countdown(self):
        """global_ui_delay_timer (bonus_timer) nonzero -> countdown frozen."""
        state = _treasure_state(300)
        state.bonus_timer = 5
        main_treasure_timer(state)
        assert state.treasure_timer == 300
        assert state.bonus_timer == 5, "main_start_game owns the shared timer"

    def test_attract_mode_does_not_count_down(self):
        state = _treasure_state(300)
        state.game_mode = GameMode.TITLE
        main_treasure_timer(state)
        assert state.treasure_timer == 300

    def test_outside_a_bonus_room_does_not_count_down(self):
        """mazenum_current < 104 -> not a treasure/secret room (0x4D2D0)."""
        state = _treasure_state(300)
        state.mazenum_current = 42
        main_treasure_timer(state)
        assert state.treasure_timer == 300

    def test_secret_room_still_counts_down(self):
        """The gate is >= 104, so secret rooms 115/116 run the timer too."""
        state = _treasure_state(300)
        state.mazenum_current = 115
        main_treasure_timer(state)
        assert state.treasure_timer == 299


# ---------------------------------------------------------------------------
# main_treasure_timer -- countdown
# ---------------------------------------------------------------------------

class TestTreasureTimer:

    def test_timer_decrements_each_frame(self):
        """Criterion 1: timer counts down by 1 every call."""
        state = _treasure_state(300)
        main_treasure_timer(state)
        assert state.treasure_timer == 299
        main_treasure_timer(state)
        assert state.treasure_timer == 298

    def test_updates_the_large_status_countdown_each_second(self):
        state = _treasure_state(61)

        main_treasure_timer(state)

        assert state.treasure_timer == 60
        assert state.alpha_ram[2 * 64 + 36] & 0x3FF

    def test_timeout_triggers_bonus_transition(self):
        """Criterion 2: timer reaching 0 sets game_mode to TREAS_EXIT when
        at least one player is active."""
        state = _treasure_state(1)                      # one frame left
        assert state.game_mode != GameMode.TREAS_EXIT   # pre-condition
        main_treasure_timer(state)                       # decrements -> 0
        assert state.treasure_timer == 0
        assert state.game_mode == GameMode.TREAS_EXIT

    def test_timeout_no_players_skips_bonus_transition(self):
        """Criterion 2 (edge): no active players -> bonus screen NOT called."""
        state = _treasure_state(1, player_alive=False)
        main_treasure_timer(state)
        assert state.treasure_timer == 0
        assert state.game_mode != GameMode.TREAS_EXIT

    def test_per_second_tick_fires_at_60_frame_intervals(self):
        """Criterion 3: countdown logic fires at exact multiples of 60 frames."""
        state = _treasure_state(120)

        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 60
        assert state.treasure_timer % 60 == 0   # confirms tick boundary

        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 0
        assert state.game_mode == GameMode.TREAS_EXIT

    def test_expired_timer_is_noop(self):
        """Criterion 4: treasure_timer == 0 at entry -> function does nothing."""
        state = _treasure_state(0)
        initial_mode = state.game_mode
        main_treasure_timer(state)
        assert state.treasure_timer == 0        # did not go negative
        assert state.game_mode == initial_mode  # no transition

    def test_negative_timer_is_noop(self):
        state = _treasure_state(-1)
        main_treasure_timer(state)
        assert state.treasure_timer == -1

    def test_multiple_active_players_counted(self):
        """player_activecount (0x4D900) counts statuses 1, 2, 8 and 0x10."""
        state = _treasure_state(1, player_alive=False)
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.players[1].status = int(PlayerStatus.RESPAWN_WAIT)
        state.players[2].status = int(PlayerStatus.SELECTING)
        main_treasure_timer(state)
        assert state.game_mode == GameMode.TREAS_EXIT


# ---------------------------------------------------------------------------
# Countdown speech -- doc/05_data_reference.md §5.5
# ---------------------------------------------------------------------------

class TestCountdownSpeech:

    def test_seconds_table_is_direct_indexed_zero_to_ten(self):
        """0x5AB64 is indexed by the seconds remaining, not by 10 - seconds.

        The first port read it backwards, so the machine said "ZERO" with ten
        seconds left and "TEN" as time ran out.
        """
        assert _TREASURE_SECONDS_SPEECH[0] == 0x54    # ZERO
        assert _TREASURE_SECONDS_SPEECH[1] == 0x4A    # ONE
        assert _TREASURE_SECONDS_SPEECH[9] == 0x52    # NINE
        assert _TREASURE_SECONDS_SPEECH[10] == 0x53   # TEN

    def test_one_second_left_says_one(self):
        state = _treasure_state(120)
        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 60
        assert 0x4A in state.sound_log, "'ONE' is spoken with one second left"

    def test_ten_seconds_left_says_ten(self):
        state = _treasure_state(11 * 60)
        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 10 * 60
        assert 0x53 in state.sound_log, "'TEN' is spoken with ten seconds left"

    def test_timeout_speaks_a_parting_shot(self):
        """At zero the ROM picks from treasure_timeout_speech (0x5ABF8)."""
        state = _treasure_state(60)
        state.sound_log.clear()
        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 0
        spoken = [s for s in state.sound_log if s in _TREASURE_TIMEOUT_SPEECH]
        assert spoken, "one of ZERO / BETTER LUCK / LOOKS LIKE YOU LOSE"

    def test_speech_disable_bit_forces_element_zero(self):
        """game_settings bit 11 pins the timeout announcement to ZERO."""
        state = _treasure_state(60)
        state.game_settings = 0x800
        state.sound_log.clear()
        for _ in range(60):
            main_treasure_timer(state)
        assert 0x54 in state.sound_log           # ZERO
        assert 0xA0 not in state.sound_log
        assert 0xA7 not in state.sound_log

    def test_fake_countdown_lies_about_the_time(self):
        """Above level 30 a 1-in-16 roll arms one of the scrambled sequences.

        The RNG seed below is chosen so the ten-second roll lands on 0; the
        assertion is that the number spoken then comes from the fake table
        rather than the true one.
        """
        state = _treasure_state(11 * 60)
        state.levelnum_current = 40
        seed = _seed_where_first_draw_is_zero(0x10)
        state.rng = GameRandom(seed=seed)
        state.sound_log.clear()
        for _ in range(60):
            main_treasure_timer(state)

        assert state.treasure_voice_set != 0, "the fake countdown must be armed"
        fake = _TREASURE_FAKE_COUNTDOWN[state.treasure_voice_set - 1]
        assert fake[4] in state.sound_log          # displayed second 10
        assert _TREASURE_SECONDS_SPEECH[10] not in state.sound_log

    def test_fake_countdown_owns_up_at_six_seconds(self):
        state = _treasure_state(7 * 60)
        state.treasure_voice_set = 1
        state.sound_log.clear()
        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 6 * 60
        assert 0xA5 in state.sound_log or 0xA6 in state.sound_log
        assert state.treasure_voice_set == 0
        assert state.treasure_announcement_delay == 1

    def test_announcement_delay_silences_the_next_second(self):
        state = _treasure_state(5 * 60)
        state.treasure_announcement_delay = 2
        state.sound_log.clear()
        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_announcement_delay == 1
        assert state.sound_log == []

    def test_six_second_warning_sets_its_delay(self):
        """A 1-in-4 roll swaps "SIX" for a taunt from 0x5AC08 (0x4D3D4)."""
        state = _treasure_state(7 * 60)
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(4))
        state.sound_log.clear()
        for _ in range(60):
            main_treasure_timer(state)
        assert state.treasure_timer == 6 * 60
        assert any(s in _TREASURE_WARNING_SPEECH for s in state.sound_log)
        assert state.treasure_announcement_delay in (1, 2)


def _seed_where_first_draw_is_zero(bound: int) -> int:
    """Find a seed whose very next ``getrandom(bound)`` returns 0."""
    return _seed_where_draw_is(bound, 0)


def _seed_where_draw_is(bound: int, want: int) -> int:
    """Find a seed whose very next ``getrandom(bound)`` returns *want*."""
    for seed in range(0x10000):
        if GameRandom(seed=seed).getrandom(bound) == want:
            return seed
    raise AssertionError("no seed produces that draw")   # pragma: no cover


# ---------------------------------------------------------------------------
# Treasure-room scheduling (doc/06 §3.5)
# ---------------------------------------------------------------------------

class TestTreasureScheduling:

    def test_countdown_ticks_once_per_level(self):
        """advance_level_countdowns is main_move_players 0x4A748-0x4A788."""
        state = GameState()
        state.mazenum_current = 40
        state.level_next = 9
        state.level_next_treasure = 3
        state.level_next_potion = 2
        state.secret_possible_counter = 20
        advance_level_countdowns(state)
        assert state.level_next_treasure == 2
        assert state.level_next_potion == 1
        assert state.secret_possible_counter == 19

    def test_countdown_is_not_ticked_in_a_bonus_room(self):
        state = GameState()
        state.mazenum_current = _TREASURE_MAZE
        state.level_next = 9
        state.level_next_treasure = 3
        advance_level_countdowns(state)
        assert state.level_next_treasure == 3

    def test_countdown_is_not_ticked_in_the_opening_act(self):
        """level_next <= 6 -> the countdown does not start (0x4A760)."""
        state = GameState()
        state.mazenum_current = 3
        state.level_next = 5
        state.level_next_treasure = 3
        advance_level_countdowns(state)
        assert state.level_next_treasure == 3

    def test_level_six_seeds_the_countdown(self):
        """maze_new_level_setup 0x438E4: getrandom(3) + 3 at level 6."""
        state = GameState()
        state.levelnum_current = 6
        state.level_next_treasure = 0
        show_level_start_screen(state)
        assert 3 <= state.level_next_treasure <= 5

    def test_countdown_zero_hijacks_the_level_into_a_treasure_room(self):
        state = GameState()
        state.levelnum_current, state.mazenum_current = 12, 40
        state.maze_next, state.level_next = 40, 12
        state.level_next_treasure = 0
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)

        show_level_start_screen(state)

        assert state.mazenum_current == 104            # treas_mazerand_num
        assert state.maze_next == 40, "the displaced rotation maze is kept"
        assert 3 <= state.level_next_treasure <= 5
        # treasure_room_duration[0] + 1 for a single active player.
        assert state.treasure_timer == _TREASURE_ROOM_DURATION[0] + 1

    def test_duration_grows_with_the_party(self):
        state = GameState()
        state.levelnum_current, state.level_next_treasure = 12, 0
        for i in range(3):
            state.players[i].status = int(PlayerStatus.ALIVE_HERE)
        show_level_start_screen(state)
        assert state.treasure_timer == _TREASURE_ROOM_DURATION[2] + 1

    def test_rotation_advances_by_adder_plus_one(self):
        state = GameState()
        state.levelnum_current, state.level_next_treasure = 12, 0
        state.treas_mazerand_num, state.treas_mazerand_adder = 104, 2
        show_level_start_screen(state)
        assert state.mazenum_current == 104
        assert state.treas_mazerand_num == 107        # 104 + 2 + 1

    def test_rotation_wraps_past_114_and_bumps_the_adder(self):
        """114 -> +1 -> 115 -> -11 -> 104, which bumps the adder (0x44EFC)."""
        state = GameState()
        state.levelnum_current, state.level_next_treasure = 12, 0
        state.treas_mazerand_num, state.treas_mazerand_adder = 114, 0
        show_level_start_screen(state)
        assert state.mazenum_current == 114
        assert state.treas_mazerand_num == 104
        assert state.treas_mazerand_adder == 1

    def test_rotation_wrap_that_misses_104_leaves_the_adder(self):
        state = GameState()
        state.levelnum_current, state.level_next_treasure = 12, 0
        state.treas_mazerand_num, state.treas_mazerand_adder = 113, 3
        show_level_start_screen(state)
        assert state.treas_mazerand_num == 106        # 113 + 4 = 117 - 11
        assert state.treas_mazerand_adder == 3

    def test_no_treasure_room_before_level_seven(self):
        state = GameState()
        state.levelnum_current, state.mazenum_current = 5, 4
        state.level_next_treasure = 0
        show_level_start_screen(state)
        assert state.mazenum_current == 4
        assert state.treasure_timer == 0

    def test_leaving_a_treasure_room_keeps_the_saved_position(self):
        """player_exit_sequence skips the next-level computation at 0x52DBA."""
        state = GameState()
        state.levelnum_current, state.mazenum_current = 12, _TREASURE_MAZE
        state.level_next, state.maze_next = 12, 40
        state.maze_stride = 0
        state.treasure_timer = 500
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
        state.players[0].mob_slot = 0

        player_exit_sequence(state, 0, 0, int(MazeObjIds.EXIT))

        assert state.level_next == 12                  # level number not consumed
        assert state.maze_next == 40                   # displaced rotation maze
        assert state.treasure_timer == 0               # 0x52E88
        # The exit animation has to run out before the level actually ends.
        assert state.mazenum_current == _TREASURE_MAZE
        _run_exit_animation(state)
        assert state.levelnum_current == 12
        assert state.mazenum_current == 40             # committed by the bonus screen

    def test_treasure_timer_survives_while_another_player_is_inside(self):
        state = GameState()
        state.mazenum_current = _TREASURE_MAZE
        state.treasure_timer = 500
        for i in (0, 1):
            state.players[i].status = int(PlayerStatus.ALIVE_HERE)
        player_exit_sequence(state, 0, 0, int(MazeObjIds.EXIT))
        assert state.treasure_timer == 500


# ---------------------------------------------------------------------------
# main_exit_move -- the moving exit
# ---------------------------------------------------------------------------

class TestExitScan:

    def test_scan_collects_every_exit_tile(self):
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        state.level_flags_4 = _LFLAG4_EXIT_FAKE          # keep the losers alive
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(3))
        for slot in (64, 300, 700):
            _exit_at(state, slot)
        exit_scan_level(state)
        assert state.exit_slots == [64, 300, 700]
        assert state.exit_open_id == 64                  # getrandom(3) -> 0
        assert state.exit_move_timer == _EXIT_MOVE_TIMER_RELOAD

    def test_scan_ignores_the_reserved_row(self):
        """The ROM's own scan starts at slot 0x20 (moveq #$20,d3 at 0x43DA6)."""
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        _exit_at(state, 4)                               # inside the row-0 fill
        _exit_at(state, 64)
        _exit_at(state, 300)
        exit_scan_level(state)
        assert state.exit_slots == [64, 300]

    def test_scan_clears_the_open_exit_without_the_flag(self):
        """maze_new_level_setup 0x43B9A: no ExitMoves -> exit_open_id = 0, and
        0x43B6A skips the pick entirely, so both exits survive."""
        state = GameState()
        _exit_at(state, 64)
        _exit_at(state, 300)
        exit_scan_level(state)
        assert state.exit_slots == [64, 300]
        assert state.exit_open_id == 0
        assert state.mobs.obj_type(300) == int(MazeObjIds.EXIT)

    def test_an_ordinary_maze_keeps_every_exit(self):
        """0x43B62-0x43B72 gates the pick on ExitMoves | Exit1of."""
        state = GameState()
        seed_before = state.rng.seed
        for slot in (64, 300, 700):
            _exit_at(state, slot)
        exit_scan_level(state)
        assert all(state.mobs.obj_type(s) == int(MazeObjIds.EXIT)
                   for s in (64, 300, 700))
        assert state.rng.seed == seed_before, "no pick means no RNG draw"

    def test_exit1of_alone_also_picks(self):
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_CHOOSEONE
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(2))
        for slot in (64, 300):
            _exit_at(state, slot)
        exit_scan_level(state)
        assert state.exit_open_id == 0, "no ExitMoves -> the exit does not move"
        assert not state.mobs.is_occupied(300), "only one exit is real"

    def test_scan_is_idempotent(self):
        """The common level-load path and the transition path may both call it.

        The pick removes the losing exits, so a second scan must not treat the
        survivor as "the level's only exit" and disarm ExitMoves.
        """
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(3))
        for slot in (64, 300, 700):
            _exit_at(state, slot)

        exit_scan_level(state)
        first = (list(state.exit_slots), state.exit_open_id)
        assert not state.mobs.is_occupied(300)   # losers removed (Exit1of)

        exit_scan_level(state)
        exit_scan_level(state)
        assert list(state.exit_slots) == first[0]
        assert state.exit_open_id == first[1]
        assert state.level_flags_3 & _LFLAG3_EXIT_MOVES

    def test_a_new_maze_is_rescanned(self):
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(2))
        for slot in (64, 300):
            _exit_at(state, slot)
        exit_scan_level(state)
        assert state.exit_open_id == 64

        state.mobs = GameState().mobs            # next level's MOB table
        for slot in (500, 600):
            _exit_at(state, slot)
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(2))
        exit_scan_level(state)
        assert state.exit_slots == [500, 600]
        assert state.exit_open_id == 500

    def test_exit_get_id_returns_the_count_when_absent(self):
        state = GameState()
        state.exit_slots = [10, 20]
        assert exit_get_id(state, 20) == 1
        assert exit_get_id(state, 999) == 2


class TestExitOneOf:
    """maze_pick_one_exit (0x43D8C called with 0) -- which exit is real."""

    def _three_exits(self, *, fake: bool, seed_bound: int = 3) -> GameState:
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        if fake:
            state.level_flags_4 = _LFLAG4_EXIT_FAKE
        state.rng = GameRandom(seed=_seed_where_first_draw_is_zero(seed_bound))
        for slot in (64, 300, 700):
            _exit_at(state, slot)
        state.exit_slots = [64, 300, 700]
        return state

    def test_pick_is_random_not_the_first_slot(self):
        """0x43E2E: ``getrandom(exit_count)`` chooses; 0x43E8C stores its slot."""
        state = self._three_exits(fake=True)
        state.rng = GameRandom(seed=_seed_where_draw_is(3, 2))
        maze_pick_one_exit(state)
        assert state.exit_open_id == 700, "the third exit was drawn, not the first"

    def test_losing_exits_are_removed_without_the_fake_flag(self):
        """Exit1of: only one of several exits is real (0x43EBC mob_remove)."""
        state = self._three_exits(fake=False)
        maze_pick_one_exit(state)
        assert state.exit_open_id == 64
        assert state.mobs.obj_type(64) == int(MazeObjIds.EXIT)
        assert not state.mobs.is_occupied(300)
        assert not state.mobs.is_occupied(700)
        # The slot list still holds every exit the maze decoded (0x43A34).
        assert state.exit_slots == [64, 300, 700]

    def test_losing_exits_are_marked_fake_with_the_flag(self):
        """FakeExit (LFLAG4 bit 6): the decoys stay, marked at 0x43EAC."""
        state = self._three_exits(fake=True)
        maze_pick_one_exit(state)
        assert state.mobs.obj_type(300) == int(MazeObjIds.EXIT)
        assert state.mobs.hpos[300] & _EXIT_FAKE_MARK
        assert state.mobs.hpos[700] & _EXIT_FAKE_MARK
        assert not state.mobs.hpos[64] & _EXIT_FAKE_MARK

    def test_single_exit_clears_the_exitmoves_flag(self):
        """0x43ED4-0x43EE8: one exit means the level cannot have a moving exit."""
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        _exit_at(state, 64)
        exit_scan_level(state)
        assert not state.level_flags_3 & _LFLAG3_EXIT_MOVES
        assert state.exit_open_id == 0

    def test_no_exits_is_a_noop(self):
        state = GameState()
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        exit_scan_level(state)
        assert state.exit_slots == []
        assert state.exit_open_id == 0
        assert state.level_flags_3 & _LFLAG3_EXIT_MOVES


class TestExitMove:

    def test_no_open_exit_is_a_noop(self):
        """Criterion 5: without an open exit nothing happens (0x52890)."""
        state = GameState()
        state.level_flags_3 = 0
        initial_timer = state.exit_move_timer
        main_exit_move(state)
        assert state.exit_move_timer == initial_timer
        assert state.sound_log == []

    def test_partial_decrement_no_sound(self):
        """ExitMoves set but timer > 1: timer decrements, no sound yet."""
        state = _exit_moves_state(timer=10)
        main_exit_move(state)
        assert state.exit_move_timer == 9
        assert state.sound_log == []

    def test_timer_expiry_plays_sound_0x31(self):
        """Criterion 6: when exit_move_timer expires, sound 0x31 is emitted."""
        state = _exit_moves_state(timer=1)
        main_exit_move(state)
        assert 0x31 in state.sound_log

    def test_timer_reloads_value_is_300_frames(self):
        """The reload constant is 0x12C == 300 frames (0x52A74)."""
        assert _EXIT_MOVE_TIMER_RELOAD == 0x12C

    def test_only_one_sound_per_expiry(self):
        state = _exit_moves_state(timer=1)
        main_exit_move(state)
        assert state.sound_log.count(0x31) == 1

    def test_the_exit_tile_actually_moves(self):
        """The exit MOB is destroyed at the old slot and created at the new one.

        With two exits, exit_move_stride[2] = 1, so the open exit steps from the
        first recorded slot to the second.
        """
        state = _exit_moves_state(timer=1, exits=(100, 200))
        assert state.exit_open_id == 100
        main_exit_move(state)
        assert state.exit_open_id == 200
        assert state.exit_close_id == 100
        assert state.mobs.obj_type(200) == int(MazeObjIds.EXIT)
        assert not state.mobs.is_occupied(100)
        from gauntpy.maze import placement_geometry

        expected_h, expected_v = placement_geometry(int(MazeObjIds.EXIT), 200)
        assert state.mobs.hpos[200] == expected_h
        assert state.mobs.vpos[200] == expected_v

    def test_single_exit_maze_does_not_lose_its_exit(self):
        state = _exit_moves_state(timer=1, exits=(100,))
        state.exit_open_id = 100                 # 0x43EDE would have disarmed it
        state.level_flags_3 = _LFLAG3_EXIT_MOVES
        main_exit_move(state)
        assert state.exit_open_id == 100
        assert state.mobs.obj_type(100) == int(MazeObjIds.EXIT)

    def test_a_player_standing_on_the_destination_exits(self):
        """0x5293C-0x52958: the exit lands on a hero and takes them with it."""
        state = _exit_moves_state(timer=1, exits=(100, 200))
        p = state.players[0]
        p.status = int(PlayerStatus.ALIVE_HERE)
        p.mob_slot = 200
        state.player_in_maze[0] = 1

        main_exit_move(state)

        # 0x52C66 parks the hero in status 8 for the exit dissolve; only when
        # that finishes does it become ALIVE_NEXT (0x4A6B2).
        assert p.status == int(PlayerStatus.EXITING)
        assert state.movement_type == 1
        _run_exit_animation(state)
        assert p.status == int(PlayerStatus.ALIVE_NEXT)

    def test_entering_an_opening_exit_animates_at_its_new_location(self):
        from gauntpy.maze import placement_geometry

        state = _exit_moves_state(timer=1, exits=(100, 200))
        main_exit_move(state)
        player = state.players[0]
        player.status = int(PlayerStatus.ALIVE_HERE)
        player.mob_slot = 201
        state.level_players_active = 1
        hpos, vpos = placement_geometry(int(MazeObjIds.PLAYERSTART), 201)
        state.mobs.create(
            201, 0x1234, hpos, vpos, int(MazeObjIds.PLAYERSTART),
        )

        player_exit_sequence(state, 0, 200, int(MazeObjIds.EXIT))

        expected_h, expected_v = placement_geometry(int(MazeObjIds.EXIT), 200)
        assert state.mobs.hpos[21] & 0xFF80 == (expected_h - 0x200) & 0xFF80
        assert state.mobs.vpos[21] & 0xFF80 == expected_v & 0xFF80


class TestExitMoveAnimation:
    """0x52A5C-0x52AF8 -- the 32-frame open/close phase and the late reload."""

    def test_swap_does_not_reload_immediately(self):
        state = _exit_moves_state(timer=1)
        main_exit_move(state)
        assert state.exit_move_timer == 0, "the swap frame leaves the timer at 0"
        assert state.exit_anim_frame == 0

    def test_step_advances_only_every_fourth_frame(self):
        """0x52A62: ``exit_timer & 3`` gates the stamp update."""
        state = _exit_moves_state(timer=1)
        main_exit_move(state)                    # swap, timer 0
        seen = {}
        for _ in range(-_EXIT_ANIM_SETTLE - 1):
            main_exit_move(state)
            seen[state.exit_move_timer] = state.exit_anim_frame
        assert seen[-1] == 0 and seen[-2] == 0 and seen[-3] == 0
        assert seen[-4] == 1
        assert seen[-5] == 1 and seen[-7] == 1
        assert seen[-8] == 2
        assert seen[-28] == 7

    def test_settles_and_reloads_at_minus_32(self):
        state = _exit_moves_state(timer=1)
        main_exit_move(state)                    # swap
        for _ in range(-_EXIT_ANIM_SETTLE):
            main_exit_move(state)
        assert state.exit_move_timer == _EXIT_MOVE_TIMER_RELOAD
        assert state.exit_anim_frame == 0
        assert state.exit_close_id == 0

    def test_period_between_moves_is_332_frames(self):
        """0x12C for the wait plus 0x20 for the animation (0x52A6E/0x52A74)."""
        state = _exit_moves_state(timer=1)
        main_exit_move(state)                    # first move
        frames = 0
        while state.sound_log.count(0x31) < 2:
            main_exit_move(state)
            frames += 1
            assert frames < 1000, "the exit never moved again"
        assert frames == _EXIT_MOVE_TIMER_RELOAD - _EXIT_ANIM_SETTLE   # 332

    def test_animation_finishes_even_after_the_flag_is_cleared(self):
        """player_exit_sequence drops ExitMoves mid-animation (0x52EB4); the
        ``exit_timer <= 0`` half of the gate keeps the phase running."""
        state = _exit_moves_state(timer=1)
        main_exit_move(state)
        state.level_flags_3 = 0
        for _ in range(-_EXIT_ANIM_SETTLE):
            main_exit_move(state)
        assert state.exit_move_timer == _EXIT_MOVE_TIMER_RELOAD

    def test_relocation_only_writes_centres_and_settlement_draws_one_floor(self):
        class RecordingRng:
            def __init__(self):
                self.bounds = []

            def getrandom(self, bound):
                self.bounds.append(bound)
                return 0

        old_slot, new_slot = 100, 200
        state = _exit_moves_state(timer=1, exits=(old_slot, new_slot))
        state.maze = type("Maze", (), {
            "data": {
                (old_slot & 31, old_slot >> 5): int(MazeObjIds.EXIT),
                (new_slot & 31, new_slot >> 5): int(MazeObjIds.EXIT),
            },
            "floorpattern": 0,
            "wallpattern": 0,
        })()
        state.rng = RecordingRng()
        for variation in range(4):
            state.playfield_floor_catalog[(0, variation)] = (
                0x120 + variation,
            ) * 4
        neighbours = {
            slot: (0x500 + slot,) * 4
            for center in (old_slot, new_slot)
            for slot in (
                center - 33, center - 32, center - 31,
                center - 1, center + 1,
                center + 31, center + 32, center + 33,
            )
        }
        for slot, descriptor in neighbours.items():
            write_tile_descriptor(state, slot, descriptor)

        main_exit_move(state)

        assert state.rng.bounds == []
        assert read_tile_descriptor(state, old_slot) == exit_descriptor(0, 0)
        assert read_tile_descriptor(state, new_slot) == exit_descriptor(0, 8)
        assert all(
            read_tile_descriptor(state, slot) == descriptor
            for slot, descriptor in neighbours.items()
        )
        assert state.maze.data[(old_slot & 31, old_slot >> 5)] == int(
            MazeObjIds.TILE_FLOOR
        )
        assert state.maze.data[(new_slot & 31, new_slot >> 5)] == int(
            MazeObjIds.EXIT
        )

        for _ in range(-_EXIT_ANIM_SETTLE):
            main_exit_move(state)

        assert state.rng.bounds == [4]
        assert read_tile_descriptor(state, old_slot) == (0x120,) * 4
        assert read_tile_descriptor(state, new_slot) == EXIT_SETTLED_DESC
        assert all(
            read_tile_descriptor(state, slot) == descriptor
            for slot, descriptor in neighbours.items()
        )


# ---------------------------------------------------------------------------
# The level-end hold (show_level_end_bonus_screen, 0x4D476)
# ---------------------------------------------------------------------------

class TestLevelEndHold:

    def test_hold_is_300_frames(self):
        """global_ui_delay_timer = 0x12C at 0x4D50E."""
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        show_level_end_bonus_screen(state)
        assert state.bonus_timer == 0x12C
        assert state.game_mode == GameMode.TREAS_EXIT

    def test_leaving_a_treasure_room_fades_the_treasure_music(self):
        state = GameState()
        state.mazenum_current = _TREASURE_MAZE
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        show_level_end_bonus_screen(state)
        assert 0x39 in state.sound_log        # slow-motion silencer
        assert 0x41 in state.sound_log        # treasure-music fade

    def test_the_whole_info_panel_is_rebuilt_before_the_tally(self):
        """0x4D4DE rebuilds the panel, then 0x4D5AA marks the new scores dirty
        for main_score_display's own rotation."""
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.players[0].coin_count = 1
        for panel in state.info_panel.players:
            panel.score_drawn = False
        treasure_collected(state, 0)

        show_level_end_bonus_screen(state)

        assert all(p.score_drawn for p in state.info_panel.players)
        assert state.score_dirty[0] == 1, "the awarded score is still pending"

    def test_countdown_speech_is_parked_while_the_tally_shows(self):
        """0x4D4D6 loads -1 into the announcement delay."""
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        show_level_end_bonus_screen(state)
        assert state.treasure_announcement_delay == 0xFFFF
        assert state.treasure_voice_set == 0

    def test_level_start_screen_rebuilds_the_panel(self):
        """show_level_start_screen 0x44F38-0x44F3E."""
        state = GameState()
        state.levelnum_current = 8
        state.level_next_treasure = 2
        for panel in state.info_panel.players:
            panel.score_drawn = False
        show_level_start_screen(state)
        assert all(p.score_drawn for p in state.info_panel.players)

    def test_treasure_room_start_draws_title_instructions_and_timer(self):
        state = GameState()
        state.levelnum_current = 17
        state.mazenum_current = _TREASURE_MAZE
        state.treasure_timer = 1201

        show_level_start_screen(state)

        assert state.alpha_ram[5 * 64 + 1] & 0x3FF
        assert "".join(
            chr(word & 0x3FF) if word & 0x3FF else " "
            for word in state.alpha_ram[11 * 64 + 5:11 * 64 + 25]
        ).startswith("YOU HAVE")
        assert state.alpha_ram[2 * 64 + 34] & 0x3FF

    def test_ordinary_level_start_draws_the_rom_level_splash(self):
        from gauntpy.subsystems.display import (
            _LARGE_GLYPH_INDEX_MAP,
            _LARGE_GLYPH_QUADS,
        )

        state = GameState()
        state.levelnum_current = 2
        state.mazenum_current = 1
        state.level_next_treasure = 2

        show_level_start_screen(state)

        expected_l = _LARGE_GLYPH_QUADS[_LARGE_GLYPH_INDEX_MAP[ord("L")]][0] | 0x100
        expected_2 = _LARGE_GLYPH_QUADS[_LARGE_GLYPH_INDEX_MAP[ord("2")]][0] | 0x100
        assert state.alpha_ram[9 * 64 + 4] & 0x3FF == expected_l
        assert state.alpha_ram[9 * 64 + 14] & 0x3FF == 0x16D  # half-width colon
        assert state.alpha_ram[9 * 64 + 15] == 0x8000         # untouched gap
        assert state.alpha_ram[9 * 64 + 20] & 0x3FF == expected_2
        assert state.bonus_timer == 0xB4


# ---------------------------------------------------------------------------
# The per-player bonus tally (0x4D516-0x4D5AA)
# ---------------------------------------------------------------------------

class TestBonusTally:
    """``100 x player_activecount x player_coincount[p] x player_treascount[p]``."""

    def test_treasure_collected_credits_the_picker_and_the_level(self):
        """0x519F8 bumps player_treascount; the level total feeds the display."""
        state = GameState()
        treasure_collected(state, 2)
        treasure_collected(state, 2)
        treasure_collected(state, 0)
        assert state.player_treascount == [1, 0, 2, 0]
        assert state.level_treasures == 3

    def test_one_pickup_is_one_bump_for_every_matching_code(self):
        """0x519C2/0x519CE/0x519DA are three compares over one ``addq.b #1`` at
        0x519E4, and ``secret_trick_id`` holds one code at a time -- so a single
        pickup can never advance an objective more than once.

        Without this, "after collecting 6 treasures" would finish in two.
        """
        for code in (TRICK_NO_TREASURE, 0x50, 0x5A):
            state = GameState()
            state.secret_trick_id = code
            treasure_collected(state, 1)
            assert state.secret_tricks_flags[1] == 1, hex(code)
            assert state.player_treascount[1] == 1, hex(code)
            assert state.level_treasures == 1, hex(code)
            assert state.secret_tricks_flags == [0, 1, 0, 0], "only the picker"

    def test_a_pickup_credits_nothing_when_no_code_matches(self):
        state = GameState()
        state.secret_trick_id = TRICK_NO_FOOD          # 0x0D is the food arm
        treasure_collected(state, 0)
        assert state.secret_tricks_flags[0] == 0
        state.secret_trick_id = 0x51                   # "all potions"
        treasure_collected(state, 0)
        assert state.secret_tricks_flags[0] == 0
        assert state.player_treascount[0] == 2, "the tally counter still moves"

    def test_six_treasures_finishes_the_matching_challenge_in_six(self):
        state = GameState()
        state.mazenum_current = _SECRET_MAZE
        state.secret_winner = 0
        state.secret_trick_id = 0x50                   # after collecting 6
        for i in range(5):
            treasure_collected(state, 0)
            assert not secret_check_winner(state), f"finished early at {i + 1}"
        treasure_collected(state, 0)
        assert secret_check_winner(state)

    def test_each_exiter_is_paid_for_their_own_treasures(self):
        state = GameState()
        for i in (0, 1):
            state.players[i].status = int(PlayerStatus.ALIVE_NEXT)
            state.players[i].coin_count = 1
        for _ in range(5):
            treasure_collected(state, 0)
        treasure_collected(state, 1)

        show_level_end_bonus_screen(state)

        # player_activecount == 2, one coin each.
        assert state.players[0].score == 100 * 2 * 1 * 5
        assert state.players[1].score == 100 * 2 * 1 * 1
        assert state.bonus_amount == 1000 + 200
        assert state.score_dirty[0] == 1 and state.score_dirty[1] == 1

    def test_coin_count_scales_a_players_own_bonus(self):
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.players[0].coin_count = 3
        for _ in range(2):
            treasure_collected(state, 0)
        show_level_end_bonus_screen(state)
        assert state.players[0].score == 100 * 1 * 3 * 2

    def test_a_player_who_collected_nothing_is_paid_nothing(self):
        state = GameState()
        for i in (0, 1):
            state.players[i].status = int(PlayerStatus.ALIVE_NEXT)
            state.players[i].coin_count = 1
        treasure_collected(state, 0)
        show_level_end_bonus_screen(state)
        assert state.players[1].score == 0

    def test_unattributed_treasures_go_to_the_first_exiter(self):
        """A pickup routed through the level total instead of
        ``treasure_collected`` still pays out, on the pre-counter rule."""
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.players[0].coin_count = 1
        state.level_treasures = 5                  # nobody claimed them
        show_level_end_bonus_screen(state)
        assert state.players[0].score == 100 * 1 * 1 * 5

    def test_no_treasures_is_no_bonus(self):
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.players[0].coin_count = 1
        show_level_end_bonus_screen(state)
        assert state.bonus_amount == 0
        assert state.players[0].score == 0

    def test_coin_factor_floors_at_one(self):
        """Every player who joins is credited a coin (player_coindrop 0x48962),
        so a hero placed directly by a test still tallies."""
        state = GameState()
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        treasure_collected(state, 0)
        show_level_end_bonus_screen(state)
        assert state.players[0].score == 100


# ---------------------------------------------------------------------------
# Secret rooms (§10.6): the level's trick, who wins it, and the challenge room
# ---------------------------------------------------------------------------

_SECRET_MAZE = 115


def _trick_state(trick: int, *, level: int = 12) -> GameState:
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.levelnum_current = level
    state.mazenum_current = 40
    state.secret_trick_id = trick
    state.secret_winner = -1
    for i in range(2):
        state.players[i].status = int(PlayerStatus.ALIVE_HERE)
    return state


class TestSecretNewLevelSetup:
    """maze_new_level_setup's objective block (0x43916-0x4395C)."""

    class _Maze:
        def __init__(self, secret):
            self.secret = secret

    def test_counter_expired_takes_the_maze_header_trick(self):
        state = GameState()
        state.levelnum_current = 20
        state.mazenum_current = 40
        state.secret_possible_counter = 0
        state.maze = self._Maze(TRICK_NOGREEDY2)
        secret_new_level_setup(state)
        assert state.secret_trick_id == TRICK_NOGREEDY2
        assert state.secret_winner == -1

    def test_counter_still_running_means_no_objective(self):
        state = GameState()
        state.mazenum_current = 40
        state.secret_possible_counter = 3
        state.maze = self._Maze(TRICK_NOGREEDY2)
        secret_new_level_setup(state)
        assert state.secret_trick_id == TRICK_NONE

    def test_dragon_trick_needs_level_twelve(self):
        """0x4394E: trick 9 wants a dragon, which arrives at level 12."""
        state = GameState()
        state.mazenum_current = 40
        state.secret_possible_counter = 0
        state.maze = self._Maze(TRICK_NOGETHIT)
        state.levelnum_current = 11
        secret_new_level_setup(state)
        assert state.secret_trick_id == TRICK_NONE

        state.secret_possible_counter = 0
        state.levelnum_current = 12
        secret_new_level_setup(state)
        assert state.secret_trick_id == TRICK_NOGETHIT

    def test_a_secret_room_keeps_its_challenge(self):
        """0x43916: inside maze 115/116 nothing is reset."""
        state = GameState()
        state.mazenum_current = _SECRET_MAZE
        state.secret_trick_id = 0x57
        state.secret_winner = 2
        secret_new_level_setup(state)
        assert state.secret_trick_id == 0x57
        assert state.secret_winner == 2


class TestSecretTrickCheck:
    """The per-trick dispatch at the head of player_exit_sequence (0x52B60)."""

    def test_watch_what_you_shoot_needs_two(self):
        state = _trick_state(TRICK_WATCHSHOOT1)
        secret_trick_progress(state, 0, TRICK_WATCHSHOOT1)
        secret_trick_check(state, 0)
        assert state.secret_winner == -1, "one is not enough"
        secret_trick_progress(state, 0, TRICK_WATCHSHOOT1)
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

    def test_progress_only_counts_for_the_active_trick(self):
        state = _trick_state(TRICK_WATCHSHOOT2)
        secret_trick_progress(state, 0, TRICK_WATCHSHOOT1)   # wrong objective
        secret_trick_progress(state, 0, TRICK_WATCHSHOOT1)
        assert state.secret_tricks_flags[0] == 0

    def test_save_super_shots_reads_the_players_bank(self):
        state = _trick_state(TRICK_SAVESUPERSHOTS)
        state.players[0].supershot = 10
        secret_trick_check(state, 0)
        assert state.secret_winner == -1
        state.players[0].supershot = 11                      # 0x52BAA
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

    def test_dont_use_invulnerability_wants_exactly_one(self):
        state = _trick_state(TRICK_NOUSEINVUL)
        secret_trick_check(state, 0)
        assert state.secret_winner == -1, "never picked it up"
        secret_trick_set(state, 0, TRICK_NOUSEINVUL, 1)      # 0x518C2
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

    def test_dont_be_greedy_is_won_by_touching_nothing(self):
        state = _trick_state(TRICK_NO_TREASURE)
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

    def test_dont_be_greedy_is_lost_by_one_pickup(self):
        state = _trick_state(TRICK_NO_TREASURE)
        treasure_collected(state, 0)
        secret_trick_check(state, 0)
        assert state.secret_winner == -1

    def test_the_treasure_trick_is_0x0E_and_the_food_trick_0x0D(self):
        """0x519C2 sits above the player_treascount bump; 0x51C0C/0x51CEE sit
        above a player_health add, so §3.17's two names are the wrong way
        round."""
        assert TRICK_NO_TREASURE == 0x0E == TRICK_NOGREEDY2
        assert TRICK_NO_FOOD == 0x0D == TRICK_DIET

    def test_treasure_does_not_advance_a_food_objective(self):
        state = _trick_state(TRICK_NO_FOOD)
        treasure_collected(state, 0)
        assert state.secret_tricks_flags[0] == 0
        secret_trick_check(state, 0)
        assert state.secret_winner == 0, "eating nothing still wins the diet"

    def test_a_food_objective_is_lost_by_eating(self):
        state = _trick_state(TRICK_NO_FOOD)
        secret_trick_progress(state, 0, TRICK_NO_FOOD)    # WP-6's 0x51CEE hook
        secret_trick_check(state, 0)
        assert state.secret_winner == -1

    def test_masked_tricks_use_their_own_width(self):
        """9/0x0D mask with 3, 0x0C/0x0E with 7 (0x52BF8 / 0x52C30)."""
        state = _trick_state(TRICK_NOGREEDY1)
        state.secret_tricks_flags[0] = 8                     # 8 & 7 == 0
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

        state = _trick_state(TRICK_NOGETHIT)
        state.secret_tricks_flags[0] = 4                     # 4 & 3 == 0
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

    def test_dont_hurt_friends_wants_a_clean_sheet(self):
        state = _trick_state(TRICK_NOHURTFRIENDS)
        secret_trick_progress(state, 0, TRICK_NOHURTFRIENDS)
        secret_trick_check(state, 0)
        assert state.secret_winner == -1

    def test_be_pushy_reads_movement_type(self):
        state = _trick_state(TRICK_BEPUSHY)
        state.movement_type = 1
        secret_trick_check(state, 0)
        assert state.secret_winner == -1
        state.movement_type = 0
        secret_trick_check(state, 0)
        assert state.secret_winner == 0

    def test_it_is_claimed_by_whoever_is_it(self):
        state = _trick_state(TRICK_IT)
        state.player_it = 1
        secret_trick_check(state, 0)                          # player 0 is not IT
        assert state.secret_winner == -1
        assert state.secret_tricks_flags == [1, 1, 1, 1], "everyone is marked"

    def test_it_locks_out_later_exiters(self):
        state = _trick_state(TRICK_IT)
        state.player_it = 1
        secret_trick_check(state, 1)
        assert state.secret_winner == 1
        state.player_it = 0
        secret_trick_check(state, 0)                          # too late, flags are 1
        assert state.secret_winner == 1

    def test_transport_tricks_are_not_decided_at_the_exit(self):
        state = _trick_state(TRICK_TRANSPORT1)
        secret_trick_check(state, 0)
        assert state.secret_winner == -1

    def test_no_objective_never_produces_a_winner(self):
        state = _trick_state(TRICK_NONE)
        secret_trick_check(state, 0)
        assert state.secret_winner == -1


class TestSecretCheck:
    """secret_check's adaptive pacing (0x486FE)."""

    def test_a_win_pushes_the_reload_up_and_records_the_maze(self):
        state = _trick_state(TRICK_NOGREEDY2)
        state.secret_winner = 0
        state.secret_possible_start = 20
        secret_check(state)
        assert state.secret_prev_maze == 40
        assert state.secret_possible_start == 35
        assert state.secret_possible_counter == 35

    def test_a_win_is_capped(self):
        state = _trick_state(TRICK_NOGREEDY2)
        state.secret_winner = 0
        state.secret_possible_start = _SECRET_START_MAX
        secret_check(state)
        assert state.secret_possible_start == _SECRET_START_MAX

    def test_a_miss_pulls_it_down_with_a_floor(self):
        state = _trick_state(TRICK_NOGREEDY2)
        state.secret_possible_start = 5
        secret_check(state)
        assert state.secret_possible_start == _SECRET_START_MIN
        secret_check(state)
        assert state.secret_possible_start == _SECRET_START_MIN

    def test_a_level_with_no_objective_is_left_alone(self):
        state = _trick_state(TRICK_NONE)
        state.secret_possible_start = 20
        state.secret_possible_counter = 7
        secret_check(state)
        assert state.secret_possible_counter == 7


class TestSecretCheckWinner:
    """The challenge-task qualification table (0x4D1A4)."""

    def _room(self, task: int, progress: int) -> GameState:
        state = GameState()
        state.mazenum_current = _SECRET_MAZE
        state.secret_winner = 0
        state.secret_trick_id = task
        state.secret_tricks_flags[0] = progress
        return state

    def test_three_secret_walls(self):
        assert not secret_check_winner(self._room(0x52, 2))
        assert secret_check_winner(self._room(0x52, 3))
        assert secret_check_winner(self._room(0x5B, 3))

    def test_while_you_are_it(self):
        assert not secret_check_winner(self._room(0x5C, 0))
        assert secret_check_winner(self._room(0x5C, 1))

    def test_exact_count_tasks(self):
        assert secret_check_winner(self._room(0x50, 6))       # 6 treasures
        assert not secret_check_winner(self._room(0x50, 5))
        assert secret_check_winner(self._room(0x51, 6))       # all potions
        assert secret_check_winner(self._room(0x56, 0x3E))    # 5 transporters
        assert secret_check_winner(self._room(0x5A, 0x13))    # remove all treasure

    def test_unconditional_tasks(self):
        for task in (0x54, 0x55, 0x57, 0x58, 0x59):
            assert secret_check_winner(self._room(task, 0))

    def test_clear_the_room_task(self):
        """0x53 sweeps the MOB table for monsters and generators."""
        state = self._room(0x53, 0)
        assert secret_check_winner(state)
        state.mobs.create(200, tile=1, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.MONST_GRUNT))
        assert not secret_check_winner(state)
        state.mobs.unlink_and_clear(200)
        state.mobs.create(201, tile=1, hpos=0, vpos=0,
                          obj_type=int(MazeObjIds.GEN_SORC2))
        assert not secret_check_winner(state)

    def test_no_winner_is_not_a_completion(self):
        state = self._room(0x54, 0)
        state.secret_winner = -1
        assert not secret_check_winner(state)


class TestSecretRoomEntry:
    """show_level_start_screen's secret arm (0x44DD6-0x44E8E)."""

    def _won(self, seed: int = 0) -> GameState:
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.levelnum_current = 13
        state.mazenum_current = 41
        state.maze_next, state.level_next = 41, 13
        state.level_next_treasure = 4          # no treasure room is due
        state.secret_winner = 0
        state.secret_trick_id = TRICK_NOGREEDY2
        state.players[0].status = int(PlayerStatus.ALIVE_NEXT)
        state.rng = GameRandom(seed=seed)
        return state

    def test_entry_swaps_the_maze_and_the_objective(self):
        state = self._won()
        show_level_start_screen(state)
        assert state.mazenum_current in (115, 116)
        assert CHALLENGE_FIRST <= state.secret_trick_id < CHALLENGE_FIRST + CHALLENGE_COUNT
        assert state.secret_trick_last == TRICK_NOGREEDY2
        assert state.treasure_timer > 0
        assert state.maze_next == 41, "the displaced rotation maze is kept"
        assert state.level_next == 13, "a secret room does not consume a level"

    def test_task_decides_which_room(self):
        """0x50-0x56 play in maze 115, 0x57-0x5D in maze 116 (0x44E26)."""
        for seed in range(64):
            state = self._won(seed=seed)
            show_level_start_screen(state)
            expected = 115 if state.secret_trick_id < 0x57 else 116
            assert state.mazenum_current == expected

    def test_no_winner_means_no_secret_room(self):
        state = self._won()
        state.secret_winner = -1
        show_level_start_screen(state)
        assert state.mazenum_current == 41

    def test_a_winner_who_did_not_reach_the_exit_is_ignored(self):
        """0x44DFA: the winner's status must be 2."""
        state = self._won()
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
        show_level_start_screen(state)
        assert state.mazenum_current == 41

    def test_the_opening_act_never_offers_one(self):
        state = self._won()
        state.levelnum_current = 6
        show_level_start_screen(state)
        assert state.mazenum_current == 41


class TestSecretRoomPayout:
    """show_level_end_bonus_screen's secret arm (0x4D720-0x4D8A0)."""

    def _in_room(self, task: int = 0x54) -> GameState:
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.levelnum_current, state.mazenum_current = 13, _SECRET_MAZE
        state.level_next, state.maze_next = 13, 41
        state.secret_winner = 0
        state.secret_trick_id = task
        state.secret_saved_keys = 3
        state.secret_saved_potions = 2
        state.secret_saved_supershot = 5
        p = state.players[0]
        p.status = int(PlayerStatus.ALIVE_NEXT)
        p.coin_count = 1
        return state

    def test_a_completed_task_pays_5000_per_coin(self):
        state = self._in_room()
        state.players[0].coin_count = 2
        show_level_end_bonus_screen(state)
        assert state.bonus_amount == _SECRET_ROOM_BONUS * 2
        assert state.players[0].score == _SECRET_ROOM_BONUS * 2
        assert state.score_dirty[0] == 1

    def test_a_missed_task_pays_nothing(self):
        state = self._in_room(task=0x50)          # needs 6 treasures
        show_level_end_bonus_screen(state)
        assert state.bonus_amount == 0
        assert state.players[0].score == 0

    def test_timing_out_inside_the_room_pays_nothing(self):
        """0x4D730/0x4D73E: the winner must have reached the exit."""
        state = self._in_room()
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
        show_level_end_bonus_screen(state)
        assert state.bonus_amount == 0
        assert state.players[0].status == int(PlayerStatus.ALIVE_NEXT), (
            "0x4D85C still puts them back on the road out"
        )

    def test_the_stash_comes_back(self):
        state = self._in_room()
        p = state.players[0]
        p.keysnum, p.potionsnum, p.supershot = 1, 0, 2   # picked up inside
        show_level_end_bonus_screen(state)
        assert (p.keysnum, p.potionsnum, p.supershot) == (4, 2, 7)
        assert state.secret_saved_keys == 0

    def test_the_winner_slot_is_cleared(self):
        """0x4D866 -- otherwise the next level walks straight back in."""
        state = self._in_room()
        show_level_end_bonus_screen(state)
        assert state.secret_winner == -1

    def test_pacing_is_not_adapted_on_the_way_out(self):
        """0x4D8CA takes the secret_need_hint arm, not secret_check."""
        state = self._in_room()
        state.secret_possible_start = 20
        state.secret_need_hint = 1
        show_level_end_bonus_screen(state)
        assert state.secret_possible_start == 20
        assert state.secret_need_hint == 0
