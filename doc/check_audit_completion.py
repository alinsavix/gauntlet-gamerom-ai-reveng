#!/usr/bin/env python3
"""Cross-check the evidence required to call the main-ROM audit complete."""

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


def require_contiguous(report: list[dict[str, str]], label: str) -> int:
    cursor = ROM_START
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
    if cursor != ROM_END + 1 or total != ROM_END - ROM_START + 1:
        raise SystemExit(f"{label} does not cover the full 128 KiB image")
    return total


def main() -> None:
    here = Path(__file__).resolve().parent

    regions = rows(here / "rom_regions.csv")
    require_contiguous(regions, "rom_regions.csv")
    if any(row["confidence"] != "Verified" for row in regions):
        raise SystemExit("rom_regions.csv contains a non-Verified range")

    byte_rows = rows(here / "rom_byte_coverage.csv")
    byte_count = require_contiguous(byte_rows, "rom_byte_coverage.csv")
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
    require_empty(here / "rom_byte_coverage_failures.csv")

    catalog = rows(here / "rom_catalog_reconciliation.csv")
    if not catalog or any(row["status"] != "exact_match" for row in catalog):
        raise SystemExit("not every §5 catalog row has an exact ROM flag")
    flags = rows(here / "rom_flag_reconciliation.csv")
    if not flags or any(
        row["status"] not in {"exact_catalog_match", "exact_header_match"}
        for row in flags
    ):
        raise SystemExit("not every non-code ROM flag has exact documentation")
    overlaps = rows(here / "rom_range_overlaps.csv")
    if any(row["classification"] != "intentional_overlapping_views" for row in overlaps):
        raise SystemExit("ROM overlap report contains a non-intentional overlap")

    callable_rows = rows(here / "callable_contract_coverage.csv")
    callable_addresses = {int(row["address"], 16) for row in callable_rows}
    if len(callable_rows) != len(callable_addresses) or any(
        row["confidence"] != "Verified" for row in callable_rows
    ):
        raise SystemExit("callable coverage is duplicate or not fully Verified")

    abi_addresses: set[int] = set()
    for path in sorted(here.glob("*_contracts.csv")):
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

    control = rows(here / "control_targets.csv")
    if any(
        row["confidence"] == "Unknown"
        or row["classification"].startswith("unresolved")
        for row in control
    ):
        raise SystemExit("control-target report contains an unresolved target")
    require_empty(here / "control_target_failures.csv")

    ram = rows(here / "ram_operands.csv")
    if any(not row["covering_flags"] or row["confidence"] != "Verified" for row in ram):
        raise SystemExit("RAM operand report contains an uncovered literal")
    require_empty(here / "ram_operand_failures.csv")
    linear_ram = rows(here / "ram_linear_reconciliation.csv")
    if any(row["status"] != "exact_union_match" for row in linear_ram):
        raise SystemExit("linear and callable-anchored RAM scans differ")
    require_empty(here / "ram_linear_scan_failures.csv")

    backlog = (here / "08_known_issues.md").read_text().split(
        "## Unresolvable from the supplied artifacts", 1
    )[0]
    if any(re.match(r"^\| P\d+ \|", line) for line in backlog.splitlines()):
        raise SystemExit("08_known_issues.md still contains an active prioritized issue")

    print(
        "audit completion: "
        f"{byte_count} ROM bytes; {len(callable_rows)} callable ABIs; "
        f"{len(catalog)} catalog rows; {len(flags)} non-code flags; "
        f"{len(ram)} RAM literals; no active backlog"
    )


if __name__ == "__main__":
    main()
