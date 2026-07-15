#!/usr/bin/env python3
"""Generate and verify the first OS boot/diagnostic ABI-contract batch."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x03B6, "normal_boot_spare_test_done", "Handle full spare-RAM result and start color-RAM test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x03C4, "normal_boot_spare_error_ack", "Wait for acknowledgement after spare-RAM error and resume color test", "inherited hardware switch/status state", "no ordinary return", "A4 continuation from error display", "33c000803100"),
    (0x0424, "normal_boot_color_test_done", "Handle full color-RAM result and start playfield test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x04A4, "normal_boot_playfield_test_done", "Handle full playfield-RAM result and start alpha test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x0512, "normal_boot_alpha_test_done", "Handle full alpha-RAM result and start MOB test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x0582, "normal_boot_mob_test_done", "Handle full MOB-RAM result and enter main initialization", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x0652, "selftest_spare_test_done", "Handle short spare-RAM result and start color test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x0660, "selftest_spare_error_ack", "Resume short diagnostics after spare-RAM error display", "inherited hardware status", "no ordinary return", "A4 continuation from error display", "33c000803100"),
    (0x067C, "selftest_color_test_done", "Handle short color-RAM result and start playfield test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x06A6, "selftest_playfield_test_done", "Handle short playfield-RAM result and start alpha test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x06D0, "selftest_alpha_test_done", "Handle short alpha-RAM result and start MOB test", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x06FC, "selftest_mob_test_done", "Handle short MOB-RAM result and enter main initialization", "inherited D4.w=test status", "no ordinary return", "A4 continuation from memory tester", "4a44"),
    (0x08EC, "boot_postcheck_dispatch", "Finish hardware/EEPROM checks, clear work RAM, and dispatch OS or game", "D5.w=boot/error mode", "no return", "shared branch target; tail-dispatches", "4a45"),
    (0x0D26, "game_descriptor_ram_test", "Run the short memory test for a game checksum-descriptor RAM range", "A0=start; A1=end", "returns through game_descriptor_ram_test_done", "saves complete register set and tail-enters tester with A4 continuation", "48e7fffe"),
    (0x0D3A, "game_descriptor_ram_test_done", "Restore descriptor-test state and display a failing address", "inherited D4.w=test status; A5=saved stack frame", "returns to game_descriptor_ram_test caller", "A4 continuation; restores another entry's saved registers", "4a44"),
    (0x0D7A, "game_rom_checksum_error", "Identify and display a failed even/odd game-ROM checksum slice", "D0.b/D1.b=checksum accumulators; A0=range end; inherited descriptor frame in A6", "D5.w=2; otherwise void", "register and inherited-frame helper", "33fc000000803120"),
    (0x0F04, "playfield_add_word_test_range", "Add a word delta to 4,095 tested playfield words", "delta in low word of one normal longword slot", "void", "", "302f0006"),
    (0x11FC, "color_test_palette_init", "Install fixed six-word diagnostic color palette", "void", "void", "", "427900910000"),
    (0x1228, "selftest_load_control_labels", "Copy game-specific or default control labels into OS work buffers", "void", "void", "", "2f0a"),
    (0x16F6, "copy_cstring", "Copy a NUL-terminated string including its terminator", "destination pointer; source pointer", "void", "frameless normal stack entry", "226f0004"),
)


def analyze_one(root: Path, loader: Path, row: tuple[object, ...]) -> dict[str, str]:
    address, name, *_ = row
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader),
        "-c", f"af- 0x{int(address):x}; af @ 0x{int(address):x}; s 0x{int(address):x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [
        line for line in completed.stderr.splitlines()
        if line.startswith(("ERROR", "FATAL"))
    ]
    if completed.returncode or errors:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        body = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": f"invalid pdfj: {exc}"}
    if int(body.get("addr", -1)) != int(address) or int(body.get("size", 0)) <= 0:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "empty or misbased analysis body"}
    if any(str(op.get("type", "")) == "ill" for op in body.get("ops", [])):
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "invalid instruction in analyzed body"}
    return {}


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rom = (root / "row9.bin").read_bytes()
    records: list[dict[str, str]] = []
    prefix_failures: list[dict[str, str]] = []
    for address, name, purpose, arguments, returns, convention, prefix in ROWS:
        actual = rom[address : address + len(prefix) // 2].hex()
        if actual != prefix:
            prefix_failures.append({"address": f"0x{address:04X}", "name": name, "error": f"byte prefix {actual} != {prefix}"})
        records.append(
            {
                "address": f"0x{address:04X}",
                "name": name,
                "purpose": purpose,
                "arguments": arguments,
                "return": returns,
                "exceptional_convention": convention,
                "confidence": "Verified",
            }
        )
    with ThreadPoolExecutor(max_workers=8) as executor:
        analysis_failures = [
            failure for failure in executor.map(
                lambda row: analyze_one(root, root / "doc" / "gauntlet_loader.r2", row),
                ROWS,
            ) if failure
        ]
    return records, prefix_failures + analysis_failures


def write_csv(path: Path, records: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    records, failures = generated(here.parent.parent)
    report = here / "os_boot_contracts.csv"
    failure_report = here / "os_boot_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS boot contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS boot contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS boot contract verification failed")


if __name__ == "__main__":
    main()
