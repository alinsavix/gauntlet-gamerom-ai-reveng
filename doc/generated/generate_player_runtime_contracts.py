#!/usr/bin/env python3
"""Generate and verify player-runtime and name-entry calling contracts."""

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
    (0x45866, "player_it_label_set", "uint16 player_index", "void", "presentation helper only; caller owns ram.it_player", "Verified", ("move.w 0xa(a6), d2", "cmp.w 0x9049dc.l, d2", "movea.l 0x596f6, a0", "jsr 0x4ad76.l")),
    (0x4590E, "player_it_label_clear", "uint16 player_index", "void", "presentation helper only; caller owns ram.it_player", "Verified", ("move.w 0xa(a6), d1", "move.w d0, (a0)+", "move.w d0, (a0)")),
    (0x45ACA, "player_inv_update", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "cmpi.w 0xfffd, 0x904918.l", "movea.l 0x5fc12, a0", "movea.l 0x904055, a0")),
    (0x45BE8, "string_length", "const char *string", "D0.l = byte length excluding the NUL terminator", "", "Verified", ("movea.l 0x8(a6), a0", "tst.b (a0)+", "ext.l d0")),
    (0x47FAC, "open_timed_doors", "void", "void", "", "Verified", ("cmpi.w 0x3400, d0", "cmpi.w 0x3800, d0", "jsr 0x5ddda.l", "jsr 0x4ad76.l")),
    (0x487CA, "player_lowhealth", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "movea.l 0x904aca, a0", "movea.l 0x904ace, a0", "jsr 0x4ad4e.l")),
    (0x49446, "death_potion_score", "uint16 doubled_death_mob_offset", "D0.l = score selected from death_potion_score_table", "", "Verified", ("move.w 0xa(a6), d0", "movea.l 0x579e2, a0", "jsr 0x49498.l", "movea.l 0x579d2, a0")),
    (0x49A3C, "death_damage_accumulate", "uint16 player_index, uint16 death_mob_slot, uint32 damage", "void", "", "Verified", ("move.w 0xa(a6), d0", "move.w 0xe(a6), d3", "move.l 0x10(a6), d2", "cmpi.w 0xc8, (a1, d1.w)", "jsr 0x47c0e.l", "jsr 0x5ddda.l")),
    (0x49A98, "player_hurt_speech_timer", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "movea.l 0x904afa, a0", "movea.l 0x57b32, a0", "jsr 0x4ad76.l")),
    (0x49B44, "ascii_to_alpha_glyph", "uint8 ascii_char", "D0.l = alpha-layer glyph index", "reads the low byte of the first normal stack slot at A6+0xB", "Verified", ("move.b 0xb(a6), d0", "cmpi.b 0x41, d0", "cmpi.b 0x30, d0", "moveq 0x25, d0")),
    (0x4A44A, "name_entry_draw_large_char", "uint16 column, uint16 row, uint8 character, uint16 color", "void", "uses fixed OS services 0x224 and 0x20C", "Verified", ("move.w 0xa(a6), d1", "move.w 0xe(a6), d0", "move.b 0x13(a6), d2", "move.w 0x16(a6), d1", "jsr 0x224.l", "jsr 0x20c.l")),
    (0x50E34, "player_damage_sample_update", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "movea.l 0x904ae6, a2", "movea.l 0x904ade, a3", "movea.l 0x904ad6, a0", "jsr 0x487ca.l")),
    (0x511AC, "player_tile_interact", "uint16 tile_mob_slot, uint16 player_index", "D0.l = -1 when handled/consumed, or 0 when unhandled", "calls sound_play indirectly through fixed A2 = 0x4AD76", "Verified", ("move.w 0xa(a6), d4", "move.w 0xe(a6), d2", "movea.l 0x4ad76, a2", "moveq 0xff, d1", "moveq 0x0, d1", "move.l d1, d0")),
    (0x53666, "player_create_shot", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "movea.l 0x9048c8, a2", "jsr 0x5df9c.l", "jsr 0x4ad76.l")),
    (0x54FE8, "secret_name_entry_update", "void", "void", "uses ram.secret_player as the player selector", "Verified", ("move.b 0x904063.l, d5", "jsr 0x55440.l", "jsr 0x554b6.l", "jsr 0x54be0.l")),
    (0x55440, "name_entry_step_char", "uint8 current_char, int16 direction, uint8 allow_backspace", "D0.l = wrapped next character", "reads byte arguments from the low bytes at A6+0xB and A6+0x13", "Verified", ("move.b 0xb(a6), d0", "move.w 0xe(a6), d2", "move.b 0x13(a6), d1", "ext.l d0")),
    (0x554B6, "name_entry_draw_char", "uint16 column, uint16 row, uint8 character, uint16 color", "void", "uses fixed OS service 0x218", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d2", "move.b 0x13(a6), d0", "move.w 0x16(a6), d1", "jsr 0x218.l")),
    (0x5554E, "name_entry_step_char_copy", "uint8 current_char, int16 direction, uint8 allow_backspace", "D0.l = wrapped next character", "byte-identical duplicate of 0x55440; no discovered direct control site", "Verified", ("move.b 0xb(a6), d0", "move.w 0xe(a6), d2", "move.b 0x13(a6), d1", "ext.l d0")),
    (0x555C4, "name_entry_draw_char_copy", "uint16 column, uint16 row, uint8 character, uint16 color", "void", "byte-identical duplicate of 0x554B6; uses fixed OS service 0x218; no discovered direct control site", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d2", "move.b 0x13(a6), d0", "move.w 0x16(a6), d1", "jsr 0x218.l")),
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


def runtime_check(root: Path, rom: bytes) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    for address, name, _, _, _, _, required in CONTRACTS:
        opcodes = analyze_body(root, loader, address)
        for expected in required:
            if expected not in opcodes:
                raise SystemExit(f"{name}: required instruction absent: {expected}")
        if "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    if rom[0x55440 - ROM_BASE : 0x554B6 - ROM_BASE] != rom[0x5554E - ROM_BASE : 0x555C4 - ROM_BASE]:
        raise SystemExit("name-entry step-character copies are no longer identical")
    if rom[0x554B6 - ROM_BASE : 0x55512 - ROM_BASE] != rom[0x555C4 - ROM_BASE : 0x55620 - ROM_BASE]:
        raise SystemExit("name-entry character-drawing copies are no longer identical")
    print(f"player-runtime contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
    output = here / "player_runtime_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("player_runtime_contracts.csv is stale; regenerate it")
        print(f"player_runtime_contracts.csv: verified {len(rows)} entries")
    else:
        with output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows to {output}")
    if args.run_check:
        runtime_check(root, rom)


if __name__ == "__main__":
    main()
