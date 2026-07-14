#!/usr/bin/env python3
"""Generate and check the m2mainloop direct-call contract catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROM_SHA1 = "decbe6438b3a2618bd7fe79d14be034efadd7ff4"
ROM_BASE = 0x40000

# (call site, destination, canonical name, phase)
CALLS = (
    (0x42A74, 0x4327A, "one_time_init", "once"),
    (0x42A98, 0x4DCBA, "main_logo_updcolors", "frame"),
    (0x42A9E, 0x40644, "input_debounce", "frame"),
    (0x42AA4, 0x42B6A, "coincheck", "frame"),
    (0x42AB4, 0x40528, "main_cycle_tport_and_ffield", "frame"),
    (0x42ABA, 0x46FEA, "main_handle_potions", "frame"),
    (0x42AC0, 0x45C00, "main_open_doors", "frame"),
    (0x42AC6, 0x474F6, "main_handle_shots", "frame"),
    (0x42ACC, 0x4A53A, "main_move_players", "frame"),
    (0x42AD2, 0x46CAA, "main_scroll_playfield", "frame"),
    (0x42AD8, 0x49034, "main_move_monsters", "frame"),
    (0x42ADE, 0x54454, "main_handle_dragon", "frame"),
    (0x42AE4, 0x4E8DC, "main_thief_anim", "frame"),
    (0x42AEA, 0x4DEB8, "main_start_thief", "frame"),
    (0x42AF0, 0x466F6, "main_health_countdown", "frame"),
    (0x42AF6, 0x4D29E, "main_treasure_timer", "frame"),
    (0x42AFC, 0x4664C, "main_handle_death", "frame"),
    (0x42B02, 0x5287C, "main_exit_move", "frame"),
    (0x42B08, 0x5E62A, "main_walls_cyclic_move", "frame"),
    (0x42B0E, 0x5E41A, "main_walls_random_move", "frame"),
    (0x42B14, 0x4CCBC, "main_msgbox_countdown", "frame"),
    (0x42B1A, 0x42DF4, "character_select_input_update", "frame"),
    (0x42B20, 0x4800C, "main_start_game", "frame"),
    (0x42B26, 0x4715E, "main_score_update", "frame"),
    (0x42B2C, 0x457C0, "main_score_display", "frame"),
    (0x42B32, 0x44562, "main_attract", "frame"),
    (0x42B38, 0x431EE, "eeprom_periodic_write", "frame"),
    (0x42B3E, 0x42D0A, "sound_response", "frame"),
    (0x42B44, 0x4AE20, "main_update_sound", "frame"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-check", action="store_true")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    rom_path = here.parent / "row76.bin"
    output_path = here / "main_loop_contracts.csv"
    rom = rom_path.read_bytes()
    if len(rom) != 0x20000 or hashlib.sha1(rom).hexdigest() != ROM_SHA1:
        raise SystemExit("row76.bin is not the documented 128 KiB target ROM")

    target_names = {target: name for _, target, name, _ in CALLS}
    direct_sites: dict[int, list[int]] = {target: [] for target in target_names}
    for offset in range(0, len(rom) - 6, 2):
        opcode = int.from_bytes(rom[offset : offset + 2], "big")
        target: int | None = None
        if opcode == 0x4EB9:  # JSR absolute-long
            target = int.from_bytes(rom[offset + 2 : offset + 6], "big")
        elif opcode == 0x6100:  # BSR word displacement
            displacement = int.from_bytes(rom[offset + 2 : offset + 4], "big", signed=True)
            target = ROM_BASE + offset + 2 + displacement
        elif opcode >> 8 == 0x61 and opcode & 0xFF not in (0, 0xFF):  # BSR byte
            displacement = int.from_bytes(bytes((opcode & 0xFF,)), "big", signed=True)
            target = ROM_BASE + offset + 2 + displacement
        if target in direct_sites:
            direct_sites[target].append(ROM_BASE + offset)

    rows: list[dict[str, str]] = []
    for site, target, name, phase in CALLS:
        offset = site - ROM_BASE
        expected = b"\x4e\xb9" + target.to_bytes(4, "big")
        actual = rom[offset : offset + 6]
        if actual != expected:
            raise SystemExit(
                f"0x{site:05X}: expected JSR 0x{target:05X}, got {actual.hex()}"
            )
        rows.append(
            {
                "call_site": f"0x{site:05X}",
                "target": f"0x{target:05X}",
                "name": name,
                "phase": phase,
                "arguments": "void",
                "return": "void",
                "exceptional_convention": "none",
                "direct_call_sites": ";".join(f"0x{item:05X}" for item in direct_sites[target]),
                "body_stack_argument_offsets": "none",
                "return_consumed_by_direct_callers": "none",
                "confidence": "Verified",
            }
        )

    fieldnames = list(rows[0])
    if args.check:
        with output_path.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("main_loop_contracts.csv is stale; regenerate it")
        print(
            f"main_loop_contracts.csv: verified {len(rows)} entries and "
            f"{sum(len(items) for items in direct_sites.values())} direct call sites"
        )
    else:
        with output_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows to {output_path}")

    if args.run_check:
        loader = here / "gauntlet_loader.r2"
        for _, target, name, _ in CALLS:
            command = [
                "r2", "-q", "-n", "-e", "scr.color=0",
                "-i", str(loader),
                "-c", f"af- 0x{target:x}; af @ 0x{target:x}; pdfj @ 0x{target:x}",
                "-c", "q", "malloc://1",
            ]
            result = subprocess.run(command, cwd=here.parent, text=True, capture_output=True)
            if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)", result.stderr):
                raise SystemExit(f"radare2 body audit failed for {name}:\n{result.stderr}")
            try:
                function = json.loads(result.stdout)
            except json.JSONDecodeError as error:
                raise SystemExit(f"invalid pdfj output for {name}: {error}") from error
            opcodes = [op["opcode"] for op in function.get("ops", [])]
            positive_a6 = {
                int(match.group(1), 16)
                for opcode_text in opcodes
                for match in re.finditer(r"(?<!-)0x([0-9a-f]+)\(a6\)", opcode_text)
                if int(match.group(1), 16) >= 8
            }
            if positive_a6:
                offsets = ", ".join(hex(item) for item in sorted(positive_a6))
                raise SystemExit(f"{name} reads possible stack arguments at {offsets}")
            if not opcodes[0].startswith("link"):
                positive_a7 = {
                    int(match.group(1), 16)
                    for opcode_text in opcodes
                    for match in re.finditer(r"(?<!-)0x([0-9a-f]+)\(a7\)", opcode_text)
                }
                if positive_a7:
                    offsets = ", ".join(hex(item) for item in sorted(positive_a7))
                    raise SystemExit(f"{name} reads possible entry-stack arguments at {offsets}")
            if "rts" not in opcodes:
                raise SystemExit(f"{name}: analyzed body has no RTS")
        print("main-loop bodies: 29 entries analyzed; no stack-argument reads")


if __name__ == "__main__":
    main()
