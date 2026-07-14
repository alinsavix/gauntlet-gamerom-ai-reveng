#!/usr/bin/env python3
"""Verify contracts for the runtime-dead upper row9 game-support module."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# Inclusive-exclusive byte bounds are also the exact code/data partition.
CONTRACTS = (
    (0x8000, 0x860C, "legacy_monster_object_update", "object-list selector word", "void", "normal stack ABI; module has no Gauntlet II caller", "Walks legacy MOB lists, updates monster/object animation and movement state, and invokes the module's collision/path workers", "302f0006", "jsr 0x470ce"),
    (0x8702, 0x89AA, "legacy_monster_choose_direction", "D2.w object byte offset; inherited A2-A6 VRAM/state bases", "updates object direction/path state; condition codes", "register worker reached only from 0x8000", "Chooses a direction from nearby player positions, validates terrain interactions, and schedules the legacy move/path operation", "41f90090", "bsr.w 0x89e6"),
    (0x89AA, 0x89E6, "legacy_four_cell_occupied_test", "D4.w first cell byte offset; inherited A2 and alternate occupancy base", "condition codes from first clear/occupied result", "register leaf", "Tests four consecutive cells against the primary and alternate occupancy arrays", "41f90090", "tst.w (a2, d4.w)"),
    (0x89E6, 0x8A12, "legacy_position_in_active_bounds", "D4.b horizontal; D5.b vertical", "D4.l=-1 inside wrapped active window; 0 outside", "register leaf", "Checks a wrapped position against the legacy active-screen bounds", "98390090", "moveq 0xff, d4"),
    (0x8A12, 0x8A64, "legacy_set_direction_from_delta", "D2.w object byte offset; D3.w candidate offset; A3/A4 positions; A6 state", "void; direction bits updated in A6[D2]", "register leaf", "Derives one of eight direction encodings from signed horizontal/vertical deltas", "30333000", "andi.w 0xe3ff"),
    (0x8AE8, 0x8B9E, "legacy_moblist_insert", "D1.w destination byte offset; inherited A2/A5/A6 arrays", "void", "register leaf", "Inserts a slot into the legacy depth/list chains while preserving upper link/state fields", "30321000", "lea.l 0x905f80"),
    (0x8C36, 0x8C70, "legacy_move_mob_slot", "D2.w source byte offset; D1.w destination byte offset; A2-A6 arrays", "void", "register shared entry; falls through to 0x8C70", "Inserts the destination, copies the five parallel slot words, repairs link fields, then removes and clears the source", "6100feb0", "move.w (a2, d2.w), (a2, d1.w)"),
    (0x8C70, 0x8D00, "legacy_moblist_remove_and_clear", "D2.w object byte offset; inherited A2-A6 arrays", "void", "register leaf and 0x8C36 fallthrough tail", "Unlinks a slot from both legacy chains, repairs the bucket head, and clears all five parallel slot words", "38352000", "move.w d0, (a2, d2.w)"),
    (0x8D00, 0x8D86, "legacy_moblist_unlink", "D2.w object byte offset; inherited A5/A6 link arrays", "void", "register leaf", "Unlinks a slot and clears only the low link-index fields while preserving upper object state", "38352000", "andi.w 0xfc00"),
    (0x8F38, 0x9006, "legacy_probe_up", "D2.w cell offset; D3.w radius; D4/D5 coordinates; A2-A4 arrays", "D1.w candidate or 0/-1 sentinel; condition codes", "register leaf", "Probes the three cells in the upward direction with wrap-aware coordinate rejection", "0c420080", "bset.b 0x1f, d2"),
    (0x9006, 0x90D2, "legacy_probe_down", "D2.w cell offset; D3.w radius; D4/D5 coordinates; A2-A4 arrays", "D1.w candidate or 0/-1 sentinel; condition codes", "register leaf", "Probes the three cells in the downward direction with wrap-aware coordinate rejection", "0c4207c0", "bset.b 0x1f, d2"),
    (0x90D2, 0x9192, "legacy_probe_left", "D2.w cell offset; D3.w radius; D4/D5 coordinates; A2-A4 arrays", "D1.w candidate or -1 sentinel; condition codes", "register leaf", "Probes left and the two adjacent diagonal cells", "32023001", "bset.b 0x1f, d2"),
    (0x9192, 0x9252, "legacy_probe_right", "D2.w cell offset; D3.w radius; D4/D5 coordinates; A2-A4 arrays", "D1.w candidate or -1 sentinel; condition codes", "register leaf", "Probes right and the two adjacent diagonal cells", "32023001", "bset.b 0x1f, d2"),
    (0x9284, 0x9864, "legacy_recursive_path_move", "D0.w legacy actor-list index; inherited D6/D7 mode and A2-A4 arrays", "D0.w status/move result", "recursive register worker", "Recursively explores neighboring cells, applies proximity/contact tests, and moves the selected legacy actor slot", "3a0041f9", "bsr.w 0x9284"),
    (0x9864, 0x9880, "legacy_test_actor_contact_a", "D1.w cell offset; D5.w actor-list offset", "D0 predicate and condition codes", "register wrapper around stale external target 0x49572", "Converts offsets to indices and invokes the legacy actor-contact predicate", "3f013005", "jsr 0x49572"),
    (0x9880, 0x989C, "legacy_test_actor_contact_b", "D1.w cell offset; D5.w actor-list offset", "D0 predicate and condition codes", "duplicate register wrapper around stale external target 0x49572", "Second identical entry for the legacy actor-contact predicate", "3f013005", "jsr 0x49572"),
    (0x989C, 0x98D8, "legacy_probe_vertical_triplet_up", "D2.w cell; D3/D4 coordinates; A2-A4 arrays", "condition codes; D1 candidate", "register worker", "Tests the upward cell and two horizontal neighbors through the common proximity leaf", "0c42007e", "bsr.b 0x9914"),
    (0x98D8, 0x9914, "legacy_probe_vertical_triplet_down", "D2.w cell; D3/D4 coordinates; A2-A4 arrays", "condition codes; D1 candidate", "register worker", "Tests the downward cell and two horizontal neighbors through the common proximity leaf", "0c4207be", "bsr.b 0x9914"),
    (0x9914, 0x99A0, "legacy_test_cell_proximity", "D1.w candidate; D3/D4 coordinates; A2-A4 arrays", "carry set iff both wrapped coordinate distances are below 0x07C0", "register leaf; also writes four diagnostic delta words", "Rejects an empty/distant cell and records signed and absolute coordinate deltas", "4a721000", "move.w d0, 0x90403c"),
    (0x99A0, 0x99D8, "legacy_probe_horizontal_triplet_left", "D2.w cell; D3/D4 coordinates; A2-A4 arrays", "condition codes; D1 candidate", "register worker", "Tests the left cell and two vertical neighbors through the common proximity leaf", "32023001", "bsr.w 0x9914"),
    (0x99D8, 0x9A10, "legacy_probe_horizontal_triplet_right", "D2.w cell; D3/D4 coordinates; A2-A4 arrays", "condition codes; D1 candidate", "register worker", "Tests the right cell and two vertical neighbors through the common proximity leaf", "32023001", "bsr.w 0x9914"),
)

ANALYSIS_LIMITS = {
    # These entries deliberately share/fall through into the following leaf.
    0x8C36: 0x8D00,
    0x98D8: 0x99A0,
}


def analyze(root: Path, contract: tuple[object, ...]) -> dict[str, object]:
    start = int(contract[0])
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


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rom = (root / "row9.bin").read_bytes()
    failures: list[dict[str, str]] = []
    rows: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        analyses = list(executor.map(lambda item: analyze(root, item), CONTRACTS))
    for contract, analysis in zip(CONTRACTS, analyses):
        start, end, name, arguments, returns, convention, purpose, prefix, required = contract
        start = int(start); end = int(end)
        if rom[start : start + len(str(prefix)) // 2].hex() != prefix:
            failures.append({"address": f"0x{start:04X}", "issue": "byte prefix mismatch"})
        if "error" in analysis:
            failures.append({"address": f"0x{start:04X}", "issue": str(analysis["error"])})
        else:
            body = analysis["body"]
            assert isinstance(body, dict)
            ops = [str(op.get("opcode", "")) for op in body.get("ops", [])]
            addresses = [int(op.get("addr", 0)) for op in body.get("ops", [])]
            if any(op.startswith("invalid") for op in ops):
                failures.append({"address": f"0x{start:04X}", "issue": "invalid instruction in analyzed body"})
            if not any(str(required) in op for op in ops):
                failures.append({"address": f"0x{start:04X}", "issue": f"required instruction absent: {required}"})
            analysis_limit = ANALYSIS_LIMITS.get(start, end)
            if not addresses or min(addresses) != start or max(addresses) >= analysis_limit:
                failures.append({"address": f"0x{start:04X}", "issue": "analysis escaped declared code range"})
        rows.append({
            "address": f"0x{start:04X}",
            "end_exclusive": f"0x{end:04X}",
            "size_bytes": str(end - start),
            "name": str(name),
            "purpose": str(purpose),
            "arguments": str(arguments),
            "return": str(returns),
            "exceptional_convention": str(convention),
            "reachability": "No incoming transfer from active OS or supplied Gauntlet II main ROM",
            "confidence": "Strong inference",
        })
    return rows, failures


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rows, failures = generated(here.parent)
    report = here / "os_legacy_module_contracts.csv"
    failure_report = here / "os_legacy_module_contract_failures.csv"
    fields = ("address", "end_exclusive", "size_bytes", "name", "purpose", "arguments", "return", "exceptional_convention", "reachability", "confidence")
    if args.check:
        if read_csv(report) != rows or read_csv(failure_report) != failures:
            raise SystemExit("OS legacy-module reports are stale")
    else:
        write_csv(report, rows, fields); write_csv(failure_report, failures, ("address", "issue"))
    print(f"OS legacy module: {len(rows)} contracts; {len(failures)} failures")
    if failures:
        raise SystemExit("OS legacy-module contract verification failed")


if __name__ == "__main__":
    main()
