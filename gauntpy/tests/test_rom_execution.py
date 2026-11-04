"""gauntpy against the original routines, executed under Unicorn (tools/rom_exec.py)."""

from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("unicorn")

from gauntpy.game.constants import Character, GameMode, MazeObjIds, PlayerStatus  # noqa: E402
from gauntpy.game.coords import encode_vpos_at_y, native_v  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import input as gin  # noqa: E402
from gauntpy.game.subsystems import player_items  # noqa: E402
from gauntpy.game.subsystems import player_transport  # noqa: E402
from gauntpy.game.subsystems import players as gp  # noqa: E402
from gauntpy.game.subsystems.monster_shooting import monster_create_shot  # noqa: E402
from gauntpy.game.subsystems.shot_effects import shot_impact_spawn  # noqa: E402
from gauntpy.game.subsystems.player_movement import player_try_move  # noqa: E402

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "rom_exec.py"
_SPEC = importlib.util.spec_from_file_location("gauntpy_rom_exec", _TOOL)
rom_exec = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = rom_exec
_SPEC.loader.exec_module(rom_exec)

pytestmark = pytest.mark.skipif(
    not rom_exec.roms_available(), reason="original local ROM images are unavailable",
)


def _cell(row: int, col: int) -> int:
    return (row << 5) | col


def _hero(state: GameState, index: int, slot: int, **fields):
    player = state.players[index]
    player.status = PlayerStatus.ALIVE_HERE
    player.mob_slot = slot
    player.health = fields.pop("health", 500)
    for name, value in fields.items():
        setattr(player, name, value)
    state.mobs.create(
        slot, tile=0x1E0D,
        hpos=((slot & 0x1F) * 16 - 4) << 7,
        vpos=native_v((slot >> 5) * 16) << 7,
        obj_type=int(MazeObjIds.PLAYERSTART), state=index,
    )
    state.level_flags_4 |= 0x80
    return player


def _wall(state: GameState, slot: int) -> None:
    state.mobs.create(
        slot, tile=0x8000, hpos=((slot & 31) * 16) << 7,
        vpos=encode_vpos_at_y((slot >> 5) * 16),
        obj_type=int(MazeObjIds.WALL_REGULAR), link_into_chain=False,
    )


def _movable(state: GameState, slot: int, dx: int = 0) -> None:
    state.mobs.create(
        slot, tile=0x20F6, hpos=(((slot & 31) * 16 + dx) << 7) & 0xFFFF,
        vpos=encode_vpos_at_y((slot >> 5) * 16),
        obj_type=int(MazeObjIds.WALL_MOVABLE),
    )


def _step_both(state: GameState, delta: int, watch: list[int] = ()):
    """One move from the same state in the ROM and in gauntpy."""
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    result = rom_exec.player_try_move(machine, state, 0, delta)
    hero = machine.player_slot(0)
    rom = (result, hero, machine.hpos(hero) & ~0xF, machine.vpos(hero))
    rom += tuple((machine.hpos(s), machine.vpos(s)) for s in watch)
    python_result = player_try_move(state, 0, delta, 0)
    hero = state.players[0].mob_slot
    python = (python_result & 0xFFFF, hero, state.mobs.hpos[hero] & ~0xF, state.mobs.vpos[hero])
    python += tuple((state.mobs.hpos[s], state.mobs.vpos[s]) for s in watch)
    return rom, python


# --- doors ---------------------------------------------------------------------

@pytest.mark.parametrize("door_state,keys", [(10, 0), (10, 1), (5, 0), (15, 0)])
def test_walking_into_a_door_matches_the_rom(door_state, keys):
    door = _cell(4, 5)
    state = GameState()
    state.mobs.link[door] = int(MazeObjIds.DOOR_HORIZ) << 10
    state.mobs.set_state(door, door_state)
    state.mobs.picture[door] = 1
    _hero(state, 0, _cell(5, 5), keysnum=keys)
    for step in range(16):
        rom, python = _step_both(state, gin.JOY_UP)
        assert rom == python, step


# --- movable walls -------------------------------------------------------------

_PUSHES = {
    "up-free": (gin.JOY_UP, [(4, 5, 0)], []),
    "up-slide-right": (gin.JOY_UP, [(4, 5, 0)], [(3, 4), (3, 5), (3, 6)]),
    "up-slide-left": (gin.JOY_UP, [(4, 5, -6)], [(3, 3), (3, 4), (3, 5), (3, 6)]),
    "up-all-blocked": (
        gin.JOY_UP, [(4, 5, 0)],
        [(3, 4), (3, 5), (3, 6), (4, 6), (5, 6), (4, 4), (5, 4)],
    ),
    "right-free": (gin.JOY_RIGHT, [(5, 6, 0)], []),
    "right-both-blocked": (gin.JOY_RIGHT, [(5, 6, 0)], [(4, 7), (5, 7), (6, 7)]),
    "left-all-blocked": (
        gin.JOY_LEFT, [(5, 4, 0)],
        [(4, 3), (5, 3), (6, 3), (4, 4), (6, 4), (4, 5), (6, 5)],
    ),
    "down-slide": (gin.JOY_DOWN, [(6, 5, 0)], [(7, 4), (7, 5), (7, 6)]),
}


def _movable_walls(reader, slots=range(32, 1024)):
    return {s: (reader.hpos(s), reader.vpos(s)) for s in slots if reader.picture(s) == 0x20F6}


@pytest.mark.parametrize("name", _PUSHES)
def test_pushing_a_movable_wall_matches_the_rom(name):
    delta, movables, walls = _PUSHES[name]
    state = GameState()
    _hero(state, 0, _cell(5, 5))
    for row, col, dx in movables:
        _movable(state, _cell(row, col), dx)
    for row, col in walls:
        _wall(state, _cell(row, col))
    for step in range(12):
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        result = rom_exec.player_try_move(machine, state, 0, delta)
        rom_hero = machine.player_slot(0)
        rom_walls = _movable_walls(machine)
        python_result = player_try_move(state, 0, delta, 0)
        hero = state.players[0].mob_slot
        python_walls = {
            s: (state.mobs.hpos[s], state.mobs.vpos[s])
            for s in range(32, 1024) if state.mobs.picture[s] == 0x20F6
        }
        assert (result, rom_hero, machine.hpos(rom_hero) & ~0xF, machine.vpos(rom_hero)) == (
            python_result & 0xFFFF, hero, state.mobs.hpos[hero] & ~0xF, state.mobs.vpos[hero],
        ), step
        assert rom_walls == python_walls, step


# --- shoves --------------------------------------------------------------------

@pytest.mark.parametrize("obj_type,picture", [
    (MazeObjIds.KEY, 0x0AFC), (MazeObjIds.WALL_MOVABLE, 0x20F6),
])
def test_a_shove_into_an_occupied_cell_matches_the_rom(obj_type, picture):
    state = GameState()
    mover = _hero(state, 0, _cell(5, 5), character=Character.WARRIOR)
    target = _hero(state, 1, _cell(5, 6), character=Character.WIZARD)
    state.mobs.hpos[mover.mob_slot] = (83 << 7) | 0x0C
    state.mobs.hpos[target.mob_slot] = (99 << 7) | 0x0D
    occupied = _cell(5, 7)
    state.mobs.create(
        occupied, tile=picture, hpos=(7 * 16) << 7,
        vpos=native_v(5 * 16) << 7, obj_type=int(obj_type),
    )
    for step in range(3):
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        result = rom_exec.player_try_move(machine, state, 0, gin.JOY_RIGHT)
        shoved = machine.player_slot(1)
        rom = (
            result, machine.player_slot(0), shoved, machine.hpos(shoved) & ~0xF,
            machine.keys(1), machine.picture(occupied),
        )
        python_result = player_try_move(state, 0, gin.JOY_RIGHT, 0)
        python = (
            python_result & 0xFFFF, mover.mob_slot, target.mob_slot,
            state.mobs.hpos[target.mob_slot] & ~0xF, target.keysnum,
            state.mobs.picture[occupied],
        )
        assert rom == python, step


# --- key piles and death drops -------------------------------------------------

def _python_record(state: GameState, slot: int):
    mobs = state.mobs
    return (mobs.picture[slot], mobs.hpos[slot], mobs.vpos[slot], mobs.obj_type(slot), mobs.state(slot))


@pytest.mark.parametrize("keys,potions,pile", [
    (2, 1, 5), (6, 4, 3), (0, 0, 0), (3, 0, 2), (10, 1, 4),
])
def test_collecting_a_key_pile_matches_the_rom(keys, potions, pile):
    state = GameState()
    player = _hero(state, 0, _cell(9, 9), keysnum=keys, potionsnum=potions)
    state.level_players_active = 1
    slot = 92
    state.mobs.create(
        slot, tile=0x1D76, hpos=((slot << 11) - 0x1FF) & 0xFFFF,
        vpos=(((slot & 0x3E0) ^ 0x3E0) << 6) + 0x11,
        obj_type=int(MazeObjIds.KEY), state=pile,
    )
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    result = machine.call(0x511AC, slot, 0)
    assert machine.halted
    python_result = player_items.player_tile_interact(state, slot, 0)
    assert (result, machine.keys(0), machine.record(slot)) == (
        python_result & 0xFFFFFFFF, player.keysnum, _python_record(state, slot),
    )


@pytest.mark.parametrize("keys", [0, 1, 5])
def test_the_death_drop_matches_the_rom(keys):
    state = GameState(game_mode=GameMode.NORMAL)
    slot = _cell(10, 10)
    _hero(state, 0, slot, health=0, keysnum=keys, coin_count=1)
    state.mobs.hpos[slot] = (163 << 7) | 0x0C
    state.mobs.vpos[slot] = native_v(158) << 7
    state.level_players_active = 1
    state.frame_counter = 1
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x466F6)
    assert machine.halted
    gp.main_health_countdown(state)
    assert machine.record(slot) == _python_record(state, slot)


@pytest.mark.parametrize("level,maze,next_maze,survivor,bonus", [
    (1, 8, 9, False, 6),
    (5, 40, 41, False, 6),
    (6, 40, 41, False, 6),      # the rotation's resume position is recorded
    (6, 0x68, 41, False, 6),    # a treasure room gives way to the next maze first
    (9, 40, 41, True, 1),
    (9, 40, 41, True, 2),       # one hero left: the survivor's bonus falls to 1
    (9, 40, 41, True, 6),
    (9, 0x68, 41, True, 6),     # the game is not over, so nothing is recorded
])
def test_the_death_blocks_game_state_matches_the_rom(level, maze, next_maze, survivor, bonus):
    state = GameState(game_mode=GameMode.NORMAL)
    dead, live = _cell(10, 10), _cell(14, 14)
    _hero(state, 0, dead, health=0, coin_count=1)
    state.level_players_active = 1
    if survivor:
        _hero(state, 1, live, health=500, coin_count=1, bonusmult=bonus)
        state.level_players_active = 2
    state.levelnum_current, state.mazenum_current = level, maze
    state.maze_next, state.maze_number = next_maze, 5
    state.secret_player = 2
    state.attract_timer = 0xFFFF
    state.frame_counter = 1
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.w16(0x904004, level)
    machine.w16(0x904000, maze)
    machine.w16(0x904B54, next_maze)
    machine.w16(0x904010, 5)
    machine.w8(0x904063, 2)
    machine.w16(0x904B7C, 0xFFFF)
    machine.w16(0x90490E + 2, state.players[1].bonusmult)
    machine.call(0x466F6)
    assert machine.halted
    gp.main_health_countdown(state)
    assert (
        machine.r16(0x904928), machine.r16(0x904000), machine.r16(0x904010),
        machine.r8(0x904063), machine.r16(0x904B7C), machine.r16(0x90490E + 2),
        machine.r16(0x904BFC),
    ) == (
        state.level_players_active, state.mazenum_current, state.maze_number,
        state.secret_player & 0xFF, state.attract_timer, state.players[1].bonusmult,
        state.rng.seed,
    )


# --- monsters are not tiles ----------------------------------------------------

@pytest.mark.parametrize("obj_type", [MazeObjIds.MONST_ACID, MazeObjIds.MONST_IT])
def test_a_monster_is_not_a_tile(obj_type):
    """0x511DC-0x51226 send creatures to the unhandled exit at 0x51E60."""
    state = GameState(game_mode=GameMode.NORMAL)
    player = _hero(state, 0, _cell(10, 9))
    target = _cell(10, 10)
    state.mobs.create(
        target, tile=0x2300, hpos=(10 * 16) << 7,
        vpos=native_v(10 * 16) << 7, obj_type=int(obj_type),
    )
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    assert machine.call(0x511AC, target, 0) == 0
    assert machine.halted
    assert machine.r16(0x905F40) == 0
    assert player_items.player_tile_interact(state, target, 0) == 0
    assert player.invuln_timer == 0


@pytest.mark.parametrize("obj_type", [MazeObjIds.MONST_ACID, MazeObjIds.MONST_IT])
def test_a_transporting_hero_deletes_an_overlapped_monster(obj_type):
    """0x50BB8 -> 0x50C7A removes what the tile interaction leaves unhandled."""
    state = GameState(game_mode=GameMode.NORMAL)
    hero = _cell(10, 10)
    _hero(state, 0, hero)
    state.mobs.hpos[hero] |= 0x0C
    left = _cell(10, 9)
    state.mobs.create(
        left, tile=0x2300, hpos=(9 * 16) << 7,
        vpos=native_v(10 * 16) << 7, obj_type=int(obj_type),
    )
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x50BB8, 0x4083A, hero, 0)
    assert machine.halted
    assert machine.picture(left) == 0
    player_transport.scan_move_path_interactions(state, hero, 0)
    assert state.mobs.picture[left] == 0


# --- firing -------------------------------------------------------------------

@pytest.mark.parametrize("frame", [0, 3, 6])
@pytest.mark.parametrize("direction", range(8))
def test_firing_sets_the_shooters_state_word_like_the_rom(direction, frame):
    """0x490DC takes the ROM compass; gauntpy's state field holds its own, two steps round."""
    state = GameState(game_mode=GameMode.NORMAL)
    slot = _cell(10, 10)
    state.mobs.create(
        slot, tile=0x18C6, hpos=((10 * 16) << 7) | 0x08,
        vpos=native_v(10 * 16) << 7, obj_type=int(MazeObjIds.MONST_DEMON),
        state=(frame << 3) | 1,
    )
    rom_direction = (direction + 2) & 7
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x490DC, slot, rom_direction, 5)
    assert machine.halted
    monster_create_shot(state, slot, direction, 5)
    assert machine.record(slot)[4] == rom_direction
    assert state.mobs.state(slot) == direction
    assert machine.hpos(slot) == state.mobs.hpos[slot]
    assert machine.record(5)[:3] == _python_record(state, 5)[:3]


# --- impact effects ------------------------------------------------------------

@pytest.mark.parametrize("target,shooter,hpos,flags", [
    (9, 8, 0x8C81, 0),          # a rock landing: the key's column comes from the raw H word
    (9, 8, 0x8C88, 0),          # the same path at its limit
    (9, 8, 0x8C90, 0),          # the 0x200 path, which has pixels by then
    (3, 2, 0x4601, 0),
    (11, 10, 0x1F81, 0),
    (0x352, 8, 0x8C81, 0),      # an ordinary MOB is its own key
    (0x352, 8, 0x8C90, 0),
    (0x340, 8, 0x8C81, 0),      # column zero uses the shot's position...
    (0x340, 8, 0x8C81, 0x20),   # ...unless the level wraps
    (0x400 + 0x145, 0, 0x8C81, 0),
    (0x400 + 0x05, 0, 0x8C81, 0),
])
def test_an_impact_takes_the_roms_position_and_depth_key(target, shooter, hpos, flags):
    state = GameState(game_mode=GameMode.NORMAL)
    state.level_flags_4 = flags
    mobs = state.mobs
    # Live records for the shot and, where it is one, the target.
    for slot in {shooter + 1, target} - {t for t in (target,) if t >= 0x400}:
        mobs.picture[slot] = 0x1C5C
        mobs.hpos[slot] = hpos
        mobs.vpos[slot] = 0x3809
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x47DAE, target, shooter)
    assert machine.halted
    shot_impact_spawn(state, target, shooter)
    assert machine.record(0x0D)[:3] == _python_record(state, 0x0D)[:3]
    assert machine.r16(0x904940 + 2 * 0x0D) == state.mobs.depth_key[0x0D]


# --- crash reports --------------------------------------------------------------

def test_starting_unicorn_is_quiet_and_a_real_crash_is_not(tmp_path):
    """conftest.py hides Unicorn's start-up fault from faulthandler, and only that."""
    (tmp_path / "test_crash.py").write_text(
        "import faulthandler\n"
        "import rom_exec\n"
        "def test_crash():\n"
        "    rom_exec.RomMachine()\n"
        "    rom_exec.RomMachine()\n"
        "    faulthandler._read_null()\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "conftest", "-p", "no:cacheprovider",
         "--rootdir", str(tmp_path), str(tmp_path / "test_crash.py")],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(
            str(root / name) for name in ("tests", "tools", "src"))},
    )
    assert run.returncode != 0
    assert run.stderr.count("Current thread") == 1, run.stderr
    assert "test_crash.py" in run.stderr
