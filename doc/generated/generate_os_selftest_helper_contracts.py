#!/usr/bin/env python3
"""Generate and verify OS self-test, input, and diagnostic helper contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x0F7E, "copy_test_tile_rows_to_alpha", "Copy sixteen source words into each selected alpha-display row", "start column word; first row word; last row inclusive word; source word pointer", "void", "", "48e73000302f000e"),
    (0x113E, "read_debounced_input", "Sample and two-frame-debounce one self-test input word; when ram.os_vblank_active is zero it also republishes ram.input_source_ptr from the 0x40042 game hook or the 0x803000 constant at 0x5A46", "input/player index word", "D0.l = stable active-low press edges, with asserted raw high-nibble inputs included", "", "48e73838342f001e"),
    (0x169C, "load_color_test_palettes", "Load the three 256-word color-test palette banks and initialize the test palette", "void", "void", "", "2f02227c00910200"),
    (0x1704, "reset_sound_test_interface", "Synchronize to VBLANK, pulse the sound reset/control line, and clear OS sound-test state", "void", "void", "", "4eb9000021904279"),
    (0x1732, "fill_incrementing_words", "Fill a word buffer with an ascending sequence", "destination word pointer; first word; count long", "void", "", "48e73000206f000c"),
    (0x1758, "display_standard_large_glyph_range", "Draw an ascending glyph-index range with standard-display large-glyph strides", "alpha destination pointer; first glyph word; count word", "void", "", "48e73800282f0010"),
    (0x179E, "display_rotated_large_glyph_range", "Draw an ascending glyph-index range with rotated-display large-glyph strides", "alpha destination pointer; first glyph word; count long", "void", "", "48e73800282f0010"),
    (0x1A34, "run_switch_test", "Render and operate the live four-player switch/input diagnostic until the advance input is pressed", "void", "void", "", "48e73e004eb90000"),
    (0x2190, "wait_os_vblank", "Clear the OS VBLANK semaphore and wait until the IRQ4 handler sets it", "void", "void", "", "4279009040044a79"),
    (0x226A, "display_next_test_prompt", "Draw the orientation-appropriate 'Press [button] for next test' descriptor chain", "color/style word", "void", "", "302f00064a790090"),
    (0x27AC, "send_sound_test_command_wait", "Send one diagnostic sound command and wait up to thirty VBLANK ticks for its response", "sound command word", "D0.l = response byte, or -1 on timeout", "", "302f0006207c0090"),
    (0x27F4, "wait_sound_test_delay_or_abort", "Clear the sound command latch and wait up to four VBLANK ticks for the advance input", "void", "D0.l = 1 when advance was pressed, otherwise 0 after timeout", "", "42790080317033fc"),
    (0x28CA, "display_two_byte_hex_pair", "Pack two byte-valued arguments and display them as a four-digit zero-padded hexadecimal field", "high byte; low byte; signed display-offset byte", "void", "", "48e73000142f000f"),
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
        records.append({
            "address": f"0x{address:04X}", "name": name, "purpose": purpose,
            "arguments": arguments, "return": returns,
            "exceptional_convention": convention, "confidence": "Verified",
        })
    with ThreadPoolExecutor(max_workers=8) as executor:
        failures.extend(
            failure
            for failure in executor.map(
                lambda row: analyze(root, root / "doc" / "gauntlet_loader.r2", row), ROWS
            )
            if failure
        )
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
    report = here / "os_selftest_helper_contracts.csv"
    failure_report = here / "os_selftest_helper_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS self-test helper contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS self-test helper contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS self-test helper contract verification failed")


if __name__ == "__main__":
    main()
