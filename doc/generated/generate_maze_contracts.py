#!/usr/bin/env python3
"""Generate and verify callable contracts for maze and Slapstic entries."""

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

# address, name, arguments, return, exceptional convention, expected A6 offsets
CONTRACTS = (
    (0x40C78, "find_maze", "maze number in wrapper caller's first longword", "D1.w bank offset; ptr_maze_data side effect", "frameless shared-stack helper; reads 8(A7) after wrapper JSR", ()),
    (0x40CC4, "maze_select_alt_bank", "uint32 maze_number", "void", "frameless wrapper; argument is consumed by find_maze", ()),
    (0x40CF2, "maze_init", "uint32 maze_number", "void", "frameless wrapper; argument is consumed by find_maze", ()),
    (0x40D24, "load_level_tileset", "uint32 maze_number", "void", "frameless wrapper; argument is consumed by find_maze", ()),
    (0x40D4E, "maze_select_bank_special", "uint32 maze_number", "void", "frameless wrapper; argument is consumed by find_maze", ()),
    (0x44AC2, "maze_setupnew", "const uint8_t *maze_record", "void", "", (0x8,)),
    (0x4C1BC, "maze_decode", "const uint8_t *maze_record", "void", "", (0x8,)),
    (0x45E40, "maze_place_object", "uint16 slot_or_offset, uint16 object_type, uint16 scan_base", "void", "", (0xA, 0xE, 0x12)),
    (0x43F68, "maze_addrandompickups", "uint16 enable_random_pickups", "void", "", (0xA,)),
    (0x42E9A, "maze_randomplace", "uint16 object_type", "uint16 packed_slot in D0.l", "", (0xA,)),
    (0x4526A, "maze_show", "void", "void", "", ()),
    (0x4529A, "maze_hide", "void", "void", "", ()),
    (0x452D0, "setup_infopanel", "int16 player_selector (-1 = whole panel)", "void", "", (0xA,)),
    (0x462AE, "dragon_reserve_footprint_cell", "uint16 packed_slot", "void", "", (0xA,)),
    (0x4631C, "maze_tile_write_at", "uint16 packed_slot, uint16 object_type, uint16 span_length", "void", "", (0xA, 0xE, 0x12)),
    (0x52ECA, "maze_checknum", "void", "void", "", ()),
    (0x4BE24, "level_splash", "void", "void", "", ()),
    (0x438AE, "maze_new_level_setup", "void", "void", "", ()),
    (0x436FE, "maze_load_pickup_config", "const uint8_t *maze_record", "void", "", (0x8,)),
    (0x436CC, "get_random_maze_flags", "void", "uint32 level_flags in D0.l", "", ()),
    (0x43D8C, "maze_scan_objects", "int16 scan_mode", "void", "", (0xA,)),
    (0x43826, "slapstic_cmd_bitwise", "void", "void", "", ()),
    (0x56E58, "slapstic_cmd_bank0", "void", "void", "clobbers D0; saves/restores SR", ()),
    (0x56E6E, "slapstic_cmd_bank3", "void", "void", "clobbers D0; saves/restores SR", ()),
    (0x56E84, "slapstic_cmd_bankX", "D0.w selector offset, A0 bank-select base", "void", "register arguments", ()),
    (0x56E90, "slapstic_cmd_maze_init", "A0 source, A1 destination; D0 dummy bus value", "void", "register arguments; branches to shared 0x56E54 tail", ()),
    (0x56E98, "slapstic_cmd_bankX_special", "D0.w selector offset, A0 bank-select base", "void", "register arguments", ()),
    (0x56EAA, "slapstic_verify", "void", "uint32 packed status/sums in D0.l; success 0x0001FFFE", "", ()),
    (0x46C5E, "scroll_to_slot", "uint16 packed_slot", "void", "", (0xA,)),
    (0x46F56, "set_scroll_pos", "int16 horizontal, int16 vertical", "void", "", (0xA, 0xE)),
)


def direct_sites(rom: bytes) -> dict[int, list[int]]:
    targets = {address for address, *_ in CONTRACTS}
    found = {address: [] for address in targets}
    for offset in range(0, len(rom) - 6, 2):
        opcode = int.from_bytes(rom[offset : offset + 2], "big")
        target: int | None = None
        if opcode in (0x4EB9, 0x4EF9):  # absolute JSR or JMP
            target = int.from_bytes(rom[offset + 2 : offset + 6], "big")
        elif opcode == 0x6100:
            displacement = int.from_bytes(rom[offset + 2 : offset + 4], "big", signed=True)
            target = ROM_BASE + offset + 2 + displacement
        elif opcode >> 8 == 0x61 and opcode & 0xFF not in (0, 0xFF):
            displacement = int.from_bytes(bytes((opcode & 0xFF,)), "big", signed=True)
            target = ROM_BASE + offset + 2 + displacement
        if target in found:
            found[target].append(ROM_BASE + offset)
    return found


def runtime_check(root: Path) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    for address, name, _, _, _, expected_a6 in CONTRACTS:
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
        actual_a6 = tuple(
            sorted(
                {
                    int(match.group(1), 16)
                    for opcode in opcodes
                    for match in re.finditer(r"(?<!-)0x([0-9a-f]+)\(a6\)", opcode)
                    if int(match.group(1), 16) >= 8
                }
            )
        )
        if actual_a6 != expected_a6:
            raise SystemExit(f"{name}: expected A6 offsets {expected_a6}, found {actual_a6}")
        if "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    print(f"maze contracts: analyzed {len(CONTRACTS)} bodies; argument offsets match")


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
            "confidence": "Strong inference" if name == "maze_place_object" else "Verified",
        }
        for address, name, arguments, return_value, convention, _ in CONTRACTS
    ]
    output = here / "maze_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("maze_contracts.csv is stale; regenerate it")
        print(f"maze_contracts.csv: verified {len(rows)} entries")
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
