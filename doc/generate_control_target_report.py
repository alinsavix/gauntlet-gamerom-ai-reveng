#!/usr/bin/env python3
"""Reconcile direct control-transfer targets from documented game code bodies."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


GAME_START = 0x40000
GAME_END = 0x5FFFF

COMPUTED_TABLES = {
    0x45C42: "door_open_direction_jumptbl@0x45C46",
    0x4961C: "monster_playerhit_jumptbl@0x495FC",
    0x4B334: "resolve_shot_hit_jumptbl@0x4B338",
    0x4FE04: "richest_player_tie_jumptbl@0x4FE08",
    0x511FC: "player_tile_lowtype_jumptbl@0x51200",
    0x51226: "player_tile_object_jumptbl@0x5122A",
    0x5220C: "mob_collision_object_jumptbl@0x52210",
    0x538FA: "shot_reflect_center_jumptbl@0x538FE",
    0x53920: "shot_reflect_neg42_jumptbl@0x53924",
    0x53944: "shot_reflect_neg22_jumptbl@0x53948",
    0x53966: "shot_reflect_pos1e_jumptbl@0x5396A",
    0x5398E: "shot_reflect_pos3e_jumptbl@0x53992",
}

# (table address, entry count, displacement base, label). These are the actual
# accessed word ranges, including the backward-biased monster-playerhit case.
DISPATCH_TABLES = (
    (0x45C46, 4, 0x45C46, "door_open_direction_jumptbl"),
    (0x49620, 10, 0x49620, "monster_playerhit_jumptbl"),
    (0x4B338, 62, 0x4B338, "resolve_shot_hit_jumptbl"),
    (0x4FE08, 8, 0x4FE08, "richest_player_tie_jumptbl"),
    (0x51200, 8, 0x51200, "player_tile_lowtype_jumptbl"),
    (0x5122A, 17, 0x5122A, "player_tile_object_jumptbl"),
    (0x52210, 47, 0x52210, "mob_collision_object_jumptbl"),
    (0x538FE, 5, 0x538FE, "shot_reflect_center_jumptbl"),
    (0x53924, 5, 0x53924, "shot_reflect_neg42_jumptbl"),
    (0x53948, 5, 0x53948, "shot_reflect_neg22_jumptbl"),
    (0x5396A, 5, 0x5396A, "shot_reflect_pos1e_jumptbl"),
    (0x53992, 5, 0x53992, "shot_reflect_pos3e_jumptbl"),
)


def function_rows(text: str) -> list[tuple[int, str]]:
    pattern = re.compile(r"^\| 0x([0-9A-Fa-f]+) \| `([^`]+)`", re.MULTILINE)
    by_address: dict[int, str] = {}
    for address_text, name in pattern.findall(text):
        address = int(address_text, 16)
        if GAME_START <= address <= GAME_END:
            by_address.setdefault(address, name)
    return sorted(by_address.items())


def loader_symbols(text: str) -> dict[int, list[str]]:
    symbols: dict[int, set[str]] = {}
    for address_text, name in re.findall(
        r"^af\+ (0x[0-9A-Fa-f]+) ([^\s]+)", text, re.MULTILINE
    ):
        symbols.setdefault(int(address_text, 16), set()).add(name)
    for name, address_text in re.findall(
        r"^f ([^\s]+) \d+ (0x[0-9A-Fa-f]+)$", text, re.MULTILINE
    ):
        symbols.setdefault(int(address_text, 16), set()).add(name)
    return {address: sorted(names) for address, names in symbols.items()}


def os_api_symbols(text: str) -> dict[int, str]:
    return {
        int(address_text, 16): name
        for address_text, name in re.findall(
            r"^\| `0x([0-9A-Fa-f]+)` \| `0x[0-9A-Fa-f]+` \| `([^`]+)` \|",
            text,
            re.MULTILINE,
        )
    }


def dispatch_entries(rom: bytes) -> list[tuple[int, str]]:
    by_target: dict[int, list[str]] = {}
    for table, count, base, label in DISPATCH_TABLES:
        offset = table - GAME_START
        for index in range(count):
            displacement = int.from_bytes(
                rom[offset + index * 2 : offset + index * 2 + 2],
                "big",
                signed=True,
            )
            target = base + displacement
            if not (GAME_START <= target <= GAME_END) or target & 1:
                raise ValueError(
                    f"invalid {label}[{index}] destination 0x{target:X}"
                )
            by_target.setdefault(target, []).append(f"{label}[{index}]")
    return [
        (target, "dispatch:" + "/".join(labels))
        for target, labels in sorted(by_target.items())
    ]


def analyze_one(root: Path, loader: Path, item: tuple[int, str]) -> dict[str, object]:
    address, name = item
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-i", str(loader),
        "-c", f"af- 0x{address:x}; af @ 0x{address:x}; s 0x{address:x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [
        line for line in result.stderr.splitlines()
        if line.startswith(("ERROR", "FATAL"))
    ]
    if result.returncode or errors:
        return {
            "address": address,
            "name": name,
            "error": "; ".join(errors) or f"r2 exit {result.returncode}",
        }
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"address": address, "name": name, "error": f"invalid pdfj: {exc}"}
    return {"address": address, "name": name, "body": body}


def classify_direct(
    kind: str,
    target: int,
    documented: dict[int, str],
    symbols: dict[int, list[str]],
    source_start: int,
    source_end: int,
    os_api: dict[int, str],
) -> tuple[str, str, str]:
    names = symbols.get(target, [])
    target_name = documented.get(target) or (names[0] if names else "")
    if kind == "call" and target == 0:
        return target_name, "null_assertion", "Verified"
    if kind == "jump" and target == 0x10000:
        return "decoded_unpopulated_rom_abort_target", "watchdog_abort_jump", "Strong inference"
    if GAME_START <= target <= GAME_END:
        if target in documented:
            return target_name, "documented_game_entry", "Verified"
        if kind == "jump" and source_start <= target < source_end:
            return target_name, "intra_body_jump", "Verified"
        return target_name, f"unresolved_game_{kind}_target", "Unknown"
    if 0 <= target < 0x10000:
        if target in os_api:
            return os_api[target], "documented_os_api", "Verified"
        if names:
            return target_name, "documented_os_implementation", "Verified"
        return target_name, "unresolved_os_target", "Unknown"
    if 0x905F00 <= target <= 0x905F17 and (target - 0x905F00) % 6 == 0:
        return "player_hurt_palette_stub", "named_runtime_stub", "Verified"
    if 0x905F18 <= target <= 0x905F2F and (target - 0x905F18) % 6 == 0:
        return "player_power_palette_stub", "named_runtime_stub", "Verified"
    return target_name, "unresolved_external_target", "Unknown"


def generated_rows(
    root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], int, int]:
    doc = root / "doc"
    entries = function_rows((doc / "07_function_index.md").read_text())
    rom = (root / "row76.bin").read_bytes()
    dispatch = dispatch_entries(rom)
    documented = dict(entries)
    symbols = loader_symbols((doc / "gauntlet_loader.r2").read_text())
    os_api = os_api_symbols((doc / "02_os_rom.md").read_text())
    failures: list[dict[str, str]] = []
    observations: dict[tuple[int, str, int | None], dict[str, object]] = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(
            lambda item: analyze_one(root, doc / "gauntlet_loader.r2", item),
            entries + dispatch,
        )
        for result in results:
            address = int(result["address"])
            name = str(result["name"])
            if "error" in result:
                failures.append(
                    {
                        "function_address": f"0x{address:05X}",
                        "name": name,
                        "error": str(result["error"]),
                    }
                )
                continue
            body = result["body"]
            assert isinstance(body, dict)
            source_start = int(body.get("addr", address))
            source_end = source_start + int(body.get("size", 0))
            for op in body.get("ops", []):
                opcode = str(op.get("opcode", ""))
                op_type = str(op.get("type", ""))
                if op_type == "call":
                    kind = "call"
                elif opcode.startswith("jmp "):
                    kind = "jump"
                else:
                    continue
                site = int(op["addr"])
                register_indirect = bool(re.match(r"^(?:jsr|jmp) \(", opcode))
                pc_indexed_jump = kind == "jump" and "(pc," in opcode
                target = None if register_indirect else (
                    None if pc_indexed_jump else (
                        int(op["jump"]) if "jump" in op else None
                    )
                )
                key = (site, kind, target)
                observation = observations.setdefault(
                    key,
                    {
                        "sources": set(),
                        "opcode": opcode,
                        "source_ranges": [],
                    },
                )
                observation["sources"].add(f"{name}@0x{address:05X}")
                observation["source_ranges"].append((source_start, source_end))

    rows: list[dict[str, str]] = []
    for (site, kind, target), observation in sorted(
        observations.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        sources = sorted(observation["sources"])
        if target is None:
            if site in COMPUTED_TABLES:
                classification = "documented_computed_dispatch"
                confidence = "Verified"
                target_name = COMPUTED_TABLES[site]
            elif site == 0x40494:
                classification = "reset_vector_jump"
                confidence = "Verified"
                target_name = "initial_PC_loaded_from_0x000004"
            elif site == 0x43A18:
                classification = "null_assertion"
                confidence = "Verified"
                target_name = "A0=0"
            else:
                classification = "indirect_call" if kind == "call" else "indirect_jump"
                confidence = "Strong inference"
                target_name = ""
            target_text = ""
        else:
            source_start, source_end = observation["source_ranges"][0]
            target_name, classification, confidence = classify_direct(
                kind, target, documented, symbols, source_start, source_end, os_api
            )
            target_text = f"0x{target:06X}"
        rows.append(
            {
                "site": f"0x{site:05X}",
                "source_entries": ";".join(sources),
                "kind": kind,
                "opcode": str(observation["opcode"]),
                "target": target_text,
                "target_name": target_name,
                "classification": classification,
                "confidence": confidence,
            }
        )
    raw_register_calls = {
        GAME_START + offset
        for offset in range(0, len(rom) - 1, 2)
        if 0x4E90 <= int.from_bytes(rom[offset : offset + 2], "big") <= 0x4E97
    }
    analyzed_register_calls = {
        int(row["site"], 16)
        for row in rows
        if row["kind"] == "call" and not row["target"]
    }
    if analyzed_register_calls != raw_register_calls:
        missing = sorted(raw_register_calls - analyzed_register_calls)
        extra = sorted(analyzed_register_calls - raw_register_calls)
        raise ValueError(
            "register-call opcode reconciliation failed; "
            f"missing={','.join(hex(value) for value in missing)} "
            f"extra={','.join(hex(value) for value in extra)}"
        )
    return rows, failures, len(entries), len(dispatch)


FIELDS = [
    "site", "source_entries", "kind", "opcode", "target", "target_name",
    "classification", "confidence",
]


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
    rows, failures, entry_count, dispatch_count = generated_rows(here.parent)
    report = here / "control_targets.csv"
    failure_report = here / "control_target_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            existing_failures = list(csv.DictReader(stream))
        if existing != rows or existing_failures != failures:
            raise SystemExit("control-target reports are stale; regenerate them")
    else:
        write_csv(report, rows, FIELDS)
        write_csv(failure_report, failures, ["function_address", "name", "error"])
    unresolved = [row for row in rows if row["confidence"] == "Unknown"]
    direct = [row for row in rows if row["target"]]
    indirect = [row for row in rows if not row["target"]]
    print(
        f"control_targets.csv: {entry_count} entries + {dispatch_count} dispatch destinations, "
        f"{len(direct)} direct sites, "
        f"{len(indirect)} indirect sites, "
        f"{len(unresolved)} unresolved, {len(failures)} analysis failures"
    )
    if unresolved or failures:
        raise SystemExit("control-target reconciliation is incomplete")


if __name__ == "__main__":
    main()
