"""Run original game-ROM routines under Unicorn on a gauntpy GameState.

This executes the routine itself, so it answers "what does the ROM do in exactly
this situation?" without MAME. It needs the ``unicorn`` dev dependency and the
owner's local ``row9.bin``, ``row10.bin`` and ``row76.bin`` at the repository
root. Tests importing it skip when either is missing.

    machine = RomMachine.from_state(state)
    result = machine.call(0x511AC, slot, player_index)
    machine.record(slot)              # picture, H, V, type, state

Limits. It runs one routine against a reconstructed snapshot of RAM, not the
whole machine: there are no interrupts, and only the fields ``load_state``
copies are present. Fixtures can therefore produce false mismatches, usually
through zero positions, a hero without its palette nibble, or a slot/position
disagreement, so check any difference before believing it. It measures no
timing; use MAME for that.

Also usable as a pytest plugin that compares every ``player_try_move`` call in
the suite with the ROM (see ``rom_xcheck_plugin.py``).
"""

from __future__ import annotations

from pathlib import Path
import struct

import unicorn
from unicorn import m68k_const as registers

from gauntpy.game.coords import native_v
from gauntpy.game.subsystems.player_transport import _tport_pos_table

REPO_ROOT = Path(__file__).resolve().parents[2]
ROM_FILES = {"row9.bin": 0x00000, "row10.bin": 0x38000, "row76.bin": 0x40000}

HALT = 0x5FFF0
STACK_TOP = 0x10F000
_PICTURE, _HPOS, _VPOS, _LINK, _STATE = (
    0x902000, 0x902800, 0x903000, 0x903800, 0x904066,
)


def roms_available() -> bool:
    return all((REPO_ROOT / name).exists() for name in ROM_FILES)


class RomMachine:
    """A 68000 with the ROMs and RAM mapped, ready to call game routines."""

    def __init__(self) -> None:
        cpu = unicorn.Uc(unicorn.UC_ARCH_M68K, unicorn.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(registers.UC_CPU_M68K_M68000)
        cpu.mem_map(0x0, 0x60000)
        for name, base in ROM_FILES.items():
            cpu.mem_write(base, (REPO_ROOT / name).read_bytes())
        cpu.mem_write(HALT, b"\x60\xfe")          # bra.s self
        cpu.mem_map(0x800000, 0x200000)
        cpu.mem_map(0x100000, 0x10000)
        self.cpu = cpu
        self.halted = False
        self.fault_pc: int | None = None

    @classmethod
    def from_state(cls, state) -> "RomMachine":
        machine = cls()
        machine.load_state(state)
        return machine

    # --- RAM access ----------------------------------------------------------

    def w16(self, address: int, value: int) -> None:
        self.cpu.mem_write(address, struct.pack(">H", value & 0xFFFF))

    def r16(self, address: int) -> int:
        return struct.unpack(">H", bytes(self.cpu.mem_read(address, 2)))[0]

    def w8(self, address: int, value: int) -> None:
        self.cpu.mem_write(address, bytes([value & 0xFF]))

    def r8(self, address: int) -> int:
        return bytes(self.cpu.mem_read(address, 1))[0]

    def load_state(self, state) -> None:
        """Copy the fields movement, pickups and monsters read into RAM."""
        mobs = state.mobs
        for slot in range(1024):
            h, v = mobs.hpos[slot], mobs.vpos[slot]
            if mobs.picture[slot] and h == 0 and v == 0 and slot >= 32:
                # Fixtures that set only a picture: give the record the position
                # its cell implies, as a real maze record would carry.
                h = ((slot & 0x1F) * 16 << 7) & 0xFFFF
                v = (native_v((slot >> 5) * 16) << 7) & 0xFFFF
            self.w16(_PICTURE + 2 * slot, mobs.picture[slot])
            self.w16(_HPOS + 2 * slot, h)
            self.w16(_VPOS + 2 * slot, v)
            self.w16(_LINK + 2 * slot, mobs.link[slot])
            self.w16(_STATE + 2 * slot, mobs.state_link[slot])
        self.w16(0x904BFC, state.rng.seed)
        for i, player in enumerate(state.players):
            if player.active and player.mob_slot and (mobs.hpos[player.mob_slot] & 0xF) < 0xC:
                # Fixture heroes without the palette nibble the ROM reads them by.
                self.w16(_HPOS + 2 * player.mob_slot,
                         (mobs.hpos[player.mob_slot] & ~0xF) | (0xC + i))
            self.w16(0x9048C8 + 2 * i, player.mob_slot if player.active else 0)
            self.w16(0x9048E8 + 2 * i, int(player.character))
            self.w16(0x9048E0 + 2 * i, player.powers)
            self.w16(0x904A54 + 2 * i, player.stundelay)
            self.w16(0x904920 + 2 * i, state.player_input_raw[i])
            self.w16(0x9048B4 + 2 * i, state.player_deferred_move_flags[i])
            self.cpu.mem_write(0x904980 + 4 * i, struct.pack(">i", player.health))
            self.w8(0x9049A0 + i, int(player.status))
            self.w8(0x90405A + i, player.keysnum)
            self.w8(0x904055 + i, player.potionsnum)
            self.w16(0x904B2A + 2 * i, player.coin_count)
            self.w16(0x904BCE + 2 * i, state.player_tport_phase[i])
            self.w16(0x9049A4 + 2 * i, (player.direction + 2) & 7)
            self.w16(0x9049BC + 2 * i, player.anim_counter)
            # The latch is the facing plus one, on each side's own compass.
            fighting = state.player_fighting_dir[i]
            self.w16(0x9049AC + 2 * i, (fighting + 2) & 0xFFFF if fighting else 0)
        pads = _tport_pos_table(state)
        for i, pad in enumerate(pads):
            self.w16(0x910700 + 2 * i, pad)
        self.w16(0x904B84, len(pads))
        for i, player in enumerate(state.players):
            self.w16(0x90490E + 2 * i, player.bonusmult)
            self.w16(0x904BD8 + 2 * i, state.player_tile_or_tport_dest[i])
        self.w16(0x904B98, state.thief_victim_pos)
        self.w16(0x904B9A, state.thief_victim)
        self.w16(0x904B9E, state.thief_enter_time)
        self.w16(0x904BA0, state.thief_mode)
        self.w16(0x904BA2, state.thief_previous_pos)
        self.w16(0x904BA4, state.thief_current_pos)
        self.w16(0x904BA6, state.thief_next_pos)
        self.w16(0x904BBA, state.thief_start_location)
        self.w16(0x904BD6, state.thief_tport_timer)
        self.cpu.mem_write(0x904BA8, struct.pack(">I", state.mugger_item_nextlevel & 0xFFFFFFFF))
        self.cpu.mem_write(0x904BAC, struct.pack(">I", state.thief_item_nextlevel & 0xFFFFFFFF))
        self.cpu.mem_write(0x904BB0, struct.pack(">I", state.mugger_item_carried & 0xFFFFFFFF))
        self.cpu.mem_write(0x904BB4, struct.pack(">I", state.thief_item_carried & 0xFFFFFFFF))
        self.cpu.mem_write(0x9049E4, struct.pack(">I", state.dialog_first_encounter_flags))
        self.w16(0x90487E, state.dialog_once_flags)
        self.w16(0x904A9E, state.dialog_timer)
        self.w8(0x90404A, state.thief_path_direction)
        self.w16(0x904B9C, state.thief_direction)
        self.w8(0x904060, state.thief_pursuit_direction)
        self.w8(0x904061, state.thief_pursuit_player)
        self.w8(0x904062, state.thief_pursuit_shot_direction)
        self.w16(0x9048B0, state.thief_direction_change_pos)
        self.w16(0x9048BC, state.thief_speed)
        self.w16(0x904BB8, state.thief_collision_direction_code)
        self.w16(0x904BBC, state.thief_stolen_item)
        self.w16(0x904BBE, state.thief_tport_active)
        self.w16(0x904BCC, state.thief_tport_saved_picture)
        self.w16(0x904BE0, state.thief_tport_dest)
        for address, value in (
            (0x90487C, state.dragon_fire_cooldown), (0x904880, state.dragon_hits),
            (0x904882, state.dragon_head_hpos), (0x904884, state.dragon_head_vpos),
            (0x904886, state.dragon_path_num), (0x90488C, state.dragon_move_state),
            (0x90488E, state.dragon_facing), (0x904890, state.dragon_state),
            (0x904892, state.dragon_anim_ctr),
        ):
            self.w16(address, value)
        self.w16(0x90486E, state.secret_need_hint)
        for i in range(4):
            self.w16(0x9048BE + 2 * i, state.reflect_count[i])
            self.w16(0x9048A8 + 2 * i, state.player_shot_last_wall_pos[i])
        for slot, key in enumerate(state.mobs.depth_key):
            self.w16(0x904940 + 2 * slot, key)
        self.w16(0x904B56, state.special_bonus_score)
        for i, slot in enumerate(state.dragon_seg_mob_ids):
            self.w16(0x904894 + 2 * i, slot)
        for channel in range(4, 12):
            owner = state.shot_owner_mob[channel]
            self.w16(0x9048C8 + 2 * channel, owner if owner >= 0 else 0)
        for channel, counter in enumerate(state.shot_anim_lifetime_counter):
            self.w16(0x904B02 + 2 * channel, counter)
        for i, timer in enumerate(state.shot_timer_next):
            self.w16(0x90492A + 2 * i, timer)
        for i, direction in enumerate(state.shot_direction):
            self.w16(0x9049C4 + 2 * i, direction)
        # The route grid and the transporter route words live in the alpha
        # workspace past column 41 (0x50FD2, 0x510BC).
        self.cpu.mem_write(0x905054, bytes(state.path_direction_grid))
        for pad in range(1, len(state.tport_route_forward)):
            offset = (pad // 22) * 0x80 + (pad % 22) * 2
            self.w16(0x905C54 + offset, state.tport_route_forward[pad])
            self.w16(0x905D54 + offset, state.tport_route_reverse[pad])
        self.w16(0x9049DC, state.player_it)
        self.w16(0x904006, state.frame_counter)
        self.w16(0x904918, int(state.game_mode))
        self.w16(0x904928, state.level_players_active)
        self.w8(0x904065, state.secret_trick_id)
        self.w8(0x90491C, state.level_flags & 0xFF)
        self.w8(0x90491D, state.level_flags_2 & 0xFF)
        self.w8(0x90491E, state.level_flags_3 & 0xFF)
        self.w8(0x90491F, state.level_flags_4 & 0xFF)
        self.w16(0x904004, state.levelnum_current)
        self.w16(0x904A24, state.game_settings)
        self.w16(0x904B86, state.games_played_counter)
        if state.maze is not None:
            self.w16(0x904B5C, getattr(state.maze, "floorpattern", 0))
            self.w16(0x904B5E, getattr(state.maze, "wallpattern", 0))
        self.w16(0x90490C, state.idle_timer)
        self.w16(0x9048C6, state.escape_timer)
        self.w16(0x904BF2, state.movement_type)
        self.w16(0x904008, state.scroll_x)
        self.w16(0x90400A, state.scroll_y)
        self.w16(0x904AC2, (state.scroll_x - 8) << 7)
        self.w16(0x904AC4, (0x108 - state.scroll_y) << 7)

    # --- calling -------------------------------------------------------------

    def call(self, entry: int, *args: int, count: int = 5_000_000) -> int:
        """Run ``entry`` with longword stack arguments; returns D0.

        ``halted`` says whether it returned. A routine that faulted (usually
        hardware or state this snapshot lacks) leaves ``fault_pc`` set, and one
        that ran out of ``count`` instructions has neither.
        """
        self.cpu.mem_write(STACK_TOP, struct.pack(f">I{len(args)}I", HALT, *[a & 0xFFFFFFFF for a in args]))
        self.cpu.reg_write(registers.UC_M68K_REG_SR, 0x2700)
        self.cpu.reg_write(registers.UC_M68K_REG_A7, STACK_TOP)
        self.fault_pc = None
        try:
            self.cpu.emu_start(entry, HALT, count=count)
        except unicorn.UcError:
            self.fault_pc = self.cpu.reg_read(registers.UC_M68K_REG_PC)
        self.halted = self.cpu.reg_read(registers.UC_M68K_REG_PC) == HALT
        return self.cpu.reg_read(registers.UC_M68K_REG_D0) & 0xFFFFFFFF

    def count_calls(self, address: int) -> list[int]:
        """A one-element list counting executions of ``address``."""
        hits = [0]

        def hook(_cpu, _address, _size, _data):
            hits[0] += 1

        self.cpu.hook_add(unicorn.UC_HOOK_CODE, hook, begin=address, end=address)
        return hits

    # --- reading -------------------------------------------------------------

    def picture(self, slot: int) -> int:
        return self.r16(_PICTURE + 2 * slot)

    def hpos(self, slot: int) -> int:
        return self.r16(_HPOS + 2 * slot)

    def vpos(self, slot: int) -> int:
        return self.r16(_VPOS + 2 * slot)

    def record(self, slot: int) -> tuple[int, int, int, int, int]:
        """``(picture, H, V, object type, state)`` of a MOB record."""
        return (
            self.picture(slot), self.hpos(slot), self.vpos(slot),
            self.r16(_LINK + 2 * slot) >> 10, self.r16(_STATE + 2 * slot) >> 10,
        )

    def player_slot(self, player_index: int) -> int:
        return self.r16(0x9048C8 + 2 * player_index)

    def keys(self, player_index: int) -> int:
        return self.r8(0x90405A + player_index)


def player_try_move(
    machine: RomMachine, state, player_index: int, delta: int,
    movement_type: int = 2,
) -> int:
    """ROM ``player_try_move`` (0x41BF0); returns the result word."""
    from gauntpy.game.subsystems.player_movement import _player_speed_units

    machine.w16(0x904BF2, movement_type)
    speed = _player_speed_units(state, state.players[player_index])
    joystick = (0xFF & ~delta) & 0xFF
    # corner_squeeze_geometry reads the stick from RAM rather than its argument (0x4FEE8).
    machine.w16(0x904920 + 2 * player_index, joystick)
    return machine.call(0x41BF0, player_index, speed, joystick, count=200_000) & 0xFFFF


def rom_try_move(state, player_index: int, delta: int, movement_type: int = 2):
    """One ROM step from ``state``: ``(result word, slot, H less palette, V)``."""
    machine = RomMachine.from_state(state)
    result = player_try_move(machine, state, player_index, delta, movement_type)
    slot = machine.player_slot(player_index)
    return result, slot, machine.hpos(slot) & ~0xF, machine.vpos(slot)
