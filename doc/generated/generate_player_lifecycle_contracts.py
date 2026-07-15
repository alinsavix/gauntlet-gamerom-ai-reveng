#!/usr/bin/env python3
"""Generate and verify EEPROM/configuration and player-lifecycle contracts."""

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
    (0x42DF4, "character_select_input_update", "void", "void", "", "Verified", ("cmpi.b 0x10, (a0, d0.w)", "move.w d1, (a0, d0.w)", "jsr 0x452d0.l")),
    (0x42F86, "eeprom_load_config", "void", "void", "uses fixed OS EEPROM services 0x184 and 0x24E", "Verified", ("movea.l 0x904b8e, a4", "jsr 0x184.l", "jsr 0x24e.l", "move.l 0x8ca0, 0x904012.l")),
    (0x43192, "eeprom_write", "void", "void", "uses fixed OS EEPROM service 0x24E", "Verified", ("movea.l 0x904b8e, a1", "move.b 0x904011.l, (a0)", "jsr 0x24e.l")),
    (0x431EE, "eeprom_periodic_write", "void", "void", "", "Verified", ("movea.l 0x904012, a0", "move.l 0x8ca0, (a0)", "jsr 0x43192.l")),
    (0x43360, "player_resetcounters", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d0", "movea.l 0x9049a0, a0", "movea.l 0x904bce, a0")),
    (0x4341E, "player_resetall", "void", "void", "", "Verified", ("moveq 0x3, d2", "jsr 0x43360.l", "clr.w 0x904928.l")),
    (0x44C7E, "show_continue_prompt", "void", "void", "calls fixed draw_string through A2 = 0x25A", "Verified", ("movea.l 0x25a, a2", "tst.w 0x904928.l", "pea.l 0x57658.l", "move.w 0x1, 0x904b82.l")),
    (0x452D0, "setup_infopanel", "int16 player_selector (-1 = whole panel)", "void", "calls fixed draw_string/copy services through A2 = 0x25A and A3 = 0x142", "Verified", ("move.w 0xa(a6), d0", "movea.l 0x25a, a2", "movea.l 0x142, a3")),
    (0x48754, "speech_welcome", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "pea.l 0x59.l", "movea.l 0x596f6, a0")),
    (0x488CA, "player_coindrop", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.b 0x10, (a0, d0.w)", "jsr 0x452d0.l")),
    (0x489B8, "remove_dying_player_sprites", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "jsr 0x5e064.l", "movea.l 0x904bce, a0")),
    (0x48A36, "player_join_finalize", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "jsr 0x488ca.l", "jsr 0x1cc.l", "jsr 0x48754.l")),
    (0x48BB6, "player_join", "uint8 player_index", "void", "reads the low byte of the first normal stack slot at A6+0xB", "Verified", ("move.b 0xb(a6), d2", "jsr 0x48bec.l", "tst.l d0", "jsr 0x48a36.l")),
    (0x48BEC, "player_start_inner", "uint16 player_index", "D0.l = -1 when placement and MOB initialization succeed, or 0 when no usable spawn position exists", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0x4ef9, (a0, d0.w)", "moveq 0x0, d0", "moveq 0xff, d0")),
    (0x49DE6, "player_death_sequence", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "jsr 0x1b4.l", "jsr 0x452d0.l", "jsr 0x44c7e.l")),
    (0x4A2CA, "draw_player_initials_entry", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "pea.l 0x58054.l", "pea.l 0x58062.l", "jsr 0x4a44a.l")),
    (0x4D1A4, "secret_bonus_earned", "void", "D0.l = -1 when the current secret-task/progress state earns the secret-room coin bonus, else 0", "", "Verified", ("moveq 0xff, d0", "clr.w d0", "ext.l d0")),
    (0x4D476, "show_level_end_bonus_screen", "void", "void", "calls fixed draw_string through A3 = 0x25A", "Verified", ("movea.l 0x25a, a3", "pea.l 0x5ab1a.l", "pea.l 0x5ab46.l", "jsr 0x4d900.l", "jsr 0x486fe.l")),
    (0x4D900, "player_activecount", "void", "D0.l = count (0..4) of player statuses 1, 2, 8, or 0x10", "", "Verified", ("cmpi.b 0x1, (a1, d1.w)", "cmpi.b 0x10, (a1, d1.w)", "cmpi.b 0x2, (a1, d1.w)", "cmpi.b 0x8, (a1, d1.w)", "ext.l d0")),
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
    for address, name, _, _, _, _, required in CONTRACTS:
        opcodes = analyze_body(root, loader, address)
        for expected in required:
            if expected not in opcodes:
                raise SystemExit(f"{name}: required instruction absent: {expected}")
        if "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    print(f"player-lifecycle contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
    output = here / "player_lifecycle_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("player_lifecycle_contracts.csv is stale; regenerate it")
        print(f"player_lifecycle_contracts.csv: verified {len(rows)} entries")
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
