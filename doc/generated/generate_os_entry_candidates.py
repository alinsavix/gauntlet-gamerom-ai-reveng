#!/usr/bin/env python3
"""Discover and reconcile direct OS-ROM callable-entry candidates."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


OS_CODE_START = 0x0300
# The final observed RTS is at 0x5998; 0x599A begins non-code table bytes.
OS_CODE_END = 0x599A
# The second API block has one unused 0xFF-filled six-byte slot at 0x22A.
API_RANGES = ((0x0100, 36), (0x0200, 7), (0x0230, 13))

# process_text_effects dispatches through the six-word signed-offset table at
# 0x2C16.  radare2 correctly stops the parent function at the computed JMP, so
# seed the four callable targets reached from those bounded case blocks.  The
# six inherited-frame case destinations themselves are cataloged separately by
# generate_os_text_contracts.py, just as game-ROM computed destinations are
# kept separate from the callable-function union.
COMPUTED_CASE_CALLEES = {
    0x2D18: "computed_case_call@0x2CCA",
    0x2D78: "computed_case_call@0x2CD6",
    0x2FBE: "computed_case_call@0x2C7C",
    0x3020: "computed_case_call@0x2C96",
}

# Complete normal-stack veneers immediately preceding two register entries.
# They are shipped callable entries even though the OS's own dispatcher enters
# four bytes later with A0 already loaded.
STACK_VENEERS = {
    0x2D14: "stack_veneer_for@0x2D18",
    0x2D74: "stack_veneer_for@0x2D78",
}

# Valid instruction entries found by the later byte-coverage sweep but having
# no incoming vector/API/direct/indirect transfer.  They remain contracted in
# os_residue_contracts.csv and named in the loader; do not turn loader naming
# into false reachability evidence for the active control closure.
BYTE_SWEEP_RESIDUE = {0x0EEE, 0x2FB2, 0x3018, 0x3088, 0x3166}


def loader_entries(text: str) -> dict[int, str]:
    return {
        int(address, 16): name
        for address, name in re.findall(
            r"^af\+ (0x[0-9A-Fa-f]+) ([^\s]+)$", text, re.MULTILINE
        )
        if int(address, 16) < 0x10000
    }


def vector_targets(rom: bytes) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for vector in range(1, 64):
        target = int.from_bytes(rom[vector * 4 : vector * 4 + 4], "big")
        if OS_CODE_START <= target < OS_CODE_END:
            result.setdefault(target, []).append(f"vector_{vector}")
    return result


def api_targets(rom: bytes) -> tuple[dict[int, list[str]], list[dict[str, str]]]:
    result: dict[int, list[str]] = {}
    failures: list[dict[str, str]] = []
    for start, count in API_RANGES:
        for index in range(count):
            entry = start + index * 6
            raw = rom[entry : entry + 6]
            if raw[:2] != b"\x4e\xf9":
                failures.append(
                    {
                        "address": f"0x{entry:04X}",
                        "name": f"api_0x{entry:03X}",
                        "error": f"expected JMP absolute, got {raw.hex()}",
                    }
                )
                continue
            target = int.from_bytes(raw[2:], "big")
            if not (OS_CODE_START <= target < OS_CODE_END):
                failures.append(
                    {
                        "address": f"0x{entry:04X}",
                        "name": f"api_0x{entry:03X}",
                        "error": f"target 0x{target:X} outside executable bounds",
                    }
                )
                continue
            result.setdefault(target, []).append(f"api_0x{entry:03X}")
    return result, failures


def analyze_one(
    root: Path, loader: Path, item: tuple[int, str]
) -> dict[str, object]:
    address, name = item
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader),
        "-c", f"af- 0x{address:x}; af @ 0x{address:x}; s 0x{address:x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [
        line for line in completed.stderr.splitlines()
        if line.startswith(("ERROR", "FATAL"))
    ]
    if completed.returncode or errors:
        return {
            "address": address,
            "name": name,
            "error": "; ".join(errors) or f"r2 exit {completed.returncode}",
        }
    try:
        body = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "address": address,
            "name": name,
            "error": f"invalid pdfj: {exc}",
        }
    return {"address": address, "name": name, "body": body}


def generated_rows(
    root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    loader = doc / "gauntlet_loader.r2"
    names = loader_entries(loader.read_text())
    legacy_names = loader_entries((root / "gauntlet.r2").read_text())
    rom = (root / "row9.bin").read_bytes()
    if len(rom) != 0x10000:
        raise SystemExit(f"row9.bin has unexpected size {len(rom)}")

    evidence: dict[int, set[str]] = {
        address: {"project_loader"}
        for address in names
        if OS_CODE_START <= address < OS_CODE_END and address not in BYTE_SWEEP_RESIDUE
    }
    for address in legacy_names:
        evidence.setdefault(address, set()).add("legacy_loader")
    for address, items in vector_targets(rom).items():
        evidence.setdefault(address, set()).update(items)
    api, failures = api_targets(rom)
    for address, items in api.items():
        evidence.setdefault(address, set()).update(items)
    for address, item in COMPUTED_CASE_CALLEES.items():
        evidence.setdefault(address, set()).add(item)
    for address, item in STACK_VENEERS.items():
        evidence.setdefault(address, set()).add(item)

    analyzed: dict[int, dict[str, object]] = {}
    pending = set(evidence)
    while pending:
        batch = sorted(pending)
        pending.clear()
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = executor.map(
                lambda address: analyze_one(
                    root, loader, (address, names.get(address, f"os_sub_{address:04x}"))
                ),
                batch,
            )
            for result in results:
                address = int(result["address"])
                if "error" in result:
                    failures.append(
                        {
                            "address": f"0x{address:04X}",
                            "name": str(result["name"]),
                            "error": str(result["error"]),
                        }
                    )
                    continue
                body = result["body"]
                assert isinstance(body, dict)
                analyzed[address] = body
                start = int(body.get("addr", address))
                end = start + int(body.get("size", 0))
                ops = list(body.get("ops", []))
                indirect_call_registers = {
                    match.group(1)
                    for op in ops
                    if (
                        match := re.match(
                            r"^(?:jsr|jmp) \((a[0-6])\)$",
                            str(op.get("opcode", "")),
                        )
                    )
                }
                transfers_to_memory_test = any(
                    int(op.get("jump", -1)) in {0x0A2C, 0x0A6A}
                    for op in ops
                )
                for op in ops:
                    op_type = str(op.get("type", ""))
                    opcode = str(op.get("opcode", ""))
                    pointer_match = re.match(
                        r"^(?:lea|movea)\.l 0x([0-9a-fA-F]+)(?:\.l)?, (a[0-6])$",
                        opcode,
                    )
                    if pointer_match:
                        target = int(pointer_match.group(1), 16)
                        register = pointer_match.group(2)
                        is_entry_use = register in indirect_call_registers
                        is_continuation = register == "a4" and transfers_to_memory_test
                        if (
                            (is_entry_use or is_continuation)
                            and OS_CODE_START <= target < OS_CODE_END
                        ):
                            kind = "continuation" if is_continuation else "indirect_call_target"
                            item = f"{kind}@0x{int(op['addr']):04X}"
                            before = target in evidence
                            evidence.setdefault(target, set()).add(item)
                            if not before and target not in analyzed:
                                pending.add(target)
                    if op_type == "call":
                        edge = "direct_call"
                    elif opcode.startswith("jmp "):
                        edge = "tail_jump"
                    else:
                        continue
                    if "jump" not in op:
                        continue
                    target = int(op["jump"])
                    if not (OS_CODE_START <= target < OS_CODE_END):
                        continue
                    if edge == "tail_jump" and start <= target < end:
                        continue
                    item = f"{edge}@0x{int(op['addr']):04X}"
                    before = target in evidence
                    evidence.setdefault(target, set()).add(item)
                    if not before and target not in analyzed:
                        pending.add(target)

    rows: list[dict[str, str]] = []
    for address in sorted(evidence):
        body = analyzed.get(address, {})
        ops = list(body.get("ops", [])) if isinstance(body, dict) else []
        endings = sorted(
            {
                str(op.get("opcode", "")).split(" ", 1)[0]
                for op in ops
                if str(op.get("type", "")) == "ret"
                or str(op.get("opcode", "")).startswith(("rts", "rte", "jmp "))
            }
        )
        rows.append(
            {
                "address": f"0x{address:04X}",
                "name": names.get(address, f"os_sub_{address:04X}"),
                "legacy_loader": "yes" if address in legacy_names else "no",
                "evidence": ";".join(sorted(evidence[address])),
                "analysis_size": str(int(body.get("size", 0))) if body else "",
                "terminators": ";".join(endings),
                "confidence": "Verified" if body else "Unknown",
            }
        )
    return rows, failures


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
    rows, failures = generated_rows(here.parent.parent)
    report = here / "os_entry_candidates.csv"
    failure_report = here / "os_entry_candidate_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_rows = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_rows != rows or old_failures != failures:
            raise SystemExit("OS entry-candidate reports are stale")
    else:
        write_csv(
            report, rows,
            [
                "address", "name", "legacy_loader", "evidence",
                "analysis_size", "terminators", "confidence",
            ],
        )
        write_csv(
            failure_report, failures,
            ["address", "name", "error"],
        )
    new = [row for row in rows if row["legacy_loader"] == "no"]
    print(
        f"OS entry candidates: {len(rows)} implementation/shared roots; "
        f"{len(new)} absent from legacy loader; {len(failures)} analysis failures"
    )
    if failures:
        raise SystemExit("OS entry discovery has analysis failures")


if __name__ == "__main__":
    main()
