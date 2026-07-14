#!/usr/bin/env python3
"""Build the complete live, residue, retained-module, dispatch, and API union."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDS = (
    "entry_kind", "address", "name", "purpose", "arguments", "return",
    "exceptional_convention", "reachability", "source_catalog", "confidence",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def generated(here: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    callable_path = here / "os_callable_contracts.csv"
    for row in read_csv(callable_path):
        kind = row["entry_kind"]
        rows.append({
            "entry_kind": kind,
            "address": row["address"],
            "name": row["name"],
            "purpose": row["purpose"],
            "arguments": row["arguments"],
            "return": row["return"],
            "exceptional_convention": row["exceptional_convention"],
            "reachability": "fixed public veneer" if kind == "api_veneer" else "active OS control closure",
            "source_catalog": "os_callable_contracts.csv",
            "confidence": row["confidence"],
        })
    for filename, kind in (("os_residue_contracts.csv", "active_image_residue"), ("os_legacy_module_contracts.csv", "retained_module")):
        for row in read_csv(here / filename):
            rows.append({
                "entry_kind": kind,
                "address": row["address"],
                "name": row["name"],
                "purpose": row["purpose"],
                "arguments": row["arguments"],
                "return": row["return"],
                "exceptional_convention": row["exceptional_convention"],
                "reachability": row["reachability"],
                "source_catalog": filename,
                "confidence": row["confidence"],
            })
    seen: dict[int, str] = {}
    for row in rows:
        address = int(row["address"], 16)
        if address in seen:
            failures.append({"address": row["address"], "issue": f"duplicate entry in {seen[address]} and {row['source_catalog']}"})
        seen[address] = row["source_catalog"]
    counts = {
        "implementation": sum(row["entry_kind"] == "implementation" for row in rows),
        "active_image_residue": sum(row["entry_kind"] == "active_image_residue" for row in rows),
        "retained_module": sum(row["entry_kind"] == "retained_module" for row in rows),
        "computed_dispatch": sum(row["entry_kind"] == "computed_dispatch" for row in rows),
        "api_veneer": sum(row["entry_kind"] == "api_veneer" for row in rows),
    }
    expected = {"implementation": 168, "active_image_residue": 5, "retained_module": 21, "computed_dispatch": 6, "api_veneer": 56}
    if counts != expected:
        failures.append({"address": "union", "issue": f"kind counts {counts} != {expected}"})
    rows.sort(key=lambda row: (int(row["address"], 16), row["entry_kind"]))
    if len(rows) != 256:
        failures.append({"address": "union", "issue": f"expected 256 rows, found {len(rows)}"})
    return rows, failures


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rows, failures = generated(here)
    report = here / "os_all_function_contracts.csv"; failure_report = here / "os_all_function_contract_failures.csv"
    if args.check:
        if read_csv(report) != rows or read_csv(failure_report) != failures:
            raise SystemExit("OS all-function reports are stale")
    else:
        write_csv(report, rows, FIELDS); write_csv(failure_report, failures, ("address", "issue"))
    print(f"OS all-function union: {len(rows)} entries; {len(failures)} failures")
    if failures:
        raise SystemExit("OS all-function union failed")


if __name__ == "__main__":
    main()
