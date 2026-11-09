"""Compare high-score qualification and the initials editor with the ROM.

``highscore_check`` (0x49D0E) runs on random scores against a score table the OS's ranking
routine (0x3F68) can read, and ``player_death_sequence`` (0x49DE6) runs frame by frame on random
input, from the first frame to the entry's end. Each frame compares the editor's words and the
alpha layer.

    python tools/name_entry_check.py

Needs the ROMs ``rom_exec.py`` needs.
"""

from __future__ import annotations

import concurrent.futures
import copy
import os
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rom_exec  # noqa: E402

from gauntpy.game.constants import GameMode, PlayerStatus  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import score  # noqa: E402
from gauntpy.game.subsystems.player_lifecycle import setup_infopanel  # noqa: E402
from gauntpy.game.subsystems.player_names import (  # noqa: E402
    highscore_check,
    player_death_sequence,
)

_SCORE_TABLES = 0x100000           # where 0x904FFC's cache points, in the harness's spare RAM
_STICK = (0xFFEF, 0xFFDF, 0xFFBF, 0xFF7F)
_IDLE = 0xFFFF
_MAGIC_HELD, _FIRE_HELD = _IDLE & ~1, _IDLE & ~2


def _machine(state: GameState, player: int) -> rom_exec.RomMachine:
    hero = state.players[player]
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.write_words(0x905000, state.alpha_ram[:64 * 30])
    machine.w8(0x9049A0 + player, int(hero.status))
    machine.w16(0x904A26 + 2 * player, hero.state_timer)
    machine.w8(0x904A36 + player, hero.name_entry_repeat_delay)
    machine.w16(0x904A2E + 2 * player, hero.name_entry_velocity)
    machine.w8(0x904A3A + 4 * player, hero.initials_cursor)
    machine.cpu.mem_write(0x904A3B + 4 * player, bytes(hero.initials))
    machine.w8(0x904A4A + player, hero.highscore_rank)
    machine.cpu.mem_write(0x904B1A + 4 * player, struct.pack(">I", hero.score_per_coin))
    machine.w16(0x9048E8 + 2 * player, int(hero.character))
    machine.w16(0x9048C8 + 2 * player, 0)
    machine.w16(0x9049E2, state.two_player_mode)
    machine.w16(0x904B7C, state.attract_timer)
    machine.w16(0x904B86, state.games_played_counter)
    return machine


def _words(machine: rom_exec.RomMachine, state: GameState, player: int) -> list[str]:
    hero = state.players[player]
    pairs = (
        ("status", machine.r8(0x9049A0 + player), int(hero.status)),
        ("timer", machine.r16(0x904A26 + 2 * player), hero.state_timer & 0xFFFF),
        ("repeat delay", machine.r8(0x904A36 + player), hero.name_entry_repeat_delay & 0xFF),
        ("velocity", machine.r16(0x904A2E + 2 * player), hero.name_entry_velocity & 0xFFFF),
        ("cursor", machine.r8(0x904A3A + 4 * player), hero.initials_cursor & 0xFF),
        ("initials", bytes(machine.cpu.mem_read(0x904A3B + 4 * player, 3)), bytes(hero.initials)),
    )
    out = [f"{name}: ROM {rom!r} PY {python!r}" for name, rom, python in pairs if rom != python]
    bad = [
        index for index in range(64 * 30)
        if index % 64 < 42 and machine.r16(0x905000 + 2 * index) != state.alpha_ram[index]
    ]
    if bad:
        at = bad[0]
        out.append(f"alpha row {at // 64} col {at % 64}: ROM {machine.r16(0x905000 + 2 * at):#x} "
                   f"PY {state.alpha_ram[at]:#x} ({len(bad)} cells)")
    return out


def highscore_cases(rng: random.Random, count: int = 1200) -> list[str]:
    out = []
    for _ in range(count):
        state = GameState(game_mode=GameMode.NORMAL, levelnum_current=8, mazenum_current=20)
        state.attract_timer = 0x5DD
        state.games_played_counter = rng.choice((0, 100, 0x708, 0x709, 1999))
        player = rng.randint(0, 3)
        hero = state.players[player]
        hero.character = rng.randint(0, 3)
        hero.state_timer = 0xFFFF
        ladder = sorted((rng.randint(100, 300000) for _ in range(10)), reverse=True)
        score.high_scores(state)
        state.high_scores[int(hero.character) & 3] = [(value, "AAA") for value in ladder]
        pick = rng.choice(ladder)
        hero.score_per_coin = rng.choice(
            (pick, pick + 1, max(pick - 1, 0), 0, 1, rng.randint(0, 500000),
             0xFFFFFF, 0x1000000, 0x7FFFFFF),
        )
        hero.initials = [rng.choice((0x41, 0x5A, 0x20)) for _ in range(3)]
        machine = _machine(state, player)
        machine.cpu.mem_write(0x904FFC, struct.pack(">I", _SCORE_TABLES))
        table = _SCORE_TABLES + 0x1E + (int(hero.character) & 3) * 0x32
        for rank, value in enumerate(ladder):
            machine.cpu.mem_write(table + rank * 5, value.to_bytes(3, "big") + b"\0\0")
        machine.call(0x49D0E, player, count=3_000_000)
        if not machine.halted:
            out.append(f"ROM did not return (fault {machine.fault_pc})")
            continue
        highscore_check(state, player)
        found = _words(machine, state, player)
        if machine.r16(0x904B86) != state.games_played_counter & 0xFFFF:
            found.append(f"games: ROM {machine.r16(0x904B86)} PY {state.games_played_counter}")
        if machine.r8(0x904A4A + player) != hero.highscore_rank & 0xFF:
            found.append(f"rank: ROM {machine.r8(0x904A4A + player)} PY {hero.highscore_rank}")
        if found:
            out.append(f"score {hero.score_per_coin:#x}: " + "; ".join(found[:3]))
    return out


def _editor_setup(rng: random.Random) -> tuple:
    """One session's hero and stick script, drawn in the order the serial loop drew them."""
    player = rng.randint(0, 3)
    rank = rng.randint(0, 9)
    score_per_coin = rng.choice((1200, 50000))
    character = rng.randint(0, 3)
    script = []
    for _ in range(40):
        script.append((rng.randint(1, 60), rng.choice((*_STICK, _IDLE, _IDLE))))
        if rng.random() < 0.5:
            script.append((rng.randint(1, 4), rng.choice((_MAGIC_HELD, _FIRE_HELD))))
        script.append((rng.randint(1, 6), _IDLE))
    return player, rank, score_per_coin, character, script


def editor_cases(rng: random.Random, count: int = 60, jobs: int = 1) -> tuple[list[str], int]:
    setups = [_editor_setup(rng) for _ in range(count)]
    if jobs <= 1:
        results = [_editor_session(setup) for setup in setups]
    else:
        with concurrent.futures.ProcessPoolExecutor(jobs) as pool:
            results = list(pool.map(_editor_session, setups))
    return [line for line, _ in results if line], sum(done for _, done in results)


def _editor_session(setup: tuple) -> tuple[str, bool]:
    player, rank, score_per_coin, character, script = setup
    state = GameState(game_mode=GameMode.NORMAL, levelnum_current=8, mazenum_current=20)
    state.attract_timer = 0x5DD
    hero = state.players[player]
    hero.status = int(PlayerStatus.DYING)
    hero.highscore_rank = rank
    hero.score_per_coin = score_per_coin
    hero.character = character
    hero.state_timer = 0xA8C
    hero.name_entry_repeat_delay = 0xA0
    machine = _machine(state, player)
    machine.call(0x452D0, player, count=3_000_000)
    setup_infopanel(state, player)
    frame = 0
    found: list[str] = []
    for frames, raw in script:
        for _ in range(frames):
            if hero.status != PlayerStatus.DYING or found:
                break
            frame += 1
            state.player_input_raw[player] = raw
            # input_debounce (0x40644), fed identically to both sides.
            state.debounce_shift_magic[player] = (
                (state.debounce_shift_magic[player] << 1) | (raw & 1 == 0)) & 0xFF
            state.debounce_shift_fire[player] = (
                (state.debounce_shift_fire[player] << 1) | (raw & 2 == 0)) & 0xFF
            machine.w16(0x904920 + 2 * player, raw)
            machine.w16(0x905F58 + 2 * player, state.debounce_shift_magic[player])
            machine.w16(0x905F60 + 2 * player, state.debounce_shift_fire[player])
            machine.call(0x49DE6, player, count=3_000_000)
            if not machine.halted:
                found = [f"ROM did not return (fault {machine.fault_pc})"]
                break
            player_death_sequence(state, player)
            found = _words(machine, state, player)
    line = f"frame {frame}: " + "; ".join(found[:3]) if found else ""
    return line, hero.status != PlayerStatus.DYING


def main() -> int:
    rng = random.Random(21)
    high = highscore_cases(rng)
    print(f"highscore_check: {len(high)} of 1200 differ")
    print(*high[:5], sep="\n")
    editor, finished = editor_cases(rng, jobs=os.cpu_count() or 1)
    print(f"initials editor: {len(editor)} of 60 differ, {finished} ran to the end")
    print(*editor[:5], sep="\n")
    return 1 if high or editor else 0


if __name__ == "__main__":
    raise SystemExit(main())
