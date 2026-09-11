"""Canonical game ownership without legacy module aliases."""

import ast
import importlib
import inspect
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "gauntpy"
CORE_MODULES = (
    "alpha_memory", "constants", "coords", "eeprom_device", "mainloop", "maze",
    "maze_data", "mob", "playfield", "playfield_vram", "rng", "romtext", "state",
)
COMPATIBILITY_EXPORTS = {
    "players": set("""
        player_add_score_with_mult update_player_sprite update_player_sprites
        secret_code_for secret_code_build secret_getname secret_name_entry_update
        highscore_check name_entry_step_char player_death_sequence
        mob_probe_down mob_probe_left mob_probe_right mob_probe_up
        door_open_start initialize_player_temporary_power maze_convert_walls_to_exits
        open_timed_doors player_tile_interact calc_score_per_coin main_handle_death
        main_health_countdown player_damage_sample_update player_hurt_palette_vblank
        player_inv_update player_join player_join_finalize player_lowhealth
        player_resetall player_resetcounters player_start_inner setup_infopanel
        show_continue_prompt speech_welcome migrate_player_record player_try_move
        corner_squeeze_geometry handle_tport nearby_mob_clearance_test player_tport
        scan_move_path_interactions squeeze_through_check tile_on_screen_test
        tport_check_dest tport_player_move tport_transition_arm
        demo_playback_start demo_record_word player_joystick_word
    """.split()),
    "exits": set("""
        in_bonus_room in_secret_room player_activecount advance_level_countdowns
        compute_next_level maze_checknum player_exit_sequence show_level_start_screen
        update_monster_spawn_bonus_from_score_per_coin CHALLENGE_COUNT CHALLENGE_FIRST
        TRICK_BEPUSHY TRICK_DIET TRICK_IT TRICK_NOFOOLED TRICK_NOGETHIT
        TRICK_NOGREEDY1 TRICK_NOGREEDY2 TRICK_NOHURTFRIENDS TRICK_NONE
        TRICK_NOUSEINVUL TRICK_NO_TREASURE TRICK_SAVESUPERSHOTS TRICK_WATCHSHOOT1
        TRICK_WATCHSHOOT2 secret_check secret_check_winner secret_new_level_setup
        secret_room_spawn secret_trick_check secret_trick_progress secret_trick_set
        treasure_collected main_treasure_timer show_level_end_bonus_screen
    """.split()),
    "monsters": set("""
        player_add_score_with_mult monster_playerhit player_hurt_speech_timer
        apply_direction_from_delta find_unused_shot monster_create_shot
        monster_find_and_shoot monster_shooter_in_view GENERATOR_RETRY_RELOAD
        generator_candidate_slot handle_generate monster_walk_picture supersorc_place
        tile_occupancy_test tile_on_screen_d4 monster_update_anim_tile
    """.split()),
    "shots": set("""
        pf_replace player_add_score_with_mult shot_collision_candidate_core
        shot_mob_collision shot_onscreen_check shot_reflect_calc SURVIVES
        death_damage_accumulate dragon_player_proximity resolve_shot_hit CONSUMED
        playfield_showscore shot_impact_spawn tport_cycle_start wall_crumble
        wall_crumble_descriptor wall_crumble_palette lobber_accumulator_seed
        shot_cell shot_picture shot_velocity
    """.split()),
}


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_modules_live_in_the_game_package(name):
    module = importlib.import_module(f"gauntpy.game.{name}")
    assert Path(module.__file__) == SOURCE / "game" / f"{name}.py"


@pytest.mark.parametrize(
    "name",
    sorted(path.stem for path in (SOURCE / "game" / "subsystems").glob("*.py")
           if path.stem != "__init__"),
)
def test_subsystem_modules_live_in_the_game_package(name):
    module = importlib.import_module(f"gauntpy.game.subsystems.{name}")
    assert Path(module.__file__) == SOURCE / "game" / "subsystems" / f"{name}.py"


@pytest.mark.parametrize("name", (*CORE_MODULES, "subsystems"))
def test_removed_game_module_paths_are_not_importable(name):
    module_name = f"gauntpy.{name}"
    with pytest.raises(ModuleNotFoundError) as error:
        importlib.import_module(module_name)
    assert error.value.name == module_name


def test_public_package_exports_are_the_game_objects():
    import gauntpy
    from gauntpy import game

    for name in gauntpy.__all__:
        assert getattr(gauntpy, name) is getattr(game, name)


def test_tick_uses_its_game_frame_binding(monkeypatch):
    from gauntpy.game import mainloop
    from gauntpy.game.state import GameState

    calls = []
    monkeypatch.setattr(mainloop, "game_frame", lambda state, **kwargs: calls.append(state))
    state = GameState()
    mainloop.tick(state)
    assert calls == [state]


@pytest.mark.parametrize("facade_name", sorted(COMPATIBILITY_EXPORTS))
def test_family_compatibility_exports_are_explicit_and_preserve_identity(facade_name):
    facade = importlib.import_module(f"gauntpy.game.subsystems.{facade_name}")
    tree = ast.parse(inspect.getsource(facade))
    exports = {
        alias.name: node
        for node in tree.body if isinstance(node, ast.ImportFrom)
        for alias in node.names if alias.asname == alias.name
    }
    assert set(exports) == COMPATIBILITY_EXPORTS[facade_name]
    for name, node in exports.items():
        owner = importlib.import_module(
            "." * node.level + node.module, facade.__package__,
        )
        value = getattr(owner, name)
        assert getattr(facade, name) is value
        if inspect.isfunction(value):
            assert value.__module__ == owner.__name__


def test_game_imports_neither_host_nor_rasterizer():
    forbidden = {"host", "render", "pygame", "PIL", "gex", "time", "random"}
    violations = []
    for path in (SOURCE / "game").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(forbidden.intersection(name.split(".")) for name in names):
                violations.append((str(path.relative_to(SOURCE)), node.lineno, names))
    assert violations == []


def test_legacy_game_module_files_are_absent():
    for name in CORE_MODULES:
        assert not (SOURCE / f"{name}.py").exists()
    assert not (SOURCE / "subsystems").exists()
