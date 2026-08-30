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
    def test_seed_accepts_integers_and_random(self):
        import argparse

        assert play._seed_value("1234") == 1234
        assert play._seed_value("0xBEEF") == 0xBEEF
        assert play._seed_value("random") == "random"
        for bad in ("-1", "65536", "not-a-seed"):
            with pytest.raises(argparse.ArgumentTypeError):
                play._seed_value(bad)

    def test_level_must_be_at_least_one(self):
        """``maze_for_level`` returns None below 1, which silently fell
        through to ``mazenum_current`` (maze 0) instead of complaining."""
        import argparse

        for bad in ("0", "-3"):
            with pytest.raises(argparse.ArgumentTypeError):
                play._positive_level(bad)
        assert play._positive_level("7") == 7

    def test_maze_number_is_independent_and_bounded(self):
        import argparse

        assert play._maze_number("0") == 0
        assert play._maze_number("116") == 116
        for bad in ("-1", "117"):
            with pytest.raises(argparse.ArgumentTypeError):
                play._maze_number(bad)

    def test_scale_must_be_at_least_one(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            play._positive_scale("0")
        assert play._positive_scale("3") == 3

    def test_inventory_counts_are_byte_sized(self):
        import argparse

        assert play._inventory_count("0") == 0
        assert play._inventory_count("255") == 255
        for bad in ("-1", "256"):
            with pytest.raises(argparse.ArgumentTypeError):
                play._inventory_count(bad)

    def test_bad_level_exits_rather_than_loading_maze_zero(self):
        with pytest.raises(SystemExit):
            play.main(["--level", "0"])

    def test_wrapped_level_requires_an_explicit_maze(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        with pytest.raises(SystemExit):
            play.main(["--level", "1000"])

        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))
        play.main(["--level", "9999", "--maze", "3"])
        assert (called["level"], called["maze_number"]) == (9999, 3)

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

    def test_reduce_text_flag_is_forwarded_to_the_runner(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main(["--reduce-text"])

        assert called["reduce_text"] is True

    def test_reduce_text_defaults_to_no_saved_state_override(
        self, monkeypatch,
    ):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main(["--load-state", "state.json"])

        assert called["reduce_text"] is False

    def test_reduce_text_sets_the_rom_operator_bit(self):
        state = GameState(game_settings=0)

        play._apply_operator_overrides(state, reduce_text=True)

        assert state.game_settings & 0x0400

    def test_direct_play_defaults_to_elf_and_accepts_an_override(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main([])
        assert called["character"] == Character.ELF
        assert called["scale"] == 4
        assert called["rng_seed"] == 0

        play.main(["--character", "wizard"])
        assert called["character"] == Character.WIZARD

    def test_level_and_maze_are_forwarded_independently(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main(["--level", "115", "--maze", "3"])

        assert called["level"] == 115
        assert called["maze_number"] == 3

    def test_explicit_seed_is_forwarded_and_random_uses_host_entropy(
        self, monkeypatch,
    ):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        monkeypatch.setattr("os.urandom", lambda count: b"\x12\x34")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main(["--seed", "1234"])
        assert called["rng_seed"] == 1234
        play.main(["--seed", "random"])
        assert called["rng_seed"] == 0x1234

    def test_direct_inventory_and_repeatable_powers_are_forwarded(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))

        play.main([
            "--keys", "4", "--potions", "3",
            "--power", "reflective-shots",
            "--power", "transportability",
        ])

        assert called["keys"] == 4
        assert called["potions"] == 3
        assert called["powers"] == (
            int(MazeObjIds.POWER_REFLECT),
            int(MazeObjIds.POWER_TRANSPORT),
        )

    def test_direct_start_items_are_rejected_with_attract(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")

        with pytest.raises(SystemExit):
            play.main(["--attract", "--potions", "1"])

    def test_saved_state_path_is_forwarded_without_direct_start_options(
        self, monkeypatch, tmp_path,
    ):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))
        path = tmp_path / "state.json"

        play.main(["--load-state", str(path), "--scale", "2"])

        assert called["load_state_path"] == path
        assert called["scale"] == 2

    def test_synthetic_scenario_path_is_forwarded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        called = {}
        monkeypatch.setattr(play, "run", lambda **kwargs: called.update(kwargs))
        path = tmp_path / "repro.gsc"

        play.main(["--scenario", str(path), "--scale", "2"])

        assert called["scenario_path"] == path
        assert called["scale"] == 2

    @pytest.mark.parametrize("option", [
        "--load-state", "--attract", "--level", "--maze", "--character", "--keys",
        "--potions", "--power", "--seed",
    ])
    def test_synthetic_scenario_rejects_other_start_modes(
        self, monkeypatch, option,
    ):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        values = {
            "--load-state": "state.json",
            "--level": "2",
            "--maze": "3",
            "--character": "wizard",
            "--keys": "1",
            "--potions": "1",
            "--power": "invisibility",
            "--seed": "1234",
        }
        argv = ["--scenario", "repro.gsc", option]
        if option in values:
            argv.append(values[option])

        with pytest.raises(SystemExit):
            play.main(argv)

    @pytest.mark.parametrize("option", [
        "--attract", "--level", "--maze", "--character", "--keys", "--potions", "--power",
        "--seed",
    ])
    def test_saved_state_rejects_other_start_modes(self, monkeypatch, option):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        values = {
            "--level": "2",
            "--maze": "3",
            "--character": "wizard",
            "--keys": "1",
            "--potions": "1",
            "--power": "invisibility",
            "--seed": "1234",
        }
        argv = ["--load-state", "state.json", option]
        if option in values:
            argv.append(values[option])

        with pytest.raises(SystemExit):
            play.main(argv)


def test_front_end_character_commit_uses_the_selected_hero_picture():
    """The no-ROM front-end path finalizes a real Wizard MOB with core artwork."""
    from gauntpy.coords import encode_hpos, encode_vpos_at_y, slot_to_pixels
    from gauntpy.subsystems.players import _ANIM_TABLE_IDLE, _PORT_DIR_TO_ROM_DIR
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
    assert state.mobs.picture[player.mob_slot] == _ANIM_TABLE_IDLE[
        int(Character.WIZARD) * 8 + _PORT_DIR_TO_ROM_DIR[player.direction]
    ]


# ---------------------------------------------------------------------------
# The mid-level drop
# ---------------------------------------------------------------------------

def test_playerstart_fallback_installs_the_live_character_palette(monkeypatch):
    from gauntpy.subsystems.display import (
        init_mob_color_ram, mob_palette_words,
    )

    state = GameState()
    init_mob_color_ram(state)
    monkeypatch.setattr(play, "player_join", lambda *_args: None)

    slot = play._spawn_player(state, Character.WARRIOR)

    assert state.mobs.hpos[slot] & 0x0F == 0x0C
    assert mob_palette_words(state, 0x0C) != mob_palette_words(GameState(), 0x0C)


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
        assert state.mazenum_current == 11
        assert state.maze_stride == 1

    def test_a_deep_level_advances_the_rotation_instead_of_becoming_a_maze(self):
        from gex.constants import MAX_MAZE_NUM

        assert play.MAX_MAZE_NUM == MAX_MAZE_NUM
        state = play.build_state(500, Character.WIZARD)
        assert state.mazenum_current == 68
        assert state.maze_stride == 6

    def test_an_explicit_maze_does_not_change_the_level_number(self):
        state = play.build_state(115, Character.WIZARD, maze_number=3)

        assert state.levelnum_current == 115
        assert state.mazenum_current == 3

    def test_the_spawn_uses_the_core_rom_idle_picture(self):
        state = play.build_state(1, Character.ELF)
        from gauntpy.subsystems.players import (
            _ANIM_TABLE_IDLE,
            _PORT_DIR_TO_ROM_DIR,
        )

        player = state.players[0]
        assert state.mobs.picture[player.mob_slot] == _ANIM_TABLE_IDLE[
            int(Character.ELF) * 8 + _PORT_DIR_TO_ROM_DIR[player.direction]
        ]

    def test_level_19_rom_maze_really_contains_four_it_creatures(self):
        state = play.build_state(19, Character.ELF, maze_number=18)

        assert state.mazenum_current == 18
        assert sum(
            state.mobs.obj_type(slot) == int(MazeObjIds.MONST_IT)
            for slot in range(32, 1024)
        ) == 4

    def test_power_on_seed_changes_which_level_16_exit_is_fake(self):
        first = play.build_state(16, Character.ELF, maze_number=15, rng_seed=0)
        second = play.build_state(16, Character.ELF, maze_number=15, rng_seed=10)

        def real_exit_index(state):
            return next(
                index for index, slot in enumerate(state.exit_slots)
                if not state.mobs.hpos[slot] & 0x10
            )

        # maze_new_level_setup's adaptive-food choice runs before
        # maze_scan_objects(0) chooses the real exit.
        assert real_exit_index(first) == 1
        assert real_exit_index(second) == 0

    def test_level_20_upper_right_passage_accepts_continued_downward_motion(self):
        from gauntpy.coords import hpos_x, vpos_y
        from gauntpy.subsystems.input import JOY_DOWN
        from gauntpy.subsystems.players import player_try_move

        state = play.build_state(20, Character.ELF, maze_number=19, keys=1)
        player = state.players[0]
        state.level_flags_4 |= 0x80
        for frame in range(60):
            state.frame_counter = frame
            state.movement_type = 2
            player_try_move(state, 0, JOY_DOWN, 0)

        assert hpos_x(state.mobs.hpos[player.mob_slot]) == 492
        assert vpos_y(state.mobs.vpos[player.mob_slot]) > 352

    def test_level_18_top_wall_coordinate_allows_lateral_movement(self):
        from gauntpy.coords import encode_hpos, encode_vpos_at_y, hpos_x, mob_cell_of
        from gauntpy.subsystems.input import JOY_LEFT, JOY_RIGHT
        from gauntpy.subsystems.players import player_try_move

        for direction, expected_x in ((JOY_LEFT, 266), (JOY_RIGHT, 270)):
            state = play.build_state(18, Character.ELF, maze_number=17)
            player = state.players[0]
            state.mobs.unlink_and_clear(player.mob_slot)
            slot = mob_cell_of(encode_hpos(268), encode_vpos_at_y(15))
            state.mobs.create(
                slot, 0x1E0D, encode_hpos(268, palette=12),
                encode_vpos_at_y(15, 3, 3), MazeObjIds.PLAYERSTART, 0,
            )
            player.mob_slot = slot
            state.level_flags_4 |= 0x80
            state.movement_type = 2

            player_try_move(state, 0, direction, 0)

            assert hpos_x(state.mobs.hpos[player.mob_slot]) == expected_x

    def test_level_17_reported_coordinate_has_no_static_downward_block(self):
        from gauntpy.coords import (
            encode_hpos, encode_vpos_at_y, hpos_x, mob_cell_of, vpos_y,
        )
        from gauntpy.subsystems.camera import snap_camera
        from gauntpy.subsystems.input import JOY_DOWN
        from gauntpy.subsystems.players import player_try_move

        state = play.build_state(17, Character.ELF, maze_number=16)
        player = state.players[0]
        state.mobs.unlink_and_clear(player.mob_slot)
        slot = mob_cell_of(encode_hpos(396), encode_vpos_at_y(176, 3, 3))
        state.mobs.create(
            slot, 0x1E0D, encode_hpos(396, palette=12),
            encode_vpos_at_y(176, 3, 3), MazeObjIds.PLAYERSTART, 0,
        )
        player.mob_slot = slot
        state.player_tile_or_tport_dest[0] = slot
        snap_camera(state)
        state.movement_type = 2

        player_try_move(state, 0, JOY_DOWN, 0)

        live = player.mob_slot
        assert (hpos_x(state.mobs.hpos[live]), vpos_y(state.mobs.vpos[live])) == (
            396, 178,
        )

    def test_level_one_top_wall_stops_at_rom_anchor_and_allows_diagonal_slide(self):
        from gauntpy.coords import hpos_x, vpos_y
        from gauntpy.mainloop import tick
        from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT, JOY_UP

        state = play.build_state(1, Character.ELF)
        player = state.players[0]

        for _ in range(40):
            state.player_input_raw[0] = JOY_IDLE & ~JOY_UP
            tick(state)

        slot = player.mob_slot
        assert vpos_y(state.mobs.vpos[slot]) == 16
        x_before = hpos_x(state.mobs.hpos[slot])

        for _ in range(4):
            state.player_input_raw[0] = JOY_IDLE & ~JOY_UP & ~JOY_RIGHT
            tick(state)

        slot = player.mob_slot
        assert vpos_y(state.mobs.vpos[slot]) == 16
        assert hpos_x(state.mobs.hpos[slot]) > x_before

    def test_level_18_left_seam_coordinate_matches_rom_movement(self):
        from gauntpy.coords import (
            encode_hpos, encode_vpos_at_y, hpos_x, mob_cell_of, vpos_y,
        )
        from gauntpy.subsystems.camera import snap_camera
        from gauntpy.subsystems.input import JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_UP
        from gauntpy.subsystems.players import player_try_move

        expected = (
            (JOY_LEFT, (14, 10)),
            (JOY_RIGHT, (18, 10)),
            (JOY_UP, (16, 10)),
            (JOY_DOWN, (16, 12)),
        )
        for direction, position in expected:
            state = play.build_state(18, Character.ELF, maze_number=17)
            player = state.players[0]
            state.mobs.unlink_and_clear(player.mob_slot)
            slot = mob_cell_of(encode_hpos(16), encode_vpos_at_y(10))
            state.mobs.create(
                slot, 0x1E0D, encode_hpos(16, palette=12),
                encode_vpos_at_y(10, 3, 3), MazeObjIds.PLAYERSTART, 0,
            )
            player.mob_slot = slot
            state.player_tile_or_tport_dest[0] = slot
            snap_camera(state)
            state.movement_type = 2

            player_try_move(state, 0, direction, 0)

            live = player.mob_slot
            assert (
                hpos_x(state.mobs.hpos[live]),
                vpos_y(state.mobs.vpos[live]),
            ) == position

    def test_direct_start_inventory_and_powers_initialize_live_state(self):
        from gauntpy.constants import PlayerPower
        from gauntpy.subsystems.players import (
            _INVIS_TIMER_LOAD,
            _CHARACTER_REPULSE_TIMER_INIT,
            _SUPERSHOT_CHARGES,
        )

        state = play.build_state(
            1, Character.ELF, keys=4, potions=3,
            powers=(
                int(MazeObjIds.POWER_INVIS),
                int(MazeObjIds.POWER_REPULSE),
                int(MazeObjIds.POWER_REFLECT),
                int(MazeObjIds.POWER_TRANSPORT),
                int(MazeObjIds.POWER_SUPERSHOT),
            ),
        )
        player = state.players[0]

        assert (player.keysnum, player.potionsnum) == (4, 3)
        assert player.powers & (
            int(PlayerPower.INVIS)
            | int(PlayerPower.REPULSE)
            | int(PlayerPower.REFLECT)
            | int(PlayerPower.TRANSPORT)
            | int(PlayerPower.SUPERSHOT)
        )
        assert state.player_invis_timer[0] == _INVIS_TIMER_LOAD
        assert state.player_repulse_timer[0] == _CHARACTER_REPULSE_TIMER_INIT[Character.ELF]
        assert player.supershot == _SUPERSHOT_CHARGES

    def test_a_built_level_survives_a_run_of_real_frames(self):
        """The whole point of the runner: ``game_frame`` drives the genuine
        simulation over a genuine maze without anything blowing up."""
        from gauntpy.mainloop import tick

        state = play.build_state(1, Character.WARRIOR)
        for _ in range(120):
            tick(state)

        assert state.frame_counter == 120
        assert state.players[0].active

    def test_f4_state_can_resume_deterministically(self, tmp_path):
        from gauntpy.coords import hpos_x
        from gauntpy.mainloop import tick
        from gauntpy.render.state_dump import dump_game_state, load_game_state
        from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT

        saved = dump_game_state(
            play.build_state(1, Character.ELF, keys=2, potions=1), tmp_path,
        )
        first = load_game_state(saved)
        second = load_game_state(saved)
        start_x = hpos_x(first.mobs.hpos[first.players[0].mob_slot])

        for state in (first, second):
            state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT
            for _ in range(12):
                tick(state)

        assert first.frame_counter == second.frame_counter == 12
        assert hpos_x(first.mobs.hpos[first.players[0].mob_slot]) > start_x
        assert first.rng.seed == second.rng.seed
        assert first.players == second.players
        assert first.mobs.picture == second.mobs.picture
        assert first.mobs.hpos == second.mobs.hpos
        assert first.mobs.vpos == second.mobs.vpos
        assert first.playfield_ram == second.playfield_ram
        assert first.alpha_ram == second.alpha_ram

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
