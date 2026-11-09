"""Sweep every object type through gauntpy and the ROM (tools/rom_exec.py).

    python tools/rom_sweeps.py walk    # walk a hero into each type, in four directions
    python tools/rom_sweeps.py scan    # run the transporter arrival scan on each type
    python tools/rom_sweeps.py shots   # resolve_shot_hit on each type, shooter and power
    python tools/rom_sweeps.py exits   # player_exit_sequence on real levels, tricks and parties
    python tools/rom_sweeps.py routes  # tport_route_connect and its if-empty form
    python tools/rom_sweeps.py reflect # shot_reflect_calc, every approach and corner (minutes)

``walk`` steps one continuous ROM run against gauntpy's movement and occupied-cell tail,
comparing the result word, position, keys, the fight latch and how often
player_tile_interact runs. It does main_move_players' 0x4AA12 and 0x4AA36-0x4AA3E around
each ROM call, which is what ends a fight when a swing misses.
``scan`` forces each type to overlap a landed hero and reports records that survive or
an instruction limit, which would be a hang.

``walk`` skips PLAYERSTART: a real one is a hero or the thief, and those need more than a
placed record (tests/test_rom_execution.py has the thief). It stops once a hero starts to
transport or leaves through an exit, because main_move_players stops moving them too. Comparing
RNG seeds needs a real level, since a fixture has no neighbours for floor restamps to draw for,
so ``shots`` and ``exits`` load one.

A difference is a lead, not a verdict: fixtures here are not real maze states, and a fault
usually means RAM the snapshot lacks. Hand-traced conclusions live in doc/04 §7.2.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import os
from pathlib import Path
import random
import sys

_TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(_TOOLS), str(_TOOLS.parent / "src")]

import rom_exec  # noqa: E402
from gauntpy.game.constants import GameMode, MazeObjIds, PlayerStatus  # noqa: E402
from gauntpy.game.coords import native_v  # noqa: E402
from gauntpy.game.maze import maze_place_object, reset_and_load_level, set_cell_descriptor  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import input as gin  # noqa: E402
from gauntpy.game.subsystems import player_items  # noqa: E402
from gauntpy.game.subsystems import player_movement as pm  # noqa: E402
from gauntpy.game.subsystems import thief  # noqa: E402
from gauntpy.game.subsystems.level_transitions import player_exit_sequence  # noqa: E402
from gauntpy.game.subsystems.player_lifecycle import player_start_inner  # noqa: E402
from gauntpy.game.subsystems.shot_collision import shot_reflect_calc  # noqa: E402
from gauntpy.game.subsystems.shots import resolve_shot_hit  # noqa: E402
from gauntpy.game.subsystems.shot_state import _shot_slot  # noqa: E402
from gauntpy.game.subsystems.player_transport import scan_move_path_interactions  # noqa: E402

_JOBS = os.cpu_count() or 1

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
    if obj_type == int(MazeObjIds.HIDDENPOT):
        state.mobs.picture[target] = 0xA728       # 0x4C86A indexes a table by the picture
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.install_slapstic()                    # an exit reads the maze table, 0x52EF2
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
            machine.w16(0x904A0E, 0)
            result = rom_exec.player_try_move(machine, state, 0, delta)
            if not machine.halted:
                return f"ROM stopped at step {step}, fault {machine.fault_pc}"
            if not machine.r16(0x904A0E):
                machine.w16(0x9049AC, 0)
            slot = machine.player_slot(0)
            rom = (result, slot, machine.hpos(slot) & ~0xF, machine.vpos(slot),
                   machine.keys(0), rom_calls[0], bool(machine.r16(0x9049AC)))
            state.movement_type = 2
            origin = (player.mob_slot, state.mobs.hpos[player.mob_slot],
                      state.mobs.vpos[player.mob_slot])
            moved = pm.player_try_move(state, 0, delta, 0, track_thief=False)
            _, refused = pm.resolve_entered_cell(state, 0, origin)
            if not state.player_fight_contact:        # 0x4AA36, as for the ROM above
                state.player_fighting_dir[0] = 0
            slot = player.mob_slot
            ours = (0xF0 if refused else moved & 0xFFFF, slot, state.mobs.hpos[slot] & ~0xF,
                    state.mobs.vpos[slot], player.keysnum, our_calls[0],
                    bool(state.player_fighting_dir[0]))
            rom_status = machine.r8(0x9049A0)
            if rom_status != int(player.status):
                return f"status differs at step {step}: ROM {rom_status:#x} gauntpy {int(player.status):#x}"
            if rom_status != int(PlayerStatus.ALIVE_HERE):
                break
            if rom != ours:
                return f"differs at step {step}: ROM {[hex(x) for x in rom]} gauntpy {[hex(x) for x in ours]}"
            if state.player_tport_phase[0] >= 0:
                break
    finally:
        player_items.player_tile_interact = original
    return "same"


def _route_address(base: int, pad: int) -> int:
    return base + ((pad // 0x16) << 7) + (pad % 0x16) * 2     # 0x51088-0x51094


def routes(count: int = 4000) -> int:
    """tport_route_connect (0x4E684) and its if-empty form (0x4E73A) on random pads and routes."""
    rng = random.Random(4)
    bad = 0
    for _ in range(count):
        state = GameState()
        pads = rng.sample(range(0x40, 0x3C0), rng.randint(2, 12))
        for pad in pads:
            state.mobs.create(pad, tile=0x8001, hpos=(pad & 0x1F) * 16 << 7,
                              vpos=native_v((pad >> 5) * 16) << 7,
                              obj_type=int(MazeObjIds.TRANSPORTER))
        for pad in range(1, len(pads) + 1):
            state.tport_route_forward[pad] = rng.choice((0, rng.getrandbits(16) & 0x0F0F))
            state.tport_route_reverse[pad] = rng.choice((0, rng.getrandbits(16) & 0x0F0F))
        ordered = sorted(pads)
        source = rng.choice((*ordered, rng.randrange(0x40, 0x3C0)))
        destination = rng.choice((*ordered, rng.randrange(0x40, 0x3C0)))
        other = (destination + rng.choice((1, -1, 32, -32, 33, -33, 31, -31))) & 0x3FF
        if_empty = rng.random() < 0.5
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        machine.call(0x4E73A if if_empty else 0x4E684, source, destination, other)
        (thief.tport_route_connect_if_empty if if_empty else thief.tport_route_connect)(
            state, source, destination, other,
        )
        for pad in range(1, len(ordered) + 2):
            rom = (machine.r16(_route_address(0x905C54, pad)), machine.r16(_route_address(0x905D54, pad)))
            ours = (state.tport_route_forward[pad], state.tport_route_reverse[pad])
            if rom != ours or not machine.halted:
                bad += 1
                if bad <= 5:
                    print(f"  {source:#x}->{destination:#x} via {other:#x} if_empty={if_empty} "
                          f"pad {pad}: ROM {rom[0]:#x},{rom[1]:#x} gauntpy {ours[0]:#x},{ours[1]:#x}")
                break
    print(f"routes: {bad} of {count} differ")
    return bad


def _reflect_pair(pair: tuple[int, int]) -> tuple[int, int, list[str]]:
    """Every case of shot_reflect_calc for one direction and shooter."""
    direction, shooter = pair
    bad = cases = 0
    lines: list[str] = []
    target = (12 << 5) | 12
    neighbours = {"up": target - 32, "down": target + 32, "left": target - 1, "right": target + 1}
    near_cell = (0, 1, -1, 32, -32, 33, -33, 31, -31, 2, -2, 64)
    for wall_mask in range(16):
        for delta in near_cell:
            for count in (0, 1, 3):
                for raw_target in (target, target | 0x400):
                    for top in (False, True):
                        cases += 1
                        state = GameState()
                        for bit, cell in enumerate(neighbours.values()):
                            if wall_mask >> bit & 1:
                                state.mobs.picture[cell] = 0x8000
                                state.mobs.hpos[cell] = (cell & 0x1F) * 16 << 7
                                state.mobs.vpos[cell] = native_v((cell >> 5) * 16) << 7
                                state.mobs.link[cell] = int(MazeObjIds.WALL_REGULAR) << 10
                        state.shot_direction[shooter] = direction
                        state.reflect_count[shooter] = count
                        state.player_shot_last_wall_pos[shooter] = (target - delta) & 0x3FF
                        slot = _shot_slot(shooter)
                        state.mobs.picture[slot] = 0x1000
                        state.mobs.hpos[slot] = 12 * 16 << 7
                        state.mobs.vpos[slot] = 0xF900 if top else native_v(12 * 16) << 7
                        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
                        rom = machine.call(0x53818, raw_target, shooter, count=500_000) & 0xFFFF
                        ours = shot_reflect_calc(state, raw_target, shooter) & 0xFFFF
                        pairs = (
                            ("result", rom, ours),
                            ("direction", machine.r16(0x9049C4 + 2 * shooter), state.shot_direction[shooter] & 0xFFFF),
                            ("bounces", machine.r16(0x9048BE + 2 * shooter), state.reflect_count[shooter] & 0xFFFF),
                            ("h", machine.hpos(slot), state.mobs.hpos[slot] & 0xFFFF),
                            ("v", machine.vpos(slot), state.mobs.vpos[slot] & 0xFFFF),
                            ("seed", machine.r16(0x904BFC), state.rng.seed & 0xFFFF),
                        )
                        wrong = [f"{name} ROM {a:#x} PY {b:#x}" for name, a, b in pairs if a != b]
                        if wrong or not machine.halted:
                            bad += 1
                            lines.append(f"  dir {direction} shooter {shooter} walls {wall_mask:#x} "
                                         f"delta {delta} count {count} target {raw_target:#x} top {top}: "
                                         f"{wrong[:3]}")
    return bad, cases, lines


def reflect() -> int:
    """shot_reflect_calc (0x53818) for every direction, approach, corner and bounce state."""
    bad = cases = 0
    shown: list[str] = []
    pairs = [(direction, shooter) for direction in range(8) for shooter in (0, 2)]
    with concurrent.futures.ProcessPoolExecutor(_JOBS) as pool:
        for pair_bad, pair_cases, lines in pool.map(_reflect_pair, pairs):
            bad += pair_bad
            cases += pair_cases
            shown += lines
    for line in shown[:6]:
        print(line)
    print(f"reflect: {bad} of {cases} differ")
    return bad
    return bad


def exits(count: int = 1500) -> int:
    """player_exit_sequence (0x52B40) on real levels, across tricks, stride and party."""
    rng = random.Random(9)
    bad = 0
    mazes = (1, 5, 7, 14, 20, 30, 39, 47, 52, 60, 77, 90, 100, 101, 102, 103, 104, 108, 112)
    for _ in range(count):
        maze = rng.choice(mazes)
        level = rng.choice((1, 2, 3, 4, 5, 6, 7, 8, 20, 100, 104, 300, 500, 998, 999))
        state = GameState()
        state.game_mode = 0
        state.levelnum_current = level
        state.rng.seed = rng.getrandbits(16)
        state.mazenum_current = maze
        if not reset_and_load_level(state, level, maze_number=maze):
            return -1
        exit_cells = [slot for slot in range(32, 1024)
                      if state.mobs.obj_type(slot) in (int(MazeObjIds.EXIT), int(MazeObjIds.EXITTO6))]
        if not exit_cells:
            cell = rng.randrange(0x60, 0x3A0)
            state.mobs.unlink_and_clear(cell)
            maze_place_object(state, cell, rng.choice((MazeObjIds.EXIT, MazeObjIds.EXITTO6)), 1)
            exit_cells = [cell]
        heroes = rng.sample(range(4), rng.randint(1, 4))
        hero = heroes[0]
        for index in heroes:
            player = state.players[index]
            status = int(PlayerStatus.ALIVE_HERE) if index == hero else rng.choice((1, 1, 2))
            player.status = status
            player.health = 500
            player.character = index
            player.coin_count = 1
            player_start_inner(state, index)
            player.status = status
        cell = rng.choice(exit_cells)
        exit_type = state.mobs.obj_type(cell)
        state.players[hero].powers = rng.choice((0, 0xC00, 0x401, 0x8FF))
        state.maze_number = rng.choice((5, 6, 50, 101))
        state.maze_stride = rng.randint(0, 7)
        state.level_next = state.maze_next = 0
        state.treasure_timer = rng.choice((0, 600))
        state.secret_trick_id = rng.choice((0, 0, 5, 6, 7, 8, 9, 0xB, 0xC, 0xD, 0xE, 0xF, 0x10, 0x11))
        state.secret_tricks_flags = [rng.choice((0, 1, 2, 3, 0xFF)) for _ in range(4)]
        state.secret_player = rng.choice((-1, -1, hero))
        state.secret_possible_counter = 0
        state.current_player = rng.choice((hero, hero, rng.randint(0, 3)))
        state.player_it = rng.choice((0xFFFF, hero))
        state.thief_victim = rng.choice((-1, hero))
        state.level_flags_3 |= rng.choice((0, 0x40, 0x80))
        state.movement_type = rng.choice((0, 2))
        machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
        machine.install_slapstic()
        machine.call(0x40D4E, maze, count=100_000)
        for address, value in (
            (0x904000, maze), (0x904004, level), (0x90400E, state.maze_stride),
            (0x904010, state.maze_number), (0x904B52, 0), (0x904B54, 0),
            (0x9049E8, state.treasure_timer),
        ):
            machine.w16(address, value)
        machine.w8(0x904063, state.secret_player & 0xFF)
        machine.w8(0x904065, state.secret_trick_id)
        machine.w8(0x90491E, state.level_flags_3)
        for index, flag in enumerate(state.secret_tricks_flags):
            machine.w8(0x904872 + index, flag)
        for index, player in enumerate(state.players):
            machine.w8(0x9049A0 + index, player.status)
            machine.w16(0x9048C8 + 2 * index, player.mob_slot)
            machine.w16(0x9048E0 + 2 * index, player.powers)
            machine.w8(0x905F68 + index, player.supershot)
        machine.call(0x52B40, hero, cell, exit_type, count=8_000_000)
        if not machine.halted:
            bad += 1
            print(f"  maze {maze} level {level}: ROM fault {machine.fault_pc}")
            continue
        player_exit_sequence(state, hero, cell, exit_type)
        player = state.players[hero]
        words = (
            ("status", machine.r8(0x9049A0 + hero), int(player.status)),
            ("slot", machine.r16(0x9048C8 + 2 * hero), player.mob_slot),
            ("powers", machine.r16(0x9048E0 + 2 * hero), player.powers & 0xFFFF),
            ("level_next", machine.r16(0x904B52), state.level_next & 0xFFFF),
            ("maze_next", machine.r16(0x904B54), state.maze_next & 0xFFFF),
            ("treasure_timer", machine.r16(0x9049E8), state.treasure_timer & 0xFFFF),
            ("stride", machine.r16(0x90400E), state.maze_stride & 0xFFFF),
            ("anim", machine.r16(0x9049BC + 2 * hero), player.anim_counter & 0xFFFF),
            ("flags_3", machine.r8(0x90491E), state.level_flags_3 & 0xFF),
            ("secret_player", machine.r8(0x904063), state.secret_player & 0xFF),
            ("seed", machine.r16(0x904BFC), state.rng.seed & 0xFFFF),
        )
        wrong = [f"{name} ROM {rom:#x} PY {python:#x}" for name, rom, python in words if rom != python]
        heroes_now = {other.mob_slot for other in state.players if other.mob_slot} | {cell}
        for slot in range(32, 1024):
            rom_record = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot))
            our_record = (state.mobs.picture[slot], state.mobs.hpos[slot], state.mobs.vpos[slot])
            if (rom_record[0] or our_record[0]) and rom_record != our_record:
                wrong.append(f"record {slot:#x} ROM {rom_record} PY {our_record}")
            elif (rom_record[0] or our_record[0]) and slot not in heroes_now \
                    and machine.r16(rom_exec._LINK + 2 * slot) != state.mobs.link[slot] & 0xFFFF:
                wrong.append(f"link {slot:#x}")
        if wrong:
            bad += 1
            if bad <= 6:
                print(f"  maze {maze} level {level} hero {hero} trick {state.secret_trick_id:#x}: {wrong[:3]}")
    print(f"exits: {bad} of {count} differ")
    return bad


def _shot_words(machine, state: GameState, shooter: int, target: int) -> list[tuple]:
    words = [("seed", machine.r16(0x904BFC), state.rng.seed & 0xFFFF)]
    for index, player in enumerate(state.players):
        words += [
            (f"score{index}", int.from_bytes(bytes(machine.cpu.mem_read(0x904990 + 4 * index, 4)), "big"),
             player.score & 0xFFFFFFFF),
            (f"health{index}", int.from_bytes(bytes(machine.cpu.mem_read(0x904980 + 4 * index, 4)), "big"),
             player.health & 0xFFFFFFFF),
            (f"keys{index}", machine.r8(0x90405A + index), player.keysnum & 0xFF),
            (f"potions{index}", machine.r8(0x904055 + index), player.potionsnum & 0xFF),
            (f"status{index}", machine.r8(0x9049A0 + index), int(player.status)),
        ]
    if shooter < 4:
        words.append(("bounces", machine.r16(0x9048BE + 2 * shooter), state.reflect_count[shooter] & 0xFFFF))
    words += [
        ("direction", machine.r16(0x9049C4 + 2 * shooter), state.shot_direction[shooter] & 0xFFFF),
        ("thief", machine.r16(0x904BA4), state.thief_current_pos & 0xFFFF),
    ]
    return words


def _shots_for(obj_type: int) -> tuple[int, int, dict[str, int], list[tuple[str, str]]]:
    """Every shots case for one object type: (differing, cases, kinds, first line of each kind)."""
    bad = cases = 0
    kinds: dict[str, int] = {}
    lines: list[tuple[str, str]] = []
    for shooter in (0, 1, 4, 7):
        for powers in (0, 0x400, 0x10):
            for health_low in (False, True):
                for seed in (0x1234, 0xBFE6):
                    # A real level, so a redraw has floors to draw on both sides.
                    state = GameState()
                    state.game_mode = 0
                    state.levelnum_current = 8
                    state.rng.seed = seed
                    if not reset_and_load_level(state, 8, maze_number=20):
                        return -1, 0, {}, []
                    hero_player = state.players[0]
                    hero_player.status = int(PlayerStatus.ALIVE_HERE)
                    hero_player.coin_count = 1
                    hero_player.health = 500
                    player_start_inner(state, 0)
                    hero_player.status = int(PlayerStatus.ALIVE_HERE)
                    state.player_input_raw[0] = 0xFFFF
                    target = next(
                        cell for cell in range(12 << 5, 1000)
                        if not state.mobs.picture[cell] and (cell & 0x1F) not in (0, 31)
                    )
                    maze_place_object(state, target, obj_type, 1)
                    if not state.mobs.picture[target]:
                        continue
                    # wall_crumble reads its headroom from the tile's palette (0x5313A).
                    if state.mobs.picture[target] == 0x8000:
                        set_cell_descriptor(state, target, obj_type)
                    if obj_type == int(MazeObjIds.HIDDENPOT):
                        state.mobs.picture[target] = 0xA728
                    hero = state.players[0]
                    hero.powers = powers
                    hero.health = 40 if health_low else 500
                    slot = _shot_slot(shooter)
                    state.mobs.picture[slot] = 0x1000
                    state.mobs.hpos[slot] = ((target & 0x1F) * 16) << 7
                    state.mobs.vpos[slot] = native_v((target >> 5) * 16) << 7
                    state.shot_direction[shooter] = 2
                    if shooter < 4:
                        state.reflect_count[shooter] = 2
                        state.player_shot_last_wall_pos[shooter] = target - 1
                    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
                    machine.install_slapstic()
                    for address, value in ((0x904000, 20), (0x904004, 8), (0x904B5C, int(state.maze.floorpattern)),
                                           (0x904B5E, int(state.maze.wallpattern))):
                        machine.w16(address, value)
                    machine.write_words(0x900000, state.playfield_ram)
                    cases += 1
                    rom_result = machine.call(0x4AF50, target, shooter, count=3_000_000) & 0xFFFF
                    if not machine.halted:
                        kinds[f"ROM stops: {_name(obj_type)}"] = kinds.get(f"ROM stops: {_name(obj_type)}", 0) + 1
                        continue
                    our_result = resolve_shot_hit(state, target, shooter) & 0xFFFF
                    wrong = [name for name, rom, ours in _shot_words(machine, state, shooter, target) if rom != ours]
                    if rom_result != our_result:
                        wrong.append("result")
                    rom_record = (machine.picture(target), machine.hpos(target), machine.vpos(target))
                    our_record = (state.mobs.picture[target], state.mobs.hpos[target], state.mobs.vpos[target])
                    if rom_record != our_record:
                        wrong.append("target record")
                    if wrong:
                        bad += 1
                        key = f"{_name(obj_type)} shooter {'hero' if shooter < 4 else 'monster'}: {wrong[0]}"
                        if key not in kinds:
                            line = (f"  {_name(obj_type)} shooter {shooter} powers {powers:#x} low {health_low}: "
                                    f"{wrong[:4]} result ROM {rom_result:#x} PY {our_result:#x} "
                                    f"record ROM {tuple(map(hex, rom_record))} PY {tuple(map(hex, our_record))}")
                            lines.append((key, line))
                        kinds[key] = kinds.get(key, 0) + 1
    return bad, cases, kinds, lines


def shots() -> int:
    """resolve_shot_hit (0x4AF50): every object type, shooter and power, seen from the records."""
    bad = cases = 0
    kinds: dict[str, int] = {}
    shown = 0
    with concurrent.futures.ProcessPoolExecutor(_JOBS) as pool:
        for part_bad, part_cases, part_kinds, lines in pool.map(_shots_for, range(1, 0x40)):
            if part_bad < 0:
                return -1
            bad += part_bad
            cases += part_cases
            for key, line in lines:
                if key not in kinds and shown < 60:
                    print(line)
                    shown += 1
            for key, count in part_kinds.items():
                kinds[key] = kinds.get(key, 0) + count
    print(f"shots: {bad} of {cases} differ")
    for key, count in sorted(kinds.items()):
        print(f"  {count:5} {key}")
    return bad


def walk() -> int:
    bad = 0
    for name, delta in (("right", gin.JOY_RIGHT), ("left", gin.JOY_LEFT),
                        ("up", gin.JOY_UP), ("down", gin.JOY_DOWN)):
        for keys in (0, 3):
            same = 0
            print(f"--- {name}, keys={keys}")
            for obj_type in range(1, 0x40):
                if obj_type == int(MazeObjIds.PLAYERSTART):
                    continue
                outcome = _walk(obj_type, keys, delta)
                if outcome == "same":
                    same += 1
                elif outcome is not None:
                    bad += 1
                    print(f"  {_name(obj_type)}: {outcome}")
            print(f"  {same} types the same")
    return bad


def scan() -> int:
    bad = 0
    hero = (10 << 5) | 10
    left = (10 << 5) | 9
    # A hidden potion needs a real picture.
    rom_skipped = {0x3D}
    for keys, powers in ((0, 0), (1, 0), (12, 0), (0, 0xFFFF)):
        limit, faults, rom_survived, our_survived = [], [], [], []
        for obj_type in range(1, 0x40):
            state = _state_with_hero(hero, keys=keys, powers=powers)
            # Exits and pads carry a marker picture, which ends the scan at 0x50C02.
            marker = obj_type in (int(MazeObjIds.EXIT), int(MazeObjIds.EXITTO6),
                                  int(MazeObjIds.TRANSPORTER))
            state.mobs.create(left, tile=0x8001 if marker else 0x0AFC, hpos=(9 * 16) << 7,
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
        bad += len(limit) + len(faults) + (rom_survived != our_survived)
        # Real records never survive to loop, since the marker pictures stop first.
    return bad


def main() -> int:
    global _JOBS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sweep", choices=("walk", "scan", "routes", "reflect", "exits", "shots"))
    parser.add_argument("--jobs", type=int, default=_JOBS,
                        help="worker processes for reflect; every case runs once whatever the count")
    args = parser.parse_args()
    _JOBS = max(1, args.jobs)
    sweep = {"walk": walk, "scan": scan, "routes": routes, "reflect": reflect, "exits": exits,
             "shots": shots}[args.sweep]
    return 1 if sweep() else 0


if __name__ == "__main__":
    raise SystemExit(main())
