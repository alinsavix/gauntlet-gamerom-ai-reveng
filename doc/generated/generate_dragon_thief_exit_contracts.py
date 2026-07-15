#!/usr/bin/env python3
"""Generate and verify dragon/thief/exit callable contracts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROM_BASE = 0x40000
ROM_SHA1 = "decbe6438b3a2618bd7fe79d14be034efadd7ff4"

# address, name, arguments, return, exceptional convention, confidence,
# required opcodes
CONTRACTS = (
    (0x54454, "main_handle_dragon", "void", "void", "", "Verified", ("link.w a6, 0x0", "movem.l d2-d4/a2-a3, -(a7)", "andi.w 0xfff7, (a3)")),
    (0x549EA, "dragon_player_proximity", "uint16 previous_pos, uint16 current_pos", "void", "", "Verified", ("move.w 0xa(a6), d0", "move.w 0xe(a6), d1", "pea.l 0xd5.l")),
    (0x5496E, "dragon_setup_segments", "uint16 primary_dragon_mob_slot", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w d2, d0", "moveq 0x20, d1")),
    (0x54748, "dragon_fire_setup", "uint16 shot_mob_slot, uint16 variant_flag", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3", "subq.w 0x1, d5")),
    (0x53E4A, "dragon_choose_move_direction", "void", "void", "", "Verified", ("link.w a6, 0xfff8", "move.w 0xf0, -0x4(a6)", "move.w -0x2(a6), d1")),
    (0x53D10, "dragon_update_segments", "void", "void", "", "Verified", ("movem.l d2-d5/a2, -(a7)", "moveq 0x3, d1", "andi.w 0xfff7, (a2)")),
    (0x540E8, "dragon_find_free_shot_slot", "void", "D0.l = free dragon-shot subslot 1-4, or 0 when full", "", "Verified", ("moveq 0x4, d1", "subq.w 0x1, d1", "move.w d1, d0")),
    (0x54AF8, "dragon_any_segment_near_screen", "void", "D0.l = -1 when any segment is near the screen, or 0 otherwise", "calls tile_near_screen_test four times indirectly through A2", "Verified", ("movem.l a2, -(a7)", "jsr (a2)", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x4DFF6, "thief_target_calc", "void", "void", "", "Verified", ("link.w a6, 0xfff8", "move.w d2, -0x8(a6, d0.w)", "cmp.w -0x8(a6, d0.w), d2")),
    (0x4E122, "thief_exit", "void", "void", "", "Verified", ("link.w a6, 0x0", "andi.w 0xfff6, (a0)", "ori.w 0x2, (a0)")),
    (0x4E1FE, "thief_steal_from_player", "uint16 player_index", "D0.l = 1 when theft/mugger damage is applied, or 0 when suppressed", "", "Verified", ("move.w 0xa(a6), d2", "moveq 0x0, d0", "moveq 0x1, d0")),
    (0x4E432, "thief_setup", "void", "void", "", "Verified", ("movem.l d2, -(a7)", "move.l 0x7d30, 0x904bb4.l", "clr.w 0x904ba0.l")),
    (0x4E4D8, "thief_timer_set", "void", "void", "", "Verified", ("movem.l d2-d4/a2-a3, -(a7)", "moveq 0x30, d1", "asl.l 0x2, d0")),
    (0x4E7FC, "thief_test_move_tile", "uint16 candidate_pos, uint16 object_type", "D0.l = nonzero when a transporter/corner path handles the move, or 0 otherwise", "", "Verified", ("move.w 0xa(a6), d1", "move.w 0xe(a6), d2", "clr.w d0", "ext.l d0")),
    (0x4E8DC, "main_thief_anim", "void", "void", "", "Verified", ("movem.l d2-d5/a2-a3, -(a7)", "move.w d1, 0x904b9c.l", "move.w d1, (a0, d0.w)")),
    (0x4EE0A, "thief_probe_axis", "int32 (*probe)(uint16 thief_slot), uint32 position_array_base, int16 coordinate_delta", "D0.l = candidate MOB slot, or -1 when blocked/rejected", "calls the supplied probe callback indirectly through A0", "Verified", ("movea.l 0x8(a6), a0", "move.l 0xc(a6), d2", "move.w 0x12(a6), d3", "jsr (a0)", "moveq 0xff, d4")),
    (0x4EE7A, "thief_move_engine", "uint16 move_flags, uint16 horizontal_delta_bias, uint16 vertical_delta_bias", "D0.l = thief_collision_direction_code plus the blocked-axis flag", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d0", "move.w 0x12(a6), d4", "add.l d1, d0")),
    (0x4F5C8, "thief_remove_and_drop_loot", "int16 score_player_or_minus1, uint16 replacement_mob_slot_or_zero", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d2", "cmpi.w 0xffff, d3")),
    (0x4F742, "thief_handle_tile_collision", "uint16 candidate_mob_slot", "D0.l = -1 when handled/blocked, or 0 when clear", "", "Verified", ("move.w 0xa(a6), d2", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x4F912, "thief_compute_path", "void", "void", "", "Verified", ("moveq 0x0, d2", "move.b (a2), d2", "move.b d0, (a2)")),
    (0x4FAD4, "thief_enter_tport", "uint16 transporter_pos", "D0.l = -1 when a transition starts, or 0 when rejected", "four route-pair reads are indirect through A2", "Verified", ("move.w 0xa(a6), d2", "jsr (a2)", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x4FBFC, "thief_start_tport_anim", "uint16 destination_pos", "void", "", "Verified", ("move.w 0xa(a6), d2", "moveq 0x12, d1", "moveq 0xb, d0")),
    (0x5287C, "main_exit_move", "void", "void", "", "Verified", ("movem.l d2-d5/a2, -(a7)", "moveq 0x3, d0", "moveq 0x1f, d1")),
    (0x52B06, "exit_get_id", "uint16 packed_exit_pos", "D0.l = zero-based exit index, or level_exit_count when absent", "", "Verified", ("move.w 0xa(a6), d3", "clr.w d0", "ext.l d0")),
    (0x52B40, "player_exit_sequence", "uint16 player_index, uint16 exit_mob_slot, uint16 exit_type", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d4", "move.w 0x12(a6), d5")),
    (0x5DF80, "exit_create_player_anim", "uint16 source_mob_slot, uint16 animation_channel", "void", "frameless shared-body entry; saves D3-D7/A5-A6, adds 0x15 to the channel, then branches to insert_mob_depth_sorted", "Verified", ("movem.l d3-d7/a5-a6, -(a7)", "move.w 0x26(a7), d7", "addi.w 0x15, d7")),
)


def direct_sites(rom: bytes) -> dict[int, list[int]]:
    targets = {address for address, *_ in CONTRACTS}
    found = {address: [] for address in targets}
    for offset in range(0, len(rom) - 6, 2):
        opcode = int.from_bytes(rom[offset : offset + 2], "big")
        target: int | None = None
        if opcode in (0x4EB9, 0x4EF9):
            target = int.from_bytes(rom[offset + 2 : offset + 6], "big")
        elif opcode == 0x6100:
            target = ROM_BASE + offset + 2 + int.from_bytes(
                rom[offset + 2 : offset + 4], "big", signed=True
            )
        elif opcode >> 8 == 0x61 and opcode & 0xFF not in (0, 0xFF):
            target = ROM_BASE + offset + 2 + int.from_bytes(
                bytes((opcode & 0xFF,)), "big", signed=True
            )
        if target in found:
            found[target].append(ROM_BASE + offset)
    return {target: sorted(set(sites)) for target, sites in found.items()}


def analyze_body(root: Path, loader: Path, address: int) -> list[str]:
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-i", str(loader),
        "-c", f"af- 0x{address:x}; af @ 0x{address:x}; pdfj @ 0x{address:x}",
        "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)", result.stderr):
        raise SystemExit(f"radare2 body audit failed at 0x{address:X}:\n{result.stderr}")
    return [op["opcode"] for op in json.loads(result.stdout).get("ops", [])]


def runtime_check(root: Path) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    shared_body_entries = {0x5DF80}
    for address, name, _, _, _, _, required in CONTRACTS:
        opcodes = analyze_body(root, loader, address)
        for expected in required:
            if expected not in opcodes:
                raise SystemExit(f"{name}: required instruction absent: {expected}")
        if address not in shared_body_entries and "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    opcodes = analyze_body(root, loader, 0x5DFA6)
    for expected in ("move.w 0x22(a7), d6", "rts"):
        if expected not in opcodes:
            raise SystemExit(f"insert_mob_depth_sorted: required instruction absent: {expected}")
    print(f"dragon/thief/exit contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    rom = (root / "row76.bin").read_bytes()
    if len(rom) != 0x20000 or hashlib.sha1(rom).hexdigest() != ROM_SHA1:
        raise SystemExit("row76.bin is not the documented 128 KiB target ROM")
    sites = direct_sites(rom)
    rows = [
        {
            "address": f"0x{address:05X}",
            "name": name,
            "arguments": arguments,
            "return": return_value,
            "exceptional_convention": convention,
            "direct_control_sites": ";".join(f"0x{site:05X}" for site in sites[address]),
            "confidence": confidence,
        }
        for address, name, arguments, return_value, convention, confidence, _ in CONTRACTS
    ]
    output = here / "dragon_thief_exit_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("dragon_thief_exit_contracts.csv is stale; regenerate it")
        print(f"dragon_thief_exit_contracts.csv: verified {len(rows)} entries")
    else:
        with output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows to {output}")
    if args.run_check:
        runtime_check(root)


if __name__ == "__main__":
    main()
