#!/usr/bin/env python3
"""Generate and verify transporter/forcefield callable contracts."""

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
    (0x47C0E, "tport_cycle_start", "uint16 source_mob_slot, uint16 animation_channel", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d0", "move.w 0x924, (a0, d0.w)")),
    (0x47CFE, "handle_tport", "uint16 source_mob_slot, uint16 animation_channel", "void", "", "Verified", ("move.w 0xa(a6), d5", "move.w 0xe(a6), d4", "addi.w 0x19, d2")),
    (0x4E684, "tport_route_connect", "uint16 source_pos, uint16 destination_pos, uint16 approach_pos", "void", "", "Verified", ("move.w 0xa(a6), d1", "move.w 0xe(a6), d2", "move.w 0x12(a6), d3")),
    (0x4E73A, "tport_route_connect_if_empty", "uint16 source_pos, uint16 destination_pos, uint16 approach_pos", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d4", "move.w 0x12(a6), d3")),
    (0x4E7C0, "tport_find_id", "uint16 packed_maze_pos", "D0.l = one-based transporter ID; level_tport_count + 1 when absent", "", "Verified", ("move.w 0xa(a6), d3", "ext.l d0", "addq.l 0x1, d0")),
    (0x50224, "player_tport", "uint16 transporter_pos, uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d4", "move.w d3, (a2, d0.w)")),
    (0x50616, "tport_player_flash", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d1", "move.w 0x1709, (a0, d0.w)")),
    (0x50662, "tport_player_move", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.w (a2, d0.w), d6", "moveq 0x1, d4")),
    (0x50ADE, "tport_check_dest", "uint16 destination_mob_slot, uint16 player_index", "D0.l = 1 blocked or 0 usable", "", "Verified", ("move.w 0xa(a6), d1", "move.w 0xe(a6), d3", "moveq 0x1, d0", "moveq 0x0, d0")),
    (0x50B88, "tport_restore_player_picture", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d0", "move.w (a0, d0.w), (a1, d1.w)")),
    (0x5107A, "tport_route_write_pair", "uint16 forward_id, uint16 reverse_id, uint32 forward_reverse_words", "void", "frameless leaf; the two halves of the third argument supply the forward and reverse words", "Verified", ("move.w 0x6(a7), d0", "move.w 0xa(a7), d0", "move.w 0xc(a7), (a0)", "move.w 0xe(a7), (a0)")),
    (0x510BC, "tport_route_read_pair", "uint16 forward_id, uint16 reverse_id", "D0.l = forward word in bits 31-16 and reverse word in bits 15-0; absent halves are zero", "frameless leaf", "Verified", ("move.w 0x6(a7), d0", "move.w 0xa(a7), d1", "swap d0")),
    (0x52F26, "maze_forcefield_setup", "void", "void", "four calls to consume_forcefield_code are indirect through A2", "Verified", ("moveq 0x20, d2", "moveq 0x0, d4", "jsr (a2)", "move.b d3, (a0, d0.w)")),
    (0x52FBE, "consume_forcefield_code", "uint16 marker_mob_slot", "D0.l = forcefield code 1-3, or 0 for a non-marker", "", "Verified", ("move.w 0xa(a6), d1", "move.w d4, d0", "ext.l d0")),
    (0x53346, "check_forcefield_collision", "uint16 packed_maze_pos", "D0.l = 1 on a forcefield tile or 0 otherwise", "", "Verified", ("move.w 0xa(a6), d2", "seq.b d1", "neg.b d1", "move.l d1, d0")),
    (0x53398, "forcefield_segments_setup", "void", "void", "", "Verified", ("clr.w (a0, d0.w)", "cmpi.w 0x3f, d1")),
    (0x5DF5A, "mob_place_tport_anim", "uint16 source_mob_slot, uint16 animation_channel", "void", "frameless shared-body entry; saves D3-D7/A5-A6, adds 0x0D to the channel, then branches to insert_mob_depth_sorted", "Verified", ("movem.l d3-d7/a5-a6, -(a7)", "move.w 0x26(a7), d7", "addi.w 0xd, d7")),
    (0x5DF8E, "tport_create_splodey", "uint16 source_mob_slot, uint16 animation_channel", "void", "frameless shared-body entry; saves D3-D7/A5-A6, adds 0x19 to the channel, then branches to insert_mob_depth_sorted", "Verified", ("movem.l d3-d7/a5-a6, -(a7)", "move.w 0x26(a7), d7", "addi.w 0x19, d7")),
    (0x5FC56, "pf_isff_d0", "D0.w packed_maze_pos", "D0.l = 1 when the coordinate belongs to a forcefield segment or 0 otherwise", "register-argument entry sharing the pf_isff body", "Verified", ("movem.l d2-d5, -(a7)", "move.w d0, d2", "move.w (a0)+, d5")),
    (0x5FC5E, "pf_isff", "uint16 packed_maze_pos", "D0.l = 1 when the coordinate belongs to a forcefield segment or 0 otherwise", "frameless stack-argument entry eight bytes after pf_isff_d0; establishes its own saved-register frame and shares the body at 0x5FC66", "Verified", ("movem.l d2-d5, -(a7)", "move.w 0x16(a7), d2", "move.w (a0)+, d5")),
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


def runtime_check(root: Path) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    shared_body_entries = {0x5DF5A, 0x5DF8E}
    for address, name, _, _, _, _, required in CONTRACTS:
        command = [
            "r2", "-q", "-n", "-e", "scr.color=0", "-i", str(loader),
            "-c", f"af- 0x{address:x}; af @ 0x{address:x}; pdfj @ 0x{address:x}",
            "-c", "q", "malloc://1",
        ]
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)", result.stderr):
            raise SystemExit(f"radare2 body audit failed for {name}:\n{result.stderr}")
        function = json.loads(result.stdout)
        opcodes = [op["opcode"] for op in function.get("ops", [])]
        for expected in required:
            if expected not in opcodes:
                raise SystemExit(f"{name}: required instruction absent: {expected}")
        if address not in shared_body_entries and "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-i", str(loader),
        "-c", "af- 0x5dfa6; af @ 0x5dfa6; pdfj @ 0x5dfa6",
        "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)", result.stderr):
        raise SystemExit(f"radare2 body audit failed for insert_mob_depth_sorted:\n{result.stderr}")
    opcodes = [op["opcode"] for op in json.loads(result.stdout).get("ops", [])]
    for expected in ("move.w 0x22(a7), d6", "rts"):
        if expected not in opcodes:
            raise SystemExit(f"insert_mob_depth_sorted: required instruction absent: {expected}")
    print(f"transporter/forcefield contracts: analyzed {len(CONTRACTS)} bodies; ABI evidence matches")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parent
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
    output = here / "tport_forcefield_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("tport_forcefield_contracts.csv is stale; regenerate it")
        print(f"tport_forcefield_contracts.csv: verified {len(rows)} entries")
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
