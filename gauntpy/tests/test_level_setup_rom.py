"""Level setup and secret-room bookkeeping against the ROM (tools/forcefield_check.py, tools/secret_check.py).

Each case loads a real maze and, at the moment level setup calls them, runs
``forcefield_segments_setup`` (0x53398) and ``maze_forcefield_setup`` (0x52F26) in the ROM on
the same state, comparing the segment table, the cycle codes, the level flags and every record.
The full sweep is ``python tools/forcefield_check.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

pytest.importorskip("unicorn")

from gex.roms import SLAPSTIC_ROMS, _rom_dir  # noqa: E402

_TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rom_exec = _load("rom_exec")
forcefield_check = _load("forcefield_check")

pytestmark = pytest.mark.skipif(
    not rom_exec.roms_available() or not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file(),
    reason="original local ROM images or Slapstic ROMs are unavailable",
)


@pytest.mark.parametrize("maze", [
    64,     # a beam that wraps across the row, in a level that does not wrap
    1, 13, 83, 91, 102,
    4, 20, 112,         # cycling walls
])
def test_level_setup_builds_the_roms_forcefields(maze):
    assert forcefield_check.check(maze, 7) == []


secret_check = _load("secret_check")


def test_the_name_entry_ring_matches_the_rom():
    assert secret_check.step_char_cases() == []


def test_secret_room_pacing_matches_the_rom():
    assert secret_check.secret_check_cases() == []


def test_secret_room_completion_matches_the_rom():
    """Signed progress bytes, no winner check, and the clear-the-monsters sweep (0x4D1A4)."""
    assert secret_check.check_winner_cases(
        tasks=range(0x50, 0x5E), winners=(-1, 2), progresses=(0, 2, 3, 6, 0x13, 0x3E, 0xFF),
    ) == []


def test_leaving_attract_retires_an_open_box():
    """0x44220-0x44232 and 0x44438-0x44448: a demo tip would otherwise hold play still."""
    from gauntpy.game.constants import GameMode
    from gauntpy.game.state import GameState
    from gauntpy.game.subsystems.attract import start_attract_screen
    from gauntpy.game.subsystems.score import demo_message_show
    from gauntpy.game.subsystems.session import start_attract_to_game

    for leave in (lambda s: start_attract_to_game(s), lambda s: start_attract_screen(s, int(GameMode.DEMO))):
        state = GameState(game_mode=GameMode.DEMO)
        demo_message_show(state, -1, 0)
        assert state.dialog_timer
        leave(state)
        assert state.dialog_timer == 0
        assert state.dialog_message == []


def test_the_secret_code_matches_the_rom():
    assert secret_check.secret_code_cases(count=600) == []


def test_the_secret_winners_name_entry_matches_the_rom_frame_by_frame():
    """Stepping, commits, the timeout and the code page (0x54EC6, 0x54FE8)."""
    assert secret_check.name_entry_cases(winners=(1,)) == []
    assert secret_check.name_entry_cases.finishes == 1
