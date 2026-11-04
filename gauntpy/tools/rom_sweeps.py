"""Sweep every object type through gauntpy and the ROM (tools/rom_exec.py).

    python tools/rom_sweeps.py walk    # walk a hero into each type, in four directions
    python tools/rom_sweeps.py scan    # run the transporter arrival scan on each type

``walk`` steps one continuous ROM run against gauntpy's movement and occupied-cell tail,
comparing the result word, position, keys and how often player_tile_interact runs.
``scan`` forces each type to overlap a landed hero and reports records that survive or
an instruction limit, which would be a hang.

A difference is a lead, not a verdict: fixtures here are not real maze states, and a fault
usually means RAM the snapshot lacks. Hand-traced conclusions live in doc/04 §7.2.
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
import sys

_TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(_TOOLS), str(_TOOLS.parent / "src")]

import rom_exec  # noqa: E402
from gauntpy.game.constants import GameMode, MazeObjIds, PlayerStatus  # noqa: E402
from gauntpy.game.coords import native_v  # noqa: E402
from gauntpy.game.maze import maze_place_object  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import input as gin  # noqa: E402
from gauntpy.game.subsystems import player_items  # noqa: E402
from gauntpy.game.subsystems import player_movement as pm  # noqa: E402
from gauntpy.game.subsystems.player_transport import scan_move_path_interactions  # noqa: E402

_NEIGHBOUR = {
    gin.JOY_RIGHT: (10 << 5) | 10, gin.JOY_LEFT: (10 << 5) | 8,
    gin.JOY_UP: (9 << 5) | 9, gin.JOY_DOWN: (11 << 5) | 9,
}


def _name(obj_type: int) -> str:
    try:
        return MazeObjIds(obj_type).name
    except ValueError:
        return hex(obj_type)


def _state_with_hero(slot: int, *, keys: int = 0, powers: int = 0) -> GameState:
    state = GameState(game_mode=GameMode.NORMAL)
    player = state.players[0]
    player.status = PlayerStatus.ALIVE_HERE
    player.mob_slot = slot
    player.health = 500
    player.keysnum = keys
    player.powers = powers
    player.coin_count = 1
    state.level_players_active = 1
    state.level_flags_4 |= 0x80
    state.movement_type = 2
    state.mobs.create(
        slot, tile=0x1E0D, hpos=(((slot & 0x1F) * 16 - 4) << 7) | 0x0C,
        vpos=native_v((slot >> 5) * 16) << 7,
        obj_type=int(MazeObjIds.PLAYERSTART), state=0,
    )
    state.player_tile_or_tport_dest[0] = slot
    return state


def _walk(obj_type: int, keys: int, delta: int, steps: int = 24):
    state = _state_with_hero((10 << 5) | 9, keys=keys)
    target = _NEIGHBOUR[delta]
    maze_place_object(state, target, obj_type, 1)
    if not state.mobs.picture[target]:
        return None
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    rom_calls = machine.count_calls(0x511AC)
    our_calls = [0]
    original = player_items.player_tile_interact

    def counted(*args):
        our_calls[0] += 1
        return original(*args)

    player_items.player_tile_interact = counted
    player = state.players[0]
    try:
        for step in range(steps):
            result = rom_exec.player_try_move(machine, state, 0, delta)
            if not machine.halted:
                return f"ROM stopped at step {step}, fault {machine.fault_pc}"
            slot = machine.player_slot(0)
            rom = (result, slot, machine.hpos(slot) & ~0xF, machine.vpos(slot),
                   machine.keys(0), rom_calls[0])
            state.movement_type = 2
            origin = (player.mob_slot, state.mobs.hpos[player.mob_slot],
                      state.mobs.vpos[player.mob_slot])
            moved = pm.player_try_move(state, 0, delta, 0, track_thief=False)
            _, refused = pm.resolve_entered_cell(state, 0, origin)
            slot = player.mob_slot
            ours = (0xF0 if refused else moved & 0xFFFF, slot, state.mobs.hpos[slot] & ~0xF,
                    state.mobs.vpos[slot], player.keysnum, our_calls[0])
            if rom != ours:
                return f"differs at step {step}: ROM {[hex(x) for x in rom]} gauntpy {[hex(x) for x in ours]}"
    finally:
        player_items.player_tile_interact = original
    return "same"


def walk() -> None:
    for name, delta in (("right", gin.JOY_RIGHT), ("left", gin.JOY_LEFT),
                        ("up", gin.JOY_UP), ("down", gin.JOY_DOWN)):
        for keys in (0, 3):
            same = 0
            print(f"--- {name}, keys={keys}")
            for obj_type in range(1, 0x40):
                outcome = _walk(obj_type, keys, delta)
                if outcome == "same":
                    same += 1
                elif outcome is not None:
                    print(f"  {_name(obj_type)}: {outcome}")
            print(f"  {same} types the same")


def scan() -> None:
    hero = (10 << 5) | 10
    left = (10 << 5) | 9
    # The exit path needs tables the snapshot lacks; a hidden potion needs a real picture.
    rom_skipped = {0x10, 0x11, 0x3D}
    for keys, powers in ((0, 0), (1, 0), (12, 0), (0, 0xFFFF)):
        limit, faults, rom_survived, our_survived = [], [], [], []
        for obj_type in range(1, 0x40):
            state = _state_with_hero(hero, keys=keys, powers=powers)
            state.mobs.create(left, tile=0x0AFC, hpos=(9 * 16) << 7,
                              vpos=native_v(10 * 16) << 7, obj_type=obj_type)
            if obj_type not in rom_skipped:
                machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
                machine.call(0x50BB8, 0x4083A, hero, 0, count=1_500_000)
                if machine.fault_pc is not None:
                    faults.append((_name(obj_type), hex(machine.fault_pc)))
                elif not machine.halted:
                    limit.append(_name(obj_type))
                elif machine.picture(left):
                    rom_survived.append(_name(obj_type))
            scan_move_path_interactions(state, hero, 0)
            if state.mobs.picture[left]:
                our_survived.append(_name(obj_type))
        print(f"keys={keys} powers={powers:#x}")
        print("  ROM instruction limit:", limit)
        print("  ROM faults:", faults)
        print("  ROM record survived:", rom_survived)
        print("  gauntpy record survived:", our_survived)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sweep", choices=("walk", "scan"))
    {"walk": walk, "scan": scan}[parser.parse_args().sweep]()


if __name__ == "__main__":
    main()
