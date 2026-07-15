#!/usr/bin/env python3
"""Extract game-function RAM literals and reconcile them with named flags."""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


RAM_START = 0x904000
RAM_END = 0x905FFF


def function_rows(text: str) -> list[tuple[int, str]]:
    pattern = re.compile(r"^\| 0x([0-9A-Fa-f]+) \| `([^`]+)`", re.MULTILINE)
    by_address: dict[int, str] = {}
    for address_text, name in pattern.findall(text):
        address = int(address_text, 16)
        if 0x40000 <= address <= 0x5FFFF:
            by_address.setdefault(address, name)
    return sorted(by_address.items())


def ram_flags(text: str) -> list[tuple[int, int, str]]:
    result = []
    for name, size_text, address_text in re.findall(
        r"^f ([^ ]+) (\d+) (0x[0-9a-fA-F]+)$", text, re.MULTILINE
    ):
        address = int(address_text, 16)
        size = int(size_text)
        if RAM_START <= address <= RAM_END:
            result.append((address, address + max(size, 1) - 1, name))
    return result


def analyze_one(root: Path, loader: Path, item: tuple[int, str]) -> tuple[int, str, str, str]:
    address, name = item
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false",
        "-i", str(loader),
        "-c", f"af- 0x{address:x}; af @ 0x{address:x}; s 0x{address:x}; pdf~0x90",
        "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = "\n".join(
        line for line in result.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))
    )
    return address, name, result.stdout, errors


def generated_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    functions = function_rows((doc / "07_function_index.md").read_text())
    flags = ram_flags((doc / "gauntlet_loader.r2").read_text())
    uses: dict[int, list[str]] = {}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(
            lambda item: analyze_one(root, doc / "gauntlet_loader.r2", item), functions
        )
        for function_address, name, output, errors in results:
            if errors:
                failures.append(
                    {
                        "function_address": f"0x{function_address:05X}",
                        "name": name,
                        "error": errors.replace("\n", "; "),
                    }
                )
                continue
            for line in output.splitlines():
                site_match = re.search(r"0x([0-9a-fA-F]{8})", line)
                if not site_match:
                    continue
                site = int(site_match.group(1), 16)
                for literal_text in re.findall(r"0x(90[45][0-9a-fA-F]{3})", line):
                    literal = int(literal_text, 16)
                    if RAM_START <= literal <= RAM_END:
                        uses.setdefault(literal, []).append(f"{name}@0x{site:05X}")

    rows = []
    for literal, examples in sorted(uses.items()):
        covering = sorted(name for start, end, name in flags if start <= literal <= end)
        rows.append(
            {
                "literal_address": f"0x{literal:06X}",
                "covering_flags": ";".join(covering),
                "example_uses": ";".join(sorted(set(examples))[:6]),
                "confidence": "Verified" if covering else "Unknown",
            }
        )
    return rows, failures


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rows, failures = generated_rows(here.parent.parent)
    report = here / "ram_operands.csv"
    failure_report = here / "ram_operand_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            existing_failures = list(csv.DictReader(stream))
        if existing != rows or existing_failures != failures:
            raise SystemExit("RAM operand reports are stale; regenerate them")
    else:
        write_csv(
            report, rows,
            ["literal_address", "covering_flags", "example_uses", "confidence"],
        )
        write_csv(
            failure_report, failures,
            ["function_address", "name", "error"],
        )
    uncovered = [row for row in rows if not row["covering_flags"]]
    print(
        f"ram_operands.csv: {len(rows)} literals, {len(uncovered)} uncovered, "
        f"{len(failures)} function-analysis failures"
    )


if __name__ == "__main__":
    main()
