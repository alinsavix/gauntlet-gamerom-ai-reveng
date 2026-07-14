#!/usr/bin/env python3
"""Generate and verify OS text/display callable and dispatch contracts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# kind, address, name, purpose, arguments, return, exceptional convention,
# byte prefix.  "dispatch" rows are inherited-frame computed-JMP cases rather
# than independent functions, so they receive bounded single-op validation.
ROWS = (
    ("callable", 0x2B3C, "process_text_effects", "Advance full-screen scrolling and all four timed text-effect slots", "void", "void", "normally called once per OS VBLANK", "48e73020"),
    ("dispatch", 0x2C22, "text_effect_case_timed_clear", "Type 1: deactivate the slot and clear its descriptor chain", "inherited D0.w=2*slot; D2.w=slot; A2=0x904F00", "returns through process_text_effects loop", "computed-dispatch entry; inherits parent saved-register frame", "42322018"),
    ("dispatch", 0x2C32, "text_effect_case_blink", "Type 2: alternate the complete descriptor chain between clear and drawn states", "inherited D0.w=2*slot; D2.w=slot; A2=0x904F00", "returns through process_text_effects loop", "computed-dispatch entry; inherits parent saved-register frame", "4a32202c"),
    ("dispatch", 0x2C64, "text_effect_case_progressive_draw", "Type 3: draw the next string character and advance/chains on its terminator", "inherited D0.w=2*slot; D2.w=slot; A2=0x904F00", "returns through process_text_effects loop", "computed-dispatch entry; inherits parent saved-register frame", "7200"),
    ("dispatch", 0x2C82, "text_effect_case_progressive_clear", "Type 4: clear the next string character and advance/chains on its terminator", "inherited D0.w=2*slot; D2.w=slot; A2=0x904F00", "returns through process_text_effects loop", "computed-dispatch entry; inherits parent saved-register frame", "7200"),
    ("dispatch", 0x2CC4, "text_effect_case_rotate_forward", "Type 5: rotate each selected descriptor line in the first direction", "inherited D0.w=2*slot; D2.w=slot; A2=0x904F00", "returns through process_text_effects loop", "computed-dispatch entry; inherits parent saved-register frame", "d040"),
    ("dispatch", 0x2CD0, "text_effect_case_rotate_reverse", "Type 6: rotate each selected descriptor line in the opposite direction", "inherited D0.w=2*slot; D2.w=slot; A2=0x904F00", "returns through process_text_effects loop", "computed-dispatch entry; inherits parent saved-register frame", "d040"),
    ("callable", 0x2D14, "rotate_text_line_forward", "Rotate every descriptor-selected alpha line one cell in the first direction with wrap", "descriptor pointer", "void", "normal-stack veneer over the A0 register body", "206f0004"),
    ("callable", 0x2D18, "rotate_text_line_forward_register", "Rotate every descriptor-selected alpha line one cell in the first direction with wrap", "A0=descriptor pointer", "void", "register entry used by text-effect type 5", "43f900905000"),
    ("callable", 0x2D74, "rotate_text_line_reverse", "Rotate every descriptor-selected alpha line one cell in the opposite direction with wrap", "descriptor pointer", "void", "normal-stack veneer over the A0 register body", "206f0004"),
    ("callable", 0x2D78, "rotate_text_line_reverse_register", "Rotate every descriptor-selected alpha line one cell in the opposite direction with wrap", "A0=descriptor pointer", "void", "register entry used by text-effect type 6", "43f900905000"),
    ("callable", 0x2DDE, "scroll_alpha_surface_one_step", "Shift the visible alpha surface one cell and clear the newly exposed edge", "void", "void", "frameless internal entry", "2f02"),
    ("callable", 0x2E36, "display_text", "Draw a chained text descriptor at its current full-screen scroll offset", "descriptor pointer; color/style word", "void", "normal API implementation", "322f000a"),
    ("callable", 0x2E3E, "display_text_register", "Draw a chained text descriptor at its current full-screen scroll offset", "A0=descriptor pointer; D1.w=color/style", "void", "register entry used by the effect engine", "48e72020"),
    ("callable", 0x2F04, "draw_string", "Draw one NUL-terminated string at an alpha coordinate", "coordinate byte 0; coordinate byte 1; string pointer; color/style word", "D0.l=source bytes consumed including NUL", "normal API implementation", "4a7900904f0e"),
    ("callable", 0x2F3C, "draw_string_register", "Draw one NUL-terminated string from a precomputed alpha offset", "D0.w=alpha byte offset; D1.w=color/style; A0=string; A1=word stride", "D0.l=source bytes consumed including NUL", "register entry", "2f02"),
    ("callable", 0x2FBE, "draw_text_effect_next_char", "Draw one indexed character for progressive effect type 3", "A0=descriptor; D0.w=character index; D1.w=color/style", "D0.l=3 while a character was drawn; 0 at NUL", "register entry; constructs coordinate slots for 0x304E", "22680002"),
    ("callable", 0x3020, "clear_text_effect_next_char", "Clear one indexed character position for progressive effect type 4", "A0=descriptor; D0.w=character index", "D0.l=4 while a character was cleared; 0 at NUL", "register entry; constructs coordinate slots for 0x304E", "22680002"),
    ("callable", 0x3044, "write_alpha_char", "Write one character/tile plus attributes at an alpha coordinate", "coordinate byte 0; coordinate byte 1; character word; color/style word", "void", "normal API implementation", "7000"),
    ("callable", 0x304E, "write_alpha_char_register", "Write one precombined character/tile plus attributes at an alpha coordinate", "D0.w=character/tile; D1.w=color/style; coordinate bytes in caller stack at +7/+11", "void", "shared register/stack body", "0241fffc"),
    ("callable", 0x308C, "clear_text_descriptor_chain", "Clear all visible non-NUL character cells in a chained text descriptor", "A0=descriptor pointer", "void", "register entry used by stop/effect paths", "48e70030"),
    ("callable", 0x3122, "start_text_line_rotation", "Allocate type 5 or 6 cyclic line rotation according to interval sign", "descriptor pointer; color/style word; signed interval word", "D0.l=1 allocated; 0 no free slot", "normal API wrapper into 0x3172", "7006"),
    ("callable", 0x3130, "init_fullscreen_text_scroll", "Initialize and allocate type 7 full-alpha scrolling", "descriptor pointer; color/style word; interval word", "D0.l=1 allocated; 0 no free slot", "normal API wrapper; also stores active flag and interval", "7007"),
    ("callable", 0x3156, "start_progressive_text_clear", "Allocate type 4 progressive character clearing", "descriptor pointer; interval word", "D0.l=1 allocated; 0 no free slot", "two-argument API wrapper; forces stored color to zero", "7004"),
    ("callable", 0x3162, "start_blink_text", "Allocate type 2 whole-descriptor blinking", "descriptor pointer; color/style word; interval word", "D0.l=1 allocated; 0 no free slot", "normal API wrapper into 0x3172", "7002"),
    ("callable", 0x3168, "start_timed_text", "Draw a descriptor and allocate type 1 timed removal", "descriptor pointer; color/style word; interval word", "D0.l=1 allocated; 0 no free slot", "normal API wrapper into 0x3172", "7001"),
    ("callable", 0x316C, "start_progressive_text", "Allocate type 3 progressive character drawing", "descriptor pointer; color/style word; interval word", "D0.l=1 allocated; 0 no free slot", "normal API wrapper into 0x3172", "7003"),
    ("callable", 0x3172, "allocate_text_effect", "Find a free one of four slots and initialize its type, interval, color, counters, and descriptor", "D0.b=type; D1.w=interval; descriptor and color in normal stack slots", "D0.l=1 allocated; 0 no free slot", "shared mixed register/stack entry", "48e72020"),
    ("callable", 0x31D2, "display_large_text", "Render mapped large-font glyphs for a chained descriptor", "descriptor pointer", "D0.l=total alpha-cell advance", "normal API implementation", "48e72038"),
    ("callable", 0x324E, "render_large_glyph_register", "Render one mapped large glyph in the orientation selected by A0", "D0.w=glyph index; D1.w=color/style; A0=packed strides; A1=alpha destination", "D0.w=alpha-cell advance (1 or 2); A1 advanced", "register entry", "48e72020"),
    ("callable", 0x3522, "init_alpha_display", "Select orientation, reset text effects, and clear the visible alpha surface", "void", "void", "normal API implementation", "7000"),
    ("callable", 0x355C, "reset_text_effects", "Reset full-screen scroll state and all four text-effect slot types/descriptors", "void", "void", "frameless internal entry", "41f900904f18"),
)


def analyze(root: Path, loader: Path, row: tuple[object, ...]) -> dict[str, str]:
    kind, address, name, *_ = row
    r2_command = "pdj 1" if kind == "dispatch" else "pdfj"
    setup = f"s 0x{int(address):x}; {r2_command}"
    if kind != "dispatch":
        setup = f"af- 0x{int(address):x}; af @ 0x{int(address):x}; {setup}"
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", str(loader), "-c", setup,
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [line for line in completed.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))]
    if completed.returncode or errors:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        body = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": f"invalid r2 JSON: {exc}"}
    if kind == "dispatch":
        valid = isinstance(body, list) and body and int(body[0].get("addr", -1)) == int(address) and str(body[0].get("type", "")) != "ill"
    else:
        valid = isinstance(body, dict) and int(body.get("addr", -1)) == int(address) and int(body.get("size", 0)) > 0 and not any(str(op.get("type", "")) == "ill" for op in body.get("ops", []))
    if not valid:
        return {"address": f"0x{int(address):04X}", "name": str(name), "error": "empty, invalid, or misbased analysis body"}
    return {}


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rom = (root / "row9.bin").read_bytes()
    records: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for kind, address, name, purpose, arguments, returns, convention, prefix in ROWS:
        actual = rom[address : address + len(prefix) // 2].hex()
        if actual != prefix:
            failures.append({"address": f"0x{address:04X}", "name": name, "error": f"byte prefix {actual} != {prefix}"})
        records.append({"kind": kind, "address": f"0x{address:04X}", "name": name, "purpose": purpose, "arguments": arguments, "return": returns, "exceptional_convention": convention, "confidence": "Verified"})
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
    report = here / "os_text_contracts.csv"
    failure_report = here / "os_text_contract_failures.csv"
    if args.check:
        with report.open(newline="") as stream:
            old_records = list(csv.DictReader(stream))
        with failure_report.open(newline="") as stream:
            old_failures = list(csv.DictReader(stream))
        if old_records != records or old_failures != failures:
            raise SystemExit("OS text contract reports are stale")
    else:
        write_csv(report, records, ["kind", "address", "name", "purpose", "arguments", "return", "exceptional_convention", "confidence"])
        write_csv(failure_report, failures, ["address", "name", "error"])
    print(f"OS text contracts: {len(records)} entries; {len(failures)} verification failures")
    if failures:
        raise SystemExit("OS text contract verification failed")


if __name__ == "__main__":
    main()
