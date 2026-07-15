#!/usr/bin/env python3
"""Reconcile absolute RAM, video-memory, and hardware operands in OS callables."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from generate_r2_loader import ADDITIONAL_OS_FLAGS


RANGES = (
    (0x800000, 0x804000, "hardware"),
    (0x900000, 0x911000, "video_or_work_ram"),
)

# This packed renderer stride happens to fall inside the hardware aperture.
# The instruction loads it as data into A0; it is not dereferenced as an
# address.  Keep it in a separate checked report rather than silently dropping
# it from the RAM/hardware reconciliation.
NON_ADDRESS_LITERALS = {
    0x00800002: "packed large-text strides: 0x0080-byte row and 0x0002-byte cell",
}


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


def loader_flags(text: str) -> list[tuple[int, int, str]]:
    flags: list[tuple[int, int, str]] = []
    for name, size_text, address_text in re.findall(r"^f (\S+) (\S+) (0x[0-9A-Fa-f]+)$", text, re.MULTILINE):
        try:
            size = int(size_text, 0)
        except ValueError:
            continue
        address = int(address_text, 16)
        if any(start <= address < end for start, end, _ in RANGES):
            flags.append((address, max(size, 1), name))
    return flags


def flag_names(flags: list[tuple[int, int, str]], address: int) -> str:
    matches = [(size, name, base) for base, size, name in flags if base <= address < base + size]
    if not matches:
        return ""
    smallest = min(size for size, _, _ in matches)
    return ";".join(sorted({name if base == address else f"{name}+0x{address-base:X}" for size, name, base in matches if size == smallest}))


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    implementations = [row for row in read_csv(doc / "generated" / "os_callable_contracts.csv") if row["entry_kind"] == "implementation"]
    flags = loader_flags((doc / "gauntlet_loader.r2").read_text())
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        analyses = list(executor.map(lambda row: analyze(root, int(row["address"], 16), row["name"]), implementations))

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
                address = int(text, 16)
                region = next((label for start, end, label in RANGES if start <= address < end), "")
                if not region:
                    continue
                item = observed.setdefault(address, {"sites": set(), "owners": set(), "opcodes": set(), "regions": set()})
                item["sites"].add(f"0x{site:04X}")
                item["owners"].add(str(result["name"]))
                item["opcodes"].add(opcode)
                item["regions"].add(region)

    rows: list[dict[str, str]] = []
    non_address_rows: list[dict[str, str]] = []
    for address, item in sorted(observed.items()):
        if address in NON_ADDRESS_LITERALS:
            non_address_rows.append({
                "value": f"0x{address:08X}",
                "meaning": NON_ADDRESS_LITERALS[address],
                "sites": ";".join(sorted(item["sites"])),
                "owners": ";".join(sorted(item["owners"])),
                "opcodes": ";".join(sorted(item["opcodes"])),
                "confidence": "Verified",
            })
            continue
        names = flag_names(flags, address)
        required = ADDITIONAL_OS_FLAGS.get(address)
        if required:
            required_name, required_size = required
            exact = [(size, name) for base, size, name in flags if base == address and name == required_name]
            if not exact or max(size for size, _ in exact) < required_size:
                failures.append({
                    "address": f"0x{address:08X}",
                    "issue": f"missing exact OS flag {required_name} size {required_size}",
                })
            else:
                names = required_name
        if not names:
            failures.append({"address": f"0x{address:08X}", "issue": "RAM/hardware literal has no containing loader flag"})
        rows.append({
            "address": f"0x{address:08X}",
            "name": names,
            "region": ";".join(sorted(item["regions"])),
            "sites": ";".join(sorted(item["sites"])),
            "owners": ";".join(sorted(item["owners"])),
            "opcodes": ";".join(sorted(item["opcodes"])),
            "confidence": "Verified" if names else "Unknown",
        })
    missing_constants = sorted(set(NON_ADDRESS_LITERALS) - {int(row["value"], 16) for row in non_address_rows})
    failures.extend(
        {"address": f"0x{address:08X}", "issue": "expected non-address literal was not observed"}
        for address in missing_constants
    )
    return rows, non_address_rows, failures


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rows, non_address_rows, failures = generated(here.parent.parent)
    report = here / "os_ram_operands.csv"
    constant_report = here / "os_non_address_literals.csv"
    failure_report = here / "os_ram_operand_failures.csv"
    if args.check:
        if (
            read_csv(report) != rows
            or read_csv(constant_report) != non_address_rows
            or read_csv(failure_report) != failures
        ):
            raise SystemExit("OS RAM-operand reports are stale")
    else:
        write_csv(report, rows, ["address", "name", "region", "sites", "owners", "opcodes", "confidence"])
        write_csv(
            constant_report,
            non_address_rows,
            ["value", "meaning", "sites", "owners", "opcodes", "confidence"],
        )
        write_csv(failure_report, failures, ["address", "issue"])
    print(
        f"OS RAM/hardware operands: {len(rows)} addresses; "
        f"{len(non_address_rows)} checked non-address literals; {len(failures)} failures"
    )
    if failures:
        raise SystemExit("OS RAM-operand reconciliation failed")


if __name__ == "__main__":
    main()
