"""A short flight of ``tools/game_run.py``: the ROM and the port, in step from a cold boot."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from gex.roms import SLAPSTIC_ROMS, _rom_dir

_TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    sys.path.insert(0, str(_TOOLS))
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rom_exec = _load("rom_exec")
game_run = _load("game_run")

pytestmark = pytest.mark.skipif(
    not (rom_exec.roms_available() and (_rom_dir() / SLAPSTIC_ROMS[0]).is_file()),
    reason="ROM files not available",
)


def test_attract_stays_in_step():
    frame, found = game_run.run(600, False, 1)
    assert not found, f"frame {frame}: {found[:4]}"


def test_a_two_hero_game_stays_in_step():
    frame, found = game_run.run(1500, False, 5, heroes=2)
    assert not found, f"frame {frame}: {found[:4]}"


def test_the_word_past_the_supershot_table_holds_the_scroll():
    lockstep = game_run.Lockstep(1)
    try:
        for _ in range(120):
            lockstep.step((game_run._IDLE,) * 4)
        assert lockstep.machine.r16(0x905F6E) == lockstep.state.vblank_scroll_word
    finally:
        lockstep.close()
