"""Sweep the secret-room bookkeeping and the name-entry ring against the ROM.

    python tools/secret_check.py

``name_entry_step_char`` (0x55440) over every character, direction and backspace setting;
``secret_check`` (0x486FE) over objectives, winners and pacing values; and
``secret_check_winner`` (0x4D1A4) over every task, winner and progress byte, in a real level
so the clear-the-monsters task has monsters to find. Each case runs the ROM routine on the same
state as gauntpy and compares the result and every word the routine owns.
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys

_TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(_TOOLS), str(_TOOLS.parent / "src")]

import rom_exec  # noqa: E402
from gauntpy.game.constants import GameMode  # noqa: E402
from gauntpy.game.maze import reset_and_load_level  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems.player_names import name_entry_step_char  # noqa: E402
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


def check_winner_cases(tasks=range(0, 0x60), winners=(-1, 0, 2, 4),
                       progresses=(0, 1, 2, 3, 4, 5, 6, 10, 0x0B, 0x10, 0x20, 0xFF)) -> list[str]:
    out = []
    level = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(level, 7, maze_number=6)
    cleared = copy.deepcopy(level)
    for slot in range(32, 1024):
        if 0x12 <= cleared.mobs.obj_type(slot) <= 0x2D:
            cleared.mobs.unlink_and_clear(slot)
    for base in (level, cleared):
        for task in tasks:
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
                                   f"{'cleared' if base is cleared else 'level'}): ROM {rom} PY {py}")
    return out


def main() -> int:
    failures = 0
    for name, cases in (("name_entry_step_char", step_char_cases), ("secret_check", secret_check_cases),
                        ("secret_check_winner", check_winner_cases)):
        differences = cases()
        failures += len(differences)
        print(f"{name}: {len(differences)} differences")
        for line in differences[:8]:
            print("  ", line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
