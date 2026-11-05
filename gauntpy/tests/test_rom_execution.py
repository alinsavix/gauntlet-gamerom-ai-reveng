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
from gex.roms import SLAPSTIC_ROMS, _rom_dir  # noqa: E402
from gauntpy.game.maze import maze_place_object, reset_and_load_level  # noqa: E402
from gauntpy.game.subsystems.camera import scroll_to_slot  # noqa: E402
from gauntpy.game.subsystems import player_items  # noqa: E402
from gauntpy.game.subsystems import player_movement  # noqa: E402
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


# --- hand contact: mob_collision_test (0x52192) ---------------------------------

_HERO, _TARGET = _cell(10, 9), _cell(10, 10)
_MONSTERS = range(int(MazeObjIds.MONST_GHOST), int(MazeObjIds.MONST_IT) + 1)


def _rom_compass(word: int) -> int:
    return (word & 0x38) | (((word & 7) + 2) & 7)


def _contact_state(obj_type, *, fighting=False, movement_type=1, seed=0x1234, keys=0, low=None):
    state = GameState(game_mode=GameMode.NORMAL)
    state.rng.seed = seed
    player = _hero(state, 0, _HERO, keysnum=keys, coin_count=1)
    state.mobs.hpos[_HERO] |= 0x0C
    state.level_players_active = 1
    state.level_flags_4 |= 0x80
    maze_place_object(state, _TARGET, int(obj_type), 1)
    if not state.mobs.picture[_TARGET]:
        state.mobs.create(
            _TARGET, tile=0x2000, hpos=((10 * 16) << 7) | 0x0B,
            vpos=native_v(10 * 16) << 7, obj_type=int(obj_type),
        )
    if low is not None:
        state.mobs.hpos[_TARGET] = (state.mobs.hpos[_TARGET] & ~0x3F) | low
    state.idle_timer, state.escape_timer = 77, 88
    state.movement_type = movement_type
    player.anim_counter = 99
    if fighting:
        state.player_fighting_dir[0] = player.direction + 1
    return state


def _rom_for_contact(state):
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    if state.mobs.obj_type(_TARGET) in _MONSTERS:
        word = state.mobs.state_link[_TARGET]
        machine.w16(rom_exec._STATE + 2 * _TARGET,
                    (word & 0x3FF) | (_rom_compass(word >> 10) << 10))
    return machine, machine.count_calls(0x549EA)


def _compare_contact(state, monkeypatch, rom_slot=_TARGET):
    from gauntpy.game.subsystems import shot_damage

    machine, rom_dragon = _rom_for_contact(state)
    result = machine.call(0x52192, rom_slot, 0)
    assert machine.halted
    real = shot_damage.dragon_player_proximity
    our_dragon = []
    monkeypatch.setattr(
        shot_damage, "dragon_player_proximity",
        lambda *args, **kwargs: (our_dragon.append(args), real(*args, **kwargs)),
    )
    ours = player_movement._player_fight_collision(state, 0, rom_slot)
    mobs = state.mobs
    assert (
        result & 0xFFFF == 0xFFFF, bool(machine.r16(0x904A0E)),
        machine.r16(0x90490C), machine.r16(0x9048C6), machine.r16(0x904BFC),
        bool(machine.r16(0x9049AC)), machine.r16(0x9049BC), rom_dragon[0],
        machine.picture(rom_slot), machine.hpos(rom_slot),
        machine.r16(0x903800 + 2 * rom_slot) >> 10,
    ) == (
        ours == -1, ours == 1,
        state.idle_timer & 0xFFFF, state.escape_timer & 0xFFFF, state.rng.seed & 0xFFFF,
        bool(state.player_fighting_dir[0]), state.players[0].anim_counter, len(our_dragon),
        mobs.picture[rom_slot], mobs.hpos[rom_slot],
        mobs.obj_type(rom_slot),
    )
    return machine


_CONTACTS = [
    (int(MazeObjIds.GEN_GHOST1), None), (int(MazeObjIds.GEN_GHOST2), None),
    (int(MazeObjIds.GEN_GHOST3), None), (int(MazeObjIds.GEN_SORC1), None),
    (int(MazeObjIds.MONST_GRUNT), None), (int(MazeObjIds.MONST_DEMON), None),
    (int(MazeObjIds.MONST_LOBBER), None), (int(MazeObjIds.MONST_AUX_GRUNT), None),
    (int(MazeObjIds.MONST_SORC), 0x0B), (int(MazeObjIds.MONST_SORC), 0x1B),
    (int(MazeObjIds.MONST_GHOST), None), (int(MazeObjIds.MONST_ACID), None),
    (int(MazeObjIds.MONST_IT), None), (int(MazeObjIds.MONST_DEATH), None),
    (int(MazeObjIds.MONST_SUPERSORC), 0x0B), (int(MazeObjIds.MONST_SUPERSORC), 0x2B),
    (int(MazeObjIds.MONST_DRAGON), None), (int(MazeObjIds.WALL_REGULAR), None),
]


@pytest.mark.parametrize("seed", [0, 0x1234, 0xBEEF])
@pytest.mark.parametrize("movement_type", [1, 0])
@pytest.mark.parametrize("fighting", [False, True])
@pytest.mark.parametrize("obj_type,low", _CONTACTS)
def test_hand_contact_matches_the_rom(obj_type, low, fighting, movement_type, seed, monkeypatch):
    """Result, fight latch, timers, RNG, dragon calls and the record, for every arm."""
    state = _contact_state(
        obj_type, fighting=fighting, movement_type=movement_type, seed=seed, low=low,
    )
    machine = _compare_contact(state, monkeypatch)
    if state.mobs.picture[_TARGET] and obj_type in _MONSTERS:
        assert machine.r16(rom_exec._STATE + 2 * _TARGET) >> 10 == _rom_compass(
            state.mobs.state(_TARGET)
        )


def test_a_killed_generator_draws_nothing_for_its_floor(monkeypatch):
    """A real level has neighbours to restamp, and the ROM leaves the floor alone."""
    state = _contact_state(MazeObjIds.GEN_GHOST1, fighting=True, seed=0)
    state.playfield_floor_catalog = {(0, 0): (0, 0, 0, 0)}
    _compare_contact(state, monkeypatch)


def test_locked_treasure_counts_as_activity(monkeypatch):
    state = _contact_state(MazeObjIds.TREASURE_LOCKED, keys=3)
    machine = _compare_contact(state, monkeypatch)
    assert machine.keys(0) == state.players[0].keysnum == 2
    assert (state.idle_timer, state.escape_timer) == (0, 0)


def _rom_and_ours_touch_super_sorcerer(toucher):
    """Two heroes; only the toucher's rear is clear, or nobody's when walled in."""
    state = GameState(game_mode=GameMode.NORMAL)
    first, second = _cell(10, 9), _cell(20, 20)
    _hero(state, 0, first, coin_count=1)
    _hero(state, 1, second, coin_count=1)
    state.players[1].direction = 0
    state.mobs.hpos[first] |= 0x0C
    state.mobs.hpos[second] |= 0x0D
    state.level_players_active = 2
    state.level_flags_4 |= 0x80
    target = _cell(10, 10) if toucher == 0 else _cell(20, 21)
    state.mobs.create(
        target, tile=0x2000, hpos=((target & 31) * 16 << 7) | 0x0B,
        vpos=native_v((target >> 5) * 16) << 7,
        obj_type=int(MazeObjIds.MONST_SUPERSORC),
    )
    state.movement_type = 1
    return state, target


@pytest.mark.parametrize("toucher", [0, 1])
def test_touching_a_super_sorcerer_sends_it_behind_that_hero(toucher):
    """0x5FDB8 passes the toucher to 0x5FDE0; only its own blink draws a random start."""
    state, target = _rom_and_ours_touch_super_sorcerer(toucher)
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    result = machine.call(0x52192, target, toucher)
    assert machine.halted
    assert player_movement._player_fight_collision(state, toucher, target) == -1
    assert result & 0xFFFF == 0xFFFF
    assert machine.r16(0x904BFC) == state.rng.seed == 0
    rom_home = [s for s in range(32, 1024)
                if machine.r16(0x903800 + 2 * s) >> 10 == int(MazeObjIds.MONST_SUPERSORC)]
    our_home = [s for s in range(32, 1024)
                if state.mobs.obj_type(s) == int(MazeObjIds.MONST_SUPERSORC)]
    assert rom_home == our_home and rom_home != [target]
    home = rom_home[0]
    assert machine.record(home)[:4] == _python_record(state, home)[:4]
    assert machine.r16(rom_exec._STATE + 2 * home) >> 10 == _rom_compass(state.mobs.state(home))


def test_a_super_sorcerer_with_nowhere_to_go_faces_the_hero_who_touched_it():
    state, target = _rom_and_ours_touch_super_sorcerer(0)
    for row in range(1, 32):
        for col in range(32):
            slot = _cell(row, col)
            if slot not in (_cell(10, 9), target, _cell(20, 20)):
                _wall(state, slot)
    state.idle_timer, state.escape_timer = 77, 88
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    result = machine.call(0x52192, target, 0)
    assert machine.halted
    assert player_movement._player_fight_collision(state, 0, target) == 0
    assert result == 0
    assert machine.picture(target) == state.mobs.picture[target]
    assert machine.r16(rom_exec._STATE + 2 * target) >> 10 == _rom_compass(state.mobs.state(target))
    assert (machine.r16(0x90490C), machine.r16(0x9048C6)) == (0, 0)
    assert (state.idle_timer, state.escape_timer) == (0, 0)


@pytest.mark.parametrize("item", [
    MazeObjIds.KEY, MazeObjIds.TREASURE, MazeObjIds.POT_DESTRUCTABLE,
])
def test_killing_the_thief_by_hand_matches_the_rom(item):
    """0x5227A has no thief test of its own; a real thief carries loot and has a slot."""
    state = GameState(game_mode=GameMode.NORMAL)
    state.rng.seed = 0x1234
    player = _hero(state, 0, _HERO, coin_count=1)
    state.mobs.hpos[_HERO] |= 0x0C
    state.level_players_active = 1
    state.level_flags_4 |= 0x80
    state.mobs.create(
        _TARGET, tile=0x2000, hpos=(10 * 16) << 7, vpos=native_v(10 * 16) << 7,
        obj_type=int(MazeObjIds.PLAYERSTART),
    )
    state.thief_mob_slot = state.thief_current_pos = _TARGET
    state.thief_item_carried = int(item)
    state.thief_victim = 0
    state.idle_timer, state.escape_timer = 77, 88
    state.movement_type = 1
    state.player_fighting_dir[0] = player.direction + 1
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.cpu.mem_write(0x904BB4, int(item).to_bytes(4, "big"))
    machine.w16(0x904BA4, _TARGET)
    machine.w16(0x904B9A, 0)
    result = machine.call(0x52192, _TARGET, 0)
    assert machine.halted and result & 0xFFFF == 0xFFFF
    assert player_movement._player_fight_collision(state, 0, _TARGET) == -1
    assert machine.record(_TARGET) == _python_record(state, _TARGET)
    assert machine.r16(0x904BFC) == state.rng.seed
    assert (machine.r16(0x90490C), machine.r16(0x9048C6)) == (0, 0)
    assert (state.idle_timer, state.escape_timer) == (0, 0)


# --- taking a tile: player_tile_interact (0x511AC) ------------------------------

_TAKEN = [
    (MazeObjIds.TREASURE, None), (MazeObjIds.TREASURE_BAG, None), (MazeObjIds.KEY, None),
    (MazeObjIds.FOOD_DESTRUCTABLE, None), (MazeObjIds.FOOD_DESTRUCTABLE, 0x25ED),
    (MazeObjIds.FOOD_INVULN, None), (MazeObjIds.POT_DESTRUCTABLE, None),
    (MazeObjIds.POT_DESTRUCTABLE, 0x20FC), (MazeObjIds.POT_INVULN, None),
    (MazeObjIds.POWER_INVIS, None), (MazeObjIds.POWER_INVULN, None),
    (MazeObjIds.DOOR_HORIZ, None), (MazeObjIds.DOOR_VERT, None),
]


@pytest.mark.parametrize("keys,potions", [(0, 0), (6, 6), (12, 0)])
@pytest.mark.parametrize("obj_type,picture", _TAKEN)
def test_taking_a_tile_matches_the_rom(obj_type, picture, keys, potions, monkeypatch):
    """The tail at 0x51E36-0x51E6A: hero proximity, idle timer, then the record."""
    from gauntpy.game.subsystems import shot_damage

    state = _contact_state(obj_type, keys=keys)
    state.players[0].potionsnum = potions
    if picture is not None:
        state.mobs.picture[_TARGET] = picture
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    rom_dragon = machine.count_calls(0x549EA)
    result = machine.call(0x511AC, _TARGET, 0)
    assert machine.halted
    real = shot_damage.dragon_player_proximity
    our_dragon = []
    monkeypatch.setattr(
        shot_damage, "dragon_player_proximity",
        lambda *args, **kwargs: (our_dragon.append(args), real(*args, **kwargs)),
    )
    ours = player_items.player_tile_interact(state, _TARGET, 0)
    assert (
        result & 0xFFFF == 0xFFFF, machine.r16(0x90490C), machine.r16(0x9048C6),
        rom_dragon[0], machine.picture(_TARGET), machine.keys(0),
    ) == (
        ours == -1, state.idle_timer & 0xFFFF, state.escape_timer & 0xFFFF,
        len(our_dragon), state.mobs.picture[_TARGET], state.players[0].keysnum,
    )


def test_the_games_counter_matches_the_rom():
    """0x46A4C-0x46A9E: one more game, and past 2000 a score reset is requested."""
    for before in (5, 1999, 2000):
        state = GameState(game_mode=GameMode.NORMAL)
        _hero(state, 0, _HERO, health=0, coin_count=1)
        state.level_players_active = 1
        state.frame_counter = 1
        state.game_settings = 0x6090
        state.games_played_counter = before
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        machine.cpu.mem_write(0x904012, state.eeprom_write_timer.to_bytes(4, "big"))
        machine.call(0x466F6)
        assert machine.halted
        gp.main_health_countdown(state)
        assert (
            machine.r16(0x904B86), machine.r16(0x904A24),
            int.from_bytes(bytes(machine.cpu.mem_read(0x904012, 4)), "big"),
        ) == (state.games_played_counter, state.game_settings, state.eeprom_write_timer)


# --- real levels ---------------------------------------------------------------

requires_mazes = pytest.mark.skipif(
    not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file(), reason="Slapstic ROMs not available",
)


def _real_level(maze, hero_slot=None, avoid=()):
    state = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(state, 7, maze_number=maze)
    hero = hero_slot or next(
        s for s in range(33, 1023) if s not in avoid and not state.mobs.picture[s]
    )
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.mob_slot = hero
    player.health, player.coin_count = 500, 1
    state.level_players_active = 1
    state.mobs.create(
        hero, tile=0x1E0D, hpos=(((hero & 0x1F) * 16 - 4) << 7) | 0x0C,
        vpos=native_v((hero >> 5) * 16) << 7, obj_type=int(MazeObjIds.PLAYERSTART), state=0,
    )
    state.player_tile_or_tport_dest[0] = hero
    state.rng.seed = 0x1234
    return state


@requires_mazes
@pytest.mark.parametrize("maze,trigger", [
    (6, MazeObjIds.TILE_TRAP1), (6, MazeObjIds.TILE_TRAP2), (7, MazeObjIds.TILE_TRAP1),
    (15, MazeObjIds.TILE_TRAP1), (29, MazeObjIds.TILE_TRAP1), (43, MazeObjIds.TILE_TRAP1),
    (43, MazeObjIds.TILE_TRAP3), (76, MazeObjIds.TILE_TRAP3), (84, MazeObjIds.TILE_TRAP1),
    (87, MazeObjIds.TILE_TRAP1), (101, MazeObjIds.TILE_TRAP1), (13, MazeObjIds.TILE_STUN),
])
def test_a_floor_trigger_in_a_real_level_matches_the_rom(maze, trigger):
    """Every floor and wall draw spends the same random numbers, and doors follow."""
    probe = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(probe, 7, maze_number=maze)
    slot = next(s for s in range(32, 1024)
                if probe.mobs.obj_type(s) == int(trigger) and probe.mobs.picture[s])
    state = _real_level(maze, avoid=(slot,))
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.call(0x511AC, slot, 0)
    assert machine.halted
    player_items.player_tile_interact(state, slot, 0)
    assert machine.r16(0x904BFC) == state.rng.seed & 0xFFFF
    assert [s for s in range(32, 1024) if machine.picture(s) != state.mobs.picture[s]] == []


_APPROACHES = (
    (gin.JOY_RIGHT, 0, -1), (gin.JOY_LEFT, 0, 1), (gin.JOY_DOWN, -1, 0), (gin.JOY_UP, 1, 0),
)


@requires_mazes
@pytest.mark.parametrize("centred", [False, True])
@pytest.mark.parametrize("maze", [16, 36, 46, 72])
def test_a_transport_in_a_real_level_matches_the_rom(maze, centred):
    """Walking onto each pad: the stored cell, then where the hero really lands."""
    probe = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(probe, 7, maze_number=maze)
    pads = [s for s in range(32, 1024)
            if probe.mobs.obj_type(s) == int(MazeObjIds.TRANSPORTER) and probe.mobs.picture[s]]
    assert len(pads) >= 2
    compared = 0
    for pad in pads[:3]:
        for delta, row_step, col_step in _APPROACHES:
            hero = (((pad >> 5) + row_step & 31) << 5) | ((pad + col_step) & 31)
            if hero < 32 or probe.mobs.picture[hero]:
                continue
            state = _real_level(maze, hero)
            scroll_to_slot(state, hero)
            player = state.players[0]
            state.movement_type = 2
            machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
            for _ in range(24):
                rom_exec.player_try_move(machine, state, 0, delta)
                state.movement_type = 2
                origin = (player.mob_slot, state.mobs.hpos[player.mob_slot],
                          state.mobs.vpos[player.mob_slot])
                player_try_move(state, 0, delta, 0, track_thief=False)
                player_movement.resolve_entered_cell(state, 0, origin)
                assert machine.r16(0x904BCE) == state.player_tport_phase[0] & 0xFFFF
                if state.player_tport_phase[0] >= 0:
                    break
            else:
                continue
            assert machine.r16(0x904BE2) == state.player_tport_type[0]
            assert machine.r16(0x904BD8) == state.player_tile_or_tport_dest[0]
            stick = 0xFFFF if centred else 0xFFFF & ~delta
            machine.w16(0x904920, stick)
            state.player_input_raw[0] = stick
            machine.call(0x50662, 0, count=2_000_000)
            assert machine.halted
            player_transport.tport_player_move(state, 0)
            slot = machine.player_slot(0)
            assert (slot, machine.hpos(slot) & 0xFF80, machine.vpos(slot) & 0xFF80) == (
                player.mob_slot, state.mobs.hpos[player.mob_slot] & 0xFF80,
                state.mobs.vpos[player.mob_slot] & 0xFF80,
            )
            assert machine.r16(0x904BFC) == state.rng.seed & 0xFFFF
            compared += 1
    assert compared


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
