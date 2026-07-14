#!/usr/bin/env python3
"""Generate and verify OS EEPROM initialization, queue, codec, and worker contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x432E, "eeprom_process", "Advance the VBLANK counter and process at most one verification/write step or one queued asynchronous read", "void", "void", "normal stack ABI; serializes EEPROM writes through unlock register 0x803150", "2f0a45f900904fa8"),
    (0x44E8, "eeprom_init", "Validate the game hook, allocate the difficulty-sized configuration image on the caller stack, load/check/correct redundant EEPROM blocks, and queue repairs", "void", "D0.l = 0 initialized, 1 invalid game-hook header, or -1 on terminal initialization/error-state exit", "nonstandard persistent stack allocation: removes the return address, reserves the configuration image, then restores the return address below it", "41f9000400003010"),
    (0x4674, "eeprom_decode_block", "Select a ten-byte destination from A2/D3 and decode one thirty-byte redundant EEPROM block with syndrome correction", "A2 = configuration image; A3 = EEPROM base; D2 = physical block; D3 = destination record", "D0.l = 0 clean, positive for a correctable syndrome, negative for uncorrectable syndrome; D2 and D3 increment", "register-only internal entry; falls into 0x467C shared decoder", "700ac0c343f20000"),
    (0x467C, "eeprom_decode_block_to", "Decode one thirty-byte redundant EEPROM block into an explicitly supplied ten-byte destination", "A1 = destination; A2 = configuration image/error counter context; A3 = EEPROM base; D2 = physical block; D3 = record counter", "D0.l = 0 clean, positive for a correctable syndrome, negative for uncorrectable syndrome; D2 and D3 increment", "register-only shared entry used by synchronous reads", "2002e9409042d040"),
    (0x4770, "eeprom_clear_statistics", "Clear the 200-byte high-score/statistics area and queue EEPROM regions 4-11", "A2 = configuration image", "void", "register-only initialization helper; tail-enters shared request-bitmap update", "303c00c74232001e"),
    (0x4784, "eeprom_clear_configuration", "Clear configuration bytes 0-9, 16-18, and 20-29 and queue EEPROM regions 0-2", "A2 = configuration image", "void", "register-only initialization helper; tail-enters shared request-bitmap update", "70094232000051c8"),
    (0x47A8, "eeprom_request_write", "Queue one logical EEPROM region by setting its request-bitmap bit", "region index long", "D0.l = supplied region index", "normal stack veneer over 0x47AC register entry", "202f00047201e1a1"),
    (0x47AC, "eeprom_request_write_register", "Queue one logical EEPROM region already selected in D0", "D0.l = region index", "D0.l = supplied region index", "register-only shared entry", "7201e1a183b90090"),
    (0x47B8, "eeprom_clear_difficulty_rows", "Clear all allocated difficulty histogram rows and queue their logical EEPROM regions", "A2 = configuration image", "void", "register-only initialization helper; returns immediately when difficulty is zero, otherwise tail-enters shared request-bitmap update", "7007c0390004006f"),
    (0x4802, "eeprom_check_busy", "Test the write bitmap, asynchronous-read ring, and active byte-write pointer", "void", "D0.l = 1 when any EEPROM work is pending, 0 when idle", "normal stack ABI", "43f900904fa82029"),
    (0x4822, "eeprom_read_block", "Read and verify a logical EEPROM block synchronously or enqueue an asynchronous read", "destination pointer; logical block index word; mode long (zero synchronous, nonzero queued)", "D0.l = 1 success/queued, 0 invalid/busy/full; synchronous decode also returns -1 correctable syndrome or -2 uncorrectable syndrome", "normal mixed-width three-slot stack ABI", "48e7303045f90090"),
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
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": f"invalid analysis JSON: {exc}"}
    ops = body.get("ops", [])
    if int(body.get("addr", -1)) != int(address) or int(body.get("size", 0)) <= 0 or any(str(op.get("type", "")) == "ill" for op in ops):
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
    records, failures = generated(here.parent)
    report = here / "os_eeprom_contracts.csv"
    failure_report = here / "os_eeprom_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS EEPROM contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS EEPROM contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS EEPROM contract verification failed")


if __name__ == "__main__":
    main()
