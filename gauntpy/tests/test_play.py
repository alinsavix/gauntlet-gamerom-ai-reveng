"""The playable runner's non-graphical half (``gauntpy.play``).

Everything here runs headless: ``run()`` opens a pygame window and is left to
manual testing, but argument handling, the ROM-directory fallback, level/maze
selection and the spawn are all ordinary functions, and they are what breaks
when the simulation underneath them changes shape.
"""

from __future__ import annotations

import pytest

from gauntpy import play
from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.state import GameState

from gex.roms import SLAPSTIC_ROMS, TILE_ROMS, _rom_dir

_ROM_PATH = _rom_dir()
_ROMS_EXIST = (
    _ROM_PATH.is_dir()
    and (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file()
    and (_ROM_PATH / TILE_ROMS[0][0]).is_file()
)

requires_roms = pytest.mark.skipif(
    not _ROMS_EXIST, reason=f"ROM files not available at {_ROM_PATH}"
)


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

class TestArguments:
    def test_level_must_be_at_least_one(self):
        """``maze_for_level`` returns None below 1, which silently fell
        through to ``mazenum_current`` (maze 0) instead of complaining."""
        import argparse

        for bad in ("0", "-3"):
            with pytest.raises(argparse.ArgumentTypeError):
                play._positive_level(bad)
        assert play._positive_level("7") == 7

    def test_scale_must_be_at_least_one(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            play._positive_scale("0")
        assert play._positive_scale("3") == 3

    def test_bad_level_exits_rather_than_loading_maze_zero(self):
        with pytest.raises(SystemExit):
            play.main(["--level", "0"])

    def test_unknown_character_is_rejected(self):
        with pytest.raises(SystemExit):
            play.main(["--character", "barbarian"])

    def test_every_character_choice_maps_to_a_class_index(self):
        assert set(play._CHARACTERS.values()) == set(Character)

    def test_missing_roms_exit_with_an_actionable_message(self, monkeypatch, capsys):
        monkeypatch.setenv("GEX_ROM_DIR", "")
        monkeypatch.setattr(play, "_ensure_rom_dir", lambda: None)

        with pytest.raises(SystemExit) as excinfo:
            play.main([])

        assert excinfo.value.code == 2
        assert "GEX_ROM_DIR" in capsys.readouterr().err

    def test_rom_dir_fallback_does_not_override_an_explicit_setting(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "somewhere-the-user-chose")
        play._ensure_rom_dir()
        import os

        assert os.environ["GEX_ROM_DIR"] == "somewhere-the-user-chose"

    def test_message_suppression_flag_is_forwarded_to_the_runner(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main(["--no-first-encounter-messages"])

        assert called["suppress_first_encounter_messages"] is True


def test_front_end_character_commit_uses_the_selected_hero_picture():
    """The no-ROM front-end path finalizes a real Wizard MOB with core artwork."""
    from gauntpy.coords import encode_hpos, encode_vpos_at_y, slot_to_pixels
    from gauntpy.subsystems.players import _PLAYER_IDLE_PICTURE, _PORT_DIR_TO_ROM_DIR
    from gauntpy.subsystems.session import main_start_game

    state = GameState(game_mode=GameMode.NORMAL, maze=object())
    start = 0x80
    x, y = slot_to_pixels(start)
    state.mobs.create(
        start, tile=0x1E0D, hpos=encode_hpos(x), vpos=encode_vpos_at_y(y),
        obj_type=MazeObjIds.PLAYERSTART,
    )
    state.players[1].status = PlayerStatus.SELECTING
    state.pending_character[1] = Character.WIZARD
    state.debounce_shift_magic[1] = 0x1C

    main_start_game(state)

    player = state.players[1]
    assert player.active
    assert state.mobs.picture[player.mob_slot] == _PLAYER_IDLE_PICTURE[
        int(Character.WIZARD) * 8 + _PORT_DIR_TO_ROM_DIR[player.direction]
    ]


# ---------------------------------------------------------------------------
# The mid-level drop
# ---------------------------------------------------------------------------

@requires_roms
class TestBuildState:
    def test_level_one_loads_maze_zero_and_spawns_a_hero(self):
        state = play.build_state(1, Character.VALKYRIE)

        assert state.game_mode == GameMode.NORMAL
        assert (state.levelnum_current, state.mazenum_current) == (1, 0)
        assert state.maze is not None

        player = state.players[0]
        assert player.active
        assert player.character == Character.VALKYRIE
        assert player.health == 750
        assert state.level_players_active == 1

    def test_the_hero_stands_on_a_real_cell_of_the_loaded_maze(self):
        state = play.build_state(1, Character.WARRIOR)
        slot = state.players[0].mob_slot
        assert state.mobs.is_occupied(slot)
        # The PLAYERSTART marker MOB *becomes* the hero, so its type stays
        # PLAYERSTART -- a MONST_* here would make the monster loop move it.
        assert state.mobs.obj_type(slot) == MazeObjIds.PLAYERSTART

    def test_a_level_past_the_opening_act_does_not_silently_replay_maze_zero(self):
        """There is no fixed level -> maze rule past level 5 (doc/06 §3.2);
        ``load_level`` reads ``mazenum_current``, so the runner has to seed it
        or every deep level would load maze 0."""
        state = play.build_state(9, Character.ELF)
        assert state.levelnum_current == 9
        assert state.mazenum_current == 8

    def test_a_deep_level_is_clamped_to_a_real_maze_number(self):
        from gex.constants import MAX_MAZE_NUM

        assert play.MAX_MAZE_NUM == MAX_MAZE_NUM
        state = play.build_state(500, Character.WIZARD)
        assert state.mazenum_current == MAX_MAZE_NUM

    def test_the_spawn_uses_the_core_rom_idle_picture(self):
        state = play.build_state(1, Character.ELF)
        from gauntpy.subsystems.players import (
            _PLAYER_IDLE_PICTURE,
            _PORT_DIR_TO_ROM_DIR,
        )

        player = state.players[0]
        assert state.mobs.picture[player.mob_slot] == _PLAYER_IDLE_PICTURE[
            int(Character.ELF) * 8 + _PORT_DIR_TO_ROM_DIR[player.direction]
        ]

    def test_a_built_level_survives_a_run_of_real_frames(self):
        """The whole point of the runner: ``game_frame`` drives the genuine
        simulation over a genuine maze without anything blowing up."""
        from gauntpy.mainloop import tick

        state = play.build_state(1, Character.WARRIOR)
        for _ in range(120):
            tick(state)

        assert state.frame_counter == 120
        assert state.players[0].active

    def test_the_mid_level_drop_arrives_with_a_scanned_exit_table(self):
        """The drop-in goes straight to ``maze.load_level`` -- it never touches
        the front end that used to be the only caller of ``exit_scan_level``.
        With the scan on the common load path it gets one anyway."""
        state = play.build_state(1, Character.WARRIOR)
        assert state.exit_slots
        for slot in state.exit_slots:
            assert state.mobs.obj_type(slot) == MazeObjIds.EXIT

    def test_post_death_coin_restores_the_same_full_starting_health(self):
        from gauntpy.subsystems.session import coincheck

        state = play.build_state(2, Character.WARRIOR)
        player = state.players[0]
        full_health = player.health
        player.health = 0
        player.status = PlayerStatus.REMOVED
        player.mob_slot = 0
        state.coin_counters = 1

        coincheck(state)

        assert player.health == full_health == 750
        assert player.status == PlayerStatus.SELECTING

    def test_moving_exits_actually_move_in_the_runner(self):
        """Level 4 is maze 3, which ships the ExitMoves flag and five exits.
        Without the scan ``exit_open_id`` stayed 0 and ``main_exit_move``
        returned at its first gate every frame -- the exit sat still forever.
        Driving real frames through ``tick`` is the end-to-end check.
        """
        from gauntpy.mainloop import tick

        state = play.build_state(4, Character.WARRIOR)
        assert state.exit_open_id, "the level must arrive with an open exit"
        assert state.level_players_active == 1, "main_exit_move needs a live player"

        start = state.exit_open_id
        for _ in range(400):                     # the period is 332 frames
            tick(state)

        assert state.exit_open_id != start
        assert state.mobs.obj_type(state.exit_open_id) == MazeObjIds.EXIT
