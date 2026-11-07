"""A dragon living through real levels in step with the ROM (tools/dragon_walk.py).

Each case wakes the dragon, keeps a hero moving around it, and, in ``hits``, shoots it to
death; it fails at the first frame where a dragon word, its segment records, its fireballs,
its loot or the RNG seed differ. The full sweep is ``python tools/dragon_walk.py``.
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
dragon_walk = _load("dragon_walk")

pytestmark = pytest.mark.skipif(
    not rom_exec.roms_available() or not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file(),
    reason="original local ROM images or Slapstic ROMs are unavailable",
)


@pytest.mark.parametrize("scenario,maze,seed", [
    ("wake", 41, 0x0F0F),       # a turn reads the path table with a negative counter
    ("leave", 13, 0x1234),
    ("stun", 67, 0xBEEF),
    ("hits", 13, 0x1234),
    ("hits", 78, 0x0F0F),
])
def test_a_dragon_lives_and_dies_in_step_with_the_rom(scenario, maze, seed):
    state = dragon_walk.setup(maze)
    assert state is not None
    state.rng.seed = seed
    frames, differences, end = dragon_walk.walk(state, scenario)
    assert differences == [], f"frame {frames}"
    if scenario == "hits":
        assert end.startswith("killed")


@pytest.mark.parametrize("anim_ctr", [0, 0x20, -0x10])
def test_a_sleeping_dragon_keeps_its_cooldown_like_the_rom(anim_ctr):
    """0x54472-0x5447E return before the cooldown count while the dragon sleeps."""
    import copy

    from gauntpy.game.subsystems import dragon

    state = dragon_walk.setup(13)
    state.dragon_state = 0x01
    state.dragon_anim_ctr = anim_ctr
    state.dragon_fire_cooldown = 5
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x54454, count=2_000_000)
    assert machine.halted
    dragon.main_handle_dragon(state)
    assert machine.r16(0x90487C) == state.dragon_fire_cooldown
    assert machine.r16(0x904892) == state.dragon_anim_ctr & 0xFFFF
    head = state.dragon_seg_mob_ids[0]
    assert machine.picture(head) == state.mobs.picture[head]
