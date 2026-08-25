"""Host troubleshooting shortcuts preserve coherent game-side state."""

from __future__ import annotations

import pytest

from gauntpy.constants import Character, GameMode, PlayerStatus
from gauntpy.render.debug_controls import (
    debug_add_key,
    debug_add_potion,
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


@requires_roms
def test_skip_level_uses_rotation_and_preserves_inventory():
    from gauntpy.play import build_state

    state = build_state(1, Character.ELF, keys=2, potions=3)

    assert debug_skip_level(state)

    assert (state.levelnum_current, state.mazenum_current) == (2, 1)
    assert state.players[0].status == int(PlayerStatus.ALIVE_HERE)
    assert state.players[0].keysnum == 2
    assert state.players[0].potionsnum == 3
    assert state.players[0].mob_slot
    assert state.bonus_timer == 0
    assert not state.level_start_pending


def test_skip_level_rejects_non_gameplay_modes():
    state = _active_state()
    state.game_mode = GameMode.TITLE

    assert not debug_skip_level(state)
