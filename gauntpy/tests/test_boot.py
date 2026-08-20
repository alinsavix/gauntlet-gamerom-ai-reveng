"""WP-20: one_time_init -- boot initialization before the first frame.

Reference: doc/03_game_rom_structure.md §5.
"""

from __future__ import annotations

from gauntpy.constants import Character, GameMode
from gauntpy.state import GameState
from gauntpy.subsystems.boot import one_time_init


class TestOneTimeInit:
    def test_default_characters_are_0123(self):
        state = GameState()
        for p in state.players:
            p.character = Character.WARRIOR   # scramble first
        one_time_init(state)
        assert [p.character for p in state.players] == [
            Character.WARRIOR, Character.VALKYRIE,
            Character.WIZARD, Character.ELF,
        ]
        assert state.pending_character == [0, 1, 2, 3]

    def test_sound_system_reset(self):
        state = GameState()
        state.sound_queue.extend([1, 2, 3])
        one_time_init(state)
        # The ring is flushed (§5 step 1) and the reset arms the 180-frame
        # holdoff, so the TITLE hand-off's own screen-change sounds
        # (start_attract_screen 0x4444E/0x4447A) take §11.1's direct-queue path
        # instead of going straight out to the board.  The factory settings
        # word 0xE090 has the attract-sound bit (0x4000) set, so the first
        # TITLE screen also queues the theme (0x3B, 0x444EC).
        assert state.sound_queue == [0x01, 0x3C, 0x3B]
        assert state.sound_holdoff == 0xB4
        assert state.sound_log == [], "nothing can reach the board during the holdoff"

    def test_game_state_cleared(self):
        state = GameState()
        state.frame_counter = 999
        state.frame_overflow = 8
        state.dialog_timer = 30
        one_time_init(state)
        assert state.frame_counter == 0
        assert state.frame_overflow == 0
        assert state.dialog_timer == 0

    def test_hands_off_to_title_attract(self):
        state = GameState()
        state.title_intro_state = 7
        state.title_logo_full_program = False
        one_time_init(state)
        assert state.game_mode == GameMode.TITLE
        assert state.attract_timer == 0x5DD
        # The factory word enables attract sound, so the theme arm runs and
        # parks title_intro_state on 2 (0x444F8).
        assert state.title_intro_state == 2
        assert state.title_logo_full_program is True

    def test_the_factory_settings_word_is_installed_on_a_fresh_cabinet(self, tmp_path):
        """0x432D8-0x432FA: an unprogrammed configuration item 12 reads back
        with bit 12 set, so one_time_init installs ROM 0x40070 = 0xE090."""
        state = GameState(eeprom_save_path=str(tmp_path / "absent.json"))
        one_time_init(state)
        assert state.game_settings == 0xE090
        assert state.eeprom_settings_cache == 0xE090

    def test_players_start_removed_and_inactive(self):
        state = GameState()
        state.players[0].status = 1
        one_time_init(state)
        assert all(p.status == 0 for p in state.players)
        assert state.level_players_active == 0

    def test_secret_counters_initialized(self):
        state = GameState()
        state.secret_possible_counter = 3
        one_time_init(state)
        assert state.secret_possible_counter == 20
        assert state.secret_possible_start == 20

    def test_potion_countdown_cleared(self):
        """0x43320 clears level_next_potion; level_next_treasure is left for
        maze_new_level_setup to arm at level 6 (0x438E4)."""
        state = GameState()
        state.level_next_potion = 7
        one_time_init(state)
        assert state.level_next_potion == 0

    def test_attract_position_is_reset_by_the_title_handoff(self):
        """start_attract_screen resets level 1 / maze 0 (0x4445A-0x44462)."""
        state = GameState()
        state.levelnum_current, state.mazenum_current = 40, 77
        one_time_init(state)
        assert (state.levelnum_current, state.mazenum_current) == (1, 0)
