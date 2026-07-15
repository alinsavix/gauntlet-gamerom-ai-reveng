#!/usr/bin/env python3
"""Reconcile analyzed instruction bytes, ROM flags, and §5 table ranges."""

from __future__ import annotations

import argparse
import csv
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from generate_control_target_report import analyze_one, dispatch_entries, function_rows


ROM_START = 0x40000
ROM_END = 0x5FFFF
MIXED_RANGES = ((0x40000, 0x5561F), (0x56E54, 0x5FFB1))


def parse_flags(text: str) -> tuple[list[tuple[int, int, str]], set[str]]:
    function_names = {
        name
        for _, name in re.findall(
            r"^af\+ (0x[0-9A-Fa-f]+) ([^\s]+)", text, re.MULTILINE
        )
    }
    flags: list[tuple[int, int, str]] = []
    for name, size_text, address_text in re.findall(
        r"^'?f ([^\s]+) (\d+) (0x[0-9A-Fa-f]+)$", text, re.MULTILINE
    ):
        address = int(address_text, 16)
        size = int(size_text)
        if ROM_START <= address <= ROM_END and size:
            flags.append((address, size, name))
    return flags, function_names


def parse_size(cell: str) -> int | None:
    clean = re.sub(r"[*_`]", "", cell)
    product = re.search(r"(\d+)\s*[×x]\s*(\d+)\s*B\b", clean, re.I)
    if product:
        return int(product.group(1)) * int(product.group(2))
    byte_sizes = re.findall(r"(\d+)\s*B\b", clean, re.I)
    return int(byte_sizes[-1]) if byte_sizes else None


def parse_catalog(text: str) -> list[dict[str, object]]:
    section = text[text.index("## 5. ROM Data Tables Catalog") :]
    section = section.split("\n## 6.", 1)[0]
    rows: list[dict[str, object]] = []
    for line in section.splitlines():
        match = re.match(r"^\|\s*0x([0-9A-Fa-f]{5})\b[^|]*\|([^|]+)\|(.+)\|\s*$", line)
        if not match:
            continue
        size = parse_size(match.group(2))
        if size is None:
            continue
        description = match.group(3).strip()
        names = re.findall(r"`([^`]+)`", description)
        rows.append(
            {
                "address": int(match.group(1), 16),
                "size": size,
                "catalog_name": names[0] if names else re.sub(r"[*_]", "", description).split(" — ", 1)[0].strip(),
            }
        )
    return rows


def parse_header_catalog(text: str) -> list[dict[str, object]]:
    section = text[text.index("## 4. Game ROM Header and Hook Tables") :]
    section = section.split("\n## 5.", 1)[0]
    rows: list[dict[str, object]] = []
    for line in section.splitlines():
        match = re.match(
            r"^\| `0x([0-9A-Fa-f]{5})` \| (\d+) B \| `([^`]+)` \|",
            line,
        )
        if match:
            rows.append(
                {
                    "address": int(match.group(1), 16),
                    "size": int(match.group(2)),
                    "catalog_name": match.group(3),
                }
            )
    return rows


def analyzed_code(root: Path, entries: list[tuple[int, str]]) -> tuple[set[int], list[dict[str, str]]]:
    loader = root / "doc" / "gauntlet_loader.r2"
    code: set[int] = set()
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(lambda item: analyze_one(root, loader, item), entries)
        for result in results:
            address = int(result["address"])
            name = str(result["name"])
            if "error" in result:
                failures.append(
                    {"function_address": f"0x{address:05X}", "name": name, "error": str(result["error"])}
                )
                continue
            body = result["body"]
            assert isinstance(body, dict)
            for op in body.get("ops", []):
                op_address = int(op["addr"])
                op_size = int(op.get("size", 0))
                code.update(range(op_address, op_address + op_size))
    return code, failures


def is_mixed(address: int) -> bool:
    return any(start <= address <= end for start, end in MIXED_RANGES)


def make_reports(root: Path) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    doc = root / "doc"
    index_entries = function_rows((doc / "07_function_index.md").read_text())
    rom = (root / "row76.bin").read_bytes()
    entries = sorted(set(index_entries + dispatch_entries(rom)))
    code, failures = analyzed_code(root, entries)
    flags, function_names = parse_flags((root / "gauntlet.r2").read_text())
    entry_addresses = {address for address, _ in index_entries}
    # The archival database uses both `af+` records and ordinary sized flags for
    # callable entries.  Exclude either representation from the data-range side
    # of the reconciliation; otherwise every sized veneer appears to overlap its
    # own analyzed instructions.
    data_flags = [
        item
        for item in flags
        if item[2] not in function_names and item[0] not in entry_addresses
    ]
    catalog = parse_catalog((doc / "05_data_reference.md").read_text())
    header_catalog = parse_header_catalog((doc / "02_os_rom.md").read_text())

    flag_bytes: dict[int, set[str]] = {}
    for start, size, name in data_flags:
        for address in range(max(start, ROM_START), min(start + size, ROM_END + 1)):
            flag_bytes.setdefault(address, set()).add(name)

    catalog_bytes: dict[int, set[str]] = {}
    for row in catalog:
        start = int(row["address"])
        size = int(row["size"])
        name = str(row["catalog_name"])
        for address in range(max(start, ROM_START), min(start + size, ROM_END + 1)):
            catalog_bytes.setdefault(address, set()).add(name)

    segments: list[dict[str, str]] = []
    segment_start = ROM_START
    previous: tuple[bool, bool, tuple[str, ...], tuple[str, ...]] | None = None
    for address in range(ROM_START, ROM_END + 2):
        state = None if address > ROM_END else (
            is_mixed(address),
            address in code,
            tuple(sorted(flag_bytes.get(address, set()))),
            tuple(sorted(catalog_bytes.get(address, set()))),
        )
        if previous is None:
            previous = state
            segment_start = address
            continue
        if state == previous:
            continue
        mixed, has_code, names, catalog_names = previous
        if has_code and names:
            classification = "analyzed_code_and_named_range"
            confidence = "Strong inference"
        elif has_code:
            classification = "analyzed_code"
            confidence = "Verified"
        elif names:
            classification = "named_rom_range"
            confidence = "Verified"
        elif mixed:
            classification = "unclassified_mixed_byte"
            confidence = "Unknown"
        else:
            classification = "top_level_nonmixed_region"
            confidence = "Verified"
        segments.append(
            {
                "start": f"0x{segment_start:05X}",
                "end_inclusive": f"0x{address - 1:05X}",
                "size_bytes": str(address - segment_start),
                "classification": classification,
                "rom_flags": ";".join(names),
                "catalog_rows": ";".join(catalog_names),
                "confidence": confidence,
            }
        )
        segment_start = address
        previous = state

    catalog_by_range: dict[tuple[int, int], list[str]] = {}
    for row in catalog:
        catalog_by_range.setdefault(
            (int(row["address"]), int(row["size"])), []
        ).append(str(row["catalog_name"]))
    header_by_range: dict[tuple[int, int], list[str]] = {}
    for row in header_catalog:
        header_by_range.setdefault(
            (int(row["address"]), int(row["size"])), []
        ).append(str(row["catalog_name"]))

    flag_reconciled: list[dict[str, str]] = []
    for address, size, name in sorted(data_flags):
        catalog_names = sorted(catalog_by_range.get((address, size), []))
        header_names = sorted(header_by_range.get((address, size), []))
        if catalog_names:
            status = "exact_catalog_match"
        elif header_names:
            status = "exact_header_match"
        else:
            status = "missing_exact_documentation"
        flag_reconciled.append(
            {
                "address": f"0x{address:05X}",
                "size_bytes": str(size),
                "flag_name": name,
                "matching_catalog_rows": ";".join(catalog_names),
                "matching_header_rows": ";".join(header_names),
                "status": status,
                "confidence": "Verified" if catalog_names or header_names else "Unknown",
            }
        )

    reconciled: list[dict[str, str]] = []
    exact_flags = {(start, size): [] for start, size, _ in data_flags}
    for start, size, name in data_flags:
        exact_flags.setdefault((start, size), []).append(name)
    for row in catalog:
        address = int(row["address"])
        size = int(row["size"])
        names = sorted(exact_flags.get((address, size), []))
        reconciled.append(
            {
                "address": f"0x{address:05X}",
                "size_bytes": str(size),
                "catalog_name": str(row["catalog_name"]),
                "matching_flags": ";".join(names),
                "status": "exact_match" if names else "missing_exact_flag",
                "confidence": "Verified" if names else "Unknown",
            }
        )

    overlaps: list[dict[str, str]] = []
    for row in segments:
        names = row["rom_flags"].split(";") if row["rom_flags"] else []
        if len(names) > 1 or row["classification"] == "analyzed_code_and_named_range":
            overlap = row.copy()
            if len(names) > 1 and row["classification"] == "named_rom_range":
                overlap["classification"] = "intentional_overlapping_views"
                overlap["confidence"] = "Verified"
            overlaps.append(overlap)
    return segments, reconciled, flag_reconciled, overlaps, failures


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    reports = make_reports(here.parent.parent)
    outputs = (
        (here / "rom_byte_coverage.csv", reports[0], ["start", "end_inclusive", "size_bytes", "classification", "rom_flags", "catalog_rows", "confidence"]),
        (here / "rom_catalog_reconciliation.csv", reports[1], ["address", "size_bytes", "catalog_name", "matching_flags", "status", "confidence"]),
        (here / "rom_flag_reconciliation.csv", reports[2], ["address", "size_bytes", "flag_name", "matching_catalog_rows", "matching_header_rows", "status", "confidence"]),
        (here / "rom_range_overlaps.csv", reports[3], ["start", "end_inclusive", "size_bytes", "classification", "rom_flags", "catalog_rows", "confidence"]),
        (here / "rom_byte_coverage_failures.csv", reports[4], ["function_address", "name", "error"]),
    )
    if args.check:
        for path, rows, _ in outputs:
            with path.open(newline="") as stream:
                if list(csv.DictReader(stream)) != rows:
                    raise SystemExit(f"{path.name} is stale; regenerate it")
    else:
        for path, rows, fields in outputs:
            write_csv(path, rows, fields)
    unknown_segments = [row for row in reports[0] if row["confidence"] == "Unknown"]
    mismatches = [row for row in reports[1] if row["status"] != "exact_match"]
    flag_mismatches = [
        row for row in reports[2] if row["status"] == "missing_exact_documentation"
    ]
    print(
        f"ROM byte coverage: {len(reports[0])} segments, {len(unknown_segments)} unknown; "
        f"{len(reports[1])} catalog rows, {len(mismatches)} without exact flags; "
        f"{len(reports[2])} data flags, {len(flag_mismatches)} without exact docs; "
        f"{len(reports[3])} overlap segments, {len(reports[4])} analysis failures"
    )
    if unknown_segments or mismatches or flag_mismatches or reports[4]:
        raise SystemExit("ROM byte coverage reconciliation is incomplete")


if __name__ == "__main__":
    main()
