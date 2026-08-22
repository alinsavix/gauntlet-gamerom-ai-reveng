#!/usr/bin/env python3
"""Generate and verify contracts for the OS destructive RAM-test state machines."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, convention, byte prefix
ROWS = (
    (0x0A2C, "mem_test_short", "Fill the range with zero, then run two bug-limited high-bit walking-pattern stages on A1 only", "A1=start; A2=end inclusive; A4=completion/failure continuation", "D4.w=0 success or 1 failure via JMP (A4)", "register entry; never RTS; A6 chains stages", "4286"),
    (0x0A42, "mem_test_short_walk_ones", "Schedule high-bit-first walking-one pass over zero base; watchdog write limits it to A1", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "33c000803100"),
    (0x0A52, "mem_test_short_walk_zeroes", "Schedule high-bit-first walking-zero pass over all-ones base; watchdog write limits it to A1", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "33c000803100"),
    (0x0A62, "mem_test_short_done", "Finish the short RAM test", "inherited D4.w status; A4=caller continuation", "D4.w status via JMP (A4)", "A6 continuation; tail-jumps through A4", "33c000803100"),
    (0x0A6A, "mem_test_full", "Run the extended destructive RAM test suite", "A1=start; A2=end inclusive; A4=completion/failure continuation", "D4.w=0 success or 1 failure via JMP (A4)", "register entry; never RTS; A6 chains stages", "4286"),
    (0x0A7A, "mem_test_full_walk_ones_highbit", "Schedule high-bit-first walking-one pass over zero base; watchdog write limits it to A1", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000a84"),
    (0x0A84, "mem_test_full_walk_zeroes_highbit", "Schedule high-bit-first walking-zero pass over all-ones base; watchdog write limits it to A1", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000a8e"),
    (0x0A8E, "mem_test_full_walk_ones_lowbit", "Schedule low-bit-first walking-one pass over zero base", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000a98"),
    (0x0A98, "mem_test_full_walk_zeroes_lowbit", "Schedule low-bit-first walking-zero pass over all-ones base", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000aa2"),
    (0x0AA2, "mem_test_full_restore_ones_highbit", "Schedule high-bit walking-one restore pass; watchdog write limits it to A1", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000aac"),
    (0x0AAC, "mem_test_full_restore_ones_lowbit", "Schedule low-bit walking-one pass that restores the zero base", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000ab6"),
    (0x0AB6, "mem_test_full_fill_ones", "Fill the tested range with 0xFFFF before inverse restore passes", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "70ff"),
    (0x0AC2, "mem_test_full_restore_zeroes_highbit", "Schedule high-bit walking-zero restore pass; watchdog write limits it to A1", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000acc"),
    (0x0ACC, "mem_test_full_restore_zeroes_lowbit", "Schedule low-bit walking-zero pass that restores the all-ones base", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000ad6"),
    (0x0AD6, "mem_test_full_toggle_words", "Schedule per-word 0x0000/0xFFFF inversion verification", "inherited A1/A2/A4; D4/D6 state", "continues through A6 or fails through A4", "A6 continuation entry", "4df900000ae0"),
    (0x0AE0, "mem_test_full_done", "Finish the extended RAM test", "inherited D4.w status; A4=caller continuation", "D4.w status via JMP (A4)", "A6 continuation; tail-jumps through A4", "4ed4"),
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
    if int(body.get("addr", -1)) != int(address) or int(body.get("size", 0)) <= 0:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "empty or misbased analysis body"}
    if any(str(op.get("type", "")) == "ill" for op in body.get("ops", [])):
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "invalid instruction in analyzed body"}
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
    report = here / "os_memory_test_contracts.csv"
    failure_report = here / "os_memory_test_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS memory-test contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS memory-test contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS memory-test contract verification failed")


if __name__ == "__main__":
    main()
