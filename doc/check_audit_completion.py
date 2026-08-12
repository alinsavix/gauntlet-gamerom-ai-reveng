#!/usr/bin/env python3
"""Cross-check the evidence required to call both ROM audits complete."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROM_START = 0x40000
ROM_END = 0x5FFFF


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def require_empty(path: Path) -> None:
    if rows(path):
        raise SystemExit(f"{path.name} is not empty")


def require_contiguous(report: list[dict[str, str]], label: str, start_address: int, end_address: int) -> int:
    cursor = start_address
    total = 0
    for row in report:
        start = int(row["start"], 16)
        end = int(row["end_inclusive"], 16)
        if start != cursor or end < start:
            raise SystemExit(
                f"{label} is not contiguous at 0x{cursor:05X}: "
                f"got 0x{start:05X}-0x{end:05X}"
            )
        total += end - start + 1
        cursor = end + 1
    if cursor != end_address + 1 or total != end_address - start_address + 1:
        raise SystemExit(f"{label} does not cover its full image")
    return total


def require_contiguous_exclusive(report: list[dict[str, str]], label: str, start_address: int, end_exclusive: int) -> int:
    cursor = start_address
    total = 0
    for row in report:
        start = int(row["start"], 16)
        end = int(row["end_exclusive"], 16)
        if start != cursor or end <= start:
            raise SystemExit(f"{label} is not contiguous at 0x{cursor:04X}")
        total += end - start
        cursor = end
    if cursor != end_exclusive or total != end_exclusive - start_address:
        raise SystemExit(f"{label} does not cover its full image")
    return total


def main() -> None:
    here = Path(__file__).resolve().parent
    artifacts = here / "generated"

    regions = rows(artifacts / "rom_regions.csv")
    require_contiguous(regions, "rom_regions.csv", ROM_START, ROM_END)
    if any(row["confidence"] != "Verified" for row in regions):
        raise SystemExit("rom_regions.csv contains a non-Verified range")

    byte_rows = rows(artifacts / "rom_byte_coverage.csv")
    byte_count = require_contiguous(byte_rows, "rom_byte_coverage.csv", ROM_START, ROM_END)
    bad_byte_rows = [
        row for row in byte_rows
        if row["confidence"] == "Unknown"
        or row["classification"] in {
            "unclassified_mixed_byte",
            "analyzed_code_and_named_range",
        }
    ]
    if bad_byte_rows:
        raise SystemExit("ROM byte report contains unknown or suspicious overlaps")
    require_empty(artifacts / "rom_byte_coverage_failures.csv")

    catalog = rows(artifacts / "rom_catalog_reconciliation.csv")
    if not catalog or any(row["status"] != "exact_match" for row in catalog):
        raise SystemExit("not every §5 catalog row has an exact ROM flag")
    flags = rows(artifacts / "rom_flag_reconciliation.csv")
    if not flags or any(
        row["status"] not in {"exact_catalog_match", "exact_header_match"}
        for row in flags
    ):
        raise SystemExit("not every non-code ROM flag has exact documentation")
    overlaps = rows(artifacts / "rom_range_overlaps.csv")
    if any(row["classification"] != "intentional_overlapping_views" for row in overlaps):
        raise SystemExit("ROM overlap report contains a non-intentional overlap")

    maze_catalog = rows(artifacts / "maze_catalog.csv")
    if [int(row["maze"]) for row in maze_catalog] != list(range(117)):
        raise SystemExit("maze_catalog.csv must contain exactly mazes 0 through 116")
    final_maze = maze_catalog[-1]
    if (
        final_maze["pointer"] != "0x3FE48"
        or final_maze["terminator_offset"]
        or int(final_maze["record_size"]) != 0x1A7
        or int(final_maze["bytes_after_record_to_boundary"]) != 0x11
        or int(final_maze["bank_table_overlap_bytes"]) != 0x0F
    ):
        raise SystemExit("maze 116 boundary/overlap metadata is not canonical")

    callable_rows = rows(artifacts / "callable_contract_coverage.csv")
    callable_addresses = {int(row["address"], 16) for row in callable_rows}
    if len(callable_rows) != len(callable_addresses) or any(
        row["confidence"] != "Verified" for row in callable_rows
    ):
        raise SystemExit("callable coverage is duplicate or not fully Verified")

    abi_addresses: set[int] = set()
    for path in sorted(artifacts.glob("*_contracts.csv")):
        for row in rows(path):
            key = "address" if "address" in row else "target" if "target" in row else ""
            if not key:
                continue
            # A blank exceptional_convention intentionally means the normal
            # convention; the user requested an annotation only when it differs.
            if all(row.get(field, "").strip() for field in ("arguments", "return")):
                abi_addresses.add(int(row[key], 16))
    missing_abi = sorted(callable_addresses - abi_addresses)
    if missing_abi:
        raise SystemExit(
            "callable entries lack explicit argument/return/convention rows: "
            + ", ".join(f"0x{address:05X}" for address in missing_abi)
        )

    control = rows(artifacts / "control_targets.csv")
    if any(
        row["confidence"] == "Unknown"
        or row["classification"].startswith("unresolved")
        for row in control
    ):
        raise SystemExit("control-target report contains an unresolved target")
    require_empty(artifacts / "control_target_failures.csv")

    ram = rows(artifacts / "ram_operands.csv")
    if any(not row["covering_flags"] or row["confidence"] != "Verified" for row in ram):
        raise SystemExit("RAM operand report contains an uncovered literal")
    require_empty(artifacts / "ram_operand_failures.csv")
    linear_ram = rows(artifacts / "ram_linear_reconciliation.csv")
    if any(row["status"] != "exact_union_match" for row in linear_ram):
        raise SystemExit("linear and callable-anchored RAM scans differ")
    require_empty(artifacts / "ram_linear_scan_failures.csv")

    os_regions = rows(artifacts / "os_rom_regions.csv")
    os_region_count = require_contiguous_exclusive(os_regions, "os_rom_regions.csv", 0, 0x10000)
    if any(row["confidence"] in {"Unknown", "Contradicted", "Hypothesis"} for row in os_regions):
        raise SystemExit("os_rom_regions.csv contains unresolved confidence")
    os_bytes = rows(artifacts / "os_rom_byte_coverage.csv")
    os_byte_count = require_contiguous(os_bytes, "os_rom_byte_coverage.csv", 0, 0xFFFF)
    if any(row["confidence"] != "Verified" or row["classification"].startswith("unknown") for row in os_bytes):
        raise SystemExit("OS byte report contains an unknown/unverified byte range")
    require_empty(artifacts / "os_rom_byte_coverage_failures.csv")

    os_data = rows(artifacts / "os_rom_data_catalog.csv")
    if len(os_data) != 42 or any(row["confidence"] in {"Unknown", "Contradicted", "Hypothesis"} for row in os_data):
        raise SystemExit("OS data catalog is incomplete or unresolved")
    os_functions = rows(artifacts / "os_all_function_contracts.csv")
    if len(os_functions) != 269 or any(
        row["confidence"] in {"Unknown", "Contradicted", "Hypothesis"}
        or not row["arguments"].strip() or not row["return"].strip()
        for row in os_functions
    ):
        raise SystemExit("OS all-function contract union is incomplete")
    for filename in (
        "os_all_function_contract_failures.csv",
        "os_residue_contract_failures.csv",
        "os_legacy_module_contract_failures.csv",
        "os_data_xref_failures.csv",
        "os_callable_contract_failures.csv",
        "os_control_target_failures.csv",
        "os_ram_operand_failures.csv",
    ):
        require_empty(artifacts / filename)

    backlog = (here / "08_known_issues.md").read_text().split(
        "## Unresolvable from the supplied artifacts", 1
    )[0]
    if any(re.match(r"^\| P\d+ \|", line) for line in backlog.splitlines()):
        raise SystemExit("08_known_issues.md still contains an active prioritized issue")

    print(
        "audit completion: "
        f"{byte_count} ROM bytes; {len(callable_rows)} callable ABIs; "
        f"{len(catalog)} ROM catalog rows; {len(maze_catalog)} maze records; "
        f"{len(flags)} non-code flags; "
        f"{len(ram)} RAM literals; {os_region_count} OS region bytes; "
        f"{os_byte_count} OS classified bytes; {len(os_functions)} OS function/veneer contracts; "
        f"{len(os_data)} OS data ranges; no active prioritized backlog row"
    )


if __name__ == "__main__":
    main()
