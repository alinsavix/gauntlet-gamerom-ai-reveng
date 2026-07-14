#!/usr/bin/env python3
"""Generate and verify high-level OS self-test screen/orchestration contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x0FCA, "run_color_test", "Build the color-RAM test palettes and patterns, display the Color Test screen, and wait for advance", "void", "void", "", "48e73020"),
    (0x129A, "os_selftest_loop", "Run the repeating OS diagnostic sequence and optional game test hooks", "one mode long supplied by 0x0E14 but not read by this body", "no return", "normal call entry whose control graph loops forever instead of executing RTS", "48e73038"),
    (0x1632, "display_init_clear", "Clear alpha and playfield display memory, reset the MOB list heads, and initialize diagnostic colors", "void", "void", "", "2f02207c"),
    (0x17D4, "run_alpha_test", "Populate the alpha display with word and large-glyph test patterns and wait for advance", "void", "void", "", "2f0a247c"),
    (0x1B20, "run_motion_object_test", "Create and interactively edit the Motion Object Test sprites, fields, and palettes", "void", "void", "", "48e73f3c"),
    (0x21A0, "validate_game_rom", "Call the optional game ROM/Slapstic verifier and display its failed bank checks", "void", "D0.l = 1 when valid, 0 after displaying a failure", "", "48e73000"),
    (0x229C, "run_sound_test", "Reset, diagnose, and interactively exercise the sound CPU, music, effects, and speech paths", "void", "void", "", "48e73e38"),
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
        records.append({
            "address": f"0x{address:04X}", "name": name, "purpose": purpose,
            "arguments": arguments, "return": returns,
            "exceptional_convention": convention, "confidence": "Verified",
        })
    with ThreadPoolExecutor(max_workers=7) as executor:
        failures.extend(
            failure
            for failure in executor.map(
                lambda row: analyze(root, root / "doc" / "gauntlet_loader.r2", row), ROWS
            )
            if failure
        )
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
    records, failures = generated(here.parent)
    report = here / "os_selftest_screen_contracts.csv"
    failure_report = here / "os_selftest_screen_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS self-test screen contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS self-test screen contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS self-test screen contract verification failed")


if __name__ == "__main__":
    main()
