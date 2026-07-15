#!/usr/bin/env python3
"""Generate and verify player-movement/collision callable contracts."""

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

# address, name, arguments, return, exceptional convention, required opcodes
CONTRACTS = (
    (0x41BF0, "player_try_move", "uint16 player_index, int16 delta, uint16 movement_flags", "D0.w movement result; 0x00F0 = no movement", "frameless wrapper saves D2-D7/A2-A6 before reading three normal stack arguments", ("move.w 0x32(a7), d0", "move.w 0x36(a7), d6", "move.w 0x3a(a7), d7")),
    (0x41C30, "player_try_move_core", "D0.w doubled player index, D6.w delta, D7.w flags; A2/A3/A4 MOB arrays", "D0.w movement result", "internal register-state entry; recursively reentered by BSR", ("move.w d0, d5",)),
    (0x42648, "tile_lookup_core", "D1.w candidate offset, D2.w current offset, D3/D4 coordinates; A2/A3/A4 MOB arrays", "carry set when occupied and within collision bounds; D1 retained", "BSR-only register entry", ("tst.w (a2, d1.w)",)),
    (0x425D0, "probe_up", "D2.w current offset, D3/D4 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset; carry = blocked", "register entry; may tail-branch to tile_lookup_core", ("cmpi.w 0x7e, d2",)),
    (0x4260C, "probe_down", "D2.w current offset, D3/D4 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset; carry = blocked", "register entry; may tail-branch to tile_lookup_core", ("cmpi.w 0x7c0, d2",)),
    (0x426D4, "probe_left", "D2.w current offset, D3/D4 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset; carry = blocked", "BSR-only register entry", ("move.w d2, d1",)),
    (0x4270C, "probe_right", "D2.w current offset, D3/D4 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset; carry = blocked", "BSR-only register entry", ("move.w d2, d1",)),
    (0x42744, "squeeze_through_check", "D1.w candidate offset, D2.w current offset, D5.w doubled player index; A3 H-position array", "D0.l boolean; Z reflects result", "register entry", ("lea.l 0x9048e0.l, a0", "tst.l d0")),
    (0x4FEB2, "corner_squeeze_geometry", "uint16 packed_slot, uint16 player_index", "D0.l boolean", "", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3")),
    (0x406B6, "mob_probe_up", "uint16 mob_slot", "D0.w blocking slot, -1 none, or 0x0400 boundary sentinel", "frameless stack leaf", ("move.w 0x6(a7), d1",)),
    (0x40732, "mob_probe_down", "uint16 mob_slot", "D0.w blocking slot, -1 none, or 0x0400 boundary sentinel", "frameless stack leaf", ("move.w 0x6(a7), d1",)),
    (0x4083A, "mob_probe_left", "uint16 mob_slot", "D0.w blocking slot or -1", "frameless stack leaf", ("move.w 0x6(a7), d1",)),
    (0x408A0, "mob_probe_right", "uint16 mob_slot", "D0.w blocking slot or -1", "frameless stack leaf", ("move.w 0x6(a7), d1",)),
    (0x407A6, "mob_probe_candidate", "D1.w candidate offset, D2.w current offset; A0/A1/A2 V/H/picture arrays", "carry set for blocking candidate; distance scratch updated", "BSR-only register entry", ("tst.w (a2, d1.w)",)),
    (0x52192, "mob_collision_test", "uint16 candidate_slot, uint16 player_index", "D0.l boolean collision/interaction result", "", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3")),
    (0x42598, "mob_collision_test_preserve_d1_a", "D1.w candidate offset, D5.w doubled player index", "D0.l boolean; Z reflects result; D1 preserved", "register wrapper", ("move.w d1, -(a7)", "tst.l d0")),
    (0x425B4, "mob_collision_test_preserve_d1_b", "D1.w candidate offset, D5.w doubled player index", "D0.l boolean; Z reflects result; D1 preserved", "register wrapper", ("move.w d1, -(a7)", "tst.l d0")),
    (0x4280E, "door_traverse_right", "D2.w current offset; A2/A3/A4 MOB arrays; saved D5 coordinate at 0x0A(A7)", "D0.w status; caller consumes Z (zero = path handled)", "register/shared-caller-stack entry", ("move.w 0xa(a7), d1", "move.w 0xe(a7), d1")),
    (0x428A4, "door_traverse_left", "D2.w current offset; A2/A3/A4 MOB arrays; saved D5 coordinate at 0x0A(A7)", "D0.w status; caller consumes Z (zero = path handled)", "register/shared-caller-stack entry", ("move.w 0xa(a7), d1", "move.w 0xe(a7), d1")),
    (0x4293A, "door_traverse_up", "D2.w current offset; A2/A3/A4 MOB arrays; saved D5 coordinate at 0x0A(A7)", "D0.w status; caller consumes Z (zero = path handled)", "register/shared-caller-stack entry", ("move.w 0xa(a7), d1", "move.w 0xe(a7), d1")),
    (0x429D0, "door_traverse_down", "D2.w current offset; A2/A3/A4 MOB arrays; saved D5 coordinate at 0x0A(A7)", "D0.w status; caller consumes Z (zero = path handled)", "register/shared-caller-stack entry", ("move.w 0xa(a7), d1", "move.w 0xe(a7), d1")),
    (0x427B4, "failed_door_post", "D2.w current offset, D4/D5 coordinates, D6/D7 state; A2/A3/A4 MOB arrays", "void", "BSR-only register entry", ("move.w d5, d1",)),
    (0x5E35E, "ray_march_right", "D2.w current offset, D3.w clearance, D4/D5 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset or -1; N signals failure; failure sets D2 bit 31", "register entry", ("move.w d2, d1", "moveq 0xff, d1")),
    (0x5E2A2, "ray_march_left", "D2.w current offset, D3.w clearance, D4/D5 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset or -1; N signals failure; failure sets D2 bit 31", "register entry", ("move.w d2, d1", "moveq 0xff, d1")),
    (0x5E1D8, "ray_march_up", "D2.w current offset, D3.w clearance, D4/D5 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset or -1; N signals failure; failure sets D2 bit 31", "register entry", ("moveq 0xff, d1",)),
    (0x5E10C, "ray_march_down", "D2.w current offset, D3.w clearance, D4/D5 coordinates; A2/A3/A4 MOB arrays", "D1.w candidate offset or -1; N signals failure; failure sets D2 bit 31", "register entry", ("moveq 0xff, d1",)),
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
    return found


def runtime_check(root: Path) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    for address, name, _, _, _, required in CONTRACTS:
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
        if "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    print(f"player/collision contracts: analyzed {len(CONTRACTS)} bodies; ABI evidence matches")


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
            "confidence": "Strong inference" if name.startswith("door_traverse_") else "Verified",
        }
        for address, name, arguments, return_value, convention, _ in CONTRACTS
    ]
    output = here / "player_collision_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("player_collision_contracts.csv is stale; regenerate it")
        print(f"player_collision_contracts.csv: verified {len(rows)} entries")
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
