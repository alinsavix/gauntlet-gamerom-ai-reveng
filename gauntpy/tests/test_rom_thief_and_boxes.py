"""Message boxes, the IT announcement, the thief and mid-level joins against the ROM."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

unicorn = pytest.importorskip("unicorn")

from gauntpy.game.constants import GameMode, MazeObjIds, PlayerStatus  # noqa: E402
from gauntpy.game.coords import native_v  # noqa: E402
from gauntpy.game.maze import reset_and_load_level  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import input as gin  # noqa: E402
from gauntpy.game.subsystems.camera import scroll_to_slot  # noqa: E402
from gauntpy.game.subsystems.exits import main_exit_move  # noqa: E402
from gauntpy.game.subsystems.level_transitions import player_exit_sequence  # noqa: E402
from gauntpy.game.subsystems.monster_contact import _it_tag  # noqa: E402
from gauntpy.game.subsystems.player_items import _player_give_item_id  # noqa: E402
from gauntpy.game.subsystems.player_lifecycle import player_start_inner  # noqa: E402
from gauntpy.game.subsystems.player_movement import player_try_move  # noqa: E402
from gauntpy.game.subsystems.score import (  # noqa: E402
    demo_message_show,
    dialog_first_encounter,
    main_msgbox_countdown,
    player_it_announce,
)
from gauntpy.game.subsystems.thief import (  # noqa: E402
    main_start_thief,
    main_thief_anim,
    thief_steal_from_player,
)
from gex.roms import SLAPSTIC_ROMS, _rom_dir  # noqa: E402

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "rom_exec.py"
_NAME = "gauntpy_rom_exec"
if _NAME in sys.modules:
    rom_exec = sys.modules[_NAME]
else:
    _SPEC = importlib.util.spec_from_file_location(_NAME, _TOOL)
    rom_exec = importlib.util.module_from_spec(_SPEC)
    sys.modules[_NAME] = rom_exec
    _SPEC.loader.exec_module(rom_exec)

pytestmark = pytest.mark.skipif(
    not rom_exec.roms_available(), reason="original local ROM images are unavailable",
)
requires_mazes = pytest.mark.skipif(
    not (_rom_dir() / SLAPSTIC_ROMS[0]).is_file(), reason="Slapstic ROMs not available",
)

_HERO = (10 << 5) | 10
_MUGGER = 0x80
_ESCAPE = 0x02
_EMPTY_CARRY = 0x7D30


def _state(slot: int = _HERO, character: int = 0, index: int = 0, settings: int = 0) -> GameState:
    state = GameState(game_mode=GameMode.NORMAL)
    state.game_settings = settings
    state.rng.seed = 0x1234
    _place_hero(state, index, slot, character)
    state.level_players_active = 1
    state.level_flags_4 |= 0x80
    scroll_to_slot(state, slot)
    return state


def _place_hero(state: GameState, index: int, slot: int, character: int = 0) -> None:
    player = state.players[index]
    player.status = PlayerStatus.ALIVE_HERE
    player.character = character
    player.mob_slot = slot
    player.health, player.coin_count = 500, 1
    state.mobs.create(
        slot, tile=0x1E0D, hpos=(((slot & 0x1F) * 16 - 4) << 7) | (0x0C + index),
        vpos=native_v((slot >> 5) * 16) << 7,
        obj_type=int(MazeObjIds.PLAYERSTART), state=index,
    )


def _rom(state: GameState) -> "rom_exec.RomMachine":
    return rom_exec.RomMachine.from_state(copy.deepcopy(state))


def _sounds(machine) -> list[int]:
    """Every byte the ROM passes to ``sound_play`` from now on."""
    log: list[int] = []

    def hook(cpu, _address, _size, _data):
        stack = cpu.reg_read(unicorn.m68k_const.UC_M68K_REG_A7)
        log.append(struct.unpack(">I", bytes(cpu.mem_read(stack + 4, 4)))[0] & 0xFF)

    machine.cpu.hook_add(unicorn.UC_HOOK_CODE, hook, begin=0x4AD76, end=0x4AD76)
    return log


def _alpha(machine) -> list[int]:
    return [machine.r16(0x905000 + 2 * i) for i in range(64 * 30)]


def _long(machine, address: int) -> int:
    return struct.unpack(">I", bytes(machine.cpu.mem_read(address, 4)))[0]


def _box_cells(words: list[int], state: GameState) -> list[int]:
    """The alpha cells inside the box the Python state says is open."""
    left, top = state.dialog_box_column, state.dialog_box_row
    return [
        words[row * 64 + column]
        for row in range(top, top + state.dialog_box_height)
        for column in range(left, left + state.dialog_box_width)
    ]


# --- message boxes -------------------------------------------------------------------

@pytest.mark.parametrize("mask", [1 << bit for bit in (3, 8, 20, 21, 28, 29)])
@pytest.mark.parametrize("slot", [_HERO, (3 << 5) | 3, (26 << 5) | 28])
def test_a_first_encounter_box_matches_the_rom_cell_for_cell(mask, slot):
    state = _state(slot)
    machine = _rom(state)
    machine.call(0x4C440, 0, mask, 7, count=500_000)
    assert machine.halted
    dialog_first_encounter(state, 0, mask, 7)
    assert _alpha(machine) == state.alpha_ram
    assert machine.r16(0x904A9E) == state.dialog_timer
    assert machine.r16(0x904A9A) == state.dialog_box_width
    assert machine.r16(0x904A9C) == state.dialog_box_height


def test_a_demo_tip_matches_the_rom_cell_for_cell():
    state = _state()
    state.game_mode = GameMode.DEMO
    machine = _rom(state)
    machine.call(0x4C9A2, 0, 0, count=500_000)
    assert machine.halted
    demo_message_show(state, 0, 0)
    assert _alpha(machine) == state.alpha_ram


def test_a_box_goes_by_a_transporting_heros_destination():
    state = _state()
    state.player_tport_phase[0] = 0
    state.player_tile_or_tport_dest[0] = _HERO + 3
    machine = _rom(state)
    machine.call(0x4C440, 0, 1 << 20, 0, count=500_000)
    dialog_first_encounter(state, 0, 1 << 20, 0)
    assert machine.r16(0x904AA0) == state.dialog_box_column
    assert _alpha(machine) == state.alpha_ram


def test_an_expiring_box_leaves_nothing_behind_like_the_rom():
    state = _state()
    machine = _rom(state)
    machine.call(0x4C440, 0, 1 << 20, 0, count=500_000)
    dialog_first_encounter(state, 0, 1 << 20, 0)
    machine.w16(0x904A9E, 1)
    state.dialog_timer = 1
    machine.call(0x4CCBC)
    main_msgbox_countdown(state)
    assert _alpha(machine) == state.alpha_ram == [0] * (64 * 30)


@pytest.mark.parametrize("settings", [0, 0x0400, 1 << 11])
@pytest.mark.parametrize("item", range(12))
@pytest.mark.parametrize("character,index", [(0, 0), (1, 1), (2, 2), (3, 3)])
def test_a_power_up_box_matches_the_rom(character, index, item, settings):
    state = _state(character=character, index=index, settings=settings)
    machine = _rom(state)
    sounds = _sounds(machine)
    result = machine.call(0x4C72A, index, item, count=500_000)
    assert machine.halted and result == 1
    assert _player_give_item_id(state, index, item)
    assert _alpha(machine) == state.alpha_ram
    assert machine.r16(0x904A9E) == state.dialog_timer
    assert machine.r16(0x9048E0 + 2 * index) == state.players[index].powers
    assert machine.r16(0x90487E) == state.dialog_once_flags
    assert sounds == state.sound_log


def test_a_power_up_retires_an_open_box_like_the_rom():
    state = _state()
    machine = _rom(state)
    machine.call(0x4C440, 0, 1 << 20, 0, count=500_000)
    machine.call(0x4C72A, 0, 0, count=500_000)
    assert machine.halted
    dialog_first_encounter(state, 0, 1 << 20, 0)
    _player_give_item_id(state, 0, 0)
    assert _alpha(machine) == state.alpha_ram


def test_a_second_grant_of_a_once_only_power_shows_no_box():
    state = _state()
    state.dialog_once_flags = 0x0100
    machine = _rom(state)
    sounds = _sounds(machine)
    assert machine.call(0x4C72A, 0, 6, count=500_000) == 1
    assert _player_give_item_id(state, 0, 6)
    assert machine.r16(0x904A9E) == state.dialog_timer == 0
    assert sounds == state.sound_log == []


# --- the IT announcement --------------------------------------------------------------

@pytest.mark.parametrize("holder", [0xFFFF, 1, 0])
@pytest.mark.parametrize("character", range(4))
def test_the_it_announcement_matches_the_rom(holder, character):
    state = _state(character=character)
    state.player_it = holder
    machine = _rom(state)
    sounds = _sounds(machine)
    machine.call(0x45866, 0)
    assert machine.halted
    player_it_announce(state, 0)
    assert sounds == state.sound_log


@pytest.mark.parametrize("holder", [0xFFFF, 1, 0])
def test_tagging_the_it_monster_matches_the_rom(holder):
    """Enter 0x4967A with its registers; stop before the dialog, which plays its own sound."""
    state = _state(character=1)
    state.player_it = holder
    monster = _HERO + 1
    state.mobs.create(
        monster, tile=0x2000, hpos=((monster & 0x1F) * 16) << 7,
        vpos=native_v((monster >> 5) * 16) << 7, obj_type=int(MazeObjIds.MONST_IT),
    )
    machine = _rom(state)
    sounds = _sounds(machine)
    machine.cpu.reg_write(unicorn.m68k_const.UC_M68K_REG_D4, 0)
    machine.cpu.reg_write(unicorn.m68k_const.UC_M68K_REG_D2, monster)

    def stop(cpu, _address, _size, _data):
        cpu.emu_stop()

    machine.cpu.hook_add(unicorn.UC_HOOK_CODE, stop, begin=0x496F4, end=0x496F4)
    machine.call(0x4967A, count=100_000)
    _it_tag(state, 0, monster)
    assert sounds == state.sound_log[:len(sounds)] and len(sounds) >= 1
    assert machine.r16(0x9049DC) == state.player_it == 0
    assert machine.r16(0x904A54) == state.players[0].stundelay


def test_passing_it_to_another_hero_matches_the_rom():
    state = _state(character=2)
    _place_hero(state, 1, _HERO + 1, character=3)
    state.level_players_active = 2
    state.player_it = 0
    state.movement_type = 2
    machine = _rom(state)
    sounds = _sounds(machine)
    rom_exec.player_try_move(machine, state, 0, gin.JOY_RIGHT, 2)
    assert machine.halted
    player_try_move(state, 0, gin.JOY_RIGHT, 0)
    assert machine.r16(0x9049DC) == state.player_it == 1
    assert sounds == state.sound_log
    assert machine.r16(0x904A54 + 2) == state.players[1].stundelay


# --- the thief ------------------------------------------------------------------------

_THIEF = (10 << 5) | 12


def _thief_on_level(state: GameState, mode: int = 0) -> None:
    state.mobs.create(
        _THIEF, tile=0x2000, hpos=((_THIEF & 0x1F) * 16 - 4) << 7,
        vpos=native_v((_THIEF >> 5) * 16) << 7, obj_type=int(MazeObjIds.PLAYERSTART),
    )
    state.thief_mob_slot = state.thief_current_pos = _THIEF
    state.thief_previous_pos = _THIEF + 1
    state.thief_next_pos = _THIEF
    state.thief_start_location = _THIEF + 2
    state.thief_mode = mode
    state.thief_victim = 0
    state.thief_enter_time = -1


@pytest.mark.parametrize("fields", [
    {}, {"potionsnum": 2}, {"keysnum": 3}, {"bonusmult": 4},
    {"powers": 0x0002}, {"powers": 0x0020}, {"potionsnum": 1, "keysnum": 1},
])
def test_a_theft_matches_the_rom(fields):
    state = _state()
    state.players[0].bonusmult = 1
    for name, value in fields.items():
        setattr(state.players[0], name, value)
    _thief_on_level(state)
    machine = _rom(state)
    sounds = _sounds(machine)
    assert machine.call(0x4E1FE, 0, count=500_000) == 1
    assert machine.halted
    assert thief_steal_from_player(state, 0) == 1
    player = state.players[0]
    assert machine.r16(0x904BA0) == state.thief_mode
    assert _long(machine, 0x904BB4) == state.thief_item_carried
    assert machine.r16(0x9048E0) == player.powers
    assert machine.r8(0x904055) == player.potionsnum
    assert machine.r8(0x90405A) == player.keysnum
    assert machine.r16(0x90490E) == player.bonusmult
    assert _long(machine, 0x9049E4) == state.dialog_first_encounter_flags == 1 << 20
    assert machine.r16(0x904A9E) == state.dialog_timer
    assert _box_cells(_alpha(machine), state) == _box_cells(state.alpha_ram, state)
    assert sounds == state.sound_log


def test_a_mugging_matches_the_rom():
    state = _state()
    _thief_on_level(state, _MUGGER)
    machine = _rom(state)
    sounds = _sounds(machine)
    assert machine.call(0x4E1FE, 0, count=500_000) == 1
    assert thief_steal_from_player(state, 0) == 1
    assert machine.r16(0x904BA0) == state.thief_mode
    assert _long(machine, 0x904BB0) == state.mugger_item_carried
    assert struct.unpack(">i", bytes(machine.cpu.mem_read(0x904980, 4)))[0] == state.players[0].health
    assert _long(machine, 0x9049E4) == state.dialog_first_encounter_flags == 1 << 29
    assert _alpha(machine) == state.alpha_ram
    assert sounds == state.sound_log


@pytest.mark.parametrize("mode,carried,victim_there", [
    (_ESCAPE, int(MazeObjIds.KEY), True),
    (_ESCAPE, _EMPTY_CARRY, True),
    (_ESCAPE | _MUGGER, 0x32, True),
    (_ESCAPE | _MUGGER, 0, True),
    (_ESCAPE | _MUGGER, 0x32, False),
])
def test_leaving_at_the_start_cell_matches_the_rom(mode, carried, victim_there):
    state = _state()
    _thief_on_level(state, mode)
    state.thief_start_location = _THIEF
    if mode & _MUGGER:
        state.mugger_item_carried = carried
    else:
        state.thief_item_carried = carried
    if not victim_there:
        state.players[0].mob_slot = 0
    machine = _rom(state)
    machine.call(0x4E8DC, count=500_000)
    assert machine.halted
    main_thief_anim(state)
    assert machine.r16(0x904BA4) == state.thief_current_pos == 0
    assert _long(machine, 0x9049E4) == state.dialog_first_encounter_flags
    assert machine.r16(0x904A9E) == state.dialog_timer
    assert _long(machine, 0x904BA8) == state.mugger_item_nextlevel
    assert _long(machine, 0x904BAC) == state.thief_item_nextlevel
    assert machine.r16(0x904BFC) == state.rng.seed


_BLOCKER_OFFSETS = [None, (-16, 0), (16, 0), (-14, 2), (-15, 0), (-16, 16), (-8, -8)]


@pytest.mark.parametrize("offset", _BLOCKER_OFFSETS)
@pytest.mark.parametrize("mode", [0, _MUGGER])
def test_the_thief_arriving_matches_the_rom(offset, mode):
    """0x48F12 goes by pixel distance, so a near neighbour delays it and a far one does not."""
    state = _state((20 << 5) | 20)
    start = _HERO
    if offset is not None:
        dx, dy = offset
        cell = start + (1 if dx > 0 else -1 if dx < 0 else 0)
        state.mobs.create(
            cell, tile=0x2000,
            hpos=(((start & 0x1F) * 16 + dx - 4) << 7) & 0xFFFF,
            vpos=(native_v((start >> 5) * 16) + dy) << 7 & 0xFFFF,
            obj_type=int(MazeObjIds.MONST_GHOST),
        )
    state.thief_mode = mode
    state.thief_victim = 0
    state.thief_start_location = start
    state.thief_enter_time = 0
    state.thief_tport_timer = 5
    machine = _rom(state)
    sounds = _sounds(machine)
    machine.call(0x4DEB8, count=500_000)
    assert machine.halted
    main_start_thief(state)
    assert machine.r16(0x904B9E) == state.thief_enter_time & 0xFFFF
    assert machine.r16(0x904BA4) == state.thief_current_pos
    assert machine.r16(0x904BD6) == state.thief_tport_timer & 0xFFFF
    assert machine.picture(start) == state.mobs.picture[start]
    assert machine.hpos(start) == state.mobs.hpos[start]
    assert machine.vpos(start) == state.mobs.vpos[start]
    assert machine.r16(0x904BFC) == state.rng.seed
    assert sounds == state.sound_log


@pytest.mark.parametrize("mode", [0, _MUGGER])
@pytest.mark.parametrize("armed", [True, False])
def test_the_victim_leaving_through_an_exit_matches_the_rom(mode, armed):
    state = _state()
    exit_slot = _HERO + 1
    state.mobs.create(
        exit_slot, tile=0x8001, hpos=((exit_slot & 0x1F) * 16) << 7,
        vpos=native_v((exit_slot >> 5) * 16) << 7, obj_type=int(MazeObjIds.EXIT),
    )
    if armed:
        state.thief_mode, state.thief_victim, state.thief_enter_time = mode, 0, 100
    else:
        _thief_on_level(state, mode)
    machine = _rom(state)
    # Stop just past the thief_exit call: the rest needs the maze tables this RAM lacks.
    reached = []

    def past_the_call(cpu, _address, _size, _data):
        reached.append(True)
        cpu.emu_stop()

    machine.cpu.hook_add(unicorn.UC_HOOK_CODE, past_the_call, begin=0x52C5E, end=0x52C5E)
    machine.call(0x52B40, 0, exit_slot, int(MazeObjIds.EXIT), count=500_000)
    assert reached
    player_exit_sequence(state, 0, exit_slot, int(MazeObjIds.EXIT))
    assert machine.r16(0x904B9E) == state.thief_enter_time & 0xFFFF
    assert machine.r16(0x904BA0) == state.thief_mode
    assert machine.r16(0x904BA6) == state.thief_next_pos
    if armed:
        assert state.thief_enter_time == -1
    else:
        assert state.thief_mode & _ESCAPE


@pytest.mark.parametrize("present,escaping", [(False, False), (True, False), (True, True)])
def test_thief_exit_matches_the_rom(present, escaping):
    state = _state()
    if present:
        _thief_on_level(state, _ESCAPE if escaping else 0)
    state.thief_enter_time = 7
    machine = _rom(state)
    machine.call(0x4E122)
    assert machine.halted
    from gauntpy.game.subsystems.thief import thief_exit

    thief_exit(state)
    assert machine.r16(0x904B9E) == state.thief_enter_time & 0xFFFF
    assert machine.r16(0x904BA0) == state.thief_mode
    assert machine.r16(0x904BA6) == state.thief_next_pos


@pytest.mark.parametrize("loot", [MazeObjIds.KEY, MazeObjIds.POT_DESTRUCTABLE, _EMPTY_CARRY])
def test_a_moving_exit_landing_on_the_thief_matches_the_rom(loot):
    state = _state((20 << 5) | 20)
    first, second = _THIEF - 4, _THIEF
    for cell in (first,):
        state.mobs.create(
            cell, tile=0x8001, hpos=((cell & 0x1F) * 16) << 7,
            vpos=native_v((cell >> 5) * 16) << 7, obj_type=int(MazeObjIds.EXIT),
        )
    _thief_on_level(state)
    state.thief_item_carried = int(loot)
    state.thief_previous_pos = state.thief_next_pos = _THIEF
    state.exit_slots = [first, second]
    state.exit_open_id = first
    state.exit_move_timer = 1
    state.level_flags_3 |= 0x40
    machine = _rom(state)
    machine.w16(0x904A08, 1)
    machine.w16(0x904A0A, first)
    machine.w16(0x904A06, 2)
    machine.w16(0x910740, first)
    machine.w16(0x910742, second)
    machine.call(0x5287C, count=500_000)
    assert machine.halted
    main_exit_move(state)
    assert machine.r16(0x904BA4) == state.thief_current_pos == 0
    assert _long(machine, 0x904BB4) == state.thief_item_carried == _EMPTY_CARRY
    assert machine.picture(second) == state.mobs.picture[second] == 0x8001
    assert machine.r16(0x904BFC) == state.rng.seed


# --- a mid-level join and a corner squeeze ---------------------------------------------

def _join_choice(state: GameState) -> int:
    """The cell ROM player_start_inner picks for hero 1, or 0 for none."""
    machine = _rom(state)
    chosen: dict[str, int] = {}

    def placed(cpu, _address, _size, _data):
        chosen["slot"] = cpu.reg_read(unicorn.m68k_const.UC_M68K_REG_D4) & 0xFFFF
        cpu.emu_stop()

    def failed(cpu, _address, _size, _data):
        chosen["slot"] = 0
        cpu.emu_stop()

    machine.cpu.hook_add(unicorn.UC_HOOK_CODE, placed, begin=0x48CA8, end=0x48CA8)
    machine.cpu.hook_add(unicorn.UC_HOOK_CODE, failed, begin=0x48C94, end=0x48C94)
    machine.call(0x48BEC, 1, count=200_000)
    return chosen["slot"]


def _python_join(state: GameState) -> int:
    state = copy.deepcopy(state)
    return state.players[1].mob_slot if player_start_inner(state, 1) == -1 else 0


@requires_mazes
@pytest.mark.parametrize("maze", [6, 13, 43, 84, 101])
def test_a_join_picks_the_roms_cell_in_real_levels(maze):
    empty = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(empty, 7, maze_number=maze)
    cells = [slot for slot in range(33, 1023) if not empty.mobs.picture[slot]]
    for hero in (*cells[::17][:60], 0x1D6):
        state = GameState(game_mode=GameMode.NORMAL)
        reset_and_load_level(state, 7, maze_number=maze)
        if state.mobs.picture[hero]:
            continue
        _place_hero(state, 0, hero)
        state.level_players_active = 1
        scroll_to_slot(state, hero)
        assert _join_choice(state) == _python_join(state), hex(hero)


def test_a_join_avoids_a_neighbour_too_close_and_a_cell_off_screen():
    # Both tests matter here: left of the hero is off screen, right has a ghost
    # too close, and above is clear.
    state = _state()
    state.maze = SimpleNamespace()
    state.scroll_x = (_HERO & 0x1F) * 16 - 4
    ghost = _HERO + 2
    state.mobs.create(
        ghost, tile=0x2000, hpos=(((_HERO & 0x1F) * 16 + 16) << 7),
        vpos=native_v((_HERO >> 5) * 16) << 7, obj_type=int(MazeObjIds.MONST_GHOST),
    )
    assert _join_choice(state) == _python_join(state)


def test_a_corner_squeeze_refuses_another_heros_destination():
    power_transport = 1 << 11
    results = []
    for taken in (False, True):
        state = _state()
        state.players[0].powers = power_transport
        key = _HERO + 1
        state.mobs.create(
            key, tile=0x8AFC, hpos=((key & 0x1F) * 16) << 7,
            vpos=native_v((key >> 5) * 16) << 7, obj_type=int(MazeObjIds.KEY),
        )
        state.movement_type = 2
        if taken:
            state.player_tport_phase[1] = 3
            state.player_tile_or_tport_dest[1] = _HERO + 2
        machine = _rom(state)
        rom_result = rom_exec.player_try_move(machine, state, 0, gin.JOY_RIGHT, 2)
        state.player_input_raw[0] = ~gin.JOY_RIGHT & 0xFFFF
        python_result = player_try_move(state, 0, gin.JOY_RIGHT, 0)
        assert rom_result == python_result & 0xFFFF
        assert machine.r16(0x904BD8) == state.player_tile_or_tport_dest[0]
        assert machine.r16(0x904BCE) == state.player_tport_phase[0] & 0xFFFF
        results.append(state.player_tport_phase[0])
    assert results[0] == 0 and results[1] == -1
