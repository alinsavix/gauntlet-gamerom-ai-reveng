"""Compare a whole level load with the ROM, for every maze.

Runs what ``main_start_game`` runs to load a level, in the ROM under Unicorn with its
Slapstic in front of the real maze data, and the same in gauntpy from the same seed. Then
every MOB record, the seed, the level flags, the setup tables and the playfield are compared.
Four sweeps, each adding a stage, and setup_infopanel (0x452D0) on random parties:

    the load     maze_select_bank_special (0x40D4E), maze_load_pickup_config (0x436FE) and
                 maze_new_level_setup (0x438AE), on every maze including the secret rooms
    the screen   show_level_start_screen (0x44DB4) first, with its splash text; it may also
                 substitute a treasure room
    the party    then each hero's player_start_inner (0x48BEC), the spawn bonus (0x48B58),
                 maze_addrandompickups (0x43F68) and thief_setup (0x4E432)
    the press    main_start_game's arms for a first hero: a continue or free play, which
                 reload the level, and a paid game from start_attract_to_game (0x44204)

    python tools/level_load_check.py                    every maze, a few seeds and levels
    python tools/level_load_check.py --maze 39 --show   one maze, with the differences

Needs GEX_ROM_DIR and the ROMs ``rom_exec.py`` needs.
"""

from __future__ import annotations

import argparse
import collections
import copy
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rom_exec  # noqa: E402

from gauntpy.game.constants import MONSTER_TYPES, GameMode, PlayerStatus  # noqa: E402
from gauntpy.game.maze import reset_and_load_level  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems import attract, score, session, thief  # noqa: E402
from gauntpy.game.subsystems.eeprom import encode_initials  # noqa: E402
from gauntpy.game.subsystems.level_transitions import (  # noqa: E402
    _spawn_level_players,
    show_level_start_screen,
)
from gauntpy.game.subsystems.player_lifecycle import setup_infopanel  # noqa: E402
from gauntpy.game.subsystems.player_transport import _tport_pos_table  # noqa: E402
from gauntpy.game.subsystems.secret_rooms import secret_new_level_setup  # noqa: E402

MONSTERS = {int(t) for t in MONSTER_TYPES}
MAZES = range(117)
LEVELS = (7, 6, 2, 150, 250, 350)
SEEDS = (0x1234, 0xBFE6, 0x0001, 0x7A5C)
PARTIES = ((0,), (1,), (2,), (3,), (0, 1), (0, 1, 2), (0, 1, 2, 3))


def new_state(level: int, seed: int, task: int = 0) -> GameState:
    state = GameState()
    state.game_mode = 0
    state.levelnum_current = level
    state.rng.seed = seed
    state.secret_trick_id = task
    return state


def rom_load(state: GameState, maze: int) -> rom_exec.RomMachine:
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.install_slapstic()
    machine.w16(0x904000, maze)
    machine.w16(0x904004, state.levelnum_current)
    machine.w16(0x904878, state.secret_possible_counter)
    machine.w8(0x904063, state.secret_player & 0xFF)
    machine.call(0x40D4E, maze, count=100_000)
    if machine.halted:
        pointer = int.from_bytes(bytes(machine.cpu.mem_read(0x904B88, 4)), "big")
        machine.call(0x436FE, pointer, count=2_000_000)
    if machine.halted:
        machine.call(0x438AE, count=50_000_000)
    return machine


def start_screen_state(maze: int, level: int, seed: int, next_treasure: int) -> GameState:
    state = new_state(level, seed)
    state.mazenum_current = maze
    state.level_next_treasure = next_treasure
    state.level_next_potion = 1
    player = state.players[0]
    player.status = int(PlayerStatus.ALIVE_NEXT)
    player.health = 500
    player.coin_count = 1
    return state


def rom_start_screen_load(state: GameState) -> rom_exec.RomMachine:
    """The start screen and then the load, as main_start_game runs them (0x4813A, 0x4820A)."""
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.install_slapstic()
    machine.w16(0x904000, state.mazenum_current)
    machine.w16(0x904004, state.levelnum_current)
    machine.w8(0x904063, state.secret_player & 0xFF)
    machine.w16(0x904878, state.secret_possible_counter)
    machine.w16(0x904B80, state.level_next_treasure)
    machine.w16(0x904B7E, state.level_next_potion)
    machine.w16(0x904018, state.treas_mazerand_num)
    machine.w16(0x904016, state.treas_mazerand_adder)
    machine.call(0x40D4E, state.mazenum_current, count=100_000)
    if machine.halted:
        machine.call(0x44DB4, count=5_000_000)
    if machine.halted:
        machine.call(0x40D4E, machine.r16(0x904000), count=100_000)
    if machine.halted:
        machine.call(0x438AE, count=50_000_000)
    return machine


def check_start_screen(maze: int, level: int, seed: int, next_treasure: int = 3):
    state = start_screen_state(maze, level, seed, next_treasure)
    machine = rom_start_screen_load(state)
    if not machine.halted:
        return f"ROM did not return (pc {machine.cpu.reg_read(rom_exec.registers.UC_M68K_REG_PC):#x})", {}
    show_level_start_screen(state)
    if not python_load(state, state.mazenum_current):
        return "gauntpy could not load it", {}
    found = differences(machine, state)
    # The panel reads OS coin settings the snapshot lacks, so only the field left of it.
    for index in range(64 * 30):
        if index % 64 < 29 and machine.r16(0x905000 + 2 * index) != state.alpha_ram[index]:
            found["splash text"].append(
                f"row {index // 64} col {index % 64}: ROM {machine.r16(0x905000 + 2 * index):#x} "
                f"PY {state.alpha_ram[index]:#x}"
            )
    return "", found


def party_state(maze: int, level: int, seed: int, characters: tuple[int, ...],
                settings: int, bonus: int) -> GameState:
    state = start_screen_state(maze, level, seed, 3)
    state.level_next_potion = 0 if level % 2 else 1
    state.game_settings = settings
    state.monster_spawn_probability_bonus = bonus
    for i, character in enumerate(characters):
        player = state.players[i]
        player.status = int(PlayerStatus.ALIVE_NEXT)
        player.health = 500
        player.coin_count = 1 + i
        player.character = character
        player.score = 30000 * (i + 1)
    return state


def check_party(maze: int, level: int, seed: int, characters: tuple[int, ...],
                settings: int = 0, bonus: int = 0) -> tuple[str, dict[str, list[str]]]:
    """The stages after the load, through thief_setup and the speech after it (0x483FC)."""
    state = party_state(maze, level, seed, characters, settings, bonus)
    machine = rom_start_screen_load(state)
    if not machine.halted:
        return "ROM did not finish the load", {}
    machine.w8(0x90405F, bonus)
    for i in range(len(characters)):
        machine.w8(0x9049A0 + i, int(PlayerStatus.ALIVE_NEXT))
        machine.cpu.mem_write(0x904990 + 4 * i, (30000 * (i + 1)).to_bytes(4, "big"))
        machine.call(0x48BEC, i, count=5_000_000)
        machine.w8(0x9049A0 + i, int(PlayerStatus.ALIVE_HERE))
    machine.call(0x48B58, count=500_000)
    machine.call(0x43F68, 1, count=5_000_000)
    machine.call(0x4E432, count=500_000)
    if not machine.halted:
        return "ROM did not finish the party", {}
    # The tail of the same routine, which plays the level's opening speech.
    played: list[int] = []

    def note_sound(cpu, _address, _size, _data) -> None:
        stack = cpu.reg_read(rom_exec.registers.UC_M68K_REG_A7)
        played.append(bytes(cpu.mem_read(stack + 7, 1))[0])

    regs = rom_exec.registers
    machine.cpu.ctl_flush_tb()
    machine.cpu.hook_add(rom_exec.unicorn.UC_HOOK_CODE, note_sound, begin=0x4AD76, end=0x4AD76)
    machine.cpu.reg_write(regs.UC_M68K_REG_A2, 0x904000)
    machine.cpu.reg_write(regs.UC_M68K_REG_A3, 0x904A4E)
    machine.cpu.reg_write(regs.UC_M68K_REG_A6, rom_exec.STACK_TOP)
    machine.cpu.reg_write(regs.UC_M68K_REG_A7, rom_exec.STACK_TOP - 0x40)
    machine.cpu.emu_start(0x48364, 0x483FC, count=2_000_000)

    show_level_start_screen(state)
    if not reset_and_load_level(state, state.levelnum_current, maze_number=state.mazenum_current):
        return "gauntpy could not load it", {}
    heard = len(state.sound_log)
    # The ROM's sounds above were not noted until the speech, so compare only the speech.
    real_setup = thief.thief_setup

    def setup_and_mark(game: GameState) -> None:
        nonlocal heard
        real_setup(game)
        heard = len(game.sound_log)

    thief.thief_setup = setup_and_mark
    try:
        _spawn_level_players(state, list(range(len(characters))))
    finally:
        thief.thief_setup = real_setup

    found = differences(machine, state)
    if played != [sound & 0xFF for sound in state.sound_log[heard:]]:
        found["speech"].append(f"ROM {played} PY {state.sound_log[heard:]}")
    # A hero's record has no meaningful type word (0x0F against 0), as demo_compare notes.
    heroes = {player.mob_slot for player in state.players if player.mob_slot}
    for kind in ("link", "state"):
        kept = [row for row in found.get(kind, ()) if int(row.split()[1].rstrip(":"), 16) not in heroes]
        if kept:
            found[kind] = kept
        else:
            found.pop(kind, None)
    words = {
        "thief_enter_time": (machine.r16(0x904B9E), state.thief_enter_time & 0xFFFF),
        "thief_victim": (machine.r16(0x904B9A), state.thief_victim & 0xFFFF),
        "spawn_bonus": (machine.r8(0x90405F), state.monster_spawn_probability_bonus & 0xFF),
        "next_potion": (machine.r16(0x904B7E), state.level_next_potion & 0xFFFF),
        "players_active": (machine.r16(0x904928), state.level_players_active),
    }
    for i in range(len(characters)):
        words[f"hero_slot[{i}]"] = (machine.r16(0x9048C8 + 2 * i), state.players[i].mob_slot)
    for name, (rom, python) in words.items():
        if rom != python:
            found[name].append(f"ROM {rom:#x} PY {python:#x}")
    return "", found


def _rom_with_party(state: GameState) -> rom_exec.RomMachine:
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.install_slapstic()
    for index, word in enumerate(state.alpha_ram[:64 * 30]):
        machine.w16(0x905000 + 2 * index, word)
    for address, value in (
        (0x904000, state.mazenum_current), (0x904004, state.levelnum_current),
        (0x9049E2, state.two_player_mode), (0x904A24, state.game_settings),
        (0x904B7C, state.attract_timer & 0xFFFF), (0x904A4E, state.global_delay_timer),
        (0x904B7E, state.level_next_potion), (0x904B80, state.level_next_treasure),
        (0x904878, state.secret_possible_counter), (0x904B52, state.level_next),
        (0x904018, state.treas_mazerand_num),
    ):
        machine.w16(address, value)
    machine.w8(0x904063, state.secret_player & 0xFF)
    machine.w8(0x90405F, state.monster_spawn_probability_bonus & 0xFF)
    for i, player in enumerate(state.players):
        machine.w8(0x9049A0 + i, player.status)
        machine.w16(0x9048C8 + 2 * i, player.mob_slot)
        machine.cpu.mem_write(0x904980 + 4 * i, player.health.to_bytes(4, "big", signed=True))
        machine.cpu.mem_write(0x904990 + 4 * i, player.score.to_bytes(4, "big"))
        machine.w16(0x904B2A + 2 * i, player.coin_count)
        machine.w16(0x9048E8 + 2 * i, int(player.character))
        machine.w16(0x904A26 + 2 * i, player.state_timer)
    return machine


def _rom_press(machine: rom_exec.RomMachine, player: int) -> bool:
    """main_start_game's decision for an accepted Magic press, 0x484A8 to where its arms meet."""
    cpu, regs = machine.cpu, rom_exec.registers
    cpu.reg_write(regs.UC_M68K_REG_D2, player)
    cpu.reg_write(regs.UC_M68K_REG_A2, 0x904000)
    cpu.reg_write(regs.UC_M68K_REG_A3, 0x904A4E)
    cpu.reg_write(regs.UC_M68K_REG_A6, rom_exec.STACK_TOP)
    cpu.reg_write(regs.UC_M68K_REG_A7, rom_exec.STACK_TOP - 0x40)
    cpu.reg_write(regs.UC_M68K_REG_SR, 0x2700)
    cpu.emu_start(0x484A8, 0x486EA, count=80_000_000)
    return cpu.reg_read(regs.UC_M68K_REG_PC) == 0x486EA


def _python_press(state: GameState, player: int) -> None:
    real = session._magic_press_edge
    session._magic_press_edge = lambda _state, index: index == player
    try:
        session.main_start_game(state)
    finally:
        session._magic_press_edge = real


def _after_a_press(machine: rom_exec.RomMachine, state: GameState) -> dict[str, list[str]]:
    found = differences(machine, state)
    heroes = {player.mob_slot for player in state.players if player.mob_slot}
    kept = [row for row in found.get("link", ()) if int(row.split()[1].rstrip(":"), 16) not in heroes]
    if kept:
        found["link"] = kept
    else:
        found.pop("link", None)
    for name, rom, python in (
        ("hero_status", machine.r8(0x9049A0), state.players[0].status),
        ("hero_slot", machine.r16(0x9048C8), state.players[0].mob_slot),
        ("players_active", machine.r16(0x904928), state.level_players_active),
        ("spawn_bonus", machine.r8(0x90405F), state.monster_spawn_probability_bonus & 0xFF),
    ):
        if rom != python:
            found[name].append(f"ROM {rom:#x} PY {python:#x}")
    for index in range(64 * 30):
        if index % 64 < 42 and machine.r16(0x905000 + 2 * index) != state.alpha_ram[index]:
            found["alpha"].append(
                f"row {index // 64} col {index % 64}: ROM {machine.r16(0x905000 + 2 * index):#x} "
                f"PY {state.alpha_ram[index]:#x}"
            )
    return found


def check_first_hero(maze: int, level: int, seed: int, pricing: int, attract_timer: int):
    """The first hero to press on a level part played: a continue, or free play."""
    state = new_state(level, seed)
    state.two_player_mode = pricing
    state.mazenum_current = maze
    state.level_next_treasure = 3
    state.level_next_potion = level % 4
    state.level_next = level + 1
    if not reset_and_load_level(state, level, maze_number=maze):
        return "gauntpy could not load it", {}
    state.rng.seed = (seed * 7 + 3) & 0xFFFF
    state.attract_timer = attract_timer
    state.global_delay_timer = 0
    player = state.players[0]
    player.status = int(PlayerStatus.SELECTING)
    player.health = 2000
    player.coin_count = 1
    player.mob_slot = 0
    player.character = 1
    state.pending_character[0] = 1
    state.level_players_active = 0
    state.alpha_ram[:] = [0x8000 if 29 <= i % 64 < 42 else 0 for i in range(len(state.alpha_ram))]
    machine = _rom_with_party(state)
    machine.call(0x40D4E, maze, count=100_000)
    if not _rom_press(machine, 0):
        return "ROM did not reach the end of the arm", {}
    _python_press(state, 0)
    return "", _after_a_press(machine, state)


def check_new_game(seed: int, character: int):
    """A paid game from the demo: start_attract_to_game (0x44204), a coin, then the press."""
    def fresh() -> GameState:
        state = GameState()
        state.game_mode = GameMode.DEMO
        state.rng.seed = seed
        state.two_player_mode = 1
        state.levelnum_current = 1
        state.mazenum_current = 0
        state.attract_timer = 300
        state.alpha_ram[:] = [0x8000 if 29 <= i % 64 < 42 else 0 for i in range(len(state.alpha_ram))]
        return state

    state = fresh()
    machine = _rom_with_party(state)
    machine.w16(0x904918, int(state.game_mode) & 0xFFFF)
    machine.call(0x44204, count=80_000_000)
    if not machine.halted:
        return "ROM did not finish starting the game", {}
    session.start_attract_to_game(state)
    found = {f"on the select screen: {kind}": rows for kind, rows in _after_a_press(machine, state).items()
             if kind not in ("hero_status", "hero_slot", "players_active")}
    if found:
        return "", found
    machine.call(0x488CA, 0, count=2_000_000)
    session.player_coindrop(state, 0)
    machine.w16(0x9048E8, character)
    state.pending_character[0] = character
    state.players[0].character = character
    machine.w16(0x904A4E, 0)
    state.global_delay_timer = 0
    if not _rom_press(machine, 0):
        return "ROM did not reach the end of the arm", {}
    _python_press(state, 0)
    return "", _after_a_press(machine, state)


def check_attract_screen(mode: int, seed: int, legend_page: int = 2) -> list[str]:
    """start_attract_screen (0x44414) and, below page 2, load_legend_page (0x4CD1C)."""
    state = GameState()
    state.game_mode = int(GameMode.TITLE)
    state.rng.seed = seed
    state.levelnum_current = 1
    state.two_player_mode = 1
    state.attract_count = 1
    state.title_intro_state = 3
    state.attract_legend = 2
    score.high_scores(state)
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    machine.install_slapstic()
    machine.w16(0x904918, int(state.game_mode) & 0xFFFF)
    machine.w16(0x904004, 1)
    machine.w16(0x904000, 0)
    machine.w16(0x9049E2, 1)
    machine.w16(0x904B60, state.attract_count)
    machine.w16(0x90491A, 2)
    machine.cpu.mem_write(0x904FFC, (0x100000).to_bytes(4, "big"))
    for klass in range(4):
        for rank, (value, initials) in enumerate(state.high_scores[klass]):
            machine.cpu.mem_write(
                0x100000 + 0x1E + klass * 0x32 + rank * 5,
                value.to_bytes(3, "big") + encode_initials(initials).to_bytes(2, "big"),
            )
    machine.call(0x44414, mode & 0xFFFFFFFF, count=120_000_000)
    attract.start_attract_screen(state, mode)
    if mode == int(GameMode.LEGEND):
        for page in range(1, legend_page - 1, -1):
            machine.w16(0x90491A, page)
            machine.call(0x4CD1C, page, count=80_000_000)
            state.attract_legend = page
            attract.load_legend_page(state)
    if not machine.halted:
        return [f"ROM did not return (fault {machine.fault_pc})"]
    out = []
    for name, rom, python in (
        ("mode", machine.r16(0x904918), int(state.game_mode) & 0xFFFF),
        ("seed", machine.r16(0x904BFC), state.rng.seed & 0xFFFF),
        ("maze", machine.r16(0x904000), state.mazenum_current),
        ("timer", machine.r16(0x904B7C), state.attract_timer & 0xFFFF),
        ("scroll", (machine.r16(0x904008), machine.r16(0x90400A)), (state.scroll_x, state.scroll_y)),
    ):
        if rom != python:
            out.append(f"{name}: ROM {rom} PY {python}")
    for index in range(64 * 30):
        if index % 64 < 42 and machine.r16(0x905000 + 2 * index) != state.alpha_ram[index]:
            out.append(f"alpha row {index // 64} col {index % 64}: ROM "
                       f"{machine.r16(0x905000 + 2 * index):#x} PY {state.alpha_ram[index]:#x}")
    for slot in range(32, 1024):
        rom_record = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot))
        our_record = (state.mobs.picture[slot], state.mobs.hpos[slot], state.mobs.vpos[slot])
        if (rom_record[0] or our_record[0]) and rom_record != our_record:
            out.append(f"record {slot:#x}: ROM {rom_record} PY {our_record}")
    if state.maze is not None:
        for index in range(64 * 64):
            if machine.r16(0x900000 + 2 * index) != state.playfield_ram[index]:
                out.append(f"playfield [{index:#x}]")
                break
    return out


def panel_state(rng: random.Random) -> GameState:
    state = GameState()
    state.game_mode = rng.choice((0, 0, 0, 0, -3, -1))
    state.levelnum_current = rng.choice((2, 8, 60))
    state.mazenum_current = rng.choice((20, 20, 106, 115))
    state.level_next = rng.randint(2, 99)
    state.two_player_mode = rng.choice((0, 1))
    state.game_settings = rng.choice((0, 0x100, 0x200, 0x300, 0x400, 0x403, 0x1F))
    for player in state.players:
        player.status = rng.choice((0, 0, 1, 1, 1, 2, 8, 0x10, 0x20))
        player.health = rng.choice((0, 500, 150)) if player.status else 0
        player.mob_slot = 100 + state.players.index(player) if player.status in (1, 8) else 0
        player.coin_count = rng.choice((0, 1, 2, 3))
        player.score = rng.choice((0, 1200, 99999))
        player.keysnum = rng.randint(0, 6)
        player.potionsnum = rng.randint(0, 6)
        player.character = rng.randint(0, 3)
        player.powers = rng.choice((0, 1, 0x3F, 0x15))
        player.state_timer = rng.choice((0xFFFF, 0xFFFF, 0, 9))
        player.bonusmult = rng.choice((1, 3))
    return state


def check_panel(rng: random.Random) -> list[str]:
    """setup_infopanel (0x452D0) on a random party, compared across the panel's columns."""
    state = panel_state(rng)
    selector = rng.choice((-1, -1, 0, 1, 2, 3))
    machine = rom_exec.RomMachine.from_state(copy.deepcopy(state))
    for index, word in enumerate(state.alpha_ram[:64 * 30]):
        machine.w16(0x905000 + 2 * index, word)
    machine.w16(0x9049E2, state.two_player_mode)
    machine.w16(0x904A24, state.game_settings)
    machine.w16(0x904918, int(state.game_mode) & 0xFFFF)
    machine.w16(0x904004, state.levelnum_current)
    machine.w16(0x904000, state.mazenum_current)
    machine.w16(0x904B52, state.level_next)
    for i, player in enumerate(state.players):
        machine.w8(0x9049A0 + i, player.status)
        machine.w16(0x9048C8 + 2 * i, player.mob_slot)
        machine.cpu.mem_write(0x904980 + 4 * i, player.health.to_bytes(4, "big", signed=True))
        machine.cpu.mem_write(0x904990 + 4 * i, player.score.to_bytes(4, "big"))
        machine.w16(0x904A26 + 2 * i, player.state_timer)
    machine.call(0x452D0, selector & 0xFFFFFFFF, count=3_000_000)
    if not machine.halted:
        return [f"ROM did not return (fault {machine.fault_pc})"]
    setup_infopanel(state, selector)
    return [
        f"row {row}: ROM {rom} PY {python}"
        for row in range(30)
        if (rom := [machine.r16(0x905000 + 2 * (row * 64 + c)) for c in range(29, 42)])
        != (python := list(state.alpha_ram[row * 64 + 29:row * 64 + 42]))
    ]


def python_load(state: GameState, maze: int) -> bool:
    if not reset_and_load_level(state, state.levelnum_current, maze_number=maze):
        return False
    secret_new_level_setup(state)      # gauntpy's half of 0x438AE that runs with the party
    return True


def differences(machine: rom_exec.RomMachine, state: GameState) -> dict[str, list[str]]:
    """What differs, by kind, in the order a reader should look at it."""
    found: dict[str, list[str]] = collections.defaultdict(list)
    r16 = machine.r16

    def scalar(name: str, rom: int, python: int) -> None:
        if rom != python:
            found[name].append(f"ROM {rom:#x} PY {python:#x}")

    scalar("seed", r16(0x904BFC), state.rng.seed & 0xFFFF)
    scalar("secret_trick_id", machine.r8(0x904065), state.secret_trick_id & 0xFF)
    scalar("secret_player", machine.r8(0x904063), state.secret_player & 0xFF)
    for i, byte in enumerate((state.level_flags, state.level_flags_2, state.level_flags_3, state.level_flags_4)):
        scalar(f"level_flags[{i}]", machine.r8(0x90491C + i), byte & 0xFF)
    # 0x9049DE is the chain's tail; gauntpy stores the head and walks to the same end.
    scalar("depth_list_tail", r16(0x9049DE), list(state.mobs.iter_chain())[-1])
    scalar("player_start_slot", r16(0x9049E0), state.maze_player_start_slot & 0xFFFF)
    scalar("scroll_h", r16(0x904AC2), ((state.scroll_x - 8) << 7) & 0xFFFF)
    scalar("scroll_v", r16(0x904AC4), ((0x108 - state.scroll_y) << 7) & 0xFFFF)
    scalar("next_treasure_room", r16(0x904B80), state.level_next_treasure & 0xFFFF)
    scalar("random_wall_timer", r16(0x9048A6), state.random_wall_timer & 0xFFFF)
    scalar("exit_count", r16(0x904A06), len(state.exit_slots))
    scalar("tport_count", r16(0x904B84), len(_tport_pos_table(state)))
    if state.maze is not None:
        scalar("floorpattern", r16(0x904B5C), int(state.maze.floorpattern))
        scalar("wallpattern", r16(0x904B5E), int(state.maze.wallpattern))
    for i, slot in enumerate(state.exit_slots):
        scalar(f"exit_slots[{i}]", r16(0x910740 + 2 * i), slot)
    for i, slot in enumerate(_tport_pos_table(state)):
        scalar(f"tport_slots[{i}]", r16(0x910700 + 2 * i), slot)
    for i, word in enumerate(state.forcefield_segment_table):
        scalar(f"forcefield segment {i}", r16(0x910780 + 2 * i), word)
    if state.level_flags_3 & 0x08:
        for i in range(8, 256):
            scalar(f"cycle_codes[{i}]", machine.r8(0x910600 + i), state.cyclic_wall_assignments[i] & 0xFF)
    # The ROM's bookmark for a row is entry (row + 1) * 2 (0x5DE90-0x5DE98); gauntpy's is row * 2.
    for band in range(2, 64):
        scalar(f"slip_heads[{band}]", r16(0x905F80 + 2 * band), state.mobs.slip_heads[band - 2] & 0xFFFF)
    mobs = state.mobs
    for slot in range(32, 1024):
        rom = (machine.picture(slot), machine.hpos(slot), machine.vpos(slot))
        python = (mobs.picture[slot], mobs.hpos[slot], mobs.vpos[slot])
        if not (rom[0] or python[0]):     # an empty record's stale position words mean nothing
            continue
        if rom != python:
            found["record"].append(f"slot {slot:#x}: ROM {tuple(map(hex, rom))} PY {tuple(map(hex, python))}")
        rom_link, py_link = r16(rom_exec._LINK + 2 * slot), mobs.link[slot] & 0xFFFF
        if rom_link != py_link:
            found["link"].append(f"slot {slot:#x}: ROM {rom_link:#x} PY {py_link:#x}")
        rom_state, py_state = r16(rom_exec._STATE + 2 * slot), mobs.state_link[slot] & 0xFFFF
        if py_link >> 10 in MONSTERS:     # gauntpy's compass is two steps round from the ROM's
            field = py_state >> 10
            py_state = (py_state & 0x3FF) | (((field & 0x38) | (((field & 7) + 2) & 7)) << 10)
        if rom_state != py_state:
            found["state"].append(f"slot {slot:#x}: ROM {rom_state:#x} PY {py_state:#x}")
    for i in range(64 * 64):
        rom, python = r16(0x900000 + 2 * i), state.playfield_ram[i]
        if rom != python:
            found["playfield"].append(f"[{i:#x}] ROM {rom:#x} PY {python:#x}")
    return found


def check(maze: int, level: int, seed: int, task: int = 0) -> tuple[str, dict[str, list[str]]]:
    state = new_state(level, seed, task)
    rom_state = new_state(level, seed, task)
    machine = rom_load(rom_state, maze)
    if not machine.halted:
        return f"ROM did not return (pc {machine.cpu.reg_read(rom_exec.registers.UC_M68K_REG_PC):#x})", {}
    if not python_load(state, maze):
        return "gauntpy could not load it", {}
    return "", differences(machine, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--maze", type=int, action="append")
    parser.add_argument("--level", type=int, action="append")
    parser.add_argument("--seed", type=lambda text: int(text, 0), action="append")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    kinds: collections.Counter[str] = collections.Counter()
    runs = bad = 0
    for maze in args.maze or MAZES:
        for level in args.level or LEVELS:
            for seed in args.seed or SEEDS:
                runs += 1
                # A secret room is only ever entered with a challenge task chosen (0x44DD6).
                task = 0x50 + seed % 14 if maze >= 115 else 0
                error, found = check(maze, level, seed, task)
                if error:
                    bad += 1
                    kinds[error.split(" (")[0]] += 1
                    print(f"maze {maze} level {level} seed {seed:#x}: {error}")
                    continue
                if found:
                    bad += 1
                    kinds.update(kind.split("[")[0] for kind in found)
                    if args.show:
                        print(f"maze {maze} level {level} seed {seed:#x}")
                        for kind, rows in found.items():
                            print(f"  {kind} ({len(rows)}): {rows[:3]}")
    for maze in args.maze or range(104):
        for level in args.level or LEVELS:
            for seed in args.seed or SEEDS:
                for next_treasure in (3, 0):
                    runs += 1
                    error, found = check_start_screen(maze, level, seed, next_treasure)
                    if error or found:
                        bad += 1
                        kinds.update((error.split(" (")[0],) if error else (k.split("[")[0] for k in found))
                        print(f"maze {maze} level {level} seed {seed:#x} screen next_treasure {next_treasure}: {error}")
                        if args.show:
                            for kind, rows in found.items():
                                print(f"  {kind} ({len(rows)}): {rows[:3]}")
    for maze in args.maze or range(5, 102, 5):
        for level in args.level or (2, 8, 13, 30, 61):
            for seed in args.seed or SEEDS[:3]:
                for characters in PARTIES:
                    for settings, bonus in ((0, 0), (0xC0, 3), (0x40, 0xFE)):
                        runs += 1
                        error, found = check_party(maze, level, seed, characters, settings, bonus)
                        if error or found:
                            bad += 1
                            kinds.update((error,) if error else (k.split("[")[0] for k in found))
                            print(f"maze {maze} level {level} seed {seed:#x} party {characters} "
                                  f"settings {settings:#x} bonus {bonus:#x}: {error}")
                            if args.show:
                                for kind, rows in found.items():
                                    print(f"  {kind} ({len(rows)}): {rows[:3]}")
    for maze in args.maze or (5, 14, 30, 39, 47, 60, 77, 90):
        for level in args.level or (2, 8, 13, 30):
            for seed in args.seed or SEEDS[:3]:
                for pricing, timer in ((1, 0x5DD), (0, 0x5DD), (0, 0xFFFF)):
                    runs += 1
                    error, found = check_first_hero(maze, level, seed, pricing, timer)
                    if error or found:
                        bad += 1
                        kinds.update((error,) if error else (k.split("[")[0] for k in found))
                        print(f"maze {maze} level {level} seed {seed:#x} first hero pricing {pricing} "
                              f"timer {timer:#x}: {error}")
    for seed in args.seed or (*SEEDS, 99, 0xFFFE):
        for character in range(4):
            runs += 1
            error, found = check_new_game(seed, character)
            if error or found:
                bad += 1
                kinds.update((error,) if error else (k.split("[")[0] for k in found))
                print(f"new game seed {seed:#x} character {character}: {error}")
    for mode, pages in ((GameMode.TITLE, (2,)), (GameMode.SCORES, (2,)), (GameMode.DEMO, (2,)),
                        (GameMode.LEGEND, (2, 1, 0))):
        for page in pages:
            for seed in args.seed or SEEDS:
                runs += 1
                found = check_attract_screen(int(mode), seed, page)
                if found:
                    bad += 1
                    kinds[f"attract {mode.name}"] += 1
                    print(f"attract {mode.name} page {page} seed {seed:#x}: {found[:3]}")
    rng = random.Random(1)
    panels = sum(bool(check_panel(rng)) for _ in range(3000))
    print(f"3000 panels, {panels} with differences")
    print(f"{runs} loads, {bad} with differences")
    for kind, count in kinds.most_common():
        print(f"  {kind}: {count}")
    return 1 if bad or panels else 0


if __name__ == "__main__":
    raise SystemExit(main())
