"""WP-16 · Coins, credits, character select, and session start.

Covers coincheck, character_select_input_update, and main_start_game.

The switches are active low: a bit that is 0 (cleared) means pressed.
``player_input_raw`` defaults to 0xFFFF (nothing pressed).

Reference: doc/04_game_subsystems.md §10.1, §22, §6.4; PLAN.md §6 WP-16.
"""

from __future__ import annotations

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.state import GameState
from gauntpy.subsystems.session import (
    character_select_input_update,
    coincheck,
    main_start_game,
    player_init_for_coin,
    start_attract_to_game,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_magic_edge(state: GameState, player_index: int) -> None:
    """Set debounce_shift_magic[player_index] so _magic_press_edge returns True.

    0x1C == 0b11100: bits 4-2 released (1s), bits 1-0 held (0s).
    """
    state.debounce_shift_magic[player_index] = 0x1C


def _no_magic(state: GameState, player_index: int) -> None:
    """Clear the magic edge for *player_index*."""
    state.debounce_shift_magic[player_index] = 0x0000  # all held, never an edge


def _coin_for_player(state: GameState, player_index: int) -> None:
    """Advance the 2-bit counter for *player_index* by 1 (simulates one coin)."""
    shift = player_index * 2
    channel = (state.coin_counters >> shift) & 3
    channel = (channel + 1) & 3
    state.coin_counters = (state.coin_counters & ~(3 << shift)) | (channel << shift)


# ---------------------------------------------------------------------------
# coincheck tests
# ---------------------------------------------------------------------------

def test_coincheck_active_player_gains_health():
    """Coin for a player with health tops up their health from the table."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.players[0].health = 800
    initial_health = state.players[0].health

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.players[0].health > initial_health, (
        "coin for an active player must add health from the 0x57862 table"
    )


def test_coincheck_active_player_health_uses_table_index():
    """Health add is indexed by game_settings & 0x1F; index 0 is 100."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.game_settings = 0
    state.players[0].health = 100

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.players[0].health == 200


def test_coin_health_table_matches_all_32_rom_words():
    from gauntpy.subsystems.session import _COIN_HEALTH_TABLE

    assert _COIN_HEALTH_TABLE == [
        100, 125, 150, 175, 200, 225, 250, 300,
        350, 400, 450, 500, 550, 600, 650, 700,
        750, 800, 850, 900, 950, 1000, 1100, 1200,
        1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000,
    ]


def test_factory_settings_use_coin_health_entry_16():
    state = GameState(game_mode=GameMode.NORMAL)
    state.game_settings = 0xE090
    state.players[0].health = 1

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.players[0].health == 751


def test_coincheck_health_add_wraps_as_a_32_bit_longword():
    state = GameState(game_mode=GameMode.NORMAL)
    state.game_settings = 0
    state.players[0].health = 0x7FFF_FFFF

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.players[0].health & 0xFFFF_FFFF == 0x8000_0063


def test_coincheck_zero_health_player_enters_selecting():
    """Coin for a player with zero health moves them to SELECTING status."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    # all players start with health = 0 by default
    assert state.players[1].health == 0

    _coin_for_player(state, 1)
    coincheck(state)

    assert state.players[1].status == PlayerStatus.SELECTING, (
        "a coin for a dead/absent player must start character selection"
    )
    assert state.players[1].character == Character.VALKYRIE, (
        "coin joins preserve player_resetall's per-slot default character"
    )


def test_coincheck_zero_health_decrements_credits():
    """A coin used to join debits one credit (when credits > 0)."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.credits = 3

    _coin_for_player(state, 2)
    coincheck(state)

    assert state.credits == 2


def test_coincheck_zero_health_increments_coin_count():
    """A joining coin increments the player's coin_count."""
    state = GameState()
    state.game_mode = GameMode.NORMAL

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.players[0].coin_count == 1


def test_coincheck_attract_all_zero_health_starts_game():
    """Coin while in attract mode with no health → game_mode becomes NORMAL."""
    state = GameState()
    assert state.game_mode == GameMode.TITLE, "sanity: default is attract"
    # all players have health == 0 by default

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.game_mode == GameMode.NORMAL, (
        "a coin in attract (all zero health) must call start_attract_to_game"
    )


def test_coincheck_attract_demo_with_health_still_starts_game():
    """In DEMO mode, demo heroes have health, but a coin must still interrupt."""
    state = GameState()
    state.game_mode = GameMode.DEMO
    state.players[0].health = 500  # demo hero has health

    _coin_for_player(state, 1)
    coincheck(state)

    assert state.game_mode == GameMode.NORMAL, (
        "the DEMO branch must fire regardless of player health"
    )


def test_coincheck_no_change_has_no_effect():
    """If coin_counters did not change, coincheck must not mutate any state."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.players[0].health = 500

    # Both coin_counters and last_coin_state are 0; no change.
    coincheck(state)

    assert state.players[0].health == 500
    assert state.players[0].status == PlayerStatus.REMOVED


def test_coincheck_updates_last_coin_state():
    """last_coin_state is shadowed after a change is processed."""
    state = GameState()
    state.game_mode = GameMode.NORMAL

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.last_coin_state == state.coin_counters, (
        "last_coin_state must shadow coin_counters after processing"
    )


def test_coincheck_free_play_shadows_but_ignores_coin_effects():
    """0x42BA4: free play skips credit/health/select effects after shadowing."""
    state = GameState(game_mode=GameMode.NORMAL)
    state.two_player_mode = 0

    _coin_for_player(state, 0)
    coincheck(state)

    assert state.last_coin_state == state.coin_counters
    assert state.players[0].status == PlayerStatus.REMOVED
    assert state.players[0].health == 0
    assert state.players[0].coin_count == 0
    assert state.sound_log == []


def test_coincheck_second_call_is_idempotent():
    """A second coincheck call with the same counters must do nothing extra."""
    state = GameState()
    state.game_mode = GameMode.NORMAL

    _coin_for_player(state, 0)
    coincheck(state)
    status_after_first = state.players[0].status
    health_after_first = state.players[0].health

    # Second call -- counters unchanged.
    coincheck(state)

    assert state.players[0].status == status_after_first
    assert state.players[0].health == health_after_first


def test_coincheck_only_affected_player_is_changed():
    """A coin for player 2 must not affect players 0, 1, or 3."""
    state = GameState()
    state.game_mode = GameMode.NORMAL

    _coin_for_player(state, 2)
    coincheck(state)

    assert state.players[0].status == PlayerStatus.REMOVED
    assert state.players[1].status == PlayerStatus.REMOVED
    assert state.players[2].status == PlayerStatus.SELECTING
    assert state.players[3].status == PlayerStatus.REMOVED


# ---------------------------------------------------------------------------
# character_select_input_update tests
# ---------------------------------------------------------------------------

def test_charselect_up_yields_warrior():
    """Bit 7 clear (up held) → Warrior (doc §22 priority order)."""
    state = GameState()
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.ELF  # start somewhere other than Warrior
    state.players[0].character = Character.ELF
    state.player_input_raw[0] = 0xFFFF & ~0x80  # bit 7 cleared = up held

    character_select_input_update(state)

    assert state.players[0].character == Character.WARRIOR
    assert state.pending_character[0] == Character.WARRIOR


def test_charselect_right_yields_elf():
    """Bit 4 clear (right held, no higher-priority direction) → Elf."""
    state = GameState()
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.WARRIOR
    state.players[0].character = Character.WARRIOR
    # bit 4 (0x10) cleared; bits 7 (0x80), 5 (0x20), 6 (0x40) left set
    state.player_input_raw[0] = 0xFFFF & ~0x10

    character_select_input_update(state)

    assert state.players[0].character == Character.ELF
    assert state.pending_character[0] == Character.ELF


def test_charselect_left_yields_valkyrie():
    """Bit 5 clear (left held, no up) → Valkyrie."""
    state = GameState()
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.WARRIOR
    state.players[0].character = Character.WARRIOR
    # bit 5 (0x20) cleared; bit 7 (0x80) left set (no up)
    state.player_input_raw[0] = 0xFFFF & ~0x20

    character_select_input_update(state)

    assert state.players[0].character == Character.VALKYRIE


def test_charselect_down_yields_wizard():
    """Bit 6 clear (down held, no up or left) → Wizard."""
    state = GameState()
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.WARRIOR
    state.players[0].character = Character.WARRIOR
    # bit 6 (0x40) cleared; bits 7 (0x80) and 5 (0x20) left set
    state.player_input_raw[0] = 0xFFFF & ~0x40

    character_select_input_update(state)

    assert state.players[0].character == Character.WIZARD


def test_charselect_no_direction_keeps_current():
    """No direction held → pending_character unchanged."""
    state = GameState()
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.ELF
    state.players[0].character = Character.ELF
    state.player_input_raw[0] = 0xFFFF  # nothing pressed (active low)

    character_select_input_update(state)

    assert state.players[0].character == Character.ELF
    assert state.pending_character[0] == Character.ELF


def test_charselect_not_selecting_player_unchanged():
    """A player not in SELECTING status must not be modified."""
    state = GameState()
    state.players[0].status = PlayerStatus.REMOVED
    state.players[0].character = Character.WARRIOR
    state.player_input_raw[0] = 0xFFFF & ~0x10  # right held → would be Elf

    character_select_input_update(state)

    assert state.players[0].character == Character.WARRIOR, (
        "REMOVED player must not have their character changed"
    )


def test_charselect_only_selecting_players_updated():
    """Only the SELECTING player should be updated; others are untouched."""
    state = GameState()
    state.players[0].status = PlayerStatus.REMOVED
    state.players[0].character = Character.WIZARD
    state.players[1].status = PlayerStatus.SELECTING
    state.pending_character[1] = Character.WARRIOR
    state.players[1].character = Character.WARRIOR
    state.player_input_raw[1] = 0xFFFF & ~0x10  # right → Elf for player 1

    character_select_input_update(state)

    assert state.players[0].character == Character.WIZARD, "player 0 untouched"
    assert state.players[1].character == Character.ELF, "player 1 updated"


# ---------------------------------------------------------------------------
# main_start_game tests
# ---------------------------------------------------------------------------

def test_main_start_game_magic_edge_commits_and_sets_alive():
    """Magic press edge on a SELECTING player → ALIVE_HERE with committed char."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.players[0].status = PlayerStatus.SELECTING
    state.players[0].health = 1234
    state.pending_character[0] = Character.ELF

    _make_magic_edge(state, 0)
    main_start_game(state)

    assert state.players[0].status == PlayerStatus.ALIVE_HERE, (
        "Magic press must commit the character and flip status to ALIVE_HERE"
    )
    assert state.players[0].character == Character.ELF, (
        "committed character must come from pending_character"
    )
    assert state.players[0].health == 1234, "coin-configured health must survive commit"


def test_main_start_game_no_magic_edge_leaves_player_unchanged():
    """Without a settled Magic press, SELECTING player must stay SELECTING."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.ELF
    _no_magic(state, 0)

    main_start_game(state)

    assert state.players[0].status == PlayerStatus.SELECTING
    assert state.players[0].health == 0


def test_main_start_game_first_warrior_sets_spawn_bonus_not_multiplier():
    """0x48EF6 writes table[Warrior] to the monster spawn bonus byte."""
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.maze = object()
    state.mobs.create(
        0x120, tile=1, hpos=0, vpos=0,
        obj_type=int(MazeObjIds.PLAYERSTART),
    )
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.WARRIOR

    _make_magic_edge(state, 0)
    main_start_game(state)

    assert state.players[0].bonusmult == 1
    assert state.spawn_probability_bonus == 3


def test_main_start_game_first_wizard_sets_spawn_bonus_not_multiplier():
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.maze = object()
    state.mobs.create(
        0x120, tile=1, hpos=0, vpos=0,
        obj_type=int(MazeObjIds.PLAYERSTART),
    )
    state.players[0].status = PlayerStatus.SELECTING
    state.pending_character[0] = Character.WIZARD

    _make_magic_edge(state, 0)
    main_start_game(state)

    assert state.players[0].bonusmult == 1
    assert state.spawn_probability_bonus == 4


def test_main_start_game_later_join_clears_spawn_bonus_not_multiplier():
    state = GameState()
    state.game_mode = GameMode.NORMAL
    state.maze = object()
    state.mobs.create(
        0x120, tile=1, hpos=0, vpos=0,
        obj_type=int(MazeObjIds.PLAYERSTART),
    )
    # Player 0 is already alive.
    state.players[0].status = PlayerStatus.ALIVE_HERE
    state.players[0].health = 800
    state.players[0].mob_slot = 0x100
    state.level_players_active = 1
    state.spawn_probability_bonus = 3

    # Player 1 commits.
    state.players[1].status = PlayerStatus.SELECTING
    state.pending_character[1] = Character.WARRIOR  # would be 3 if first

    _make_magic_edge(state, 1)
    main_start_game(state)

    assert state.players[1].bonusmult == 1
    assert state.spawn_probability_bonus == 0


def test_main_start_game_free_play_magic_in_attract_starts_game():
    """In free play (two_player_mode == 0), Magic in attract starts a session."""
    state = GameState()
    state.game_mode = GameMode.TITLE   # attract, < 0
    state.two_player_mode = 0          # free play

    # Player 0 is not SELECTING -- this is the free-play attract interruption.
    state.players[0].status = PlayerStatus.REMOVED
    _make_magic_edge(state, 0)

    main_start_game(state)

    assert state.game_mode == GameMode.NORMAL, (
        "free-play Magic press in attract must call start_attract_to_game"
    )


def test_main_start_game_paid_play_magic_in_attract_no_effect():
    """In paid play (two_player_mode != 0), Magic alone in attract does nothing."""
    state = GameState()
    state.game_mode = GameMode.TITLE
    state.two_player_mode = 1  # paid play

    state.players[0].status = PlayerStatus.REMOVED
    _make_magic_edge(state, 0)

    main_start_game(state)

    assert state.game_mode == GameMode.TITLE, (
        "paid-play Magic press in attract must NOT start a session"
    )


def test_main_start_game_advances_welcome_elapsed_frames():
    state = GameState()
    state.welcome_elapsed_frames = 0xFFFF_FFFF

    main_start_game(state)

    assert state.welcome_elapsed_frames == 0


# ---------------------------------------------------------------------------
# start_attract_to_game (0x44204)
# ---------------------------------------------------------------------------

class TestStartAttractToGame:
    """The attract -> gameplay hand-off, and the transition state it resets."""

    def test_mode_level_and_maze(self):
        state = GameState()
        state.game_mode = GameMode.TITLE
        state.levelnum_current, state.mazenum_current = 40, 77
        start_attract_to_game(state)
        assert state.game_mode == GameMode.NORMAL   # 0x44266
        assert state.levelnum_current == 1          # 0x4426C
        assert state.mazenum_current == 0           # 0x4420E (ROMs absent: stays 0)

    def test_attract_timer_is_parked_on_the_disabled_sentinel(self):
        """0x4436C loads 0xFFFF so main_attract stands down."""
        state = GameState()
        state.game_mode = GameMode.TITLE
        state.attract_timer = 300
        start_attract_to_game(state)
        assert state.attract_timer == 0xFFFF

    def test_transition_state_is_cleared(self):
        """global_ui_delay_timer = 0 at 0x44366; no stale treasure countdown."""
        state = GameState()
        state.game_mode = GameMode.DEMO
        state.bonus_timer = 90
        state.bonus_amount = 1234
        state.treasure_timer = 600
        state.welcome_elapsed_frames = 900
        start_attract_to_game(state)
        assert (state.bonus_timer, state.bonus_amount, state.treasure_timer) == (0, 0, 0)
        assert state.welcome_elapsed_frames == 0

    def test_session_sounds(self):
        state = GameState()
        state.game_mode = GameMode.TITLE
        state.sound_log.clear()
        start_attract_to_game(state)
        assert 0x3C in state.sound_log    # 0x4425A theme fade-out
        assert 0x02 in state.sound_log    # 0x4429A session-start sting

    def test_demo_hero_cannot_leak_into_the_session(self):
        state = GameState()
        state.game_mode = GameMode.DEMO
        p = state.players[1]
        p.status, p.health, p.score, p.mob_slot = PlayerStatus.ALIVE_HERE, 800, 500, 99
        start_attract_to_game(state)
        assert p.status == PlayerStatus.REMOVED
        assert (p.health, p.score, p.mob_slot) == (0, 0, 0)


# ---------------------------------------------------------------------------
# player_init_for_coin (0x488CA) and the info-panel rebuilds it drives
# ---------------------------------------------------------------------------

class TestPlayerInitForCoin:
    """The join half of a coin: sound, health, one coin, SELECTING, panel."""

    def test_free_play_health_and_one_coin(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.two_player_mode = 0
        player_init_for_coin(state, 2)
        p = state.players[2]
        assert p.health == 0x7D0            # 0x578A0 free-play start
        assert p.coin_count == 1            # 0x48962
        assert p.score == 0                 # 0x48954
        assert p.status == PlayerStatus.SELECTING
        assert p.state_timer == 0xFFFF      # 0x4896C

    def test_new_credit_resets_stale_health_and_multiplier(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.two_player_mode = 0
        state.players[0].health = 17
        state.players[0].bonusmult = 7

        player_init_for_coin(state, 0)

        assert state.players[0].health == 0x7D0
        assert state.players[0].bonusmult == 1
        assert state.info_panel.players[0].health == 0x7D0

    def test_paid_play_health_comes_from_the_coin_table(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.two_player_mode = 1
        state.game_settings = 8             # table index 8 -> 350
        player_init_for_coin(state, 0)
        assert state.players[0].health == 350

    def test_coin_slot_sound_is_per_slot(self):
        """ROM table 0x57002: red/blue/yellow/green = 0x22-0x25 (0x488FE)."""
        for slot, expected in enumerate((0x22, 0x23, 0x24, 0x25)):
            state = GameState()
            state.game_mode = GameMode.NORMAL
            player_init_for_coin(state, slot)
            assert expected in state.sound_log

    def test_demo_join_is_silent(self):
        """0x488E4: the demo's scripted joins take free-play health, no sound."""
        state = GameState()
        state.game_mode = GameMode.DEMO
        player_init_for_coin(state, 0)
        assert state.players[0].health == 0x7D0
        assert 0x22 not in state.sound_log

    def test_the_info_panel_is_rebuilt(self):
        """0x489A8 calls the real setup_infopanel, which latches that player's
        panel fields and services the redraw-request bits."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.score_dirty[1] = 1
        state.health_dirty[1] = 1
        player_init_for_coin(state, 1)
        assert state.score_dirty[1] == 0
        assert state.health_dirty[1] == 0
        panel = state.info_panel.players[1]
        assert panel.score_drawn and panel.health_drawn
        assert panel.health == state.players[1].health


class TestCoinForActivePlayer:
    """coincheck's re-coin branch (0x42C6C-0x42CBA)."""

    def _active(self) -> GameState:
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].health = 100
        state.players[0].coin_count = 1
        state.score_dirty[0] = 0
        state.health_dirty[0] = 0
        state.sound_log.clear()
        _coin_for_player(state, 0)
        return state

    def test_health_dirty_bit_is_raised(self):
        """0x42C72 ORs player_redraw bit 1 before anything else."""
        state = self._active()
        coincheck(state)
        assert state.players[0].health == 200
        assert state.players[0].coin_count == 2     # 0x42C04

    def test_coin_slot_sound_plays(self):
        state = self._active()
        coincheck(state)
        assert 0x22 in state.sound_log            # 0x42CB6, red slot

    def test_panel_rebuild_stops_past_the_coins_to_start_allowance(self):
        """0x42C88-0x42CA4: the full rebuild only runs while coincount is still
        within "coins to start" + 1."""
        state = self._active()
        state.players[0].coin_count = 9             # well past the allowance
        state.info_panel.players[0].score_drawn = False
        coincheck(state)
        assert not state.info_panel.players[0].score_drawn, (
            "no rebuild past the allowance"
        )

    def test_panel_is_rebuilt_inside_the_allowance(self):
        """Coins-to-start 4 (settings bits 8-9 = 3) keeps the rebuild running."""
        state = self._active()
        state.game_settings = 0x300
        state.info_panel.players[0].score_drawn = False
        coincheck(state)
        assert state.info_panel.players[0].score_drawn


class TestCharacterSelectPanel:
    def test_changing_the_selection_rebuilds_that_players_panel(self):
        """0x42E7E -- the real setup_infopanel, not a notification stub."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = PlayerStatus.SELECTING
        state.info_panel.players[0].score_drawn = False
        state.player_input_raw[0] = 0xFFFF & ~0x40   # bit 6 -> Wizard
        character_select_input_update(state)
        assert state.players[0].character == Character.WIZARD
        assert state.info_panel.players[0].score_drawn


# ---------------------------------------------------------------------------
# player_resetcounters / player_resetall (0x43360 / 0x4341E) and the reset
# sites that call them
# ---------------------------------------------------------------------------

class TestPlayerReset:
    @staticmethod
    def _dirty(state: GameState, index: int) -> None:
        p = state.players[index]
        p.status = PlayerStatus.ALIVE_HERE
        p.health, p.score = 777, 4242
        p.keysnum, p.potionsnum = 5, 3
        p.powers = 0x1FFF
        p.bonusmult, p.mob_slot = 6, 99
        p.state_timer, p.stundelay, p.supershot = 12, 34, 7
        p.acid_timer = 20
        p.character = Character.ELF
        state.player_invis_timer[index] = 50
        state.player_repulse_timer[index] = 60
        state.player_tport_phase[index] = 4

    def test_resetcounters_clears_the_whole_slot(self):
        from gauntpy.subsystems.players import player_resetcounters

        state = GameState()
        self._dirty(state, 2)
        player_resetcounters(state, 2)
        p = state.players[2]
        assert p.status == PlayerStatus.REMOVED     # 0x9049A0
        assert (p.keysnum, p.potionsnum) == (0, 0)  # 0x90405A / 0x904055
        assert p.mob_slot == 0                      # 0x9048C8
        assert p.bonusmult == 1                     # 0x90490E
        assert p.state_timer == 0xFFFF              # 0x904A26
        assert p.powers == 0                        # 0x9048E0
        assert (p.acid_timer, p.supershot, p.stundelay) == (0, 0, 0)
        assert state.player_invis_timer[2] == 0     # 0x905F50
        assert state.player_repulse_timer[2] == 0   # 0x905F38
        assert state.player_tport_phase[2] == -1    # 0x904BCE
        # 0x43360 does not touch these: player_resetall clears them itself.
        assert (p.health, p.score) == (777, 4242)

    def test_resetall_clears_every_slot_and_the_counters(self):
        from gauntpy.subsystems.players import player_resetall

        state = GameState()
        for i in range(4):
            self._dirty(state, i)
        state.level_players_active = 3
        player_resetall(state)
        for p in state.players:
            assert p.status == PlayerStatus.REMOVED
            assert (p.health, p.score, p.powers, p.keysnum) == (0, 0, 0, 0)
        assert state.level_players_active == 0      # 0x43458
        assert [p.character for p in state.players] == [
            Character.WARRIOR, Character.VALKYRIE, Character.WIZARD, Character.ELF,
        ]                                            # 0x4345E-0x43474

    def test_every_attract_screen_resets_the_players(self):
        """0x4446E: start_attract_screen calls player_resetall unconditionally,
        so no session can leak an inventory into the attract screens."""
        from gauntpy.subsystems.attract import start_attract_screen

        for mode in (GameMode.TITLE, GameMode.SCORES, GameMode.LEGEND):
            state = GameState()
            state.game_mode = GameMode.NORMAL
            self._dirty(state, 0)
            state.level_players_active = 1
            start_attract_screen(state, int(mode))
            p = state.players[0]
            assert p.status == PlayerStatus.REMOVED, mode
            assert (p.keysnum, p.potionsnum, p.powers) == (0, 0, 0), mode
            assert (p.health, p.score, p.mob_slot) == (0, 0, 0), mode
            assert p.state_timer == 0xFFFF, mode
            assert state.level_players_active == 0, mode

    def test_leaving_demo_for_a_session_resets_the_demo_hero(self):
        """0x4424A-0x44254: the DEMO arm of start_attract_to_game."""
        state = GameState()
        state.game_mode = GameMode.DEMO
        self._dirty(state, 1)
        start_attract_to_game(state)
        p = state.players[1]
        assert p.status == PlayerStatus.REMOVED
        assert (p.health, p.score, p.mob_slot, p.keysnum, p.powers) == (0, 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# monster_spawn_probability_bonus (0x90405F)
# ---------------------------------------------------------------------------

class TestSpawnProbabilityBonus:
    def test_the_level_handoff_adds_score_per_coin_over_the_party(self):
        """0x48B58, called from the level handoff at 0x4834E."""
        from gauntpy.subsystems.exits import (
            update_monster_spawn_bonus_from_score_per_coin,
        )

        state = GameState()
        for i in (0, 1):
            state.players[i].status = PlayerStatus.ALIVE_HERE
            state.players[i].coin_count = 1
        state.players[0].score = 100_000
        state.players[1].score = 60_000
        update_monster_spawn_bonus_from_score_per_coin(state)
        # (160000 >> 14) // 2 == 9 // 2 == 4
        assert state.spawn_probability_bonus == 4

    def test_only_players_on_the_level_count(self):
        from gauntpy.subsystems.exits import (
            update_monster_spawn_bonus_from_score_per_coin,
        )

        state = GameState()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.players[0].score, state.players[0].coin_count = 1_000_000, 1
        state.players[1].status = PlayerStatus.ALIVE_NEXT     # not counted
        state.players[1].score, state.players[1].coin_count = 9_000_000, 1
        update_monster_spawn_bonus_from_score_per_coin(state)
        assert state.spawn_probability_bonus == 1_000_000 >> 14

    def test_a_coinless_party_is_left_alone(self):
        """The ROM's divs.w would trap; nothing is added instead."""
        from gauntpy.subsystems.exits import (
            update_monster_spawn_bonus_from_score_per_coin,
        )

        state = GameState()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.players[0].score = 1_000_000
        state.spawn_probability_bonus = 7
        update_monster_spawn_bonus_from_score_per_coin(state)
        assert state.spawn_probability_bonus == 7

    def test_the_bonus_is_a_byte(self):
        from gauntpy.subsystems.exits import (
            update_monster_spawn_bonus_from_score_per_coin,
        )

        state = GameState()
        state.players[0].status = PlayerStatus.ALIVE_HERE
        state.players[0].score, state.players[0].coin_count = 0x7F0000, 1
        state.spawn_probability_bonus = 0xFF
        update_monster_spawn_bonus_from_score_per_coin(state)
        assert 0 <= state.spawn_probability_bonus <= 0xFF     # add.b wraps

    def test_a_re_coin_walks_a_positive_bonus_back(self):
        """0x42C30-0x42C38: paying to stay alive buys a calmer level."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].health = 100
        state.players[0].coin_count = 1
        state.spawn_probability_bonus = 3
        _coin_for_player(state, 0)
        coincheck(state)
        assert state.spawn_probability_bonus == 2

    def test_a_re_coin_does_not_push_a_negative_bonus_further_down(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].health = 100
        state.players[0].coin_count = 1
        state.spawn_probability_bonus = 0xFE           # -2
        _coin_for_player(state, 0)
        coincheck(state)
        assert state.spawn_probability_bonus == 0xFE   # 0x42C36 ``ble``

    def test_a_re_coin_leaves_a_zero_bonus_alone(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].health = 100
        state.players[0].coin_count = 1
        state.spawn_probability_bonus = 0
        _coin_for_player(state, 0)
        coincheck(state)
        assert state.spawn_probability_bonus == 0

    def test_a_re_coin_re_arms_the_low_health_warning(self):
        """0x42C46-0x42C64 clear the latch, the spacing timer and the cadence."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].health = 100
        state.players[0].coin_count = 1
        state.players[0].state_timer = 40
        state.player_lowhealth_spoken[0] = 1
        state.player_respawn_speech_timer[0] = 500
        _coin_for_player(state, 0)
        coincheck(state)
        assert state.player_lowhealth_spoken[0] == 0
        assert state.player_respawn_speech_timer[0] == -1
        assert state.players[0].state_timer == 0xFFFF
