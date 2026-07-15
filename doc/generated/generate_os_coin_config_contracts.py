#!/usr/bin/env python3
"""Generate and verify OS coin, configuration, high-score, and statistics contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# address, name, purpose, arguments, return, exceptional convention, byte prefix
ROWS = (
    (0x35C4, "process_coins", "Decode two packed four-channel coin-counter samples, apply the configured multiplier/bonus, and update per-player coin totals and pending credits", "previous packed 2-bit counter sample; current packed 2-bit counter sample", "void", "normal two-slot stack ABI; only each slot's low byte is consumed", "4e56fffe48e73f38"),
    (0x3706, "get_coin_multiplier", "Validate the complementary coin-configuration bytes and derive the current coin multiplier", "void", "D0.l = multiplier 1-4, or 0 for free play/invalid high setting", "normal stack ABI", "2f02223900904ffc"),
    (0x3740, "calc_health_per_coin", "Fold pending credit units into one player's bounded coin accumulator and convert it to health units", "player index long", "D0.l = 12 * accumulated coin units / multiplier, or 24 in free play", "normal stack ABI; mutates the selected pending and accumulated coin bytes", "2f02242f00084eb9"),
    (0x37C2, "check_and_deduct_coin", "Check whether one player has at least twelve health units of credit and deduct one multiplier group", "player index long", "D0.l = 1 on success/free play, 0 when insufficient", "normal stack ABI", "48e73020242f0010"),
    (0x3804, "check_and_deduct_credits", "Check a player's pending-plus-accumulated credit units and consume the requested amount", "required credit units long; player index long", "D0.l = 1 on success/free play, 0 when insufficient", "normal stack ABI; consumes pending units before accumulated units", "48e73000242f000c"),
    (0x3860, "read_eeprom_setting", "Read one difficulty-row histogram byte when that row is available", "difficulty threshold/row long; bin index long", "D0.l = byte value, -1 when bin index exceeds 19, or -2 when current difficulty is not above the requested row", "normal stack ABI", "48e73e00242f0018"),
    (0x38C0, "read_game_config", "Decode one packed game-configuration item through the descriptor table", "configuration index long", "D0.l = decoded value; index 13 returns the signed game difficulty byte; indexes above 13 return -1", "normal stack ABI", "48e73e20242f001c"),
    (0x39B0, "read_high_score_entry", "Expand one five-byte EEPROM high-score record into the shared score/ASCII work buffer", "character class word; rank word", "D0.l = pointer to seven-byte expanded entry, or 0 when rank exceeds 9", "normal stack ABI; character class is expected to be 0-3 and is not bounds-checked", "48e73830362f001a"),
    (0x3A7E, "write_high_score_entry", "Encode and insert one expanded score/initials record into a class table and queue affected EEPROM regions", "character class word; rank word; expanded-entry pointer", "D0.l = 0 success, -1 when rank exceeds 9, or -2 when score exceeds 24 bits", "normal stack ABI; character class is expected to be 0-3 and is not bounds-checked", "4e56fffa48e73f3c"),
    (0x3BE8, "update_active_player_time_stats", "Accumulate elapsed VBLANKs for active players, periodically fold hours into configuration counters, and update the active mask", "active-player bit mask long", "D0.l = pointer to the first per-player elapsed-VBLANK counter at 0x904F50", "normal stack ABI; queues EEPROM regions when hour counters change", "48e73838242f001c"),
    (0x3CF6, "write_eeprom_setting", "Apply the public setting-write policy and delegate packed configuration storage", "configuration index long; value long", "D0.l = -1 for index above 13; otherwise the delegated writer's observable result", "normal stack ABI; indexes below 11 are forcibly written as zero", "2f02242f0008222f"),
    (0x3D18, "write_game_config", "Pack one configuration value according to the descriptor table and queue affected EEPROM regions", "configuration index long; value long", "D0.l = -1 for index above 13; a changed ordinary value returns queued region 0 or 1; unchanged-value paths leave an incidental work value", "normal stack ABI; index 13 clears difficulty rows and queues their regions", "4e56fff848e73f38"),
    (0x3F68, "rank_high_score", "Compare a 24-bit score against one class's ten EEPROM records", "character class word; score long", "D0.l = rank 0-9, 10 when score does not rank, or -1 when score exceeds 24 bits", "normal stack ABI; character class is expected to be 0-3 and is not bounds-checked", "4e56fffc48e73c00"),
    (0x401A, "activate_player_time_tracking", "Add one player to the active-time mask and immediately account elapsed VBLANKs", "player index long", "D0.l = pointer to the first per-player elapsed-VBLANK counter at 0x904F50", "normal stack ABI; tail result is propagated from 0x3BE8", "222f00047001e3a0"),
    (0x4038, "record_player_session_histogram", "Remove a player from active-time tracking, normalize the elapsed session by coin count/difficulty, and increment the corresponding EEPROM histogram bin", "player index word in a long slot; coin-count/divisor word in a long slot", "void", "normal two-slot stack ABI; divisor is capped at 128 and is expected nonzero", "48e73e00342f001a"),
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
    records, failures = generated(here.parent.parent)
    report = here / "os_coin_config_contracts.csv"
    failure_report = here / "os_coin_config_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS coin/config contract reports are stale")
    else:
        write_csv(report, records, ["address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS coin/config contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS coin/config contract verification failed")


if __name__ == "__main__":
    main()
