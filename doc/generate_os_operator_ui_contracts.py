#!/usr/bin/env python3
"""Generate and verify OS statistics and operator-options UI contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x4896, "wait_vblank_counter_ticks", "Wait for a requested number of changes to the EEPROM/VBLANK long counter", "tick count word in a long slot", "void", "normal stack ABI", "2f02302f000a6012"),
    (0x48B8, "display_text_set_cursor", "Draw one string at explicit coordinates and update the operator-UI cursor to its end", "coordinate0 low byte; coordinate1 low byte; string pointer", "void", "normal three-slot stack ABI", "4e56fff82f02122e"),
    (0x4912, "display_text_at_cursor", "Draw one string at the saved operator-UI cursor and advance that cursor", "string pointer", "void", "normal stack veneer over 0x48B8", "202f00042f001039"),
    (0x493C, "display_decimal_at_cursor", "Draw one trimmed eight-digit decimal value at the saved operator-UI cursor", "value long", "void", "normal stack veneer over 0x4966", "202f00042f001039"),
    (0x4966, "display_decimal_set_cursor", "Format an eight-digit zero-padded decimal, trim leading zeroes while retaining one digit, draw it at explicit coordinates, and update the cursor", "coordinate0 low byte; coordinate1 low byte; value long", "void", "normal three-slot stack ABI", "4e56fff648e73000"),
    (0x49C8, "option_record_present", "Test whether the first two bytes of an option descriptor record are both zero", "record pointer", "D0.l = bitwise OR of record bytes 0 and 1 (zero means terminator)", "normal stack ABI", "2f02206f00087200"),
    (0x49E8, "find_option_record", "Advance through a variable-length option-descriptor stream to one record index", "descriptor-stream pointer; record index word", "D0.l = selected record pointer, or 0 at/past the terminator", "normal two-slot stack ABI", "48e73020246f0010"),
    (0x4A44, "render_option_record", "Render one option descriptor's label and selected value, optionally clearing its prior effect", "record pointer; current settings word; comparison/default word; display row word; style/clear flags word", "D0.l = pointer to the following record, or 0 for a terminator", "normal five-slot stack ABI", "4e56fff448e73c20"),
    (0x4B66, "render_option_record_page", "Find a starting option record and render one orientation-sized page of records", "stream pointer; current settings word; comparison/default word; first record index word; style/clear flags word", "void", "normal five-slot stack ABI", "48e73e00242f0018"),
    (0x4BE6, "display_next_screen_prompt", "Draw the game-specific action label inside the OS 'Press ... for next screen' prompt", "void", "void", "normal stack ABI", "2f024a3900040072"),
    (0x4C38, "init_operator_mob_display", "Install the eight-word operator-screen MOB template and clear its trailing link word", "void", "void", "normal stack ABI", "48e72020227c0091"),
    (0x4C66, "run_statistics_histograms", "Display and navigate per-player difficulty histograms, with optional clearing", "nonzero allows clear operation", "void", "normal stack ABI", "4e56fffe48e73f38"),
    (0x4FA0, "display_statistics_play_time", "Sum stored play-time groups, scale large totals safely, and display total time plus active-time percentage", "display row word in a long slot", "void", "normal stack ABI", "48e73e00342f001a"),
    (0x5098, "run_statistics_summary", "Display stored configuration/statistics counters and optionally clear the resettable counters", "nonzero allows clear operation", "void", "normal stack ABI", "48e73c20242f0018"),
    (0x522A, "run_game_settings_bit_editor", "Interactively edit the sixteen raw game-settings bits and store configuration item 12", "void", "void", "normal stack ABI", "48e73800740f4878"),
    (0x5392, "draw_game_settings_bits", "Draw all sixteen game-settings bits and highlight one selected bit", "settings word in a long slot; selected bit index word in a long slot", "void", "normal two-slot stack ABI", "48e73f38362f002a"),
    (0x5454, "run_statistics_screens", "Initialize operator-screen MOBs, run the statistics summary, then run the histogram viewer", "nonzero allows clear operations", "void", "normal stack ABI", "2f02242f00084eb9"),
    (0x5476, "run_option_descriptor_editor", "Render and interactively edit a variable-length option-descriptor stream", "descriptor-stream pointer; current settings word; comparison/default settings word", "D0.l = edited settings word", "normal three-slot stack ABI", "4e56ffde48e73f3c"),
    (0x58C6, "run_game_options", "Initialize the operator display and edit configuration item 12 through a descriptor stream or the raw-bit fallback", "descriptor-stream pointer, or null for raw-bit editor", "D0.l = observable delegated setting-writer result, not the edited word", "normal stack ABI", "2f02242f00084eb9"),
    (0x593C, "run_coin_options", "Initialize the operator display, edit configuration item 11 through the built-in coin-options stream, and store it", "void", "D0.l = observable delegated setting-writer result, not the edited word", "normal stack ABI", "4eb9000035224eb9"),
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
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": f"invalid analysis JSON: {exc}"}
    ops = body.get("ops", [])
    if int(body.get("addr", -1)) != int(address) or int(body.get("size", 0)) <= 0 or any(str(op.get("type", "")) == "ill" for op in ops):
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
    records, failures = generated(here.parent)
    report = here / "os_operator_ui_contracts.csv"
    failure_report = here / "os_operator_ui_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS operator-UI contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS operator-UI contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS operator-UI contract verification failed")


if __name__ == "__main__":
    main()
