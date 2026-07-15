#!/usr/bin/env python3
"""Reconcile direct, register-indirect, and computed OS control transfers."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


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


def latest_register_source(ops: list[dict[str, object]], index: int, register: str) -> tuple[str, int | None]:
    for op in reversed(ops[:index]):
        opcode = str(op.get("opcode", ""))
        if not re.search(rf", {register}$", opcode):
            continue
        immediate = re.match(r"^(?:lea|movea)\.l 0x([0-9a-fA-F]+)(?:\.l)?, " + register + r"$", opcode)
        return opcode, int(immediate.group(1), 16) if immediate else None
    return "caller/inherited register", None


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    union = read_csv(doc / "generated" / "os_callable_contracts.csv")
    implementations = [row for row in union if row["entry_kind"] == "implementation"]
    names = {int(row["address"], 16): row["name"] for row in union}
    api = {int(row["address"], 16) for row in union if row["entry_kind"] == "api_veneer"}
    roots = {int(row["address"], 16) for row in implementations}
    dispatch = {int(row["address"], 16) for row in union if row["entry_kind"] == "computed_dispatch"}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        analyses = list(executor.map(lambda row: analyze(root, int(row["address"], 16), row["name"]), implementations))

    collected: dict[tuple[int, str, str, str], dict[str, object]] = {}
    for result in analyses:
        if "error" in result:
            failures.append({"site": f"0x{int(result['address']):04X}", "owner": str(result["name"]), "issue": str(result["error"])})
            continue
        body = result["body"]
        assert isinstance(body, dict)
        ops = list(body.get("ops", []))
        owner = str(result["name"])
        for index, op in enumerate(ops):
            opcode = str(op.get("opcode", ""))
            match = re.match(r"^(jsr|jmp) (.+)$", opcode)
            if not match:
                continue
            kind, operand = match.groups()
            site = int(op.get("addr", 0))
            target_text = ""
            target_name = ""
            source = ""
            classification = ""
            target: int | None = None

            register_match = re.fullmatch(r"\((a[0-6])\)", operand)
            if site == 0x2C12:
                source = "signed-word offset table at 0x2C16"
                classification = "text_effect_computed_dispatch"
                target_text = ";".join(f"0x{x:04X}" for x in sorted(dispatch))
                target_name = ";".join(names[x] for x in sorted(dispatch))
            elif register_match:
                register = register_match.group(1)
                source, target = latest_register_source(ops, index, register)
                if target is not None:
                    target_text = f"0x{target:05X}" if target >= 0x10000 else f"0x{target:04X}"
                    target_name = names.get(target, "")
                    if target in roots:
                        classification = "constant_internal_root"
                    elif target in api:
                        classification = "constant_api_veneer"
                    elif 0x40000 <= target <= 0x4005A:
                        classification = "constant_game_header_hook"
                    else:
                        classification = "constant_external_target"
                elif owner.startswith("mem_test_") or owner == "display_working_ram_error":
                    classification = "inherited_memory_test_continuation"
                else:
                    classification = "dynamic_register_call"
            elif operand.startswith("("):
                source = operand
                if site == 0x2C12:
                    classification = "text_effect_computed_dispatch"
                    target_text = ";".join(f"0x{x:04X}" for x in sorted(dispatch))
                    target_name = ";".join(names[x] for x in sorted(dispatch))
                else:
                    classification = "computed_control_transfer"
            else:
                if "jump" in op:
                    target = int(op["jump"])
                else:
                    number = re.search(r"0x([0-9a-fA-F]+)", operand)
                    target = int(number.group(1), 16) if number else None
                if target is not None:
                    target_text = f"0x{target:05X}" if target >= 0x10000 else f"0x{target:04X}"
                    target_name = names.get(target, "")
                    if target in roots:
                        classification = "direct_internal_root"
                    elif target in dispatch:
                        classification = "direct_computed_case"
                    elif target in api:
                        classification = "direct_api_veneer"
                    elif 0x300 <= target < 0x599A:
                        classification = "direct_internal_nonroot"
                    elif 0x40000 <= target <= 0x4005A:
                        classification = "direct_game_header_hook"
                    else:
                        classification = "direct_external_target"
            key = (site, kind, opcode, target_text)
            item = collected.setdefault(key, {
                "site": site, "owners": set(), "kind": kind, "opcode": opcode,
                "target": target_text, "target_name": target_name,
                "source": source, "classification": classification,
            })
            owners = item["owners"]
            assert isinstance(owners, set)
            owners.add(owner)

            if classification in {"direct_internal_nonroot", "computed_control_transfer", "constant_external_target"}:
                failures.append({"site": f"0x{site:04X}", "owner": owner, "issue": f"unreconciled {classification}: {opcode} ({source})"})

    rows: list[dict[str, str]] = []
    for item in sorted(collected.values(), key=lambda value: (int(value["site"]), str(value["opcode"]))):
        owners = item["owners"]
        assert isinstance(owners, set)
        rows.append({
            "site": f"0x{int(item['site']):04X}",
            "owners": ";".join(sorted(owners)),
            "kind": str(item["kind"]),
            "opcode": str(item["opcode"]),
            "target": str(item["target"]),
            "target_name": str(item["target_name"]),
            "register_source": str(item["source"]),
            "classification": str(item["classification"]),
            "confidence": "Verified",
        })
    return rows, failures


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
    rows, failures = generated(here.parent.parent)
    report = here / "os_control_targets.csv"
    failure_report = here / "os_control_target_failures.csv"
    if args.check:
        if read_csv(report) != rows or read_csv(failure_report) != failures:
            raise SystemExit("OS control-target reports are stale")
    else:
        write_csv(report, rows, ["site", "owners", "kind", "opcode", "target", "target_name", "register_source", "classification", "confidence"])
        write_csv(failure_report, failures, ["site", "owner", "issue"])
    print(f"OS control targets: {len(rows)} unique sites; {len(failures)} failures")
    if failures:
        raise SystemExit("OS control-target reconciliation failed")


if __name__ == "__main__":
    main()
