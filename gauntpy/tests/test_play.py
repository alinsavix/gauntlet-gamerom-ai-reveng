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

    def test_performance_durations_must_be_positive(self):
        import argparse

        assert play._positive_frame_count("600") == 600
        assert play._positive_seconds("1.5") == 1.5
        for parser, bad in (
            (play._positive_frame_count, "0"),
            (play._positive_seconds, "0"),
            (play._positive_seconds, "-1"),
        ):
            with pytest.raises(argparse.ArgumentTypeError):
                parser(bad)

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

    def test_host_runtime_flags_default_off_and_can_be_enabled(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        calls = []
        monkeypatch.setattr(play, "run", lambda **kwargs: calls.append(kwargs))

        play.main([])
        play.main(["--sound"])
        play.main(["--sound", "--uncapped"])

        assert calls[0]["sound_enabled"] is False
        assert calls[0]["uncapped"] is False
        assert calls[1]["sound_enabled"] is True
        assert calls[1]["uncapped"] is False
        assert calls[2]["sound_enabled"] is False
        assert calls[2]["uncapped"] is True

    def test_performance_modes_are_forwarded_to_the_runner(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        calls = []
        monkeypatch.setattr(play, "run", lambda **kwargs: calls.append(kwargs))

        play.main(["--benchmark"])
        play.main(["--benchmark", "25"])
        play.main(["--stresstest", "3.5"])
        play.main(["--benchmark", "25", "--workload", "benchmark-mobs"])

        assert calls[0]["benchmark_frames"] == 600
        assert calls[1]["benchmark_frames"] == 25
        assert calls[2]["stress_seconds"] == 3.5
        assert calls[3]["workload_name"] == "benchmark-mobs"

    def test_workload_catalog_does_not_require_roms(self, monkeypatch, capsys):
        monkeypatch.delenv("GEX_ROM_DIR", raising=False)
        monkeypatch.setattr(
            play, "run", lambda **_kwargs: pytest.fail("listing must not run the game"),
        )

        play.main(["--list-workloads"])

        output = capsys.readouterr().out
        assert "rom-title" in output
        assert "benchmark-generators" in output

    def test_workload_requires_a_performance_mode(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")

        with pytest.raises(SystemExit):
            play.main(["--workload", "benchmark-empty"])

    def test_ctrl_c_exits_130_without_a_traceback(self, monkeypatch, capsys):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")

        def interrupt(**_kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(play, "run", interrupt)

        with pytest.raises(SystemExit) as excinfo:
            play.main([])

        assert excinfo.value.code == 130
        assert capsys.readouterr().err == "\ngauntpy interrupted\n"

    @pytest.mark.parametrize("mode", ["--benchmark", "--stresstest"])
    def test_performance_modes_reject_sound(self, monkeypatch, mode):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")
        argv = [mode, "2", "--sound"]

        with pytest.raises(SystemExit):
            play.main(argv)

    def test_stress_mode_owns_its_screen_selection(self, monkeypatch):
        monkeypatch.setenv("GEX_ROM_DIR", "configured")

        for options in (["--level", "12"], ["--scenario", "fixture.gsc"]):
            with pytest.raises(SystemExit):
                play.main(["--stresstest", "2", *options])

    def test_benchmark_loop_excludes_warmup_and_uses_host_raster_timing(
        self, monkeypatch, capsys,
    ):
        from gauntpy.render import host as host_module

        state = GameState()
        calls = {"wait": 0, "present": 0, "tick": 0}

        class FakeHost:
            paused = False
            treasure_timer_paused = False
            last_render_time_ms = 3.25

            def __init__(self, **kwargs):
                assert kwargs["uncapped"] is True

            def wait_for_vblank(self, current):
                assert current is state
                calls["wait"] += 1

            def present(self, current):
                assert current is state
                calls["present"] += 1

            def close(self):
                pass

        clock_value = 0.0

        def clock():
            nonlocal clock_value
            clock_value += 0.001
            return clock_value

        monkeypatch.setattr(play, "build_state", lambda *_args, **_kwargs: state)
        monkeypatch.setattr(play, "tick", lambda *_args, **_kwargs: calls.__setitem__(
            "tick", calls["tick"] + 1,
        ))
        monkeypatch.setattr(play, "perf_counter", clock)
        monkeypatch.setattr(host_module, "HostShell", FakeHost)

        play.run(benchmark_frames=2, scale=1)

        assert calls == {"wait": 4, "present": 4, "tick": 4}
        assert state.eeprom_persistence_enabled is False
        output = capsys.readouterr().out
        assert "gauntpy benchmark: 2 frames at scale 1" in output
        assert "   3.250" in output

    def test_benchmark_all_runs_each_named_workload(self, monkeypatch, capsys):
        from gauntpy.render import host as host_module

        built = []

        class FakeHost:
            paused = False
            treasure_timer_paused = False
            last_render_time_ms = 1.0

            def __init__(self, **_kwargs):
                pass

            def wait_for_vblank(self, _state):
                pass

            def present(self, _state):
                pass

            def close(self):
                pass

        def build_workload(workload, _seed):
            built.append(workload.name)
            return GameState()

        clock_value = 0.0

        def clock():
            nonlocal clock_value
            clock_value += 0.001
            return clock_value

        monkeypatch.setattr(play, "_build_workload_state", build_workload)
        monkeypatch.setattr(play, "tick", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(play, "perf_counter", clock)
        monkeypatch.setattr(host_module, "HostShell", FakeHost)

        play.run(benchmark_frames=1, workload_name="all", scale=1)

        assert built == [workload.name for workload in play.WORKLOADS]
        output = capsys.readouterr().out
        assert output.count("gauntpy benchmark:") == len(play.WORKLOADS)
        assert "workload benchmark-cyclic-walls" in output

    def test_stress_loop_advances_each_phase_in_order(
        self, monkeypatch, capsys,
    ):
        from gauntpy.render import host as host_module

        built_phases = []

        class FakeHost:
            paused = False
            treasure_timer_paused = False

            def __init__(self, **kwargs):
                assert kwargs["uncapped"] is True

            def wait_for_vblank(self, _state):
                pass

            def present(self, _state):
                pass

            def close(self):
                pass

        clock_value = 0.0

        def clock():
            nonlocal clock_value
            clock_value += 0.001
            return clock_value

        def build_phase(index, _seed):
            built_phases.append(index)
            return GameState(eeprom_persistence_enabled=False)

        monkeypatch.setattr(play, "_build_stress_state", build_phase)
        monkeypatch.setattr(play, "tick", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(play, "perf_counter", clock)
        monkeypatch.setattr(host_module, "HostShell", FakeHost)

        play.run(stress_seconds=1.0, scale=1)

        assert built_phases[:len(play._STRESS_PHASES)] == list(
            range(len(play._STRESS_PHASES))
        )
        assert "stress test complete" in capsys.readouterr().out

    def test_muted_default_does_not_probe_the_sound_library(self, monkeypatch):
        monkeypatch.setattr(
            play, "_sound_dir",
            lambda: pytest.fail("muted runs must not inspect the sound library"),
        )

        assert play._enabled_sound_dir(False) is None

    def test_sound_flag_resolves_the_configured_library(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GAUNTPY_SOUND_DIR", str(tmp_path))

        assert play._enabled_sound_dir(True) == tmp_path

    def test_host_frame_limit_policy_does_not_require_pygame(self):
        from gauntpy.constants import FRAMES_PER_SECOND
        from gauntpy.render.host import HostShell

        class Clock:
            def __init__(self):
                self.calls = []

            def tick(self, limit):
                self.calls.append(limit)

        for uncapped, expected in ((False, [FRAMES_PER_SECOND]), (True, [])):
            shell = object.__new__(HostShell)
            shell.clock = Clock()
            shell.uncapped = uncapped
            shell._limit_frame_rate()
            assert shell.clock.calls == expected

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

    def test_seed_zero_level_one_survives_the_idle_escape_conversion(self):
        """The default Elf/reduced-text run stays valid past frame 21,008.

        Frame 21,000 converts every eligible wall through ``mob_place_tile``.
        The former picture-zero ``mob_create`` approximation put those exits in
        the depth chain, and a monster moving at frame 21,008 linked one twice.
        """
        from gauntpy.mainloop import tick
        from gauntpy.maze import TILE_MARKER_PICTURE
        from gauntpy.subsystems.players import _ESCAPE_TIMER_LIMIT

        state = play.build_state(1, Character.ELF, rng_seed=0)
        play._apply_operator_overrides(state, reduce_text=True)

        for _ in range(_ESCAPE_TIMER_LIMIT + 8):
            tick(state)

        chain = list(state.mobs.iter_chain())
        converted_exits = [
            slot for slot in range(32, 1024)
            if state.mobs.obj_type(slot) == int(MazeObjIds.EXIT)
        ]
        assert state.frame_counter == _ESCAPE_TIMER_LIMIT + 8
        assert len(chain) == len(set(chain))
        assert converted_exits
        assert all(
            state.mobs.picture[slot] == TILE_MARKER_PICTURE
            for slot in converted_exits
        )
        assert not set(converted_exits) & set(chain)

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
