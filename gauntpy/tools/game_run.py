"""Run the whole game in the ROM and in gauntpy, in lockstep from a cold boot.

    python tools/game_run.py --frames 6000                      # attract, untouched
    python tools/game_run.py --play 1 --frames 8000             # a coin, a hero, random input
    python tools/game_run.py --pilot 4 --frames 30000           # four heroes, played through levels
    python tools/game_run.py --pilot 2 --warp --frames 30000    # each exit leads somewhere deep
    python tools/game_run.py --pilot 2 --coins 2 --rich --frames 30000  # heroes die, enter initials, play again

The ROM's main loop body (0x42A86-0x42B66) and VBLANK handler (0x4017E) run under Unicorn against
gauntpy's ``tick``, with the same raw input on the same frame. Each frame compares the records,
depth links, seed, playfield, alpha, sound requests and game words, and the run stops at the first
difference, because everything after it depends on it.

The ROM's boot runs for real but for the OS's EEPROM queue, which needs interrupts: its two
readers are stubbed and handed the settings gauntpy boots with. A difference is a lead, not a
verdict, though here both sides built their own RAM from the same input.

Needs GEX_ROM_DIR and the ROMs ``rom_exec.py`` needs.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
import random
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rom_exec  # noqa: E402
from rom_exec import registers  # noqa: E402
from gauntpy.game.constants import MONSTER_TYPES, GameMode, MazeObjIds, PlayerStatus  # noqa: E402
from gauntpy.game.mainloop import tick  # noqa: E402
from gauntpy.game.subsystems import sound  # noqa: E402
from gauntpy.game.subsystems.level_transitions import maze_checknum, player_exit_sequence  # noqa: E402
from gauntpy.game.subsystems.eeprom import encode_initials  # noqa: E402
from gauntpy.host.eeprom import PersistencePolicy  # noqa: E402
from gauntpy.host.startup import build_cold_boot_state  # noqa: E402

MONSTERS = {int(t) for t in MONSTER_TYPES}
_EXITS = {int(MazeObjIds.EXIT), int(MazeObjIds.EXITTO6)}
_CLOSED = {int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT), int(MazeObjIds.WALL_MOVABLE)}
_GENERATORS = range(0x1C, 0x2E)
_STEPS = ((-32, 0xFF7F), (32, 0xFFBF), (-1, 0xFFDF), (1, 0xFFEF))     # up, down, left, right
_RTS = b"\x4e\x75"
_VBLANK_RTE = 0x4049E
_SCORE_TABLES = 0x100000
_IDLE = 0xFFFF
_STICK = (0xFFEF, 0xFFDF, 0xFFBF, 0xFF7F, 0xFFEF & 0xFF7F, 0xFFDF & 0xFF7F, 0xFFEF & 0xFFBF, 0xFFDF & 0xFFBF)


def _words(machine: rom_exec.RomMachine, address: int, count: int) -> tuple[int, ...]:
    return struct.unpack(f">{count}H", bytes(machine.cpu.mem_read(address, count * 2)))


def _sound_request_trampoline(state, sound_id: int) -> None:
    _lockstep_sound_request(state, sound_id)  # noqa: F821 - runs with sound.py's globals


class Lockstep:
    def __init__(self, seed: int = 0) -> None:
        self.state = build_cold_boot_state(seed, persistence_policy=PersistencePolicy.ISOLATED)
        self.machine = rom_exec.RomMachine()
        self.frame = 0
        self.coins = 0
        self.rom_sounds: list[int] = []
        self.python_sounds: list[int] = []
        self._boot_rom(seed)
        self._watch_sounds()

    def _watch_sounds(self) -> None:
        """Hear each side ask for a sound, before the queue or the sound CPU has a say."""
        def rom_request(cpu, _address, _size, _data) -> None:
            stack = cpu.reg_read(registers.UC_M68K_REG_A7)
            self.rom_sounds.append(cpu.mem_read(stack + 7, 1)[0])

        self.machine.cpu.hook_add(rom_exec.unicorn.UC_HOOK_CODE, rom_request, begin=0x4AD76, end=0x4AD76)

        def pin_stale_aim(cpu, address, size, data):
            # With no hero in sight 0x41810 aims from locals nothing wrote. They hold
            # whatever the last call to reach this stack depth left there, which the port
            # has no stack to reproduce, so both sides are given its commonest leftover.
            frame = cpu.reg_read(registers.UC_M68K_REG_A6)
            if struct.unpack(">h", cpu.mem_read(frame - 0xC, 2))[0] == -1:
                cpu.mem_write(frame - 0xA, struct.pack(">IHH", 0x00902000, 0x0090, 0x4066))
        self.machine.cpu.hook_add(rom_exec.unicorn.UC_HOOK_CODE, pin_stale_aim, begin=0x41810, end=0x41810)
        # Every caller holds this one function object, so it is wrapped in place.
        original = sound.sound_play
        passthrough = type(original)(original.__code__, original.__globals__, "sound_play_inner")

        def python_request(state, sound_id: int) -> None:
            self.python_sounds.append(sound_id & 0xFF)
            passthrough(state, sound_id)

        sound.__dict__["_lockstep_sound_request"] = python_request
        self._sound_code = original.__code__
        original.__code__ = _sound_request_trampoline.__code__

    def close(self) -> None:
        """Hand ``sound_play`` back: the wrapper outlives this object otherwise."""
        sound.sound_play.__code__ = self._sound_code
        sound.__dict__.pop("_lockstep_sound_request", None)

    def set_score(self, index: int, score: int) -> None:
        """A score the same on both sides, as the high-score table needs a large one."""
        self.state.players[index].score = score
        self.machine.cpu.mem_write(0x904990 + 4 * index, struct.pack(">I", score))

    def set_health(self, index: int, health: int) -> None:
        self.state.players[index].health = health
        self.machine.cpu.mem_write(0x904980 + 4 * index, struct.pack(">i", health))

    def aim(self, level: int, maze: int) -> None:
        """Send the next level somewhere else: both sides hold it in the same two words."""
        state = self.state
        state.level_next = level
        state.maze_next = maze
        maze_checknum(state)
        self.machine.w16(0x904B52, state.level_next)
        self.machine.w16(0x904B54, state.maze_next)
        # Level 6 seeds the treasure-room countdown (0x438E4), and a warp can jump over it.
        if not state.level_next_treasure:
            state.level_next_treasure = 3
            self.machine.w16(0x904B80, 3)

    def force_exit(self, player: int) -> None:
        """Walk a hero out on the spot, on both sides: some mazes hold a pilot for ever."""
        state = self.state
        slot = state.players[player].mob_slot
        self.machine.call(0x52B40, player, slot, int(MazeObjIds.EXIT), count=2_000_000)
        player_exit_sequence(state, player, slot, int(MazeObjIds.EXIT))

    def _boot_rom(self, seed: int) -> None:
        machine, state = self.machine, self.state
        machine.install_slapstic()
        machine.cpu.mem_write(0x42F86, _RTS)            # eeprom_load_config: the OS's queue
        # 0x444A4 re-reads the settings from the EEPROM every 13th title. There is no EEPROM here:
        # the settings stay as _load_settings wrote them, as the file does on the other side.
        machine.cpu.mem_write(0x444A4, bytes.fromhex("6022"))    # bra.b 0x444C8
        cpu = machine.cpu
        machine.w16(0x904BFC, seed)
        cpu.mem_write(rom_exec.STACK_TOP, struct.pack(">I", rom_exec.HALT))
        cpu.reg_write(registers.UC_M68K_REG_SR, 0x2700)
        cpu.reg_write(registers.UC_M68K_REG_A7, rom_exec.STACK_TOP)
        # game_start's four pointers, then one_time_init up to its first attract screen.
        cpu.emu_start(0x4014C, 0x40174, count=100)
        cpu.emu_start(0x4327A, 0x43300, count=2_000_000)
        cpu.reg_write(registers.UC_M68K_REG_PC, 0x43312)
        self._load_settings()
        cpu.emu_start(0x43312, 0x4334A, count=100_000)
        machine.call(0x44414, 0xFFFFFFFE, count=2_000_000)
        if not machine.halted:
            raise RuntimeError(f"ROM boot stopped at {cpu.reg_read(registers.UC_M68K_REG_PC):#x}")
        machine.cpu.mem_write(0x904FFC, struct.pack(">I", _SCORE_TABLES))
        # The sound board has answered its reset by now on a real cabinet. Nothing answers here,
        # and without that every sound would go through the ring (0x4AD7C), which matters:
        # the transporter's landing choice reads the A1 that the ring leaves (0x505AC).
        machine.w16(0x9049EE, 0)
        state.sound_holdoff = 0

    def _load_settings(self) -> None:
        """What eeprom_load_config and highscore_table_init leave, from gauntpy's own copy."""
        machine, state = self.machine, self.state
        for address, value in (
            (0x904A24, state.game_settings), (0x9049E2, state.two_player_mode),
            (0x904010, state.maze_number), (0x90400E, state.maze_stride),
            (0x904018, state.treas_mazerand_num), (0x904016, state.treas_mazerand_adder),
            (0x904B86, state.games_played_counter),
        ):
            machine.w16(address, value)
        machine.cpu.mem_write(0x904FFC, struct.pack(">I", _SCORE_TABLES))
        for klass, ladder in enumerate(state.high_scores):
            for rank, (value, initials) in enumerate(ladder):
                machine.cpu.mem_write(
                    _SCORE_TABLES + 0x1E + klass * 0x32 + rank * 5,
                    value.to_bytes(3, "big") + encode_initials(initials).to_bytes(2, "big"),
                )
        for player in range(4):
            machine.cpu.mem_write(0x904A3B + 4 * player, b"AAA")

    def coin(self, player: int) -> None:
        self.machine.cpu.mem_write(0x904FEC + player, b"\x01")
        field = 3 << (2 * player)
        self.coins = (self.coins & ~field) | ((self.coins + (1 << (2 * player))) & field)
        self.state.coin_counters = self.coins

    def step(self, raw: tuple[int, int, int, int]) -> None:
        machine, state = self.machine, self.state
        cpu = machine.cpu
        self.frame += 1
        self.rom_sounds.clear()
        self.python_sounds.clear()
        for index, word in enumerate(raw):
            machine.w16(0x803000 + 2 * index, word)
            state.player_input_raw[index] = word
        # The board has answered the last diagnostic poll: the OS is no longer waiting on it
        # (0x41A8), and it reported nothing wrong (0x42D40).
        machine.cpu.mem_write(0x904F94, bytes(4))
        machine.w16(0x9049F0, 0)
        # VBLANK, up to its rte: Unicorn cannot take that return here, and nothing needs it to.
        cpu.reg_write(registers.UC_M68K_REG_A7, rom_exec.STACK_TOP - 0x40)
        cpu.reg_write(registers.UC_M68K_REG_SR, 0x2700)
        # Bit 3 of this port means the self-test switch is off to VBLANK (0x4047E), but sends
        # init_display waiting for a VBLANK no interrupt will bring (0x434A2).
        machine.w16(0x803008, 0xFFFF)
        cpu.emu_start(0x4017E, _VBLANK_RTE, count=2_000_000)
        machine.w16(0x803008, 0)
        cpu.reg_write(registers.UC_M68K_REG_SR, 0x2300 | 0x0700)
        cpu.reg_write(registers.UC_M68K_REG_A2, 0x904002)
        cpu.reg_write(registers.UC_M68K_REG_A6, rom_exec.STACK_TOP)
        cpu.reg_write(registers.UC_M68K_REG_A3, rom_exec.STACK_TOP - 2)
        cpu.reg_write(registers.UC_M68K_REG_A7, rom_exec.STACK_TOP - 0x40)
        cpu.emu_start(0x42A86, 0x42B66, count=120_000_000)
        pc = cpu.reg_read(registers.UC_M68K_REG_PC)
        if pc != 0x42B66:
            raise RuntimeError(f"frame {self.frame}: ROM stopped at {pc:#x}")
        tick(state)
        # A level setup overruns its frame on the real machine (0x42B4E), and gauntpy models
        # that. A frame here is one pass of the loop and never overruns, so the ROM is told.
        machine.w16(0x904916, state.frame_overflow & 0xFFFF)

    def differences(self) -> list[str]:
        machine, state = self.machine, self.state
        mobs = state.mobs
        out: list[str] = []
        pictures = _words(machine, 0x902000, 1024)
        hpos = _words(machine, 0x902800, 1024)
        vpos = _words(machine, 0x903000, 1024)
        links = _words(machine, 0x903800, 1024)
        states = _words(machine, 0x904066, 1024)
        heroes = {player.mob_slot for player in state.players if player.mob_slot}
        mode = int(state.game_mode)
        for slot in range(1024):
            if not (pictures[slot] or mobs.picture[slot]):
                continue
            if (pictures[slot], hpos[slot], vpos[slot]) != (
                mobs.picture[slot] & 0xFFFF, mobs.hpos[slot] & 0xFFFF, mobs.vpos[slot] & 0xFFFF,
            ):
                out.append(f"record {slot:#x}: ROM {pictures[slot]:#x},{hpos[slot]:#x},{vpos[slot]:#x} "
                           f"PY {mobs.picture[slot]:#x},{mobs.hpos[slot]:#x},{mobs.vpos[slot]:#x}")
            if slot in heroes or slot < 32:
                continue
            if mode == GameMode.TITLE and not links[slot] >> 10 and mobs.link[slot] >> 10 == 0x0F:
                continue        # a hero's old record: its type is 0 on the ROM's side
            if links[slot] >> 10 != mobs.link[slot] >> 10:
                out.append(f"type {slot:#x}: ROM {links[slot] >> 10:#x} PY {mobs.link[slot] >> 10:#x}")
            field = (mobs.state_link[slot] >> 10) & 0x3F
            if links[slot] >> 10 in MONSTERS:
                field = (field & 0x38) | (((field & 7) + 2) & 7)
            # The title leaves the demo's state words under its own records, with
            # no type left to say which compass they are in.
            if mode != GameMode.TITLE and states[slot] >> 10 != field:
                out.append(f"state {slot:#x}: ROM {states[slot] >> 10:#x} PY {field:#x}")
        words = [
            ("seed", machine.r16(0x904BFC), state.rng.seed & 0xFFFF),
            ("frame", machine.r16(0x904006), state.frame_counter & 0xFFFF),
            ("mode", machine.r16(0x904918), int(state.game_mode) & 0xFFFF),
            ("level", machine.r16(0x904004), state.levelnum_current),
            ("maze", machine.r16(0x904000), state.mazenum_current),
            ("attract", machine.r16(0x904B7C), state.attract_timer & 0xFFFF),
            ("delay", machine.r16(0x904A4E), state.global_delay_timer & 0xFFFF),
            ("treasure", machine.r16(0x9049E8), state.treasure_timer & 0xFFFF),
            ("dialog", machine.r16(0x904A9E), state.dialog_timer & 0xFFFF),
            ("active", machine.r16(0x904928), state.level_players_active),
            ("scroll", (machine.r16(0x904008), machine.r16(0x90400A)), (state.scroll_x & 0xFFFF, state.scroll_y & 0xFFFF)),
        ]
        if mode >= 0:      # a new game sets the loot words, and gauntpy boots with them set
            words += [
                ("thief mode", machine.r16(0x904BA0), state.thief_mode & 0xFFFF),
                ("thief cell", machine.r16(0x904BA4), state.thief_current_pos & 0xFFFF),
                ("thief next", machine.r16(0x904BA6), state.thief_next_pos & 0xFFFF),
                ("thief previous", machine.r16(0x904BA2), state.thief_previous_pos & 0xFFFF),
                ("thief heading", machine.r16(0x904B9C), state.thief_direction & 0xFFFF),
                ("thief timer", machine.r16(0x904B9E), state.thief_enter_time & 0xFFFF),
                ("thief speed", machine.r16(0x9048BC), state.thief_speed & 0xFFFF),
                ("thief contact", machine.r16(0x904BB8), state.thief_collision_direction_code & 0xFFFF),
                ("thief count", machine.r16(0x904BBC), state.thief_stolen_item & 0xFFFF),
                ("thief carried", machine.r32(0x904BB4), state.thief_item_carried & 0xFFFFFFFF),
                ("mugger carried", machine.r32(0x904BB0), state.mugger_item_carried & 0xFFFFFFFF),
                ("thief next level", machine.r32(0x904BAC), state.thief_item_nextlevel & 0xFFFFFFFF),
                ("mugger next level", machine.r32(0x904BA8), state.mugger_item_nextlevel & 0xFFFFFFFF),
                ("next level", machine.r16(0x904B52), state.level_next & 0xFFFF),
                ("next maze", machine.r16(0x904B54), state.maze_next & 0xFFFF),
                ("treasure in", machine.r16(0x904B80), state.level_next_treasure & 0xFFFF),
                ("potion in", machine.r16(0x904B7E), state.level_next_potion & 0xFFFF),
                ("secret in", machine.r16(0x904878), state.secret_possible_counter & 0xFFFF),
                ("idle", machine.r16(0x90490C), state.idle_timer & 0xFFFF),
                ("escape", machine.r16(0x9048C6), state.escape_timer & 0xFFFF),
                ("spawn bonus", machine.r8(0x90405F), state.monster_spawn_probability_bonus & 0xFF),
            ]
        for index, player in enumerate(state.players):
            words += [
                (f"status{index}", machine.r8(0x9049A0 + index), int(player.status)),
                (f"slot{index}", machine.r16(0x9048C8 + 2 * index), player.mob_slot),
                (f"health{index}", struct.unpack(">i", bytes(machine.cpu.mem_read(0x904980 + 4 * index, 4)))[0], player.health),
                (f"score{index}", struct.unpack(">I", bytes(machine.cpu.mem_read(0x904990 + 4 * index, 4)))[0], player.score & 0xFFFFFFFF),
                (f"keys{index}", machine.r8(0x90405A + index), player.keysnum & 0xFF),
                (f"potions{index}", machine.r8(0x904055 + index), player.potionsnum & 0xFF),
                (f"powers{index}", machine.r16(0x9048E0 + 2 * index), player.powers & 0xFFFF),
                (f"coins{index}", machine.r16(0x904B2A + 2 * index), player.coin_count & 0xFFFF),
                (f"anim{index}", machine.r16(0x9049BC + 2 * index), player.anim_counter & 0xFFFF),
                (f"shoot{index}", machine.r16(0x9049B4 + 2 * index), state.player_shooting[index] & 0xFFFF),
                (f"stun{index}", machine.r16(0x904A54 + 2 * index), player.stundelay & 0xFFFF),
                (f"bonus{index}", machine.r16(0x90490E + 2 * index), player.bonusmult & 0xFFFF),
                (f"supershot{index}", machine.r8(0x905F68 + 1 * index), player.supershot & 0xFF),
                (f"invuln{index}", machine.r16(0x905F40 + 2 * index), player.invuln_timer & 0xFFFF),
                (f"invis{index}", machine.r16(0x905F50 + 2 * index), state.player_invis_timer[index] & 0xFFFF),
                (f"repulse{index}", machine.r16(0x905F38 + 2 * index), state.player_repulse_timer[index] & 0xFFFF),
                (f"dizzy{index}", machine.r16(0x905F48 + 2 * index), state.player_dizzy_timer[index] & 0xFFFF),
                (f"hurt{index}", machine.r16(0x905F30 + 2 * index), player.hurt_cooldown & 0xFFFF),
                (f"statetimer{index}", machine.r16(0x904A26 + 2 * index), player.state_timer & 0xFFFF),
                (f"character{index}", machine.r16(0x9048E8 + 2 * index), int(player.character) & 0xFFFF),
            ]
            if player.mob_slot:      # gauntpy only loads these words with the hero, as they first matter
                words += [
                    (f"moved{index}", machine.r16(0x9048F0 + 2 * index), state.player_joystick[index] & 0xFFFF),
                    (f"facing{index}", machine.r16(0x9049A4 + 2 * index), (player.direction + 2) & 7),
                    # The latch holds a facing plus one, in each side's own compass.
                    (f"fight{index}", machine.r16(0x9049AC + 2 * index),
                     ((state.player_fighting_dir[index] + 1) & 7) + 1 if state.player_fighting_dir[index] else 0),
                    (f"pending{index}", machine.r16(0x904AD6 + 2 * index), player.pending_damage & 0xFFFF),
                    (f"cumulative{index}", machine.r16(0x904ADE + 2 * index), player.cumulative_damage & 0xFFFF),
                    (f"sampletimer{index}", machine.r16(0x904AE6 + 2 * index), player.damage_sample_timer & 0xFFFF),
                    (f"samplecount{index}", machine.r16(0x904AEE + 2 * index), player.damage_sample_count & 0xFFFF),
                ]
        out += [f"{name}: ROM {rom} PY {python}" for name, rom, python in words if rom != python]
        if self.rom_sounds != self.python_sounds:
            out.append(f"sounds: ROM {[hex(s) for s in self.rom_sounds]} PY {[hex(s) for s in self.python_sounds]}")
        if mode >= 0:
            grid = bytes(machine.cpu.mem_read(0x905054, 0xC00))
            # Only the offscreen columns are the thief's: the rest of the span is the alpha below.
            bad = [
                i for i in range(0xC00)
                if (0x54 + i) % 0x80 >= 84 and grid[i] != state.path_direction_grid[i]
            ]
            if bad:
                at = bad[0]
                out.append(f"route grid [{at:#x}]: ROM {grid[at]:#x} PY {state.path_direction_grid[at]:#x} ({len(bad)} bytes)")
        alpha = _words(machine, 0x905000, 64 * 30)
        bad = [i for i in range(64 * 30) if i % 64 < 42 and alpha[i] != state.alpha_ram[i]]
        if bad:
            at = bad[0]
            out.append(f"alpha row {at // 64} col {at % 64}: ROM {alpha[at]:#x} PY {state.alpha_ram[at]:#x} ({len(bad)} cells)")
        playfield = _words(machine, 0x900000, 64 * 64)
        bad = [i for i in range(64 * 64) if playfield[i] != state.playfield_ram[i]]
        if bad:
            at = bad[0]
            out.append(f"playfield [{at:#x}]: ROM {playfield[at]:#x} PY {state.playfield_ram[at]:#x} ({len(bad)} words)")
        return out


def script(rng: random.Random, frames: int, play: bool):
    """Raw input per frame, and on which frame a coin drops."""
    held = _IDLE
    until = 0
    for frame in range(1, frames + 1):
        if not play or frame < 60:
            yield frame, _IDLE, frame == 20 and play
            continue
        if frame < 64:
            yield frame, _IDLE & ~1, False      # Magic, which starts the hero
            continue
        if frame >= until:
            until = frame + rng.randint(5, 80)
            held = rng.choice(_STICK)
            if rng.random() < 0.5:
                held &= ~2                      # hold Fire too
            if rng.random() < 0.1:
                held &= ~1                      # Magic
        yield frame, held, False


def _towards(state, start: int, wanted: set[int]) -> int:
    """The stick that starts the shortest walk from a cell to one of the wanted cells, or idle."""
    mobs = state.mobs
    seen = {start: _IDLE}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell in wanted:
            return seen[cell]
        for step, stick in _STEPS:
            row, column = cell >> 5, cell & 0x1F
            if step in (-1, 1):
                column = (column + step) & 0x1F
            else:
                row = (row + step // 32) & 0x1F
            next_cell = row << 5 | column
            if next_cell in seen or next_cell < 0x20:
                continue
            blocked = mobs.picture[next_cell] & 0x8000 or mobs.obj_type(next_cell) in _CLOSED
            if blocked and next_cell not in wanted:
                continue
            seen[next_cell] = stick if cell == start else seen[cell]
            queue.append(next_cell)
    return _IDLE


class Pilot:
    """Heroes who join, stay fed, and walk to exits, items and monsters.

    It reads only gauntpy's state, which equals the ROM's until the run stops, and the same
    input goes to both sides. With ``coins`` each hero has only that many per game, so heroes
    die, work the initials editor when they qualify, and come back from attract for another game.
    """

    def __init__(self, rng: random.Random, heroes: int, coins: int | None = None) -> None:
        self.rng = rng
        self.heroes = heroes
        self.coins = coins
        self.paid = [0] * 4
        self.goal = ["exit"] * 4
        self.until = [0] * 4
        self.jitter = [0] * 4
        self.stick = [_IDLE] * 4
        self.last_cell = [0] * 4
        self.still = [0] * 4
        self.fed = [0] * 4
        self.level = 0
        self.arrived = 0
        self.target = (0, 0)
        self.patience = 3000

    def _targets(self, state, goal: str) -> set[int]:
        mobs = state.mobs
        cells = set()
        for cell in range(0x20, 1024):
            if not mobs.picture[cell]:
                continue
            kind = mobs.obj_type(cell)
            if (
                (goal == "exit" and kind in _EXITS)
                or (goal == "monster" and (kind in MONSTERS or kind in _GENERATORS))
                or (goal == "item" and 0x2E <= kind <= 0x3E)
                or (goal == "key" and kind == MazeObjIds.KEY)
                or (goal == "door" and kind in (MazeObjIds.DOOR_HORIZ, MazeObjIds.DOOR_VERT))
                or (goal == "wall" and kind == MazeObjIds.WALL_MOVABLE)
            ):
                cells.add(cell)
        return cells

    def _hero(self, frame: int, state, index: int) -> int:
        rng, player = self.rng, state.players[index]
        cell = player.mob_slot
        if not player.active or cell < 0x20:
            return _IDLE & ~1 if frame % 20 < 4 else _IDLE      # Magic starts a hero
        if frame >= self.until[index]:
            self.until[index] = frame + rng.randint(120, 600)
            # A hero with a key looks for a door, and one without looks for a key.
            lock = "door" if player.keysnum else "key"
            self.goal[index] = rng.choices(("exit", "item", "monster", lock, "wall"), (5, 2, 1, 4, 1))[0]
        self.still[index] = self.still[index] + 1 if cell == self.last_cell[index] else 0
        self.last_cell[index] = cell
        if self.still[index] > 40:                              # stuck on a corner
            self.still[index] = 0
            self.jitter[index] = frame + rng.randint(5, 30)
            self.stick[index] = rng.choice(_STICK)
        if frame >= self.jitter[index]:
            self.stick[index] = _towards(state, cell, self._targets(state, self.goal[index]))
            if self.stick[index] == _IDLE:
                self.stick[index] = rng.choice(_STICK)
        word = self.stick[index]
        if self.goal[index] == "monster" and frame % 16 < 10:
            word &= ~2                                          # Fire
        if rng.random() < 0.002:
            word &= ~1                                          # Magic
        return word

    def warp(self, lockstep: Lockstep, frame: int) -> None:
        """Send the party somewhere deep from each ordinary level, after a while if need be."""
        state = lockstep.state
        if state.levelnum_current != self.level:
            self.level = state.levelnum_current
            self.arrived = frame
            self.target = (self.rng.randint(7, 400), self.rng.randint(5, 0x65))
        if state.mazenum_current >= 0x68:
            return
        # Each hero's exit computes the next level again, so this holds to the last one.
        if any(player.exit_pending for player in state.players):
            lockstep.aim(*self.target)
        elif frame - self.arrived > self.patience:
            for player in state.players:
                if player.active and player.mob_slot >= 0x20 and state.player_tport_phase[player.index] < 0:
                    lockstep.force_exit(player.index)
            lockstep.aim(*self.target)

    def _initials(self, frame: int) -> int:
        """A press now and then, and a push of the stick between them."""
        beat = frame % 48
        if beat < 3:
            return self.rng.choice((_IDLE & ~1, _IDLE & ~2))
        if 12 <= beat < 12 + self.rng.randint(1, 20):
            return self.rng.choice((0xFFDF, 0xFFEF))
        return _IDLE

    def inputs(self, frame: int, state) -> tuple[tuple[int, int, int, int], list[int]]:
        coins = []
        raw = [_IDLE] * 4
        if self.coins is not None and state.game_mode < 0 and frame % 400 == 0:
            self.paid = [0] * 4
        for index in range(self.heroes):
            player = state.players[index]
            if (
                frame >= 20 + 10 * index and player.health < 500 and frame >= self.fed[index]
                and (self.coins is None or self.paid[index] < self.coins)
            ):
                coins.append(index)
                self.paid[index] += 1
                self.fed[index] = frame + 90
            if self.coins is not None and player.status == PlayerStatus.DYING:
                raw[index] = self._initials(frame)
            else:
                raw[index] = self._hero(frame, state, index)
        return tuple(raw), coins


def run(
    frames: int, play: bool, seed: int, heroes: int = 0, warp: bool = False,
    coins: int | None = None, rich: bool = False,
) -> tuple[int, list[str]]:
    lockstep = Lockstep(seed)
    try:
        return _fly(lockstep, frames, play, seed, heroes, warp, coins, rich)
    finally:
        lockstep.close()


def _fly(
    lockstep: Lockstep, frames: int, play: bool, seed: int, heroes: int, warp: bool,
    coins: int | None, rich: bool,
) -> tuple[int, list[str]]:
    rng = random.Random(seed)
    found = lockstep.differences()
    if found:
        return 0, found
    if heroes:
        pilot = Pilot(rng, heroes, coins)
        for frame in range(1, frames + 1):
            if rich and frame == 100:
                for index, player in enumerate(lockstep.state.players):
                    if player.active:
                        lockstep.set_score(index, 3_000_000 + index * 1000)
            raw, due = pilot.inputs(frame, lockstep.state)
            for player in due:
                lockstep.coin(player)
            lockstep.step(raw)
            found = lockstep.differences()
            if found:
                return frame, found
            if warp:
                pilot.warp(lockstep, frame)
        return frames, []
    for frame, raw, coin in script(rng, frames, play):
        if coin:
            lockstep.coin(0)
        lockstep.step((raw, _IDLE, _IDLE, _IDLE))
        found = lockstep.differences()
        if found:
            return frame, found
    return frames, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=3000)
    parser.add_argument("--play", type=int, default=0)
    parser.add_argument("--pilot", type=int, default=0, help="this many heroes, walked to goals")
    parser.add_argument("--warp", action="store_true", help="send each exit to a random deep level")
    parser.add_argument("--coins", type=int, help="this many coins per hero per game, so heroes die")
    parser.add_argument("--rich", action="store_true", help="a score high enough for the high-score table")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    frame, found = run(args.frames, bool(args.play), args.seed, args.pilot, args.warp, args.coins, args.rich)
    if found:
        print(f"first difference at frame {frame}:")
        print(*found[:14], sep="\n")
        print(f"... {len(found)} in all")
        return 1
    print(f"{frame} frames, no differences")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
