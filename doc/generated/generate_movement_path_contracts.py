#!/usr/bin/env python3
"""Generate and verify movement, path-grid, and door-record contracts."""

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

# address, name, arguments, return, exception, confidence, size, required opcodes
CONTRACTS = (
    (0x48F12, "tile_occupancy_test", "uint16 candidate_packed_slot", "D0.l = -1 when usable; 0 when out of bounds, occupied, or too near another MOB", "normal stack", "Verified", 0x122, ("move.w 0xa(a6), d2", "cmpi.w 0x20, d2", "cmpi.w 0x400, d2", "cmpi.l 0x7c0, d3", "cmpi.l 0x7c0, d1", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x50BB8, "scan_move_path_interactions", "int16 (*neighbor_probe)(uint16 packed_slot), uint16 packed_slot, uint16 player_index", "void", "calls the supplied probe through A2 until negative/blocked; resolves removable interior objects", "Verified", 0xC2, ("movea.l 0x8(a6), a2", "move.w 0xe(a6), d3", "move.w 0x12(a6), d2", "jsr (a2)", "cmpi.w 0x8001, (a0, d0.w)", "cmpi.w 0x8000, (a0, d0.w)", "jsr 0x50c7a", "rts")),
    (0x50C7A, "resolve_move_tile_interaction", "uint16 mob_slot, uint16 player_index", "D0.l = -1 when interaction/type blocks continued cleanup; 0 after removable-object cleanup", "normal stack; recursive for type 0x0F after thief/exit cleanup", "Verified", 0x9A, ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3", "jsr 0x511ac", "cmpi.w 0x10, d1", "cmpi.w 0xf, d0", "jsr 0x4f5c8", "jsr 0x50c7a", "jsr 0x5ddda", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x50D14, "nearby_mob_clearance_test", "uint16 candidate_packed_slot, uint16 excluded_player_index_or_4", "D0.l = -1 when clear; 0 when a qualifying nearby MOB overlaps the 0x7C0 axis window", "second argument 0-3 excludes that player's own hpos nibble 12+index; 4 excludes none", "Verified", 0x120, ("move.w 0xa(a6), d3", "move.w 0xe(a6), d4", "cmpi.w 0xc, d0", "add.l d2, d1", "cmpi.l 0x7c0, d1", "moveq 0x0, d0", "moveq 0xff, d0")),
    (0x50FD2, "path_grid_set_low_direction", "uint16 grid_index, uint8 direction", "void", "normal stack; writes direction+1 to low nibble of a 44-column/128-byte-stride grid", "Verified", 0x2E, ("move.w 0x6(a7), d0", "move.b 0xb(a7), d1", "divu.w 0x2c, d0", "asl.w 0x7, d0", "andi.b 0xf0, d0", "move.b d0, (a0)", "rts")),
    (0x51000, "path_grid_set_high_direction_if_empty", "uint16 grid_index, uint8 direction", "void", "normal stack; no-op in thief-mode bit 1 or when high nibble is already nonzero", "Verified", 0x3E, ("btst.b 0x1, 0x904ba1.l", "move.w 0x6(a7), d0", "move.b 0xb(a7), d1", "divu.w 0x2c, d0", "andi.b 0xf0, d0", "asl.b 0x4, d1", "andi.b 0xf, d0", "rts")),
    (0x5103E, "path_grid_get_direction", "uint16 grid_index", "D0.l = direction 0-7; 8 when the selected nibble is unset/invalid", "normal stack; bit 1 of thief mode selects high nibble, otherwise low nibble", "Verified", 0x3C, ("move.w 0x6(a7), d0", "divu.w 0x2c, d0", "btst.b 0x1, 0x904ba1.l", "lsr.b 0x4, d0", "subq.b 0x1, d0", "moveq 0x8, d0", "rts")),
    (0x510FC, "calc_direction", "uint16 from_packed_slot, uint16 to_packed_slot", "D0.w = direction 0-7; 8 when positions are equal", "normal stack; honors horizontal/vertical wrap flags", "Verified", 0xB0, ("move.w 0xe(a7), d3", "move.w 0x12(a7), d2", "btst.b 0x5, 0x90491f.l", "btst.b 0x4, 0x90491f.l", "andi.w 0x7, d3", "moveq 0x8, d0", "rts")),
    (0x51E80, "door_record_endpoints", "uint16 packed_door_slot, uint16 player_index, uint16 door_object_type", "void", "normal stack; fills that player's two endpoint positions/directions and calls main_open_doors", "Verified", 0x12E, ("move.w 0xa(a6), d3", "move.w 0xe(a6), d2", "move.w 0x12(a6), d4", "cmpi.w 0x9d7c, (a0, d0.w)", "cmpi.w 0x9d3c, (a0, d0.w)", "cmpi.w 0xe, d4", "jsr 0x51fae", "jsr 0x5207c", "jsr 0x45c00", "rts")),
    (0x51FAE, "door_scan_vertical_endpoints", "uint16 packed_door_slot, uint16 player_index, uint16 next_endpoint_index", "D0.l = updated endpoint index, clamped at 2", "normal stack; tests only the immediate above/below cells and writes direction codes 0/2", "Verified", 0xCE, ("move.w 0xa(a6), d4", "move.w 0xe(a6), d3", "move.w 0x12(a6), d2", "subq.l 0x1, d0", "addq.l 0x1, d0", "jsr 0x5f772", "move.w 0x2, (a0, d0.w)", "move.w d2, d0", "ext.l d0", "rts")),
    (0x5207C, "door_scan_horizontal_endpoints", "uint16 packed_door_slot, uint16 player_index, uint16 next_endpoint_index", "D0.l = updated endpoint index, clamped at 2", "normal stack; tests only the immediate left/right cells and writes direction codes 3/1", "Verified", 0xD0, ("move.w 0xa(a6), d4", "move.w 0xe(a6), d3", "move.w 0x12(a6), d2", "subq.l 0x1, d1", "addq.l 0x1, d1", "jsr 0x5f772", "move.w 0x3, (a0, d0.w)", "move.w 0x1, (a0, d0.w)", "move.w d2, d0", "ext.l d0", "rts")),
)


def direct_sites(rom: bytes) -> dict[int, list[int]]:
    found = {row[0]: [] for row in CONTRACTS}
    for offset in range(0, len(rom) - 6, 2):
        opcode = int.from_bytes(rom[offset : offset + 2], "big")
        target = None
        if opcode in (0x4EB9, 0x4EF9):
            target = int.from_bytes(rom[offset + 2 : offset + 6], "big")
        elif opcode == 0x6100:
            target = ROM_BASE + offset + 2 + int.from_bytes(rom[offset + 2 : offset + 4], "big", signed=True)
        elif opcode >> 8 == 0x61 and opcode & 0xFF not in (0, 0xFF):
            target = ROM_BASE + offset + 2 + int.from_bytes(bytes((opcode & 0xFF,)), "big", signed=True)
        if target in found:
            found[target].append(ROM_BASE + offset)
    return {address: sorted(set(sites)) for address, sites in found.items()}


def opcodes(root: Path, loader: Path, address: int, size: int) -> list[str]:
    command = ["r2", "-q", "-n", "-e", "scr.color=0", "-i", str(loader), "-c", f"pDj {size} @ 0x{address:x}", "-c", "q", "malloc://1"]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)", result.stderr):
        raise SystemExit(f"radare2 movement/path audit failed at 0x{address:X}:\n{result.stderr}")
    return [item["opcode"] for item in json.loads(result.stdout)]


def runtime_check(root: Path) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    for address, name, _, _, _, _, size, required in CONTRACTS:
        operations = opcodes(root, loader, address, size)
        for expected in required:
            if not any(operation == expected or operation.startswith(expected + ".") for operation in operations):
                raise SystemExit(f"{name} (0x{address:X}): required instruction absent: {expected}")
    print(f"movement/path contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
        {"address": f"0x{address:05X}", "name": name, "arguments": arguments, "return": return_value, "exceptional_convention": exception, "direct_control_sites": ";".join(f"0x{site:05X}" for site in sites[address]), "confidence": confidence}
        for address, name, arguments, return_value, exception, confidence, _, _ in CONTRACTS
    ]
    output = here / "movement_path_contracts.csv"
    if args.check:
        with output.open(newline="") as handle:
            old_rows = list(csv.DictReader(handle))
        if old_rows != rows:
            raise SystemExit("movement_path_contracts.csv is stale; regenerate it")
        print(f"movement_path_contracts.csv: verified {len(rows)} entries")
    else:
        with output.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows to {output}")
    if args.run_check:
        runtime_check(root)


if __name__ == "__main__":
    main()
