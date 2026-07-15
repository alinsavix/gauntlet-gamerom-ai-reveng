#!/usr/bin/env python3
"""Linearly rescan proven executable ROM ranges for main-RAM operands."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from generate_ram_operand_report import RAM_END, RAM_START, ram_flags


def code_ranges(path: Path) -> list[tuple[int, int]]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [
        (int(row["start"], 16), int(row["end_inclusive"], 16) + 1)
        for row in rows
        if row["classification"] == "analyzed_code"
    ]


def scan_one(
    root: Path, loader: Path, bounds: tuple[int, int]
) -> tuple[int, int, list[dict[str, object]], str]:
    start, end = bounds
    size = end - start
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader),
        "-c", f"s 0x{start:x}; pdj {size // 2}", "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [
        line for line in result.stderr.splitlines()
        if line.startswith(("ERROR", "FATAL"))
    ]
    if result.returncode or errors:
        return start, end, [], "; ".join(errors) or f"r2 exit {result.returncode}"
    try:
        ops = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return start, end, [], f"invalid pdj JSON: {exc}"
    cursor = start
    kept: list[dict[str, object]] = []
    for op in ops:
        address = int(op.get("addr", -1))
        if address >= end:
            break
        op_size = int(op.get("size", 0))
        if address != cursor:
            return start, end, kept, f"decode gap at 0x{cursor:05X}; next op 0x{address:05X}"
        if op_size <= 0 or address + op_size > end:
            return start, end, kept, f"instruction crosses range end at 0x{address:05X}"
        if str(op.get("type", "")) == "ill" or str(op.get("opcode", "")).startswith("invalid"):
            return start, end, kept, f"invalid instruction at 0x{address:05X}"
        kept.append(op)
        cursor = address + op_size
    if cursor != end:
        return start, end, kept, f"decode stopped at 0x{cursor:05X}, expected 0x{end:05X}"
    return start, end, kept, ""


def generated_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    ranges = code_ranges(doc / "generated" / "rom_byte_coverage.csv")
    flags = ram_flags((doc / "gauntlet_loader.r2").read_text())
    with (doc / "generated" / "ram_operands.csv").open(newline="") as stream:
        callable_rows = list(csv.DictReader(stream))
    callable_by_address = {
        int(row["literal_address"], 16): row for row in callable_rows
    }
    linear_uses: dict[int, set[int]] = {}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(
            lambda bounds: scan_one(root, doc / "gauntlet_loader.r2", bounds),
            ranges,
        )
        for start, end, ops, error in results:
            if error:
                failures.append(
                    {
                        "range_start": f"0x{start:05X}",
                        "range_end_inclusive": f"0x{end - 1:05X}",
                        "error": error,
                    }
                )
                continue
            for op in ops:
                opcode = str(op.get("opcode", ""))
                site = int(op["addr"])
                for literal_text in re.findall(r"0x(90[45][0-9a-fA-F]{3})", opcode):
                    literal = int(literal_text, 16)
                    if RAM_START <= literal <= RAM_END:
                        linear_uses.setdefault(literal, set()).add(site)

    rows: list[dict[str, str]] = []
    for literal in sorted(set(linear_uses) | set(callable_by_address)):
        linear_sites = sorted(linear_uses.get(literal, set()))
        callable = callable_by_address.get(literal)
        if linear_sites and callable:
            status = "exact_union_match"
            confidence = "Verified"
        elif linear_sites:
            status = "linear_only_candidate"
            confidence = "Unknown"
        else:
            status = "callable_only_candidate"
            confidence = "Unknown"
        covering = sorted(name for start, end, name in flags if start <= literal <= end)
        rows.append(
            {
                "literal_address": f"0x{literal:06X}",
                "linear_sites": ";".join(f"0x{site:05X}" for site in linear_sites[:12]),
                "callable_examples": callable["example_uses"] if callable else "",
                "covering_flags": ";".join(covering),
                "status": status,
                "confidence": confidence,
            }
        )
    return rows, failures


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
    rows, failures = generated_rows(here.parent.parent)
    report = here / "ram_linear_reconciliation.csv"
    failure_report = here / "ram_linear_scan_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_rows = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_rows != rows or old_failures != failures:
            raise SystemExit("linear RAM scan reports are stale; regenerate them")
    else:
        write_csv(
            report, rows,
            ["literal_address", "linear_sites", "callable_examples", "covering_flags", "status", "confidence"],
        )
        write_csv(
            failure_report, failures,
            ["range_start", "range_end_inclusive", "error"],
        )
    candidates = [row for row in rows if row["status"] != "exact_union_match"]
    print(
        f"linear RAM scan: {len(rows)} literals, {len(candidates)} reconciliation candidates, "
        f"{len(failures)} range failures"
    )
    if candidates or failures:
        raise SystemExit("linear RAM reconciliation is incomplete")


if __name__ == "__main__":
    main()
