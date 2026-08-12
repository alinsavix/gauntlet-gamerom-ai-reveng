#!/usr/bin/env python3
"""Generate and verify OS numeric-format and direct-display contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, convention, byte prefix
ROWS = (
    (0x2918, "format_number", "Format a value as decimal ('d' unsigned, 's' signed), hexadecimal ('X' uppercase, 'x' and 'h' lowercase), octal ('o'), or binary for any other format byte; the mode selects zero/space padding and the comma-separator post-pass indexed by field width", "value; destination buffer; format byte; format mode word; field width word", "void", "normal stack ABI", "206f0008"),
    (0x2A5E, "format_hex", "Format an unsigned value as uppercase hexadecimal into a fixed-width NUL-terminated field", "value; destination buffer; field width word; nonzero=space pad, zero=zero pad", "void", "normal stack ABI", "222f0004"),
    (0x2ABE, "format_decimal", "Format an unsigned value as decimal into a fixed-width NUL-terminated field", "value; destination buffer; field width word; nonzero=space pad, zero=zero pad", "void", "normal stack ABI", "2f02"),
    (0x2CE4, "calc_alpha_address", "Convert two alpha coordinates to the orientation-correct absolute VRAM word address", "column byte; row byte", "D0.l=absolute alpha VRAM address", "normal stack ABI", "4a7900904f0e"),
    (0x2EB4, "display_decimal_value", "Format and draw a decimal value through a temporary chained-text descriptor", "column byte; row byte; value; field width; nonzero=space pad, zero=zero pad; color/style", "void", "normal six-slot stack ABI", "4e56fff0"),
    (0x2EEA, "display_hex_value", "Format and draw an uppercase hexadecimal value through a temporary chained-text descriptor", "column byte; row byte; value; field width; nonzero=space pad, zero=zero pad; color/style", "void", "normal six-slot stack ABI", "4e56fff0"),
    (0x30F4, "stop_text_effect", "Deactivate a matching effect slot if present and clear the supplied descriptor chain", "descriptor pointer", "void", "normal stack ABI", "2f0a"),
    (0x32A0, "display_large_char_raw", "Render one mapped large glyph with the rotated-display stride/attribute mode", "alpha destination pointer; glyph index word; color/style word", "D0.w=alpha-cell advance (1 or 2)", "tail-enters register renderer", "226f0004"),
    (0x32BC, "display_large_char_at", "Render one mapped large glyph with the standard-display stride/attribute mode", "alpha destination pointer; glyph index word; color/style word", "D0.w=alpha-cell advance (1 or 2)", "tail-enters register renderer", "226f0004"),
    (0x32DA, "display_large_decimal_value", "Format and draw a decimal value with the mapped large font", "column byte; row byte; value; field width; nonzero=space pad, zero=zero pad; color/style", "D0.l=total alpha-cell advance", "normal six-slot stack ABI", "4e56fff0"),
    (0x3310, "display_large_hex_value", "Format and draw an uppercase hexadecimal value with the mapped large font", "column byte; row byte; value; field width; nonzero=space pad, zero=zero pad; color/style", "D0.l=total alpha-cell advance", "normal six-slot veneer sharing the 0x32F2 display tail", "4e56fff0"),
    (0x332A, "display_large_text_at", "Build a temporary descriptor from coordinates and draw a mapped large-font string", "column byte; row byte; string pointer; color/style", "D0.l=total alpha-cell advance", "normal four-slot stack ABI", "1f6f0007000a"),
    (0x3346, "clear_large_text", "Clear the alpha cells occupied by a mapped large-font descriptor chain", "descriptor pointer", "D0.l=alpha-cell span cleared for the final descriptor", "normal stack ABI", "48e72038"),
    (0x3586, "write_alpha_word", "Write a raw word to one indexed alpha VRAM cell", "cell index long; value word", "void", "normal stack ABI", "41f900905000"),
    (0x359A, "wait_vblanks", "Busy-wait for the requested number of changes to the OS VBLANK counter", "count word", "void", "normal stack ABI", "302f0006"),
    (0x35B2, "set_text_position", "Set the two leading descriptor coordinates and clear descriptor repeat byte 6", "descriptor pointer; column byte; row byte", "void", "normal stack ABI", "206f0004"),
)


def analyze(root: Path, loader: Path, row: tuple[object, ...]) -> dict[str, str]:
    address, name, *_ = row
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader),
        "-c", f"af- 0x{int(address):x}; af @ 0x{int(address):x}; s 0x{int(address):x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [line for line in completed.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))]
    if completed.returncode or errors:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        body = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": f"invalid pdfj: {exc}"}
    if int(body.get("addr", -1)) != int(address) or int(body.get("size", 0)) <= 0 or any(str(op.get("type", "")) == "ill" for op in body.get("ops", [])):
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "empty, invalid, or misbased analysis body"}
    return {}


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rom = (root / "row9.bin").read_bytes()
    records: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for address, name, purpose, arguments, returns, convention, prefix in ROWS:
        actual = rom[address : address + len(prefix) // 2].hex()
        if actual != prefix:
            failures.append({"address": f"0x{address:04X}", "name": name, "error": f"byte prefix {actual} != {prefix}"})
        records.append({"address": f"0x{address:04X}", "name": name, "purpose": purpose, "arguments": arguments, "return": returns, "exceptional_convention": convention, "confidence": "Verified"})
    with ThreadPoolExecutor(max_workers=8) as executor:
        failures.extend(failure for failure in executor.map(lambda row: analyze(root, root / "doc" / "gauntlet_loader.r2", row), ROWS) if failure)
    return records, failures


def write_csv(path: Path, records: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    records, failures = generated(here.parent.parent)
    report = here / "os_numeric_display_contracts.csv"
    failure_report = here / "os_numeric_display_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS numeric/display contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS numeric/display contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS numeric/display contract verification failed")


if __name__ == "__main__":
    main()
