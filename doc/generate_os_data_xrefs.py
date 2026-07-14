#!/usr/bin/env python3
"""Extract direct active-OS references into the active row9 data image."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


DATA_START = 0x599A
DATA_END = 0x6DA8


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def analyze(root: Path, address: int, name: str) -> dict[str, object]:
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", "doc/gauntlet_loader.r2",
        "-c", f"af- 0x{address:x}; af @ 0x{address:x}; s 0x{address:x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [line for line in completed.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))]
    if completed.returncode or errors:
        return {"address": address, "name": name, "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        return {"address": address, "name": name, "body": json.loads(completed.stdout)}
    except json.JSONDecodeError as exc:
        return {"address": address, "name": name, "error": f"invalid analysis JSON: {exc}"}


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    implementations = [
        row for row in read_csv(doc / "os_callable_contracts.csv")
        if row["entry_kind"] == "implementation"
    ]
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        analyses = list(executor.map(
            lambda row: analyze(root, int(row["address"], 16), row["name"]),
            implementations,
        ))

    observed: dict[int, dict[str, set[str]]] = {}
    for result in analyses:
        if "error" in result:
            failures.append({"address": f"0x{int(result['address']):04X}", "issue": str(result["error"])})
            continue
        body = result["body"]
        assert isinstance(body, dict)
        for op in body.get("ops", []):
            opcode = str(op.get("opcode", ""))
            site = int(op.get("addr", 0))
            for text in re.findall(r"0x([0-9A-Fa-f]+)", opcode):
                target = int(text, 16)
                if not DATA_START <= target < DATA_END:
                    continue
                item = observed.setdefault(target, {"sites": set(), "owners": set(), "opcodes": set()})
                item["sites"].add(f"0x{site:04X}")
                item["owners"].add(str(result["name"]))
                item["opcodes"].add(opcode)

    rows = [
        {
            "target": f"0x{target:04X}",
            "sites": ";".join(sorted(item["sites"])),
            "owners": ";".join(sorted(item["owners"])),
            "opcodes": ";".join(sorted(item["opcodes"])),
            "confidence": "Verified",
        }
        for target, item in sorted(observed.items())
    ]
    return rows, failures


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
    rows, failures = generated(here.parent)
    report = here / "os_data_xrefs.csv"
    failure_report = here / "os_data_xref_failures.csv"
    if args.check:
        if read_csv(report) != rows or read_csv(failure_report) != failures:
            raise SystemExit("OS data-xref reports are stale")
    else:
        write_csv(report, rows, ("target", "sites", "owners", "opcodes", "confidence"))
        write_csv(failure_report, failures, ("address", "issue"))
    print(f"OS active-data xrefs: {len(rows)} targets; {len(failures)} failures")
    if failures:
        raise SystemExit("OS high-data xref extraction failed")


if __name__ == "__main__":
    main()
