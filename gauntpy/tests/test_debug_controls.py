"""Host troubleshooting shortcuts preserve coherent game-side state."""

from __future__ import annotations

import pytest

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.render.debug_controls import (
    debug_add_key,
    debug_add_potion,
    debug_enable_secret_room,
    debug_force_secret_room,
    debug_skip_level,
)
from gauntpy.state import GameState

from gex.roms import SLAPSTIC_ROMS, _rom_dir

_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not _ROM_PATH.is_dir() or not (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file(),
    reason=f"ROM files not available at {_ROM_PATH}",
)


def _active_state() -> GameState:
    state = GameState(game_mode=GameMode.NORMAL)
    state.players[0].status = PlayerStatus.ALIVE_HERE
    state.level_players_active = 1
    return state


def test_add_key_and_potion_update_active_player_inventory():
    state = _active_state()

    assert debug_add_key(state, 0)
    assert debug_add_potion(state, 0)

    assert state.players[0].keysnum == 1
    assert state.players[0].potionsnum == 1
    assert any(state.alpha_ram)


def test_inventory_shortcuts_reject_inactive_or_invalid_players():
    state = GameState()

    assert not debug_add_key(state, 0)
    assert not debug_add_potion(state, -1)
    assert state.players[0].keysnum == 0
    assert state.players[0].potionsnum == 0


class _Maze:
    def __init__(self, secret: int):
        self.secret = secret


def test_enable_secret_room_arms_current_maze_through_level_setup():
    state = _active_state()
    state.levelnum_current = 20
    state.mazenum_current = 40
    state.maze = _Maze(13)
    state.secret_possible_counter = 7

    assert debug_enable_secret_room(state)

    assert state.secret_possible_counter == 0
    assert state.secret_trick_id == 13
    assert state.secret_player == -1


def test_enabled_secret_trick_enters_room_only_after_exit_check_passes():
    from gauntpy.subsystems import exits

    state = _active_state()
    state.levelnum_current = 20
    state.mazenum_current = 40
    state.level_next_treasure = 2
    state.maze = _Maze(exits.TRICK_DIET)

    assert debug_enable_secret_room(state)
    assert state.secret_player == -1

    exits.secret_trick_check(state, 0)
    state.players[0].status = PlayerStatus.ALIVE_NEXT
    exits.show_level_start_screen(state)

    assert state.secret_player == 0
    assert state.mazenum_current in (115, 116)


def test_enable_secret_room_rejects_maze_without_current_objective():
    state = _active_state()
    state.maze = _Maze(0)
    state.secret_possible_counter = 7

    assert not debug_enable_secret_room(state)
    assert state.secret_possible_counter == 7
    assert state.secret_trick_id == 0


def test_enable_secret_room_applies_normal_solo_party_cancellation():
    state = _active_state()
    state.levelnum_current = 20
    state.mazenum_current = 40
    state.maze = _Maze(15)
    state.secret_possible_counter = 7

    assert not debug_enable_secret_room(state)
    assert state.secret_possible_counter == 7
    assert state.secret_trick_id == 0


def test_force_secret_room_marks_only_selected_live_player():
    state = _active_state()
    state.levelnum_current = 20
    state.mazenum_current = 40
    state.secret_trick_id = 13
    before = list(state.secret_tricks_flags)

    assert debug_force_secret_room(state, 0)

    assert state.secret_player == 0
    assert state.secret_trick_id == 0
    assert state.secret_tricks_flags == before


def test_force_secret_room_winner_cannot_be_replaced_by_exit_objective_check():
    from gauntpy.subsystems import exits

    state = _active_state()
    state.levelnum_current = 20
    state.mazenum_current = 40
    state.secret_trick_id = exits.TRICK_DIET
    state.players[1].status = PlayerStatus.ALIVE_HERE

    assert debug_force_secret_room(state, 0)
    exits.secret_trick_check(state, 1)

    assert state.secret_player == 0


def test_forced_secret_winner_enters_through_normal_status_handoff():
    from gauntpy.subsystems import exits

    state = _active_state()
    state.levelnum_current = 20
    state.mazenum_current = 40
    state.level_next_treasure = 2

    assert debug_force_secret_room(state, 0)
    assert state.mazenum_current == 40

    state.players[0].status = PlayerStatus.ALIVE_NEXT
    exits.show_level_start_screen(state)

    assert state.mazenum_current in (115, 116)


def test_force_secret_room_rejects_before_secret_rooms_are_reachable():
    state = _active_state()
    state.levelnum_current = 5
    state.mazenum_current = 4

    assert not debug_force_secret_room(state, 0)
    assert state.secret_player == -1


def test_secret_room_shortcuts_reject_bonus_rooms_and_inactive_players():
    state = _active_state()
    state.mazenum_current = 115
    state.maze = _Maze(13)
    assert not debug_enable_secret_room(state)
    assert not debug_force_secret_room(state, 0)

    state.mazenum_current = 40
    state.players[0].status = PlayerStatus.REMOVED
    assert not debug_enable_secret_room(state)
    assert not debug_force_secret_room(state, 0)


@requires_roms
def test_skip_level_uses_rotation_and_preserves_inventory():
    from gauntpy.play import build_state

    state = build_state(1, Character.ELF, keys=2, potions=3)

    assert debug_skip_level(state)

    assert (state.levelnum_current, state.mazenum_current) == (2, 1)
    assert state.players[0].status == int(PlayerStatus.ALIVE_NEXT)
    assert state.players[0].keysnum == 2
    assert state.players[0].potionsnum == 3
    assert state.players[0].mob_slot
    assert state.global_delay_timer == 0xB4
    assert state.level_start_pending
    assert any(
        state.alpha_ram[row * 64 + column]
        for row in range(30)
        for column in range(29)
    )

    from gauntpy.subsystems.session import main_start_game

    for _ in range(0xB4):
        main_start_game(state)
    assert state.players[0].status == int(PlayerStatus.ALIVE_HERE)
    assert state.players[0].mob_slot
    assert state.global_delay_timer == 0
    assert not state.level_start_pending


def test_skip_level_rejects_non_gameplay_modes():
    state = _active_state()
    state.game_mode = GameMode.TITLE

    assert not debug_skip_level(state)


@requires_roms
def test_skip_level_advances_treasure_countdown_before_start_screen():
    from gauntpy.play import build_state

    state = build_state(7, Character.ELF)
    state.level_next_treasure = 1
    state.treas_mazerand_num = 104

    assert debug_skip_level(state)

    assert state.level_next_treasure in (3, 4, 5)
    assert state.mazenum_current == 104
    assert state.level_start_pending


@requires_roms
def test_skip_level_neutralizes_an_in_flight_exit():
    from gauntpy.play import build_state
    from gauntpy.subsystems import exits

    state = build_state(7, Character.ELF)
    state.level_next_treasure = 2
    exits.compute_next_level(state, int(MazeObjIds.EXIT))
    expected = (state.level_next, state.maze_next, state.maze_stride)
    player = state.players[0]
    player.status = PlayerStatus.EXITING
    player.exit_pending = 1

    assert debug_skip_level(state)

    assert (
        state.levelnum_current, state.mazenum_current, state.maze_stride,
    ) == expected
    assert player.status == PlayerStatus.ALIVE_NEXT
    assert player.exit_pending == 0
    assert state.level_start_pending


def test_skip_secret_room_restores_stashed_inventory(monkeypatch):
    from gauntpy.subsystems import exits

    state = GameState(game_mode=GameMode.NORMAL)
    state.levelnum_current, state.mazenum_current = 20, 115
    state.level_next, state.maze_next = 20, 41
    state.secret_player = 1
    state.secret_trick_id = 0x54
    state.monster_spawn_probability_bonus = 3
    player = state.players[1]
    player.status = PlayerStatus.ALIVE_HERE
    player.keysnum = 2
    player.potionsnum = 1
    player.supershot = 2
    state.level_players_active = 1
    # Secret-room RAM aliases hold saved potions in player zero's key byte.
    state.secret_saved_supershot = 5
    state.players[0].keysnum = 4
    state.secret_possible_counter = 5
    monkeypatch.setattr(
        exits, "_finish_level_end",
        lambda current: setattr(current, "level_start_pending", True),
    )

    assert debug_skip_level(state)
    assert state.secret_player == -1
    assert player.status == PlayerStatus.ALIVE_NEXT
    assert (player.keysnum, player.potionsnum, player.supershot) == (5, 5, 7)
    assert (state.levelnum_current, state.mazenum_current) == (20, 41)
    assert state.secret_possible_counter == 4


def test_skip_secret_room_splash_does_not_duplicate_unstashed_inventory(
    monkeypatch,
):
    from gauntpy.subsystems import exits

    state = _active_state()
    state.levelnum_current, state.mazenum_current = 20, 115
    state.level_next, state.maze_next = 20, 41
    state.secret_player = 0
    state.secret_trick_id = 0x54
    state.level_start_pending = True
    player = state.players[0]
    player.keysnum, player.potionsnum, player.supershot = 2, 3, 4
    state.monster_spawn_probability_bonus = 7
    state.secret_saved_supershot = 9
    monkeypatch.setattr(
        exits, "_finish_level_end",
        lambda current: setattr(current, "level_start_pending", True),
    )

    assert debug_skip_level(state)

    assert state.secret_player == -1
    assert (player.keysnum, player.potionsnum, player.supershot) == (2, 3, 4)
    assert (state.levelnum_current, state.mazenum_current) == (20, 41)
