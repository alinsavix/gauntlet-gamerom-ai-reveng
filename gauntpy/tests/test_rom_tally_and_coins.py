"""The level-end tally and a coin during name entry, against the ROM (tools/rom_exec.py)."""

from __future__ import annotations

import copy
import importlib.util
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

from gauntpy.game.constants import PlayerStatus  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems.session import coincheck  # noqa: E402
from gauntpy.game.subsystems.treasure_rooms import show_level_end_bonus_screen  # noqa: E402

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "rom_exec.py"
_SPEC = importlib.util.spec_from_file_location("gauntpy_rom_exec", _TOOL)
rom_exec = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = rom_exec
_SPEC.loader.exec_module(rom_exec)

pytestmark = pytest.mark.skipif(
    not rom_exec.roms_available(), reason="original local ROM images are unavailable",
)

_NEXT = int(PlayerStatus.ALIVE_NEXT)
_NAME_ENTRY = int(PlayerStatus.DYING)


def _sounds(machine) -> list[int]:
    """Every byte passed to sound_play (0x4AD76)."""
    played: list[int] = []

    def hook(cpu, _address, _size, _data):
        stack = cpu.reg_read(rom_exec.registers.UC_M68K_REG_A7)
        played.append(bytes(cpu.mem_read(stack + 7, 1))[0])

    machine.cpu.hook_add(rom_exec.unicorn.UC_HOOK_CODE, hook, begin=0x4AD76, end=0x4AD76)
    return played


def _field(words: list[int]) -> list[int]:
    """The alpha columns left of the info panel. The panel reads OS coin settings the snapshot lacks."""
    return [word for i, word in enumerate(words) if i % 64 < 29]


def _rom_alpha(machine) -> list[int]:
    return [machine.r16(0x905000 + 2 * i) for i in range(64 * 30)]


def _long(machine, address: int) -> int:
    return struct.unpack(">I", bytes(machine.cpu.mem_read(address, 4)))[0]


@pytest.mark.parametrize(
    ("statuses", "coins", "treasures"),
    [
        pytest.param([_NEXT, _NEXT], [2, 3], [1, 4], id="plain"),
        pytest.param([_NEXT, _NEXT], [1, 1], [0, 2], id="first-exiter-holds-none"),
        pytest.param([_NEXT] * 4, [200] * 4, [2] * 4, id="coin-factor-wraps-16-bits"),
        pytest.param([_NEXT, _NEXT], [400, 1], [3, 0], id="wraps-with-two-heroes"),
        pytest.param([_NEXT], [0], [4], id="no-coins"),
        pytest.param([_NEXT], [1], [255], id="treasure-byte-at-its-top"),
    ],
)
def test_the_ordinary_tally_pays_and_shows_what_the_rom_does(statuses, coins, treasures):
    state = GameState()
    state.mazenum_current, state.levelnum_current = 20, 8
    state.maze_next, state.level_next = 21, 9
    for i, status in enumerate(statuses):
        state.players[i].status = status
        state.players[i].coin_count = coins[i]
        state.player_treascount[i] = treasures[i]

    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    for i, count in enumerate(state.player_treascount):
        machine.w8(0x904A50 + i, count)
    machine.w16(0x904000, state.mazenum_current)
    machine.w16(0x904B54, state.maze_next)
    machine.call(0x4D476)
    assert machine.halted, machine.fault_pc

    show_level_end_bonus_screen(state)
    assert [p.score for p in state.players] == [_long(machine, 0x904990 + 4 * i) for i in range(4)]
    assert state.score_dirty[: len(statuses)] == [1] * len(statuses)
    assert [machine.r8(0x904908 + i) & 1 for i in range(len(statuses))] == [1] * len(statuses)
    assert _field(state.alpha_ram) == _field(_rom_alpha(machine))


def _coin_state(statuses: dict[int, int], level: int = 8, active: int = 0) -> GameState:
    state = GameState()
    state.game_mode = 0
    state.mazenum_current, state.levelnum_current = 20, level
    state.level_players_active = active
    state.attract_timer = 0x5DD
    for i, status in statuses.items():
        state.players[i].status = status
    return state


def _rom_coin(state: GameState, player: int):
    """Drop one coin for ``player``: the OS keeps a count per player, top byte first."""
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    for i, player_state in enumerate(state.players):
        machine.w8(0x9049A0 + i, player_state.status)
    machine.cpu.mem_write(0x904FEC, struct.pack(">I", 1 << (8 * (3 - player))))
    machine.cpu.mem_write(0x9049EA, struct.pack(">I", 0))
    machine.w16(0x9049E2, 1)
    machine.w16(0x904928, state.level_players_active)
    played = _sounds(machine)
    prompts = machine.count_calls(0x44C7E)
    machine.call(0x42B6A)
    assert machine.halted, machine.fault_pc
    return machine, played, prompts[0]


@pytest.mark.parametrize(
    ("statuses", "level", "prompt_written"),
    [
        pytest.param({2: _NAME_ENTRY}, 8, True, id="alone-in-name-entry"),
        pytest.param({2: _NAME_ENTRY, 0: _NAME_ENTRY}, 8, False, id="another-still-entering"),
        pytest.param({2: _NAME_ENTRY}, 1, False, id="level-one-has-no-prompt"),
        pytest.param({2: 0}, 8, False, id="not-in-name-entry"),
    ],
)
def test_a_coin_during_name_entry_runs_the_continue_prompt(statuses, level, prompt_written):
    state = _coin_state(statuses, level=level)
    machine, played, prompts = _rom_coin(state, 2)
    assert prompts == (1 if statuses[2] == _NAME_ENTRY else 0)
    assert (0x3B in played) == prompt_written, "the theme marks a prompt actually drawn"

    state.coin_counters = 1 << (2 * 2)   # gauntpy's own two-bit channel for player 2
    state.last_coin_state = 0
    coincheck(state)

    assert [p.status for p in state.players] == [machine.r8(0x9049A0 + i) for i in range(4)]
    assert state.sound_log == played
    assert _field(state.alpha_ram) == _field(_rom_alpha(machine))
