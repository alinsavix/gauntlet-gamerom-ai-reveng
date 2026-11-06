"""A thief walking real levels in step with the ROM (tools/thief_walk.py).

Each case runs the thief from arrival through theft to getaway, frame by frame on both
sides, and fails at the first frame where its RAM, record, route grid, the victim or the
RNG seed differ. The full sweep is ``python tools/thief_walk.py``; these are a sample of it.
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
thief_walk = _load("thief_walk")

pytestmark = pytest.mark.skipif(
    not rom_exec.roms_available() or not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file(),
    reason="original local ROM images or Slapstic ROMs are unavailable",
)


@pytest.mark.parametrize("scenario,maze,start,length,mugger", [
    ("plain", 6, 0x84, 14, False),
    ("plain", 84, 0x1D6, 30, True),
    ("monster", 13, 0x1D6, 14, False),
    ("monster", 43, 0x330, 30, True),
    ("shot", 6, 0x84, 6, False),        # the dodge squeezes the thief through (0x4E8AC)
    ("shot", 101, 0x2A8, 14, False),
    ("moving", 7, 0x1D6, 14, False),
    ("moving", 87, 0x2A8, 6, True),
])
def test_a_thief_walks_in_step_with_the_rom(scenario, maze, start, length, mugger):
    made = thief_walk.setup(maze, start, length, mugger, scenario)
    assert made is not None
    state, onward = made
    frames, differences, end = thief_walk.walk(state, onward, scenario)
    assert differences == [], f"frame {frames}"
    assert end in ("left", "left after a transport", "time")
