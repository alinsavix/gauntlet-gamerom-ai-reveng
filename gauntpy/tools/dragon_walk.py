"""Run a dragon in a real level in gauntpy and in the ROM, frame by frame.

    python tools/dragon_walk.py                 # a sweep over the dragon mazes and scenarios
    python tools/dragon_walk.py --maze 13 --scenario hits --show

Dragons are placed from level 12 on (0x45E6A), so the level is 13. A hero steps into the
dragon's wake box, which ``dragon_player_proximity`` (0x549EA) reports on both sides, and then
moves around it so the head has someone new to face. Each frame runs ``main_handle_dragon``
(0x54454) on both sides and compares every dragon word, its four segment records, the fireball
channels it fills, and the RNG seed. The ROM machine keeps its own RAM throughout; only the
scenario's own events are written to both sides.

Scenarios: ``wake``, the hero arrives and wanders; ``leave``, the hero also leaves the box
again, which reverses the wake; ``hits``, a shot lands on the dragon every 40 frames until the
ninth kills it (``dragon_shot_hit``, 0x54112); ``stun``, a hit while the hero is away.

The run stops at the first difference. A difference is a lead, not a verdict: the RAM here
is what ``rom_exec.load_state`` copies.
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
from gauntpy.game.maze import reset_and_load_level  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems.camera import scroll_to_slot  # noqa: E402
from gauntpy.game.subsystems import dragon  # noqa: E402
from gauntpy.game.subsystems.shot_damage import dragon_player_proximity  # noqa: E402
from gauntpy.game.subsystems.shots import main_handle_shots  # noqa: E402

MAZES = (13, 41, 67, 78)
SCENARIOS = ("wake", "leave", "hits", "stun")

_WORDS = {
    "dragon_fire_cooldown": 0x90487C, "dragon_hits": 0x904880, "dragon_head_hpos": 0x904882,
    "dragon_head_vpos": 0x904884, "dragon_path_num": 0x904886, "dragon_move_state": 0x90488C,
    "dragon_facing": 0x90488E, "dragon_state": 0x904890, "dragon_anim_ctr": 0x904892,
}


def _free_cells(state: GameState, centre: int, radius: int) -> list[int]:
    """Empty cells within ``radius`` rows and columns of ``centre``, nearest first."""
    out = []
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            row, col = (centre >> 5) + dr, (centre & 0x1F) + dc
            if 2 <= row < 31 and 0 <= col < 32:
                cell = (row << 5) | col
                if not state.mobs.picture[cell]:
                    out.append((abs(dr) + abs(dc), cell))
    return [cell for _, cell in sorted(out)]


def setup(maze: int) -> GameState | None:
    state = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(state, 13, maze_number=maze)
    if not state.dragon_seg_mob_ids[0]:
        return None
    hero = state.players[0]
    hero.status = PlayerStatus.ALIVE_HERE
    hero.health, hero.coin_count = 2000, 1
    state.level_players_active = 1
    state.rng.seed = 0x1234
    return state


def _place_hero(state: GameState, machine, cell: int) -> None:
    hero = state.players[0]
    old = hero.mob_slot
    if old:
        state.mobs.unlink_and_clear(old)
    state.mobs.create(
        cell, tile=0x1E0D, hpos=((((cell & 0x1F) * 16 - 4) << 7) | 0x0C) & 0xFFFF,
        vpos=(native_v((cell >> 5) * 16) << 7) & 0xFFFF, obj_type=int(MazeObjIds.PLAYERSTART), state=0,
    )
    hero.mob_slot = cell
    scroll_to_slot(state, cell)
    for slot in (old, cell):
        if slot:
            machine.w16(rom_exec._PICTURE + 2 * slot, state.mobs.picture[slot])
            machine.w16(rom_exec._HPOS + 2 * slot, state.mobs.hpos[slot])
            machine.w16(rom_exec._VPOS + 2 * slot, state.mobs.vpos[slot])
            machine.w16(rom_exec._LINK + 2 * slot, state.mobs.link[slot])
            machine.w16(rom_exec._STATE + 2 * slot, state.mobs.state_link[slot])
    machine.w16(0x9048C8, cell)
    machine.w16(0x904008, state.scroll_x)
    machine.w16(0x90400A, state.scroll_y)
    machine.w16(0x904AC2, ((state.scroll_x - 8) << 7) & 0xFFFF)
    machine.w16(0x904AC4, ((0x108 - state.scroll_y) << 7) & 0xFFFF)


def _move_hero(state: GameState, machine, cell: int) -> None:
    """The hero moves to ``cell``; both sides hear of it as the movement tail reports it."""
    previous = state.players[0].mob_slot
    _place_hero(state, machine, cell)
    machine.call(0x549EA, previous, cell)          # (previous, current), as 0x512AC pushes them
    dragon_player_proximity(state, cell, previous)


def compare(machine, state: GameState, cells=()) -> list[str]:
    """``cells``: extra records to compare, such as where a dying dragon drops its loot."""
    out = []
    for name, address in (("secret_need_hint", 0x90486E), ("special_bonus_score", 0x904B56)):
        rom, py = machine.r16(address), getattr(state, name) & 0xFFFF
        if rom != py:
            out.append(f"{name}: ROM {rom:#x} PY {py:#x}")
    for slot in cells:
        rom = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot),
               machine.r16(rom_exec._LINK + 2 * slot) >> 10)
        py = (state.mobs.picture[slot], state.mobs.hpos[slot], state.mobs.vpos[slot],
              state.mobs.obj_type(slot))
        if rom != py:
            out.append(f"cell {slot:#x}: ROM {tuple(hex(v) for v in rom)} PY {tuple(hex(v) for v in py)}")
    for name, address in _WORDS.items():
        rom, py = machine.r16(address), getattr(state, name) & 0xFFFF
        if rom != py:
            out.append(f"{name}: ROM {rom:#x} PY {py:#x}")
    segments = [machine.r16(0x904894 + 2 * i) for i in range(4)]
    if segments != list(state.dragon_seg_mob_ids):
        out.append(f"segments: ROM {[hex(s) for s in segments]} PY {[hex(s) for s in state.dragon_seg_mob_ids]}")
    # Link fields are not compared: the depth chain's tables at 0x905F80 are not
    # loaded, so the ROM threads a new record differently.
    for slot in set(segments) | set(state.dragon_seg_mob_ids) | set(range(5, 9)):
        if not slot:
            continue
        rom = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot),
               machine.r16(rom_exec._LINK + 2 * slot) >> 10, machine.r16(rom_exec._STATE + 2 * slot) >> 10)
        py = (state.mobs.picture[slot], state.mobs.hpos[slot], state.mobs.vpos[slot],
              state.mobs.obj_type(slot), state.mobs.state(slot))
        if rom != py:
            out.append(f"record {slot:#x}: ROM {tuple(hex(v) for v in rom)} PY {tuple(hex(v) for v in py)}")
    for channel in range(4, 8):
        rom, py = machine.r16(0x9049C4 + 2 * channel), state.shot_direction[channel] & 0xFFFF
        if rom != py:
            out.append(f"shot_direction[{channel}]: ROM {rom:#x} PY {py:#x}")
    for channel in range(4, 8):
        rom, py = machine.r16(0x904B02 + 2 * channel), state.shot_anim_lifetime_counter[channel] & 0xFFFF
        if rom != py:
            out.append(f"shot counter[{channel}]: ROM {rom:#x} PY {py:#x}")
    rom_health = int.from_bytes(bytes(machine.cpu.mem_read(0x904980, 4)), "big", signed=True)
    if rom_health != state.players[0].health:
        out.append(f"health: ROM {rom_health} PY {state.players[0].health}")
    if machine.r16(0x904BFC) != state.rng.seed:
        out.append(f"seed: ROM {machine.r16(0x904BFC):#x} PY {state.rng.seed:#x}")
    return out


def walk(state: GameState, scenario: str, frames: int = 1500, show: bool = False,
         shots_too: bool = True):
    """``(frames compared, first differences, how the run ended)``."""
    head = state.dragon_seg_mob_ids[0]
    near = _free_cells(state, head, 3)
    far = [cell for cell in _free_cells(state, head, 9) if cell not in _free_cells(state, head, 6)]
    if len(near) < 4 or not far:
        return 0, [], "no room"
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    _place_hero(state, machine, far[0])
    hits = 0
    last_hit = -100
    around: list[int] = []
    for frame in range(1, frames + 1):
        state.frame_counter = (state.frame_counter + 1) & 0xFFFF
        machine.w16(0x904006, state.frame_counter)
        if frame == 2:
            _move_hero(state, machine, near[0])
        elif frame > 2 and frame % 60 == 0:
            if scenario == "leave" and frame % 120 == 0:
                _move_hero(state, machine, far[(frame // 120) % len(far)])
            elif scenario != "stun":
                _move_hero(state, machine, near[(frame // 60) % len(near)])
        if (scenario == "hits" and state.dragon_seg_mob_ids[0] and frame - last_hit >= 40
                and not state.dragon_state & 0x05 and dragon._current_path_byte(state) & 1):
            # A player shot reaches the head as 0x400 plus its slot (0x4B3B4); it
            # counts only with the mouth open and no transition running (0x54112).
            target = 0x400 | state.dragon_seg_mob_ids[0]
            around = _free_cells(state, state.dragon_seg_mob_ids[0], 2) + list(state.dragon_seg_mob_ids)
            machine.call(0x54112, target, 0, count=2_000_000)
            dragon.dragon_shot_hit(state, target, 0)
            last_hit = frame
            hits += 1
        if scenario == "stun" and frame == 200:
            _move_hero(state, machine, far[0])
        if scenario == "stun" and frame == 210:
            machine.call(0x54112, state.dragon_seg_mob_ids[0], 0, count=2_000_000)
            dragon.dragon_shot_hit(state, state.dragon_seg_mob_ids[0], 0)
        if scenario == "stun" and frame == 400:
            _move_hero(state, machine, near[1])
        if shots_too:
            # main_handle_shots (0x474F6) runs before the dragon in the main loop.
            machine.call(0x474F6, count=2_000_000)
            if not machine.halted:
                return frame, [f"ROM did not return from main_handle_shots (fault {machine.fault_pc})"], "fault"
            main_handle_shots(state)
        machine.call(0x54454, count=2_000_000)
        if not machine.halted:
            return frame, [f"ROM did not return from main_handle_dragon (fault {machine.fault_pc})"], "fault"
        dragon.main_handle_dragon(state)
        differences = compare(machine, state, around)
        if show and frame % 100 == 0:
            print(frame, hex(state.dragon_state), state.dragon_anim_ctr, state.dragon_hits)
        if differences:
            return frame, differences, "differs"
        if scenario == "hits" and not state.dragon_seg_mob_ids[0]:
            return frame, [], f"killed after {hits} hits"
    return frames, [], "time"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--maze", type=int, action="append")
    parser.add_argument("--scenario", choices=SCENARIOS, action="append")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    failures = 0
    endings: dict[str, int] = {}
    for scenario in args.scenario or SCENARIOS:
        for maze in args.maze or MAZES:
            for seed in (0x1234, 0xBEEF, 0x0F0F):
                state = setup(maze)
                if state is None:
                    print(f"maze {maze}: no dragon")
                    continue
                state.rng.seed = seed
                frames, differences, end = walk(state, scenario, show=args.show)
                endings[f"{scenario}/{end}"] = endings.get(f"{scenario}/{end}", 0) + 1
                if differences:
                    failures += 1
                    print(f"{scenario} maze {maze} seed {seed:#x}: frame {frames}: {'; '.join(differences)}")
    print("endings:", dict(sorted(endings.items())))
    print("runs with differences:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
