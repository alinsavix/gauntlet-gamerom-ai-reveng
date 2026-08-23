"""WP-17: attract state machine, screen rotation, and input lockout.

Acceptance (PLAN.md §6 WP-17): screens rotate on their documented timers; the
input lockout blocks screen switches but never blocks a coin.

Plus the expiry half of ``main_attract`` (0x44860-0x4491A) the first pass left
out: legend paging, the ``start_attract_to_game`` hand-off at 0x448CE, the
0xFFFF disabled sentinel, and the ``game_mode -= 1`` rotation.
"""

from __future__ import annotations

import pytest

from gauntpy.coords import hpos_x, vpos_y
from gauntpy.constants import GameMode, MazeObjIds, PlayerStatus
from gauntpy.state import GameState
from gauntpy.subsystems.attract import (
    main_attract,
    main_logo_updcolors,
    start_attract_screen,
    _LOADED_TIMER,
    _INPUT_THRESHOLD,
    _SETTINGS_ATTRACT_SOUND,
    _SOUND_SCREEN_CHANGE,
    _SOUND_THEME_FADE,
    _TITLE_SETTINGS_REFRESH_CYCLE,
)

from gex.roms import SLAPSTIC_ROMS, _rom_dir

_ROMS_EXIST = (_rom_dir() / SLAPSTIC_ROMS[0]).is_file()
requires_roms = pytest.mark.skipif(not _ROMS_EXIST, reason="Slapstic ROMs not available")

# Active-low idle: no button, no direction pressed.
_IDLE = 0xFFFF


def _attract(state: GameState, mode: int) -> None:
    state.game_mode = mode
    state.attract_timer = _LOADED_TIMER[mode]
    state.player_input_raw = [_IDLE, _IDLE, _IDLE, _IDLE]


def _expire(state: GameState) -> None:
    """Drive the screen timer to the ROM's expiry point and run one more frame.

    ``main_attract`` decrements first and only treats the timer as expired once
    it has gone negative (0x445DA / 0x44860), so a screen ends on the frame that
    takes it from 0 to -1.
    """
    state.attract_timer = 0
    main_attract(state)


class TestScreenRotation:
    def test_timer_decrements(self):
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        before = state.attract_timer
        main_attract(state)
        assert state.attract_timer == before - 1

    def test_continue_screen_writes_its_live_seconds_into_the_prompt(self):
        state = GameState(game_mode=GameMode.NORMAL, levelnum_current=4)
        state.attract_timer = 0x5DD

        main_attract(state)

        assert state.attract_timer == 1500
        assert "".join(
            chr(word & 0x3FF) for word in state.alpha_ram[14 * 64 + 13:14 * 64 + 15]
        ) == "25"

    def test_zero_is_not_yet_expired(self):
        """0x44860 branches on ``bge``: zero is still a live frame."""
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        state.attract_timer = 1
        main_attract(state)
        assert state.attract_timer == 0
        assert state.game_mode == int(GameMode.SCORES)

    def test_scores_rotates_to_title_on_expiry(self):
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        _expire(state)
        assert state.game_mode == int(GameMode.TITLE)
        assert state.attract_timer == _LOADED_TIMER[int(GameMode.TITLE)]

    def test_full_rotation_order(self):
        """SCORES -> TITLE -> DEMO -> LEGEND (three pages) -> SCORES."""
        state = GameState()
        _attract(state, int(GameMode.SCORES))

        _expire(state)
        assert state.game_mode == int(GameMode.TITLE)
        _expire(state)
        assert state.game_mode == int(GameMode.DEMO)
        _expire(state)
        assert state.game_mode == int(GameMode.LEGEND)
        assert state.attract_legend == 2

        # LEGEND pages down before handing back to SCORES (0x4486E-0x4489C).
        _expire(state)
        assert (state.game_mode, state.attract_legend) == (int(GameMode.LEGEND), 1)
        _expire(state)
        assert (state.game_mode, state.attract_legend) == (int(GameMode.LEGEND), 0)
        _expire(state)
        assert state.game_mode == int(GameMode.SCORES)

    def test_gameplay_mode_is_idle(self):
        """A player actually on the level stops the machine (0x445D0)."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = int(PlayerStatus.ALIVE_HERE)
        state.attract_timer = 500
        main_attract(state)
        assert state.attract_timer == 500, "no attract work during gameplay"

    def test_disabled_sentinel_stops_the_machine(self):
        """start_attract_to_game parks the timer on 0xFFFF (0x4436C)."""
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        state.attract_timer = 0xFFFF
        main_attract(state)
        assert state.attract_timer == 0xFFFF
        assert state.game_mode == int(GameMode.SCORES)

    def test_fresh_state_starts_disabled(self):
        state = GameState()
        assert state.attract_timer == 0xFFFF


class TestSelectPhaseExpiry:
    """game_mode 0 with nobody playing -- the character-select countdown."""

    def test_select_phase_counts_down(self):
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = int(PlayerStatus.SELECTING)
        state.attract_timer = 300
        main_attract(state)
        assert state.attract_timer == 299

    def test_expiry_with_no_health_falls_back_to_scores(self):
        """0x448D6: ``subq.w #1,game_mode`` takes NORMAL to SCORES."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = int(PlayerStatus.SELECTING)
        _expire(state)
        assert state.game_mode == int(GameMode.SCORES)
        assert state.attract_timer == _LOADED_TIMER[int(GameMode.SCORES)]

    def test_expiry_with_health_left_starts_the_session(self):
        """0x448A8-0x448CE: a player still holding health is owed a game."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = int(PlayerStatus.SELECTING)
        state.players[0].health = 500
        _expire(state)
        assert state.game_mode == int(GameMode.NORMAL)
        assert state.levelnum_current == 1
        assert state.attract_timer == 0xFFFF   # start_attract_to_game stands down


class TestInputLockout:
    def test_fire_ignored_during_lockout_window(self):
        """While timer > threshold (first second), a button does not switch."""
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        # timer at loaded value -> above threshold -> locked out
        state.player_input_raw[0] = _IDLE & ~0x02   # player 0 FIRE held
        main_attract(state)
        assert state.game_mode == int(GameMode.SCORES), "switch blocked in lockout"

    def test_fire_switches_after_lockout(self):
        """Once timer <= threshold, player 0/3 FIRE restarts TITLE."""
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.SCORES)]
        state.player_input_raw[0] = _IDLE & ~0x02   # FIRE
        main_attract(state)
        assert state.game_mode == int(GameMode.TITLE)

    def test_player12_fire_restarts_scores(self):
        state = GameState()
        _attract(state, int(GameMode.TITLE))
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.TITLE)]
        state.player_input_raw[1] = _IDLE & ~0x02   # position 1 FIRE
        main_attract(state)
        assert state.game_mode == int(GameMode.SCORES)

    def test_direction_restarts_demo_from_position0(self):
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.SCORES)]
        state.player_input_raw[0] = _IDLE & ~0x80   # UP held on position 0
        main_attract(state)
        assert state.game_mode == int(GameMode.DEMO)

    def test_position0_direction_advances_demo_to_legend(self):
        state = GameState()
        _attract(state, int(GameMode.DEMO))
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.DEMO)]
        state.player_input_raw[0] = _IDLE & ~0x80

        main_attract(state)

        assert state.game_mode == int(GameMode.LEGEND)

    def test_position3_direction_still_restarts_demo(self):
        state = GameState()
        _attract(state, int(GameMode.DEMO))
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.DEMO)]
        state.player_input_raw[3] = _IDLE & ~0x80

        main_attract(state)

        assert state.game_mode == int(GameMode.DEMO)
        assert state.attract_timer == _LOADED_TIMER[int(GameMode.DEMO)]

    def test_free_play_ignores_magic_only(self):
        """In free play (two_player_mode 0) only FIRE qualifies, not MAGIC."""
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        state.two_player_mode = 0
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.SCORES)]
        state.player_input_raw[0] = _IDLE & ~0x01   # MAGIC only
        main_attract(state)
        assert state.game_mode == int(GameMode.SCORES), "magic must not switch in free play"

    def test_paid_play_accepts_magic(self):
        state = GameState()
        _attract(state, int(GameMode.SCORES))
        state.two_player_mode = 1
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.SCORES)]
        state.player_input_raw[0] = _IDLE & ~0x01   # MAGIC
        main_attract(state)
        assert state.game_mode == int(GameMode.TITLE)

    def test_select_phase_ignores_the_interruption_blocks(self):
        """0x445DC jumps straight past them when game_mode is 0."""
        state = GameState()
        state.game_mode = GameMode.NORMAL
        state.players[0].status = int(PlayerStatus.SELECTING)
        state.attract_timer = 100
        state.player_input_raw = [_IDLE & ~0x02] * 4   # everyone holding FIRE
        main_attract(state)
        assert state.game_mode == int(GameMode.NORMAL)


class TestLegendPaging:
    def test_direction_pages_legend(self):
        state = GameState()
        _attract(state, int(GameMode.LEGEND))
        state.attract_timer = _INPUT_THRESHOLD[int(GameMode.LEGEND)]
        state.attract_legend = 2
        state.player_input_raw[1] = _IDLE & ~0x80   # direction on position 1
        main_attract(state)
        assert state.attract_legend == 1
        assert state.game_mode == int(GameMode.LEGEND)

    def test_timer_expiry_pages_legend_without_restarting_it(self):
        """0x44882-0x4489C reloads only the timer; attract_legend != 2 then
        skips the start_attract_screen call at 0x44904."""
        state = GameState()
        _attract(state, int(GameMode.LEGEND))
        state.attract_legend = 2
        state.sound_log.clear()
        _expire(state)
        assert state.game_mode == int(GameMode.LEGEND)
        assert state.attract_legend == 1
        assert state.attract_timer == _LOADED_TIMER[int(GameMode.LEGEND)]
        assert state.sound_log == [], "paging is not a screen change"

    def test_last_page_hands_back_to_scores(self):
        state = GameState()
        _attract(state, int(GameMode.LEGEND))
        state.attract_legend = 0
        _expire(state)
        assert state.game_mode == int(GameMode.SCORES)


class TestStartAttractScreen:
    def test_screen_change_sounds_and_position_reset(self):
        """0x4444E/0x4445A/0x44462/0x4447A."""
        state = GameState()
        state.levelnum_current, state.mazenum_current = 42, 77
        state.sound_log.clear()
        start_attract_screen(state, int(GameMode.SCORES))
        assert state.levelnum_current == 1
        assert state.mazenum_current == 103
        assert state.sound_log[:2] == [_SOUND_SCREEN_CHANGE, _SOUND_THEME_FADE]

    def test_legend_rebuilds_the_whole_info_panel(self):
        """0x4453C-0x44542 calls the real setup_infopanel(-1)."""
        state = GameState()
        for panel in state.info_panel.players:
            panel.score_drawn = False
        start_attract_screen(state, int(GameMode.LEGEND))
        assert all(p.score_drawn for p in state.info_panel.players)

    @requires_roms
    def test_legend_loads_maze_103_as_attract_scenery(self):
        state = GameState()

        start_attract_screen(state, int(GameMode.LEGEND))

        assert state.mazenum_current == 103
        assert state.maze is not None

    @requires_roms
    def test_title_builds_its_fixed_playfield_and_mob_display(self):
        from gauntpy.playfield_vram import playfield_index

        state = GameState()
        start_attract_screen(state, int(GameMode.TITLE))

        assert state.playfield_ram[playfield_index(21, 8)] == 0x44B2
        assert any(state.playfield_color_ram)
        assert any(state.playfield_shadow_color_ram)
        assert state.mobs.picture[0x20] == 0x2000
        assert state.mobs.picture[0xBE] == 0x2727
        assert not any(state.alpha_ram)

    @requires_roms
    def test_every_attract_screen_restores_alpha_color_ram(self):
        for mode in (GameMode.SCORES, GameMode.TITLE, GameMode.DEMO, GameMode.LEGEND):
            state = GameState()
            start_attract_screen(state, int(mode))
            assert any(state.alpha_color_ram), mode

    def test_demo_rebuilds_the_whole_info_panel(self):
        """attract_demo_init 0x449DE-0x449E4, and it clears the first-encounter
        dialog flags at 0x449F6."""
        state = GameState()
        for panel in state.info_panel.players:
            panel.score_drawn = False
        state.dialog_first_encounter_flags = 0xFF
        start_attract_screen(state, int(GameMode.DEMO))
        assert all(p.score_drawn for p in state.info_panel.players)
        assert state.dialog_first_encounter_flags == 0

    def test_title_cycle_counter_wraps_at_thirteen(self):
        """attract_count (0x904B60) drives the periodic EEPROM re-read."""
        state = GameState()
        state.eeprom_save_path = "no-such-eeprom-file.json"
        for _ in range(_TITLE_SETTINGS_REFRESH_CYCLE - 1):
            start_attract_screen(state, int(GameMode.TITLE))
            state.sound_log.clear()
        assert state.attract_count == _TITLE_SETTINGS_REFRESH_CYCLE - 1
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.attract_count == 0

    def test_thirteenth_title_rereads_the_operator_settings(self, tmp_path):
        """0x444A4-0x444C2: an operator-menu change is picked up without a
        reboot, through WP-19's real loader."""
        from gauntpy.subsystems.eeprom import eeprom_save_settings

        saved = GameState()
        saved.eeprom_save_path = str(tmp_path / "eeprom.json")
        saved.game_settings = _SETTINGS_ATTRACT_SOUND
        saved.two_player_mode = 0
        eeprom_save_settings(saved)

        state = GameState()
        state.eeprom_save_path = saved.eeprom_save_path
        state.game_settings = 0
        state.two_player_mode = 1
        for _ in range(_TITLE_SETTINGS_REFRESH_CYCLE - 1):
            start_attract_screen(state, int(GameMode.TITLE))
        assert state.game_settings == 0, "no re-read before the 13th screen"
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.game_settings == _SETTINGS_ATTRACT_SOUND
        assert state.two_player_mode == 0


class TestDemoInit:
    def test_demo_switch_loads_demo_maze(self):
        state = GameState()
        start_attract_screen(state, int(GameMode.DEMO))
        assert state.game_mode == int(GameMode.DEMO)
        assert state.mazenum_current == 102
        assert state.frame_counter == 0

    def test_demo_streams_loaded_from_rom(self):
        """attract_demo_init installs the recorded streams and selects the Elf."""
        state = GameState()
        start_attract_screen(state, int(GameMode.DEMO))
        # Player 1's ROM stream (0x581C4) begins 1, 243 and joins at 254, 32.
        assert state.demo_streams[1][:2] == [1, 243]
        assert 254 in state.demo_streams[1], "the 0xFE join record must be present"
        assert state.demo_active_player == 1
        assert state.players[1].character == 3   # Elf
        assert state.players[1].health == 2000

    def test_join_records_are_the_documented_pair(self):
        """§6.2: the only two 0xFE records are FE 20 and FE 03, adjacent."""
        stream = GameState()
        start_attract_screen(stream, int(GameMode.DEMO))
        data = stream.demo_streams[1]
        joins = [i for i, b in enumerate(data) if b == 0xFE]
        assert len(joins) == 2
        assert [data[i + 1] for i in joins] == [0x20, 0x03]

    @requires_roms
    def test_demo_loads_the_maze_and_spawns_the_elf(self):
        """The DEMO screen shows a real world: maze 102's MOBs are placed and
        the scripted Elf (player 2) is dropped in at its PLAYERSTART."""
        state = GameState()
        start_attract_screen(state, int(GameMode.DEMO))
        assert state.maze is not None
        # The maze populated the MOB table (walls/monsters/items).
        assert len(state.mobs) > 0
        elf = state.players[1]
        assert elf.status == int(PlayerStatus.ALIVE_HERE)
        assert state.mobs.obj_type(elf.mob_slot) == int(MazeObjIds.PLAYERSTART)
        assert state.level_players_active >= 1

    @requires_roms
    def test_the_demo_screen_never_runs_the_post_loop_timers(self):
        """main_move_players counts a processed player at 0x4A8B4, inside the
        ``game_mode == 0`` arm of 0x4A8A2, and 0x4ACD4 gates the whole post-loop
        on that count.  So the real DEMO screen moves its hero for a full second
        while ``idle_timer`` and ``escape_timer`` -- the timed doors and the
        escape-timeout wall conversion -- stand completely still."""
        from gauntpy.mainloop import tick

        state = GameState()
        start_attract_screen(state, int(GameMode.DEMO))
        elf = state.players[1]
        start = (state.mobs.hpos[elf.mob_slot], state.mobs.vpos[elf.mob_slot])
        state.idle_timer, state.escape_timer = 5, 7

        moved = False
        for _ in range(60):
            tick(state)
            if state.game_mode != int(GameMode.DEMO):
                break                       # the screen expired; that is fine
            if (state.mobs.hpos[elf.mob_slot],
                    state.mobs.vpos[elf.mob_slot]) != start:
                moved = True

        assert moved, "the recorded stream still drives the demo hero"
        assert state.idle_timer == 5, "no timed-door countdown on the attract screen"
        assert state.escape_timer == 7

    @requires_roms
    def test_demo_elf_pushes_out_of_the_starting_box(self):
        """The opening script is DOWN 8, then DOWN 144 while pushing a wall."""
        from gauntpy.constants import MazeObjIds
        from gauntpy.mainloop import tick

        state = GameState()
        start_attract_screen(state, int(GameMode.DEMO))
        elf = state.players[1]
        start_y = vpos_y(state.mobs.vpos[elf.mob_slot])
        wall = next(
            slot for slot in range(32, 1024)
            if state.mobs.obj_type(slot) == int(MazeObjIds.WALL_MOVABLE)
        )
        wall_y = vpos_y(state.mobs.vpos[wall])

        for _ in range(600):
            tick(state)

        assert state.demo_stream_pos[1] >= 10
        assert vpos_y(state.mobs.vpos[elf.mob_slot]) == start_y + 112
        moved_wall = next(
            slot for slot in range(32, 1024)
            if state.mobs.obj_type(slot) == int(MazeObjIds.WALL_MOVABLE)
        )
        assert vpos_y(state.mobs.vpos[moved_wall]) == wall_y + 96

    @requires_roms
    def test_demo_recording_uses_the_mame_transporter_landing(self, tmp_path):
        from gauntpy.mainloop import tick

        state = GameState()
        state.eeprom_save_path = str(tmp_path / "demo-eeprom.json")
        start_attract_screen(state, int(GameMode.DEMO))
        elf = state.players[1]
        transported = False
        resumed_after_transport = False
        arrival_sparkle = False

        for _ in range(7000):
            tick(state)
            if elf.mob_slot:
                x = hpos_x(state.mobs.hpos[elf.mob_slot])
                y = vpos_y(state.mobs.vpos[elf.mob_slot])
                transported |= x == 92 and 240 <= y <= 242
                resumed_after_transport |= (
                    state.demo_stream_pos[1] >= 76
                    and x == 44
                    and 280 <= y <= 282
                )
            if state.player_tport_phase[1] >= 0:
                effect = 0x19 + 1
                if state.mobs.picture[effect]:
                    arrival_sparkle |= (
                        hpos_x(state.mobs.hpos[effect]) == 92
                        and vpos_y(state.mobs.vpos[effect]) == 240
                    )

        assert transported
        assert resumed_after_transport
        assert arrival_sparkle
        assert state.demo_stream_pos[1] >= 148
        assert elf.status == int(PlayerStatus.ALIVE_NEXT), "the Elf reached the exit"
        assert state.dialog_first_encounter_flags & 0x01000000


class TestLogoColors:
    def test_cadence_counter_advances(self):
        state = GameState()
        before = state.logo_color_timer
        main_logo_updcolors(state)
        assert state.logo_color_timer == (before + 1) & 0xFFFF

    def test_scores_rotates_the_rom_alpha_palette_block_every_sixteen_frames(self):
        state = GameState(game_mode=GameMode.SCORES)
        state.alpha_color_ram[144:160] = list(range(16))
        state.frame_counter = 0

        main_logo_updcolors(state)

        assert state.alpha_color_ram[144:160] == list(range(12, 16)) + list(range(12))

        state.frame_counter = 1
        before = list(state.alpha_color_ram)
        main_logo_updcolors(state)
        assert state.alpha_color_ram == before


class TestTitleLogoMotionSelection:
    def test_attract_sound_bit_is_settings_bit_14(self):
        """0x444DA masks game_settings with 0x4000 -- "Music/attract sound
        enable" in doc/05_data_reference.md §1.10."""
        assert _SETTINGS_ATTRACT_SOUND == 1 << 14

    def test_sound_enabled_titles_cycle_full_short_short(self):
        state = GameState()
        state.game_settings = _SETTINGS_ATTRACT_SOUND
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.title_logo_full_program is True
        assert state.title_intro_state == 2
        assert 0x3B in state.sound_log

        state.sound_log.clear()
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.title_logo_full_program is False
        assert state.title_intro_state == 1
        assert 0x3B not in state.sound_log
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.title_logo_full_program is False
        assert state.title_intro_state == 0
        state.sound_log.clear()
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.title_logo_full_program is True
        assert state.title_intro_state == 2
        assert 0x3B in state.sound_log

    def test_sound_disabled_selector_decrements_as_16_bit_word(self):
        state = GameState()
        start_attract_screen(state, int(GameMode.TITLE))
        assert state.title_logo_full_program is True
        assert state.title_intro_state == 0xFFFF
        assert 0x3B not in state.sound_log
