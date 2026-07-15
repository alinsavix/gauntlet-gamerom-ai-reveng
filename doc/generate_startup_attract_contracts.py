#!/usr/bin/env python3
"""Generate and verify startup, attract, demo, title, and legend contracts."""

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
    (0x4327A, "one_time_init", "void", "void", "", "Verified", ("jsr 0x43486.l", "jsr 0x49bd0.l", "jsr 0x44414.l")),
    (0x43486, "init_display", "uint16 main_palette_index, uint16 special_palette_variant", "void", "calls the fixed copy_longwords body indirectly through A2 = 0x5FD6A", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d3", "movea.l 0x5fd6a, a2", "jsr (a2)")),
    (0x44204, "start_attract_to_game", "void", "void", "", "Verified", ("jsr 0x44db4.l", "jsr 0x438ae.l", "jsr 0x43486.l")),
    (0x4438E, "load_attract_display_tilemap", "void", "void", "", "Verified", ("movea.l 0x5cb28, a2", "movea.l 0x5850e, a0", "jsr 0x43486.l")),
    (0x44414, "start_attract_screen", "int16 screen_mode", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w d2, 0x904918.l", "jsr 0x4438e.l", "jsr 0x449d4.l")),
    (0x44562, "main_attract", "void", "void", "", "Verified", ("movea.l 0x904918, a2", "jsr 0x44414.l", "jsr 0x44204.l", "jsr 0x449cc.l")),
    (0x449CC, "attract_noop_hook", "void", "void", "", "Verified", ("link.w a6, 0x0", "unlk a6", "rts")),
    (0x449D4, "attract_demo_init", "void", "void", "", "Verified", ("pea.l 0x66.w", "jsr 0x40d24.l", "jsr 0x438ae.l", "move.l 0x581c4, 0x904b6a.l")),
    (0x44A82, "game_playfield_init", "void", "void", "OS invokes this callback through the JMP veneer at game-ROM 0x40030", "Verified", ("jsr 0x4438e.l", "move.w d0, (a0)", "movea.l 0x1dc.l, a1")),
    (0x44DB4, "show_level_start_screen", "void", "void", "calls fixed draw_string service indirectly through A3 = 0x25A", "Verified", ("movea.l 0x25a, a3", "jsr 0x5fc4e.l", "move.w 0x73, 0x904000.l", "cmpi.b 0x57, (a2)", "addq.w 0x1, 0x904000.l", "jsr 0x40d4e.l", "movea.l 0x57360, a0", "movea.l 0x5737c, a0", "movea.l 0x573d4, a0")),
    (0x4800C, "main_start_game", "void", "void", "", "Verified", ("jsr 0x438ae.l", "jsr 0x43486.l", "jsr 0x48b58.l")),
    (0x4C9A2, "demo_speech_cmd", "uint16 player_index, uint16 message_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d0", "movea.l 0x5815c, a0", "jsr 0x4cb50.l")),
    (0x4CD1C, "load_legend_page", "uint16 page_selector", "void", "", "Verified", ("move.w 0xa(a6), d2", "moveq 0x67, d1", "jsr 0x4cfae.l", "jsr 0x4cfda.l", "jsr 0x4cdb8.l")),
    (0x4CDB8, "draw_legend_monsters_page", "void", "void", "calls fixed draw_string service indirectly through A3 = 0x25A", "Verified", ("movea.l 0x25a, a3", "jsr 0x4d12e.l", "jsr (a3)")),
    (0x4CFAE, "draw_legend_overview_page", "void", "void", "", "Verified", ("pea.l 0x5a99c.l", "jsr 0x142.l", "pea.l 0x5ab0e.l")),
    (0x4CFDA, "draw_legend_rules_page", "void", "void", "calls alpha_clear_rect indirectly through A2 = 0x4D12E", "Verified", ("movea.l 0x4d12e, a2", "jsr (a2)", "pea.l 0x5a7e8.l")),
    (0x4D956, "scroll_apply", "int16 horizontal_delta, int16 vertical_delta", "D0.l = -1 for the zero/zero anchor-reset path, or 0 after a nonzero scroll", "", "Verified", ("move.w 0xa(a6), d2", "move.w 0xe(a6), d1", "moveq 0xff, d0", "moveq 0x0, d0")),
    (0x4DA3E, "title_logo_init", "void", "void", "", "Verified", ("move.l 0x5ac20, 0x904a20.l", "movea.l 0x5ac2e, a0", "movea.l 0x5ac4e, a0", "jsr 0x4d956.l")),
    (0x4DCBA, "main_logo_updcolors", "void", "void", "", "Verified", ("jsr 0x4de76.l", "jsr 0x4d956.l", "cmp.l d0, d1")),
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
    if rom[0x30:0x32] != b"\x4e\xf9" or int.from_bytes(rom[0x32:0x36], "big") != 0x44A82:
        raise SystemExit("game-ROM playfield-init JMP veneer at 0x40030 does not target 0x44A82")
    print(f"startup/attract contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
    output = here / "startup_attract_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("startup_attract_contracts.csv is stale; regenerate it")
        print(f"startup_attract_contracts.csv: verified {len(rows)} entries")
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
