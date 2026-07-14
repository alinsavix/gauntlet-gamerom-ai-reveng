#!/usr/bin/env python3
"""Generate and verify RNG, memory, display-init, and Super Sorcerer contracts."""

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

# address, name, arguments, return, exception, confidence,
# audit start, audit byte count, required opcodes
CONTRACTS = (
    (0x5FC22, "random_seeded", "uint16 upper_bound, uint16 *seed", "D0.l = value in [0, upper_bound); 0 when upper_bound is 0", "normal-stack dormant veneer; no discovered direct control site", "Verified", 0x5FC22, 0x24, ("movea.l 0x8(a7), a0", "moveq 0x0, d0", "move.w 0x6(a7), d0", "move.w (a0), d1", "muls.w 0x3619, d1", "move.w d1, (a0)", "ext.l d0", "rts")),
    (0x5FC26, "random_bound_stack_core", "uint16 upper_bound on inherited caller stack; A0 = uint16 *seed", "D0.l = value in [0, upper_bound); 0 when upper_bound is 0", "mixed inherited-stack/register shared entry reached by getrandom", "Verified", 0x5FC26, 0x20, ("moveq 0x0, d0", "move.w 0x6(a7), d0", "muls.w d0, d1", "swap d0", "ext.l d0", "rts")),
    (0x5FC2C, "random_core", "D0.l = zero-extended upper_bound; A0 = uint16 *seed", "D0.l = value in [0, upper_bound); 0 when upper_bound is 0", "register shared body; updates *seed with seed = seed * 0x3619 + 0x5D35 modulo 2^16", "Verified", 0x5FC2C, 0x1A, ("move.w (a0), d1", "muls.w 0x3619, d1", "addi.w 0x5d35, d1", "move.w d1, (a0)", "muls.w d0, d1", "asr.l 0x1, d0", "add.l d1, d0", "ext.l d0", "rts")),
    (0x5FC46, "random_word", "D0.l = zero-extended upper_bound", "D0.l = value in [0, upper_bound); 0 when upper_bound is 0", "register wrapper using global random_seed; branches to random_core", "Verified", 0x5FC46, 0x08, ("lea.l 0x904bfc.l, a0", "bra.b 0x5fc2c")),
    (0x5FC4E, "getrandom", "uint16 upper_bound", "D0.l = value in [0, upper_bound); 0 when upper_bound is 0", "normal-stack wrapper using global random_seed; branches to random_bound_stack_core", "Verified", 0x5FC4E, 0x08, ("lea.l 0x904bfc.l, a0", "bra.b 0x5fc26")),
    (0x5FCCE, "pf_palette_clear", "void", "void", "tail-calls memclear_core for the final 0x40-longword shadow-color clear", "Verified", 0x5FCCE, 0x46, ("move.w d0, 0x90401e.l", "lea.l 0x910000.l, a0", "move.w 0x40, d0", "lea.l 0x910200.l, a0", "move.w 0x80, d0", "lea.l 0x910500.l, a0", "lea.l 0x910400.l, a0", "bra.w 0x5fd64")),
    (0x5FD14, "display_state_clear", "void", "void", "tail-calls memclear_core for the final 0x800-longword playfield clear", "Verified", 0x5FD14, 0x44, ("lea.l 0x905f80.l, a0", "move.w 0x20, d0", "move.w d0, 0x90400a.l", "move.w d0, 0x902000.l", "lea.l 0x905000.l, a0", "move.w 0x3c0, d0", "lea.l 0x900000.l, a0", "move.w 0x800, d0", "bra.b 0x5fd64")),
    (0x5FD58, "memclear", "uint16 count, uint32 *destination", "void", "normal-stack wrapper; pre-tested DBRA loop clears exactly count longwords and does nothing for zero", "Verified", 0x5FD58, 0x12, ("move.w 0x6(a7), d0", "movea.l 0x8(a7), a0", "bra.b 0x5fd64", "clr.l (a0)+", "dbra d0, 0x5fd62")),
    (0x5FD64, "memclear_core", "D0.w = count, A0 = uint32 *destination", "void", "register pre-test entry; clears exactly count longwords and does nothing for zero", "Verified", 0x5FD62, 0x08, ("clr.l (a0)+", "dbra d0, 0x5fd62", "rts")),
    (0x5FD6A, "copy_longwords", "uint16 count, const uint32 *source, uint32 *destination", "void", "normal-stack pre-tested DBRA loop copies exactly count longwords and does nothing for zero", "Verified", 0x5FD6A, 0x16, ("move.w 0x6(a7), d0", "movea.l 0x8(a7), a0", "movea.l 0xc(a7), a1", "move.l (a0)+, (a1)+", "dbra d0, 0x5fd78", "rts")),
    (0x5FD80, "palette_fade_copy", "uint16 count, const uint16 *source, uint16 *destination, uint16 delta", "void", "normal-stack pre-tested DBRA loop copies exactly count words; preserves D2", "Verified", 0x5FD80, 0x2C, ("move.w 0xa(a7), d0", "movea.l 0xc(a7), a0", "movea.l 0x10(a7), a1", "move.w 0x16(a7), d1", "sub.w d1, d2", "andi.w 0xfff, d2", "ori.w 0x1000, d2", "dbra d0, 0x5fd94", "rts")),
    (0x5FDB8, "supersorc_place_helper", "uint16 target_mob_slot, uint16 starting_player_index", "D0.w = packed destination tile; 0 when no placement is possible", "normal-stack wrapper; loads D2=2*target_mob_slot and fixed A2/A3/A4 MOB-array bases", "Verified", 0x5FDB8, 0x28, ("move.w 0x16(a7), d2", "move.w 0x1a(a7), d0", "add.w d2, d2", "lea.l 0x902000.l, a2", "lea.l 0x902800.l, a3", "lea.l 0x903000.l, a4", "bsr.b 0x5fde0", "rts")),
    (0x5FDE0, "supersorc_place", "D0.w = starting player index; D2.w = target MOB byte offset; A2/A3/A4 = picture/hpos/vpos bases", "D0.w = packed destination tile; 0 when no placement is possible", "register body; tries four players cyclically and three behind-player direction biases", "Verified", 0x5FDE0, 0x1B8, ("move.w d0, d6", "lea.l 0x9048c8.l, a0", "lea.l 0x9049a4.l, a0", "lea.l 0x5fdac.l, a0", "lea.l 0x5fdb2.l, a0", "bsr.w 0x5e57e", "cmpi.w 0x6, -0x6(a6)", "andi.w 0x6, d6", "moveq 0x0, d0", "move.w d4, d0", "rts")),
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

    # Tail/shared-body branches are intentional entry sites, not subroutine calls.
    found[0x5FC26].append(0x5FC54)
    found[0x5FC2C].append(0x5FC4C)
    found[0x5FD64].extend((0x5FD10, 0x5FD56, 0x5FD60))
    return {address: sorted(set(sites)) for address, sites in found.items()}


def opcodes(root: Path, loader: Path, start: int, size: int) -> list[str]:
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0",
        "-i", str(loader), "-c", f"pDj {size} @ 0x{start:x}", "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)", result.stderr):
        raise SystemExit(f"radare2 utility audit failed at 0x{start:X}:\n{result.stderr}")
    return [item["opcode"] for item in json.loads(result.stdout)]


def runtime_check(root: Path) -> None:
    loader = root / "doc" / "gauntlet_loader.r2"
    for address, name, _, _, _, _, start, size, required in CONTRACTS:
        operations = opcodes(root, loader, start, size)
        for expected in required:
            if expected not in operations:
                raise SystemExit(f"{name} (0x{address:X}): required instruction absent: {expected}")
    print(f"utility/init contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
            "exceptional_convention": exception,
            "direct_control_sites": ";".join(f"0x{site:05X}" for site in sites[address]),
            "confidence": confidence,
        }
        for address, name, arguments, return_value, exception, confidence, _, _, _ in CONTRACTS
    ]

    output = here / "utility_init_contracts.csv"
    if args.check:
        with output.open(newline="") as handle:
            old_rows = list(csv.DictReader(handle))
        if old_rows != rows:
            raise SystemExit("utility_init_contracts.csv is stale; regenerate it")
        print(f"utility_init_contracts.csv: verified {len(rows)} entries")
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
