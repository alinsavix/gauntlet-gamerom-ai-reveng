#!/usr/bin/env python3
"""Build the unique OS callable-contract union, including every API veneer."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


CATALOGS = (
    "os_boot_contracts.csv",
    "os_memory_test_contracts.csv",
    "os_text_contracts.csv",
    "os_numeric_display_contracts.csv",
    "os_core_contracts.csv",
    "os_selftest_helper_contracts.csv",
    "os_selftest_screen_contracts.csv",
    "os_sound_contracts.csv",
    "os_coin_config_contracts.csv",
    "os_eeprom_contracts.csv",
    "os_operator_ui_contracts.csv",
)
API_ADDRESSES = (
    *range(0x100, 0x1D8, 6),
    *range(0x200, 0x22A, 6),
    *range(0x230, 0x27E, 6),
)
FIELDS = (
    "entry_kind", "address", "name", "target", "purpose", "arguments",
    "return", "exceptional_convention", "source_catalog", "confidence",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def generated(here: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    by_address: dict[int, tuple[dict[str, str], str]] = {}
    for filename in CATALOGS:
        for row in read_csv(here / filename):
            address = int(row["address"], 16)
            if address in by_address:
                failures.append({"address": row["address"], "issue": f"duplicate implementation contract in {by_address[address][1]} and {filename}"})
                continue
            by_address[address] = (row, filename)

    candidate_contracts = {
        address: contract
        for address, contract in by_address.items()
        if contract[0].get("kind") != "dispatch"
    }
    dispatch_contracts = {
        address: contract
        for address, contract in by_address.items()
        if contract[0].get("kind") == "dispatch"
    }
    candidates = {int(row["address"], 16): row for row in read_csv(here / "os_entry_candidates.csv")}
    for address in sorted(candidates.keys() - candidate_contracts.keys()):
        failures.append({"address": f"0x{address:04X}", "issue": "candidate root has no contract"})
    for address in sorted(candidate_contracts.keys() - candidates.keys()):
        failures.append({"address": f"0x{address:04X}", "issue": "contract address is not in candidate closure"})
    if len(candidates) != 168:
        failures.append({"address": "closure", "issue": f"expected 168 implementation/shared roots, found {len(candidates)}"})

    records: list[dict[str, str]] = []
    for address in sorted(candidates):
        if address not in candidate_contracts:
            continue
        row, filename = candidate_contracts[address]
        records.append({
            "entry_kind": "implementation",
            "address": f"0x{address:04X}",
            "name": row["name"],
            "target": "",
            "purpose": row["purpose"],
            "arguments": row["arguments"],
            "return": row["return"],
            "exceptional_convention": row["exceptional_convention"],
            "source_catalog": filename,
            "confidence": row["confidence"],
        })

    if len(dispatch_contracts) != 6:
        failures.append({"address": "dispatch", "issue": f"expected 6 computed-dispatch contracts, found {len(dispatch_contracts)}"})
    for address, (row, filename) in sorted(dispatch_contracts.items()):
        records.append({
            "entry_kind": "computed_dispatch",
            "address": f"0x{address:04X}",
            "name": row["name"],
            "target": "",
            "purpose": row["purpose"],
            "arguments": row["arguments"],
            "return": row["return"],
            "exceptional_convention": row["exceptional_convention"],
            "source_catalog": filename,
            "confidence": row["confidence"],
        })

    rom = (here.parent.parent / "row9.bin").read_bytes()
    if len(API_ADDRESSES) != 56:
        failures.append({"address": "api", "issue": f"expected 56 API addresses, generated {len(API_ADDRESSES)}"})
    for address in API_ADDRESSES:
        opcode = int.from_bytes(rom[address : address + 2], "big")
        target = int.from_bytes(rom[address + 2 : address + 6], "big")
        if opcode != 0x4EF9:
            failures.append({"address": f"0x{address:04X}", "issue": f"API opcode 0x{opcode:04X} is not JMP absolute"})
            continue
        contract = by_address.get(target)
        if contract is None:
            failures.append({"address": f"0x{address:04X}", "issue": f"API target 0x{target:04X} has no implementation contract"})
            continue
        row, filename = contract
        records.append({
            "entry_kind": "api_veneer",
            "address": f"0x{address:04X}",
            "name": row["name"],
            "target": f"0x{target:04X}",
            "purpose": f"Fixed OS API absolute-JMP veneer to {row['name']}",
            "arguments": row["arguments"],
            "return": row["return"],
            "exceptional_convention": f"absolute JMP veneer; target convention: {row['exceptional_convention']}",
            "source_catalog": filename,
            "confidence": "Verified",
        })

    records.sort(key=lambda row: (int(row["address"], 16), row["entry_kind"]))
    if len(records) != 230:
        failures.append({"address": "union", "issue": f"expected 230 callable/dispatch entries, generated {len(records)}"})
    return records, failures


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    records, failures = generated(here)
    report = here / "os_callable_contracts.csv"
    failure_report = here / "os_callable_contract_failures.csv"
    if args.check:
        if read_csv(report) != records or read_csv(failure_report) != failures:
            raise SystemExit("OS callable-contract union reports are stale")
    else:
        write_csv(report, records, FIELDS)
        write_csv(failure_report, failures, ("address", "issue"))
    print(f"OS callable-contract union: {len(records)} entries; {len(failures)} failures")
    if failures:
        raise SystemExit("OS callable-contract union failed")


if __name__ == "__main__":
    main()
