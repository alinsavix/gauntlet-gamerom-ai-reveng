"""Sweep the secret-room bookkeeping and the name-entry ring against the ROM.

    python tools/secret_check.py

``name_entry_step_char`` (0x55440) over every character, direction and backspace setting;
``secret_check`` (0x486FE) over objectives, winners and pacing values; and
``secret_check_winner`` (0x4D1A4) over every task, winner and progress byte, in a real level
so the clear-the-monsters task has monsters to find. Each case runs the ROM routine on the same
state as gauntpy and compares the result and every word the routine owns.
"""

from __future__ import annotations

import concurrent.futures

import copy
from pathlib import Path
import sys

_TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(_TOOLS), str(_TOOLS.parent / "src")]

import rom_exec  # noqa: E402
from jobs import default_jobs  # noqa: E402
from gauntpy.game.constants import GameMode  # noqa: E402
from gauntpy.game.maze import reset_and_load_level  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems.player_names import name_entry_step_char, secret_code_for  # noqa: E402
from gauntpy.game.subsystems.secret_rooms import secret_check, secret_check_winner  # noqa: E402


def _signed32(value: int) -> int:
    return value - (1 << 32) if value & 0x80000000 else value


def step_char_cases() -> list[str]:
    out = []
    machine = rom_exec.RomMachine()
    for current in range(0x00, 0x80):
        for direction in (-1, 1):
            for allow in (0, 1):
                rom = machine.call(0x55440, current, direction & 0xFFFFFFFF, allow) & 0xFF
                py = name_entry_step_char(current, direction, bool(allow)) & 0xFF
                if rom != py:
                    out.append(f"step_char({current:#x}, {direction}, {allow}): ROM {rom:#x} PY {py:#x}")
    return out


def _load_secret_words(machine, state: GameState) -> None:
    machine.w8(0x904063, state.secret_player)
    machine.w8(0x904065, state.secret_trick_id)
    machine.w16(0x904870, state.secret_prev_maze)
    machine.w16(0x904878, state.secret_possible_counter)
    machine.w16(0x90487A, state.secret_possible_start)
    machine.w16(0x904000, state.mazenum_current)
    for i, flag in enumerate(state.secret_tricks_flags):
        machine.w8(0x904872 + i, flag)


def secret_check_cases() -> list[str]:
    out = []
    for trick in (0, 1, 5, 9, 0x10):
        for winner in (-1, 0, 3):
            for start in (2, 4, 5, 6, 20, 25, 26, 40, 41):
                state = GameState(game_mode=GameMode.NORMAL)
                state.mazenum_current = 37
                state.secret_trick_id = trick
                state.secret_player = winner
                state.secret_possible_start = start
                state.secret_possible_counter = 3
                machine = rom_exec.RomMachine.from_state(state)
                _load_secret_words(machine, state)
                machine.call(0x486FE)
                secret_check(state)
                rom = (machine.r16(0x904870), machine.r16(0x904878), machine.r16(0x90487A))
                py = (state.secret_prev_maze, state.secret_possible_counter, state.secret_possible_start)
                if rom != py:
                    out.append(f"secret_check(trick {trick}, winner {winner}, start {start}): ROM {rom} PY {py}")
    return out


_WINNER_BASES: list[GameState] = []


def _winner_bases() -> list[GameState]:
    """Level 7 on maze 6, and the same level with its monsters and generators gone."""
    if not _WINNER_BASES:
        level = GameState(game_mode=GameMode.NORMAL)
        reset_and_load_level(level, 7, maze_number=6)
        cleared = copy.deepcopy(level)
        for slot in range(32, 1024):
            if 0x12 <= cleared.mobs.obj_type(slot) <= 0x2D:
                cleared.mobs.unlink_and_clear(slot)
        _WINNER_BASES.extend((level, cleared))
    return _WINNER_BASES


def _check_winner_task(job: tuple) -> list[str]:
    cleared, task, winners, progresses = job
    base = _winner_bases()[cleared]
    out = []
    for winner in winners:
        for progress in progresses:
            state = copy.deepcopy(base)
            state.secret_trick_id = task
            state.secret_player = winner
            if 0 <= winner < 4:
                state.secret_tricks_flags[winner] = progress
            machine = rom_exec.RomMachine.from_state(state)
            _load_secret_words(machine, state)
            rom = _signed32(machine.call(0x4D1A4))
            py = -1 if secret_check_winner(state) else 0
            if rom != py:
                out.append(f"check_winner(task {task:#x}, winner {winner}, progress {progress:#x}, "
                           f"{'cleared' if cleared else 'level'}): ROM {rom} PY {py}")
    return out


def check_winner_cases(tasks=range(0, 0x60), winners=(-1, 0, 2, 4),
                       progresses=(0, 1, 2, 3, 4, 5, 6, 10, 0x0B, 0x10, 0x20, 0xFF),
                       jobs: int = 1) -> list[str]:
    work = [(cleared, task, tuple(winners), tuple(progresses)) for cleared in (0, 1) for task in tasks]
    if jobs <= 1:
        return [line for job in work for line in _check_winner_task(job)]
    with concurrent.futures.ProcessPoolExecutor(jobs) as pool:
        return [line for lines in pool.map(_check_winner_task, work, chunksize=4) for line in lines]


def secret_code_cases(count: int = 3000) -> list[str]:
    """``secret_code_build`` (0x54BE0) on random names and contest fields."""
    import random

    rng = random.Random(0x5EC)
    out = []
    machine = rom_exec.RomMachine()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ    "
    for _ in range(count):
        length = rng.randint(0, 29)
        name = "".join(rng.choice(alphabet) for _ in range(length))
        maze = rng.randint(0, 117)
        previous_trick = rng.randint(0, 15)
        challenge = rng.choice([0, *range(0x50, 0x5E)])
        machine.cpu.mem_write(0x904AA4, name.encode("ascii") + b"\0" * 4)
        machine.w8(0x904064, previous_trick)
        machine.w8(0x904065, challenge)
        machine.w16(0x904870, maze)
        machine.call(0x54BE0)
        rom = bytes(machine.cpu.mem_read(0x904AA4, 7)).decode("ascii", "replace")
        py = secret_code_for(name, maze, previous_trick, challenge)
        if rom != py:
            out.append(f"secret_code({name!r}, {maze}, {previous_trick}, {challenge:#x}): ROM {rom} PY {py}")
    return out


# ROM addresses of the secret winner's editor fields, per player.
_CURSOR, _VELOCITY, _DELAY, _STATUS = 0x904A3A, 0x904A2E, 0x904A36, 0x9049A0
_TIMER, _BUFFER, _MAGIC, _FIRE, _RAW = 0x904A4E, 0x904AA4, 0x905F58, 0x905F60, 0x904920

_SCRIPT = (                       # (frames, raw word): active low; dirs in bits 4-7
    (130, 0xFFFF), (40, 0xFFEF), (3, 0xFFFD), (10, 0xFFFF), (25, 0xFFDF), (3, 0xFFFD),
    (6, 0xFFFF), (60, 0xFFBF), (3, 0xFFFE), (8, 0xFFFF), (90, 0xFF7F), (3, 0xFFFD),
    (20, 0xFFFF), (12, 0xFFEF), (3, 0xFFFD), (4, 0xFFFF), (200, 0xFFDF), (3, 0xFFFE),
    (1100, 0xFFFF),               # idle until the timer ends the entry and shows the code
)


def _editor_words(machine, state: GameState, winner: int) -> list[str]:
    player = state.players[winner]
    pairs = (
        ("cursor", machine.r8(_CURSOR + 4 * winner), player.initials_cursor & 0xFF),
        ("velocity", machine.r16(_VELOCITY + 2 * winner), player.name_entry_velocity & 0xFFFF),
        ("repeat delay", machine.r8(_DELAY + winner), player.name_entry_repeat_delay & 0xFF),
        ("status", machine.r8(_STATUS + winner), int(player.status) & 0xFF),
        ("global_delay_timer", machine.r16(_TIMER), state.global_delay_timer & 0xFFFF),
        ("secret_player", machine.r8(0x904063), state.secret_player & 0xFF),
    )
    out = [f"{name}: ROM {rom:#x} PY {py:#x}" for name, rom, py in pairs if rom != py]
    rom_buffer = list(bytes(machine.cpu.mem_read(_BUFFER, 29)))
    if rom_buffer != [b & 0xFF for b in state.secret_name_buffer[:29]]:
        out.append(f"buffer: ROM {bytes(rom_buffer)!r} PY {bytes(state.secret_name_buffer[:29])!r}")
    alpha = [machine.r16(0x905000 + 2 * i) for i in range(64 * 30)]
    bad = [i for i in range(64 * 30) if (i % 64) < 42 and alpha[i] != state.alpha_ram[i]]
    if bad:
        i = bad[0]
        out.append(f"alpha ({i % 64},{i // 64}): ROM {alpha[i]:#x} PY {state.alpha_ram[i]:#x} ({len(bad)} cells)")
    return out


def name_entry_cases(winners=(0, 2), settings=(0x2000, 0)) -> list[str]:
    """``secret_getname`` (0x54EC6), then ``secret_name_entry_update`` (0x54FE8) each frame."""
    from gauntpy.game.constants import PlayerStatus
    from gauntpy.game.subsystems.player_names import secret_getname, secret_name_entry_update

    out = []
    finishes = 0
    for winner in winners:
        for setting in settings:
            state = GameState(game_mode=GameMode.NORMAL)
            state.game_settings = setting
            state.secret_player = winner
            state.secret_prev_maze, state.secret_trick_last, state.secret_trick_id = 37, 5, 0x54
            player = state.players[winner]
            player.status = PlayerStatus.ALIVE_NEXT
            machine = rom_exec.RomMachine.from_state(state)
            _load_secret_words(machine, state)
            machine.w8(0x904064, state.secret_trick_last)
            machine.w16(_TIMER, state.global_delay_timer)
            machine.cpu.mem_write(_BUFFER, bytes(b & 0xFF for b in state.secret_name_buffer))
            machine.call(0x54EC6, count=2_000_000)
            secret_getname(state)
            label = f"winner {winner} settings {setting:#x}"
            differences = _editor_words(machine, state, winner)
            if differences:
                out.append(f"{label} after secret_getname: " + "; ".join(differences[:3]))
                continue
            frame = 0
            for frames, raw in _SCRIPT:
                for _ in range(frames):
                    frame += 1
                    if state.secret_player != winner:
                        break
                    # input_debounce (0x40644), fed identically to both sides.
                    state.player_input_raw[winner] = raw
                    state.debounce_shift_magic[winner] = ((state.debounce_shift_magic[winner] << 1) | (raw & 1)) & 0xFFFF
                    state.debounce_shift_fire[winner] = ((state.debounce_shift_fire[winner] << 1) | ((raw >> 1) & 1)) & 0xFFFF
                    machine.w16(_RAW + 2 * winner, raw)
                    machine.w16(_MAGIC + 2 * winner, state.debounce_shift_magic[winner])
                    machine.w16(_FIRE + 2 * winner, state.debounce_shift_fire[winner])
                    if state.global_delay_timer:
                        state.global_delay_timer -= 1
                    machine.w16(_TIMER, state.global_delay_timer)
                    machine.call(0x54FE8, count=2_000_000)
                    if not machine.halted:
                        out.append(f"{label} frame {frame}: ROM did not return (fault {machine.fault_pc})")
                        break
                    secret_name_entry_update(state)
                    finished = state.secret_player != winner
                    differences = _editor_words(machine, state, winner)
                    if differences:
                        out.append(f"{label} frame {frame}: " + "; ".join(differences[:3]))
                        break
                    if finished:
                        finishes += 1
                else:
                    continue
                break
    name_entry_cases.finishes = finishes
    return out


_GROUPS = (("name_entry_step_char", step_char_cases), ("secret_check", secret_check_cases),
           ("secret_check_winner", check_winner_cases), ("secret_code_build", secret_code_cases),
           ("secret name entry", name_entry_cases))


def main() -> int:
    failures = 0
    # check_winner shares its cases between workers; the other four are quick.
    results = [
        cases(jobs=default_jobs()) if cases is check_winner_cases else cases()
        for _, cases in _GROUPS
    ]
    for (name, _), differences in zip(_GROUPS, results):
        failures += len(differences)
        print(f"{name}: {len(differences)} differences")
        for line in differences[:8]:
            print("  ", line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
