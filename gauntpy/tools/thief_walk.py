"""Walk a thief through a real level in gauntpy and in the ROM, frame by frame.

    python tools/thief_walk.py                 # a sweep over mazes, routes and scenarios
    python tools/thief_walk.py --maze 13 --scenario shot --show

A hero walks a route across the maze first, so its moves write the trail exactly as
``thief_track_victim_move`` does. The thief arrives at the route's start, follows the trail,
steals, and runs back. Each frame runs ``main_thief_anim`` and ``main_start_thief`` on both
sides (0x4E8DC, 0x4DEB8), in the main loop's order, and compares the thief's RAM, its record,
the route grid, the hero's health and potions, and the RNG seed. The ROM machine keeps its own
RAM throughout; only the scenario's own changes are written to both sides.

Scenarios: ``plain``; ``monster``, a ghost standing on the route; ``shot``, a hero's arrow
held on the thief's ray for 40 frames, which starts and ends a dodge; ``moving``, a hero who
keeps walking away, reported through ``thief_track_victim_move`` (0x4E630) on both sides;
``block``, the hero steps onto the escape route after the theft, so the thief fights its way
past (0x4F788-0x4F866); ``tport``, the trail goes through a transporter pair, recorded with
``tport_route_connect`` (0x4E684) as a hero's transport does, so the thief takes it too.

The run stops at the first difference, because everything after it is contaminated. While a
thief transition is in flight, main_score_update (0x4715E), which drives it, runs on both sides
too. A difference is a lead, not a verdict: the RAM here is what
``rom_exec.load_state`` copies.
"""

from __future__ import annotations

import argparse
from collections import deque
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
from gauntpy.game.subsystems import score, thief  # noqa: E402

SCENARIOS = ("plain", "monster", "shot", "moving", "block", "tport")
_STEPS = (-1, 1, -0x20, 0x20)
_COLUMN_STEP = (0, 1, 1, 1, 0, -1, -1, -1)
_ROW_STEP = (-1, -1, 0, 1, 1, 1, 0, -1)
_ARROW = 0x0A00
_GHOST = 0x2000


def route(state: GameState, start: int, length: int, avoid: frozenset = frozenset()) -> list[int]:
    """A shortest walk over empty cells from ``start`` to a cell ``length`` steps away."""
    previous = {start: None}
    depth = {start: 0}
    queue = deque([start])
    far = start
    while queue:
        cell = queue.popleft()
        far = cell
        if depth[cell] >= length:
            break
        for step in _STEPS:
            nxt = cell + step
            if not 0x40 <= nxt < 0x3E0 or nxt in previous or nxt in avoid:
                continue
            if step in (-1, 1) and (nxt >> 5) != (cell >> 5):
                continue
            if state.mobs.picture[nxt]:
                continue
            previous[nxt] = cell
            depth[nxt] = depth[cell] + 1
            queue.append(nxt)
    path = [far]
    while previous[path[-1]] is not None:
        path.append(previous[path[-1]])
    return path[::-1]


def _tport_trail(state: GameState, start: int, length: int):
    """A walk to a transporter pad, a jump to another pad's free neighbour, and on from there."""
    pads = [slot for slot in range(0x20, 0x400) if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)]
    if len(pads) < 2:
        return None
    for source in pads:
        for step in _STEPS:
            approach = source - step
            if not 0x40 <= approach < 0x3E0 or state.mobs.picture[approach]:
                continue
            path = route(state, start, 40)
            if approach not in path:
                lead = _route_to(state, start, approach)
                if lead is None:
                    continue
            else:
                lead = path[:path.index(approach) + 1]
            for destination in pads:
                if destination == source:
                    continue
                for out in _STEPS:
                    landing = destination + out
                    if 0x40 <= landing < 0x3E0 and not state.mobs.picture[landing]:
                        tail = route(state, landing, length, avoid=frozenset(lead))
                        if len(tail) > 3:
                            return lead + [(source, destination, landing)] + tail[1:]
    return None


def _route_to(state: GameState, start: int, goal: int):
    previous = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = [cell]
            while previous[path[-1]] is not None:
                path.append(previous[path[-1]])
            return path[::-1]
        for step in _STEPS:
            nxt = cell + step
            if not 0x40 <= nxt < 0x3E0 or nxt in previous or state.mobs.picture[nxt]:
                continue
            if step in (-1, 1) and (nxt >> 5) != (cell >> 5):
                continue
            previous[nxt] = cell
            queue.append(nxt)
    return None


def _record(state: GameState, slot: int, picture: int, obj_type: int, state_word: int = 0,
            palette: int = 0) -> None:
    state.mobs.create(
        slot, tile=picture, hpos=(((slot & 0x1F) * 16 - 4) << 7) | palette,
        vpos=native_v((slot >> 5) * 16) << 7, obj_type=obj_type, state=state_word,
    )


def setup(maze: int, start: int, length: int, mugger: bool, scenario: str = "plain"):
    """``(state, onward route)``, or None when the maze has no room for it."""
    state = GameState(game_mode=GameMode.NORMAL)
    reset_and_load_level(state, 7, maze_number=maze)
    if state.mobs.picture[start]:
        return None
    if scenario == "tport":
        path = _tport_trail(state, start, length)
        if path is None:
            return None
    else:
        path = route(state, start, length)
    if len(path) < 4:
        return None
    hero = state.players[0]
    hero.status = PlayerStatus.ALIVE_HERE
    hero.health, hero.coin_count, hero.potionsnum, hero.bonusmult = 900, 1, 2, 1
    state.level_players_active = 1
    state.thief_victim = 0
    state.thief_victim_pos = path[0]
    for cell in path[1:]:
        if isinstance(cell, tuple):                  # a transport: (source pad, destination pad, landing)
            source, destination, landing = cell
            thief.thief_track_victim_move(state, source, 0)
            thief.tport_route_connect(state, source, destination, landing)
            state.thief_victim_pos = landing
            continue
        thief.thief_track_victim_move(state, cell, 0)
    path = [cell[2] if isinstance(cell, tuple) else cell for cell in path]
    end = path[-1]
    hero.mob_slot = end
    _record(state, end, 0x1E0D, int(MazeObjIds.PLAYERSTART), 0, palette=0x0C)
    onward = route(state, end, 12, avoid=frozenset(path))[1:] if scenario == "moving" else []
    if scenario == "block":
        onward = list(path)
    if scenario == "monster":
        _record(state, path[len(path) // 2], _GHOST, int(MazeObjIds.MONST_GHOST))
    scroll_to_slot(state, end)
    state.thief_start_location = path[0]
    # thief_timer_set (0x4E4D8) leaves a scheduled visitor in pursuit.
    state.thief_mode = thief.THIEF_PURSUE | (thief.THIEF_IS_MUGGER if mugger else 0)
    state.thief_speed = thief._SPEED_MUGGER if mugger else thief._SPEED_THIEF
    state.thief_enter_time = 1
    state.thief_level_setup_done = True      # as main_start_game's 0x4835E tail leaves it
    state.rng.seed = 0x1234
    return state, onward


_WORDS = {
    "thief_mode": 0x904BA0, "thief_previous_pos": 0x904BA2, "thief_current_pos": 0x904BA4,
    "thief_next_pos": 0x904BA6, "thief_enter_time": 0x904B9E, "thief_direction": 0x904B9C,
    "thief_collision_direction_code": 0x904BB8, "thief_stolen_item": 0x904BBC,
    "thief_tport_active": 0x904BBE, "thief_tport_timer": 0x904BD6,
    "thief_direction_change_pos": 0x9048B0, "thief_victim_pos": 0x904B98,
}


def compare(machine, state: GameState) -> list[str]:
    out = []
    for name, address in _WORDS.items():
        rom, py = machine.r16(address), getattr(state, name) & 0xFFFF
        if rom != py:
            out.append(f"{name}: ROM {rom:#x} PY {py:#x}")
    for name, address in (("thief_pursuit_direction", 0x904060), ("thief_pursuit_player", 0x904061),
                          ("thief_pursuit_shot_direction", 0x904062)):
        rom, py = machine.r8(address), getattr(state, name) & 0xFF
        if rom != py:
            out.append(f"{name}: ROM {rom:#x} PY {py:#x}")
    if machine.r16(0x904BFC) != state.rng.seed:
        out.append(f"seed: ROM {machine.r16(0x904BFC):#x} PY {state.rng.seed:#x}")
    slot = state.thief_current_pos
    if slot:
        rom = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot))
        py = (state.mobs.picture[slot], state.mobs.hpos[slot], state.mobs.vpos[slot])
        if rom != py:
            out.append(f"record {slot:#x}: ROM {tuple(hex(v) for v in rom)} PY {tuple(hex(v) for v in py)}")
    # Only the first 44 bytes of each 0x80-byte row are the grid; the rest is alpha RAM.
    grid = bytes(machine.cpu.mem_read(0x905054, 0xC00))
    bad = [i for i in range(0xC00) if i % 0x80 < 44 and grid[i] != state.path_direction_grid[i]]
    if bad:
        at = bad[0]
        out.append(f"grid byte {at:#x}: ROM {grid[at]:#x} PY {state.path_direction_grid[at]:#x}")
    hero = state.players[0]
    rom_health = int.from_bytes(bytes(machine.cpu.mem_read(0x904980, 4)), "big", signed=True)
    if rom_health != hero.health:
        out.append(f"health: ROM {rom_health} PY {hero.health}")
    if machine.r8(0x904055) != hero.potionsnum:
        out.append(f"potions: ROM {machine.r8(0x904055)} PY {hero.potionsnum}")
    return out


def _copy_slot(machine, state: GameState, slot: int) -> None:
    """Write one record's words from gauntpy into ROM RAM."""
    machine.w16(rom_exec._PICTURE + 2 * slot, state.mobs.picture[slot])
    machine.w16(rom_exec._HPOS + 2 * slot, state.mobs.hpos[slot])
    machine.w16(rom_exec._VPOS + 2 * slot, state.mobs.vpos[slot])
    machine.w16(rom_exec._LINK + 2 * slot, state.mobs.link[slot])
    machine.w16(rom_exec._STATE + 2 * slot, state.mobs.state_link[slot])


def _shot_ahead(state: GameState) -> tuple[int, int] | None:
    """A cell three steps along the thief's heading, and the arrow's heading back at it."""
    direction = state.thief_direction
    if not 0 <= direction <= 7 or not state.thief_current_pos:
        return None
    current = state.thief_current_pos
    row = (current >> 5) + 3 * _ROW_STEP[direction]
    column = (current & 0x1F) + 3 * _COLUMN_STEP[direction]
    if not 2 <= row < 31 or not 0 <= column < 32:
        return None
    return (row << 5) | column, (direction + 4) & 7


def walk(state: GameState, onward=(), scenario: str = "plain", frames: int = 2000,
         show: bool = False) -> tuple[int, list[str], str]:
    """``(frames compared, first differences, how the run ended)``."""
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    onward = list(onward)
    transported = False
    blocked = False
    escape_frame = None
    for frame in range(1, frames + 1):
        state.frame_counter = (state.frame_counter + 1) & 0xFFFF
        machine.w16(0x904006, state.frame_counter)
        if scenario == "shot" and frame in (90, 130):
            if frame == 90:
                shot = _shot_ahead(state)
                if shot:
                    cell, heading = shot
                    _record(state, 1, _ARROW, 0)
                    state.mobs.hpos[1] = (((cell & 0x1F) * 16 - 4) << 7) & 0xFFFF
                    state.mobs.vpos[1] = (native_v((cell >> 5) * 16) << 7) & 0xFFFF
                    state.shot_direction[0] = heading
            else:
                state.mobs.picture[1] = 0
            _copy_slot(machine, state, 1)
            machine.w16(0x9049C4, state.shot_direction[0])
        if scenario == "block" and state.thief_mode & thief.THIEF_ESCAPE and not blocked:
            if escape_frame is None:
                escape_frame = frame
            elif frame == escape_frame + 40:
                blocked = True
                behind = [c for c in onward[1:-1] if not state.mobs.picture[c]]
                if behind:
                    hero = state.players[0]
                    old, new = hero.mob_slot, behind[len(behind) // 2]
                    state.mobs.move_slot(old, new)
                    state.mobs.hpos[new] = ((((new & 0x1F) * 16 - 4) << 7) | 0x0C) & 0xFFFF
                    state.mobs.vpos[new] = (native_v((new >> 5) * 16) << 7) & 0xFFFF
                    hero.mob_slot = new
                    for slot in (old, new):
                        _copy_slot(machine, state, slot)
                    machine.w16(0x9048C8, new)
        if scenario == "moving" and onward and frame > 70 and frame % 10 == 0 \
                and not state.thief_mode & thief.THIEF_ESCAPE:
            hero = state.players[0]
            old, new = hero.mob_slot, onward.pop(0)
            if not state.mobs.picture[new]:
                machine.call(0x4E630, new, 0)
                thief.thief_track_victim_move(state, new, 0)
                state.mobs.move_slot(old, new)
                state.mobs.hpos[new] = ((((new & 0x1F) * 16 - 4) << 7) | 0x0C) & 0xFFFF
                state.mobs.vpos[new] = (native_v((new >> 5) * 16) << 7) & 0xFFFF
                hero.mob_slot = new
                for slot in (old, new):
                    _copy_slot(machine, state, slot)
                machine.w16(0x9048C8, new)
        machine.call(0x4E8DC, count=2_000_000)
        if not machine.halted:
            return frame, [f"ROM did not return from main_thief_anim (fault {machine.fault_pc})"], "fault"
        machine.call(0x4DEB8, count=2_000_000)
        thief.main_thief_anim(state)
        thief.main_start_thief(state)
        if state.thief_tport_timer >= 0 or machine.r16(0x904BD6) < 0x8000:
            # main_score_update (0x4715E) steps the transporter dissolve; only its
            # thief pass has work while no hero is transporting.
            machine.call(0x4715E, count=2_000_000)
            score.main_score_update(state)
            transported = True
        differences = compare(machine, state)
        if show and frame % 50 == 0:
            print(frame, hex(state.thief_current_pos), hex(state.thief_mode))
        if differences:
            return frame, differences, "differs"
        if state.thief_enter_time >= 0x100 or (
            not state.thief_current_pos and state.thief_mode & thief.THIEF_ESCAPE
        ):
            return frame, [], "left after a transport" if transported else "left"
    return frames, [], "time"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--maze", type=int, action="append")
    parser.add_argument("--scenario", choices=SCENARIOS, action="append")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    mazes = args.maze or [6, 7, 13, 15, 29, 43, 76, 84, 87, 101]
    scenarios = args.scenario or list(SCENARIOS)
    failures = 0
    endings: dict[str, int] = {}
    for scenario in scenarios:
        for maze in mazes:
            for start in (0x84, 0x14A, 0x1D6, 0x2A8, 0x330):
                for length in (6, 14, 30):
                    for mugger in (False, True):
                        made = setup(maze, start, length, mugger, scenario)
                        if made is None:
                            continue
                        state, onward = made
                        frames, differences, end = walk(state, onward, scenario, show=args.show)
                        endings[f"{scenario}/{end}"] = endings.get(f"{scenario}/{end}", 0) + 1
                        if differences:
                            failures += 1
                            print(f"{scenario} maze {maze} start {start:#x} length {length} mugger {mugger}: "
                                  f"frame {frames}: {'; '.join(differences)}")
    print("endings:", dict(sorted(endings.items())))
    print("runs with differences:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
