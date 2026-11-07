"""Compare the forcefield and cyclic-wall level setup with the ROM, maze by maze.

    python tools/forcefield_check.py

Level setup calls ``forcefield_segments_setup`` (0x53398) and, on levels with cycling walls,
``maze_forcefield_setup`` (0x52F26). This intercepts each call, runs the ROM routine on a copy
of the exact state gauntpy had at that moment, and compares the results: the segment table at
0x910780, the cycle-code table at 0x910600, the level flags, and every maze record's picture,
position, type and state.
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
from gauntpy.game.subsystems import maze_objects  # noqa: E402


def _records(machine, state: GameState) -> list[str]:
    out = []
    for slot in range(32, 1024):
        rom = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot),
               machine.r16(rom_exec._LINK + 2 * slot) >> 10, machine.r16(rom_exec._STATE + 2 * slot) >> 10)
        py = (state.mobs.picture[slot], state.mobs.hpos[slot], state.mobs.vpos[slot],
              state.mobs.obj_type(slot), state.mobs.state(slot))
        if rom != py:
            out.append(f"record {slot:#x}: ROM {tuple(hex(v) for v in rom)} PY {tuple(hex(v) for v in py)}")
    return out


def check(maze: int, level: int) -> list[str]:
    differences: list[str] = []
    real_segments = maze_objects.forcefield_segments_setup
    real_cycles = maze_objects.maze_forcefield_setup

    def segments(state: GameState) -> None:
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        machine.call(0x53398, count=5_000_000)
        real_segments(state)
        if not machine.halted:
            differences.append(f"segments: ROM did not return (fault {machine.fault_pc})")
            return
        table = []
        for i in range(64):
            word = machine.r16(0x910780 + 2 * i)
            if not word:
                break
            table.append(word)
        if table != list(state.forcefield_segment_table):
            differences.append(f"segment table: ROM {[hex(w) for w in table]} PY "
                               f"{[hex(w) for w in state.forcefield_segment_table]}")
        differences.extend("after segments: " + d for d in _records(machine, state)[:4])

    def cycles(state: GameState) -> None:
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        machine.call(0x52F26, count=5_000_000)
        real_cycles(state)
        rom = list(bytes(machine.cpu.mem_read(0x910600, 256)))
        if rom[8:] != [b & 0xFF for b in state.cyclic_wall_assignments][8:]:
            at = next(i for i in range(8, 256) if rom[i] != state.cyclic_wall_assignments[i])
            differences.append(f"cycle codes [{at}]: ROM {rom[at]:#x} PY {state.cyclic_wall_assignments[at]:#x}")
        if machine.r8(0x90491E) != state.level_flags_3 & 0xFF:
            differences.append(f"level_flags_3: ROM {machine.r8(0x90491E):#x} PY {state.level_flags_3:#x}")
        differences.extend("after cycles: " + d for d in _records(machine, state)[:4])

    maze_objects.forcefield_segments_setup = segments
    maze_objects.maze_forcefield_setup = cycles
    try:
        state = GameState(game_mode=GameMode.NORMAL)
        reset_and_load_level(state, level, maze_number=maze)
    finally:
        maze_objects.forcefield_segments_setup = real_segments
        maze_objects.maze_forcefield_setup = real_cycles
    return differences


def main() -> int:
    failures = 0
    for maze in range(0, 118):
        for level in (7, 13):
            try:
                differences = check(maze, level)
            except Exception as error:  # noqa: BLE001 -- a maze this build cannot load
                print(f"maze {maze} level {level}: not loaded ({error.__class__.__name__})")
                continue
            if differences:
                failures += 1
                print(f"maze {maze} level {level}: " + "; ".join(differences[:3]))
    print("mazes with differences:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
