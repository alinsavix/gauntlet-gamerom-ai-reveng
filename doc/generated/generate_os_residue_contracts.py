#!/usr/bin/env python3
"""Check the five unreferenced callable entries found by OS byte coverage."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


CONTRACTS = (
    (0x0EEE, 0x0F04, "selftest_watchdog_reset_trap", "D0.w watchdog service value", "no return", "non-returning trap; supervisor SR write", "Masks interrupts, services the watchdog until the self-test switch is released, then spins without servicing it so hardware resets", "46fc2700", "move.w d0, 0x803100"),
    (0x2FB2, 0x2FBE, "draw_text_effect_next_char_stack_veneer", "descriptor pointer; color/style word; character index word", "same as 0x2FBE", "normal stack veneer; falls through to register worker", "Loads the stack arguments into A0/D1/D0 and falls through to draw_text_effect_next_char", "322f000a206f0004302f000e", "movea.l 0x4(a7), a0"),
    (0x3018, 0x3020, "clear_text_effect_next_char_stack_veneer", "descriptor pointer; character index word", "same as 0x3020", "normal stack veneer; falls through to register worker", "Loads the stack arguments into A0/D0 and falls through to clear_text_effect_next_char", "206f0004302f000a", "movea.l 0x4(a7), a0"),
    (0x3088, 0x308C, "clear_text_descriptor_chain_stack_veneer", "descriptor pointer", "void", "normal stack veneer; falls through to register worker", "Loads A0 from the normal argument slot and falls through to clear_text_descriptor_chain", "206f0004", "movea.l 0x4(a7), a0"),
    (0x3166, 0x3168, "unused_text_effect_noop", "void", "void; registers preserved", "one-instruction RTS entry", "Returns immediately; no encoded caller or API veneer reaches this entry", "4e75", "rts"),
)


def analyze(root: Path, start: int, name: str) -> dict[str, object]:
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", "doc/gauntlet_loader.r2",
        "-c", f"af- 0x{start:x}; af @ 0x{start:x}; s 0x{start:x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [line for line in completed.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))]
    if completed.returncode or errors:
        return {"start": start, "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        return {"start": start, "body": json.loads(completed.stdout)}
    except json.JSONDecodeError as exc:
        return {"start": start, "error": f"invalid JSON: {exc}"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rom = (root / "row9.bin").read_bytes()
    failures: list[dict[str, str]] = []
    rows: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        analyses = list(executor.map(lambda row: analyze(root, int(row[0]), str(row[2])), CONTRACTS))
    for contract, analysis in zip(CONTRACTS, analyses):
        start, end, name, arguments, returns, convention, purpose, prefix, required = contract
        if rom[start : start + len(prefix) // 2].hex() != prefix:
            failures.append({"address": f"0x{start:04X}", "issue": "byte prefix mismatch"})
        if "error" in analysis:
            failures.append({"address": f"0x{start:04X}", "issue": str(analysis["error"])})
        else:
            body = analysis["body"]
            assert isinstance(body, dict)
            relevant = [op for op in body.get("ops", []) if start <= int(op.get("addr", -1)) < end]
            opcodes = [str(op.get("opcode", "")) for op in relevant]
            byte_union = {
                address
                for op in relevant
                for address in range(int(op["addr"]), int(op["addr"]) + int(op.get("size", 0)))
            }
            if byte_union != set(range(start, end)):
                failures.append({"address": f"0x{start:04X}", "issue": "entry prefix is not completely decoded"})
            if any(op.startswith("invalid") for op in opcodes):
                failures.append({"address": f"0x{start:04X}", "issue": "invalid instruction in entry"})
            if not any(required in op for op in opcodes):
                failures.append({"address": f"0x{start:04X}", "issue": f"required instruction absent: {required}"})
        rows.append({
            "address": f"0x{start:04X}", "end_exclusive": f"0x{end:04X}",
            "size_bytes": str(end - start), "name": name, "purpose": purpose,
            "arguments": arguments, "return": returns,
            "exceptional_convention": convention,
            "reachability": "No incoming transfer or fixed API veneer in the supplied image",
            "confidence": "Verified",
        })
    return rows, failures


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rows, failures = generated(here.parent.parent)
    report = here / "os_residue_contracts.csv"; failure_report = here / "os_residue_contract_failures.csv"
    fields = ("address", "end_exclusive", "size_bytes", "name", "purpose", "arguments", "return", "exceptional_convention", "reachability", "confidence")
    if args.check:
        if read_csv(report) != rows or read_csv(failure_report) != failures:
            raise SystemExit("OS residue reports are stale")
    else:
        write_csv(report, rows, fields); write_csv(failure_report, failures, ("address", "issue"))
    print(f"OS residue: {len(rows)} contracts; {len(failures)} failures")
    if failures:
        raise SystemExit("OS residue contract verification failed")


if __name__ == "__main__":
    main()
