"""ROM-family ownership and compatibility without wrapper implementations."""

import ast
import inspect

import pytest

from gauntpy import playfield
from gauntpy.constants import Character, PlayerStatus
from gauntpy.state import GameState
from gauntpy.game.subsystems import (
    player_animation, player_names, player_transport, players, shots,
)


@pytest.mark.parametrize(
    "owner,facade,names",
    [
        (
            player_names, players,
            (
                "_secret_crc16", "secret_code_for", "secret_code_build",
                "secret_getname", "secret_name_entry_update", "highscore_check",
                "name_entry_step_char", "_name_entry_initials",
                "_name_entry_commit_pressed", "_name_entry_finish",
                "player_death_sequence", "_name_entry_edit",
            ),
        ),
        (
            player_animation, players,
            (
                "_rom_picture_table", "_player_animation_action",
                "update_player_sprite", "update_player_sprites",
            ),
        ),
        (playfield, shots, ("pf_replace",)),
    ],
)
def test_compatibility_exports_are_the_owned_functions(owner, facade, names):
    definitions = {
        node.name for node in ast.parse(inspect.getsource(facade)).body
        if isinstance(node, ast.FunctionDef)
    }
    for name in names:
        function = getattr(owner, name)
        assert getattr(facade, name) is function
        assert function.__module__ == owner.__name__
        assert name not in definitions, "a facade must not duplicate the ROM body"


@pytest.mark.parametrize(
    "name",
    (
        "_ANIM_TABLE_IDLE", "_ANIM_TABLE_WALKING", "_ANIM_TABLE_FIGHTING",
        "_ANIM_TABLE_SHOOTING", "_PLAYER_EXIT_PICTURE", "_PORT_DIR_TO_ROM_DIR",
        "_INVISIBILITY_FLASH_MASKS",
    ),
)
def test_animation_tables_have_one_owner(name):
    assert getattr(players, name) is getattr(player_animation, name)
    assert player_animation.update_player_sprite.__globals__[name] is getattr(
        player_animation, name,
    )


@pytest.mark.parametrize("module", (player_names, player_animation, playfield))
def test_game_families_do_not_import_host_or_rendering(module):
    forbidden = {"host", "render", "pygame", "PIL", "gex"}
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            imports = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports = [node.module or ""]
            imports.extend(alias.name for alias in node.names)
        else:
            continue
        assert all(not forbidden.intersection(name.split(".")) for name in imports)


def test_transport_and_shots_import_the_shared_game_playfield_owner():
    for module in (player_transport, shots):
        imports = [
            node for node in ast.walk(ast.parse(inspect.getsource(module)))
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "pf_replace" for alias in node.names)
        ]
        assert len(imports) == 1
        assert (imports[0].level, imports[0].module) == (2, "playfield")


def test_distinct_editors_use_the_same_owned_rom_character_helper():
    for editor in (
        player_names._name_entry_edit,
        player_names.secret_name_entry_update,
    ):
        assert editor.__globals__["name_entry_step_char"] is (
            player_names.name_entry_step_char
        )
        assert editor.__globals__["_name_entry_commit_pressed"] is (
            player_names._name_entry_commit_pressed
        )


@pytest.mark.parametrize(
    "fighting,walking,shooting,expected",
    [
        (1, 1, -1, 0x0D6C),  # fighting outranks walking and shooting
        (0, 1, -1, 0x0BD8),  # walking outranks shooting
        (0, 0, -1, 0x0C90),
        (0, 0, 0, 0x0BD8),
    ],
)
def test_owned_picture_writer_preserves_action_counters_and_rng(
    fighting, walking, shooting, expected,
):
    state = GameState()
    player = state.players[0]
    player.status = int(PlayerStatus.ALIVE_HERE)
    player.health = 500
    player.mob_slot = 0x80
    player.character = int(Character.WARRIOR)
    player.direction = 6  # up in the port's direction encoding
    player.anim_counter = 4
    state.player_fighting_dir[0] = fighting
    state.player_walking[0] = walking
    state.player_shooting[0] = shooting
    seed = state.rng.seed

    player_animation.update_player_sprite(state, 0)

    assert state.mobs.picture[0x80] == expected
    assert player.anim_counter == 4
    assert state.player_fighting_dir[0] == fighting
    assert state.player_walking[0] == walking
    assert state.player_shooting[0] == shooting
    assert state.rng.seed == seed
