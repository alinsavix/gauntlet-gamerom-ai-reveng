#!/usr/bin/env python3
"""Generate and verify MOB-list and depth-placement calling contracts."""

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
# requires RTS in analyzed body, required opcodes
CONTRACTS = (
    (0x5DC58, "mob_create", "uint16 mob_slot, uint16 picture, uint16 hpos, uint16 vpos, uint16 object_type, uint16 object_state", "void", "frameless; saves D2-D7/A2-A6 before reading six normal stack slots", "Verified", True, ("move.w 0x32(a7), d1", "move.w 0x36(a7), (a2, d1.w)", "move.w 0x3a(a7), (a3, d1.w)", "move.w 0x3e(a7), (a4, d1.w)", "bsr.b 0x5dcbc")),
    (0x5DCBC, "moblist_insert", "D1.w = doubled destination slot; A2-A6 = picture/H/V/link/state arrays", "void", "BSR-only register entry", "Verified", True, ("move.w (a2, d1.w), d0", "lea.l 0x905f80.l, a1", "lea.l 0x904940.l, a0", "move.w d6, 0x9049de.l")),
    (0x5DD72, "moblist_replace", "uint16 source_slot, uint16 destination_slot", "void", "frameless; saves D2-D7/A2-A6 before reading normal stack slots", "Verified", True, ("move.w 0x32(a7), d2", "move.w 0x36(a7), d1", "bsr.b 0x5de0a")),
    (0x5DDA8, "moblist_remove", "uint16 mob_slot", "void", "frameless wrapper; preserves object fields and clears only link indices; no discovered direct control site", "Verified", True, ("move.w 0x32(a7), d2", "bsr.w 0x5ded4")),
    (0x5DDDA, "moblist_remove_and_clear", "uint16 mob_slot", "void", "frameless wrapper", "Verified", True, ("move.w 0x32(a7), d2", "bsr.b 0x5de44")),
    (0x5DE0A, "move_mob_slot", "D2.w = doubled source slot, D1.w = doubled destination slot; A2-A6 = picture/H/V/link/state arrays", "void", "register entry; falls through into moblist_remove_and_clear_regs", "Verified", True, ("bsr.w 0x5dcbc", "move.w (a2, d2.w), (a2, d1.w)", "move.w (a3, d2.w), (a3, d1.w)", "move.w (a4, d2.w), (a4, d1.w)", "moveq 0x0, d0")),
    (0x5DE44, "moblist_remove_and_clear_regs", "D2.w = doubled mob slot; A2-A6 = picture/H/V/link/state arrays", "void", "register entry; unlinks and zeros all five slot words", "Verified", True, ("move.w (a5, d2.w), d4", "cmp.w 0x9049de.l, d6", "lea.l 0x905f80.l, a1", "move.w d0, (a2, d2.w)", "move.w d0, (a6, d2.w)")),
    (0x5DED4, "moblist_unlink_regs", "D2.w = doubled mob slot; A2-A6 = picture/H/V/link/state arrays", "void", "register entry; preserves object fields and upper link/state bits", "Verified", True, ("move.w (a5, d2.w), d4", "cmp.w 0x9049de.l, d6", "lea.l 0x905f80.l, a1", "move.w 0xfc00, d0", "and.w d0, (a6, d2.w)")),
    (0x5DF68, "mob_place_shot", "uint16 depth_key, uint16 physical_slot", "void", "tail-branches into shared saved-register body at 0x5DFA6; slot bias 0", "Verified", False, ("movem.l d3-d7/a5-a6, -(a7)", "move.w 0x26(a7), d7", "bra.b 0x5dfa6")),
    (0x5DF72, "mob_place_anim", "uint16 depth_key, uint16 logical_channel", "void", "tail-branches into shared saved-register body at 0x5DFA6; physical slot = channel + 0x11", "Verified", False, ("movem.l d3-d7/a5-a6, -(a7)", "move.w 0x26(a7), d7", "addi.w 0x11, d7", "bra.b 0x5dfa6")),
    (0x5DF9C, "mob_place_explosion", "uint16 depth_key, uint16 logical_channel", "void", "falls through into shared saved-register body at 0x5DFA6; physical slot = channel + 1", "Verified", True, ("movem.l d3-d7/a5-a6, -(a7)", "move.w 0x26(a7), d7", "addq.w 0x1, d7", "move.w 0x22(a7), d6")),
    (0x5DFA6, "insert_mob_depth_sorted", "D7.w = resolved physical slot; first wrapper stack argument at 0x22(A7) = uint16 depth_key", "void", "shared inherited saved-register body; exits through wrapper epilogue", "Verified", True, ("move.w 0x22(a7), d6", "lea.l 0x904940.l, a0", "move.w d7, 0x9049de.l", "move.w d6, (a0, d7.w)", "movem.l (a7)+, d3-d7/a5-a6")),
    (0x5E064, "mob_depth_remove", "uint16 physical_slot_minus_one", "void", "frameless normal-stack wrapper; resolves physical slot by adding 1", "Verified", True, ("move.w 0x22(a7), d2", "addq.w 0x1, d2", "cmp.w 0x9049de.l, d6", "lea.l 0x904940.l, a0", "move.w d0, (a0, d2.w)")),
)

DIRECT_SITE_OVERRIDES = {
    # Three tail branches; 0x5DF9C reaches the shared body by fall-through.
    0x5DFA6: (0x5DF66, 0x5DF70, 0x5DF7E),
}


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
    for target, sites in DIRECT_SITE_OVERRIDES.items():
        found[target].extend(sites)
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
    for address, name, _, _, _, _, require_rts, required in CONTRACTS:
        opcodes = analyze_body(root, loader, address)
        for expected in required:
            if expected not in opcodes:
                raise SystemExit(f"{name}: required instruction absent: {expected}")
        if require_rts and "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS/shared epilogue")
        if not require_rts and "bra.b 0x5dfa6" not in opcodes:
            raise SystemExit(f"{name}: tail branch to shared body absent")
    print(f"MOB-list contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
        for address, name, arguments, return_value, convention, confidence, _, _ in CONTRACTS
    ]
    output = here / "mob_list_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("mob_list_contracts.csv is stale; regenerate it")
        print(f"mob_list_contracts.csv: verified {len(rows)} entries")
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
