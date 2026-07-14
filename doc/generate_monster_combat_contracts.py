#!/usr/bin/env python3
"""Generate and verify monster/shot-combat callable contracts."""

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
    (0x40E6A, "monsters_everything", "uint16 first_mob_offset", "void", "frameless wrapper saves D2-D7/A2-A6 before reading the normal first stack argument", "Verified", ("movem.l d2-d7/a2-a6, -(a7)", "move.w 0x32(a7), d2")),
    (0x40FAE, "monster_loop_core", "D2.w current doubled MOB offset; A2-A6 MOB arrays; outer local stack frame", "no independent return; continues the outer iteration/epilogue", "interior branch entry in monsters_everything", "Verified", ("move.w (a5, d2.w), d6", "move.b (a7), d6")),
    (0x4119A, "monster_special_handler", "D2.w current doubled MOB offset, D4/D5 H/V state, D6.w monster type; A2-A6 MOB arrays; caller-pushed type word", "no independent return; continues the outer iteration/epilogue", "interior branch entry sharing monsters_everything registers and stack", "Verified", ("btst.b 0x5, d4", "bsr.w 0x41750")),
    (0x414A4, "monster_update_anim_tile", "D2.w current doubled MOB offset, D6.w animation-table selector; A2 picture array, A6 state array", "no independent return; continues the outer iteration/epilogue", "interior branch entry sharing monsters_everything registers and stack", "Verified", ("lea.l 0x40db2.l, a0", "move.w (a0, d0.w), (a2, d2.w)")),
    (0x41750, "monster_find_and_shoot", "D2.w current doubled MOB offset; A2/A3/A4 picture/H/V arrays, A6 state array; caller-pushed monster type word", "void", "BSR-only shared-stack entry; reads the type word at 8(A6) after LINK", "Verified", ("link.w a6, 0xfff4", "move.w 0x8(a6), d0")),
    (0x41B16, "find_unused_shot", "D4.w initial doubled shot offset; A2 picture array", "D4.w selected doubled shot offset; Z set when the slot is free", "BSR-only register entry", "Verified", ("tst.w (a2, d4.w)", "tst.w (a0, d4.w)")),
    (0x41B52, "monster_shooter_in_view", "D4.b horizontal coordinate, D5.b vertical coordinate", "D4.l = -1 in view or 0 outside; Z reflects result", "BSR-only register entry", "Verified", ("moveq 0xff, d4", "moveq 0x0, d4")),
    (0x41B7E, "apply_direction_from_delta", "D2.w current offset, D3.w target offset, D4/D5 current H/V; A3/A4 H/V arrays, A6 state array", "void; writes direction bits in the current MOB state", "BSR-only register entry", "Verified", ("move.w (a3, d3.w), d0", "andi.w 0xe3ff, (a6, d2.w)")),
    (0x490DC, "monster_create_shot", "uint16 monster_slot, uint16 direction, uint16 shot_slot", "void", "", "Verified", ("move.w 0xa(a6), d5", "move.w 0xe(a6), d4", "move.w 0x12(a6), d2")),
    (0x492C0, "handle_generate", "uint16 generator_slot, uint16 generated_type, uint16 spawn_probability", "void", "", "Verified", ("move.w 0xa(a6), d4", "move.w 0xe(a6), d2", "move.w 0x12(a6), d3")),
    (0x495A6, "monster_playerhit", "uint16 player_slot, uint16 monster_slot", "void", "", "Verified", ("move.w 0xa(a6), d0", "move.w 0xe(a6), d2")),
    (0x40906, "shot_mob_collision", "uint16 shot_mob_slot, uint16 shooter_id", "D0.w target slot or -1 when no collision", "frameless leaf reads both normal stack arguments before saving D2-D7/A2-A3", "Verified", ("move.w 0x6(a7), d0", "move.w 0xa(a7), d1", "moveq 0xff, d0")),
    (0x40A78, "shot_collision_candidate_core", "D0.w candidate offset, D1.w doubled shooter offset, D3.w axis limit, D4.w self offset, D5.w sum limit, D6/D7 shot H/V; A0/A1/A2 H/V/picture arrays", "D0.w retained/tagged candidate offset; D2.w candidate type/result or -1; N signals rejection", "BSR-only register entry", "Verified", ("cmpi.w 0x40, d0", "moveq 0xff, d2")),
    (0x4AF50, "resolve_shot_hit", "uint16 target_slot_or_playfield_code, uint16 shooter_id", "D0.l = 0 shot survives or -1 shot consumed", "", "Verified", ("move.w 0xa(a6), d4", "move.w 0xe(a6), d3", "jmp 0x4b338(pc, d0.w)")),
    (0x4AEA0, "shot_onscreen_check", "uint16 target_slot, uint16 horizontal_limit, uint16 vertical_limit", "D0.l = -1 in range or 0 outside", "", "Verified", ("move.w 0xa(a6), d0", "move.w 0xe(a6), d2", "move.w 0x12(a6), d3", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x53818, "shot_reflect_calc", "uint16 target_slot_or_playfield_code, uint16 shooter_id", "D0.w reflected direction", "computed-dispatch body; standard stack entry", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3", "jmp 0x538fe(pc, d0.w)")),
    (0x5303A, "wall_crumble", "uint16 packed_slot, uint16 damage", "D0.l = -1 wall destroyed or 0 wall remains", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3", "move.l d1, d0")),
    (0x54112, "dragon_shot_hit", "uint16 target_slot, uint16 shooter_id", "void", "", "Verified", ("move.w 0xa(a6), d4", "move.w 0xe(a6), d3")),
    (0x54B68, "dragon_shot_hitbox_adjust", "D0.w candidate offset, D3.w axis limit, D5.w sum limit, D6/D7 shot H/V", "D0.w candidate offset, plus 0x1000 on head overlap", "register-argument leaf called only by shot_mob_collision; clobbers D2/D6/A3", "Verified", ("lea.l 0x54bd6.l, a3", "addi.w 0x1000, d0")),
    (0x47DAE, "shot_impact_spawn", "uint16 target_slot, uint16 shooter_slot", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3")),
)

INTERIOR_SITES = {
    0x40FAE: (0x40FA4, 0x414D4, 0x414FA),
    0x4119A: (0x41066,),
    0x414A4: (0x413D8, 0x4142C, 0x41434, 0x41498),
}


def direct_sites(rom: bytes) -> dict[int, list[int]]:
    targets = {address for address, *_ in CONTRACTS}
    found = {address: list(INTERIOR_SITES.get(address, ())) for address in targets}
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
        if "rts" not in opcodes:
            raise SystemExit(f"{name}: analyzed body has no RTS")
    print(f"monster/combat contracts: analyzed {len(CONTRACTS)} bodies; ABI evidence matches")


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
    output = here / "monster_combat_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("monster_combat_contracts.csv is stale; regenerate it")
        print(f"monster_combat_contracts.csv: verified {len(rows)} entries")
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
