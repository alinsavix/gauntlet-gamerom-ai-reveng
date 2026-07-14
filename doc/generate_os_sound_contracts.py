#!/usr/bin/env python3
"""Generate and verify OS sound submission, polling, receive, and reset contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x4184, "send_sound_command", "Submit a sound command with a direct response destination and byte count", "command word; response destination pointer; response byte count word", "D0.l = 1 when accepted, 0 when latch or direct-response channel is busy", "normal stack wrapper over 0x4198 register body", "43f900904f8e302f"),
    (0x4198, "send_sound_command_register", "Submit the packed command/direct-response request already loaded in registers", "D0.l = response count in high word and command in low word; A0 = response destination; A1 = sound state base", "D0.l = 1 when accepted, 0 when busy", "register entry shared with the 0x4184 wrapper", "40c146fc25000839"),
    (0x41C8, "send_sound_command_wait", "Wait until the sound latch is available and submit one command", "command word", "D0.l = 1", "normal stack veneer; D0=0 selects retry in shared body 0x41CE", "7000600270012040"),
    (0x41CC, "try_send_sound_command", "Attempt one sound-latch submission without waiting", "command word", "D0.l = 1 when accepted, 0 when busy", "normal stack veneer; D0=1 selects one attempt in shared body 0x41CE", "70012040302f0006"),
    (0x41FA, "process_sound", "Advance sound-status polling, coin-status delivery, EEPROM processing, and command-3 response polling", "void", "void", "normal stack ABI", "43f900904f8e1029"),
    (0x427A, "sound_receive_irq_body", "Receive one sound byte into the active direct destination or the 15-byte ring", "CPU interrupt frame", "no scalar result", "interrupt entry; saves D0/A0/A1 and returns with RTE", "48e780c043f90090"),
    (0x42C8, "read_sound_data", "Pop one byte from the 15-byte sound receive ring", "void", "D0.l = next byte, or -1 when empty", "normal stack ABI", "41f900904f8e1028"),
    (0x42F8, "reset_sound_cpu", "Assert sound reset, emit a startup command, clear queue/direct-response state, and release reset", "sound control word; startup command word", "void", "normal two-slot stack ABI", "43f900904f8e302f"),
)

BOUNDED = {0x4198: 0x30, 0x41C8: 0x32, 0x41CC: 0x2E}


def analyze(root: Path, loader: Path, row: tuple[object, ...]) -> dict[str, str]:
    address, name, *_ = row
    if int(address) in BOUNDED:
        analysis_command = f"s 0x{int(address):x}; pDj {BOUNDED[int(address)]}"
    else:
        analysis_command = f"af- 0x{int(address):x}; af @ 0x{int(address):x}; s 0x{int(address):x}; pdfj"
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader), "-c", analysis_command,
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
    if int(address) in BOUNDED:
        ops = body
        valid = bool(ops) and int(ops[0].get("addr", -1)) == int(address)
    else:
        ops = body.get("ops", [])
        valid = int(body.get("addr", -1)) == int(address) and int(body.get("size", 0)) > 0
    if not valid or any(str(op.get("type", "")) == "ill" for op in ops):
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
    with ThreadPoolExecutor(max_workers=8) as executor:
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
    report = here / "os_sound_contracts.csv"
    failure_report = here / "os_sound_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS sound contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS sound contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS sound contract verification failed")


if __name__ == "__main__":
    main()
