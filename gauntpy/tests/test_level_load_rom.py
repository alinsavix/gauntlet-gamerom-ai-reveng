"""A whole level load against the ROM, with its Slapstic in front of the maze data.

A sample of ``tools/level_load_check.py``, chosen so each maze here once differed. The full
sweep is ``python tools/level_load_check.py``.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

from gex.roms import SLAPSTIC_ROMS, _rom_dir  # noqa: E402

from gauntpy.game.constants import GameMode, MazeObjIds  # noqa: E402
from gauntpy.game.playfield import pf_replace  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems.shot_damage import _handle_wall  # noqa: E402

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
level_load_check = _load("level_load_check")
name_entry_check = _load("name_entry_check")
rom_sweeps = _load("rom_sweeps")

pytestmark = pytest.mark.skipif(
    not (rom_exec.roms_available() and (_rom_dir() / SLAPSTIC_ROMS[0]).is_file()),
    reason="original local ROM images are unavailable",
)


@pytest.mark.parametrize(
    ("maze", "level", "seed", "task"),
    [
        pytest.param(5, 7, 0x1234, 0, id="floor-art-after-the-start-draw"),
        pytest.param(5, 6, 0x1234, 0, id="level-six-countdown-after-the-mirror-draw"),
        pytest.param(7, 7, 0x1234, 0, id="food-covered-by-a-wall-run-spends-its-draw"),
        pytest.param(65, 7, 1, 0, id="food-covered-by-a-wall-run-with-no-mirror"),
        pytest.param(52, 7, 0x1234, 0, id="more-exits-than-the-exit-table-holds"),
        pytest.param(13, 7, 0x1234, 0, id="pattern-11-walls-beside-destructibles"),
        pytest.param(79, 7, 0x1234, 0, id="pattern-6-floors-beside-destructibles"),
        pytest.param(6, 150, 0x1234, 0, id="dragon-has-no-head-pose-yet"),
        pytest.param(115, 7, 0x1234, 0x5C, id="secret-room-replacements-draw-no-floor"),
        pytest.param(116, 7, 1, 0x51, id="last-maze-and-its-missing-delimiter"),
    ],
)
def test_a_level_loads_as_the_rom_loads_it(maze, level, seed, task):
    error, found = level_load_check.check(maze, level, seed, task)
    assert not error
    assert not found, {kind: rows[:3] for kind, rows in found.items()}


@pytest.mark.parametrize(
    ("maze", "level", "seed", "next_treasure"),
    [
        pytest.param(5, 2, 0x1234, 3, id="mirror-draw-before-the-splash-draws"),
        pytest.param(5, 6, 0x1234, 3, id="level-six-after-the-splash-too"),
        pytest.param(40, 12, 1, 3, id="an-ordinary-late-level"),
        pytest.param(40, 12, 0xBFE6, 0, id="a-treasure-room-replaces-the-level"),
    ],
)
def test_the_start_screen_and_load_draw_in_the_roms_order(maze, level, seed, next_treasure):
    error, found = level_load_check.check_start_screen(maze, level, seed, next_treasure)
    assert not error
    assert not found, {kind: rows[:3] for kind, rows in found.items()}


@pytest.mark.parametrize(
    ("maze", "level", "characters", "settings", "bonus"),
    [
        pytest.param(5, 8, (0,), 0, 0, id="warrior"),
        pytest.param(30, 13, (2,), 0xC0, 3, id="wizard-hard-with-a-bonus"),
        pytest.param(60, 30, (3,), 0xC0, 0xFE, id="elf-hard-with-a-negative-bonus"),
        pytest.param(90, 61, (0, 1, 2, 3), 0x40, 3, id="full-party"),
    ],
)
def test_the_party_pickups_and_thief_land_as_the_rom_places_them(
    maze, level, characters, settings, bonus,
):
    error, found = level_load_check.check_party(maze, level, 0x1234, characters, settings, bonus)
    assert not error
    assert not found, {kind: rows[:3] for kind, rows in found.items()}


@pytest.mark.parametrize(
    ("maze", "level", "pricing", "timer"),
    [
        pytest.param(5, 8, 1, 0x5DD, id="continue-restores-the-level"),
        pytest.param(30, 13, 1, 0x5DD, id="continue-on-a-thief-level"),
        pytest.param(5, 8, 0, 0x5DD, id="continue-on-free-play"),
        pytest.param(39, 8, 0, 0xFFFF, id="free-play-with-its-pickups"),
    ],
)
def test_the_first_hero_reloads_the_level_as_the_rom_does(maze, level, pricing, timer):
    error, found = level_load_check.check_first_hero(maze, level, 0x1234, pricing, timer)
    assert not error
    assert not found, {kind: rows[:3] for kind, rows in found.items()}


@pytest.mark.parametrize("character", range(4))
def test_a_paid_new_game_starts_as_the_rom_starts_it(character):
    error, found = level_load_check.check_new_game(0x1234, character)
    assert not error
    assert not found, {kind: rows[:3] for kind, rows in found.items()}


def test_highscore_check_is_the_roms():
    assert not name_entry_check.highscore_cases(random.Random(21), count=150)


def test_the_initials_editor_is_the_roms_to_its_end():
    differences, finished = name_entry_check.editor_cases(random.Random(21), count=4)
    assert not differences
    assert finished == 4


@pytest.mark.parametrize(
    ("mode", "page"),
    [
        pytest.param(GameMode.TITLE, 2, id="title"),
        pytest.param(GameMode.SCORES, 2, id="high-scores"),
        pytest.param(GameMode.DEMO, 2, id="demo"),
        pytest.param(GameMode.LEGEND, 2, id="legend-rules"),
        pytest.param(GameMode.LEGEND, 1, id="legend-monsters"),
        pytest.param(GameMode.LEGEND, 0, id="legend-credits"),
    ],
)
def test_an_attract_screen_is_the_roms(mode, page):
    assert not level_load_check.check_attract_screen(int(mode), 0x1234, page)


def test_an_exit_is_the_roms_across_tricks_and_parties():
    assert rom_sweeps.exits(count=40) == 0


def test_transporter_routes_are_the_roms():
    assert rom_sweeps.routes(count=300) == 0


def test_the_info_panel_is_the_roms_for_any_party():
    rng = random.Random(1)
    for _ in range(200):
        assert not level_load_check.check_panel(rng)


def _loaded(maze: int, level: int = 7, seed: int = 0x1234):
    machine = level_load_check.rom_load(level_load_check.new_state(level, seed), maze)
    state = level_load_check.new_state(level, seed)
    assert level_load_check.python_load(state, maze)
    return machine, state


def _first_slot(state: GameState, wanted) -> int:
    return next(slot for slot in range(64, 1024) if wanted(slot))


@pytest.mark.parametrize(
    "kind",
    ["sprite", "wall-marker", "empty"],
)
def test_clearing_a_cell_redraws_only_a_marker(kind):
    machine, state = _loaded(5)
    mobs = state.mobs
    slot = _first_slot(state, {
        "sprite": lambda s: mobs.picture[s] and not mobs.picture[s] & 0x8000,
        "wall-marker": lambda s: mobs.picture[s] == 0x8000,
        "empty": lambda s: not mobs.picture[s],
    }[kind])
    machine.call(0x5F31E, slot, 0, count=2_000_000)
    assert machine.halted, machine.fault_pc
    pf_replace(state, slot, int(MazeObjIds.TILE_FLOOR))
    found = level_load_check.differences(machine, state)
    assert not found, {name: rows[:3] for name, rows in found.items()}


def test_a_dissolving_movable_wall_leaves_the_floor_and_the_seed_alone():
    """0x4B484-0x4B490: an impact effect and the record's removal, and no floor draw."""
    state = GameState()
    state.movable_wall_hits = {}
    slot = (9 << 5) | 9
    state.mobs.create(slot, 0x20F6, 9 * 16 << 7, 0, int(MazeObjIds.WALL_MOVABLE), 0)
    state.mobs.state_link[slot] = 0x6000
    before = list(state.playfield_ram)
    seed = state.rng.seed
    _handle_wall(state, slot, slot, 0, int(MazeObjIds.WALL_MOVABLE))
    assert state.mobs.picture[slot] == 0
    assert state.rng.seed == seed
    assert state.playfield_ram == before
