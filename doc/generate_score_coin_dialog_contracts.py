#!/usr/bin/env python3
"""Generate and verify scoring, coin, HUD, sound, and dialog contracts."""

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
    (0x40628, "calc_score_per_coin", "uint32 score, uint16 coin_count", "D0.l = unsigned 32-bit score / coin_count", "frameless two-stage 68000 32/16 division leaf", "Verified", ("move.w 0xa(a7), d1", "move.w 0x4(a7), d0", "divu.w d1, d0", "swap d0")),
    (0x42B6A, "coincheck", "void", "void", "", "Verified", ("move.l 0x904fec.l, d1", "jsr 0x166.l", "jsr 0x488ca.l")),
    (0x452D0, "setup_infopanel", "int16 player_selector (-1 = whole panel)", "void", "", "Verified", ("move.w 0xa(a6), d0", "movea.l 0x25a, a2", "movea.l 0x142, a3", "jsr 0x45940.l", "jsr 0x459a2.l")),
    (0x457C0, "main_score_display", "void", "void", "", "Verified", ("andi.w 0x3, d0", "jsr 0x45940.l", "jsr 0x459a2.l")),
    (0x45940, "draw_player_score", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "jsr 0x260.l", "andi.b 0xfe, (a0, d2.w)")),
    (0x459A2, "draw_player_health", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "jsr 0x260.l", "andi.b 0xfd, (a0, d2.w)")),
    (0x4715E, "main_score_update", "void", "void", "", "Verified", ("movea.l 0x902000, a2", "movea.l 0x904ba4, a3", "subq.w 0x1, (a0, d0.w)")),
    (0x488CA, "player_coindrop", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "jsr 0x4ad76.l", "jsr 0x452d0.l")),
    (0x48B58, "update_monster_bonus_from_score_per_coin", "void", "void", "", "Verified", ("moveq 0x3, d2", "divs.w d3, d0", "add.b d0, 0x90405f.l")),
    (0x49498, "playfield_showscore", "uint16 source_mob_slot, uint16 popup_type_index", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d4", "move.w 0x3c, (a0, d0.w)", "jsr 0x5df72.l")),
    (0x49BD0, "highscore_table_init", "void", "void", "", "Verified", ("jsr 0x1a8.l", "jsr 0x1b4.l", "move.b 0x41, 0x1(a1, d0.w)")),
    (0x49D0E, "highscore_check", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "jsr 0x1c6.l", "jsr 0x452d0.l")),
    (0x4A124, "attract_highscores", "void", "void", "calls fixed OS draw/display service indirectly through A2 = 0x200", "Verified", ("movea.l 0x200, a2", "jsr 0x40d24.l", "jsr (a2)", "jsr 0x260.l")),
    (0x4A2CA, "draw_player_initials_entry", "uint16 player_index", "void", "", "Verified", ("move.w 0xa(a6), d2", "pea.l 0x58054.l", "pea.l 0x58062.l", "jsr 0x4a44a.l")),
    (0x4AD4E, "sound_speech_play", "uint8 sound_id", "void", "", "Verified", ("move.b 0x7(a7), d1", "andi.l 0x800, d0", "jsr 0x4ad76.l")),
    (0x4AD76, "sound_play", "uint8 sound_id", "void", "", "Verified", ("move.b 0xb(a7), d2", "jsr 0x242.l", "jsr 0x4add6.l")),
    (0x4C440, "dialog_first_encounter", "uint16 player_index, uint32 encounter_mask, optional uint16 numeric_value", "D0.l = 1 when the selected dialog has a speech entry, else 0", "third argument is consumed only by the numeric-message record; other call sites pass only player and mask", "Verified", ("move.w 0xa(a6), d3", "move.l 0xc(a6), d2", "move.w 0x12(a6), d4", "moveq 0x1, d6", "move.w d6, d0")),
    (0x4C70A, "dialog_clear_message", "int16 last_character_index", "void", "", "Verified", ("move.w 0xa(a6), d0", "move.b 0x20, (a0)+", "clr.b (a0)+")),
    (0x4C72A, "player_give_item_with_message", "uint16 player_index, uint16 item_index", "D0.l = 1 when the item is newly granted, else 0", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d2", "moveq 0x0, d0", "moveq 0x1, d0")),
    (0x4CB50, "dialog_position_box", "int16 player_index_or_minus1", "void", "", "Verified", ("move.w 0xa(a6), d0", "cmpi.w 0xffff, d0", "movea.l 0x904aa0, a1")),
    (0x4CCBC, "main_msgbox_countdown", "void", "void", "", "Verified", ("movea.l 0x904a9e, a0", "subq.w 0x1, (a0)", "clr.w (a1)")),
    (0x4D1A4, "secret_bonus_earned", "void", "D0.l = -1 when the current secret-task/progress state earns the secret-room coin bonus, else 0", "", "Verified", ("moveq 0xff, d0", "clr.w d0", "ext.l d0")),
    (0x4DE76, "score_screen_color_cycle", "void", "void", "", "Verified", ("movea.l 0x910140, a2", "moveq 0xb, d0", "move.w -(a3), -(a2)")),
    (0x5214C, "player_add_score_with_mult", "uint16 player_index, uint16 base_score", "void", "", "Verified", ("move.w 0xa(a6), d3", "move.w 0xe(a6), d4", "mulu.w d4, d0", "add.l d0, (a0, d1.w)")),
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
    print(f"score/coin/dialog contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")


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
    output = here / "score_coin_dialog_contracts.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("score_coin_dialog_contracts.csv is stale; regenerate it")
        print(f"score_coin_dialog_contracts.csv: verified {len(rows)} entries")
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
