"""Shared 0x5214C/0x4E7C0 contracts, including optional original-ROM execution."""

from copy import deepcopy
import json
import os
from pathlib import Path
import pickle
import struct
import subprocess
import sys

import pytest

from gauntpy.game.constants import MazeObjIds
from gauntpy.game.state import GameState
from gauntpy.game.subsystems import (
    maze_objects,
    monsters,
    player_transport,
    players,
    score,
    shot_damage,
    shots,
    thief,
)


_SCORE_VECTORS = [
    (100, 3, 25, 175),
    (0xFFFF_FFF0, 3, 10, 14),
    (0, 2, 0x10001, 2),
    (0, 2, 0x8000, 0x10000),
    (0, 2, 0xFFFF, 0x1FFFE),
    (0, 0xFFFF, 0xFFFF, 0xFFFE0001),
    (123, 0, 12345, 123),
    (123, 7, 0, 123),
    (0xFFFF0000, 1, 0x10000, 0xFFFF0000),
]
_TPORT_VECTORS = [
    ((), 0x44, 1),
    ((0x44, 0x155, 0x2AA), 0x44, 1),
    ((0x44, 0x155, 0x2AA), 0x155, 2),
    ((0x44, 0x155, 0x2AA), 0x2AA, 3),
    ((0x44, 0x155, 0x2AA), 0x99, 4),
    ((0x44, 0x155, 0x2AA), 0, 4),
    ((0x44,), 0x10044, 1),
    ((0x44,), 0xFFFF, 2),
]


def _assert_same_state(actual, expected):
    # Compare all instance/component state, not a selected gameplay snapshot.
    assert pickle.dumps(actual) == pickle.dumps(expected)


def _score_state(player_index, initial, bonus):
    state = GameState()
    for index, player in enumerate(state.players):
        player.score = 1000 + index
        player.bonusmult = index + 1
        player.health = 200 + index
    state.score_dirty = [1, 0, 1, 0]
    state.health_dirty = [1, 1, 0, 1]
    state.score_dirty[player_index] = 0
    state.players[player_index].score = initial
    state.players[player_index].bonusmult = bonus
    state.idle_timer = 37
    state.escape_timer = 91
    return state


def _pad_state(pads):
    state = GameState()
    for slot in reversed(pads):
        state.mobs.set_obj_type(slot, int(MazeObjIds.TRANSPORTER))
    return state


def test_shared_routine_exports_have_one_identity():
    for module in (players, shots, monsters, thief):
        assert module.player_add_score_with_mult is score.player_add_score_with_mult
    for module in (maze_objects, thief):
        assert module.tport_find_id is player_transport.tport_find_id


@pytest.mark.parametrize("player_index", range(4))
@pytest.mark.parametrize("initial,bonus,base,result", _SCORE_VECTORS)
def test_score_words_longword_and_complete_side_effects(
    player_index, initial, bonus, base, result,
):
    state = _score_state(player_index, initial, bonus)
    expected = deepcopy(state)
    expected.players[player_index].score = result
    expected.score_dirty[player_index] = 1

    assert score.player_add_score_with_mult(state, player_index, base) is None

    _assert_same_state(state, expected)


def test_signed_host_word_is_not_a_negative_score_award():
    """The raw 0xFFFF operand is unsigned at MULU.W, not a gameplay penalty."""
    state = _score_state(0, 0, 2)
    score.player_add_score_with_mult(state, 0, -1)
    assert state.players[0].score == 0x1FFFE


def test_bonus_is_read_as_a_word():
    state = _score_state(0, 0, 0x10002)
    score.player_add_score_with_mult(state, 0, 25)
    assert state.players[0].score == 50


@pytest.mark.parametrize("factor", [0, 1, 5, 10, 100])
@pytest.mark.parametrize("idle_timer", [-1, 0, 37])
def test_shot_caller_prepares_base_once_and_preserves_other_state(
    monkeypatch, factor, idle_timer,
):
    state = _score_state(1, 0xFFFF_FFF0, 3)
    state.idle_timer = idle_timer
    state.players[1].supershot = 1
    expected = deepcopy(state)
    expected.players[1].score = (0xFFFF_FFF0 + 3 * factor * 3) & 0xFFFF_FFFF
    expected.score_dirty[1] = 1
    expected.idle_timer = min(0, idle_timer)
    calls = []
    canonical = score.player_add_score_with_mult

    def record_call(current, player_index, base):
        calls.append((player_index, base))
        canonical(current, player_index, base)

    monkeypatch.setattr(score, "player_add_score_with_mult", record_call)
    result = shot_damage._score_tail(
        state, 0x155, 1, 3, int(MazeObjIds.MONST_GRUNT), factor,
    )

    assert result == shot_damage.SURVIVES
    assert calls == [(1, 3 * factor)]
    _assert_same_state(state, expected)


def test_monster_shot_skips_score_and_player_idle_tail(monkeypatch):
    state = _score_state(0, 123, 3)
    expected = deepcopy(state)
    finished = []

    def finish(current, slot, shooter):
        finished.append((slot, shooter))
        return shot_damage.SURVIVES

    monkeypatch.setattr(shot_damage, "_finish", finish)
    assert shot_damage._score_tail(
        state, 0x155, 4, 3, int(MazeObjIds.MONST_GRUNT), 10,
    ) == shot_damage.SURVIVES
    assert finished == [(0x155, 4)]
    _assert_same_state(state, expected)


@pytest.mark.parametrize("player_index", [0, 3, -1, 0xFFFF])
def test_thief_bounty_uses_shared_score_and_keeps_no_award_sentinel(player_index):
    state = _score_state(0, 0xFFFF_FFF0, 3)
    state.thief_item_carried = 0
    state.special_bonus_score = 321
    state.thief_victim = -1
    state.thief_enter_time = 42
    expected = deepcopy(state)
    expected.special_bonus_score = 0
    expected.thief_item_carried = 0x7D30
    expected.thief_enter_time = -1
    if player_index in (0, 3):
        player = expected.players[player_index]
        player.score = (player.score + 500 * player.bonusmult) & 0xFFFF_FFFF
        expected.score_dirty[player_index] = 1

    thief.thief_remove_and_drop_loot(state, player_index, 0)

    _assert_same_state(state, expected)


@pytest.mark.parametrize("pads,query,result", _TPORT_VECTORS)
def test_transporter_lookup_order_miss_and_no_side_effects(pads, query, result):
    state = _pad_state(pads)
    expected = deepcopy(state)
    assert player_transport.tport_find_id(state, query) == result
    _assert_same_state(state, expected)


@pytest.mark.parametrize("destination", [0, 0x99, 0x2AA])
@pytest.mark.parametrize("powers_gate", [False, True])
def test_secret_progress_bridge_does_not_mark_the_lookup_miss(
    destination, powers_gate,
):
    state = _pad_state((0x44, 0x155, 0x2AA))
    state.secret_trick_id = 0x56
    state.tport_secret_pad_masks[1] = 0x10
    state.secret_tricks_flags[1] = 0x10
    expected = deepcopy(state)
    if not powers_gate:
        mask = 0x12 | (0x08 if destination == 0x2AA else 0)
        expected.tport_secret_pad_masks[1] = mask
        expected.secret_tricks_flags[1] = mask

    maze_objects.record_transporter_secret_progress(
        state, 1, 0x44, destination, 0x156, powers_gate=powers_gate,
    )

    _assert_same_state(state, expected)


@pytest.mark.parametrize("pad", [0, 0x99, 0x155, 0x10155])
@pytest.mark.parametrize("trick", [0x56, 1])
def test_player_visit_keeps_success_absence_and_objective_guards(pad, trick):
    state = _pad_state((0x44, 0x155, 0x2AA))
    state.secret_trick_id = trick
    state.secret_tricks_flags[1] = 0x10
    expected = deepcopy(state)
    if trick == 0x56 and pad & 0xFFFF == 0x155:
        expected.secret_tricks_flags[1] = 0x14

    player_transport._tport_visit_pad(state, 1, pad)

    _assert_same_state(state, expected)


def test_player_visit_calls_the_shared_lookup(monkeypatch):
    state = _pad_state((0x44, 0x155))
    state.secret_trick_id = 0x56
    calls = []
    canonical = player_transport.tport_find_id

    def record_call(current, pad):
        calls.append(pad)
        return canonical(current, pad)

    monkeypatch.setattr(player_transport, "tport_find_id", record_call)
    player_transport._tport_visit_pad(state, 0, 0x155)
    assert calls == [0x155]
    assert state.secret_tricks_flags[0] == 1 << 2


@pytest.fixture(scope="module")
def rom_runner():
    pytest.importorskip("unicorn")
    pytest.importorskip("unicorn.m68k_const")
    rom_path = Path(__file__).resolve().parents[2] / "row76.bin"
    if not rom_path.is_file():
        pytest.skip("original local row76.bin is unavailable")

    def run(check_name, *arguments):
        # Unicorn's handled Windows memory probes trigger pytest's fatal-error
        # handler. Isolate native execution without changing pytest's handler.
        script = (
            "import faulthandler,json,runpy,sys; faulthandler.disable(); "
            "module=runpy.run_path(sys.argv[1]); "
            "module[sys.argv[2]](*json.loads(sys.argv[3]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script, str(Path(__file__).resolve()),
             check_name, json.dumps(arguments)],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        )
        assert result.returncode == 0, result.stdout + result.stderr

    return run


def _make_rom_cpu():
    import unicorn
    from unicorn import m68k_const as registers

    rom = (Path(__file__).resolve().parents[2] / "row76.bin").read_bytes()
    cpu = unicorn.Uc(unicorn.UC_ARCH_M68K, unicorn.UC_MODE_BIG_ENDIAN)
    cpu.ctl_set_cpu_model(registers.UC_CPU_M68K_M68000)
    cpu.mem_map(0x40000, 0x20000)
    cpu.mem_write(0x40000, rom)
    cpu.mem_map(0x900000, 0x20000)
    cpu.mem_write(0x900000, b"\x5A" * 0x20000)
    cpu.mem_map(0x100000, 0x10000)
    cpu.reg_write(registers.UC_M68K_REG_A7, 0x108000)
    writes = []

    def record_write(current, access, address, size, value, context):
        if 0x900000 <= address < 0x920000:
            writes.append((address, size))

    cpu.hook_add(unicorn.UC_HOOK_MEM_WRITE, record_write)
    return cpu, registers, writes


def _assert_rom_score_ram(cpu, writes, before, player_index, result):
    expected = bytearray(before)
    score_offset = 0x4990 + 4 * player_index
    expected[score_offset:score_offset + 4] = struct.pack(">I", result)
    expected[0x4908 + player_index] |= 1
    assert bytes(cpu.mem_read(0x900000, 0x20000)) == bytes(expected)
    assert writes == [(0x904990 + 4 * player_index, 4), (0x904908 + player_index, 1)]


@pytest.mark.parametrize("initial,bonus,base,result", _SCORE_VECTORS)
def test_original_score_routine_matches_all_ram_writes(
    rom_runner, initial, bonus, base, result,
):
    rom_runner("_check_original_score", initial, bonus, base, result)


def _check_original_score(initial, bonus, base, result):
    cpu, registers, writes = _make_rom_cpu()
    player_index = 2
    cpu.mem_write(0x108000, struct.pack(">III", 0x58000, player_index, base))
    cpu.mem_write(0x904998, struct.pack(">I", initial))
    cpu.mem_write(0x904912, struct.pack(">H", bonus))
    cpu.mem_write(0x90490A, b"\xA6")
    before = bytes(cpu.mem_read(0x900000, 0x20000))

    cpu.emu_start(0x5214C, 0x58000, count=100)

    assert cpu.reg_read(registers.UC_M68K_REG_PC) == 0x58000
    _assert_rom_score_ram(cpu, writes, before, player_index, result)


@pytest.mark.parametrize("damage,factor,bonus", [
    (3, 100, 3), (3, 10, 2), (2, 5, 4), (3, 0, 8), (3, 1, 4),
    # Register-level boundary probes, not reachable negative gameplay damage.
    (0x100, 0x100, 3), (0xFFFF, 25, 3), (0x7FFF, 3, 3),
])
def test_original_shot_muls_precedes_unsigned_word_score(
    rom_runner, damage, factor, bonus,
):
    rom_runner("_check_original_shot_score", damage, factor, bonus)


def _check_original_shot_score(damage, factor, bonus):
    cpu, registers, writes = _make_rom_cpu()
    player_index = 1
    cpu.reg_write(registers.UC_M68K_REG_D3, player_index)
    cpu.reg_write(registers.UC_M68K_REG_D5, factor)
    cpu.reg_write(registers.UC_M68K_REG_D6, damage)
    cpu.mem_write(0x904994, struct.pack(">I", 0))
    cpu.mem_write(0x904910, struct.pack(">H", bonus))
    cpu.mem_write(0x904909, b"\xA6")
    before = bytes(cpu.mem_read(0x900000, 0x20000))
    state = _score_state(player_index, 0, bonus)
    score.player_add_score_with_mult(state, player_index, damage * factor)

    cpu.emu_start(0x4BD7A, 0x4BD8E, count=100)

    assert cpu.reg_read(registers.UC_M68K_REG_PC) == 0x4BD8E
    _assert_rom_score_ram(
        cpu, writes, before, player_index, state.players[player_index].score,
    )


@pytest.mark.parametrize("pads,query,result", _TPORT_VECTORS)
def test_original_transporter_lookup_matches_without_ram_writes(
    rom_runner, pads, query, result,
):
    rom_runner("_check_original_transporter_lookup", pads, query, result)


def _check_original_transporter_lookup(pads, query, result):
    cpu, registers, writes = _make_rom_cpu()
    cpu.mem_write(0x108000, struct.pack(">II", 0x58000, query))
    cpu.mem_write(0x904B84, struct.pack(">H", len(pads)))
    if pads:
        cpu.mem_write(0x910700, struct.pack(">" + "H" * len(pads), *pads))
    before = bytes(cpu.mem_read(0x900000, 0x20000))

    cpu.emu_start(0x4E7C0, 0x58000, count=500)

    assert cpu.reg_read(registers.UC_M68K_REG_D0) == result
    assert cpu.reg_read(registers.UC_M68K_REG_PC) == 0x58000
    assert bytes(cpu.mem_read(0x900000, 0x20000)) == before
    assert writes == []
