"""gauntpy against the original routines, executed under Unicorn (tools/rom_exec.py)."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys

import pytest

pytest.importorskip("unicorn")

from gauntpy.game.constants import Character, GameMode, MazeObjIds, PlayerStatus  # noqa: E402
from gauntpy.game.coords import encode_vpos_at_y, native_v  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import input as gin  # noqa: E402
from gauntpy.game.subsystems import player_items  # noqa: E402
from gauntpy.game.subsystems import players as gp  # noqa: E402
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
    """main_health_countdown writes the drop before later code this snapshot
    cannot run (it faults at 0x40632), so only the record is compared."""
    state = GameState(game_mode=GameMode.NORMAL)
    slot = _cell(10, 10)
    _hero(state, 0, slot, health=0, keysnum=keys)
    state.mobs.hpos[slot] = (163 << 7) | 0x0C
    state.mobs.vpos[slot] = native_v(158) << 7
    state.level_players_active = 1
    state.frame_counter = 1
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x466F6)
    gp.main_move_players(state)
    assert machine.record(slot) == _python_record(state, slot)
