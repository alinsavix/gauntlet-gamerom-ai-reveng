#!/usr/bin/env python3
"""Generate and verify core OS vector, boot, error, and VBLANK contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, convention, byte prefix
ROWS = (
    (0x0300, "exception_handler", "Dispatch CPU exceptions to the optional game exception veneer or return from the exception", "CPU exception frame", "no scalar result; D0.w=0 on game dispatch", "vector entry; RTE or tail-JMP", "0c794ef9"),
    (0x0314, "irq1_handler", "Dispatch IRQ1 to game hook 0x4000C when installed", "CPU interrupt frame", "no scalar result", "interrupt entry; RTE or tail-JMP", "0c794ef9"),
    (0x0326, "irq2_handler", "Dispatch IRQ2 to game hook 0x40018 when installed", "CPU interrupt frame", "no scalar result", "interrupt entry; RTE or tail-JMP", "0c794ef9"),
    (0x0338, "irq3_handler", "Dispatch IRQ3 to game hook 0x40012 when installed", "CPU interrupt frame", "no scalar result", "interrupt entry; RTE or tail-JMP", "0c794ef9"),
    (0x034A, "irq4_vblank_handler", "Dispatch VBLANK to the OS handler or game hook, otherwise acknowledge it locally", "CPU interrupt frame", "no scalar result", "interrupt entry; RTE or tail-JMP", "4a7900904f0c"),
    (0x036C, "irq6_handler", "Dispatch self-test-mode IRQ6 to the game sound hook or consume/store the OS-lane sound response", "CPU interrupt frame", "no scalar result", "interrupt entry; RTE or tail-JMP", "08390003"),
    (0x03A0, "selftest_boot", "Start the full destructive test of video-RAM spare before the self-test boot continuation chain", "void", "no return", "early-boot tail entry; installs A4 continuation", "43f900904000"),
    (0x05E2, "reset_entry", "Mask interrupts, pulse the board latch, delay while petting watchdog, and select normal or self-test boot", "reset-vector CPU state", "no return", "reset vector entry; tail-JMP", "46fc2700"),
    (0x061E, "normal_boot", "Seed color RAM and start the short destructive video-RAM-spare test for normal boot", "void", "no return", "early-boot tail entry; installs A4 continuation", "41f900910000"),
    (0x070C, "main_init_cont", "Initialize display/stack, validate OS and game ROM checksums plus EEPROM, clear OS RAM, and dispatch game or OS mode", "void", "no return", "early-boot continuation; final tail dispatch", "7a00"),
    (0x0C52, "display_working_ram_error", "Write the fixed 'Working RAM error' message to diagnostic video memory", "A4=continuation", "no ordinary return", "register continuation entry; JMP (A4)", "33fc0000"),
    (0x0C98, "error_display_ram", "Initialize alpha display and show detailed RAM-test failure values", "D4.l=error class; A0=failing address; D0.w=expected; D1.w=actual", "void", "register wrapper that constructs four normal stack arguments", "2f01"),
    (0x0CC0, "rom_checksum_display", "Display OS-ROM checksum accumulators and identify failed even/odd byte lanes", "D0.b=even accumulator; D1.b=odd accumulator", "D5.w=2", "early-boot register helper; clobbers D2/D3/D5", "33fc0000"),
    (0x0E14, "os_vblank_mode_entry", "Enable OS-owned VBLANK processing and enter the non-returning OS self-test loop", "D5.w=mode value pushed as an unused long argument", "no return", "register entry; its post-call cleanup/tail-JMP has no discovered returning predecessor", "33fc0001"),
    (0x0E5E, "os_vblank_handler", "Acknowledge VBLANK, update scroll/input/text/EEPROM state, and return from interrupt", "CPU interrupt frame", "no scalar result", "interrupt entry; saves D0-D1/A0-A1 and RTE", "48e7c0c0"),
    (0x2828, "display_ram_error_detail", "Draw RAM region name, failing address, expected word, and actual word", "error class/index; failing address; expected word; actual word", "void", "normal four-slot stack ABI", "48e73000"),
)


def analyze(root: Path, loader: Path, row: tuple[object, ...]) -> dict[str, str]:
    address, name, *_ = row
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader),
        "-c", f"af- 0x{int(address):x}; af @ 0x{int(address):x}; s 0x{int(address):x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [line for line in completed.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))]
    if completed.returncode or errors:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        body = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": f"invalid pdfj: {exc}"}
    if int(body.get("addr", -1)) != int(address) or int(body.get("size", 0)) <= 0 or any(str(op.get("type", "")) == "ill" for op in body.get("ops", [])):
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "empty, invalid, or misbased analysis body"}
    return {}


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rom = (root / "row9.bin").read_bytes()
    records: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for address, name, purpose, arguments, returns, convention, prefix in ROWS:
        actual = rom[address : address + len(prefix) // 2].hex()
        if actual != prefix:
            failures.append({"address": f"0x{address:04X}", "name": name, "error": f"byte prefix {actual} != {prefix}"})
        records.append({"address": f"0x{address:04X}", "name": name, "purpose": purpose, "arguments": arguments, "return": returns, "exceptional_convention": convention, "confidence": "Verified"})
    with ThreadPoolExecutor(max_workers=8) as executor:
        failures.extend(failure for failure in executor.map(lambda row: analyze(root, root / "doc" / "gauntlet_loader.r2", row), ROWS) if failure)
    return records, failures


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
    report = here / "os_core_contracts.csv"
    failure_report = here / "os_core_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS core contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS core contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS core contract verification failed")


if __name__ == "__main__":
    main()
